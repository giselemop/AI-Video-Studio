using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using MySqlConnector;

namespace VideoStudio.Server;

public sealed record LlmBudgetDecision(
    bool Allowed,
    string? Error,
    int PromptChars,
    int MaxTokens,
    long UsedPromptChars,
    long UsedMaxTokens,
    long DailyPromptCharBudget,
    long DailyTokenBudget,
    int TimeoutMs);

public sealed record LlmAuditReservation(long Id, int TimeoutMs);

public sealed record LlmRequestPreview(
    bool Allowed,
    string Provider,
    string Host,
    string Model,
    string? Error,
    string RedactedPreview,
    LlmBudgetDecision Budget);

public sealed class LlmRedirectBlockedException : HttpRequestException
{
    public LlmRedirectBlockedException(string message) : base(message) { }
}

/// <summary>
/// Budget reservation and append-only egress audit. The short MySQL advisory
/// lock serializes reservations across processes; Reserved rows conservatively
/// count until their 24-hour window expires.
/// </summary>
public sealed class LlmEgressAuditService
{
    private const string BudgetLockName = "ai-video-studio:llm-egress-budget";
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly ILogger<LlmEgressAuditService> _logger;

    public LlmEgressAuditService(StudioSettings settings, StudioRepository repository, ILogger<LlmEgressAuditService> logger)
    {
        _settings = settings;
        _repository = repository;
        _logger = logger;
    }

    public async Task<LlmBudgetDecision> CheckAsync(int promptChars, int maxTokens, CancellationToken ct = default)
    {
        promptChars = Math.Max(0, promptChars);
        maxTokens = Math.Max(0, maxTokens);
        var limits = await LoadLimitsAsync(ct);
        if (promptChars > limits.MaxPromptChars) return new(false, "LLM prompt exceeds the per-request character budget", promptChars, maxTokens, 0, 0, limits.DailyPromptChars, limits.DailyTokens, limits.TimeoutMs);
        if (maxTokens > limits.MaxTokens) return new(false, "LLM max_tokens exceeds the per-request token budget", promptChars, maxTokens, 0, 0, limits.DailyPromptChars, limits.DailyTokens, limits.TimeoutMs);
        try
        {
            await using var connection = await OpenAsync(ct);
            var used = await ReadUsageAsync(connection, ct);
            var allowed = used.PromptChars + promptChars <= limits.DailyPromptChars && used.MaxTokens + maxTokens <= limits.DailyTokens;
            return new(allowed, allowed ? null : "LLM daily budget would be exceeded", promptChars, maxTokens, used.PromptChars, used.MaxTokens, limits.DailyPromptChars, limits.DailyTokens, limits.TimeoutMs);
        }
        catch (MySqlException ex)
        {
            _logger.LogWarning(ex, "LLM budget audit schema is unavailable; egress is blocked");
            return new(false, "LLM budget/audit schema is not ready", promptChars, maxTokens, 0, 0, limits.DailyPromptChars, limits.DailyTokens, limits.TimeoutMs);
        }
    }

    public async Task<LlmAuditReservation?> ReserveAsync(string provider, string host, string model, int promptChars, int maxTokens, string preview, CancellationToken ct = default)
    {
        var limits = await LoadLimitsAsync(ct);
        if (promptChars > limits.MaxPromptChars || maxTokens > limits.MaxTokens) return null;
        await using var connection = await OpenAsync(ct);
        var locked = Convert.ToInt32(await ScalarAsync(connection, "SELECT GET_LOCK(@name,5)", ("@name", BudgetLockName), ct), System.Globalization.CultureInfo.InvariantCulture) == 1;
        if (!locked) throw new InvalidOperationException("LLM budget lock could not be acquired");
        try
        {
            var used = await ReadUsageAsync(connection, ct);
            if (used.PromptChars + promptChars > limits.DailyPromptChars || used.MaxTokens + maxTokens > limits.DailyTokens)
            {
                await InsertAsync(connection, provider, host, model, promptChars, maxTokens, "BudgetRejected", null, "LLM daily budget exceeded", null, preview, limits.TimeoutMs, ct);
                return null;
            }
            var id = await InsertAsync(connection, provider, host, model, promptChars, maxTokens, "Reserved", null, null, null, preview, limits.TimeoutMs, ct);
            return new LlmAuditReservation(id, limits.TimeoutMs);
        }
        finally
        {
            try { await ScalarAsync(connection, "SELECT RELEASE_LOCK(@name)", ("@name", BudgetLockName), CancellationToken.None); } catch { }
        }
    }

