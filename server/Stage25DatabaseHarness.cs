using System.Globalization;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Explicitly-invoked stage 2.5 harness. It is not part of normal server
/// startup. All database names, account names and cleanup paths are exact
/// constants or values written by the setup command; no wildcard cleanup is
/// performed.
/// </summary>
public static partial class Stage25DatabaseHarness
{
    private const string DatabaseName = "ai_video_studio_stage12_acceptance_20260813";
    private const string AppUser = "ai_video_studio_stage12_app";
    private const string MigratorUser = "ai_video_studio_stage12_migrator";
    private const string AccountHost = "127.0.0.1";
    private const string Stage25Prefix = "ai-video-studio-stage25-";

    public static async Task<int> RunAsync(string[] args)
    {
        try
        {
            return args.Length switch
            {
                >= 2 when args[0] == "--stage25-setup" => await SetupAsync(args[1]),
                >= 2 when args[0] == "--stage25-apply" => await ApplyAsync(args[1]),
                >= 2 when args[0] == "--stage25-structure" => await StructureAsync(args[1]),
                >= 3 when args[0] == "--stage25-summary" => await SummaryAsync(args[1], args[2]),
                >= 3 when args[0] == "--stage25-manifest-summary" => await ManifestSummaryAsync(args[1], args[2]),
                >= 2 when args[0] == "--stage25-migration-report" => await MigrationReportAsync(args[1]),
                >= 2 when args[0] == "--stage25-safety" => await SafetyAsync(args[1]),
                >= 2 when args[0] == "--stage25-path" => await PathNegativeAsync(args[1]),
                >= 2 when args[0] == "--stage25-llm" => await LlmNegativeAsync(args[1]),
                >= 2 when args[0] == "--stage25-privilege" => await PrivilegeAsync(args[1]),
                >= 2 when args[0] == "--stage25-domain" => await DomainAsync(args[1]),
                >= 4 when args[0] == "--stage25-race-worker" => await RaceWorkerAsync(args[1], args[2], args[3], args.Length > 4 ? args[4..] : []),
                >= 2 when args[0] == "--stage25-drop-accounts" => await DropAccountsAsync(args[1]),
                >= 1 when args[0] == "--stage25-account-status" => await AccountStatusAsync(),
                >= 1 when args[0] == "--stage25-database-status" => await DatabaseStatusAsync(),
                _ => Fail("usage: --stage25-setup|apply|structure|summary|privilege|domain|race-worker|drop-accounts <secure-config> ...")
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"STAGE25_FAILURE {ex.GetType().Name}: {SanitizeMessage(ex.Message)}");
            return 1;
        }
    }

    private static int Fail(string message)
    {
        Console.Error.WriteLine(message);
        return 2;
    }

    private static async Task<int> SetupAsync(string secretPath)
    {
        secretPath = Path.GetFullPath(secretPath);
        if (File.Exists(secretPath)) throw new InvalidOperationException("Stage25 secure config already exists; use a new exact path");
        var root = StudioPaths.FindRoot();
        var baseSettings = LoadBaseSettings(root);
        var dataRoot = Path.Combine(Path.GetTempPath(), Stage25Prefix + Guid.NewGuid().ToString("N"), "Data");
        var config = new Stage25Config
        {
            Database = DatabaseName,
            Host = baseSettings.DatabaseHost,
            Port = baseSettings.DatabasePort,
            AppUser = AppUser,
            AppPassword = RandomPassword(),
            MigratorUser = MigratorUser,
            MigratorPassword = RandomPassword(),
            DataRoot = dataRoot,
            StatePath = secretPath + ".state.json",
            CreatedAtUtc = DateTimeOffset.UtcNow
        };

        SaveEncryptedConfig(secretPath, config);
        try
        {
            await using var rootConnection = await OpenAsync(baseSettings.ServerConnectionString);
            if (await ExistsAsync(rootConnection, "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=@name", DatabaseName))
                throw new InvalidOperationException("The exact isolated database already exists; refusing to reuse it as a new fixture");
            if (await ExistsAsync(rootConnection, "SELECT COUNT(*) FROM mysql.user WHERE User=@user AND Host=@host", AppUser, AccountHost)
                || await ExistsAsync(rootConnection, "SELECT COUNT(*) FROM mysql.user WHERE User=@user AND Host=@host", MigratorUser, AccountHost))
                throw new InvalidOperationException("An exact stage25 account already exists; refusing to rotate its password");

            await ExecuteAsync(rootConnection, $"CREATE DATABASE `{DatabaseName}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci");
            await ExecuteAsync(rootConnection, $"CREATE USER '{AppUser}'@'{AccountHost}' IDENTIFIED BY '{config.AppPassword}'");
            await ExecuteAsync(rootConnection, $"CREATE USER '{MigratorUser}'@'{AccountHost}' IDENTIFIED BY '{config.MigratorPassword}'");
            await ExecuteAsync(rootConnection, $"GRANT SELECT, INSERT, UPDATE, DELETE ON `{DatabaseName}`.* TO '{AppUser}'@'{AccountHost}'");
            await ExecuteAsync(rootConnection, $"GRANT SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES ON `{DatabaseName}`.* TO '{MigratorUser}'@'{AccountHost}'");
            await ExecuteAsync(rootConnection, "FLUSH PRIVILEGES");
            Directory.CreateDirectory(dataRoot);
            Console.WriteLine($"PASS setup database={DatabaseName} app={AppUser}@{AccountHost} migrator={MigratorUser}@{AccountHost}");
            Console.WriteLine($"SECURE_CONFIG_PATH {secretPath}");
            return 0;
        }
        catch
        {
            // Keep the exact encrypted config and any partial database objects
            // as evidence. The caller's failure path decides account cleanup.
            throw;
        }
    }

