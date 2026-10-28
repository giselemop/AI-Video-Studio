# 两个人物模型库与视频调用验收

用户授权：2026-10-26，先用两个固定人物跑通人物模型库和视频生成调用，完成测试和验收。

## 实施范围与验收顺序

1. 复用现有角色、参考图及 `entity_versions` 不可变快照，不增加第二套模型目录或数据库结构。
2. 保存人物外貌、造型、声音设定、参考图版本/哈希和明确选定的视频工作流，形成可跨项目选择的试用版本。
3. 视频调用必须指定人物版本和参考视角；服务端解析并冻结实际首帧、提示词和工作流。提交前与GPU执行前均复核来源，禁止缺图后静默替换。
4. 工作台提供人物版本浏览、保存、调用预览和视频提交，保留原角色管理入口。
5. 新生成两个人物参考，分别从人物库调用两个镜头。使用本地队列、GPU并发1，不下载新模型、不训练LoRA、不调用云服务。
6. 验证版本不可变、重复请求、缺失视角、路径/哈希/工作流漂移、旧角色编辑、媒体解码和实际浏览器操作。

## 当前进度

- 运行环境：API/MySQL/ComfyUI/FFmpeg在线，RTX4070 12GB，队列空闲。
- 备份：`backup/20261026_090123/`，修改前已有大量未提交工作，全部保留。
- 技术实现与本轮验收 Passed。人物自然度和最终偏好仍待人工复核，发布 Blocked。

恢复入口：`Data/CharacterLibrary20261026/run.json`。已登记任务必须先查询，禁止因重跑验收脚本重复生成。


## 最终技术验收

项目46，分支`main`，HEAD `d6ec38d`；本轮未提交或推送。原有未提交工作保留。

| 人物/调用 | 任务 | 人物版本ID | 参考视角 | 成片规格 |
| --- | --- | --- | --- | --- |
| linan-video-front | 1424 | 1 | front | 864×480 / 24FPS / 124帧 |
| linan-video-threeQuarterRight | 1426 | 1 | threeQuarterRight | 864×480 / 24FPS / 124帧 |
| zhouyan-video-front | 1427 | 2 | front | 864×480 / 24FPS / 124帧 |
| zhouyan-video-threeQuarterRight | 1428 | 2 | threeQuarterRight | 864×480 / 24FPS / 124帧 |
| browser-linan-v2 | 1425 | 3 | threeQuarterRight | 864×480 / 24FPS / 124帧 |

实际API检查73项、媒体和来源检查55项、实际UI检查7项及五条完整浏览器播放均Passed。媒体逐条完整解码，并验证HTTP Range 206、业务库快照、Comfy实际首帧/提示词/成功回执及输出SHA。

观察到的Comfy运行并发最高1；GPU使用采样最高11712MiB，磁盘可用空间采样最低121.7GiB。采样值不是单任务精确峰值。

修复了MySQL JSON小数格式变化引起的哈希误判，按原有DECIMAL(5,2)声音字段精度计算稳定快照；未改写旧版本。另修复提交后回滚掩盖原始错误、卡片布局、历史版本显示及源角色删除/版本保存的竞争保护。

本轮使用已安装的RealVisXL、Klein和H3，通过真实业务队列新生成四张人物参考及五条视频；没有新增模型、LoRA训练或云推理。仅验证小幅表情、眨眼、轻点头和两个参考角度；跨场景、完整转身、复杂肢体、长视频、固定角色声音及精细口型不属于本轮通过结论。人物身份与自然度仍由用户复核，未虚构身份识别评分。

证据：`Data/CharacterLibrary20261026/`中的`run.json`、`api-regression.json`、`media-verification.json`、`task-input-traces.json`、逐任务Comfy历史与FFprobe、`browser-ui-checks.json`、`browser-playback.json`、`resource-samples.json`、`acceptance-summary.json`。技术结果可在[验收样片](http://127.0.0.1:18080/character-library-preview.html)查看，日常使用见[人物模型库使用说明](人物模型库使用说明.md)。


## 部署与内容复核

已将同一验收构建同步到标准启动目录`server/publish`，与运行中的V3程序集SHA完全一致；旧标准构建备份在`Data/CharacterLibrary20261026/previous-normal-publish`。原`start.bat`和上级启动入口可以继续使用，队列启用配置已核对。辅助18081服务保持原来的暂停状态。

对五条视频各六处抽帧进行了参考图对照，人物、发型和服装基本相符；部分镜头仍有嘴部动作，固定声音和精细表演没有据此判为通过。详见`visual-inspection.json`。所有工作流、图片与视频继续保留，完成后执行恢复脚本只核验，不再提交任务。
