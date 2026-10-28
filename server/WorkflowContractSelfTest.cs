using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace VideoStudio.Server;

/// <summary>
/// Read-only regression for the workflow admission boundary. It exercises the
/// same contract service used by task preflight and the worker, without opening
/// the database, starting a web listener, or submitting to ComfyUI.
/// </summary>
public static class WorkflowContractSelfTest
{
    public static Task<int> RunAsync()
    {
        try
        {
            var root = StudioPaths.FindRoot();
            var configuration = new ConfigurationBuilder()
                .AddJsonFile(Path.Combine(root, "config", "appsettings.json"), optional: true, reloadOnChange: false)
                .Build();
            var settings = StudioPaths.Load(configuration, root);
            var service = new WorkflowContractService(settings, NullLogger<WorkflowContractService>.Instance);
            var deadlineMethod = typeof(GenerationQueue).GetMethod("TaskDeadline", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!;
            double Deadline(string type, string resource, string file) => ((TimeSpan)deadlineMethod.Invoke(null, [type, resource, file])!).TotalMinutes;
            var pilotDeadlinesPassed = Deadline("ImageToVideo", "GPU", "infinitetalk_dialogue_125_api.json") == 120
                && Deadline("ImageToVideo", "GPU", "infinitetalk_dialogue_241_api.json") == 120
                && Deadline("ImageToVideo", "GPU", "infinitetalk_dialogue_125_exact_api.json") == 120
                && Deadline("ImageToVideo", "GPU", "infinitetalk_dialogue_241_exact_api.json") == 120
                && Deadline("ImageToVideo", "GPU", "ordinary_api.json") == 30
                && Deadline("Concat", "CPU", "infinitetalk_dialogue_241_api.json") == 10
                && Deadline("VideoRestore", "GPU", "ordinary_api.json") == 95;
            Console.WriteLine($"{(pilotDeadlinesPassed ? "PASS" : "FAIL")} scoped-pilot-deadlines-and-existing-routes");
            var inventory = service.Inventory();
            var contracted = inventory.Where(item => !string.IsNullOrWhiteSpace(item.ContractId)).ToArray();
            foreach (var item in contracted)
                Console.WriteLine($"{(item.Status == "Passed" ? "PASS" : "FAIL")} workflow={item.FileName} status={item.Status} models={item.Issues.Count == 0}");

            var ltxPath = Path.Combine(settings.WorkflowsPath, "12_ltx_face_stable_v3_api.json");
            using var validDocument = JsonDocument.Parse("""
            {
              "workflowVersion": "12_ltx_face_stable_v3_api.json",
              "width": 320,
              "height": 416,
              "frames": 73,
              "fps": 24,
              "duration": 3.042,
              "guideFrameIndex": 64,
              "inputSlots": { "firstFrame": "fixture.png", "guideFrame": "fixture.png" }
            }
            """);
            var plan = service.Prepare(
                ltxPath,
                "ImageToVideo",
                validDocument.RootElement,
                new Dictionary<string, string?> { ["firstFrame"] = "fixture.png", ["guideFrame"] = "fixture.png" },
                requireProductionRoute: true);
            var mappingPassed = plan.RequestedFrameCount == 73 && plan.ExecutionLength == 65 && plan.GuideFrameIndex == 64;
            Console.WriteLine($"{(mappingPassed ? "PASS" : "FAIL")} ltx-output-mapping requested=73 execution={plan.ExecutionLength} guide={plan.GuideFrameIndex}");

            using var wrongGuideDocument = JsonDocument.Parse(validDocument.RootElement.GetRawText().Replace("\"guideFrameIndex\": 64", "\"guideFrameIndex\": 72", StringComparison.Ordinal));
            var rejectedWrongGuide = false;
            try
            {
                service.Prepare(ltxPath, "ImageToVideo", wrongGuideDocument.RootElement, new Dictionary<string, string?> { ["firstFrame"] = "fixture.png", ["guideFrame"] = "fixture.png" }, requireProductionRoute: true);
            }
            catch (WorkflowContractException ex) when (ex.Code == "GUIDE_FRAME_MISMATCH")
            {
                rejectedWrongGuide = true;
            }
            Console.WriteLine($"{(rejectedWrongGuide ? "PASS" : "FAIL")} guide-frame-mismatch-rejected");

            var experimentalPath = Path.Combine(settings.WorkflowsPath, "02_ltx_i2v_quality_api.json");
            using var experimentalDocument = JsonDocument.Parse("""
            {
              "workflowVersion": "02_ltx_i2v_quality_api.json",
              "width": 512,
              "height": 320,
              "frames": 121,
              "fps": 24,
              "inputSlots": { "firstFrame": "fixture.png" }
            }
            """);
            var experimentalRejected = false;
            try
            {
                service.Prepare(experimentalPath, "ImageToVideo", experimentalDocument.RootElement, new Dictionary<string, string?> { ["firstFrame"] = "fixture.png" }, requireProductionRoute: true);
            }
            catch (WorkflowContractException ex) when (ex.Code == "WORKFLOW_EXPERIMENTAL")
            {
                experimentalRejected = true;
            }
            Console.WriteLine($"{(experimentalRejected ? "PASS" : "FAIL")} experimental-route-rejected");

            var passed = contracted.Length == service.Contracts.Count
                && contracted.All(item => item.Status == "Passed")
                && mappingPassed
                && rejectedWrongGuide
                && experimentalRejected;
            passed = passed && pilotDeadlinesPassed;
            Console.WriteLine(passed ? "WORKFLOW_CONTRACT_SELF_TEST_PASSED" : "WORKFLOW_CONTRACT_SELF_TEST_FAILED");
            return Task.FromResult(passed ? 0 : 1);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"WORKFLOW_CONTRACT_SELF_TEST_FAILED {ex.GetType().Name}: {ex.Message}");
            return Task.FromResult(1);
        }
    }
}