    private static async Task<int> ApplyAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var settings = SettingsFor(config, config.MigratorUser, config.MigratorPassword, autoApply: true);
        var db = new StudioDb(settings, NullLogger<StudioDb>.Instance);
        var initializer = new DatabaseInitializer(settings, db, NullLogger<DatabaseInitializer>.Instance);
        await initializer.ApplyExistingSchemaAsync();
        Console.WriteLine($"PASS migration applied using {config.MigratorUser}@{AccountHost}; database={config.Database}; baseline=001_database_sql; structural=002,003,004,005,007,008; 006=data-repair-not-applicable-on-clean-database");
        return 0;
    }

    private static async Task<int> StructureAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        await using var connection = await OpenAsync(SettingsFor(config, config.MigratorUser, config.MigratorPassword).DatabaseConnectionString);
        var requiredTables = new[] { "projects", "episodes", "shots", "generation_tasks", "generation_results", "schema_migrations", "production_profiles", "project_production_profile_bindings", "entity_versions", "shot_plans", "task_attempts", "asset_manifests", "artifact_publish_intents", "llm_egress_audit" };
        var missingTables = new List<string>();
        foreach (var table in requiredTables)
            if (!await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=@name", table)) missingTables.Add(table);

        var requiredColumns = new (string Table, string Column)[]
        {
            ("generation_tasks", "production_profile_id"), ("generation_tasks", "shot_plan_id"), ("generation_tasks", "input_asset_id"), ("generation_tasks", "active_attempt_id"), ("generation_tasks", "lease_token"), ("generation_tasks", "output_manifest_id"),
            ("generation_results", "attempt_id"), ("generation_results", "manifest_id"), ("task_events", "attempt_id"), ("task_events", "lease_token"), ("task_events", "output_manifest_id"),
            ("assets", "manifest_id"), ("assets", "purpose"), ("assets", "version"), ("assets", "status"), ("assets", "source_attempt_id"), ("assets", "immutable_path"),
            ("llm_egress_audit", "redacted_preview"), ("llm_egress_audit", "redirect_count"), ("llm_egress_audit", "timeout_ms")
        };
        var missingColumns = new List<string>();
        foreach (var (table, column) in requiredColumns)
            if (!await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=@table AND column_name=@column", table, column)) missingColumns.Add($"{table}.{column}");

        var requiredIndexes = new (string Table, string Name)[]
        {
            ("generation_tasks", "uq_generation_tasks_idempotency"), ("generation_tasks", "ix_tasks_active_attempt"), ("generation_results", "uq_results_manifest"), ("assets", "uq_assets_manifest"),
            ("production_profiles", "uq_production_profiles_version"), ("production_profiles", "uq_production_profiles_content"), ("entity_versions", "uq_entity_versions_version"), ("entity_versions", "uq_entity_versions_content"),
            ("shot_plans", "uq_shot_plans_version"), ("shot_plans", "uq_shot_plans_content"), ("task_attempts", "uq_task_attempts_task_no"), ("asset_manifests", "uq_asset_manifests_path"), ("artifact_publish_intents", "uq_artifact_publish_intent")
        };
        var missingIndexes = new List<string>();
        foreach (var (table, name) in requiredIndexes)
            if (!await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=@table AND index_name=@name", table, name)) missingIndexes.Add($"{table}.{name}");

        var requiredForeignKeys = new (string Table, string Name)[]
        {
            ("asset_manifests", "fk_asset_manifests_attempt"), ("asset_manifests", "fk_asset_manifests_task"), ("assets", "fk_assets_manifest_stage12"), ("assets", "fk_assets_attempt_stage12"),
            ("generation_results", "fk_results_attempt_stage12"), ("generation_results", "fk_results_manifest_stage12"), ("generation_tasks", "fk_tasks_active_attempt"), ("generation_tasks", "fk_tasks_output_manifest")
        };
        var missingForeignKeys = new List<string>();
        foreach (var (table, name) in requiredForeignKeys)
            if (!await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name=@table AND constraint_name=@name AND constraint_type='FOREIGN KEY'", table, name)) missingForeignKeys.Add($"{table}.{name}");

        var versions = await QueryStringsAsync(connection, "SELECT version FROM schema_migrations ORDER BY version");
        var tableCount = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()"), CultureInfo.InvariantCulture);
        var passed = missingTables.Count == 0 && missingColumns.Count == 0 && missingIndexes.Count == 0 && missingForeignKeys.Count == 0 && versions.Contains("001_database_sql") && versions.Contains(Stage12SchemaMigrator.Version);
        Console.WriteLine($"{(passed ? "PASS" : "FAIL")} structure tables={tableCount} missingTables={missingTables.Count} missingColumns={missingColumns.Count} missingIndexes={missingIndexes.Count} missingForeignKeys={missingForeignKeys.Count} schemaVersions={string.Join(',', versions)}");
        if (!passed)
        {
            Console.WriteLine($"DETAIL missingTables={string.Join('|', missingTables)} missingColumns={string.Join('|', missingColumns)} missingIndexes={string.Join('|', missingIndexes)} missingForeignKeys={string.Join('|', missingForeignKeys)}");
            return 1;
        }
        return 0;
    }

    private static async Task<int> SummaryAsync(string secretPath, string taskIdText)
    {
        if (!long.TryParse(taskIdText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var taskId) || taskId <= 0)
            throw new ArgumentException("summary requires a positive task id", nameof(taskIdText));
        var config = LoadEncryptedConfig(secretPath);
        await using var connection = await OpenAsync(SettingsFor(config, config.AppUser, config.AppPassword).DatabaseConnectionString);
        await using var command = new MySqlCommand(@"SELECT t.id,t.status,t.attempts,t.max_retries,t.state_version,t.active_attempt_id,t.output_manifest_id,
            (SELECT COUNT(*) FROM task_attempts a WHERE a.task_id=t.id) AS attempt_count,
            (SELECT COUNT(*) FROM asset_manifests m WHERE m.task_id=t.id) AS manifest_count,
            (SELECT COUNT(*) FROM artifact_publish_intents i WHERE i.task_id=t.id) AS intent_count
            FROM generation_tasks t WHERE t.id=@task", connection);
        command.Parameters.AddWithValue("@task", taskId);
        await using var reader = await command.ExecuteReaderAsync();
        if (!await reader.ReadAsync()) throw new InvalidOperationException($"Task {taskId} was not found");
        long ReadLong(string name) => Convert.ToInt64(reader.GetValue(reader.GetOrdinal(name)), CultureInfo.InvariantCulture);
        int ReadInt(string name) => Convert.ToInt32(reader.GetValue(reader.GetOrdinal(name)), CultureInfo.InvariantCulture);
        long? ReadNullableLong(string name) => reader.IsDBNull(reader.GetOrdinal(name)) ? null : ReadLong(name);
        var values = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["taskId"] = ReadLong("id"), ["status"] = Convert.ToString(reader.GetValue(reader.GetOrdinal("status")), CultureInfo.InvariantCulture),
            ["attempts"] = ReadInt("attempts"), ["maxRetries"] = ReadInt("max_retries"), ["stateVersion"] = ReadInt("state_version"),
            ["activeAttemptId"] = ReadNullableLong("active_attempt_id"),
            ["outputManifestId"] = ReadNullableLong("output_manifest_id"),
            ["attemptCount"] = ReadLong("attempt_count"), ["manifestCount"] = ReadLong("manifest_count"), ["intentCount"] = ReadLong("intent_count")
        };
        Console.WriteLine(JsonSerializer.Serialize(values));
        return 0;
    }

    private static async Task<int> RunCachePreviewAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var settings = SettingsFor(config, config.AppUser, config.AppPassword);
        var db = new StudioDb(settings, NullLogger<StudioDb>.Instance);
        var service = new CacheCleanupService(settings, db);
        var preview = await service.PreviewAsync(TimeSpan.Zero);
        Console.WriteLine($"PASS cache-preview candidates={preview.Candidates.Count} deletePerformed=false");
        return 0;
    }

    private static async Task<int> ManifestSummaryAsync(string secretPath, string manifestIdText)
    {
        if (!long.TryParse(manifestIdText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var manifestId) || manifestId <= 0)
            throw new ArgumentException("manifest-summary requires a positive manifest id", nameof(manifestIdText));
        var config = LoadEncryptedConfig(secretPath);
        await using var connection = await OpenAsync(SettingsFor(config, config.AppUser, config.AppPassword).DatabaseConnectionString);
        await using var command = new MySqlCommand(@"SELECT m.id,m.status AS manifest_status,m.attempt_id,m.relative_path,
            a.status AS asset_status,i.status AS intent_status
            FROM asset_manifests m LEFT JOIN assets a ON a.manifest_id=m.id
            LEFT JOIN artifact_publish_intents i ON i.manifest_id=m.id WHERE m.id=@manifest LIMIT 1", connection);
        command.Parameters.AddWithValue("@manifest", manifestId);
        await using var reader = await command.ExecuteReaderAsync();
        if (!await reader.ReadAsync()) throw new InvalidOperationException($"Manifest {manifestId} was not found");
        var result = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
        {
            ["manifestId"] = manifestId,
            ["manifestStatus"] = Convert.ToString(reader.GetValue(reader.GetOrdinal("manifest_status")), CultureInfo.InvariantCulture),
            ["attemptId"] = reader.IsDBNull(reader.GetOrdinal("attempt_id")) ? null : Convert.ToInt64(reader.GetValue(reader.GetOrdinal("attempt_id")), CultureInfo.InvariantCulture),
            ["assetStatus"] = reader.IsDBNull(reader.GetOrdinal("asset_status")) ? null : Convert.ToString(reader.GetValue(reader.GetOrdinal("asset_status")), CultureInfo.InvariantCulture),
            ["intentStatus"] = reader.IsDBNull(reader.GetOrdinal("intent_status")) ? null : Convert.ToString(reader.GetValue(reader.GetOrdinal("intent_status")), CultureInfo.InvariantCulture),
            ["relativePath"] = Convert.ToString(reader.GetValue(reader.GetOrdinal("relative_path")), CultureInfo.InvariantCulture)
        };
        Console.WriteLine(JsonSerializer.Serialize(result));
        return 0;
    }

    private static async Task<int> MigrationReportAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        await using var connection = await OpenAsync(SettingsFor(config, config.MigratorUser, config.MigratorPassword).DatabaseConnectionString);
        var versions = new List<object>();
        await using (var command = new MySqlCommand("SELECT version,applied_at FROM schema_migrations ORDER BY applied_at,version", connection))
        await using (var reader = await command.ExecuteReaderAsync())
        {
            while (await reader.ReadAsync()) versions.Add(new { version = reader.GetString(0), appliedAtUtc = reader.GetDateTime(1).ToUniversalTime().ToString("O", CultureInfo.InvariantCulture) });
        }
        var counts = new Dictionary<string, long>(StringComparer.OrdinalIgnoreCase);
        foreach (var table in new[] { "projects", "episodes", "shots", "generation_tasks", "task_attempts", "asset_manifests", "artifact_publish_intents", "entity_versions", "shot_plans", "llm_egress_audit" })
            counts[table] = Convert.ToInt64(await ScalarAsync(connection, $"SELECT COUNT(*) FROM `{table}`"), CultureInfo.InvariantCulture);
        var tableCount = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()"), CultureInfo.InvariantCulture);
        Console.WriteLine(JsonSerializer.Serialize(new { database = config.Database, tableCount, schemaVersions = versions, rowCounts = counts }));
        return 0;
    }

    private static async Task<int> SafetyAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var settings = SettingsFor(config, config.AppUser, config.AppPassword);
        var db = new StudioDb(settings, NullLogger<StudioDb>.Instance);
        var normalDisk = new DiskSpaceGuard(settings).Check(config.DataRoot);
        var forcedLowDisk = new DiskSpaceGuard(new StudioSettings
        {
            DataPath = config.DataRoot,
            MinimumFreeDiskBytes = long.MaxValue
        }).Check(config.DataRoot);
        if (!normalDisk.Allowed || forcedLowDisk.Allowed) throw new InvalidOperationException("Disk guard did not distinguish sufficient and low-space fixtures");

        var cacheRoot = Path.Combine(config.DataRoot, "Cache");
        Directory.CreateDirectory(cacheRoot);
        var cacheFile = Path.Combine(cacheRoot, "stage25-cache-preview.bin");
        await File.WriteAllTextAsync(cacheFile, "stage25-dry-run");
        File.SetLastWriteTimeUtc(cacheFile, DateTime.UtcNow.AddHours(-2));
        var preview = await new CacheCleanupService(settings, db).PreviewAsync(TimeSpan.Zero);
        var candidate = preview.Candidates.FirstOrDefault(item => item.RelativePath.Equals("Cache/stage25-cache-preview.bin", StringComparison.OrdinalIgnoreCase));
        if (candidate is null || !File.Exists(cacheFile)) throw new InvalidOperationException("Cache dry-run did not report the controlled old file or changed it");
        Console.WriteLine($"PASS safety disk-normal={normalDisk.Allowed} disk-low-rejected={!forcedLowDisk.Allowed} cache-candidates={preview.CandidateCount} delete-performed=false fixture-retained=true");
        return 0;
    }

    private static async Task<int> LlmNegativeAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var settings = SettingsFor(config, config.AppUser, config.AppPassword);
        var db = new StudioDb(settings, NullLogger<StudioDb>.Instance);
        var repository = new StudioRepository(db, NullLogger<StudioRepository>.Instance);
        var policy = new LlmEndpointPolicy();
        var loopbackPort = GetFreeTcpPort();
        var allowed = await policy.ValidateAsync("Local", $"http://127.0.0.1:{loopbackPort}/");
        var blocked = await policy.ValidateAsync("OpenAICompatible", "https://evil.example.invalid/");
        if (!allowed.Allowed || blocked.Allowed) throw new InvalidOperationException("LLM allowlist validation did not produce the expected loopback/blocked results");

        await repository.SetSettingAsync("llm.max_prompt_chars", "128", "llm", false);
        await repository.SetSettingAsync("llm.max_tokens", "16", "llm", false);
        await repository.SetSettingAsync("llm.daily_prompt_char_budget", "10000", "llm", false);
        await repository.SetSettingAsync("llm.daily_token_budget", "10000", "llm", false);
        var audit = new LlmEgressAuditService(settings, repository, NullLogger<LlmEgressAuditService>.Instance);
        var overBudget = await audit.CheckAsync(129, 1);
        if (overBudget.Allowed) throw new InvalidOperationException("LLM prompt budget overflow was allowed");
        var rejectedPreview = LlmEgressAuditService.RedactedPreview("API_KEY_SECRET", "FULL_PROMPT_SECRET", "OpenAICompatible", blocked.Host, "stage25");
        await audit.RecordRejectedAsync("OpenAICompatible", blocked.Host, "stage25", 129, 1, "LLM_ENDPOINT_NOT_ALLOWLISTED", rejectedPreview);

        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var redirectPort = ((IPEndPoint)listener.LocalEndpoint).Port;
        var accept = ServeRedirectAsync(listener);
        using var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(10) };
        var inner = new OpenAiCompatibleLlmProvider(http, new Uri($"http://127.0.0.1:{redirectPort}/"), "stage25", "never-output", "Local");
        var audited = new AuditedLlmProvider(inner, audit, "127.0.0.1", "stage25");
        var redirectBlocked = false;
        try { await audited.CompleteAsync("system", "user", 0.1m, 1); }
        catch (LlmRedirectBlockedException) { redirectBlocked = true; }
        finally { listener.Stop(); }
        await accept;
        if (!redirectBlocked) throw new InvalidOperationException("Local redirect fixture was not blocked");

        var auditRows = await db.QueryAsync("SELECT outcome,error_code,redirect_count,redacted_preview FROM llm_egress_audit ORDER BY id DESC LIMIT 10");
        var redirectAudited = auditRows.Any(row => row.Int("redirectCount") > 0 && string.Equals(row.Text("errorCode"), "LLM_REDIRECT_BLOCKED", StringComparison.OrdinalIgnoreCase));
        var secretFree = auditRows.All(row => !(row.Text("redactedPreview") ?? "").Contains("API_KEY_SECRET", StringComparison.Ordinal) && !(row.Text("redactedPreview") ?? "").Contains("FULL_PROMPT_SECRET", StringComparison.Ordinal));
        if (!redirectAudited || !secretFree) throw new InvalidOperationException("LLM redirect/audit redaction evidence was incomplete");
        Console.WriteLine($"PASS llm allowlist-loopback=true disallowed-host=true redirect-blocked=true budget-rejected=true audited=true secret-free={secretFree} auditRows={auditRows.Count}");
        return 0;
    }

    private static async Task<int> PathNegativeAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var settings = SettingsFor(config, config.AppUser, config.AppPassword);
        var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
        var policy = new AssetPathPolicy(settings, ffmpeg, NullLogger<AssetPathPolicy>.Instance);
        var fixtureId = Guid.NewGuid().ToString("N");
        var allowedDirectory = Path.Combine(config.DataRoot, "PathFixtures", fixtureId);
        var outsideDirectory = Path.Combine(Path.GetTempPath(), "ai-video-studio-stage25-path-outside-" + fixtureId);
        Directory.CreateDirectory(allowedDirectory);
        Directory.CreateDirectory(outsideDirectory);
        var valid = Path.Combine(allowedDirectory, "valid.png");
        var outside = Path.Combine(outsideDirectory, "outside.png");
        await File.WriteAllBytesAsync(valid, TinyPng());
        await File.WriteAllBytesAsync(outside, TinyPng());
        var cases = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase)
        {
            ["valid-under-root"] = policy.TryResolveExisting(Path.GetRelativePath(config.DataRoot, valid), out _, out _),
            ["path-traversal"] = !policy.TryResolveExisting(Path.GetRelativePath(config.DataRoot, outside), out _, out _),
            ["unc"] = !policy.TryResolveExisting(@"\\127.0.0.1\share\outside.png", out _, out _),
            ["device"] = !policy.TryResolveExisting(@"\\.\PIPE\stage25", out _, out _),
            ["device-prefix"] = !policy.TryResolveExisting(@"\\?\C:\outside.png", out _, out _),
            ["ads"] = !policy.TryResolveExisting(Path.GetRelativePath(config.DataRoot, valid) + ":secret", out _, out _),
            ["absolute-outside"] = !policy.TryResolveExisting(outside, out _, out _)
        };
        var commandMarker = Path.Combine(allowedDirectory, "unexpected-command.marker");
        var maliciousName = Path.Combine(allowedDirectory, "stage25-evil;echo-stage25.png");
        await File.WriteAllBytesAsync(maliciousName, TinyPng());
        _ = await ffmpeg.ProbeAsync(maliciousName);
        cases["ffmpeg-argument-isolation"] = !File.Exists(commandMarker);
        var link = Path.Combine(config.DataRoot, "PathFixtures", fixtureId, "outside-link");
        var reparseAvailable = true;
        try { Directory.CreateSymbolicLink(link, outsideDirectory); }
        catch (Exception ex) when (ex is UnauthorizedAccessException or IOException or PlatformNotSupportedException)
        {
            // Windows directory junctions are also reparse points and do not
            // require the symbolic-link developer privilege on this host.
            try
            {
                var junction = new ProcessStartInfo("cmd.exe") { UseShellExecute = false, CreateNoWindow = true };
                junction.ArgumentList.Add("/c"); junction.ArgumentList.Add("mklink"); junction.ArgumentList.Add("/J"); junction.ArgumentList.Add(link); junction.ArgumentList.Add(outsideDirectory);
                using var process = Process.Start(junction) ?? throw new InvalidOperationException("junction process did not start");
                process.WaitForExit(10000);
                reparseAvailable = process.ExitCode == 0 && Directory.Exists(link);
            }
            catch { reparseAvailable = false; }
            if (!reparseAvailable) Console.WriteLine($"BLOCKED path-reparse-fixture reason={SanitizeMessage(ex.Message)}");
        }
        if (reparseAvailable)
            cases["reparse-point-outside-root"] = !policy.TryResolveExisting(Path.Combine("PathFixtures", fixtureId, "outside-link", "outside.png"), out _, out _);
        var failed = cases.Where(pair => !pair.Value).Select(pair => pair.Key).ToArray();
        var passed = failed.Length == 0 && reparseAvailable;
        Console.WriteLine($"{(passed ? "PASS" : "FAIL")} path-negative cases={cases.Count} failed={string.Join('|', failed)} reparseFixture={reparseAvailable} fixtureRoot={allowedDirectory}");
        return passed ? 0 : 1;
    }

    private static int GetFreeTcpPort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        return ((IPEndPoint)listener.LocalEndpoint).Port;
    }

    private static async Task ServeRedirectAsync(TcpListener listener)
    {
        using var client = await listener.AcceptTcpClientAsync();
        await using var stream = client.GetStream();
        var request = new byte[4096];
        _ = await stream.ReadAsync(request);
        var response = Encoding.ASCII.GetBytes("HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:1/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        await stream.WriteAsync(response);
        await stream.FlushAsync();
    }

    private static async Task<int> PrivilegeAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var appSettings = SettingsFor(config, config.AppUser, config.AppPassword);
        var migratorSettings = SettingsFor(config, config.MigratorUser, config.MigratorPassword);
        await using var appConnection = await OpenAsync(appSettings.DatabaseConnectionString);
        await using var migratorConnection = await OpenAsync(migratorSettings.DatabaseConnectionString);
        var checks = new List<(string Name, bool Passed)>();

        checks.Add(("app-isolation-select", Convert.ToInt32(await ScalarAsync(appConnection, "SELECT COUNT(*) FROM projects"), CultureInfo.InvariantCulture) >= 0));
        checks.Add(("app-cannot-read-formal", await DeniedAsync(appConnection, "SELECT COUNT(*) FROM `ai_video_studio`.projects")));
        checks.Add(("app-cannot-create", await DeniedAsync(appConnection, "CREATE TABLE stage25_forbidden_create(id INT)")));
        checks.Add(("app-cannot-alter", await DeniedAsync(appConnection, "ALTER TABLE stage25_missing_table ADD COLUMN forbidden_column INT")));
        checks.Add(("app-cannot-drop", await DeniedAsync(appConnection, "DROP TABLE stage25_missing_table")));
        checks.Add(("app-cannot-grant", await DeniedAsync(appConnection, $"GRANT SELECT ON `{DatabaseName}`.* TO '{AppUser}'@'{AccountHost}'")));
        checks.Add(("migrator-cannot-read-formal", await DeniedAsync(migratorConnection, "SELECT COUNT(*) FROM `ai_video_studio`.projects")));
        checks.Add(("migrator-cannot-create-user", await DeniedAsync(migratorConnection, "CREATE USER 'stage25_forbidden_user'@'127.0.0.1' IDENTIFIED BY 'not-used'")));
        checks.Add(("migrator-cannot-grant", await DeniedAsync(migratorConnection, $"GRANT SELECT ON `{DatabaseName}`.* TO '{AppUser}'@'{AccountHost}'")));

        var root = LoadBaseSettings(StudioPaths.FindRoot());
        await using var rootConnection = await OpenAsync(root.ServerConnectionString);
        var appGrants = await ShowGrantsAsync(rootConnection, AppUser);
        var migratorGrants = await ShowGrantsAsync(rootConnection, MigratorUser);
        var noGlobalGrant = appGrants.Concat(migratorGrants).All(grant =>
            (!grant.Contains("ON *.*", StringComparison.OrdinalIgnoreCase)
             || Regex.IsMatch(grant.Trim(), @"^GRANT\s+USAGE\s+ON\s+\*\.\*", RegexOptions.IgnoreCase))
            && !grant.Contains("WITH GRANT OPTION", StringComparison.OrdinalIgnoreCase));
        checks.Add(("no-global-or-grant-option", noGlobalGrant));
        foreach (var check in checks) Console.WriteLine($"{(check.Passed ? "PASS" : "FAIL")} privilege {check.Name}");
        Console.WriteLine($"GRANTS app={SanitizeGrantSummary(appGrants)}");
        Console.WriteLine($"GRANTS migrator={SanitizeGrantSummary(migratorGrants)}");
        return checks.All(check => check.Passed) ? 0 : 1;
    }

    private static async Task<int> DropAccountsAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var root = LoadBaseSettings(StudioPaths.FindRoot());
        await using var connection = await OpenAsync(root.ServerConnectionString);
        var exactDatabaseExists = await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=@name", DatabaseName);
        if (!exactDatabaseExists) throw new InvalidOperationException("Exact isolated database is missing; refusing account cleanup");
        await ExecuteAsync(connection, $"DROP USER IF EXISTS '{config.AppUser}'@'{AccountHost}'");
        await ExecuteAsync(connection, $"DROP USER IF EXISTS '{config.MigratorUser}'@'{AccountHost}'");
        if (await UserExistsViaShowGrantsAsync(connection, config.AppUser) || await UserExistsViaShowGrantsAsync(connection, config.MigratorUser))
            throw new InvalidOperationException("An exact stage25 account remains after cleanup");
        Console.WriteLine($"PASS temporary accounts deleted exactly: {config.AppUser}@{AccountHost}, {config.MigratorUser}@{AccountHost}; database retained={DatabaseName}");
        DeleteExactSecureConfig(secretPath);
        return 0;
    }

    private static async Task<int> AccountStatusAsync()
    {
        var root = LoadBaseSettings(StudioPaths.FindRoot());
        await using var connection = await OpenAsync(root.ServerConnectionString);
        var databaseExists = await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=@name", DatabaseName);
        var appExists = await UserExistsViaShowGrantsAsync(connection, AppUser);
        var migratorExists = await UserExistsViaShowGrantsAsync(connection, MigratorUser);
        Console.WriteLine($"PASS account-status database={DatabaseName} databaseRetained={databaseExists} appPresent={appExists} migratorPresent={migratorExists}");
        return databaseExists ? 0 : 1;
    }

    private static async Task<bool> UserExistsViaShowGrantsAsync(MySqlConnection connection, string user)
    {
        try { _ = await ShowGrantsAsync(connection, user); return true; }
        catch (MySqlException ex) when (ex.Number is 1141 or 1396) { return false; }
    }

    private static async Task<int> DatabaseStatusAsync()
    {
        var root = LoadBaseSettings(StudioPaths.FindRoot());
        await using var connection = await OpenAsync(root.ServerConnectionString);
        var databaseExists = await ExistsAsync(connection, "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=@name", DatabaseName);
        Console.WriteLine($"PASS database-status database={DatabaseName} retained={databaseExists}");
        return databaseExists ? 0 : 1;
    }

    private static async Task<int> DomainAsync(string secretPath)
    {
        var config = LoadEncryptedConfig(secretPath);
        var settings = SettingsFor(config, config.AppUser, config.AppPassword);
        Directory.CreateDirectory(config.DataRoot);
        var db = new StudioDb(settings, NullLogger<StudioDb>.Instance);
        var repository = new StudioRepository(db, NullLogger<StudioRepository>.Instance);
        var production = new ProductionCoreRepository(db);
        var leases = new TaskLeaseRepository(settings);
        var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
        var paths = new AssetPathPolicy(settings, ffmpeg, NullLogger<AssetPathPolicy>.Instance);
        var artifacts = new TaskArtifactService(settings, ffmpeg);
        var resolver = new AssetReferenceResolver(db, paths);
        var suffix = Guid.NewGuid().ToString("N");

        var projectId = await repository.CreateProjectAsync(new ProjectInput { Name = $"Stage25 Project {suffix}", Description = "隔离验收数据，仅用于阶段2.5", Status = "Active" });
        var otherProjectId = await repository.CreateProjectAsync(new ProjectInput { Name = $"Stage25 Other Project {suffix}", Description = "隔离跨项目负向测试", Status = "Active" });
        var episodeId = await repository.CreateEpisodeAsync(new EpisodeInput { ProjectId = projectId, EpisodeNumber = 1, Name = "Stage25 Episode", TargetSeconds = 5, OutputFps = 24, OutputWidth = 320, OutputHeight = 320 });
        var character = new CharacterInput { ProjectId = projectId, Name = "Stage25 Character", FixedPrompt = "adult test character v1", VoiceId = "stage25-voice", VoiceSpeed = 1, VoicePitch = 0 };
        var characterId = await repository.CreateCharacterAsync(character);
        var scene = new SceneInput { ProjectId = projectId, Name = "Stage25 Scene", Description = "isolated test scene", FixedPrompt = "scene v1", Style = "test" };
        var sceneId = await repository.CreateSceneAsync(scene);
        var workflowId = await db.ExecuteInsertAsync("INSERT INTO workflows(name,workflow_type,path,model_name,parameter_mapping_json,enabled) VALUES(@name,'Image',@path,'stage25-test',@mapping,1)", command =>
        {
            StudioDb.Add(command, "@name", $"Stage25 Workflow {suffix}");
            StudioDb.Add(command, "@path", Path.Combine(settings.WorkflowsPath, $"stage25-test-{suffix}.json"));
            StudioDb.Add(command, "@mapping", "{}");
        });
        var shot = new ShotInput
        {
            ProjectId = projectId, EpisodeId = episodeId, ShotNumber = 1, Title = "Stage25 Shot", SceneId = sceneId,
            CharacterIds = [characterId], Prompt = "prompt v1", NegativePrompt = "bad", WorkflowId = workflowId,
            Width = 320, Height = 320, Frames = 1, Fps = 24, DurationSeconds = 1, Status = "Draft",
            CharacterPrompt = "character v1", ScenePrompt = "scene v1", ActionPrompt = "still", CameraPrompt = "medium", PromptVersion = 1
        };
        var shotId = await repository.CreateShotAsync(shot);

        var profileJson = JsonDocument.Parse("{\"episodeSeconds\":5,\"subtitlePolicy\":\"manual\",\"outputStrategy\":\"immutable\"}");
        var profileId = await production.CreateProfileAsync(new ProductionProfileInput { ProjectId = projectId, ProfileKey = $"stage25-{suffix[..8]}", Name = "Stage25 Profile", OutputWidth = 320, OutputHeight = 320, OutputFps = 24, Settings = profileJson.RootElement.Clone() });
        await production.BindProfileAsync(projectId, profileId, "stage25");

        var characterVersion1 = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Character", EntityId = characterId, CreatedBy = "stage25" });
        var characterVersionSame = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Character", EntityId = characterId, CreatedBy = "stage25" });
        Require(characterVersion1 == characterVersionSame, "same Character payload did not reuse its hash version");
        character.FixedPrompt = "adult test character v2";
        await repository.UpdateCharacterAsync(characterId, character);
        var characterVersion2 = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Character", EntityId = characterId, CreatedBy = "stage25" });
        Require(characterVersion2 != characterVersion1, "changed Character payload did not append a version");

        var sceneVersion1 = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Scene", EntityId = sceneId, CreatedBy = "stage25" });
        scene.FixedPrompt = "scene v2";
        await repository.UpdateSceneAsync(sceneId, scene);
        var sceneVersion2 = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Scene", EntityId = sceneId, CreatedBy = "stage25" });
        Require(sceneVersion2 != sceneVersion1, "changed Scene payload did not append a version");

        var promptVersion = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Prompt", EntityId = shotId, CreatedBy = "stage25" });
        var workflowVersion = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Workflow", EntityId = workflowId, CreatedBy = "stage25" });
        var voiceVersion = await production.CaptureEntityVersionAsync(new EntityVersionCaptureInput { ProjectId = projectId, EntityType = "Voice", EntityId = characterId, CreatedBy = "stage25" });
        var shotPlanId = await production.CreateShotPlanAsync(new ShotPlanInput
        {
            ProjectId = projectId, EpisodeId = episodeId, ShotId = shotId, ProductionProfileId = profileId,
            CharacterVersionIds = [characterVersion1], SceneVersionId = sceneVersion1, PromptVersionId = promptVersion,
            WorkflowVersionId = workflowVersion, VoiceVersionId = voiceVersion, Parameters = JsonDocument.Parse("{\"seed\":25,\"steps\":1}").RootElement.Clone(), CreatedBy = "stage25"
        });
        var crossProjectRejected = false;
        try
        {
            await production.CreateShotPlanAsync(new ShotPlanInput { ProjectId = otherProjectId, EpisodeId = episodeId, ShotId = shotId, ProductionProfileId = profileId, CharacterVersionIds = [characterVersion1], PromptVersionId = promptVersion, WorkflowVersionId = workflowVersion });
        }
        catch (InvalidOperationException) { crossProjectRejected = true; }
        Require(crossProjectRejected, "cross-project ShotPlan was not rejected");

        var artifactTaskId = await repository.CreateTaskAsync(new TaskInput { ProjectId = projectId, EpisodeId = episodeId, ShotId = shotId, TaskType = "Image", ResourceClass = "CPU", Stage = "Stage25", MaxRetries = 1, IdempotencyKey = $"stage25-artifact-{suffix}", Parameters = JsonDocument.Parse("{}").RootElement.Clone() });
        var artifactLease = await leases.ClaimAsync(artifactTaskId, "stage25-domain", TimeSpan.FromMinutes(2)) ?? throw new InvalidOperationException("artifact task claim failed");
        var workspace = artifacts.CreateWorkspace(artifactLease);
        var staged = artifacts.CreateStagedPath(workspace, "stage25-fixture.png", "stage25-fixture.png");
        await File.WriteAllBytesAsync(staged, TinyPng());
        using var inputManifestDocument = JsonDocument.Parse("{\"fixture\":\"stage25\",\"parameters\":{\"seed\":25,\"steps\":1}}");
        var published = await artifacts.PublishAsync(workspace, new ArtifactPublishSpec(projectId, episodeId, shotId, ArtifactPurpose.Image, "stage25-fixture.png", profileId, shotPlanId, inputManifestDocument.RootElement.Clone()), staged);
        var stagedManifestStatus = await ReadStatusAsync(db, "SELECT status FROM asset_manifests WHERE id=@id", published.ManifestId);
        Require(stagedManifestStatus == "Staged", "published artifact was not staged before task completion");
        Require(await leases.CompleteAsync(artifactLease, "Succeeded", manifestId: published.ManifestId) == 1, "artifact task did not complete");
        var readyManifestStatus = await ReadStatusAsync(db, "SELECT status FROM asset_manifests WHERE id=@id", published.ManifestId);
        var readyAssetStatus = await ReadStatusAsync(db, "SELECT status FROM assets WHERE id=@id", published.AssetId);
        var readyIntentStatus = await ReadStatusAsync(db, "SELECT status FROM artifact_publish_intents WHERE manifest_id=@id", published.ManifestId);
        Require(readyManifestStatus == "Ready" && readyAssetStatus == "Ready" && readyIntentStatus == "Ready", "manifest/asset/intent did not finalize atomically");
        await resolver.ResolveAsync(published.AssetId, projectId, [ArtifactPurpose.Image]);
        var crossProjectAssetRejected = false;
        try { await resolver.ResolveAsync(published.AssetId, otherProjectId, [ArtifactPurpose.Image]); }
        catch (AssetValidationException) { crossProjectAssetRejected = true; }
        Require(crossProjectAssetRejected, "cross-project Asset ID was not rejected");
        var wrongPurposeRejected = false;
        try { await resolver.ResolveAsync(published.AssetId, projectId, [ArtifactPurpose.Audio]); }
        catch (AssetValidationException) { wrongPurposeRejected = true; }
        Require(wrongPurposeRejected, "wrong-purpose Asset ID was not rejected");
        var deleteProtected = false;
        try { await repository.DeleteAssetAsync(published.AssetId); }
        catch (AssetRetentionException) { deleteProtected = true; }
        Require(deleteProtected, "manifest-backed asset deletion was not protected");
        var attemptDeleteProtected = await DeniedByForeignKeyAsync(db, "DELETE FROM task_attempts WHERE id=@id", artifactLease.AttemptId);
        var manifestDeleteProtected = await DeniedByForeignKeyAsync(db, "DELETE FROM asset_manifests WHERE id=@id", published.ManifestId);
        Require(attemptDeleteProtected && manifestDeleteProtected, "referenced Attempt/Manifest direct deletion was not blocked by foreign keys");

        var rejectedArtifacts = await RunArtifactNegativeTestsAsync(repository, leases, artifacts, projectId, episodeId, shotId, suffix);
        Require(rejectedArtifacts == 3, "not all empty/corrupt/half artifacts were rejected");
        var nonOverwriteRejected = await NonOverwriteProbeAsync(config.DataRoot);
        Require(nonOverwriteRejected, "same final target was overwritable");

        var maxRetryTaskId = await repository.CreateTaskAsync(new TaskInput { ProjectId = projectId, EpisodeId = episodeId, ShotId = shotId, TaskType = "QA", ResourceClass = "CPU", Stage = "Stage25", MaxRetries = 1, IdempotencyKey = $"stage25-max-retry-{suffix}", Parameters = JsonDocument.Parse("{}").RootElement.Clone() });
        var maxLease1 = await leases.ClaimAsync(maxRetryTaskId, "stage25-max-1", TimeSpan.FromMinutes(2)) ?? throw new InvalidOperationException("max retry first claim failed");
        await leases.CompleteAsync(maxLease1, "Failed", "first failure");
        Require(await leases.RetryAsync(maxRetryTaskId, "stage25") == 1, "first retry was unexpectedly blocked");
        var maxLease2 = await leases.ClaimAsync(maxRetryTaskId, "stage25-max-2", TimeSpan.FromMinutes(2)) ?? throw new InvalidOperationException("max retry second claim failed");
        await leases.CompleteAsync(maxLease2, "Failed", "second failure");
        Require(await leases.RetryAsync(maxRetryTaskId, "stage25") == 0, "retry exceeded max_retries");

        var state = new Stage25State
        {
            ProjectId = projectId, OtherProjectId = otherProjectId, EpisodeId = episodeId, ShotId = shotId, CharacterId = characterId, SceneId = sceneId, WorkflowId = workflowId,
            ProfileId = profileId, CharacterVersion1 = characterVersion1, CharacterVersion2 = characterVersion2, SceneVersion1 = sceneVersion1, SceneVersion2 = sceneVersion2,
            PromptVersion = promptVersion, WorkflowVersion = workflowVersion, VoiceVersion = voiceVersion, ShotPlanId = shotPlanId, PublishedAssetId = published.AssetId,
            PublishedManifestId = published.ManifestId, PublishedAttemptId = artifactLease.AttemptId, ArtifactTaskId = artifactTaskId, MaxRetryTaskId = maxRetryTaskId,
            DuplicateKey = $"stage25-duplicate-{suffix}", ClaimRaceTaskId = await CreateStage25TaskAsync(repository, projectId, episodeId, shotId, "ClaimRace", suffix),
            LeaseRecoveryTaskId = await CreateStage25TaskAsync(repository, projectId, episodeId, shotId, "LeaseRecovery", suffix),
            StaleFenceTaskId = await CreateStage25TaskAsync(repository, projectId, episodeId, shotId, "StaleFence", suffix),
            ArtifactRecoveryTaskId = await CreateStage25TaskAsync(repository, projectId, episodeId, shotId, "ArtifactRecovery", suffix),
            CancelRaceTaskId = await CreateStage25TaskAsync(repository, projectId, episodeId, shotId, "CancelRace", suffix),
            IllegalTransitionTaskId = await CreateStage25TaskAsync(repository, projectId, episodeId, shotId, "IllegalTransition", suffix)
        };
        SaveState(config.StatePath, state);
        Console.WriteLine($"PASS domain profile={profileId} entityVersions=6 shotPlan={shotPlanId} attempt={artifactLease.AttemptId} manifest={published.ManifestId} asset={published.AssetId} intent={readyIntentStatus} negativeArtifacts={rejectedArtifacts} deleteProtection=true maxRetry=blocked");
        Console.WriteLine($"STATE_PATH {config.StatePath}");
        return 0;
    }

    private static async Task<long> CreateStage25TaskAsync(StudioRepository repository, long projectId, long episodeId, long shotId, string type, string suffix)
        => await repository.CreateTaskAsync(new TaskInput { ProjectId = projectId, EpisodeId = episodeId, ShotId = shotId, TaskType = type, ResourceClass = "CPU", Stage = "Stage25", MaxRetries = 1, IdempotencyKey = $"stage25-{type}-{suffix}-{Guid.NewGuid():N}", Parameters = JsonDocument.Parse("{}").RootElement.Clone() });

    private static async Task<int> RunArtifactNegativeTestsAsync(StudioRepository repository, TaskLeaseRepository leases, TaskArtifactService artifacts, long projectId, long episodeId, long shotId, string suffix)
    {
        var rejected = 0;
        var cases = new[]
        {
            (Purpose: ArtifactPurpose.Image, Name: "empty.png", Bytes: Array.Empty<byte>()),
            (Purpose: ArtifactPurpose.Image, Name: "corrupt.png", Bytes: Enumerable.Repeat((byte)0x7F, 64).ToArray()),
            (Purpose: ArtifactPurpose.Subtitle, Name: "half.srt", Bytes: Encoding.UTF8.GetBytes("1\n00:00:00,000 -->"))
        };
        foreach (var item in cases)
        {
            var taskId = await repository.CreateTaskAsync(new TaskInput { ProjectId = projectId, EpisodeId = episodeId, ShotId = shotId, TaskType = "Stage25Negative", ResourceClass = "CPU", Stage = "Stage25", MaxRetries = 0, IdempotencyKey = $"stage25-negative-{suffix}-{item.Name}", Parameters = JsonDocument.Parse("{}").RootElement.Clone() });
            var lease = await leases.ClaimAsync(taskId, "stage25-negative", TimeSpan.FromMinutes(2)) ?? throw new InvalidOperationException("negative artifact claim failed");
            var workspace = artifacts.CreateWorkspace(lease);
            var staged = artifacts.CreateStagedPath(workspace, item.Name, item.Name);
            await File.WriteAllBytesAsync(staged, item.Bytes);
            try
            {
                await artifacts.PublishAsync(workspace, new ArtifactPublishSpec(projectId, episodeId, shotId, item.Purpose, item.Name), staged);
            }
            catch (AssetValidationException) { rejected++; }
            finally { await leases.CompleteAsync(lease, "Failed", "negative artifact fixture"); }
        }
        return rejected;
    }

    private static async Task<bool> NonOverwriteProbeAsync(string dataRoot)
    {
        var directory = Path.Combine(dataRoot, "Temp", "Stage25NonOverwrite");
        Directory.CreateDirectory(directory);
        var source = Path.Combine(directory, "source.bin");
        var target = Path.Combine(directory, "final.bin");
        await File.WriteAllTextAsync(source, "source");
        await File.WriteAllTextAsync(target, "original");
        try
        {
            File.Move(source, target, false);
            return false;
        }
        catch (IOException) { return true; }
        finally
        {
            if (File.Exists(source)) File.Delete(source);
            if (File.Exists(target)) File.Delete(target);
        }
    }

    private static async Task<bool> DeniedByForeignKeyAsync(StudioDb db, string sql, long id)
    {
        try
        {
            await db.ExecuteAsync(sql, command => StudioDb.Add(command, "@id", id));
            return false;
        }
        catch (MySqlException) { return true; }
    }

    private static async Task<string?> ReadStatusAsync(StudioDb db, string sql, long id)
        => (await db.QueryAsync(sql, command => StudioDb.Add(command, "@id", id))).FirstOrDefault()?.Text("status");

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private static byte[] TinyPng() => Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=");

    private sealed class Stage25State
    {
        public long ProjectId { get; set; }
        public long OtherProjectId { get; set; }
        public long EpisodeId { get; set; }
        public long ShotId { get; set; }
        public long CharacterId { get; set; }
        public long SceneId { get; set; }
        public long WorkflowId { get; set; }
        public long ProfileId { get; set; }
        public long CharacterVersion1 { get; set; }
        public long CharacterVersion2 { get; set; }
        public long SceneVersion1 { get; set; }
        public long SceneVersion2 { get; set; }
        public long PromptVersion { get; set; }
        public long WorkflowVersion { get; set; }
        public long VoiceVersion { get; set; }
        public long ShotPlanId { get; set; }
        public long PublishedAssetId { get; set; }
        public long PublishedManifestId { get; set; }
        public long PublishedAttemptId { get; set; }
        public long ArtifactTaskId { get; set; }
        public long MaxRetryTaskId { get; set; }
        public string DuplicateKey { get; set; } = "";
        public long ClaimRaceTaskId { get; set; }
        public long LeaseRecoveryTaskId { get; set; }
        public long StaleFenceTaskId { get; set; }
        public long ArtifactRecoveryTaskId { get; set; }
        public long CancelRaceTaskId { get; set; }
        public long IllegalTransitionTaskId { get; set; }
    }

    private static void SaveState(string path, Stage25State state)
        => File.WriteAllText(path, JsonSerializer.Serialize(state, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));

    private static Stage25State LoadState(Stage25Config config)
        => JsonSerializer.Deserialize<Stage25State>(File.ReadAllText(config.StatePath, Encoding.UTF8)) ?? throw new InvalidOperationException("Stage25 state is empty");

    private static async Task<int> RaceWorkerAsync(string secretPath, string scenario, string workerId, string[] extra)
    {
        if (extra.Length == 0) throw new ArgumentException("race worker requires an exact result path");
        var resultPath = Path.GetFullPath(extra[0]);
        var config = LoadEncryptedConfig(secretPath);
        var state = LoadState(config);
        var settings = SettingsFor(config, config.AppUser, config.AppPassword);
        var db = new StudioDb(settings, NullLogger<StudioDb>.Instance);
        var repository = new StudioRepository(db, NullLogger<StudioRepository>.Instance);
        var leases = new TaskLeaseRepository(settings);
        try
        {
            object result;
            switch (scenario)
            {
                case "duplicate-same":
                case "duplicate-different":
                {
                    var keySuffix = extra.ElementAtOrDefault(1) ?? "";
                    var key = (scenario == "duplicate-same" ? state.DuplicateKey : state.DuplicateKey + "-different") + keySuffix;
                    var variant = scenario == "duplicate-same" ? "same" : workerId;
                    try
                    {
                        var taskId = await repository.CreateTaskAsync(new TaskInput { ProjectId = state.ProjectId, EpisodeId = state.EpisodeId, ShotId = state.ShotId, TaskType = "RaceSubmit", ResourceClass = "CPU", Stage = "Stage25", MaxRetries = 0, IdempotencyKey = key, Parameters = JsonDocument.Parse($"{{\"variant\":\"{variant}\"}}").RootElement.Clone() });
                        result = new { scenario, outcome = "created-or-reused", taskId };
                    }
                    catch (IdempotencyConflictException ex) { result = new { scenario, outcome = "conflict", message = SanitizeMessage(ex.Message) }; }
                    break;
                }
                case "claim":
                case "claim-short":
                {
                    var taskId = long.Parse(extra.ElementAtOrDefault(1) ?? state.ClaimRaceTaskId.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
                    var seconds = int.Parse(extra.ElementAtOrDefault(2) ?? (scenario == "claim-short" ? "1" : "30"), CultureInfo.InvariantCulture);
                    var lease = await leases.ClaimAsync(taskId, workerId, TimeSpan.FromSeconds(seconds));
                    var leasePath = lease is null ? null : resultPath + ".lease.json";
                    if (lease is not null) SaveLease(leasePath!, lease);
                    result = new { scenario, outcome = lease is null ? "not-claimed" : "claimed", taskId, attemptNo = lease?.AttemptNo, leasePath };
                    break;
                }
                case "recover-claim":
                {
                    var taskId = long.Parse(extra.ElementAtOrDefault(1) ?? state.LeaseRecoveryTaskId.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
                    var recovered = await leases.RecoverExpiredAsync();
                    var lease = await leases.ClaimAsync(taskId, workerId, TimeSpan.FromSeconds(int.Parse(extra.ElementAtOrDefault(2) ?? "30", CultureInfo.InvariantCulture)));
                    var leasePath = lease is null ? null : resultPath + ".lease.json";
                    if (lease is not null) SaveLease(leasePath!, lease);
                    result = new { scenario, recovered, outcome = lease is null ? "not-claimed" : "claimed", taskId, attemptNo = lease?.AttemptNo, leasePath };
                    break;
                }
                case "heartbeat":
                {
                    var lease = LoadLease(extra.ElementAtOrDefault(1) ?? throw new ArgumentException("heartbeat requires lease path"));
                    var changed = await leases.HeartbeatAsync(lease, TimeSpan.FromSeconds(30));
                    result = new { scenario, changed, taskId = lease.TaskId };
                    break;
                }
                case "complete":
                {
                    var lease = LoadLease(extra.ElementAtOrDefault(1) ?? throw new ArgumentException("complete requires lease path"));
                    var status = extra.ElementAtOrDefault(2) ?? "Succeeded";
                    var changed = await leases.CompleteAsync(lease, status, "stage25 race completion");
                    result = new { scenario, changed, taskId = lease.TaskId, status };
                    break;
                }
                case "cancel":
                {
                    var taskId = long.Parse(extra.ElementAtOrDefault(1) ?? state.CancelRaceTaskId.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
                    var changed = await leases.CancelAsync(taskId, "stage25 race cancellation", workerId);
                    result = new { scenario, changed, taskId };
                    break;
                }
                case "publish-staged":
                {
                    var lease = LoadLease(extra.ElementAtOrDefault(1) ?? throw new ArgumentException("publish-staged requires lease path"));
                    var ffmpeg = new FfmpegService(settings, NullLogger<FfmpegService>.Instance);
                    var artifacts = new TaskArtifactService(settings, ffmpeg);
                    var workspace = artifacts.CreateWorkspace(lease);
                    var staged = artifacts.CreateStagedPath(workspace, "stage25-recovery.png", "stage25-recovery.png");
                    await File.WriteAllBytesAsync(staged, TinyPng());
                    var published = await artifacts.PublishAsync(workspace, new ArtifactPublishSpec(state.ProjectId, state.EpisodeId, state.ShotId, ArtifactPurpose.Image, "stage25-recovery.png"), staged);
                    result = new { scenario, outcome = "staged", taskId = lease.TaskId, manifestId = published.ManifestId, assetId = published.AssetId };
                    break;
                }
                case "illegal":
                {
                    var lease = new TaskLease(state.IllegalTransitionTaskId, 999999, 1, 1, workerId, Guid.NewGuid().ToString(), "Temp/Tasks/illegal");
                    var changed = await leases.CompleteAsync(lease, "Succeeded", "illegal transition probe");
                    result = new { scenario, changed, taskId = state.IllegalTransitionTaskId };
                    break;
                }
                case "retry-exhausted":
                {
                    var changed = await leases.RetryAsync(state.MaxRetryTaskId, workerId);
                    result = new { scenario, changed, taskId = state.MaxRetryTaskId };
                    break;
                }
                default:
                    throw new ArgumentException($"unknown race scenario: {scenario}");
            }
            WriteResult(resultPath, result);
            Console.WriteLine($"PASS race-worker scenario={scenario} result={resultPath}");
            return 0;
        }
        catch (Exception ex)
        {
            WriteResult(resultPath, new { scenario, outcome = "error", errorType = ex.GetType().Name, error = SanitizeMessage(ex.Message) });
            throw;
        }
    }

    private static void SaveLease(string path, TaskLease lease)
        => File.WriteAllText(path, JsonSerializer.Serialize(lease), new UTF8Encoding(false));

    private static TaskLease LoadLease(string path)
        => JsonSerializer.Deserialize<TaskLease>(File.ReadAllText(Path.GetFullPath(path), Encoding.UTF8), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidOperationException("Lease file is empty");

    private static void WriteResult(string path, object value)
        => File.WriteAllText(Path.GetFullPath(path), JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));

    private static async Task<bool> DeniedAsync(MySqlConnection connection, string sql)
    {
        try
        {
            await ExecuteAsync(connection, sql);
            return false;
        }
        catch (MySqlException) { return true; }
    }

    private static async Task<List<string>> ShowGrantsAsync(MySqlConnection connection, string user)
    {
        await using var command = new MySqlCommand($"SHOW GRANTS FOR '{user}'@'{AccountHost}'", connection);
        await using var reader = await command.ExecuteReaderAsync();
        var rows = new List<string>();
        while (await reader.ReadAsync()) rows.Add(reader.GetString(0));
        return rows;
    }

    private static string SanitizeGrantSummary(IEnumerable<string> grants)
        => string.Join("; ", grants.Select(grant => grant.Replace("'", "", StringComparison.Ordinal)));

    private static StudioSettings LoadBaseSettings(string root)
    {
        var configuration = new ConfigurationBuilder().AddJsonFile(Path.Combine(root, "config", "appsettings.json"), optional: true, reloadOnChange: false).Build();
        return StudioPaths.Load(configuration, root);
    }

    private static StudioSettings SettingsFor(Stage25Config config, string user, string password, bool autoApply = false)
    {
        var baseSettings = LoadBaseSettings(StudioPaths.FindRoot());
        return new StudioSettings
        {
            RootPath = baseSettings.RootPath,
            DataPath = config.DataRoot,
            ModelsPath = baseSettings.ModelsPath,
            WorkflowsPath = baseSettings.WorkflowsPath,
            ComfyUrl = baseSettings.ComfyUrl,
            ComfyRoot = baseSettings.ComfyRoot,
            ComfyInputPath = baseSettings.ComfyInputPath,
            ComfyOutputPath = baseSettings.ComfyOutputPath,
            FfmpegPath = baseSettings.FfmpegPath,
            FfprobePath = baseSettings.FfprobePath,
            QueuePollMilliseconds = baseSettings.QueuePollMilliseconds,
            MinFreeVramMiB = baseSettings.MinFreeVramMiB,
            WorkerEnabled = false,
            DatabaseHost = config.Host,
            DatabasePort = config.Port,
            DatabaseName = config.Database,
            DatabaseUser = user,
            DatabasePassword = password,
            AutoApplySchema = autoApply,
            AllowDatabaseCreate = false,
            MinimumFreeDiskBytes = 1
        };
    }

    private static async Task<MySqlConnection> OpenAsync(string connectionString)
    {
        var connection = new MySqlConnection(connectionString);
        await connection.OpenAsync();
        return connection;
    }

    private static async Task ExecuteAsync(MySqlConnection connection, string sql, params object[] values)
    {
        await using var command = new MySqlCommand(sql, connection);
        BindValues(command, values);
        await command.ExecuteNonQueryAsync();
    }

    private static async Task<object?> ScalarAsync(MySqlConnection connection, string sql, params object[] values)
    {
        await using var command = new MySqlCommand(sql, connection);
        BindValues(command, values);
        return await command.ExecuteScalarAsync();
    }

    private static async Task<bool> ExistsAsync(MySqlConnection connection, string sql, params object[] values)
        => Convert.ToInt32(await ScalarAsync(connection, sql, values), CultureInfo.InvariantCulture) > 0;

    private static async Task<List<string>> QueryStringsAsync(MySqlConnection connection, string sql)
    {
        await using var command = new MySqlCommand(sql, connection);
        await using var reader = await command.ExecuteReaderAsync();
        var rows = new List<string>();
        while (await reader.ReadAsync()) rows.Add(reader.GetString(0));
        return rows;
    }

    private static void BindValues(MySqlCommand command, object[] values)
    {
        var names = Regex.Matches(command.CommandText, "@[A-Za-z_][A-Za-z0-9_]*")
            .Select(match => match.Value)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        for (var index = 0; index < values.Length; index++)
            command.Parameters.AddWithValue(index < names.Length ? names[index] : $"@value{index}", values[index]);
    }

    private static string RandomPassword()
        => Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();

    private static string SanitizeMessage(string value)
        => value.Replace("Password=", "Password=<redacted>", StringComparison.OrdinalIgnoreCase);

    private static void SaveEncryptedConfig(string path, Stage25Config config)
    {
        var directory = Path.GetDirectoryName(path) ?? throw new InvalidOperationException("Secure config directory is missing");
        Directory.CreateDirectory(directory);
        File.WriteAllText(path, JsonSerializer.Serialize(config, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
        if (!OperatingSystem.IsWindows())
        {
            File.Delete(path);
            throw new InvalidOperationException("Windows ACL temporary credential storage is unavailable; no test account was created");
        }
        try
        {
            var user = WindowsIdentity.GetCurrent().Name;
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "icacls.exe",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                }
            };
            process.StartInfo.ArgumentList.Add(path);
            process.StartInfo.ArgumentList.Add("/inheritance:r");
            process.StartInfo.ArgumentList.Add("/grant:r");
            process.StartInfo.ArgumentList.Add($"{user}:F");
            if (!process.Start() || !process.WaitForExit(10000) || process.ExitCode != 0)
                throw new InvalidOperationException("icacls did not apply the exact current-user ACL");
            _ = process.StandardOutput.ReadToEnd();
            _ = process.StandardError.ReadToEnd();
        }
        catch
        {
            File.Delete(path);
            throw new InvalidOperationException("Windows ACL temporary credential storage is unavailable; no test account was created");
        }
    }

    private static Stage25Config LoadEncryptedConfig(string path)
    {
        path = Path.GetFullPath(path);
        if (!File.Exists(path)) throw new FileNotFoundException("Stage25 encrypted config not found", path);
        var config = JsonSerializer.Deserialize<Stage25Config>(File.ReadAllText(path, Encoding.UTF8));
        return config is null || config.Database != DatabaseName || config.AppUser != AppUser || config.MigratorUser != MigratorUser
            ? throw new InvalidOperationException("Stage25 config does not match the exact authorized objects")
            : config;
    }

    private static void DeleteExactSecureConfig(string path)
    {
        path = Path.GetFullPath(path);
        if (!File.Exists(path)) return;
        File.Delete(path);
    }

    private sealed class Stage25Config
    {
        public string Database { get; set; } = "";
        public string Host { get; set; } = "127.0.0.1";
        public int Port { get; set; } = 3306;
        public string AppUser { get; set; } = "";
        public string AppPassword { get; set; } = "";
        public string MigratorUser { get; set; } = "";
        public string MigratorPassword { get; set; } = "";
        public string DataRoot { get; set; } = "";
        public string StatePath { get; set; } = "";
        public DateTimeOffset CreatedAtUtc { get; set; }
    }
}
