---
name: starline-flux-video-director
description: Safely direct, plan, generate, resume, and review multi-shot FLUX 3 videos through shared start/end keyframes, the BFL API, or a guarded BFL Playground browser fallback when API submission is unavailable. Use when the user wants 连续视频, 首尾帧连续生成, 多镜头循环生成, STAR 视频, FLUX 3 Video API, API不可用转网页, Playground回退, i2v keyframe chaining, storyboard-to-video, 断点续跑, or consistent character/camera/audio across generated clips. Do not use for ordinary video editing or unbounded unattended rendering.
metadata:
  author: "墨点星痕 (starline)"
  version: "0.4.0"
---

# Starline FLUX Video Director

## 首帧上传后的提交门禁

- 首帧上传后不得立刻点击 Generate。BFL CDN 缩略图要连续保持同一地址，并额外随机等待 `8–12` 秒。
- 稳定等待后，再同时确认缩略图、`Replace start frame` / `Remove start frame` 控件，以及 enabled 的 Generate 均仍存在；任一状态变化则重新观察。
- 可用 `--upload-settle-min` / `--upload-settle-max` 调整稳定等待范围，最低不得少于 5 秒。

## Playground 提交确认（v0.4.0）

- `Generating...` 只表示点击被页面接收，不表示任务已经创建，严禁据此立即关闭浏览器。
- 点击前记录右侧任务卡片快照；点击后必须观察到右侧出现新任务卡或卡片摘要发生变化。
- 右侧任务变化后默认继续稳定观察 30 秒，才允许 `--submit-only` 退出；可通过 `--submit-stabilize-seconds` 调整为 5–120 秒。
- 90 秒内右侧任务区没有变化时保存诊断截图并报错；不重复点击 Generate。
- `Cancel` 只能辅助判断页面正在处理，不能单独证明任务已经创建。
- Generate 的可见文字嵌套在多层 `span` 中；定位时优先使用 `button[aria-label="Generate"]`，并以精确 `span` 文本向上解析最近的 `button` 作为回退，禁止直接点击文字 span。
- Start frame 必须点击 `button[aria-label="Attach start frame"]` 并通过 file chooser 选择文件；只有 `Replace start frame`、`Remove start frame` 与 `img[alt="Input image"]` 同时出现，且缩略图来自 BFL CDN，才算上传成功。上传未验证时禁止点击 Generate。

把一个叙事目标编排成连续、可恢复、可审查的 FLUX 3 多镜头项目。主路径使用 BFL API；当 API 因额度或访问条件不可用、但用户已登录的免费 Playground 可用时，可显式切换到受保护的浏览器回退模式。FFmpeg 末帧提取和本地状态管理由脚本完成。

## 工作流

1. 先读 `references/directing-system.md`，把内容整理成一个视觉命题、角色圣经、场景圣经、声音圣经和镜头表。
2. 每个镜头只保留一个主要事件：开场构图 → 可见原因 → 物理反应 → 收束画面。CJK 字幕、项目名和精确同步交给后期。
3. 采用共享边界帧链：镜头 1 使用 `frame-00 → frame-01`，镜头 2 使用 `frame-01 → frame-02`，依次类推。所有镜头使用 `i2v` + 两张 `keyframes`；上一镜尾帧必须与下一镜首帧是同一文件。
4. 创建项目 JSON；格式见 `references/project-schema.md`，可从 `examples/ai-learning-star.project.json` 开始。
5. 先校验和预览，不产生费用：

```powershell
python scripts/flux_video_loop.py validate examples/ai-learning-star.project.json
python scripts/flux_video_loop.py plan examples/ai-learning-star.project.json
```

6. 在免费 Playground 主路径中，由人把提示词粘贴到页面、上传首帧（后续为上一段末帧）、点击 Generate 并下载 MP4。Skill 不执行页面按钮。API 自动执行仅作为可选备用路径，只有用户明确授权真实生成后才执行：

```powershell
$env:BFL_API_KEY = "<your-key>"
python scripts/flux_video_loop.py run examples/ai-learning-star.project.json --execute --confirm-run FREE_PROMO_CONFIRMED
```

