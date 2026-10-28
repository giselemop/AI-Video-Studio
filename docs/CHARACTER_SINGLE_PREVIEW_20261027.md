# 林安单人动作试片（2026-10-27）

应用户“现在可以生成一段视频看看效果了吗”的新请求，完成一个独立人物参考图动画实验。本次明确选用旧版已批准参考36，不恢复原双人剧情、不采用待审修复候选、不撤销原拒绝记录。

- [本次新视频与来源](http://127.0.0.1:18080/character-single-preview.html)
- 项目52，真实业务任务1550；Comfy执行 `804dca4d-cedf-451e-a24d-443c8156c2ac`。
- 人物19林安，库版本3（v2、历史二图包），正面参考36当前审核Approved。库版本与最终视频仍NeedReview，发布Blocked。
- 实际H3首帧SHA256：`faba35ff94c4a080aea1ca5bb663e611697a2b31cad7cc9a2c6e0ec9d6657fef`。
- 最终媒体：`Artifacts/project-52/video/task-1550/v0001/v0001_task_1550_task_1550_attempt_1_df34df4d_00001__f1d1a4349166.mp4`；SHA256：`f1d1a4349166b771cc22c7f1bee0ba8402a894c4075090469520202fba4fc016`。
- 原生864×480、24FPS、124帧、20步，实测时长5.167000秒；本次生成耗时559.873秒，服务采样显存峰值9870MiB。无升分辨率、换模型或缩减契约。

## 检查结论

技术Passed：14项实际媒体与来源检查，包括任务/Comfy历史、执行参数、实际首帧与源参考一致、输出等于原生Comfy文件、FFprobe、全片解码、哈希、Range206、单任务边界和原剧情检查点保全。浏览器已完整播放至结束，无媒体或控制台错误。

试片画面检查 **Failed**：已检查12个实际时点及浏览器完整播放：同一女性的脸型、黑色短发与米白针织上衣未见明显换人或换衣，可见眨眼、轻微呼吸与头部逐渐回正，嘴部基本闭合。预期向画面左转头再返回的方向动作不明显，精确动作命中Failed；外观粗检Passed，不生成身份分数。近景不评价画外手脚，皮肤细节、年龄相似度与自然度保留人工复核。

本次为助手PreviewInspection，人工内容保持NeedReview；不生成身份分数，不代表正式人物包或双人剧情验收通过。音频策略为H3原生音频，预览页默认静音；原生音频内容未验收。

## 文件、原流程与恢复

证据：`C:\install\AI\Data\CharacterSinglePreview20261027`。主要文件：run.json、resolved.json、preflight.json、submission.json、task-trace.json、comfy-history.json、ffprobe.json、media-checks.json、contact-sheet.jpg、frames、visual-inspection.json、browser-playback.json与截图。

原`CharacterScene20261027/run.json`及generationHold保持逐字节不变；原正式剧情resolve仍以422拒绝失效来源。新九图人物与双人剧情继续待审。本轮只有一个新视频任务，没有重生图片、创建新人物版本或审核批准，没有下载模型、云调用或公开发布。

控制器：`tools/character_single_preview.py`；模板：`tools/character_single_preview.template.html`。运行submit会保留已登记任务1550，不会重复提交；完成后只核验当前输出。分支main/d6ec38d，未提交，既有未完成工作保留，无数据库结构迁移。
