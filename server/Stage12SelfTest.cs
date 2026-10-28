using System.Text.Json;

namespace VideoStudio.Server;

public static class Stage12SelfTest
{
    public static async Task<int> RunAsync()
    {
        var failures = new List<string>();
        void Check(bool condition, string name)
        {
            Console.WriteLine($"{(condition ? "PASS" : "FAIL")} {name}");
            if (!condition) failures.Add(name);
        }

        var left = CanonicalJson.Serialize(new { b = 2, a = 1, nested = new { z = true, c = "x" } });
        var right = CanonicalJson.Serialize(new { nested = new { c = "x", z = true }, a = 1, b = 2 });
        Check(left == right && CanonicalJson.Sha256(left) == CanonicalJson.Sha256(right), "canonical JSON is key-order invariant");
        Check(TaskStateMachine.CanTransition(TaskLifecycleState.Pending, TaskLifecycleState.Running), "Pending -> Running is legal");
        Check(TaskStateMachine.CanTransition(TaskLifecycleState.Running, TaskLifecycleState.Succeeded), "Running -> Succeeded is legal");
        Check(!TaskStateMachine.CanTransition(TaskLifecycleState.Succeeded, TaskLifecycleState.Running), "Succeeded -> Running is rejected");
        Check(!TaskStateMachine.CanTransition(TaskLifecycleState.Pending, TaskLifecycleState.Succeeded), "Pending -> Succeeded is rejected");
        Check(TaskStateMachine.CanTransition(TaskLifecycleState.Failed, TaskLifecycleState.Pending), "Failed -> Pending retry is legal");
        Check(TaskStateMachine.CanTransition(TaskLifecycleState.Cancelled, TaskLifecycleState.Pending), "Cancelled -> Pending retry is legal");
        Check(ArtifactPurposePolicy.Allows(ArtifactPurpose.Video, ".mp4"), "video purpose accepts mp4");
        Check(!ArtifactPurposePolicy.Allows(ArtifactPurpose.Video, ".srt"), "video purpose rejects subtitle extension");
        Check(ArtifactPurposePolicy.Allows(ArtifactPurpose.QaReport, ".md"), "QA report accepts markdown");

        var root = Path.Combine(Path.GetTempPath(), $"ai-video-studio-stage12-selftest-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        var settings = new StudioSettings { DataPath = root, FfmpegPath = "missing-ffmpeg", FfprobePath = "missing-ffprobe" };
        var artifacts = new TaskArtifactService(settings, new FfmpegService(settings, Microsoft.Extensions.Logging.Abstractions.NullLogger<FfmpegService>.Instance));
        var halfFile = Path.Combine(root, "half.srt");
        await File.WriteAllTextAsync(halfFile, "1\n00:00:00,000 --> ");
        var rejected = false;
        try { await artifacts.ValidateStagedAsync(halfFile, ArtifactPurpose.Subtitle); }
        catch (AssetValidationException) { rejected = true; }
        Check(rejected, "half-written subtitle cannot pass staged artifact validation");
        Console.WriteLine($"FIXTURE_ROOT {root}");
        return failures.Count == 0 ? 0 : 1;
    }
}
