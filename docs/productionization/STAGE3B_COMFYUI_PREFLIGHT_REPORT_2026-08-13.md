# Stage 3B Gate 5：ComfyUI loopback 只读预检报告

日期：2026-08-13\
状态：`BLOCKED`（服务和白名单证据通过；目标工作流契约未通过）

## 命令与边界

```text
powershell -ExecutionPolicy Bypass -File scripts/test_stage3b_comfyui_preflight.ps1
```

脚本退出码为 `1`，因为发现执行包契约阻塞后主动停止；不是服务崩溃或测试断言被放宽。脚本只使用现有 ComfyUI venv，未安装、升级或下载任何模型、节点或依赖；API和ComfyUI均在 finally 中停止。

## 实际运行证据

| 检查 | 结果 |
|---|---|
| ComfyUI监听 | PASS；唯一监听 `127.0.0.1:8188` |
| `/system_stats` | PASS；loopback健康响应 |
| `/object_info` | PASS；节点注册表868项 |
| 空 prompt 防护 | PASS；POST `/prompt` 返回HTTP 400，未提交生成prompt |
| API联动 | PASS；API健康同时看到MySQL和ComfyUI online |
| Workflow白名单 | PASS；18个注册工作流，未知Workflow ID拒绝，任意输入路径拒绝 |
| JSON解析 | PASS；实际目录18个JSON全部可解析，缺失节点0 |
| 目标工作流 | BLOCKED；见下节 |

## 目标工作流事实

目标文件：`C:\install\AI\Workflows\12_ltx_face_stable_v3_api.json`。

已确认的尺寸/时长标记：320×416、73帧、24 FPS、`frame_idx=72`，文件名为 v3 目标前缀。

阻塞项：

1. 执行包要求的 `small` 标记未出现。
2. 执行包要求的 `IPAdapter` 标记未出现。
3. 目标节点/输入没有 IP-Adapter，实际使用 `LTXVAddGuide`；这不是同一工作流契约，不能静默等价。
4. 本机实际工作流JSON为18个，而当前验收基线期望15个；差异未被自动忽略。

## 结论与停止点

Gate 5 只能判定为 `BLOCKED`。节点注册和JSON解析不能替代目标工艺契约，不能据此进入Gate 6A或6B。未修改任何Workflow，未提交GPU任务，未生成关键帧、视频或正式Asset。

下一步必须由用户/云端确认是补齐执行包要求，还是正式接受现有 `LTXVAddGuide` 目标契约；确认前保持 Gate 6 `NOT RUN`。
