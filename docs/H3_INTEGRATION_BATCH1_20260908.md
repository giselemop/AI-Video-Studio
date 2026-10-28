# H3 接入第一批改动（2026-09-08）

## 实际完成

- 分支 main，基线 d6ec38d；保留全部原有未提交修改，仅做局部补丁，未 reset/clean、提交或推送。
- 新增 H3WorkflowPolicy：识别原生 H3 图；首轮仅接受图生/文生、124帧、24fps、32倍数尺寸及面积上限。拒绝尚未验证的参考生和高级节点。
- GenerationQueue：H3 不再应用旧 LTX 尺寸/帧数修正，不再因携带参考图切回 LTX。禁止 H3 正式任务及关联生产 Shot 的任务，当前只预留无 Shot 实验路径。
- ComfyUiClient：绑定 H3 原生 prompt；拒绝含糊的多参考/首尾帧自动分配。
- 新增 H3Regression 并接入质量测试工具。

## 验证

- dotnet run --project tests/VideoStudio.QualityHarness -- --h3-regression：12 Passed。
- dotnet run --project tests/VideoStudio.QualityHarness -- --self-test：Passed。
- dotnet build server/VideoStudio.Server.csproj --no-restore：0 warning / 0 error。
- git diff --check：无空白错误；现有文件有换行转换提示。
- 上述是源码/参数夹具验证，不是业务队列或生成能力验收。未修改前端、数据库和运行服务；未执行迁移。
- GPU耗时0；未运行生成，因此显存/内存峰值、合格秒成本无实测值。

## 许可校正与阻塞

前次“所有本地商用都需付费”的结论过于绝对。MiniMax原始 LICENSE 的 IV.1 写明年度商业产品和服务收入超过2000万美元需事先书面授权；同时存在地域、标识及使用限制。Comfy销售页则概括本地商用需商业许可。不能把两者直接等同，也不能据销售页自行购买或据收入门槛直接批准发布。

原始许可：https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE
销售说明：https://comfy.org/minimax/license

需核实部署/发布地域、预期用途、适用主体及选用量化/Turbo权重的完整许可链。未通过前不下载大模型、不启动GPU实验或批准商用。

## 未完成与下一步

1. 将实验准入阻断前移到提交预检；检查所有生产入口，不能把当前 worker 保护称为完整发布许可门禁。
2. 实验视频 QA 应绑定实际124/24时长和生成尺寸，不能沿用生产 Shot 默认512×320。
3. 保存音视频各路输出及模型/工作流/输入哈希；真实验证后处理音轨保留。
4. 720p目标已获用户授权，但本轮未修改自动增强的1080p默认值；需把 Episode 目标可靠贯穿后期及发布包。
5. 完成许可与兼容核查后，只准备首轮约44.4GB文件，执行一条864×480短片，再扩大固定基准。
6. 新源码未部署；真实业务队列、取消恢复、浏览器以及内容验收均未通过。无新样片，无允许发布结果。
