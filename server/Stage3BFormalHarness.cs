using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using MySqlConnector;

namespace VideoStudio.Server;

/// <summary>
/// Gate 3 only: creates the explicitly authorized formal accounts, validates
/// their effective boundary, applies only 008 through the explicit migrator,
/// locks the migrator, and switches local.env away from root.
/// </summary>
public static class Stage3BFormalHarness
{
    private const string DatabaseName = "ai_video_studio";
    private const string AccountHost = "127.0.0.1";
    private const string AppUser = "ai_video_studio_app";
    private const string MigratorUser = "ai_video_studio_migrator";
    private const string RestoreDatabase = "ai_video_studio_restore_acceptance_20260813";
    private const string CredentialsFileName = "stage3b-formal-credentials.json";

    public static async Task<int> RunAsync(string[] args)
    {
        try
        {
            return args.FirstOrDefault() switch
            {
                "--stage3b-setup" => await SetupAsync(),
                "--stage3b-privilege" => await PrivilegeAsync(),
                "--stage3b-migrate" => await MigrateAsync(),
                "--stage3b-config-status" => await ConfigStatusAsync(),
                _ => Fail("usage: --stage3b-setup|privilege|migrate|config-status")
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"STAGE3B STOPPED: {ex.Message}");
            return 1;
        }
    }

    private static async Task<int> SetupAsync()
    {
        var settings = LoadSettings();
        if (!string.Equals(settings.DatabaseName, DatabaseName, StringComparison.Ordinal)
            || !string.Equals(settings.DatabaseUser, "root", StringComparison.OrdinalIgnoreCase)
            || string.IsNullOrWhiteSpace(settings.DatabasePassword))
            throw new InvalidOperationException("formal database/root baseline is not uniquely confirmed");

        var credentialsPath = CredentialsPath();
        if (File.Exists(credentialsPath))
            throw new InvalidOperationException("formal secure credentials already exist; refusing password rotation");

        var root = await OpenAsync(settings, "root", settings.DatabasePassword, DatabaseName);
        var snapshot = await ReadSnapshotAsync(root);
        if (snapshot.PendingOrRunning != 0 || snapshot.Tables != 41 || snapshot.Versions.Count != 5)
            throw new InvalidOperationException("formal pre-migration baseline is not the authorized 41-table/5-version idle baseline");

        var existingHosts = await QueryStringsAsync(root, $"SELECT Host FROM mysql.user WHERE User IN ('{AppUser}','{MigratorUser}') ORDER BY User,Host");
        if (existingHosts.Count != 0)
            throw new InvalidOperationException("an exact formal account name already exists; refusing overwrite or host-variant ambiguity");

        var credentials = new FormalCredentials
        {
            Database = DatabaseName,
            RootUser = "root",
            RootPassword = settings.DatabasePassword,
            AppUser = AppUser,
            AppPassword = RandomHex(32),
            MigratorUser = MigratorUser,
            MigratorPassword = RandomHex(32)
        };
        SaveSecureCredentials(credentialsPath, credentials);

        await ExecuteAsync(root, $"CREATE USER '{AppUser}'@'{AccountHost}' IDENTIFIED BY '{credentials.AppPassword}'");
        await ExecuteAsync(root, $"CREATE USER '{MigratorUser}'@'{AccountHost}' IDENTIFIED BY '{credentials.MigratorPassword}'");
        await ExecuteAsync(root, $"GRANT SELECT, INSERT, UPDATE, DELETE ON `{DatabaseName}`.* TO '{AppUser}'@'{AccountHost}'");
        await ExecuteAsync(root, $"GRANT SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES ON `{DatabaseName}`.* TO '{MigratorUser}'@'{AccountHost}'");

        var appGrants = await ShowGrantsAsync(root, AppUser);
        var migratorGrants = await ShowGrantsAsync(root, MigratorUser);
        ValidateGrants(appGrants, isApp: true);
        ValidateGrants(migratorGrants, isApp: false);
        Console.WriteLine("PASS formal accounts created exact at @127.0.0.1; grants are database-scoped and credentials remain local-secure");
        return 0;
    }

