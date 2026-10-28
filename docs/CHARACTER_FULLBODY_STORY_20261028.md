# 《窗边等候》林安全身远景试片（2026-10-28）

## 实际结果和边界

用户希望将林安全身远景加入之前剧情。保留原15秒切镜版 #1572，在 8.75–10.25 秒插入1.5秒新全身画面，再接回原无人窗景和人物近景；总时长16.5秒。保留原三个旁白来源，第三句后移1.5秒，背景音乐以0.94倍速度铺满新时长并在结尾淡出。原音轨未覆盖；新片音频为重新混制，不声称与原片音轨哈希相同。

旧版角色 #3 有已审正面近照 #36，但没有已审核的全身造型参考。原剧情只显示米白上衣；深灰裤和白鞋依据人物库文字设定新生成，不能证明与原片画外的造型一致。被拒绝的全身参考 #43、#44 未作为输入；它们和双人场景的待审状态保持不变。新结果仅为本地实验性试片，未保存为已审核的人物库版本，也未声称满足正式全身选角门禁。

## 真实来源和候选

| 步骤 | 结果 |
|---|---|
| 原片 | #1572，SHA256 e92400cf14ac53983d4a5d4dd91aa29fdc768d1fa70485acda5750327a194388，未覆盖 |
| 原身份来源 | 人物版本 #3，已审近照 #36，SHA256 faba35ff94c4a080aea1ca5bb663e611697a2b31cad7cc9a2c6e0ec9d6657fef；用于血缘和对照，不是本轮模型的直接图像输入 |
| 实际切镜参考 | 原片 #1572 第209帧，SHA256 05a0d2f60ac18db7f1e9cf04a2846867b77d00b9be8c8d1cea435d0885212db7；与直接解码相同，记录了任务依赖 |
| 初次关键帧 #1573 | 已保留；脸部和微笑与切镜前存在差异，预检 Failed |
| 第一次修复 #1574 | 以原片第209帧修复脸和表情，但针织上衣新增原片没有的麻花纹，预检 Failed |
| 第二次修复 #1575 | 去掉新增麻花纹，完整坐姿及双鞋可见，试片预检 Passed；脸部轻微差别、手指细节和窗格差异仍需人工查看；SHA256 49c18cbc90c2cb48c1721b2cc9a4d3a5193b5add19f36cdb9551f972396d8a91 |
| 全身视频 #1576 | 本地 H3 首帧路线，实际输入哈希与关键帧一致；864×480、24fps、124帧、20步；SHA256 34299482be7854b2cf2eda94caaa1ee052bc20c0bfe84dac7106a7aed2dfbbc1。后半段出现无意义文字和张嘴，整段内容 Failed；逐帧检查前0–1.5秒后仅取前36帧，无原生声音 |
| 合成 #1581 | 16.5秒、864×480、24fps、396帧，重新混制旁白和配乐；SHA256 22a7d9642b0e8be233297b9983fe515d525bc47ce49e9a41d0d9d24dcdda4f11 |

## 测试与审看

实际业务任务、Comfy执行记录、原生输出文件和首帧哈希经过核对，视频全片解码通过；最终成片 FFprobe、媒体 Range、完整解码、抽样画面来源与三段旁白时序检查通过。浏览器完成16.5秒非静音播放，定位到全身画面并截图，无控制台错误。技术通过不等于原生完整视频内容合格，也不能替代人物一致性或听感的最终判断。

视觉限制：林安面部和表情较接近原片，但不保证完全一致；手指较小且相互靠近，窗格、墙面和背景细节与原近景及无人远景并非严格一致；裤鞋此前未出画，需要用户确认造型是否合适。

- 播放与对比：http://127.0.0.1:18080/character-fullbody-story.html
- 成片：C:\install\AI\Data\Artifacts\project-54\video\task-1581\v0001\v0001_fullbody_story_16_5s_narrated_22a7d9642b0e.mp4
- 已截取的全身片段：C:\install\AI\Data\Artifacts\project-54\video\task-1578\v0001\v0001_fullbody_story_insert_ce071a9060fe.mp4
- 原生完整视频（后半段内容失败，保留证据）：C:\install\AI\Data\Artifacts\project-54\video\task-1576\v0001\v0001_task_1576_task_1576_attempt_1_e8a973dd_00001__34299482be78.mp4
- 检查点：C:\install\AI\Data\CharacterFullBodyScene20261028\run.json
- 技术报告及 FFprobe：C:\install\AI\Data\CharacterFullBodyScene20261028\final-checks.json、C:\install\AI\Data\CharacterFullBodyScene20261028\final\ffprobe.json
- 实际图像/视频来源：C:\install\AI\Data\CharacterFullBodyScene20261028\image-checks.json、C:\install\AI\Data\CharacterFullBodyScene20261028\video-checks.json、C:\install\AI\Data\CharacterFullBodyScene20261028\range-inspection.json 和对应任务目录的 Comfy 历史
- 面部和手部对照：C:\install\AI\Data\CharacterFullBodyScene20261028\inspection\face-hands-shoes-1575.jpg
- 浏览器播放和截图：C:\install\AI\Data\CharacterFullBodyScene20261028\browser\playback.json、C:\install\AI\Data\CharacterFullBodyScene20261028\browser\fullbody-shot.png

技术状态 **Passed**；人物、服装、场景连续性和听感 **NeedReview**；正式发布 **Blocked**。已满两次针对关键帧的定向修复预算；旧候选、原片、人物审核和所有检查点均保留。

当前分支 main，未提交或推送。检查点完成后重新执行 tools/character_fullbody_scene.py prepare 只核验已有记录，不重提任务；发现来源变更先调查，不覆盖旧输出。
