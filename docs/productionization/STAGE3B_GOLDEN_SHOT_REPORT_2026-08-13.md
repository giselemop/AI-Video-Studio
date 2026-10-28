# Stage 3B Gate 6：黄金镜头停止报告

日期：2026-08-13\
状态：`NOT RUN`（Gate 5 `BLOCKED`）

## 未执行内容

- Gate 6A 候选关键帧：未执行，未创建候选Asset，未请求用户选择。
- Gate 6B 单次3秒I2V：未执行，未提交ComfyUI prompt，未消耗真实GPU。
- 任务、Attempt、Manifest、PublishIntent和正式媒体：本轮没有新增或修改。

## 停止原因

Gate 5发现目标 `12_ltx_face_stable_v3_api.json` 与执行包要求不一致：缺少 `small` 和 IP-Adapter 契约，实际使用 `LTXVAddGuide`，并且工作流目录数量为18而非15。按照硬停止规则，不能把节点/JSON读取通过当作工艺通过，也不能自动修改Workflow或安装依赖。

## 后续门槛

只有在用户/云端确认目标工作流契约、Gate 5只读预检重新通过，并明确允许Gate 6A后，才可创建最多一个候选关键帧；Gate 6B还需要用户明确批准具体Asset ID。任何一次受控生成后都必须停止等待人工视觉审核，不能自动进入样片或连续生产。
