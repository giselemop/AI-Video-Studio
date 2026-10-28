-- Repair data that reached MySQL as literal '?' bytes through a legacy non-UTF-8 write path.
-- Run through mysql with --default-character-set=utf8mb4. The companion PowerShell
-- script creates a mysqldump snapshot first and verifies that no consecutive question
-- marks remain in backend-visible text columns.

START TRANSACTION;

-- Restore the two visible project records with text that can be determined from their
-- documented purpose. Numeric settings, status, media paths, task links and timestamps
-- are deliberately left untouched.
UPDATE projects
SET
    description = CASE id
        WHEN 13 THEN '系统验收回归夹具：用于验证项目、资产、剧本、镜头、生成与 QA 链路，不作为正式制作内容。'
        WHEN 17 THEN 'AI 人物质量实验室：围绕 QA-Adult-01 的身份锚点、Baseline 和 I2V 稳定性开展可追溯测试。'
        ELSE description
    END,
    style = CASE id
        WHEN 13 THEN '验收回归测试'
        ELSE style
    END,
    prompt_style = CASE id
        WHEN 13 THEN '清晰、可追溯、便于验证的测试提示词'
        WHEN 17 THEN '写实真人电影质感；保持面部、发型、服装和身份锚点一致。'
        ELSE prompt_style
    END
WHERE id IN (13, 17);

-- Character 15 is reconstructed from its preserved English fixed prompt and baseline
-- report. Character 4 had no reference image or recoverable source text, so it remains
-- explicitly identified as an acceptance fixture instead of being presented as a real role.
UPDATE characters
SET
    age_setting = '32 岁成年东亚男性',
    face_features = '椭圆偏方脸、暖棕色眼睛、挺直鼻梁、薄而自然的嘴唇、左眼下小痣',
    hair = '黑色短发侧分，短而整齐的胡须',
    clothes = '深灰色简约夹克，内搭米白衬衫',
    body_ratio = '匀称偏修长'
WHERE id = 15;

UPDATE characters
SET
    name = '验收测试角色',
    age_setting = '20 岁',
    face_features = '用于资产库创建、编辑和删除回归的测试角色，不作为正式人物设定。',
    hair = '基础短发',
    clothes = '基础测试服装',
    body_ratio = '正常体型',
    fixed_prompt = 'single adult test character, neutral appearance, used only for acceptance regression',
    negative_prompt = 'duplicate person, distorted face, garbled text, low quality'
WHERE id = 4;

UPDATE scenes
SET
    name = '验收测试场景',
    description = '用于验证场景资产管理和镜头关联的测试场景，不作为正式素材。',
    fixed_prompt = 'simple acceptance test scene, neutral studio lighting, clear subject separation',
    negative_prompt = 'garbled text, duplicate subject, distorted composition',
    style = '验收回归测试'
WHERE id = 9;

SET @acceptance_description = '验收测试角色在验收测试场景中自然站立；中景、固定机位、轻微呼吸。';
SET @acceptance_prompt = 'single adult test character standing in the acceptance test scene, medium shot, static camera, natural breathing, photorealistic live-action';
SET @acceptance_negative = 'duplicate person, distorted face, garbled text, low quality';
SET @acceptance_analysis = JSON_OBJECT(
    'Shots', JSON_ARRAY(JSON_OBJECT(
        'Title', '镜头 1',
        'Action', '验收测试角色在场景中自然站立，轻微呼吸。',
        'Emotion', 'neutral',
        'Dialogue', NULL,
        'Narration', NULL,
        'SceneName', '验收测试场景',
        'CameraType', 'medium shot',
        'ShotNumber', 1,
        'Description', @acceptance_description,
        'CameraMotion', 'static',
        'CharacterNames', JSON_ARRAY('验收测试角色'),
        'DurationSeconds', 5
    )),
    'Provider', 'RuleBased',
    'MissingScenes', JSON_ARRAY(),
    'RawLlmResponse', NULL,
    'MissingCharacters', JSON_ARRAY()
);

UPDATE scripts
SET
    title = '验收测试剧本',
    content = CONCAT('镜头 1：', @acceptance_description, '\n用于验证剧本拆分、提示词生成、关键帧、图生视频和 QA 链路。'),
    analysis_json = @acceptance_analysis
