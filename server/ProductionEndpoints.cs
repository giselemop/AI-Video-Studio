using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
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
            if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
            var id = await repo.CreateScriptAsync(input, ct);
            return Results.Created($"/api/scripts/{id}", new { id });
        });
        app.MapGet("/api/scripts/{id:long}", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(new { script = (await repo.ScriptAsync(id, ct)).FirstOrDefault(), versions = await repo.ScriptVersionsAsync(id, ct) }));
        app.MapPut("/api/scripts/{id:long}", async (long id, ScriptInput input, string? changeNote, StudioRepository repo, CancellationToken ct) =>
        {
            if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
            return Results.Ok(new { updated = await repo.UpdateScriptAsync(id, input, changeNote, ct) });
        });
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
            if (TextEncodingGuard.FindError(input) is { } encodingError) return Results.BadRequest(new { error = encodingError });
            var composition = new PromptComposition("", "", "", "", "", "", "", input.Prompt, input.NegativePrompt ?? "");
            var updated = await repo.SavePromptAsync(id, composition, input.Locked ?? false, input.Source, ct);
            return Results.Ok(new { updated, locked = input.Locked ?? false });
        });
        app.MapGet("/api/shots/{id:long}/prompt-history", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.PromptHistoryAsync(id, ct)));
        app.MapPost("/api/shots/{id:long}/prompt-history/{version:int}/rollback", async (long id, int version, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.RollbackPromptAsync(id, version, ct) }));

        app.MapGet("/api/shots/{id:long}/candidates", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
            Results.Ok((await repo.CandidatesAsync(id, ct)).Select(candidate => ToPublicCandidate(candidate, paths))));
        app.MapGet("/api/shots/{id:long}/takes", async (long id, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
            Results.Ok((await repo.ShotTakesAsync(id, ct)).Select(take => ToPublicTake(take, paths))));
        app.MapGet("/api/shots/{id:long}/sound-effects", async (long id, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ShotSoundEffectsAsync(id, ct)));
        app.MapPost("/api/shots/{id:long}/sound-effects", async (long id, ShotSoundEffectInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.BindShotSoundEffectAsync(id, input, ct) }));
        app.MapPost("/api/shots/{id:long}/candidates/{candidateId:long}/select", async (long id, long candidateId, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var path = await repo.SelectCandidateAsync(id, candidateId, ct);
            if (path is null || !paths.TryResolveExisting(path, out _, out var assetPath)) return Results.NotFound(new { error = "候选关键帧不存在或不在受控媒体目录" });
            return Results.Ok(new { selected = true, assetPath, mediaUrl = $"/api/media?assetPath={Uri.EscapeDataString(assetPath)}" });
        });
        app.MapPost("/api/shots/{id:long}/approve-keyframe", async (long id, HttpRequest request, StudioRepository repo, GenerationQueue queue, FaceQualityService faceQuality, QualityPreflightService qualityPreflight, WorkflowContractService contracts, CharacterReferenceGateService characterReferences, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var shot = await FindShotAsync(repo, id, ct); if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            var input = shot.Text("selectedKeyframePath") ?? shot.Text("inputImagePath");
            if (!paths.TryResolveExisting(input, out var inputPath, out _)) return Results.BadRequest(new { error = "请先选择存在且位于受控目录的关键帧候选" });
            if (await repo.HasActiveTaskForShotAsync(id, "ImageToVideo", ct)) return Results.Conflict(new { error = "该镜头已有 I2V 任务正在排队或执行" });
            var characterIds = CharacterReferenceGateService.ReadCharacterIds(shot.Text("characterIdsJson"));
            var characterGate = characterIds.Count > 0 ? await characterReferences.CheckShotAsync(id, ct) : new CharacterReferenceGateResult(true, [], []);
            if (!characterGate.Passed)
                return Results.UnprocessableEntity(new { error = "角色参考图尚未通过当前版本的人工审核，未提交 I2V", characterReferenceApproval = characterGate });
            IReadOnlyList<string> references = characterIds.Count > 0
                ? characterGate.References.Select(reference => reference.FullPath).ToArray()
                : await repo.ShotReferencePathsAsync(id, ct);
            var referencePath = references.FirstOrDefault(reference => paths.IsAllowedExistingFile(reference));
            var face = await faceQuality.AnalyzeImageAsync(inputPath, referencePath, portraitPreferred: false, ct: ct);
            if (face.Rejected) return Results.UnprocessableEntity(new { error = "关键帧未通过脸部稳定性预检，请更换候选图", faceQuality = face.Metrics, issues = face.Issues });
            var idempotencyKey = RequestIdempotencyKey(request, $"shot:{id}:i2v:{StableKey(inputPath)}");
            var existing = await repo.TaskByIdempotencyKeyAsync(idempotencyKey, ct);
            if (existing is not null) return Results.Accepted($"/api/tasks/{existing.Long("id")}", new { taskId = existing.Long("id"), status = existing.Text("status") ?? "Pending", idempotent = true });
            var workflowId = shot.LongOrNull("workflowId");
            if (workflowId is null)
                return Results.UnprocessableEntity(new { error = "镜头没有显式绑定 I2V 工作流；不会按参考图数量自动选择路线" });
            var workflowRow = (await repo.WorkflowsAsync(ct)).FirstOrDefault(x => x.LongOrNull("id") == workflowId);
            if (workflowRow is null || !string.Equals(workflowRow.Text("workflowType"), "ImageToVideo", StringComparison.OrdinalIgnoreCase))
                return Results.UnprocessableEntity(new { error = "镜头绑定的工作流不是已登记的 ImageToVideo 路线" });
            if (!paths.TryResolveExistingWorkflow(workflowRow.Text("path"), out var controlledWorkflowPath, out _))
                return Results.UnprocessableEntity(new { error = "镜头绑定的工作流不在受控目录" });
            var workflowFile = Path.GetFileName(controlledWorkflowPath);
            var contract = contracts.Find(controlledWorkflowPath, workflowFile);
            if (contract is null || !contract.ProductionEligible)
                return Results.UnprocessableEntity(new { error = "镜头绑定的 I2V 工作流没有通过正式生产契约" });
            var frames = contract.Media.OutputFrames.FirstOrDefault();
            if (frames <= 0) return Results.UnprocessableEntity(new { error = "I2V 契约没有声明合法输出帧数" });
            var fps = (decimal)contract.Media.NativeFps;
            var duration = Math.Round(frames / fps, 3);
            var inputSlots = BuildVideoSlots(inputPath, contract.Media.RequiresGuide);
            var parametersObject = new JsonObject
            {
                ["positive"] = shot.Text("prompt"),
                ["negative"] = shot.Text("negativePrompt"),
                ["inputSlots"] = inputSlots,
                ["referenceRequired"] = characterIds.Count > 0,
                ["referenceProfile"] = characterIds.Count > 0 ? "character" : null,
                ["workflowVersion"] = workflowFile,
                ["width"] = contract.Media.DefaultWidth,
                ["height"] = contract.Media.DefaultHeight,
                ["frames"] = frames,
                ["fps"] = (double)fps,
                ["duration"] = (double)duration,
                ["cameraMotion"] = shot.Text("cameraMotion"),
                ["action"] = shot.Text("action"),
                ["inputStrength"] = 1.0,
                ["faceStabilityPriority"] = characterIds.Count > 0,
                ["allowLongVideo"] = false
            };
            if (shot.LongOrNull("seed") is { } seed) parametersObject["seed"] = seed;
            using var i2vParameters = JsonDocument.Parse(parametersObject.ToJsonString());
            var preflight = await qualityPreflight.CheckI2VAsync(id, new I2VPreflightInput { InputImagePath = inputPath, Parameters = i2vParameters.RootElement.Clone() }, ct);
            if (!preflight.Passed) return Results.UnprocessableEntity(new { error = "I2V 前置检查未通过，任务未提交", preflight });
             var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = id, TaskType = "ImageToVideo", WorkflowId = workflowRow.Long("id"), InputImagePath = inputPath, MaxRetries = 2, Stage = "I2V", RequestId = request.HttpContext.TraceIdentifier, IdempotencyKey = idempotencyKey, Parameters = i2vParameters.RootElement.Clone() }, ct);
            await repo.UpdateShotStatusAsync(id, "VideoGenerating", ct); queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "VideoGenerating" });
        });
        app.MapPost("/api/shots/{id:long}/approve-video", async (long id, HttpRequest request, StudioRepository repo, GenerationQueue queue, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var shot = await FindShotAsync(repo, id, ct);
            if (shot is null) return Results.NotFound(new { error = "镜头不存在" });
            var input = shot.Text("finalVideoPath") ?? shot.Text("videoPath");
            if (!paths.TryResolveExisting(input, out var inputPath, out _)) return Results.BadRequest(new { error = "请先生成并审核位于受控目录的有效视频" });
            if (await repo.HasActiveTaskForShotAsync(id, "Enhance", ct)) return Results.Conflict(new { error = "该镜头的视频增强任务已在队列中" });
            var idempotencyKey = RequestIdempotencyKey(request, $"shot:{id}:enhance:{StableKey(inputPath)}");
            var existing = await repo.TaskByIdempotencyKeyAsync(idempotencyKey, ct);
            if (existing is not null) return Results.Accepted($"/api/tasks/{existing.Long("id")}", new { taskId = existing.Long("id"), status = existing.Text("status") ?? "Pending", idempotent = true });
            var taskId = await repo.CreateTaskAsync(new TaskInput
            {
                ProjectId = shot.LongOrNull("projectId"), EpisodeId = shot.LongOrNull("episodeId"), ShotId = id,
                TaskType = "Enhance", ResourceClass = "CPU", Stage = "PostProcessing", InputImagePath = inputPath,
                MaxRetries = 1, RequestId = request.HttpContext.TraceIdentifier, IdempotencyKey = idempotencyKey,
                Parameters = JsonSerializer.SerializeToDocument(new { inputImagePath = inputPath, width = 1920, height = 1080, fps = 24, deflicker = false, interpolate = false, qaRetry = false }).RootElement.Clone()
            }, ct);
            await repo.UpdateShotStatusAsync(id, "PostProcessing", ct);
            queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = "PostProcessing" });
        });
        app.MapPost("/api/shots/{id:long}/rating", async (long id, RatingInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.RateShotAsync(id, input.Rating, ct) }));

        app.MapPost("/api/production/start", async (ProductionStartInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, ComfyUiClient comfy, LocalTtsService tts, StudioSettings settings, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var episode = (await repo.EpisodeAsync(input.EpisodeId, ct)).FirstOrDefault(); if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            var shots = await repo.ShotsAsync(input.EpisodeId, ct); if (shots.Count == 0) return Results.BadRequest(new { error = "Episode 没有可生产镜头" });
            var requestedMode = string.Equals(input.Mode, "AutoProduction", StringComparison.OrdinalIgnoreCase) ? "AutoProduction" : "ManualReview";
            var requestKey = string.IsNullOrWhiteSpace(input.IdempotencyKey) ? request.Headers["Idempotency-Key"].FirstOrDefault()?.Trim() : input.IdempotencyKey.Trim();
            var existingRun = string.IsNullOrWhiteSpace(requestKey) ? null : await repo.ProductionRunByIdempotencyKeyAsync(requestKey, ct);
            if (existingRun is not null)
            {
                if (existingRun.LongOrNull("projectId") != episode.LongOrNull("projectId") || existingRun.LongOrNull("episodeId") != input.EpisodeId || !string.Equals(existingRun.Text("mode"), requestedMode, StringComparison.OrdinalIgnoreCase) || existingRun.Int("totalShots", -1) != shots.Count)
                    return Results.Conflict(new { error = "Idempotency-Key 已绑定到不同的生产批次" });
                var existingTasks = await repo.ProductionRunTasksAsync(existingRun.Long("id"), ct);
                return Results.Accepted("/api/production/status", new { runId = existingRun.Long("id"), mode = existingRun.Text("mode"), taskIds = existingTasks.Select(x => x.Long("id")).ToArray(), totalShots = existingRun.Int("totalShots", shots.Count), candidateCount = input.CandidateCount, idempotent = true });
            }
            var activeRun = await repo.ActiveProductionRunAsync(input.EpisodeId, ct);
            if (activeRun is not null) return Results.Conflict(new { error = "本集已有生产任务正在执行，请等待完成或使用同一个 Idempotency-Key 重试", runId = activeRun.Long("id") });
            if (string.IsNullOrWhiteSpace(requestKey)) requestKey = $"production:{input.EpisodeId}:{Guid.NewGuid():N}";
            var missing = new List<string>();
            var workflows = await repo.WorkflowsAsync(ct);
            var keyframeWorkflow = workflows.FirstOrDefault(x => string.Equals(x.Text("workflowType"), "Image", StringComparison.OrdinalIgnoreCase) && (x.Text("name") ?? "").Contains("scene_keyframe", StringComparison.OrdinalIgnoreCase))
                ?? workflows.FirstOrDefault(x => string.Equals(x.Text("workflowType"), "Image", StringComparison.OrdinalIgnoreCase));
            var keyframeWorkflowPath = keyframeWorkflow?.Text("path");
            if (string.IsNullOrWhiteSpace(keyframeWorkflowPath)) keyframeWorkflowPath = Path.Combine(settings.WorkflowsPath, "06_scene_keyframe_quality_api.json");
            var referenceKeyframeWorkflowPath = Path.Combine(settings.WorkflowsPath, "06_scene_keyframe_reference_api.json");
            var referenceVideoWorkflowPath = Path.Combine(settings.WorkflowsPath, "12_ltx_face_stable_v3_api.json");
            var ipAdapterWorkflowPath = Path.Combine(settings.WorkflowsPath, "13_sd15_ipadapter_face_v1_api.json");
            var ipAdapterAvailable = File.Exists(ipAdapterWorkflowPath)
                && Directory.Exists(Path.Combine(settings.ModelsPath, "ipadapter"))
                && Directory.EnumerateFiles(Path.Combine(settings.ModelsPath, "ipadapter"), "*face*", SearchOption.AllDirectories).Any()
                && Directory.Exists(Path.Combine(settings.ModelsPath, "clip_vision"))
                && Directory.EnumerateFiles(Path.Combine(settings.ModelsPath, "clip_vision"), "*", SearchOption.AllDirectories).Any();
            foreach (var shot in shots)
            {
                if (string.IsNullOrWhiteSpace(shot.Text("prompt"))) missing.Add($"Shot {shot.Int("shotNumber")}: Prompt 未生成");
                var selectedWorkflow = workflows.FirstOrDefault(x => x.LongOrNull("id") == shot.LongOrNull("workflowId"));
                var workflow = selectedWorkflow?.Text("path");
                var workflowType = selectedWorkflow?.Text("workflowType");
                if (string.IsNullOrWhiteSpace(workflow) || (!string.IsNullOrWhiteSpace(workflowType) && !workflowType.Equals("ImageToVideo", StringComparison.OrdinalIgnoreCase))) workflow = Path.Combine(settings.WorkflowsPath, "05_wan22_ti2v_5b_api.json");
                foreach (var requiredWorkflow in new[] { workflow, keyframeWorkflowPath, referenceKeyframeWorkflowPath, referenceVideoWorkflowPath, ipAdapterAvailable ? ipAdapterWorkflowPath : null }.Where(x => !string.IsNullOrWhiteSpace(x)).Distinct(StringComparer.OrdinalIgnoreCase))
                {
                    if (!paths.TryResolveExistingWorkflow(requiredWorkflow, out var controlledRequiredWorkflow, out _))
                    {
                        missing.Add($"Shot {shot.Int("shotNumber")}: 工作流不在受控目录 {Path.GetFileName(requiredWorkflow)}");
                        continue;
                    }
                    if (!File.Exists(controlledRequiredWorkflow))
                    {
                        missing.Add($"Shot {shot.Int("shotNumber")}: 工作流不存在 {Path.GetFileName(controlledRequiredWorkflow)}");
                        continue;
                    }
                    foreach (Match model in Regex.Matches(await File.ReadAllTextAsync(controlledRequiredWorkflow, ct), "\\\"(?:ckpt_name|unet_name|clip_name)\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"", RegexOptions.IgnoreCase))
                    {
                        var modelName = model.Groups[1].Value;
                        var modelFileName = Path.GetFileName(modelName);
                        var modelExists = !string.IsNullOrWhiteSpace(modelFileName)
                            && Directory.Exists(settings.ModelsPath)
                            && Directory.EnumerateFiles(settings.ModelsPath, "*", SearchOption.AllDirectories)
                                .Any(file => string.Equals(Path.GetFileName(file), modelFileName, StringComparison.OrdinalIgnoreCase) && paths.IsAllowedExistingModelFile(file));
                        if (!modelExists) missing.Add($"Shot {shot.Int("shotNumber")}: 模型缺失 {modelFileName}");
                    }
                }
            }
            var comfyStatus = await comfy.CheckAsync(ct); if (!comfyStatus.Online) missing.Add("ComfyUI API 当前离线");
            if (missing.Count > 0) return Results.BadRequest(new { error = "生产前检查未通过", missing });
            if (input.GenerateAudio && shots.Any(HasSpeech))
            {
                var characters = await repo.CharactersAsync(episode.LongOrNull("projectId"), ct);
                var voicesToCheck = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                if (!string.IsNullOrWhiteSpace(episode.Text("narratorVoiceId"))) voicesToCheck.Add(episode.Text("narratorVoiceId")!);
                foreach (var shot in shots)
                {
                    foreach (var speaker in ParseSpeakers(shot.Text("dialogue")))
                    {
                        var character = characters.FirstOrDefault(x => string.Equals(x.Text("name"), speaker, StringComparison.OrdinalIgnoreCase));
                        voicesToCheck.Add(character?.Text("voiceId") ?? "");
                    }
                    if (!string.IsNullOrWhiteSpace(shot.Text("narration"))) voicesToCheck.Add(episode.Text("narratorVoiceId") ?? "");
                }
                if (voicesToCheck.Count == 0) voicesToCheck.Add("");
                foreach (var voice in voicesToCheck)
                {
                    var preflight = await tts.PreflightAsync(voice, ct);
                    if (!preflight.Passed) return Results.BadRequest(new { error = "中文 TTS 预检未通过，已阻止生产提交", voiceId = voice, detail = preflight.Message });
                }
            }
            var mode = requestedMode;
            await repo.UpdateEpisodeProductionAsync(input.EpisodeId, mode, episode.Text("narratorVoiceId"), episode.Decimal("voiceVolume", 1), episode.Decimal("bgmVolume", .18m), episode.Decimal("sfxVolume", .6m), ct);
            var runId = await repo.CreateProductionRunAsync(episode.Long("projectId"), input.EpisodeId, mode, shots.Count, requestKey, ct);
            var taskIds = new List<long>(); var candidateCount = Math.Clamp(input.CandidateCount, 1, 3);
            foreach (var shot in shots)
            {
                await repo.UpdateShotStatusAsync(shot.Long("id"), "ImageGenerating", ct);
                var referenceImages = await repo.ShotReferencePathsAsync(shot.Long("id"), ct);
                var useIpAdapter = ipAdapterAvailable && referenceImages.Count > 0 && HasCharacterReference(shot);
                for (var candidate = 0; candidate < candidateCount; candidate++)
                {
                    var keyframePrompt = PromptEngine.Englishize(shot.Text("prompt"));
                    if (!string.IsNullOrWhiteSpace(keyframePrompt)) keyframePrompt = $"{keyframePrompt}, cinematic photorealistic movie still, natural realistic lighting, coherent production design";
                    var keyframeNegative = PromptEngine.Englishize(shot.Text("negativePrompt"));
                    var routeFile = referenceImages.Count == 0
                        ? "01_portrait_quality_api.json"
                        : useIpAdapter
                            ? "13_sd15_ipadapter_face_v1_api.json"
                            : HasCharacterReference(shot)
                                ? "09_character_master_reference_v2_api.json"
                                : "06_scene_keyframe_reference_api.json";
                    var routeWorkflow = workflows.FirstOrDefault(x => string.Equals(Path.GetFileName(x.Text("path") ?? ""), routeFile, StringComparison.OrdinalIgnoreCase));
                    if (routeWorkflow is null) return Results.UnprocessableEntity(new { error = $"数据库未登记工作流 {routeFile}，未提交生产" });
                    var routeWidth = routeFile.StartsWith("06_", StringComparison.OrdinalIgnoreCase) ? 768 : 640;
                    var routeHeight = routeFile.StartsWith("06_", StringComparison.OrdinalIgnoreCase) ? 512 : 832;
                    var inputSlots = new JsonObject();
                    if (referenceImages.Count > 0) inputSlots[useIpAdapter || HasCharacterReference(shot) ? "identityReference" : "sceneReference"] = referenceImages.First();
                    var parameters = JsonSerializer.SerializeToDocument(new { positive = keyframePrompt, negative = keyframeNegative, inputSlots, referenceRequired = referenceImages.Count > 0, referenceProfile = useIpAdapter || HasCharacterReference(shot) ? "character" : "scene", identityControlMode = useIpAdapter ? "ipadapter-face-plus" : referenceImages.Count > 0 ? "reference-img2img" : null, identityControlStrength = useIpAdapter ? .95 : (double?)null, seed = shot.LongOrNull("seed") is { } seed ? seed + candidate : Random.Shared.NextInt64(1, 900000000), workflowVersion = routeFile, width = routeWidth, height = routeHeight, candidateIndex = candidate + 1 }).RootElement.Clone();
                    var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = shot.LongOrNull("projectId"), EpisodeId = input.EpisodeId, ShotId = shot.Long("id"), ProductionRunId = runId, TaskType = "Keyframe", WorkflowId = routeWorkflow.Long("id"), Priority = candidate == 0 ? 10 : 0, MaxRetries = 2, Stage = "Keyframe", RequestId = request.HttpContext.TraceIdentifier, IdempotencyKey = $"{requestKey}:shot:{shot.Long("id")}:candidate:{candidate + 1}", Parameters = parameters }, ct);
                    taskIds.Add(taskId); queue.Enqueue(taskId);
                }
            }
            return Results.Accepted("/api/production/status", new { runId, mode, taskIds, totalShots = shots.Count, candidateCount });
        });
        app.MapGet("/api/production/status", async (long episodeId, StudioRepository repo, GenerationQueue queue, AssetPathPolicy paths, CancellationToken ct) =>
        {
            var shots = await repo.ShotsAsync(episodeId, ct);
            var publicShots = shots.Select(shot => new
            {
                id = shot.Long("id"),
                shotNumber = shot.Int("shotNumber"),
                title = shot.Text("title"),
                status = shot.Text("status"),
                qualityScore = shot["qualityScore"],
                prompt = shot.Text("prompt"),
                promptLocked = shot.Bool("promptLocked"),
                promptVersion = shot.Int("promptVersion", 1),
                cameraType = shot.Text("cameraType"),
                durationSeconds = shot["durationSeconds"],
                inputImageAvailable = paths.IsAllowedExistingFile(shot.Text("inputImagePath")),
                selectedKeyframeAvailable = paths.IsAllowedExistingFile(shot.Text("selectedKeyframePath")),
                videoAvailable = paths.IsAllowedExistingFile(shot.Text("videoPath")),
                finalVideoAvailable = paths.IsAllowedExistingFile(shot.Text("finalVideoPath"))
            });
            return Results.Ok(new { run = (await repo.ProductionRunAsync(episodeId, ct)).FirstOrDefault(), shots = publicShots, queue = queue.Status });
        });
        app.MapPost("/api/production/pause", (GenerationQueue queue) => { queue.Pause(); return Results.Ok(new { paused = true }); });
        app.MapPost("/api/production/resume", (GenerationQueue queue) => { queue.Resume(); return Results.Ok(new { paused = false }); });
        app.MapPost("/api/production/cancel", async (long episodeId, StudioRepository repo, GenerationQueue queue, CancellationToken ct) => { await queue.CancelEpisodeAsync(episodeId, ct); return Results.Ok(new { cancelled = true }); });

        app.MapGet("/api/audio/voices", async (LocalTtsService tts, CancellationToken ct) => Results.Ok(await tts.VoiceCatalogAsync(ct)));
        app.MapPost("/api/audio/preflight", async (TtsInput input, LocalTtsService tts, CancellationToken ct) => Results.Ok(await tts.PreflightAsync(input.VoiceId, ct)));
        app.MapPost("/api/audio/tts", async (TtsInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, LocalTtsService tts, CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(input.Text)) return Results.BadRequest(new { error = "对白或旁白文本不能为空" });
            var validation = tts.ValidateInput(input);
            if (validation is not null) return Results.UnprocessableEntity(new { error = validation });
            if (input.ProjectId is not > 0 || (await repo.ProjectAsync(input.ProjectId.Value, ct)).Count == 0)
                return Results.BadRequest(new { error = "请为配音选择有效的保存项目" });
            input.EngineVersion = tts.EngineIdentity(input.VoiceId);
            var key = RequestIdempotencyKey(request, $"tts:{StableKey(input.Text, input.VoiceId, input.Speed.ToString(), input.Pitch.ToString(), input.Instruction, tts.EngineIdentity(input.VoiceId), input.ProjectId.ToString(), input.EpisodeId.ToString(), input.ShotId.ToString())}");
            var existing = await repo.TaskByIdempotencyKeyAsync(key, ct);
            var preflight = await tts.PreflightAsync(input.VoiceId, ct);
            if (!preflight.Passed)
                return Results.UnprocessableEntity(new { error = "中文 TTS 预检未通过，未创建音频任务", preflight });
            var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = input.ProjectId, EpisodeId = input.EpisodeId, ShotId = input.ShotId, TaskType = "Audio", ResourceClass = Qwen3TtsService.ResourceClass(input.VoiceId), Stage = "TTS", MaxRetries = 0, RequestId = request.HttpContext.TraceIdentifier, IdempotencyKey = key, Parameters = JsonSerializer.SerializeToDocument(input).RootElement.Clone() }, ct);
            if (existing is null || existing.Text("status") == "Pending") queue.Enqueue(taskId);
            return Results.Accepted($"/api/tasks/{taskId}", new { taskId, status = existing?.Text("status") ?? "Pending", idempotent = existing is not null });
        });
        app.MapPost("/api/episodes/{episodeId:long}/subtitles", async (long episodeId, SubtitleGenerateInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, CancellationToken ct) =>
        {
            var key = RequestIdempotencyKey(request, $"subtitles:{episodeId}:{StableKey(input.OutputName ?? "default")}");
            var existing = await repo.TaskByIdempotencyKeyAsync(key, ct);
            if (existing is not null) return Results.Accepted($"/api/tasks/{existing.Long("id")}", new { taskId = existing.Long("id"), status = existing.Text("status") ?? "Pending", idempotent = true });
            var taskId = await repo.CreateTaskAsync(new TaskInput { EpisodeId = episodeId, TaskType = "Subtitles", ResourceClass = "CPU", Stage = "Subtitle", MaxRetries = 1, RequestId = request.HttpContext.TraceIdentifier, IdempotencyKey = key, Parameters = JsonSerializer.SerializeToDocument(new { episodeId, outputName = input.OutputName }).RootElement.Clone() }, ct);
            queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId });
        });
        app.MapGet("/api/episodes/{episodeId:long}/subtitles", async (long episodeId, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.SubtitlesAsync(episodeId, ct)));

        app.MapGet("/api/sound-effects", async (string? category, StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.SoundEffectsAsync(category, ct)));
        app.MapPost("/api/sound-effects", async (HttpRequest request, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => await UploadLibraryFileAsync(request, repo, paths, false, ct));
        app.MapGet("/api/bgm", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.BgmTracksAsync(ct)));
        app.MapPost("/api/bgm", async (HttpRequest request, StudioRepository repo, AssetPathPolicy paths, CancellationToken ct) => await UploadLibraryFileAsync(request, repo, paths, true, ct));
        app.MapPost("/api/episodes/{episodeId:long}/bgm/{bgmId:long}", async (long episodeId, long bgmId, BgmInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.BindEpisodeBgmAsync(episodeId, bgmId, Math.Clamp(input.Volume, 0, 1), ct) }));
        app.MapGet("/api/project-templates", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ProjectTemplatesAsync(ct)));
        app.MapPost("/api/project-templates", async (ProjectTemplateInput input, StudioRepository repo, CancellationToken ct) => Results.Ok(new { id = await repo.CreateProjectTemplateAsync(input, ct) }));
        app.MapPost("/api/projects/{projectId:long}/apply-template/{templateId:long}", async (long projectId, long templateId, StudioRepository repo, CancellationToken ct) => Results.Ok(new { updated = await repo.ApplyProjectTemplateAsync(projectId, templateId, ct) }));
        app.MapGet("/api/presets", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.PresetsAsync(ct)));

        app.MapPost("/api/episode/render", (EpisodeRenderInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, FfmpegService ffmpeg, AssetPathPolicy paths, CancellationToken ct)
            => QueueEpisodeRenderWithQualityGateAsync(input, request, repo, queue, ffmpeg, paths, ct));

        // The previous ungated implementation is retained below as source history
        // only; it is excluded from the build so no caller can bypass the gate.
