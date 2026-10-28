# 《窗边等候》环境远景切镜试片（2026-10-28）

## 实际产出与范围

用户希望看远景切镜或其他画面。本次以原15秒有声试片 #1565 为基础，在 **8.75–10.25秒** 插入无人窗边环境镜头，随后切回林安。原始成片、声音、关键帧、人物版本与先前双人待审状态均保留。林安全身参考仍有被拒绝内容，本次未使用这些素材，也未声称这是人物全身远景。

原画面的木窗与树景用于场景参考，但新画面窗格和房间布局并非完全相同，生成图也没有出现提示词中要求的小桌。场景是氛围示例，不能把它当作同一房间几何连续性已通过的证据；运动比较轻微。

## 真实任务与证据

| 步骤 | 任务/结果 |
|---|---|
| 场景参考 | 已保留原关键帧 #1554，SHA256 02692555a45b3cd9e22b270bc064a328e7369e1eb58c05b9b1cdf346fb914847 |
| 新远景关键帧 | #1566，Klein 现有工作流，1536×864，SHA256 34020925fa8e1abb71e38730fe93758cab3abd44001c121fd198416c4249e3ba；已查看实际图片，人物不存在，小桌缺失 |
| 环境视频 | #1567，现有 MiniMax H3 FL2VA 首帧实验工作流，864×480、24fps、124帧、20步；实际首帧哈希与 #1566 一致，Comfy 历史和原生输出匹配；SHA256 c3a6a9c1f22b3f90efbace0706a02734388ec9683f70db2a19ffc8c617374ffa |
| 画面剪辑 | #1568（前段）、#1569（远景）、#1570（后段）、#1571（拼接），均通过业务 CPU 队列，来源哈希受检 |
| 完整成片 | #1572，15秒、864×480、24fps、360帧，SHA256 e92400cf14ac53983d4a5d4dd91aa29fdc768d1fa70485acda5750327a194388 |
| 声音 | 从原片无损复制 AAC 音轨，源与新片的音频包 SHA256 同为 SHA256=573330bf4b0972938e24e687e39546912b8e45b0c667ba5aad25db3c2547c375；无新增配音或音乐 |
| 视频路线 | 无人环境镜头使用既有 ImageToVideo 实验入口，先检查真实关键帧再进 H3；未声称多人物身份绑定或正式剧情镜头审核通过 |

媒体经过 FFprobe、完整音视频解码及媒体接口 Range/206 检查。对切入前、切入后和两个切点的抽样画面与原片/环境源作像素差核对（这只是剪辑核对，不是人物身份分数）。原字幕区间 0.4–4.56、5.5–8.7、10.8–14.48 秒不与插入区间重叠；成片字幕来自原画面。剪辑为重新编码，像素并非逐字节相同。

浏览器实际播放到 15 秒结束、非静音、无控制台错误；9 秒处截图显示环境远景；原片播放器可加载。未把浏览器可播放等同于听感或内容最终通过。

- 观看与对照：http://127.0.0.1:18080/character-wide-cutaway.html
- 新成片：C:\install\AI\Data\Artifacts\project-54\video\task-1572\v0001\v0001_window_cutaway_15s_same_audio_e92400cf14ac.mp4
- 任务/检查点：C:\install\AI\Data\CharacterSceneCutaway20261028\run.json
- 关键帧和 H3 血缘：C:\install\AI\Data\CharacterSceneCutaway20261028\image-checks.json、C:\install\AI\Data\CharacterSceneCutaway20261028\video-checks.json 及各任务目录的 Comfy 历史
- 合成验证、FFprobe 与抽帧：C:\install\AI\Data\CharacterSceneCutaway20261028\final-checks.json、C:\install\AI\Data\CharacterSceneCutaway20261028\final
- 浏览器回放记录与截图：C:\install\AI\Data\CharacterSceneCutaway20261028\browser\playback.json、C:\install\AI\Data\CharacterSceneCutaway20261028\browser\cutaway-at-9s.png

## 验收与恢复

- 技术和浏览器播放：**Passed**。实际画面切镜可见，原 AAC 音频包哈希一致。
- 内容和听感：**NeedReview**。远景几乎静止，窗格/房间布局不同；人物、切镜和听感等待用户审看。
- 正式发布：**Blocked**。不得把本地试片当成正式审核或人物全身素材。
- 未生成或恢复被拒素材；此前双人场景仍保持待审。
- 原片及其检查点和素材 SHA256 在执行前后比对一致。模型、人物库、原片均未清理、覆盖或重置。
- 控制器检查点 Data/CharacterSceneCutaway20261028/run.json 标记完成后，重新执行 tools/character_wide_cutaway.py prepare 只核验并恢复记录，不重新提交任务；遇到不确定提交记录先查业务任务而非重复生成。
- 当前分支 main，本轮未提交、未推送；本地原有未提交修改保留。
