using System.Collections.Concurrent;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Http;

namespace VideoStudio.Server;

public sealed record LocalAuthPrincipal(long SessionId, string Username, string Role, DateTime ExpiresAt);

public sealed record LocalAuthDecision(bool Allowed, int StatusCode, string? Error, string Outcome, LocalAuthPrincipal? Principal = null);

public sealed record LocalAuthStatus(bool Configured, bool Authenticated, bool SetupAllowed, string? Username = null, string? Role = null, string? CsrfToken = null, DateTime? ExpiresAt = null, bool LoginRequired = true, string AccessMode = "Password");

public sealed record LocalAuthLoginResult(bool Succeeded, int StatusCode, string? Error, string Outcome, LocalAuthPrincipal? Principal = null, string? SessionToken = null, string? CsrfToken = null);

/// <summary>
/// Local and explicitly trusted-LAN administrator authentication. Session and
/// CSRF secrets are stored as hashes; the browser only receives an HttpOnly
/// session cookie and an in-memory CSRF token. No password or raw session
/// secret is logged.
/// </summary>
public sealed class LocalAuthService
{
    public const string SessionCookieName = "ai_video_studio_session";
    public const string CsrfCookieName = "ai_video_studio_csrf";
    public const string CsrfHeaderName = "X-CSRF-Token";
    public const string PrincipalItemKey = "videoStudio.localAuthPrincipal";

    private static readonly string[] DefaultAllowedOrigins =
    {
        "http://127.0.0.1:18080", "http://localhost:18080", "http://127.0.0.1:18081", "http://localhost:18081"
    };
    private static readonly Regex UsernamePattern = new(@"^[\p{L}\p{N}._-]{3,64}$", RegexOptions.CultureInvariant);
    private readonly StudioSettings _settings;
    private readonly StudioRepository _repository;
    private readonly ILogger<LocalAuthService> _logger;
    private readonly HashSet<string> _allowedOrigins;
    private readonly IReadOnlyList<TrustedNetwork> _trustedNetworks;
    private readonly object _configurationLock = new();
    private readonly SemaphoreSlim _setupGate = new(1, 1);
    private readonly ConcurrentDictionary<string, LoginThrottle> _loginAttempts = new(StringComparer.Ordinal);
    private string _username;
    private string _password;
    private string _passwordHash;
    private readonly byte[] _localCsrfKey = RandomNumberGenerator.GetBytes(32);

    public LocalAuthService(StudioSettings settings, StudioRepository repository, ILogger<LocalAuthService> logger)
    {
        _settings = settings;
        _repository = repository;
        _logger = logger;
        _allowedOrigins = new HashSet<string>(DefaultAllowedOrigins, StringComparer.OrdinalIgnoreCase);
        foreach (var origin in SplitConfigurationValues(Environment.GetEnvironmentVariable("AI_VIDEO_STUDIO_ALLOWED_ORIGINS")))
            _allowedOrigins.Add(origin);
        _trustedNetworks = SplitConfigurationValues(Environment.GetEnvironmentVariable("AI_VIDEO_STUDIO_TRUSTED_NETWORKS"))
            .Select(TryParseTrustedNetwork)
            .Where(network => network is not null)
            .Select(network => network!.Value)
            .ToArray();
        _username = settings.AdminUsername.Trim();
        _password = settings.AdminPassword;
        _passwordHash = settings.AdminPasswordHash;
    }

    public bool IsConfigured
    {
        get
        {
            var snapshot = ConfigurationSnapshot();
            return !string.IsNullOrWhiteSpace(snapshot.Username) && (!string.IsNullOrWhiteSpace(snapshot.Password) || !string.IsNullOrWhiteSpace(snapshot.PasswordHash));
        }
    }