7. 每段人工下载后，把 MP4 放入项目目录；脚本立即提取末帧、保存无密钥状态并打印下一镜提示词。API 备用路径成功后才由脚本自动下载 `result.samples`。
8. 每个镜头必须人工按 `references/review-scorecard.md` 判定。未经人工确认，不把“API Ready”称为成片通过。

## API 不可用时的 Playground 回退

仅当 API 明确不可用（例如提交返回 `402 Insufficient credits`），且用户确认 Playground 免费生成可用时，运行 `scripts/playground_loop.py`。浏览器必须复用用户指定的既有 Chrome profile 和代理；不得复制、读取或打印登录密钥。

回退状态机固定为：

1. 页面存在 `Cancel`、排队提示或运行中任务时只等待；禁止 Reset、禁止重交。
2. 空闲后真实点击 `Reset all inputs`，并确认 Prompt 归零、旧媒体输入清空。
3. 按 API 请求顺序重建页面状态：模型 → Prompt → Start/End frame 或 Start video → aspect ratio → duration → resolution → generate audio → safety tolerance → draft。
4. Prompt 必须读取实际 `textarea.value` 验证，不能只相信 Playwright `fill()` 返回成功。
5. `Generate` 带原生 `disabled` 属性时不得 `force=True`；等待它恢复 enabled。超时则截图并停止。
6. 正常点击后必须观察到新 `Cancel`/排队状态才算提交成功；否则按失败处理，不重复点击。
7. 默认采用人工节奏：每次交互后独立生成 `1.0–3.0` 秒的随机小数等待，不使用固定节拍。可通过 `--pace-min` 与 `--pace-max` 调整范围；要求 `0.5 <= min <= max <= 10`。
8. 当前页面稳定控件契约：Duration 使用可见 `input[type=number][min=5][max=20]`，输入后同时验证数字框 value、滑杆 `aria-valuenow` 和参数按钮文本；Generate 使用精确的 `button[aria-label="Generate"]`，只有无 `disabled` 属性时才允许点击。

当前已验证的 Windows ChromeGo profile 为 `D:\Programs\ChromeGo\TorBrowserPortable\v2rayn\v2rayn2025\chrome-data`，Chrome 可执行文件仍位于 `chrome\Chrome-bin\chrome.exe`，代理为 `socks5://127.0.0.1:10808`。`%~dp0chrome-data` 始终相对批处理所在目录解析，不相对 `CD` 目录解析。

## 连续性铁律

- 每个镜头的首尾帧被像素级固定；提示词只描述两帧之间发生的一个连续动作。
- 每镜固定五个不变量：人物身份、服装、主光方向、镜头运动方向、环境声底色。
- 接缝处记录方向、速度、构图关系和声音尾音；一次只修一个连续性变量。
- 共享帧必须使用同一文件字节；不得为相邻镜头重新生成“看起来相同”的边界帧。
- 两次结构相似的失败后停止自动重试，回到镜头设计；不要继续堆形容词或烧额度。

## 安全边界

- 默认命令只读或写本地计划；真实提交必须同时具备 `--execute` 和精确确认短语。免费活动也保留确认门，避免误启动长任务。
- 不打印、保存或传递 `BFL_API_KEY`。不要把带 `sig=`、`token=` 等查询参数的短期媒体 URL写入模板、日志或仓库。
- HTTP `429`：提交阶段未创建任务，可退避后重交；轮询阶段任务已存在，只继续轮询，严禁重交。
- HTTP `400/401/402/403/422` 不自动重试。`5xx` 只做有上限退避。
- 每个项目设 `max_submissions`；达到上限立即停止。
- 不自动发布、不自动上传本地素材到第三方存储、不自动合并成片。最终字幕、混音和剪辑属于后期。

## 输出契约

- `project.json`：无密钥导演计划。
- `.flux-video-state.json`：任务 ID、轮询地址、状态、本地成果路径和错误；不含 API Key。
- `clips/<shot-id>/`：下载的全部 MP4 或 draft cache。
- `requests/<shot-id>.json`：实际无密钥请求体，便于复现。
- 人工审片结论：`ship / usable_with_defect / experimental / reject`。