    public async Task CompleteAsync(long auditId, string outcome, long durationMs, string? errorCode, int redirectCount = 0, CancellationToken ct = default)
    {
        try
        {
            await using var connection = await OpenAsync(ct);
            await using var command = new MySqlCommand("UPDATE llm_egress_audit SET outcome=@outcome,duration_ms=@duration,error_code=@error,redirect_count=@redirect WHERE id=@id AND outcome='Reserved'", connection);
            Add(command, "@outcome", outcome); Add(command, "@duration", Math.Max(0, durationMs)); Add(command, "@error", errorCode); Add(command, "@redirect", Math.Clamp(redirectCount, 0, 8)); Add(command, "@id", auditId);
            await command.ExecuteNonQueryAsync(ct);
        }
        catch (Exception ex) { _logger.LogWarning(ex, "Unable to finalize LLM egress audit {AuditId}", auditId); }
    }

    public async Task RecordRejectedAsync(string provider, string host, string model, int promptChars, int maxTokens, string error, string preview, CancellationToken ct = default)
    {
        try
        {
            await using var connection = await OpenAsync(ct);
            await InsertAsync(connection, provider, host, model, promptChars, maxTokens, "Rejected", null, error, null, preview, null, ct);
        }
        catch (Exception ex) { _logger.LogWarning(ex, "Unable to record rejected LLM egress"); }
    }

    public static string RedactedPreview(string systemPrompt, string userPrompt, string provider, string host, string model)
    {
        static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()[..16];
        return $"provider={provider};host={host};model={model};system_chars={systemPrompt.Length};user_chars={userPrompt.Length};system_sha256={Hash(systemPrompt)};user_sha256={Hash(userPrompt)};content=[REDACTED]";
    }

    private async Task<(long PromptChars, long MaxTokens)> ReadUsageAsync(MySqlConnection connection, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"SELECT COALESCE(SUM(prompt_chars),0),COALESCE(SUM(max_tokens),0) FROM llm_egress_audit
            WHERE created_at >= UTC_TIMESTAMP() - INTERVAL 24 HOUR AND outcome IN ('Reserved','Succeeded','Failed','Timeout')", connection);
        await using var reader = await command.ExecuteReaderAsync(ct);
        return await reader.ReadAsync(ct) ? (reader.GetInt64(0), reader.GetInt64(1)) : (0, 0);
    }

    private async Task<(int MaxPromptChars, int MaxTokens, long DailyPromptChars, long DailyTokens, int TimeoutMs)> LoadLimitsAsync(CancellationToken ct)
    {
        var maxPrompt = await SettingIntAsync("llm.max_prompt_chars", 640 * 1024, ct);
        var maxTokens = await SettingIntAsync("llm.max_tokens", 3000, ct);
        var dailyChars = await SettingLongAsync("llm.daily_prompt_char_budget", 2_000_000, ct);
        var dailyTokens = await SettingLongAsync("llm.daily_token_budget", 100_000, ct);
        var timeout = Math.Clamp(await SettingIntAsync("llm.timeout_ms", 120_000, ct), 1_000, 600_000);
        return (Math.Clamp(maxPrompt, 1, 640 * 1024), Math.Clamp(maxTokens, 1, 16_000), Math.Max(1, dailyChars), Math.Max(1, dailyTokens), timeout);
    }

    private async Task<int> SettingIntAsync(string key, int fallback, CancellationToken ct)
        => int.TryParse(await _repository.GetSettingAsync(key, ct), out var value) ? value : fallback;

    private async Task<long> SettingLongAsync(string key, long fallback, CancellationToken ct)
        => long.TryParse(await _repository.GetSettingAsync(key, ct), out var value) ? value : fallback;

    private async Task<MySqlConnection> OpenAsync(CancellationToken ct)
    {
        var connection = new MySqlConnection(_settings.DatabaseConnectionString);
        await connection.OpenAsync(ct);
        return connection;
    }