    public async Task<LocalAuthStatus> StatusAsync(HttpContext context, CancellationToken ct = default)
    {
        if (!_settings.RequireLocalLogin)
        {
            if (!IsAllowedLocalModeRequest(context)) return new LocalAuthStatus(IsConfigured, false, false, AccessMode: "OriginRejected");
            var expiresAt = DateTime.UtcNow.AddHours(8);
            var payload = $"{NewToken()}.{new DateTimeOffset(expiresAt).ToUnixTimeSeconds()}";
            var signature = Convert.ToHexString(HMACSHA256.HashData(_localCsrfKey, Encoding.UTF8.GetBytes(payload)));
            return new LocalAuthStatus(IsConfigured, false, false, "local-operator", "LocalOperator", $"{payload}.{signature}", expiresAt, false, "LocalOnly");
        }
        if (!IsConfigured) return new LocalAuthStatus(false, false, IsLoopbackRequest(context));

        var decision = await AuthenticateAsync(context, false, ct);
        if (!decision.Allowed || decision.Principal is null) return new LocalAuthStatus(true, false, false);

        var csrfToken = NewToken();
        var updated = await _repository.RotateAdminSessionCsrfAsync(decision.Principal.SessionId, HashToken(csrfToken), ct);
        if (updated != 1) return new LocalAuthStatus(true, false, false);

        return new LocalAuthStatus(true, true, false, decision.Principal.Username, decision.Principal.Role, csrfToken, decision.Principal.ExpiresAt);
    }

    public async Task<LocalAuthLoginResult> LoginAsync(HttpContext context, LocalLoginInput input, CancellationToken ct = default)
    {
        if (!_settings.RequireLocalLogin) return new(false, StatusCodes.Status409Conflict, "当前使用本机免登录模式，无需登录", "LocalOnly");
        if (!IsTrustedRequest(context) || !HasAllowedOrigin(context))
            return new LocalAuthLoginResult(false, StatusCodes.Status403Forbidden, "仅允许本机页面登录", "OriginRejected");
        if (!IsConfigured)
            return new LocalAuthLoginResult(false, StatusCodes.Status503ServiceUnavailable, "尚未创建本机管理员账号，请先完成初始化", "SetupRequired");

        var username = input.Username?.Trim() ?? "";
        // Limit by source rather than account name so changing usernames cannot
        // bypass the local login throttle.
        var throttleKey = ClientIp(context);
        if (IsLoginBlocked(throttleKey))
        {
            await AuditAsync(context, null, "auth.login", "RateLimited", new { reason = "login_throttled" }, ct);
            return new LocalAuthLoginResult(false, StatusCodes.Status429TooManyRequests, "登录尝试过于频繁，请稍后再试", "RateLimited");
        }

        if (!VerifyCredentials(username, input.Password ?? ""))
        {
            RecordLoginFailure(throttleKey);
            await AuditAsync(context, null, "auth.login", "Denied", new { username, reason = "invalid_credentials" }, ct);
            return new LocalAuthLoginResult(false, StatusCodes.Status401Unauthorized, "账号或密码错误", "Denied");
        }

        _loginAttempts.TryRemove(throttleKey, out _);
        var created = await CreateSessionAsync(context, username, ct);
        await AuditAsync(context, created.Principal, "auth.login", "Succeeded", null, ct);
        return created;
    }

