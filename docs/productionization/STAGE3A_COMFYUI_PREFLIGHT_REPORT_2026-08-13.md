# 阶段3A ComfyUI只读运行时预检报告

状态：`NOT RUN（Gate 3/4未通过）`\
日期：2026-08-13

## 本轮边界

本轮未启动ComfyUI，未监听`127.0.0.1:8188`，未读取节点列表、模型路径或工作流运行时状态，未提交任何GPU任务。未安装/升级节点、模型或依赖。

## 待执行检查

- loopback HTTP/API健康和GPU识别：NOT RUN。
- 节点列表、模型路径、缺节点、缺模型、无效参数和过时节点：NOT RUN。
- 当前15个工作流JSON逐个解析：NOT RUN。
- `12_ltx_face_stable_v3`读取、目标模型/节点、320×416、73帧、24FPS、guideFrameIndex=72、small motion：NOT RUN。
- 正式接口只允许注册工作流、拒绝任意工作流/路径：NOT RUN。

预检未通过前，不得安装任何缺失组件，也不得进入Gate 6。
