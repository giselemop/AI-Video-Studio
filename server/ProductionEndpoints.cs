using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace VideoStudio.Server;

public static class ProductionEndpoints
{
    public static void Map(WebApplication app)
    {
        app.MapGet("/api/scripts", async (long? projectId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ScriptsAsync(projectId, ct)));
        app.MapPost("/api/scripts", async (ScriptInput input, StudioRepository repo, CancellationToken ct) =>
        {
            if (input.ProjectId <= 0 || string.IsNullOrWhiteSpace(input.Content)) return Results.BadRequest(new { error = "项目和剧本内容不能为空" });
            var id = await repo.CreateScriptAsync(input, ct);
            return Results.Created($"/api/scripts/{id}", new { id });
        });
        app.MapGet("/api/scripts/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { script = (await repo.ScriptAsync(id, ct)).FirstOrDefault(), versions = await repo.ScriptVersionsAsync(id, ct) }));
        app.MapPut("/api/scripts/{id:long}", async (long id, ScriptInput input, string? changeNote, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateScriptAsync(id, input, changeNote, ct) }));
        app.MapGet("/api/scripts/{id:long}/versions", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ScriptVersionsAsync(id, ct)));
        app.MapPost("/api/scripts/{id:long}/analyze", async (long id, ScriptAnalyzeInput input, StudioRepository repo, ScriptAnalyzer analyzer, PromptEngine promptEngine, CancellationToken ct) =>
        {
            var script = (await repo.ScriptAsync(id, ct)).FirstOrDefault();
            if (script is null) return Results.NotFound(new { error = "剧本不存在" });
            var episodeId = input.EpisodeId ?? script.LongOrNull("episodeId");
            if (episodeId is null) return Results.BadRequest(new { error = "剧本尚未绑定 Episode，无法拆分镜头" });
            var projectId = script.Long("projectId");
            var characters = await repo.CharactersAsync(projectId, ct);
            var scenes = await repo.ScenesAsync(projectId, ct);
            var result = await analyzer.AnalyzeAsync(script.Text("content") ?? "", characters, scenes, input.UseLlm, ct);
            var created = new List<long>();
            foreach (var draft in result.Shots)
            {
                var scene = FindScene(scenes, draft.SceneName);
                var matchedCharacters = characters.Where(c => draft.CharacterNames.Any(name => string.Equals(name, c.Text("name"), StringComparison.OrdinalIgnoreCase) || name.Contains(c.Text("name") ?? "", StringComparison.OrdinalIgnoreCase))).ToList();
                var characterIds = matchedCharacters.Select(c => c.Long("id")).ToArray();
                var existing = (await repo.ShotByNumberAsync(episodeId.Value, draft.ShotNumber, ct)).FirstOrDefault();
                long shotId;
                if (existing is null)
                {
                    shotId = await repo.CreateShotAsync(new ShotInput
                    {
                        ProjectId = projectId, EpisodeId = episodeId.Value, ShotNumber = draft.ShotNumber, Title = draft.Title, Description = draft.Description,
                        SceneId = scene?.Long("id"), CharacterIds = characterIds.ToList(), Action = draft.Action, Dialogue = draft.Dialogue, Narration = draft.Narration,
                        Emotion = draft.Emotion, CameraType = draft.CameraType, CameraMotion = draft.CameraMotion, DurationSeconds = draft.DurationSeconds,
                        Width = 512, Height = 320, Frames = (int)Math.Round(draft.DurationSeconds * 24), Fps = 24, Seed = Random.Shared.NextInt64(1, 900000000),
                        MotionPreset = draft.CameraMotion, CameraPreset = draft.CameraType, Status = "Ready"
                    }, ct);
                }
                else
                {
                    shotId = existing.Long("id");
                    await repo.UpdateAnalyzedShotAsync(shotId, draft, scene?.Long("id"), characterIds, ct);
                }
                var current = (await repo.QueryShotAsync(shotId, ct)).FirstOrDefault();
                if (current is not null && !current.Bool("promptLocked"))
                {
                    var composition = promptEngine.Compose(matchedCharacters, scene, current);
                    await repo.SavePromptAsync(shotId, composition, false, "analysis", ct);
                }
                created.Add(shotId);
            }
            var analysisJson = JsonSerializer.Serialize(result);
            await repo.SaveScriptAnalysisAsync(id, analysisJson, ct);
            return Results.Ok(new { scriptId = id, episodeId, provider = result.Provider, shots = result.Shots, shotIds = created, missingCharacters = result.MissingCharacters, missingScenes = result.MissingScenes, draftCharacters = result.MissingCharacters.Select(name => new { name, status = "Character Missing", requiresConfirmation = true }), draftScenes = result.MissingScenes.Select(name => new { name, status = "Scene Draft", requiresConfirmation = true }) });
        });