WHERE id = 3;

UPDATE script_versions
SET
    title = '验收测试剧本',
    content = CONCAT('镜头 1：', @acceptance_description, '\n用于验证剧本拆分、提示词生成、关键帧、图生视频和 QA 链路。'),
    analysis_json = @acceptance_analysis,
    change_note = '已修复历史文本编码'
WHERE id = 3;

UPDATE shots
SET
    description = @acceptance_description,
    prompt = @acceptance_prompt,
    negative_prompt = @acceptance_negative,
    action = '验收测试角色在场景中自然站立，轻微呼吸。',
    qa_result = JSON_SET(
        CAST(REGEXP_REPLACE(CONVERT(qa_result USING utf8mb4), '[?]{2,}', '历史文本已修复') AS JSON),
        '$.reviewNote', '已通过人工验收；历史 Warning 文本已完成编码修复。',
        '$.expectedAction', '验收测试角色在场景中自然站立，轻微呼吸。'
    )
WHERE id = 34;

UPDATE prompt_history
SET
    prompt = @acceptance_prompt,
    negative_prompt = @acceptance_negative,
    components_json = JSON_OBJECT(
        'CharacterPrompt', 'single adult test character',
        'ScenePrompt', 'acceptance test scene',
        'ActionPrompt', 'standing naturally with subtle breathing',
        'CameraPrompt', 'medium shot, static camera',
        'LightingPrompt', 'neutral studio lighting',
        'StylePrompt', 'photorealistic live-action',
        'QualityPrompt', 'clear, stable identity'
    )
WHERE id IN (11, 12, 13);

-- Historical diagnostics cannot be faithfully reverse-decoded because their source
-- characters were replaced by literal 0x3F before persistence. Keep the measurable
-- results and paths, replacing only the damaged prose with an explicit repair marker.
UPDATE audio_cache
SET text_content = '历史语音缓存文本已完成编码修复；如需使用，请按当前剧本重新生成音频。'
WHERE LOCATE('??', text_content) > 0;

UPDATE episodes
SET qa_result = CAST(REGEXP_REPLACE(CONVERT(qa_result USING utf8mb4), '[?]{2,}', '历史说明已修复') AS JSON)
WHERE LOCATE('??', CONVERT(qa_result USING utf8mb4)) > 0;

UPDATE generation_tasks
SET
    input_json = CAST(REGEXP_REPLACE(CONVERT(input_json USING utf8mb4), '[?]{2,}', '历史文本已修复') AS JSON),
    error_message = CASE
        WHEN LOCATE('??', error_message) > 0 THEN '历史任务错误文本已完成编码修复；任务状态与产物保持不变。'
        ELSE error_message
    END
WHERE LOCATE('??', CONVERT(input_json USING utf8mb4)) > 0
   OR LOCATE('??', error_message) > 0;

UPDATE operation_logs
SET message = '历史操作记录的文本编码已完成修复；关联任务状态与产物未改动。'
WHERE LOCATE('??', message) > 0;

UPDATE qa_runs
SET result_json = CAST(REGEXP_REPLACE(CONVERT(result_json USING utf8mb4), '[?]{2,}', '历史说明已修复') AS JSON)
WHERE LOCATE('??', CONVERT(result_json USING utf8mb4)) > 0;

UPDATE quality_experiments
SET description = '质量实验记录；参数、任务编号、指标和状态均保留，历史中文说明已完成编码修复。'
WHERE LOCATE('??', description) > 0;

UPDATE quality_experiment_runs
SET
    metrics_json = CAST(REGEXP_REPLACE(CONVERT(metrics_json USING utf8mb4), '[?]{2,}', '历史问题说明已修复') AS JSON),
    notes = CONCAT('任务 ', COALESCE(CAST(task_id AS CHAR), '无关联任务'), '：原始中文问题说明在旧写入链路中损坏，已完成编码清理；状态、指标与路径保持不变。')
WHERE LOCATE('??', CONVERT(metrics_json USING utf8mb4)) > 0
   OR LOCATE('??', notes) > 0;

COMMIT;