    public async Task<LocalAuthLoginResult> SetupAsync(HttpContext context, LocalAdminSetupInput input, CancellationToken ct = default)
    {
        if (!_settings.RequireLocalLogin) return new(false, StatusCodes.Status409Conflict, "当前使用本机免登录模式，无需初始化账号", "LocalOnly");
        if (!IsLoopbackRequest(context) || !HasAllowedOrigin(context))
            return new LocalAuthLoginResult(false, StatusCodes.Status403Forbidden, "仅允许本机页面初始化", "OriginRejected");

        var username = input.Username?.Trim() ?? "";
        var password = input.Password ?? "";
        if (!UsernamePattern.IsMatch(username))
            return new LocalAuthLoginResult(false, StatusCodes.Status400BadRequest, "账号需为 3-64 位汉字、字母、数字、点、下划线或连字符", "InvalidInput");
        if (password.Length < 12 || password.Length > 512)
            return new LocalAuthLoginResult(false, StatusCodes.Status400BadRequest, "本机管理员密码长度需为 12-512 位", "InvalidInput");

        await _setupGate.WaitAsync(ct);
        try
        {
            if (IsConfigured)
                return new LocalAuthLoginResult(false, StatusCodes.Status409Conflict, "本机管理员账号已初始化，请直接登录", "AlreadyConfigured");

            var hash = HashPassword(password);
            await PersistLocalAdminConfigurationAsync(username, hash, ct);
            lock (_configurationLock)
            {
                _username = username;
                _password = "";
                _passwordHash = hash;
            }

            var created = await CreateSessionAsync(context, username, ct);
            await AuditAsync(context, created.Principal, "auth.setup", "Succeeded", new { username }, ct);
            return created;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "保存本机管理员配置失败");
            await AuditAsync(context, null, "auth.setup", "Failed", new { reason = "configuration_write_failed" }, ct);
            return new LocalAuthLoginResult(false, StatusCodes.Status500InternalServerError, "本机管理员配置保存失败，请检查 config 目录写入权限", "ConfigurationWriteFailed");
        }
        finally
        {
            _setupGate.Release();
        }
    }

    public async Task<LocalAuthDecision> AuthenticateAsync(HttpContext context, bool requireCsrf, CancellationToken ct = default)
    {
        if (!_settings.RequireLocalLogin)
        {
            if (!IsAllowedLocalModeRequest(context))
                return new(false, StatusCodes.Status403Forbidden, "免登录模式仅允许本机工作台访问", "OriginRejected");
            var localPrincipal = new LocalAuthPrincipal(0, "local-operator", "LocalOperator", DateTime.UtcNow.AddHours(8));
            if (requireCsrf && !HasValidLocalCsrf(context))
                return new(false, StatusCodes.Status403Forbidden, "写操作缺少有效的本机校验令牌，请刷新工作台后重试", "CsrfRejected", localPrincipal);
            return new(true, StatusCodes.Status200OK, null, "LocalOnly", localPrincipal);
        }
        if (!IsConfigured)
            return new LocalAuthDecision(false, StatusCodes.Status503ServiceUnavailable, "尚未创建本机管理员账号，请先在本机登录页完成初始化", "SetupRequired");
        if (!IsTrustedRequest(context))
            return new LocalAuthDecision(false, StatusCodes.Status403Forbidden, "仅允许本机访问", "OriginRejected");
        if (!HasAllowedOrigin(context))
            return new LocalAuthDecision(false, StatusCodes.Status403Forbidden, "请求来源未获允许", "OriginRejected");

        var sessionToken = context.Request.Cookies[SessionCookieName];
        if (string.IsNullOrWhiteSpace(sessionToken))
            return new LocalAuthDecision(false, StatusCodes.Status401Unauthorized, "请先登录本机管理员账号", "Unauthenticated");

        var session = await _repository.AdminSessionByTokenHashAsync(HashToken(sessionToken), ct);
        if (session is null || !SessionIsActive(session))
            return new LocalAuthDecision(false, StatusCodes.Status401Unauthorized, "登录已失效，请重新登录", "SessionExpired");

        var principal = new LocalAuthPrincipal(session.Long("id"), session.Text("username") ?? "", session.Text("role") ?? "", SessionExpiry(session));
        if (!string.Equals(principal.Role, "Administrator", StringComparison.Ordinal))
            return new LocalAuthDecision(false, StatusCodes.Status403Forbidden, "当前账号没有后台管理权限", "PermissionDenied", principal);

        if (requireCsrf)
        {
            var csrfToken = context.Request.Headers[CsrfHeaderName].ToString();
            var expectedHash = session.Text("csrfHash") ?? "";
            if (string.IsNullOrWhiteSpace(csrfToken) || !FixedTimeEquals(HashToken(csrfToken), expectedHash))
                return new LocalAuthDecision(false, StatusCodes.Status403Forbidden, "写操作缺少有效的本机校验令牌，请刷新页面后重试", "CsrfRejected", principal);
        }

        await _repository.TouchAdminSessionAsync(principal.SessionId, ct);
        return new LocalAuthDecision(true, StatusCodes.Status200OK, null, "Succeeded", principal);
    }

    public LocalAuthPrincipal? CurrentPrincipal(HttpContext context)
        => context.Items.TryGetValue(PrincipalItemKey, out var principal) ? principal as LocalAuthPrincipal : null;

    public async Task LogoutAsync(HttpContext context, LocalAuthPrincipal principal, CancellationToken ct = default)
    {
        if (principal.SessionId > 0) await _repository.RevokeAdminSessionAsync(principal.SessionId, ct);
        ClearSessionCookie(context);
        await AuditAsync(context, principal, "auth.logout", "Succeeded", null, ct);
    }

    public void SetSessionCookies(HttpContext context, string sessionToken, string csrfToken, DateTime expiresAt)
    {
        context.Response.Cookies.Append(SessionCookieName, sessionToken, new CookieOptions
        {
            HttpOnly = true,
            IsEssential = true,
            SameSite = SameSiteMode.Strict,
            Secure = context.Request.IsHttps,
            Path = "/",
            Expires = new DateTimeOffset(expiresAt)
        });
        SetCsrfCookie(context, csrfToken, expiresAt);
    }

    public void SetCsrfCookie(HttpContext context, string csrfToken, DateTime expiresAt)
    {
        context.Response.Cookies.Append(CsrfCookieName, csrfToken, new CookieOptions
        {
            HttpOnly = false,
            IsEssential = true,
            SameSite = SameSiteMode.Strict,
            Secure = context.Request.IsHttps,
            Path = "/",
            Expires = new DateTimeOffset(expiresAt)
        });
    }

    private static void ClearSessionCookie(HttpContext context)
    {
        context.Response.Cookies.Delete(SessionCookieName, new CookieOptions
        {
            HttpOnly = true,
            IsEssential = true,
            SameSite = SameSiteMode.Strict,
            Secure = context.Request.IsHttps,
            Path = "/"
        });
        context.Response.Cookies.Delete(CsrfCookieName, new CookieOptions
        {
            IsEssential = true,
            SameSite = SameSiteMode.Strict,
            Secure = context.Request.IsHttps,
            Path = "/"
        });
    }

    public async Task RejectAsync(HttpContext context, LocalAuthDecision decision, CancellationToken ct = default)
    {
        context.Response.StatusCode = decision.StatusCode;
        context.Response.ContentType = "application/json; charset=utf-8";
        await context.Response.WriteAsJsonAsync(new { error = decision.Error, code = decision.Outcome, requestId = context.TraceIdentifier }, ct);
        await AuditAsync(context, decision.Principal, "api.request", decision.Outcome, new { statusCode = decision.StatusCode }, ct);
    }

    public async Task AuditRequestAsync(HttpContext context, LocalAuthPrincipal? principal, string outcome, object? details = null, CancellationToken ct = default)
        => await AuditAsync(context, principal, "api.request", outcome, details, ct);

    public async Task AuditAsync(HttpContext context, LocalAuthPrincipal? principal, string action, string outcome, object? details, CancellationToken ct = default)
    {
        try
        {
            var detailsJson = details is null ? null : JsonSerializer.Serialize(details);
            await _repository.AddSecurityAuditEventAsync(principal?.SessionId is > 0 ? principal.SessionId : null, principal?.Username, principal?.Role, action,
                context.Request.Method, context.Request.Path.ToString(), context.TraceIdentifier, ClientIp(context), outcome, detailsJson, ct);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "安全审计记录写入失败: {Action}", action);
        }
    }

    public static bool IsAnonymousApiPath(PathString path)
        => path == "/api/health" || path == "/api/auth/status" || path == "/api/auth/login" || path == "/api/auth/setup";

    private async Task<LocalAuthLoginResult> CreateSessionAsync(HttpContext context, string username, CancellationToken ct)
    {
        var sessionToken = NewToken();
        var csrfToken = NewToken();
        // MySQL DATETIME/NOW() in this local deployment use the host local clock.
        // Keep the session comparison on the same clock to avoid immediate expiry.
        var expiresAt = DateTime.Now.AddHours(8);
        var sessionId = await _repository.CreateAdminSessionAsync(HashToken(sessionToken), HashToken(csrfToken), username, "Administrator", expiresAt, ClientIp(context), Truncate(context.Request.Headers.UserAgent.ToString(), 512), ct);
        return new LocalAuthLoginResult(true, StatusCodes.Status200OK, null, "Succeeded", new LocalAuthPrincipal(sessionId, username, "Administrator", expiresAt), sessionToken, csrfToken);
    }

    // Local maintenance only; deliberately not exposed as an HTTP endpoint.
    public async Task ResetLocalPasswordAsync(string username, string password, CancellationToken ct = default)
    {
        if (!UsernamePattern.IsMatch(username) || password.Length < 12 || password.Length > 512)
            throw new ArgumentException("Invalid administrator credential format");
        await PersistLocalAdminConfigurationAsync(username, HashPassword(password), ct);
    }

    private async Task PersistLocalAdminConfigurationAsync(string username, string passwordHash, CancellationToken ct)
    {
        var configDirectory = Path.Combine(_settings.RootPath, "config");
        var path = Path.Combine(configDirectory, "local.env");
        Directory.CreateDirectory(configDirectory);
        var lines = File.Exists(path) ? await File.ReadAllLinesAsync(path, ct) : [];
        var replacement = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["AI_VIDEO_STUDIO_ADMIN_USERNAME"] = username,
            ["AI_VIDEO_STUDIO_ADMIN_PASSWORD_HASH"] = passwordHash
        };
        var result = new List<string>(lines.Length + replacement.Count);
        foreach (var line in lines)
        {
            var separator = line.IndexOf('=');
            var key = separator > 0 ? line[..separator].Trim() : "";
            if (string.Equals(key, "AI_VIDEO_STUDIO_ADMIN_PASSWORD", StringComparison.OrdinalIgnoreCase)) continue;
            if (replacement.TryGetValue(key, out var value))
            {
                result.Add($"{key}={value}");
                replacement.Remove(key);
            }
            else result.Add(line);
        }
        foreach (var pair in replacement) result.Add($"{pair.Key}={pair.Value}");

        var temporaryPath = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await File.WriteAllLinesAsync(temporaryPath, result, new UTF8Encoding(false), ct);
            File.Move(temporaryPath, path, true);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
        }
    }

    private (string Username, string Password, string PasswordHash) ConfigurationSnapshot()
    {
        lock (_configurationLock) return (_username, _password, _passwordHash);
    }

    private bool VerifyCredentials(string username, string password)
    {
        var snapshot = ConfigurationSnapshot();
        if (!FixedTimeEquals(username, snapshot.Username)) return false;
        return !string.IsNullOrWhiteSpace(snapshot.PasswordHash)
            ? VerifyPasswordHash(password, snapshot.PasswordHash)
            : FixedTimeEquals(password, snapshot.Password);
    }

    private bool IsLoginBlocked(string key)
    {
        if (!_loginAttempts.TryGetValue(key, out var attempt)) return false;
        lock (attempt)
        {
            var now = DateTime.UtcNow;
            if (attempt.BlockedUntil > now) return true;
            if (attempt.WindowStartedAt.AddMinutes(15) <= now) _loginAttempts.TryRemove(key, out _);
            return false;
        }
    }

    private void RecordLoginFailure(string key)
    {
        var attempt = _loginAttempts.GetOrAdd(key, _ => new LoginThrottle(DateTime.UtcNow));
        lock (attempt)
        {
            var now = DateTime.UtcNow;
            if (attempt.WindowStartedAt.AddMinutes(15) <= now)
            {
                attempt.WindowStartedAt = now;
                attempt.Failures = 0;
                attempt.BlockedUntil = DateTime.MinValue;
            }
            attempt.Failures++;
            if (attempt.Failures >= 5) attempt.BlockedUntil = now.AddMinutes(15);
        }
    }

    private static bool SessionIsActive(IReadOnlyDictionary<string, object?> session)
        => string.IsNullOrWhiteSpace(session.Text("revokedAt")) && SessionExpiry(session) > DateTime.Now;

    private static DateTime SessionExpiry(IReadOnlyDictionary<string, object?> session)
    {
        if (!session.TryGetValue("expiresAt", out var raw) || raw is null) return DateTime.MinValue;
        if (raw is DateTime value) return value.Kind == DateTimeKind.Local ? value : DateTime.SpecifyKind(value, DateTimeKind.Local);
        return DateTime.TryParse(Convert.ToString(raw, CultureInfo.InvariantCulture), CultureInfo.InvariantCulture, DateTimeStyles.AssumeLocal, out var parsed) ? parsed : DateTime.MinValue;
    }

    private bool HasAllowedOrigin(HttpContext context)
    {
        var origin = context.Request.Headers.Origin.ToString();
        return string.IsNullOrWhiteSpace(origin) || _allowedOrigins.Contains(origin);
    }

    private static bool IsAllowedLocalModeRequest(HttpContext context)
    {
        if (!IsLoopbackRequest(context)) return false;
        var host = context.Request.Host.Host;
        if (!host.Equals("localhost", StringComparison.OrdinalIgnoreCase)
            && (!IPAddress.TryParse(host, out var address) || !IsLoopbackAddress(address))) return false;
        var origin = context.Request.Headers.Origin.ToString();
        return string.IsNullOrWhiteSpace(origin) || DefaultAllowedOrigins.Contains(origin, StringComparer.OrdinalIgnoreCase);
    }

    private bool HasValidLocalCsrf(HttpContext context)
    {
        var token = context.Request.Headers[CsrfHeaderName].ToString();
        var cookie = context.Request.Cookies[CsrfCookieName];
        if (string.IsNullOrWhiteSpace(token) || token.Length > 256 || string.IsNullOrWhiteSpace(cookie) || !FixedTimeEquals(token, cookie)) return false;
        var parts = token.Split('.');
        if (parts.Length != 3 || !long.TryParse(parts[1], out var expiry) || expiry <= DateTimeOffset.UtcNow.ToUnixTimeSeconds()) return false;
        var signature = Convert.ToHexString(HMACSHA256.HashData(_localCsrfKey, Encoding.UTF8.GetBytes($"{parts[0]}.{parts[1]}")));
        return FixedTimeEquals(signature, parts[2]);
    }

    private bool IsTrustedRequest(HttpContext context)
    {
        var remote = context.Connection.RemoteIpAddress;
        return IsLoopbackAddress(remote) || (remote is not null && _trustedNetworks.Any(network => network.Contains(remote)));
    }

    private static bool IsLoopbackRequest(HttpContext context) => IsLoopbackAddress(context.Connection.RemoteIpAddress);

    private static bool IsLoopbackAddress(IPAddress? address)
    {
        return address is not null && (IPAddress.IsLoopback(address) || IPAddress.IsLoopback(address.MapToIPv4()));
    }

    private static IEnumerable<string> SplitConfigurationValues(string? values)
        => string.IsNullOrWhiteSpace(values)
            ? []
            : values.Split([',', ';'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    private static TrustedNetwork? TryParseTrustedNetwork(string value)
    {
        var parts = value.Split('/', 2, StringSplitOptions.TrimEntries);
        if (!IPAddress.TryParse(parts[0], out var address) || address.AddressFamily != AddressFamily.InterNetwork) return null;
        var prefixLength = 32;
        if (parts.Length == 2 && (!int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out prefixLength) || prefixLength is < 0 or > 32)) return null;
        var mask = prefixLength == 0 ? 0u : uint.MaxValue << (32 - prefixLength);
        return new TrustedNetwork(ToUInt32(address.GetAddressBytes()) & mask, mask);
    }

    private static uint ToUInt32(byte[] bytes)
        => ((uint)bytes[0] << 24) | ((uint)bytes[1] << 16) | ((uint)bytes[2] << 8) | bytes[3];

    private readonly record struct TrustedNetwork(uint Network, uint Mask)
    {
        public bool Contains(IPAddress address)
        {
            if (address.AddressFamily != AddressFamily.InterNetwork) return false;
            return (ToUInt32(address.GetAddressBytes()) & Mask) == Network;
        }
    }

    private static string ClientIp(HttpContext context) => context.Connection.RemoteIpAddress?.ToString() ?? "unknown";

    private static string NewToken() => Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    private static string HashToken(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    private static bool FixedTimeEquals(string left, string right) => CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(left ?? ""), Encoding.UTF8.GetBytes(right ?? ""));
    private static string Truncate(string value, int maxLength) => value.Length <= maxLength ? value : value[..maxLength];

    private static string HashPassword(string password)
    {
        const int iterations = 210_000;
        var salt = RandomNumberGenerator.GetBytes(16);
        var derived = Rfc2898DeriveBytes.Pbkdf2(password, salt, iterations, HashAlgorithmName.SHA512, 32);
        return $"pbkdf2-sha512${iterations}${ToBase64Url(salt)}${ToBase64Url(derived)}";
    }

    private static bool VerifyPasswordHash(string password, string encoded)
    {
        try
        {
            var parts = encoded.Split('$');
            if (parts.Length != 4 || !string.Equals(parts[0], "pbkdf2-sha512", StringComparison.Ordinal) || !int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out var iterations) || iterations is < 100_000 or > 1_000_000) return false;
            var salt = FromBase64Url(parts[2]);
            var expected = FromBase64Url(parts[3]);
            if (salt.Length < 16 || expected.Length < 32) return false;
            var actual = Rfc2898DeriveBytes.Pbkdf2(password, salt, iterations, HashAlgorithmName.SHA512, expected.Length);
            return CryptographicOperations.FixedTimeEquals(actual, expected);
        }
        catch (FormatException) { return false; }
    }

    private static string ToBase64Url(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    private static byte[] FromBase64Url(string value)
    {
        var normalized = value.Replace('-', '+').Replace('_', '/');
        normalized += (normalized.Length % 4) switch { 2 => "==", 3 => "=", 0 => "", _ => throw new FormatException("Invalid base64url value") };
        return Convert.FromBase64String(normalized);
    }

    private sealed class LoginThrottle(DateTime startedAt)
    {
        public DateTime WindowStartedAt { get; set; } = startedAt;
        public int Failures { get; set; }
        public DateTime BlockedUntil { get; set; } = DateTime.MinValue;
    }
}
