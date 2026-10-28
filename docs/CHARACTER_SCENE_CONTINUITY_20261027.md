# 阅读室场景连续性增量实施与验收（2026-10-27）

本阶段已完成本地代码、场景版本界面、真实关键帧及证据页交付。代码与文件技术检查 **Passed**；四张新关键帧的试片检查为一张 **Passed**、三张 **Failed**；人工内容 **NeedReview**，本轮视频与合成 **Blocked**。用户明确回复“保持待审”，后台已保存生成暂停检查点，不自动续跑。

- 工作台：[剧情选角与试片](http://127.0.0.1:18080/#character-story)，选择“阅读室找书_场景连续性_f890ac0a”。
- 新结果：[同一阅读室四张关键帧与失败说明](http://127.0.0.1:18080/character-scene-preview.html)。
- 上轮结果：[原四视频与预览](http://127.0.0.1:18080/character-story-preview.html)，仅保留作历史对照，不作为本轮新视频。
- 另一任务产物：[人物修复候选](http://127.0.0.1:18080/character-reference-repair.html)。该任务独立完成，候选尚待用户审核，本轮未重复生成或自动采用。

## 实际范围与不可变来源

保留 Vue / .NET / MySQL、既有人物库、Episode / Shot、业务队列和 H3 首帧路线。没有下载模型、调用云服务、训练人物 LoRA 或公开发布。

| 对象 | 实际记录 |
| --- | --- |
| 项目 / 集 | 51 / 36 |
| 项目选角 / 本集快照 | 27 / 28 |
| 固定演员 | 林安：人物19、造型版本4；周言：人物20、造型版本5 |
| 场景 / 初始场景版本 | 32 / 29 |
| 定向修复场景版本 | 38，另存；原29保留 |
| 原Shot计划 | 镜头253–256，计划30–33 |
| 仅失败项的新计划 | 39、40、41；已检查通过的计划32保留 |
| 构图基准 | 已有真实关键帧1514，1536×864，含原两个人物 |
| 构图文件SHA256 | `2b766ed70aecd4993ce0f18f7a36fc7a5a40230080e35aaac2d4065cec91cf1b` |

基准1514是明确引用的原输出，不是本轮新生成的空场景。场景版本冻结原请求、文件哈希、来源任务与检查、演员造型版本、画面站位、相机、场景说明及人物区域。旧版本SHA、旧预览与历史媒体均重新核验保留。

本机已经支持 `entity_versions` 的 `Scene` 类型，本轮无需新增迁移。原010/011已实际就绪。实施前核验的备份为 `C:\install\AI\VideoStudio\backup\20261027_134951`；SQL哈希保存在本轮检查点，不恢复或改写其他业务数据。

## 代码与界面

`CharacterSceneService` 复用既有Scene资产与不可变版本表；新增场景版本列表、捕获接口：

```text
GET  /api/character-story/scenes?projectId=51
POST /api/character-story/scenes/{sceneId}/capture
```

固定构图目前限定为同机位双人中景，人物、造型和左右站位须与基准一致。更换人物版本、机位或场景不能静默套用旧基准；原有未绑定固定场景的文字路线继续可读。`StoryShotInput.SceneVersionId` 显式选择场景版本，H3参数仅保留场景来源信息，实际首帧仍是已检查的剧情关键帧。

新增 `CharacterScenePanel.vue`：原图放大、区域叠加、版本查看、真实来源任务读取及区域校验。保存新版本前服务端再次核验真实PNG、1536×864、SHA256及试片检查。保存版本本身不批准内容、不提交GPU任务。已有场景锚点与所选输出不一致时提示另建场景，避免覆盖原锚点。

`CharacterStoryPanel.vue` 增加显式场景选择与演员版本审核状态。改变场景会标记分镜尚未冻结；切换历史计划恢复其原始场景绑定。含拒绝或失效素材的演员版本显示原因并禁用生成入口；已有镜头与任务仍可查看。切换项目清除旧任务、分镜和调用状态。

真实页面测试发现 Element Plus 数值控件在初次禁用后留下错误的 `aria-disabled` 状态。新场景表单改用响应式原生数值输入，重新验证可编辑状态、越界错误与保存禁用。

## 实际工作流及边界

`character_scene_klein4b_five_locked_api.json` 使用现有Klein权重和节点：两个人物各有独立身份、造型输入，第五槽为明确的场景构图。并非把服装槽当成第二个人物，也没有宣称H3支持Ref2VA。

生成的双人区域通过遮罩羽化合成回原场景；保存节点确实保存最终合成，而非仅在提示词中要求背景一致。补丁在通用宽高处理后恢复验证过的遮罩尺寸，避免所有区域被错误改成整幅1536×864。

首轮区域：左人物 `(300,50,420,814)`，右人物 `(820,8,430,856)`，羽化32。每张输出中，区域外 **617144像素（46.5%画幅）与原基准完全一致，RGB单通道最大差值0**。这是具体像素保持证据，不是身份分数，也不能证明区域内人物、方向、手或动作正确。

针对失败内容，另存 `character_scene_klein4b_five_masked_locked_api.json`：只在条件图中隔离旧头部姿态，保留原身体布局；最终背景仍取真实原图。修复区域扩大为左 `(270,32,480,832)`、右 `(770,0,500,864)`。这一路线已通过代码、节点与契约检查，**尚未真实生成验证**；不能宣称已解决方向或手部问题。

每个Shot的关键帧/视频修复预算跨计划版本累计，初次加最多两次定向修复。新建场景或计划不会重置预算，也不能借用另一Shot的失败任务作为修复来源。

## 四张真实输出

| 槽位 / 任务 | 技术 | 试片内容检查 | 实际观察与处理 |
| --- | --- | --- | --- |
| 寻找书架 / 1522 | Passed | Failed | 女方朝画面右看男方，未望向左外侧书架；男方手边有淡化残影。保留原图，未生成视频。 |
| 共同注意 / 1523 | Passed | Failed | 双方实际相向对视，未共同望向画面左书架。保留原图，未生成视频。 |
| 相互确认 / 1524 | Passed | Passed（PreviewInspection） | 左女右男相向、基本服装及四手体侧未见明显异常；身份细节、接缝与最终偏好仍待人工审核。 |
| 点头回应 / 1525 | Passed | Failed | 女方抬手，体侧仍见手部，疑似额外肢体；不符仅点头、双手下垂的起始状态。 |

四项均来自业务队列的真实ComfyUI执行；未用占位图或原视频充当新结果。场景整体静态连续性仍为 `false`。三项失败的修复计划已经另存，但没有创建任何修复图任务；本轮H3任务数、视频数和合成数均为0。

## 审核阻塞与用户指示

生成后发生新的真实素材审核：林安版本4及周言版本5均含被拒绝素材。当前审核状态与冻结版本文件分开记录，不撤销拒绝、不覆盖旧版、不回退到缺全身图的历史二图版本。

后续提交在来源校验阶段返回422，并明确提示拒绝参考。另一任务“修复人物生成双脸问题”的24个真实任务与候选不计入本轮；本轮只认检查点登记的1522–1525。其成果依旧待人工审核，不会自动更新本集演员。

用户回复“保持待审”已写入：

```text
C:\install\AI\Data\CharacterScene20261027\run.json
stage = AwaitingHumanReview
completed = false
generationHold.active = true
staticContinuityPassed = false
```

控制器在任何新图/视频请求前检查此指示，重启或误重跑也不会自动继续。继续需用户另行明确指示，并明确采用审核后的演员及相符的新构图版本；无需反复询问当前待审选择。

## 测试与证据

证据根目录：`C:\install\AI\Data\CharacterScene20261027`。

| 检查 | 结果 / 证据 |
| --- | --- |
| .NET构建 | Passed，原 `backend-build.log`；当前已部署服务支持新接口 |
| 场景后端自测 | 24项Passed，`backend-checks.json`；包括区域边界、固定演员、机位、五输入与遮罩补丁 |
| 首轮实际API回归 | 25项Passed，`api-checks.json`；在后续素材拒绝前执行，不当成当前素材可用证明 |
| 当前待审与交付回归 | 45项Passed，`delivery-checks.json`；包含实际422、原版本与历史媒体、4任务边界、没有新视频/任务/批准 |
| 前端状态与选择校验 | 5组Passed，`frontend-checks.tap`；旧版无场景兼容、新版本/站位/机位及区域保护 |
| 媒体和执行来源 | 71项Passed，`pilot-media-checks.json`；真实Comfy记录、执行图、输入/输出SHA、尺寸与保护背景像素 |
| 任务列表故障回归 | 5/100/500条排序与原SQL结果一致，`task-list-regression.json` |
| Web构建 | Passed，`web-build.log`；保留既有包体大小提示 |
| 真实浏览器 | 13项Passed，`browser-checks.json`；图像加载、放大、错误提示、旧计划、项目切换和无控制台错误 |
| 截图 | `screenshots\review-overview.png`、`review-first-pair.png`、`review-second-pair.png`、`scene-original-zoom.png`、`keyframe-1524-zoom.png` |

另修复实际故障：大场景快照使原任务列表查询触发MySQL1038排序内存不足。`Database.TasksAsync` 先按原规则查询有限ID，再分批读取完整任务行并在内存恢复原顺序，保留完整参数及API形状，不改数据库内存配置。实际5/100/500条接口及顺序对照Passed。

执行痕迹：`C:\install\AI\Data\CharacterStoryTrace\task_1522` 至 `task_1525`，包含submission、applied-workflow、requested-input和Comfy历史。新图文件路径与SHA完整收录在 `pilot-media-checks.json`，可从新结果页直接放大。

本轮无新视频，故本轮FFprobe视频参数、全片解码、H3首帧实际一致性、动态人物/动作连续性、音画及合成播放均 **Blocked（未执行）**；不能拿上一轮检查代替。若续做，保持已选择的864×480、24FPS、124帧、20步最短有效H3契约和后期配音策略；不截短契约或静默降级。

## 分支、修改和恢复

当前 `main`，提交 `d6ec38d076a8b0336d349c36df5c123f2c941ac8`，未新增Git提交或推送。共享工作区在接管前已有大量未提交修改；本轮未清理、重置、暂存或覆盖其他任务成果。

主要增量：`CharacterSceneService.cs`、`CharacterSceneSelfTest.cs`、`CharacterStoryService.cs` / Store / Endpoints、`ComfyUiClient.cs`、`Database.cs`、`Program.cs`、两个已登记场景工作流与契约、`CharacterScenePanel.vue`、`characterSceneModel.js`、`CharacterStoryPanel.vue`、前端测试、`tools/character_scene`及本报告。人物提示词统一和人物修复页由另一任务负责，保持原改动。

恢复以本轮 `run.json` 为入口。先读审核指示、真实队列和已登记任务，已成功图只校验，不重新提交。`python tools/character_scene/verify.py` 与 `check_delivery.py` 只核验，`hold_review.py` 可幂等保留暂停指示。`repair_round1.py` 当前禁止运行生成。

源码前快照为 `source-before`；服务初始快照为 `server-before`；本轮Web构建前完整快照为 `web-before`。共享后端文件可能包含其他任务的新改动，回退必须比对具体增量，不能整目录覆盖旧服务或执行Git重置。数据库与原媒体无需回退。本轮检查点及失败素材应保留，以便以后从明确的新版本继续。
