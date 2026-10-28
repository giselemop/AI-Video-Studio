namespace VideoStudio.Server;

public static class ReferenceMetadataSelfTest
{
    public static int Run()
    {
        try
        {
            var json = ReferenceMetadata.CreateJson("abc123", "受伤后", "outfit", "换成病号服");
            var metadata = ReferenceMetadata.Read(json, "identity");
            var roundTrip = metadata.Stage == "受伤后" && metadata.Role == "outfit" && metadata.ChangeReason == "换成病号服"
                && metadata.AssetVersion == 1 && metadata.Sha256 == "abc123";
            Console.WriteLine($"{(roundTrip ? "PASS" : "FAIL")} reference-metadata-round-trip");

            var rejected = false;
            try { ReferenceMetadata.NormalizeStage("..\\escape"); }
            catch (AssetValidationException) { rejected = true; }
            Console.WriteLine($"{(rejected ? "PASS" : "FAIL")} reference-stage-path-rejected");

            var defaulted = ReferenceMetadata.Read("{}", "environment");
            var defaultsPassed = defaulted.Stage == "base" && defaulted.Role == "environment" && defaulted.ReviewStatus == "NeedReview";
            Console.WriteLine($"{(defaultsPassed ? "PASS" : "FAIL")} reference-metadata-defaults");

            var passed = roundTrip && rejected && defaultsPassed;
            Console.WriteLine(passed ? "REFERENCE_METADATA_SELF_TEST_PASSED" : "REFERENCE_METADATA_SELF_TEST_FAILED");
            return passed ? 0 : 1;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"REFERENCE_METADATA_SELF_TEST_FAILED {ex.GetType().Name}: {ex.Message}");
            return 1;
        }
    }
}