    private static async Task<long> InsertAsync(MySqlConnection connection, string provider, string host, string model, int promptChars, int maxTokens, string outcome, long? duration, string? error, string? requestId, string preview, int? timeoutMs, CancellationToken ct)
    {
        await using var command = new MySqlCommand(@"INSERT INTO llm_egress_audit(provider,host,model,prompt_chars,max_tokens,outcome,duration_ms,error_code,request_id,redacted_preview,redirect_count,timeout_ms)
            VALUES(@provider,@host,@model,@prompt,@tokens,@outcome,@duration,@error,@request,@preview,0,@timeout)", connection);
        Add(command, "@provider", Limit(provider, 64)); Add(command, "@host", Limit(host, 255)); Add(command, "@model", Limit(model, 255)); Add(command, "@prompt", promptChars); Add(command, "@tokens", maxTokens); Add(command, "@outcome", Limit(outcome, 32)); Add(command, "@duration", duration); Add(command, "@error", Limit(error, 64)); Add(command, "@request", Limit(requestId, 128)); Add(command, "@preview", Limit(preview, 4000)); Add(command, "@timeout", timeoutMs);
        await command.ExecuteNonQueryAsync(ct);
        return command.LastInsertedId;
    }

    private static async Task<object?> ScalarAsync(MySqlConnection connection, string sql, (string Name, object Value) parameter, CancellationToken ct)
    {
        await using var command = new MySqlCommand(sql, connection); Add(command, parameter.Name, parameter.Value); return await command.ExecuteScalarAsync(ct);
    }

    private static void Add(MySqlCommand command, string name, object? value) => command.Parameters.AddWithValue(name, value ?? DBNull.Value);
    private static string? Limit(string? value, int max) => string.IsNullOrWhiteSpace(value) ? null : value.Length <= max ? value : value[..max];
}

public sealed class AuditedLlmProvider : ILLMProvider
{
    private readonly ILLMProvider _inner;
    private readonly LlmEgressAuditService _audit;
    private readonly string _host;
    private readonly string _model;

    public AuditedLlmProvider(ILLMProvider inner, LlmEgressAuditService audit, string host, string model)
    {
        _inner = inner; _audit = audit; _host = host; _model = model; Name = inner.Name;
    }

    public string Name { get; }

    public async Task<string> CompleteAsync(string systemPrompt, string userPrompt, decimal temperature, int maxTokens, CancellationToken ct = default)
    {
        var promptChars = checked(systemPrompt.Length + userPrompt.Length);
        var preview = LlmEgressAuditService.RedactedPreview(systemPrompt, userPrompt, Name, _host, _model);
        var reservation = await _audit.ReserveAsync(Name, _host, _model, promptChars, maxTokens, preview, ct);
        if (reservation is null)
        {
            await _audit.RecordRejectedAsync(Name, _host, _model, promptChars, maxTokens, "LLM_BUDGET_EXCEEDED", preview, ct);
            throw new InvalidOperationException("LLM request exceeds the configured budget");
        }
        var stopwatch = Stopwatch.StartNew();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(reservation.TimeoutMs);
        try
        {
            var result = await _inner.CompleteAsync(systemPrompt, userPrompt, temperature, maxTokens, timeout.Token);
            await _audit.CompleteAsync(reservation.Id, "Succeeded", stopwatch.ElapsedMilliseconds, null, ct: CancellationToken.None);
            return result;
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested && timeout.IsCancellationRequested)
        {
            await _audit.CompleteAsync(reservation.Id, "Timeout", stopwatch.ElapsedMilliseconds, "LLM_TIMEOUT", ct: CancellationToken.None);
            throw new TimeoutException("LLM request exceeded its configured timeout");
        }
        catch (Exception ex)
        {
            await _audit.CompleteAsync(reservation.Id, "Failed", stopwatch.ElapsedMilliseconds, Classify(ex), ex is LlmRedirectBlockedException ? 1 : 0, CancellationToken.None);
            throw;
        }
    }

    private static string Classify(Exception ex) => ex switch { TimeoutException => "LLM_TIMEOUT", LlmRedirectBlockedException => "LLM_REDIRECT_BLOCKED", HttpRequestException => "LLM_HTTP", JsonException => "LLM_RESPONSE", _ => "LLM_FAILED" };
}