    private static async Task<int> PrivilegeAsync()
    {
        var credentials = LoadSecureCredentials();
        var app = await OpenAsync(credentials, credentials.AppUser, credentials.AppPassword, DatabaseName);
        var migrator = await OpenAsync(credentials, credentials.MigratorUser, credentials.MigratorPassword, DatabaseName);

        var checks = new List<string>();
        _ = await ScalarAsync(app, "SELECT COUNT(*) FROM projects");
        checks.Add("app-select");
        await DmlTransactionAsync(app);
        checks.Add("app-dml-rollback");

        await ExpectDeniedAsync(app, "CREATE TEMPORARY TABLE stage3b_permission_probe(id INT)", 1044, 1142);
        checks.Add("app-create-denied");
        await ExpectDeniedAsync(app, "ALTER TABLE projects ADD COLUMN name VARCHAR(160)", 1142);
        checks.Add("app-alter-denied");
        await ExpectDeniedAsync(app, "DROP TABLE stage3b_missing_permission_table", 1142);
        checks.Add("app-drop-denied");
        await ExpectDeniedAsync(app, $"GRANT SELECT ON `{DatabaseName}`.* TO '{AppUser}'@'{AccountHost}'", 1044, 1142, 1227);
        checks.Add("app-grant-denied");
        await ExpectDeniedAsync(app, $"CREATE USER 'stage3b_forbidden_user'@'{AccountHost}' IDENTIFIED BY 'not-used'", 1044, 1227);
        checks.Add("app-create-user-denied");
        await ExpectDeniedAsync(app, $"SELECT COUNT(*) FROM {RestoreDatabase}.projects", 1044, 1142);
        checks.Add("app-cross-db-denied");

        _ = await ScalarAsync(migrator, "SELECT COUNT(*) FROM projects");
        checks.Add("migrator-select");
        await ExpectDeniedAsync(migrator, "DELETE FROM generation_tasks WHERE id=0", 1142);
        checks.Add("migrator-delete-denied");
        await ExpectDeniedAsync(migrator, "DROP TABLE stage3b_missing_permission_table", 1142);
        checks.Add("migrator-drop-denied");
        await ExpectDeniedAsync(migrator, $"CREATE USER 'stage3b_forbidden_user'@'{AccountHost}' IDENTIFIED BY 'not-used'", 1044, 1227);
        checks.Add("migrator-create-user-denied");
        await ExpectDeniedAsync(migrator, $"GRANT SELECT ON `{DatabaseName}`.* TO '{MigratorUser}'@'{AccountHost}'", 1044, 1142, 1227);
        checks.Add("migrator-grant-denied");
        await ExpectDeniedAsync(migrator, $"SELECT COUNT(*) FROM {RestoreDatabase}.projects", 1044, 1142);
        checks.Add("migrator-cross-db-denied");

        var root = await OpenAsync(credentials, credentials.RootUser, credentials.RootPassword, DatabaseName);
        ValidateGrants(await ShowGrantsAsync(root, AppUser), isApp: true);
        ValidateGrants(await ShowGrantsAsync(root, MigratorUser), isApp: false);
        Console.WriteLine($"PASS formal least privilege checks={checks.Count}; app DML rollback and all forbidden DDL/GRANT/cross-db probes passed");
        return 0;
    }

