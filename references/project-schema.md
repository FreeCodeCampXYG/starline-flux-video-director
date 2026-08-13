# 项目 JSON 规范

## 顶层

```json
{
  "project": "short-name",
  "endpoint": "https://api.bfl.ai/v1/flux-3-video",
  "output_dir": "./generated/project-name",
  "delivery": {
    "target_root": "D:/data/AI资料",
    "date": "20260812",
    "folder": "AI领导力-群星之舵",
    "cover": "./AI领导力-群星之舵-横版封面.png",
    "shot_titles": {
      "01-situation": "S危机-决策瓶颈"
    }
  },
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
- `delivery` 只控制本地剪辑交付包，不参与 BFL 请求。`target_root` 可省略；Windows 默认 `D:/data/AI资料`，其他平台必须显式配置。`date` 必须是 `YYYYMMDD`；`folder` 是项目子目录；`cover` 相对项目 JSON 解析；`shot_titles` 按镜头 ID 配置最终中文文件名。
- 使用 `python scripts/package_delivery.py project.json` 预览，确认后追加 `--execute`。脚本按 `shots` 数组顺序编号，复制并做 SHA-256 校验，不移动原始视频。

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
