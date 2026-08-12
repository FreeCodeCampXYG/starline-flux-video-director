# 项目 JSON 规范

## 顶层

```json
{
  "project": "short-name",
  "endpoint": "https://api.bfl.ai/v1/flux-3-video",
  "output_dir": "./generated/project-name",
  "max_submissions": 6,
  "defaults": {
    "aspect_ratio": "16:9",
    "duration": 10,
    "resolution": "fhd",
    "generate_audio": true,
    "safety_tolerance": 2,
    "draft": false
  },
  "continuity_bible": {},
  "shots": []
}
```

- `max_submissions` 必须为正整数，限制本项目累计真实提交数。
- `duration`：整数 5–20 或 `"auto"`。
- `aspect_ratio`：`auto / 21:9 / 2:1 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16`。
- `resolution`：`hd / fhd`。

## 镜头

```json
{
  "id": "01-situation",
  "star": "S",
  "mode": "i2v",
  "prompt": "...",
  "keyframes": ["https://.../start.jpg", "https://.../end.jpg"],
  "duration": 10,
  "review": {"intent": "...", "seam_out": "..."}
}
```

- 本 Skill 的连续项目只接受 `mode: "i2v"`，每镜恰好两张 `keyframes`。
- 项目文件里的 `keyframes` 写两个公开 URL 或本地相对路径。提交时脚本会自动转换成 `[[0, 首帧], [duration, 尾帧]]`；本地图片变为内联 data URL，请求快照只保存原路径。
- 因为使用精确时间戳帧，`duration` 必须是 5–20 的整数，不能使用 `auto`。
- 脚本校验 `shot[n].keyframes[1] == shot[n+1].keyframes[0]`，不共享同一路径就阻断。
- 镜头级参数会覆盖 `defaults`。
- 不支持的字段会在提交前阻断，避免 API `422` 和无意义付费请求。

## Draft 流程

项目处于创意探索时使用 `draft: true`。本版本会下载 draft caches，但不会自动增强；只有人工选中具体 cache 后，再使用 BFL `draft_enhance` 单独执行，避免多候选映射错误。
