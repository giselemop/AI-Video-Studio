using System.Text.Json;

namespace VideoStudio.Server;

public static class CharacterLibrarySelfTest
{
    public static int Run()
    {
        var count = 0;
        string Canonical(string text)
        { using var document = JsonDocument.Parse(text); return CharacterLibraryService.CanonicalPayload(document.RootElement); }
        void Check(bool passed, string name)
        { if (!passed) throw new InvalidOperationException(name); count++; }
        const string initial = "{\"schema\":\"character-library-v1\",\"voice\":{\"id\":\"\",\"pitch\":0.00,\"speed\":1.00},\"reference\":\"abc\"}";
        var expected = Canonical(initial);
        Check(expected == Canonical(initial.Replace("0.00", "0.0").Replace("1.00", "1.0")), "MySQL decimal normalization must preserve the hash");
        Check(expected == Canonical(initial.Replace("0.00", "0").Replace("1.00", "1")), "integer numeric encoding must preserve the hash");
        Check(expected != Canonical(initial.Replace("1.00", "1.25")), "a real voice value change must change the hash");
        Check(expected != Canonical(initial.Replace("abc", "def")), "reference changes must change the hash");
        var rejected = false;
        try { Canonical(initial.Replace("1.00", "1.001")); } catch (AssetValidationException) { rejected = true; }
        Check(rejected, "unsupported precision cannot be silently rounded");
        var refs = CharacterLibraryService.BasicSlots.Select((slot, index) => new LibraryReference(index + 1, slot.View, $"test/{index}.png", new string('a', 64), 1, "NeedReview", slot.Framing)).ToArray();
        Check(CharacterLibraryService.Coverage(refs).Complete, "all nine reference slots are complete");
        Check(CharacterLibraryService.Coverage(refs.Where(r => r.Framing == "fullBody")).Present == 6, "full-body views do not replace face close-ups");
        Check(CharacterLibraryService.Coverage(refs.Where(r => r.View != "back")).Missing.Contains(new LibraryReferenceSlot("back", "fullBody")), "missing rear full-body view is reported");
        var capture = new LibraryVersionInput { ReferencePack = CharacterLibraryService.BasicPack, References = refs.Select(r => new LibraryReferenceInput(r.ReferenceId, r.View, r.Framing)).ToList() };
        Check(CharacterLibraryService.ValidateReferenceSlots(capture), "front close-up and front full-body may coexist");
        var duplicatesRejected = false;
        try { CharacterLibraryService.ValidateReferenceSlots(new LibraryVersionInput { References = [new(1, "front", "closeUp"), new(2, "front", "closeUp")] }); } catch (ArgumentException) { duplicatesRejected = true; }
        Check(duplicatesRejected, "duplicate view/framing pair is rejected");
        var incompleteRejected = false;
        try { CharacterLibraryService.ValidateReferenceSlots(new LibraryVersionInput { ReferencePack = CharacterLibraryService.BasicPack, References = [new(1, "front", "closeUp")] }); } catch (ArgumentException) { incompleteRejected = true; }
        Check(incompleteRejected, "incomplete pack cannot declare all nine references");
        Check(!CharacterLibraryService.ValidateReferenceSlots(new LibraryVersionInput { References = [new(1, "front")] }), "legacy capture remains legacy");
        var oldBinding = new LibraryBinding(CharacterLibraryService.Schema, 1, 1, 1, "hash", "front", 1, "x.png", "sha", 1, 1, "workflow", "scene", "Experimental");
        Check(!JsonSerializer.Serialize(oldBinding, CharacterLibraryService.Json).Contains("framing"), "legacy task fingerprints omit framing");
        var payload = new LibraryPayload(CharacterLibraryService.CurrentSchema, 1, "test", "test", "outfit", "identity", null, null, null, null, new(null, 1, 0), new(1, "workflow.json", "sha", "baseline480"), refs, "NeedReview", CharacterLibraryService.BasicPack, CharacterLibraryService.ViewConvention);
        var version = new LibraryVersion(1, 1, 1, "sha", payload, null);
        Check(CharacterLibraryService.SelectReference(version, "front", "closeUp").ReferenceId == 1, "face request selects exact face reference");
        Check(CharacterLibraryService.SelectReference(version, "front", "fullBody").ReferenceId == 4, "full-body request selects distinct front reference");
        var ambiguousRejected = false;
        try { CharacterLibraryService.SelectReference(version, "front", null); } catch (ArgumentException) { ambiguousRejected = true; }
        Check(ambiguousRejected, "missing framing cannot select an arbitrary front reference");
        Console.WriteLine($"CHARACTER_LIBRARY_SELF_TEST_PASSED {count}");
        return 0;
    }
}