#if false
        app.MapPost("/api/episode/render-legacy", async (EpisodeRenderInput input, HttpRequest request, StudioRepository repo, GenerationQueue queue, FfmpegService ffmpeg, CancellationToken ct) =>
        {
            return Results.StatusCode(StatusCodes.Status410Gone);
            var episode = (await repo.EpisodeAsync(input.EpisodeId, ct)).FirstOrDefault(); if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
            if (episode.Bool("qaLocked")) return Results.Conflict(new { error = "Episode 已锁定，不能直接重新合成；请先解锁并重新 QA" });
            if (await repo.HasActiveTaskForEpisodeAsync(input.EpisodeId, "EpisodeRender", ct)) return Results.Conflict(new { error = "本集已有正式成片任务正在排队或合成，请先等待当前任务完成" });
            var shots = (await repo.ShotsAsync(input.EpisodeId, ct)).OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))).ToList();
            if (shots.Count == 0) return Results.BadRequest(new { error = "本集还没有镜头，无法生成整集成片" });
            var files = new List<string>();
            var sourceSnapshot = new List<object>();
            var missingShots = new List<object>();
            foreach (var shot in shots)
            {
                var path = ResolveShotVideoPath(shot, paths);
                var probe = string.IsNullOrWhiteSpace(path) ? null : await ffmpeg.ProbeAsync(path, ct);
                var ready = probe is { Width: > 0, Height: > 0 };
                sourceSnapshot.Add(new { shotId = shot.Long("id"), shotNumber = shot.Int("shotNumber"), title = shot.Text("title") ?? $"镜头 {shot.Int("shotNumber")}", path, durationSeconds = shot.Decimal("durationSeconds", 5), ready });
                if (ready && path is not null) files.Add(path);
                else missingShots.Add(new { shotId = shot.Long("id"), shotNumber = shot.Int("shotNumber"), title = shot.Text("title") ?? $"镜头 {shot.Int("shotNumber")}", status = shot.Text("status") ?? "Draft" });
            }
            if (missingShots.Count > 0) return Results.BadRequest(new { error = $"还有 {missingShots.Count} 个镜头没有可播放的正式视频，完成后才能生成整集成片", missingShots });
            var shotStarts = new Dictionary<long, double>();
            var cursor = 0d;
            foreach (var shot in shots)
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
            var renderVersion = (await repo.EpisodeRenderHistoryAsync(input.EpisodeId, ct)).Count + 1;
            var outputName = BuildEpisodeOutputName(input.OutputName, episode.Text("name") ?? "Episode", episode.Int("episodeNumber", 1), renderVersion);
            var parameters = JsonSerializer.SerializeToDocument(new { files, sourceSnapshot, renderVersion, outputName, targetWidth = episode.Int("outputWidth", 1920), targetHeight = episode.Int("outputHeight", 1080), targetFps = episode.Int("outputFps", 30), subtitlePath, audioTracks }).RootElement.Clone();
            var key = RequestIdempotencyKey(request, $"episode-render:{input.EpisodeId}:v{renderVersion}");
            var existing = await repo.TaskByIdempotencyKeyAsync(key, ct);
            if (existing is not null) return Results.Accepted($"/api/tasks/{existing.Long("id")}", new { taskId = existing.Long("id"), version = renderVersion, files = files.Count, status = existing.Text("status") ?? "Pending", idempotent = true });
            var taskId = await repo.CreateTaskAsync(new TaskInput { ProjectId = episode.LongOrNull("projectId"), EpisodeId = input.EpisodeId, TaskType = "EpisodeRender", ResourceClass = "CPU", Stage = "Episode", MaxRetries = 1, RequestId = request.HttpContext.TraceIdentifier, IdempotencyKey = key, Parameters = parameters }, ct);
            queue.Enqueue(taskId); return Results.Accepted($"/api/tasks/{taskId}", new { taskId, version = renderVersion, files = files.Count, status = "Pending" });
        });

 #endif
        app.MapGet("/api/system/settings/llm", async (StudioRepository repo, CancellationToken ct) => Results.Ok(new { provider = await repo.GetSettingAsync("llm.provider", ct) ?? "OpenAICompatible", baseUrl = await repo.GetSettingAsync("llm.base_url", ct), model = await repo.GetSettingAsync("llm.model", ct), temperature = await repo.GetSettingAsync("llm.temperature", ct) ?? "0.2", maxTokens = await repo.GetSettingAsync("llm.max_tokens", ct) ?? "3000", apiKeyConfigured = !string.IsNullOrWhiteSpace(await repo.GetSettingAsync("llm.api_key", ct)) }));
        app.MapPut("/api/system/settings/llm", async (LlmSettingsInput input, StudioRepository repo, LlmEndpointPolicy endpointPolicy, CancellationToken ct) =>
        {
            if (input.ApiKey?.Length > 512 || input.Model?.Length > 256) return Results.BadRequest(new { error = "LLM 密钥或模型名称超过安全长度限制" });
            var provider = string.IsNullOrWhiteSpace(input.Provider) ? "OpenAICompatible" : input.Provider.Trim();
            if (!string.IsNullOrWhiteSpace(input.BaseUrl))
            {
                var validation = await endpointPolicy.ValidateAsync(provider, input.BaseUrl, ct);
                if (!validation.Allowed || validation.BaseUri is null) return Results.BadRequest(new { error = validation.Error ?? "LLM 出站地址未通过安全策略", host = validation.Host });
                input.BaseUrl = validation.BaseUri.ToString().TrimEnd('/');
            }
            if (input.ApiKey is not null && input.ApiKey.Any(char.IsWhiteSpace)) return Results.BadRequest(new { error = "LLM API Key 不能包含空白字符" });
            await repo.SetSettingAsync("llm.provider", provider, "llm", false, ct); await repo.SetSettingAsync("llm.base_url", input.BaseUrl, "llm", false, ct); await repo.SetSettingAsync("llm.model", input.Model?.Trim(), "llm", false, ct); await repo.SetSettingAsync("llm.temperature", Math.Clamp(input.Temperature, 0, 2).ToString(System.Globalization.CultureInfo.InvariantCulture), "llm", false, ct); await repo.SetSettingAsync("llm.max_tokens", Math.Clamp(input.MaxTokens, 256, 16000).ToString(), "llm", false, ct);
            if (input.ApiKey is not null) await repo.SetSettingAsync("llm.api_key", input.ApiKey, "llm", true, ct);
            return Results.Ok(new { saved = true, apiKeyConfigured = !string.IsNullOrWhiteSpace(input.ApiKey) });
        });
        app.MapGet("/api/system/settings/audio", async (StudioRepository repo, LocalTtsService tts, CancellationToken ct) => Results.Ok(new { ttsAvailable = tts.IsAvailable, settings = await repo.GetSettingsAsync("audio", ct) }));
        app.MapGet("/api/production/recommendations", async (StudioRepository repo, CancellationToken ct) => Results.Ok(await repo.ParameterRecommendationsAsync(ct)));
    }

    private static async Task<IResult> UploadLibraryFileAsync(HttpRequest request, StudioRepository repo, AssetPathPolicy paths, bool bgm, CancellationToken ct)
    {
        if (!request.HasFormContentType) return Results.BadRequest(new { error = "请使用 multipart/form-data 上传音频" });
        var form = await request.ReadFormAsync(ct); var file = form.Files.GetFile("file"); if (file is null || file.Length == 0) return Results.BadRequest(new { error = "音频文件不能为空" });
        try
        {
            var upload = await paths.StoreUploadAsync(file, bgm ? "BGM" : "SoundEffects", UploadKind.Audio, 300L * 1024 * 1024, ct);
            var name = Path.GetFileNameWithoutExtension(file.FileName);
            if (bgm)
            {
                var id = await repo.AddBgmAsync(name, upload.FullPath, upload.Sha256, null, decimal.TryParse(form["volume"], out var volume) ? volume : .18m, ct);
                return Results.Ok(new { id, assetPath = upload.RelativePath, mediaUrl = $"/api/media?assetPath={Uri.EscapeDataString(upload.RelativePath)}" });
            }
            var effect = await repo.AddSoundEffectAsync(name, form["category"].ToString() ?? "environment", upload.FullPath, upload.Sha256, null, ct);
            return Results.Ok(new { id = effect, assetPath = upload.RelativePath, mediaUrl = $"/api/media?assetPath={Uri.EscapeDataString(upload.RelativePath)}" });
        }
        catch (AssetValidationException ex) { return Results.BadRequest(new { error = ex.Message }); }
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

    private static async Task<IResult> QueueEpisodeRenderWithQualityGateAsync(
        EpisodeRenderInput input,
        HttpRequest request,
        StudioRepository repo,
        GenerationQueue queue,
        FfmpegService ffmpeg,
        AssetPathPolicy paths,
        CancellationToken ct)
    {
        var episode = (await repo.EpisodeAsync(input.EpisodeId, ct)).FirstOrDefault();
        if (episode is null) return Results.NotFound(new { error = "Episode 不存在" });
        var approvedAndLocked = string.Equals(episode.Text("qaStatus"), "Approved", StringComparison.OrdinalIgnoreCase) && episode.Bool("qaLocked");
        if (!input.Preview && episode.Bool("qaLocked") && !approvedAndLocked)
            return Results.Conflict(new { error = "Episode 已锁定但尚未 Approved，请先解锁并重新 QA" });
        if (await repo.HasActiveTaskForEpisodeAsync(input.EpisodeId, "EpisodeRender", ct))
            return Results.Conflict(new { error = input.Preview ? "本集已有渲染任务正在排队或合成，请先等待当前任务完成" : "本集已有正式成片任务正在排队或合成，请先等待当前任务完成" });

        var shots = (await repo.ShotsAsync(input.EpisodeId, ct)).OrderBy(x => x.Int("sortOrder", x.Int("shotNumber"))).ToList();
        if (shots.Count == 0) return Results.BadRequest(new { error = "本集还没有镜头，无法生成成片" });
        var qualityGate = await EpisodeQualityGateEvaluator.EvaluateAsync(episode, shots, repo, ffmpeg, paths, ct);
        if (!input.Preview && !qualityGate.FormalReady)
            return Results.UnprocessableEntity(new
            {
                error = "正式成片已被质量门禁阻断；请先完成镜头 QA、Episode Approved 和正式增强视频",
                previewAllowed = qualityGate.PreviewReady,
                qualityGate
            });
        if (input.Preview && !qualityGate.PreviewReady)
            return Results.BadRequest(new { error = "没有可播放的镜头视频，无法生成审核预览", qualityGate });

        var shotById = shots.ToDictionary(x => x.Long("id"));
        var files = new List<string>();
        var sourceSnapshot = new List<object>();
        var missingShots = new List<object>();
        foreach (var source in qualityGate.Sources)
        {
            var path = input.Preview ? source.SelectedPath : source.FinalVideoPath;
            var ready = input.Preview ? source.PreviewReady : source.FormalReady;
            var duration = shotById.TryGetValue(source.ShotId, out var shot) ? shot.Decimal("durationSeconds", 5) : 5m;
            sourceSnapshot.Add(new
            {
                source.ShotId,
                shotNumber = source.ShotNumber,
                title = source.Title,
                path,
                sourceKind = input.Preview ? "preview" : "formal",
                qaStatus = source.QaStatus,
                durationSeconds = duration,
                ready
            });
            if (ready && path is not null) files.Add(path);
            else missingShots.Add(new { source.ShotId, shotNumber = source.ShotNumber, title = source.Title, qaStatus = source.QaStatus, reason = source.BlockedReason });
        }
        if (missingShots.Count > 0)
            return Results.BadRequest(new { error = $"还有 {missingShots.Count} 个镜头没有满足当前渲染模式的可用视频", missingShots, qualityGate });

        var shotStarts = new Dictionary<long, double>();
        var cursor = 0d;
        foreach (var shot in shots)
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
            var path = audio.Text("path");
            if (!paths.TryResolveExisting(path, out var fullPath, out _)) continue;
            var start = audio.LongOrNull("shotId") is { } shotId && shotStarts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
            audioTracks.Add(new { path = fullPath, volume = voiceVolume, startSeconds = start });
        }
        foreach (var effect in await repo.EpisodeSoundEffectsAsync(input.EpisodeId, ct))
        {
            var path = effect.Text("path");
            if (!paths.TryResolveExisting(path, out var fullPath, out _)) continue;
            var start = effect.LongOrNull("shotId") is { } shotId && shotStarts.TryGetValue(shotId, out var shotStart) ? shotStart : 0;
            audioTracks.Add(new { path = fullPath, volume = Math.Clamp((double)effect.Decimal("volume", .6m) * sfxVolume, .05, 2), startSeconds = start + (double)effect.Decimal("startSeconds", 0) });
        }
        foreach (var bgm in await repo.EpisodeBgmAsync(input.EpisodeId, ct))
        {
            var path = bgm.Text("path");
            if (!paths.TryResolveExisting(path, out var fullPath, out _)) continue;
            audioTracks.Add(new { path = fullPath, volume = Math.Clamp((double)bgm.Decimal("volume", .18m) * bgmVolume, .05, 2), startSeconds = 0d });
        }
        foreach (var audioPath in input.AudioPaths)
        {
            if (!paths.TryResolveExisting(audioPath, out var fullPath, out _))
                return Results.UnprocessableEntity(new { error = "额外音频必须位于受控数据目录" });
            audioTracks.Add(new { path = fullPath, volume = 1d, startSeconds = 0d });
        }

        var subtitlePath = input.IncludeSubtitles ? episode.Text("subtitlePath") : null;
        if (!string.IsNullOrWhiteSpace(subtitlePath) && !paths.TryResolveExisting(subtitlePath, out subtitlePath, out _))
            return Results.UnprocessableEntity(new { error = "字幕文件必须位于受控数据目录" });
        var renderVersion = (await repo.EpisodeRenderHistoryAsync(input.EpisodeId, ct)).Count + 1;
        var outputName = BuildEpisodeOutputName(input.OutputName, episode.Text("name") ?? "Episode", episode.Int("episodeNumber", 1), renderVersion);
        if (input.Preview) outputName = BuildEpisodePreviewOutputName(outputName);
        var parameters = JsonSerializer.SerializeToDocument(new
        {
            files,
            sourceSnapshot,
            renderVersion,
            outputName,
            preview = input.Preview,
            renderMode = input.Preview ? "Preview" : "Formal",
            qualityGate = new { qualityGate.AllShotsPassed, qualityGate.EpisodeApproved, qualityGate.QaLocked, qualityGate.OpenBlockingIssueCount },
            targetWidth = episode.Int("outputWidth", 1920),
            targetHeight = episode.Int("outputHeight", 1080),
            targetFps = episode.Int("outputFps", 30),
            subtitlePath,
            audioTracks
        }).RootElement.Clone();
        var key = RequestIdempotencyKey(request, $"episode-{(input.Preview ? "preview" : "render")}:{input.EpisodeId}:v{renderVersion}");
        var existing = await repo.TaskByIdempotencyKeyAsync(key, ct);
        if (existing is not null)
            return Results.Accepted($"/api/tasks/{existing.Long("id")}", new { taskId = existing.Long("id"), version = renderVersion, files = files.Count, preview = input.Preview, status = existing.Text("status") ?? "Pending", idempotent = true });
        var taskId = await repo.CreateTaskAsync(new TaskInput
        {
            ProjectId = episode.LongOrNull("projectId"),
            EpisodeId = input.EpisodeId,
            TaskType = "EpisodeRender",
            ResourceClass = "CPU",
            Stage = "Episode",
            MaxRetries = 1,
            RequestId = request.HttpContext.TraceIdentifier,
            IdempotencyKey = key,
            Parameters = parameters
        }, ct);
        queue.Enqueue(taskId);
        return Results.Accepted($"/api/tasks/{taskId}", new { taskId, version = renderVersion, files = files.Count, preview = input.Preview, status = "Pending" });
    }

    private static object ToPublicCandidate(IReadOnlyDictionary<string, object?> candidate, AssetPathPolicy paths)
    {
        var available = paths.TryResolveExisting(candidate.Text("path"), out _, out var assetPath);
        return new
        {
            id = candidate.Long("id"),
            shotId = candidate.LongOrNull("shotId"),
            taskId = candidate.LongOrNull("taskId"),
            candidateIndex = candidate.Int("candidateIndex"),
            seed = candidate.LongOrNull("seed"),
            qcStatus = candidate.Text("qcStatus"),
            qualityScore = candidate["qualityScore"],
            createdAt = candidate["createdAt"],
            available,
            assetPath = available ? assetPath : null,
            mediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(assetPath)}" : null
        };
    }

    private static object ToPublicTake(IReadOnlyDictionary<string, object?> take, AssetPathPolicy paths)
    {
        var storedPath = take.Text("path") ?? take.Text("assetRelativePath");
        var available = paths.TryResolveExisting(storedPath, out _, out var relativePath);
        return new
        {
            id = take.Long("id"),
            taskId = take.LongOrNull("taskId"),
            shotId = take.LongOrNull("shotId"),
            taskType = take.Text("taskType"),
            status = take.Text("status"),
            resultType = take.Text("resultType"),
            workflowId = take.LongOrNull("workflowId"),
            candidateIndex = take.Int("candidateIndex") is var candidate && candidate > 0 ? (int?)candidate : null,
            isSelected = take.Bool("isSelected"),
            qualityScore = take["qualityScore"],
            userRating = take.Int("userRating") is var rating && rating != 0 ? (int?)rating : null,
            promptVersion = take.Int("promptVersion") is var promptVersion && promptVersion > 0 ? (int?)promptVersion : null,
            seed = take.LongOrNull("seed"),
            assetName = take.Text("assetName"),
            mimeType = take.Text("mimeType"),
            width = take.Int("width"),
            height = take.Int("height"),
            durationSeconds = take["durationSeconds"],
            fps = take["fps"],
            available,
            assetPath = available ? relativePath : null,
            mediaUrl = available ? $"/api/media?assetPath={Uri.EscapeDataString(relativePath)}" : null,
            createdAt = take["createdAt"],
            taskCreatedAt = take["taskCreatedAt"],
            taskStartedAt = take["taskStartedAt"],
            taskFinishedAt = take["taskFinishedAt"]
        };
    }

    private static string? ResolveShotVideoPath(IReadOnlyDictionary<string, object?> shot, AssetPathPolicy paths)
    {
        foreach (var path in new[] { shot.Text("finalVideoPath"), shot.Text("videoPath"), shot.Text("resultPath") })
            if (!string.IsNullOrWhiteSpace(path) && IsVideoPath(path) && paths.TryResolveExisting(path, out var fullPath, out _)) return fullPath;
        return null;
    }

    private static bool IsVideoPath(string path) => Path.GetExtension(path).ToLowerInvariant() is ".mp4" or ".mov" or ".webm" or ".mkv";

    private static string BuildEpisodeOutputName(string? requestedName, string episodeName, int episodeNumber, int version)
    {
        var raw = Path.GetFileName(string.IsNullOrWhiteSpace(requestedName) ? $"{episodeName}_{episodeNumber:000}_V{version:00}.mp4" : requestedName);
        var stem = Path.GetFileNameWithoutExtension(raw);
        var invalid = Path.GetInvalidFileNameChars();
        stem = string.Concat(stem.Select(character => invalid.Contains(character) ? '_' : character)).Trim();
        return $"{(string.IsNullOrWhiteSpace(stem) ? $"Episode_{episodeNumber:000}_V{version:00}" : stem)}.mp4";
    }

    private static string BuildEpisodePreviewOutputName(string formalName)
    {
        var fileName = Path.GetFileName(formalName);
        var stem = Path.GetFileNameWithoutExtension(fileName);
        if (stem.StartsWith("PREVIEW_", StringComparison.OrdinalIgnoreCase)) return fileName;
        // BuildEpisodeOutputName already embeds the render version. Do not add a
        // second Vxx suffix to preview files.
        return $"PREVIEW_{stem}.mp4";
    }

    private static bool HasCharacterReference(IReadOnlyDictionary<string, object?> shot)
    {
        try
        {
            using var json = shot.Json("characterIdsJson");
            return json.RootElement.ValueKind == JsonValueKind.Array && json.RootElement.EnumerateArray().Any(item => item.TryGetInt64(out var id) && id > 0);
        }
        catch { return false; }
    }

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

    private static string RequestIdempotencyKey(HttpRequest request, string fallback)
    {
        var header = request.Headers["Idempotency-Key"].FirstOrDefault();
        return string.IsNullOrWhiteSpace(header) ? fallback : header.Trim();
    }

    private static string StableKey(params string?[] values)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", values.Select(x => x ?? ""))))).ToLowerInvariant()[..24];

    private static bool HasSpeech(IReadOnlyDictionary<string, object?> shot)
        => !string.IsNullOrWhiteSpace(shot.Text("dialogue")) || !string.IsNullOrWhiteSpace(shot.Text("narration"));

    private static IEnumerable<string> ParseSpeakers(string? dialogue)
    {
        if (string.IsNullOrWhiteSpace(dialogue)) yield break;
        foreach (var line in dialogue.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var separator = line.IndexOfAny([':', '：']);
            if (separator > 0 && !string.IsNullOrWhiteSpace(line[..separator])) yield return line[..separator].Trim();
        }
    }

    private static JsonObject BuildVideoSlots(string firstFrame, bool withGuide)
    {
        var slots = new JsonObject { ["firstFrame"] = firstFrame };
        if (withGuide) slots["guideFrame"] = firstFrame;
        return slots;
    }
}
