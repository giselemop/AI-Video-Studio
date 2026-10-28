using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;

namespace VideoStudio.Server;

/// <summary>
/// OS file-handle mutex shared by every process using the same governed Data
/// root. The handle is released by the OS after crashes; the lock file itself
/// is intentionally retained as an audit breadcrumb.
/// </summary>
public sealed class GpuGlobalGate
{
    private readonly string _lockPath;
    private readonly ILogger<GpuGlobalGate> _logger;

    public GpuGlobalGate(StudioSettings settings, ILogger<GpuGlobalGate> logger)
    {
        var dataRoot = Path.GetFullPath(settings.DataPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var directory = Path.Combine(dataRoot, "Locks");
        EnsureNoReparsePoint(directory);
        Directory.CreateDirectory(directory);
        EnsureNoReparsePoint(directory);
        _lockPath = Path.Combine(directory, "gpu-generation.lock");
        _logger = logger;
    }

    public GpuGlobalGate(StudioSettings settings) : this(settings, NullLogger<GpuGlobalGate>.Instance) { }

    public string LockPath => _lockPath;

    public async Task<GpuGlobalLease> AcquireAsync(string owner, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(owner)) throw new ArgumentException("GPU lock owner is required", nameof(owner));
        var normalizedOwner = owner.Trim().Length <= 128 ? owner.Trim() : owner.Trim()[..128];
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                var stream = new FileStream(_lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None, 4096, FileOptions.Asynchronous | FileOptions.WriteThrough);
                try
                {
                    stream.SetLength(0);
                    var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
                    {
                        owner = normalizedOwner,
                        processId = Environment.ProcessId,
                        machine = Environment.MachineName,
                        acquiredAtUtc = DateTimeOffset.UtcNow
                    }));
                    await stream.WriteAsync(bytes, ct);
                    await stream.FlushAsync(ct);
                    stream.Flush(true);
                    _logger.LogInformation("Cross-process GPU gate acquired by {Owner} in process {ProcessId}", normalizedOwner, Environment.ProcessId);
                    return new GpuGlobalLease(stream, normalizedOwner, _logger);
                }
                catch
                {
                    await stream.DisposeAsync();
                    throw;
                }
            }
            catch (IOException ex) when (IsSharingViolation(ex))
            {
                await Task.Delay(200, ct);
            }
        }
    }

    private static bool IsSharingViolation(IOException exception)
        => (exception.HResult & 0xFFFF) is 32 or 33;

    private static void EnsureNoReparsePoint(string path)
    {
        var current = Directory.Exists(path) ? new DirectoryInfo(path) : new FileInfo(path).Directory;
        while (current is not null)
        {
            if (current.Exists && (current.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("GPU lock path crosses a reparse point");
            current = current.Parent;
        }
    }
}

public sealed class GpuGlobalLease : IAsyncDisposable, IDisposable
{
    private FileStream? _stream;
    private readonly string _owner;
    private readonly ILogger _logger;

    internal GpuGlobalLease(FileStream stream, string owner, ILogger logger)
    {
        _stream = stream;
        _owner = owner;
        _logger = logger;
    }

    public void Dispose()
    {
        var stream = Interlocked.Exchange(ref _stream, null);
        if (stream is null) return;
        try { stream.Dispose(); }
        finally { _logger.LogInformation("Cross-process GPU gate released by {Owner}", _owner); }
    }

    public async ValueTask DisposeAsync()
    {
        var stream = Interlocked.Exchange(ref _stream, null);
        if (stream is null) return;
        try { await stream.DisposeAsync(); }
        finally { _logger.LogInformation("Cross-process GPU gate released by {Owner}", _owner); }
    }
}
