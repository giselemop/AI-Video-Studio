namespace VideoStudio.Server;

public static class Stage12GpuProbe
{
    public static async Task RunAsync(string dataRoot, string id, string? mode = null)
    {
        Directory.CreateDirectory(dataRoot);
        var gate = new GpuGlobalGate(new StudioSettings { DataPath = dataRoot });
        await using var lease = await gate.AcquireAsync($"stage12-probe-{id}");
        await File.WriteAllTextAsync(Path.Combine(dataRoot, $"{id}.entered"), DateTimeOffset.UtcNow.ToString("O"));
        if (string.Equals(mode, "crash", StringComparison.OrdinalIgnoreCase))
        {
            await Task.Delay(Timeout.InfiniteTimeSpan);
            return;
        }
        await Task.Delay(700);
        await File.WriteAllTextAsync(Path.Combine(dataRoot, $"{id}.exited"), DateTimeOffset.UtcNow.ToString("O"));
    }
}