    private static async Task<int> MigrateAsync()
    {
        var credentials = LoadSecureCredentials();
        var root = await OpenAsync(credentials, credentials.RootUser, credentials.RootPassword, DatabaseName);
        var before = await ReadSnapshotAsync(root);
        if (before.Tables != 41 || before.PendingOrRunning != 0 || before.Versions.Count != 5)
            throw new InvalidOperationException("formal migration baseline changed before explicit 008");

        var migrator = await OpenAsync(credentials, credentials.MigratorUser, credentials.MigratorPassword, DatabaseName);
        var migrationPath = Path.Combine(StudioPaths.FindRoot(), "database", "migrations", "008_stage12_production_core.sql");
        await Stage12SchemaMigrator.ApplyAsync(migrator, migrationPath);
        await migrator.CloseAsync();

        var afterFirst = await ReadSnapshotAsync(root);
        ValidatePostMigration(before, afterFirst);

        var second = await OpenAsync(credentials, credentials.MigratorUser, credentials.MigratorPassword, DatabaseName);
        await Stage12SchemaMigrator.ApplyAsync(second, migrationPath);
        await second.CloseAsync();
        var afterSecond = await ReadSnapshotAsync(root);
        ValidatePostMigration(before, afterSecond);

        await ExecuteAsync(root, $"ALTER USER '{MigratorUser}'@'{AccountHost}' ACCOUNT LOCK");
        var locked = Convert.ToString(await ScalarAsync(root, $"SELECT account_locked FROM mysql.user WHERE User='{MigratorUser}' AND Host='{AccountHost}'"));
        if (!string.Equals(locked, "Y", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("migrator account did not become ACCOUNT LOCKed");

        SwitchApplicationConfig(credentials);
        Console.WriteLine($"PASS formal 008 first-and-repeat migration; tables={afterSecond.Tables} versions={string.Join(',', afterSecond.Versions)} existingRowsUnchanged=true migratorLocked=true appConfigUser={AppUser}");
        return 0;
    }

    private static async Task<int> ConfigStatusAsync()
    {
        var settings = LoadSettings();
        if (!string.Equals(settings.DatabaseName, DatabaseName, StringComparison.Ordinal)
            || !string.Equals(settings.DatabaseHost, "127.0.0.1", StringComparison.Ordinal)
            || !string.Equals(settings.DatabaseUser, AppUser, StringComparison.Ordinal)
            || settings.AutoApplySchema || settings.WorkerEnabled)
            throw new InvalidOperationException("application config is not formal app/loopback/AUTO=0/Worker=0");
        var app = await OpenAsync(settings, settings.DatabaseUser, settings.DatabasePassword, DatabaseName);
        _ = await ScalarAsync(app, "SELECT 1");
        Console.WriteLine("PASS application config uses formal app@127.0.0.1; AUTO_APPLY_SCHEMA=0; Worker=0; database connection online");
        return 0;
    }

    private static void ValidatePostMigration(FormalSnapshot before, FormalSnapshot after)
    {
        if (after.Tables != 49 || after.Versions.Count != 6 || !after.Versions.Contains("008_stage12_production_core"))
            throw new InvalidOperationException("formal 008 structure/version result is incomplete");
        if (before.Projects != after.Projects || before.Episodes != after.Episodes || before.Shots != after.Shots
            || before.Assets != after.Assets || before.Tasks != after.Tasks || before.Results != after.Results
            || before.PendingOrRunning != after.PendingOrRunning || !string.Equals(before.Statuses, after.Statuses, StringComparison.Ordinal))
            throw new InvalidOperationException("formal existing row counts or task status aggregation changed unexpectedly");
        var requiredTables = new[] { "production_profiles", "project_production_profile_bindings", "entity_versions", "shot_plans", "task_attempts", "asset_manifests", "artifact_publish_intents", "llm_egress_audit" };
        if (after.RequiredTables != requiredTables.Length || after.RequiredColumns < 20 || after.RequiredIndexes < 8 || after.RequiredForeignKeys < 8)
            throw new InvalidOperationException("formal 008 required objects are incomplete");
    }

    private static async Task<FormalSnapshot> ReadSnapshotAsync(MySqlConnection connection)
    {
        var snapshot = new FormalSnapshot
        {
            Tables = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()")),
            Versions = await QueryStringsAsync(connection, "SELECT version FROM schema_migrations ORDER BY version"),
            Projects = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM projects")),
            Episodes = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM episodes")),
            Shots = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM shots")),
            Assets = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM assets")),
            Tasks = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM generation_tasks")),
            Results = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM generation_results")),
            PendingOrRunning = Convert.ToInt64(await ScalarAsync(connection, "SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running')")),
            Statuses = string.Join(',', await QueryStringsAsync(connection, "SELECT CONCAT(status,':',COUNT(*)) FROM generation_tasks GROUP BY status ORDER BY status")),
            RequiredTables = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('production_profiles','project_production_profile_bindings','entity_versions','shot_plans','task_attempts','asset_manifests','artifact_publish_intents','llm_egress_audit')")),
            RequiredColumns = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND ((table_name='generation_tasks' AND column_name IN ('production_profile_id','shot_plan_id','input_asset_id','active_attempt_id','lease_token','output_manifest_id')) OR (table_name='generation_results' AND column_name IN ('attempt_id','manifest_id')) OR (table_name='task_events' AND column_name IN ('attempt_id','lease_token','output_manifest_id')) OR (table_name='assets' AND column_name IN ('manifest_id','purpose','version','status','source_attempt_id','immutable_path')) OR (table_name='llm_egress_audit' AND column_name IN ('redacted_preview','redirect_count','timeout_ms')))")),
            RequiredIndexes = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND index_name IN ('ix_tasks_active_attempt','ix_tasks_input_asset','ix_tasks_profile_plan','ix_results_attempt','uq_results_manifest','ix_task_events_attempt','uq_assets_manifest','ix_assets_project_purpose_status')")),
            RequiredForeignKeys = Convert.ToInt32(await ScalarAsync(connection, "SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND constraint_type='FOREIGN KEY' AND constraint_name IN ('fk_tasks_active_attempt','fk_tasks_output_manifest','fk_results_attempt_stage12','fk_results_manifest_stage12','fk_task_events_attempt_stage12','fk_task_events_manifest_stage12','fk_assets_manifest_stage12','fk_assets_attempt_stage12')"))
        };
        return snapshot;
    }

    private static async Task DmlTransactionAsync(MySqlConnection connection)
    {
        await using var transaction = await connection.BeginTransactionAsync();
        await ExecuteAsync(connection, "INSERT INTO operation_logs(level,operation,message) VALUES('Info','stage3b_permission_probe','rolled back')", transaction);
        await ExecuteAsync(connection, "UPDATE projects SET name=name WHERE id=0", transaction);
        await ExecuteAsync(connection, "DELETE FROM generation_tasks WHERE id=0", transaction);
        await transaction.RollbackAsync();
    }

    private static async Task ExpectDeniedAsync(MySqlConnection connection, string sql, params int[] expectedCodes)
    {
        try
        {
            await ExecuteAsync(connection, sql);
        }
        catch (MySqlException ex) when (expectedCodes.Length == 0 || expectedCodes.Contains(ex.Number))
        {
            return;
        }
        catch (MySqlException ex)
        {
            throw new InvalidOperationException($"forbidden formal privilege probe returned MySQL {ex.Number}; expected {string.Join(',', expectedCodes)}");
        }
        throw new InvalidOperationException("a forbidden formal privilege probe unexpectedly succeeded or returned an unexpected error");
    }

    private static void ValidateGrants(IEnumerable<string> grants, bool isApp)
    {
        var rows = grants.Select(item => item.ToUpperInvariant()).ToArray();
        if (rows.Length == 0 || rows.Any(item => item.Contains("WITH GRANT OPTION", StringComparison.Ordinal)))
            throw new InvalidOperationException("formal account has no grants or has GRANT OPTION");
        foreach (var row in rows)
        {
            var usageOnly = row.StartsWith("GRANT USAGE ON *.*", StringComparison.Ordinal);
            if (!usageOnly && !row.Contains($"ON `{DatabaseName.ToUpperInvariant()}`.*", StringComparison.Ordinal))
                throw new InvalidOperationException("formal account has an unexpected global or other-database grant");
            if (isApp && (row.Contains(" CREATE ") || row.Contains(" ALTER ") || row.Contains(" DROP ") || row.Contains(" INDEX ") || row.Contains(" REFERENCES ") || row.Contains(" FILE ") || row.Contains(" PROCESS ") || row.Contains(" SUPER ") || row.Contains(" SYSTEM_USER ") || row.Contains(" CREATE USER ")))
                throw new InvalidOperationException("formal app account has forbidden effective privilege");
            if (!isApp && (row.Contains(" DROP ") || row.Contains(" DELETE ") || row.Contains(" FILE ") || row.Contains(" PROCESS ") || row.Contains(" SUPER ") || row.Contains(" SYSTEM_USER ") || row.Contains(" CREATE USER ")))
                throw new InvalidOperationException("formal migrator account has forbidden effective privilege");
        }
    }

    private static void SwitchApplicationConfig(FormalCredentials credentials)
    {
        var path = Path.Combine(StudioPaths.FindRoot(), "config", "local.env");
        var lines = File.ReadAllLines(path, Encoding.UTF8).ToList();
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_DB_NAME", credentials.Database);
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_DB_HOST", "127.0.0.1");
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_DB_USER", credentials.AppUser);
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_DB_PASSWORD", credentials.AppPassword);
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA", "0");
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_WORKER_ENABLED", "0");
        ReplaceOrAppend(lines, "AI_VIDEO_STUDIO_ALLOW_DATABASE_CREATE", "0");
        File.WriteAllLines(path, lines, new UTF8Encoding(false));
    }

    private static void ReplaceOrAppend(List<string> lines, string key, string value)
    {
        var index = lines.FindIndex(line => line.TrimStart().StartsWith(key + "=", StringComparison.Ordinal));
        if (index >= 0) lines[index] = key + "=" + value;
        else lines.Add(key + "=" + value);
    }

    private static StudioSettings LoadSettings()
    {
        var root = StudioPaths.FindRoot();
        var config = new ConfigurationBuilder().AddJsonFile(Path.Combine(root, "config", "appsettings.json"), optional: true, reloadOnChange: false).Build();
        return StudioPaths.Load(config, root);
    }

    private static async Task<MySqlConnection> OpenAsync(StudioSettings settings, string user, string password, string database)
    {
        var builder = new MySqlConnectionStringBuilder
        {
            Server = "127.0.0.1",
            Port = (uint)settings.DatabasePort,
            Database = string.Empty,
            UserID = user,
            Password = password,
            CharacterSet = "utf8mb4",
            ConnectionTimeout = 5,
            DefaultCommandTimeout = 120,
            AllowUserVariables = true,
            ConnectionProtocol = MySqlConnectionProtocol.Sockets,
            SslMode = MySqlSslMode.None,
            Pooling = false
        };
        var connection = new MySqlConnection(builder.ConnectionString);
        await connection.OpenAsync();
        await ExecuteAsync(connection, $"USE `{database}`");
        return connection;
    }

    private static async Task ExecuteAsync(MySqlConnection connection, string sql, MySqlTransaction? transaction = null)
    {
        await using var command = new MySqlCommand(sql, connection, transaction);
        await command.ExecuteNonQueryAsync();
    }

    private static async Task<object?> ScalarAsync(MySqlConnection connection, string sql)
    {
        await using var command = new MySqlCommand(sql, connection);
        return await command.ExecuteScalarAsync();
    }

    private static async Task<List<string>> QueryStringsAsync(MySqlConnection connection, string sql)
    {
        var result = new List<string>();
        await using var command = new MySqlCommand(sql, connection);
        await using var reader = await command.ExecuteReaderAsync();
        while (await reader.ReadAsync()) result.Add(Convert.ToString(reader.GetValue(0)) ?? string.Empty);
        return result;
    }

    private static async Task<List<string>> ShowGrantsAsync(MySqlConnection connection, string user)
        => await QueryStringsAsync(connection, $"SHOW GRANTS FOR '{user}'@'{AccountHost}'");

    private static async Task<MySqlConnection> OpenAsync(FormalCredentials credentials, string user, string password, string database, int port = 3306)
    {
        var builder = new MySqlConnectionStringBuilder
        {
            Server = "127.0.0.1",
            Port = (uint)port,
            Database = string.Empty,
            UserID = user,
            Password = password,
            CharacterSet = "utf8mb4",
            ConnectionTimeout = 5,
            DefaultCommandTimeout = 120,
            AllowUserVariables = true,
            ConnectionProtocol = MySqlConnectionProtocol.Sockets,
            SslMode = MySqlSslMode.None,
            Pooling = false
        };
        var connection = new MySqlConnection(builder.ConnectionString);
        await connection.OpenAsync();
        await ExecuteAsync(connection, $"USE `{database}`");
        return connection;
    }

    private static string RandomHex(int bytes) => Convert.ToHexString(RandomNumberGenerator.GetBytes(bytes)).ToLowerInvariant();

    private static string CredentialsPath() => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI-Video-Studio", CredentialsFileName);

    private static void SaveSecureCredentials(string path, FormalCredentials credentials)
    {
        var directory = Path.GetDirectoryName(path) ?? throw new InvalidOperationException("secure credential directory is missing");
        Directory.CreateDirectory(directory);
        File.WriteAllText(path, JsonSerializer.Serialize(credentials, new JsonSerializerOptions { WriteIndented = false }), new UTF8Encoding(false));
        if (!OperatingSystem.IsWindows()) throw new InvalidOperationException("formal secure credential ACL requires Windows");
        var current = WindowsIdentity.GetCurrent().Name;
        var psi = new System.Diagnostics.ProcessStartInfo
        {
            FileName = "icacls.exe",
            Arguments = $"\"{path}\" /inheritance:r /grant:r \"{current}:F\"",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        using var process = System.Diagnostics.Process.Start(psi) ?? throw new InvalidOperationException("icacls did not start");
        process.WaitForExit();
        if (process.ExitCode != 0) throw new InvalidOperationException("secure credential ACL could not be applied");
    }

    private static FormalCredentials LoadSecureCredentials()
    {
        var path = CredentialsPath();
        if (!File.Exists(path)) throw new FileNotFoundException("formal secure credentials are missing", path);
        var credentials = JsonSerializer.Deserialize<FormalCredentials>(File.ReadAllText(path, Encoding.UTF8));
        if (credentials is null || credentials.Database != DatabaseName || credentials.AppUser != AppUser || credentials.MigratorUser != MigratorUser)
            throw new InvalidOperationException("formal secure credentials do not match exact authorized objects");
        return credentials;
    }

    private static int Fail(string message)
    {
        Console.Error.WriteLine(message);
        return 2;
    }

    private sealed class FormalCredentials
    {
        public string Database { get; set; } = string.Empty;
        public string RootUser { get; set; } = string.Empty;
        public string RootPassword { get; set; } = string.Empty;
        public string AppUser { get; set; } = string.Empty;
        public string AppPassword { get; set; } = string.Empty;
        public string MigratorUser { get; set; } = string.Empty;
        public string MigratorPassword { get; set; } = string.Empty;
    }

    private sealed class FormalSnapshot
    {
        public int Tables { get; init; }
        public List<string> Versions { get; init; } = [];
        public long Projects { get; init; }
        public long Episodes { get; init; }
        public long Shots { get; init; }
        public long Assets { get; init; }
        public long Tasks { get; init; }
        public long Results { get; init; }
        public long PendingOrRunning { get; init; }
        public string Statuses { get; init; } = string.Empty;
        public int RequiredTables { get; init; }
        public int RequiredColumns { get; init; }
        public int RequiredIndexes { get; init; }
        public int RequiredForeignKeys { get; init; }
    }
}
