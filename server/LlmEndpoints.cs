namespace VideoStudio.Server;

public sealed class LlmPreviewInput
{
    public string SystemPrompt { get; set; } = "";
    public string UserPrompt { get; set; } = "";
    public int MaxTokens { get; set; } = 3000;
}

public static class LlmEndpoints
{
    public static void MapLlmEndpoints(this WebApplication app)
    {
        app.MapPost("/api/llm/preview", async (LlmPreviewInput input, LlmProviderFactory factory, CancellationToken ct) =>
        {
            if (input.SystemPrompt.Length > 128 * 1024 || input.UserPrompt.Length > 512 * 1024)
                return Results.BadRequest(new { error = "LLM prompt exceeds the per-request character limit" });
            var preview = await factory.PreviewAsync(input.SystemPrompt, input.UserPrompt, Math.Clamp(input.MaxTokens, 1, 16000), ct);
            return preview.Allowed ? Results.Ok(preview) : Results.BadRequest(preview);
        });
    }
}
