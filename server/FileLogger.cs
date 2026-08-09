using Microsoft.Extensions.Logging;

namespace VideoStudio.Server;

public sealed class FileLoggerProvider : ILoggerProvider
{
    private readonly string _directory;
    private readonly object _gate = new();
    private readonly long _maxBytes;

    public FileLoggerProvider(string directory, long maxBytes = 10 * 1024 * 1024)
    {
        _directory = directory;
        _maxBytes = maxBytes;
        Directory.CreateDirectory(directory);
    }

    public ILogger CreateLogger(string categoryName) => new FileLogger(this, categoryName);
    public void Dispose() { }

    private void Write(string category, LogLevel level, string message, Exception? exception)
    {
        lock (_gate)
        {
            var path = Path.Combine(_directory, "server.log");
            if (File.Exists(path) && new FileInfo(path).Length > _maxBytes)
            {
                var rotated = Path.Combine(_directory, $"server_{DateTime.Now:yyyyMMdd_HHmmss}.log");
                File.Move(path, rotated, true);
            }
            var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{level}] {category}: {message}" + (exception is null ? "" : Environment.NewLine + exception) + Environment.NewLine;
            File.AppendAllText(path, line);
        }
    }

    private sealed class FileLogger : ILogger
    {
        private readonly FileLoggerProvider _provider;
        private readonly string _category;
        public FileLogger(FileLoggerProvider provider, string category) { _provider = provider; _category = category; }
        public IDisposable BeginScope<TState>(TState state) where TState : notnull => NullScope.Instance;
        public bool IsEnabled(LogLevel logLevel) => logLevel != LogLevel.None;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        { if (IsEnabled(logLevel)) _provider.Write(_category, logLevel, formatter(state, exception), exception); }
    }

    private sealed class NullScope : IDisposable
    {
        public static readonly NullScope Instance = new();
        public void Dispose() { }
    }
}
