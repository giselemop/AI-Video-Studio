# Asset / Attempt / Manifest约定

## 1. Formal Asset ID输入

Formal API的最小输入是`ProjectId + ProductionProfileId + IdempotencyKey + TaskType`，镜头任务还必须有`ShotPlanId`。输入通过`InputAssetId/InputAssetIds`引用数据库资产；服务按项目、用途、扩展名、Manifest状态和不可变路径核验。Formal任务遇到`InputImagePath`、原始参考路径或Episode的`files`数组即拒绝。

| 用途 | 允许扩展名 | 典型来源 |
|---|---|---|
| Image/Cover | png/jpg/jpeg/webp | Keyframe/参考图 |
| Video/Episode/EpisodePreview/Master | mp4 | I2V、Episode、Master |
| Audio | wav/mp3/ogg/flac | TTS/混音 |
| Subtitle | srt/vtt | 字幕 |
| QaReport | json/md | QA报告 |

## 2. 路径边界

`AssetPathPolicy`是已有资产读取边界；`AssetReferenceResolver`额外要求Asset和Manifest都为Ready、`immutable_path=1`、项目归属一致，且数据库相对路径与Manifest相对路径一致。`TaskArtifactService`只允许`Data/Temp/Tasks`作为Attempt临时目录，最终路径为：

```text
Data/Artifacts/project-{projectId}/{purpose}/task-{taskId}/v{version}/v{version}_{name}_{sha256-prefix}.ext
```

拒绝越根、`..`、UNC、设备路径、ADS/非法冒号、错误用途扩展名、空文件、`.part`/`.tmp`文件和现有重解析点祖先。目录/文件必须在受控Data根内。

## 3. 发布顺序

1. `TaskLeaseRepository.ClaimAsync`创建Attempt和任务级临时目录。
2. 外部进程输出到Attempt目录的唯一暂存名；FFmpeg、TTS、字幕和Comfy下载完成后才移动。
3. `ValidateStagedAsync`检查稳定大小、独占读、用途/扩展名；媒体再做FFprobe和解码检查，字幕检查完整时间轴和文本，QA报告解析JSON/Markdown。
4. 事务创建`artifact_publish_intents`（Staging），计算SHA-256和尺寸。
5. 同一磁盘上的`File.Move(source, final, false)`完成非覆盖原子最终化；最终文件名带版本和哈希，已存在目标直接失败。
6. 事务写入`asset_manifests`、`assets`、`generation_results`为Staged并关联Attempt；任务成功时统一改Ready，失败/取消/过期改Quarantined/Rejected。

## 4. 恢复语义

`NeedsReconcile`表示文件已移动但数据库最终化未完成；恢复SOP必须同时比对PublishIntent、Manifest、Asset、文件存在性、大小和SHA-256，禁止直接把文件改名覆盖为成功结果。未完成的Attempt临时目录只能按Attempt隔离处理，不能把残留文件作为正式Asset。

## 5. 阶段2.5隔离库证据

`--stage25-domain`在隔离库真实验证跨Project Asset ID、错误用途、引用删除保护、Attempt编号、Manifest输入/参数/哈希/输出关系、Staged→Ready和定向重做新Attempt；故障产物为Quarantined/Rejected且未成为Ready。空文件、损坏PNG和半字幕三类负向均拒绝，同一最终目标非覆盖移动失败。

`--stage25-path`在受控临时目录验证9类路径/重解析点负向；`test_asset_path_policy.ps1`检查1360个Data文件；`test_external_process_boundary.ps1`和真实FFprobe参数夹具通过。上述是隔离库/受控文件证据，不等同正式项目媒体或真实视频链路。