        app.MapGet("/api/shots/{id:long}/prompt", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { shot = (await repo.QueryShotAsync(id, ct)).FirstOrDefault(), history = await repo.PromptHistoryAsync(id, ct) }));
        app.MapPost("/api/shots/{id:long}/generate-prompt", async (long id, StudioRepository repo, PromptEngine promptEngine, CancellationToken ct) =>
        {
            var shot = await FindShotAsync(repo, id, ct); if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            if (shot.Bool("promptLocked")) return Results.Ok(new { locked = true, prompt = shot.Text("prompt"), negativePrompt = shot.Text("negativePrompt"), version = shot.Int("promptVersion", 1) });
            var characters = await repo.CharactersAsync(null, ct); var selected = ResolveCharacterIds(shot, characters); var scene = await FindSceneByIdAsync(repo, shot.LongOrNull("sceneId"), ct);
            var composition = promptEngine.Compose(selected, scene, shot); await repo.SavePromptAsync(id, composition, false, "system", ct);
            return Results.Ok(new { locked = false, composition, shot = (await FindShotAsync(repo, id, ct)) });
        });
        app.MapPut("/api/shots/{id:long}/prompt", async (long id, PromptUpdateInput input, StudioRepository repo, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.Prompt)) return Results.BadRequest(new { error = "Prompt 不能为空" });
            var composition = new PromptComposition("", "", "", "", "", "", "", input.Prompt, input.NegativePrompt ?? "");
            var updated = await repo.SavePromptAsync(id, composition, input.Locked ?? false, input.Source, ct);
            return Results.Ok(new { updated, locked = input.Locked ?? false });
        });
        app.MapGet("/api/shots/{id:long}/prompt-history", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.PromptHistoryAsync(id, ct)));
        app.MapPost("/api/shots/{id:long}/prompt-history/{version:int}/rollback", async (long id, int version, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.RollbackPromptAsync(id, version, ct) }));

        app.MapGet("/api/shots/{id:long}/candidates", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.CandidatesAsync(id, ct)));
        app.MapGet("/api/shots/{id:long}/sound-effects", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ShotSoundEffectsAsync(id, ct)));
        app.MapPost("/api/shots/{id:long}/sound-effects", async (long id, ShotSoundEffectInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.BindShotSoundEffectAsync(id, input, ct) }));
        app.MapPost("/api/shots/{id:long}/candidates/{candidateId:long}/select", async (long id, long candidateId, StudioRepository repo, CancellationToken ct) =>
        {
            var path = await repo.SelectCandidateAsync(id, candidateId, ct); return path is null ? Results.NotFound(new { error = "候选关键帧不存在" }) : Results.Ok(new { selected = true, path });
        });
        app.MapPost("/api/shots/{id:long}/approve-keyframe", async (long id, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
        {
            var shot = await FindShotAsync(repo, id, ct); if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            var input = shot.Text("selectedKeyframePath") ?? shot.Text("inputImagePath");
            if (string.IsNullOrWhiteSpace(input) || !File.Exists(input)) return Results.BadRequest(new { error = "请先选择存在的关键帧候选" });
            var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = id, TaskType = "ImageToVideo", WorkflowId = shot.LongOrNull("workflowId"), InputImagePath = input, MaxRetries = 2, Stage = "I2V", Parameters = JsonSerializer.SerializeToDocument(new { positive = shot.Text("prompt"), negative = shot.Text("negativePrompt"), seed = shot.LongOrNull("seed") ?? Random.Shared.NextInt64(1, 900000000), width = shot.Int("width", 512), height = shot.Int("height", 320), frames = Math.Clamp((int)Math.Round(shot.Decimal("durationSeconds", 5) * shot.Decimal("fps", 24)), 49, 241), fps = shot.Decimal("fps", 24), duration = shot.Decimal("durationSeconds", 5), cameraMotion = shot.Text("cameraMotion"), action = shot.Text("action") }).RootElement.Clone() }, ct);
            await repo.UpdateShotStatusAsync(id, "VideoGenerating", ct); queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "VideoGenerating" });
        });
        app.MapPost("/api/shots/{id:long}/approve-video", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.UpdateShotStatusAsync(id, "AudioGenerating", ct) }));
        app.MapPost("/api/shots/{id:long}/rating", async (long id, RatingInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.RateShotAsync(id, input.Rating, ct) }));

        app.MapPost("/api/production/start", async (ProductionStartInput input, StudioRepository repo, GenerationQueue queue, ComfyUiClient comfy, StudioSettings settings, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(input.EpisodeId, ct)).FirstOrDefault(); if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var shots = await repo.ShotsAsync(input.EpisodeId, ct); if (shots.Count == 0) return Results.BadRequest(new { error = "Episode 没有可生产镜头" });
            var missing = new List<string>();
            foreach (var shot in shots)
            {
                if (string.IsNullOrWhiteSpace(shot.Text("prompt"))) missing.Add($"Shot {shot.Int("shotNumber")}: Prompt 未生成");
                var workflow = shot.Text("workflowPath"); if (string.IsNullOrWhiteSpace(workflow)) workflow = Path.Combine(settings.WorkflowsPath, "01_portrait_quality_api.json");
                if (!File.Exists(workflow)) missing.Add($"Shot {shot.Int("shotNumber")}: 工作流不存在 {workflow}");
                else
                {
                    foreach (Match model in Regex.Matches(await File.ReadAllTextAsync(workflow, ct), "\\\"(?:ckpt_name|unet_name|clip_name)\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"", RegexOptions.IgnoreCase))
                    {
                        var modelName = model.Groups[1].Value;
                        if (!Directory.Exists(settings.ModelsPath) || !Directory.EnumerateFiles(settings.ModelsPath, modelName, SearchOption.AllDirectories).Any()) missing.Add($"Shot {shot.Int("shotNumber")}: 模型缺失 {modelName}");
                    }
                }
            }
            var comfyStatus = await comfy.CheckAsync(ct); if (!comfyStatus.Online) missing.Add("ComfyUI API 当前离线");
            if (missing.Count > 0) return Results.BadRequest(new { error = "生产前检查未通过", missing });
            var mode = string.Equals(input.Mode, "AutoProduction", StringComparison.OrdinalIgnoreCase) ? "AutoProduction" : "ManualReview";
            await repo.UpdateEpisodeProductionAsync(input.EpisodeId, mode, episode.Text("narratorVoiceId"), episode.Decimal("voiceVolume", 1), episode.Decimal("bgmVolume", .18m), episode.Decimal("sfxVolume", .6m), ct);
            var runId = await repo.CreateProductionRunAsync(episode.Long("projectId"), input.EpisodeId, mode, shots.Count, ct);
            var taskIds = new List<long>(); var candidateCount = Math.Clamp(input.CandidateCount, 1, 3);
            foreach (var shot in shots)
            {
                await repo.UpdateShotStatusAsync(shot.Long("id"), "ImageGenerating", ct);
                for (var candidate = 0; candidate < candidateCount; candidate++)
                {
                    var parameters = JsonSerializer.SerializeToDocument(new { positive = shot.Text("prompt"), negative = shot.Text("negativePrompt"), seed = shot.LongOrNull("seed") is { } seed ? seed + candidate : Random.Shared.NextInt64(1, 900000000), width = shot.Int("width", 512), height = shot.Int("height", 320), frames = shot.Int("frames", 121), fps = shot.Decimal("fps", 24), candidateIndex = candidate + 1 }).RootElement.Clone();
                    var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = input.EpisodeId, ShotId = shot.Long("id"), TaskType = "Keyframe", WorkflowId = shot.LongOrNull("workflowId"), Priority = candidate == 0 ? 10 : 0, MaxRetries = 2, Stage = "Keyframe", Parameters = parameters }, ct);
                    taskIds.Add(taskId); queue.Enqueue(taskId);
                }
            }
            return Results.Accepted("/api/production/status", new { runId, mode, taskIds, totalShots = shots.Count, candidateCount });
        });
        app.MapGet("/api/production/status", async (long episodeId, StudioRepository repo, GenerationQueue queue, CancellationToken ct) => Results.Ok(new { run = (await repo.ProductionRunAsync(episodeId, ct)).FirstOrDefault(), shots = await repo.ShotsAsync(episodeId, ct), queue = queue.Status }));
        app.MapPost("/api/production/pause", (GenerationQueue queue) => { queue.Pause(); return Results.Ok(new { paused = true }); });
        app.MapPost("/api/production/resume", (GenerationQueue queue) => { queue.Resume(); return Results.Ok(new { paused = false }); });
        app.MapPost("/api/production/cancel", async (long episodeId, StudioRepository repo, GenerationQueue queue, CancellationToken ct) => { await queue.CancelEpisodeAsync(episodeId, ct); return Results.Ok(new { cancelled = true }); });

        app.MapGet("/api/audio/voices", (LocalTtsService tts) => Results.Ok(new { available = tts.IsAvailable, voices = new[] { new { id = "", name = "系统中文默认音色" }, new { id = "Huihui", name = "Microsoft Huihui（中文女声，若已安装）" }, new { id = "Yunxi", name = "Microsoft Yunxi（中文男声，若已安装）" } } }));
        app.MapPost("/api/audio/tts", async (TtsInput input, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.Text)) return Results.BadRequest(new { error = "对白或旁白文本不能为空" });
            var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = input.ProjectId, EpisodeId = input.EpisodeId, ShotId = input.ShotId, TaskType = "Audio", ResourceClass = "CPU", Stage = "TTS", MaxRetries = 1, Parameters = JsonSerializer.SerializeToDocument(input).RootElement.Clone() }, ct);
            queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "Pending" });
        });
        app.MapPost("/api/episodes/{episodeId:long}/subtitles", async (long episodeId, SubtitleGenerateInput input, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
        {
            var taskId = await repo.CreateTaskAsync(new TaskInput { EpisodeId = episodeId, TaskType = "Subtitles", ResourceClass = "CPU", Stage = "Subtitle", MaxRetries = 1, Parameters = JsonSerializer.SerializeToDocument(new { episodeId, outputName = input.OutputName }).RootElement.Clone() }, ct);
            queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId });
        });
        app.MapGet("/api/episodes/{episodeId:long}/subtitles", async (long episodeId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.SubtitlesAsync(episodeId, ct)));

        app.MapGet("/api/sound-effects", async (string? category, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.SoundEffectsAsync(category, ct)));
        app.MapPost("/api/sound-effects", async (HttpRequest request, StudioSettings settings, StudioRepository repo, CancellationToken ct) => await UploadLibraryFileAsync(request, settings, repo, false, ct));
        app.MapGet("/api/bgm", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.BgmTracksAsync(ct)));
        app.MapPost("/api/bgm", async (HttpRequest request, StudioSettings settings, StudioRepository repo, CancellationToken ct) => await UploadLibraryFileAsync(request, settings, repo, true, ct));
        app.MapPost("/api/episodes/{episodeId:long}/bgm/{bgmId:long}", async (long episodeId, long bgmId, BgmInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.BindEpisodeBgmAsync(episodeId, bgmId, Math.Clamp(input.Volume, 0, 1), ct) }));
        app.MapGet("/api/project-templates", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ProjectTemplatesAsync(ct)));
        app.MapPost("/api/project-templates", async (ProjectTemplateInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { id = await repo.CreateProjectTemplateAsync(input, ct) }));
        app.MapPost("/api/projects/{projectId:long}/apply-template/{templateId:long}", async (long projectId, long templateId, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.ApplyProjectTemplateAsync(projectId, templateId, ct) }));
        app.MapGet("/api/presets", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.PresetsAsync(ct)));

        app.MapPost("/api/episode/render", async (EpisodeRenderInput input, StudioRepository repo, GenerationQueue queue, StudioSettings settings, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(input.EpisodeId, ct)).FirstOrDefault(); if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var shots = await repo.ShotsAsync(input.EpisodeId, ct);
            var files = shots.OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))).Select(x => x.Text("finalVideoPath") ?? x.Text("videoPath") ?? x.Text("resultPath")).Where(x => !string.IsNullOrWhiteSpace(x) && File.Exists(x)).ToArray();
            if (files.Length == 0) return Results.BadRequest(new { error = "没有可合成的已通过视频镜头" });
            var shotStarts = new Dictionary<long, double>();
            var cursor = 0d;
            foreach (var shot in shots.OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))))
            {
                shotStarts[shot.Long("id")] = cursor;
                cursor += Math.Max(1, Convert.ToDouble(shot.Decimal("durationSeconds", 5)));
            }
            var voiceVolume = (double)episode.Decimal("voiceVolume", 1);
            var bgmVolume = (double)episode.Decimal("bgmVolume", .18m);
            var sfxVolume = (double)episode.Decimal("sfxVolume", .6m);
            var audioTracks = new List<object>();
            foreach (var audio in await repo.EpisodeAudioResultsAsync(input.EpisodeId, ct))
            {
                var path = audio.Text("path"); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
                var start = audio.LongOrNull("shotId") is { } shotId && shotStarts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
                audioTracks.Add(new { path, volume = voiceVolume, startSeconds = start });
            }
            foreach (var effect in await repo.EpisodeSoundEffectsAsync(input.EpisodeId, ct))
            {
                var path = effect.Text("path"); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
                var start = effect.LongOrNull("shotId") is { } shotId && shotStarts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
                audioTracks.Add(new { path, volume = Math.Clamp((double)effect.Decimal("volume", .6m) * sfxVolume, .05, 2), startSeconds = start + (double)effect.Decimal("startSeconds", 0) });
            }
            foreach (var bgm in await repo.EpisodeBgmAsync(input.EpisodeId, ct))
            {
                var path = bgm.Text("path"); if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) continue;
                audioTracks.Add(new { path, volume = Math.Clamp((double)bgm.Decimal("volume", .18m) * bgmVolume, .05, 2), startSeconds = 0d });
            }
            audioTracks.AddRange(input.AudioPaths.Where(File.Exists).Select(path => (object)new { path, volume = 1d, startSeconds = 0d }));
            var subtitlePath = input.IncludeSubtitles ? episode.Text("subtitlePath") : null;
            var parameters = JsonSerializer.SerializeToDocument(new { files, outputName = input.OutputName ?? $"{episode.Text("name") ?? "Episode"}_{episode.Int("episodeNumber", 1):000}.mp4", subtitlePath, audioTracks }).RootElement.Clone();
            var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = episode.LongOrNull("projectId"), EpisodeId = input.EpisodeId, TaskType = "EpisodeRender", ResourceClass = "CPU", Stage = "Episode", MaxRetries = 1, Parameters = parameters }, ct);
            queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId, files = files.Length });
        });

        app.MapGet("/api/system/settings/llm", async (StudioRepository repo, CancellationToken ct) => Results.Ok(new { provider = await repo.GetSettingAsync("llm.provider", ct) ?? "OpenAICompatible", baseUrl = await repo.GetSettingAsync("llm.base_url", ct), model = await repo.GetSettingAsync("llm.model", ct), temperature = await repo.GetSettingAsync("llm.temperature", ct) ?? "0.2", maxTokens = await repo.GetSettingAsync("llm.max_tokens", ct) ?? "3000", apiKeyConfigured = !string.IsNullOrWhiteSpace(await repo.GetSettingAsync("llm.api_key", ct)) }));
        app.MapPut("/api/system/settings/llm", async (LlmSettingsInput input, StudioRepository repo, CancellationToken ct) =>
        {
            await repo.SetSettingAsync("llm.provider", input.Provider, "llm", false, ct); await repo.SetSettingAsync("llm.base_url", input.BaseUrl, "llm", false, ct); await repo.SetSettingAsync("llm.model", input.Model, "llm", false, ct); await repo.SetSettingAsync("llm.temperature", input.Temperature.ToString(System.Globalization.CultureInfo.InvariantCulture), "llm", false, ct); await repo.SetSettingAsync("llm.max_tokens", input.MaxTokens.ToString(), "llm", false, ct);
            if (input.ApiKey is not null) await repo.SetSettingAsync("llm.api_key", input.ApiKey, "llm", true, ct);
            return Results.Ok(new { saved = true, apiKeyConfigured = !string.IsNullOrWhiteSpace(input.ApiKey) });
        });
        app.MapGet("/api/system/settings/audio", async (StudioRepository repo, LocalTtsService tts, CancellationToken ct) => Results.Ok(new { ttsAvailable = tts.IsAvailable, settings = await repo.GetSettingsAsync("audio", ct) }));
        app.MapGet("/api/production/recommendations", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ParameterRecommendationsAsync(ct)));
    }

    private static async Task<IResult> UploadLibraryFileAsync(HttpRequest request, StudioSettings settings, StudioRepository repo, bool bgm, CancellationToken ct)
    {
        if (!request.HasFormContentType) return Results.BadRequest(new { error = "请使用 multipart/form-data 上传音频" });
        var form = await request.ReadFormAsync(ct); var file = form.Files.GetFile("file"); if (file is null || file.Length == 0) return Results.BadRequest(new { error = "音频文件不能为空" });
        if (file.Length > 300L * 1024 * 1024) return Results.BadRequest(new { error = "音频文件不能超过 300MB" });
        var ext = Path.GetExtension(file.FileName).ToLowerInvariant(); if (ext is not ".wav" and not ".mp3" and not ".ogg" and not ".flac") return Results.BadRequest(new { error = "只允许 wav、mp3、ogg、flac" });
        var name = Path.GetFileNameWithoutExtension(file.FileName); var folder = Path.Combine(settings.DataPath, bgm ? "BGM" : "SoundEffects"); Directory.CreateDirectory(folder); var path = Path.Combine(folder, $"{Guid.NewGuid().ToString("N")}_{name}{ext}");
        await using (var stream = File.Create(path)) await file.CopyToAsync(stream, ct);
        await using var input = File.OpenRead(path); var hash = Convert.ToHexString(await SHA256.HashDataAsync(input, ct)).ToLowerInvariant();
        var probe = new FfmpegService(settings, LoggerFactory.Create(x => { }).CreateLogger<FfmpegService>());
        var duration = await probe.ProbeAsync(path, ct);
        if (bgm) { var id = await repo.AddBgmAsync(name, path, hash, duration?.DurationSeconds, decimal.TryParse(form["volume"], out var volume) ? volume : .18m, ct); return Results.Ok(new { id, path }); }
        var effect = await repo.AddSoundEffectAsync(name, form["category"].ToString() ?? "environment", path, hash, duration?.DurationSeconds, ct); return Results.Ok(new { id = effect, path });
    }

    private static async Task<Dictionary<string, object?>?> FindShotAsync(StudioRepository repo, long id, CancellationToken ct)
        => (await repo.QueryShotAsync(id, ct)).FirstOrDefault();

    private static async Task<Dictionary<string, object?>?> FindSceneByIdAsync(StudioRepository repo, long? id, CancellationToken ct)
    {
        if (id is null) return null;
        return (await repo.QuerySceneAsync(id.Value, ct)).FirstOrDefault();
    }

    private static Dictionary<string, object?>? FindScene(IReadOnlyList<Dictionary<string, object?>> scenes, string? name)
        => string.IsNullOrWhiteSpace(name) ? null : scenes.FirstOrDefault(x => string.Equals(x.Text("name"), name, StringComparison.OrdinalIgnoreCase) || name.Contains(x.Text("name") ?? "", StringComparison.OrdinalIgnoreCase));

    private static List<Dictionary<string, object?>> ResolveCharacterIds(IReadOnlyDictionary<string, object?> shot, IReadOnlyList<Dictionary<string, object?>> characters)
    {
        var ids = new HashSet<long>();
        try
        {
            using var json = shot.Json("characterIdsJson"); if (json.RootElement.ValueKind == JsonValueKind.Array) foreach (var item in json.RootElement.EnumerateArray()) if (item.TryGetInt64(out var id)) ids.Add(id);
        }
        catch { }
        return characters.Where(x => ids.Contains(x.Long("id"))).ToList();
    }
}
