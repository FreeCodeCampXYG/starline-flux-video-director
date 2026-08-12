# Starline FLUX Video Director

## Install with npx

Install this skill for Codex, Claude Code, Cursor, and other supported agents:

```bash
npx skills add FreeCodeCampXYG/starline-flux-video-director --skill starline-flux-video-director --all
```

For a global user-level installation, add `--global`:

```bash
npx skills add FreeCodeCampXYG/starline-flux-video-director --skill starline-flux-video-director --all --global
```

作者：**墨点星痕**｜英文名：**starline**

把 STAR 故事、课程总结或项目复盘，编排成由人操作 BFL Playground、由脚本负责末帧接力和本地管理的 FLUX 3 多镜头视频项目。

## 它解决什么

- 使用 7 张共享边界帧生成 6 段 `i2v`：A→B、B→C、C→D……，相邻镜头共享同一张图。
- 人工负责 Playground 中的模型选择、图片上传、Generate、结果下载；Skill 不控制浏览器按钮。
- 异步提交、6 秒轮询、立即下载全部样本、失败续跑。
- 默认仅预览；双重付费确认和最大提交数防止失控循环。
- 提供“AI 学习 → Skill → GitHub 开源成果”的 60 秒 STAR 示例。

## Installation｜安装与快速开始

要求 Python 3.10+。纯 API 规划和末帧脚本只使用标准库；Playground 浏览器回退需要 Playwright。

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

本地安装到个人 Skills 目录（不会发布网络）：

```powershell
Copy-Item -Recurse -Force . "$env:USERPROFILE\.codex\skills\starline-flux-video-director"
```

Verify the package after installation with `npx skills list` or `npx skills list --global`.

## Examples｜你可以直接这样说

- “把这份 STAR 复盘做成七张首尾帧衔接的六段 FLUX 3 视频。”
- “检查项目连续性和 API 参数，先不要真实生成。”
- “活动免费，按 6×20 秒 FHD 执行，断点后继续。”

```powershell
python scripts/flux_video_loop.py validate examples/ai-learning-star.project.json
python scripts/flux_video_loop.py plan examples/ai-learning-star.project.json
```

把示例复制到独立工作目录，替换素材 URL。不要提交带签名的临时 CDN URL。

无需图片上传接口：把七张本地 JPG/PNG 放入 `examples/keyframes/`。脚本会在内存中转成 API 支持的内联 Base64，并提交为 `[[0, 首帧], [20, 尾帧]]`；Base64 不会落盘到请求快照。

确认账户额度和预计提交数后：

```powershell
$env:BFL_API_KEY = "<your-key>"
python scripts/flux_video_loop.py run path\to\project.json --execute --confirm-run FREE_PROMO_CONFIRMED
```

中断后运行同一命令即可续跑。查看状态：

```powershell
python scripts/flux_video_loop.py status path\to\project.json
```

## 人工操作循环

每段按此顺序操作：复制本项目打印的镜头提示词 → 在 Playground 选择 FLUX 3 → 上传初始图（第一段可不上传，后续上传上一段末帧）→ 设置横屏、音频和时长 → 点击 Generate → 下载 MP4 → 放入 `generated/ai-learning-star-film/clips/<shot-id>/<shot-id>.mp4` → 运行 `extract-last-frame` 提取下一段首帧。

提取人工下载视频的末帧：

```powershell
python scripts/flux_video_loop.py extract-last-frame examples/ai-learning-star.project.json 01-situation path\to\01-situation.mp4
```

如果 API 返回 `402 Insufficient credits`，不要继续调用 API；直接使用以上人工循环。免费 Playground 与 API credits 可能是不同配额。

## 浏览器自动化（可选）

当 API 明确返回不可用（例如 `402 Insufficient credits`），但免费 Playground 可用时，可切换到受保护的浏览器回退模式。严格顺序为：等待不存在 `Cancel`/排队任务 → 点击 `Reset all inputs` 并确认 Prompt 归零 → 按 API 字段重建模型、提示词、媒体和参数 → 等待 `Generate.disabled` 消失 → 正常点击并确认出现新任务。运行中禁止 Reset、禁止强制点击禁用按钮、禁止重复提交。

可以让 Playwright 操作独立的 ChromeGo 会话。首次运行会打开浏览器；Google 登录、验证码和风控由你人工完成，脚本不会读取密码。默认是 dry-run，只填入镜头提示词不点击 Generate：

```powershell
python scripts/playground_loop.py examples/ai-learning-star.project.json
```

确认页面结构和提示词无误后，才使用 `--run` 自动点击 Generate、等待视频、下载 MP4 并提取末帧：

```powershell
python scripts/playground_loop.py examples/ai-learning-star.project.json --run
```

自动化严格使用你现有 ChromeGo 的 profile：`D:\Programs\ChromeGo\TorBrowserPortable\v2rayn\v2rayn2025\chrome-data`，并使用 `socks5://127.0.0.1:10808`。批处理中的 `%~dp0chrome-data` 相对批处理所在目录解析。运行前请先关闭正在使用该 profile 的 ChromeGo 窗口，避免 profile 锁冲突；关闭窗口不会删除用户数据。若页面改版导致选择器失效，脚本会停止并保存诊断截图。

## 项目目录

```text
project.json
.flux-video-state.json
requests/
clips/
```

## 代理

脚本使用 Python/系统标准代理环境变量：

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:10808"
$env:HTTPS_PROXY = "http://127.0.0.1:10808"
```

## 重要限制

- BFL 是付费外部服务；本包没有在你的账户上做真实付费生成，因此 provider-backed 成片质量仍是 `missing evidence`。
- `Ready` 只表示技术完成，不代表导演质量通过。
- 中文标题、项目名、GitHub 界面、精确口播同步应在剪映/达芬奇等后期完成。
- 脚本不会上传本地图片。`i2v` 素材应使用公开 URL 或 API 支持的内联媒体。

## Verification｜验证命令

```powershell
python -m unittest discover -s tests -v
python scripts/flux_video_loop.py validate examples/ai-learning-star.project.json
python <starline-meta-skill>/scripts/validate_skill.py .
```

## Troubleshooting

- `Generating...` 后任务消失：该文字只是按钮瞬态。v0.3.0 必须等待右侧任务卡片发生变化并稳定 30 秒；未出现右侧任务时不判定成功，也不重复点击。
- 找不到 Generate：页面文字嵌套在多层 `span` 中，脚本会从精确文字向上解析真正的 `button`；不要直接对最内层 span 发送点击。
- Start frame 没上传：脚本通过 `Attach start frame` 打开文件选择器，并等待 `Replace/Remove start frame` 与 CDN 缩略图三重证据；三者未出现时停止提交。中文源路径会先复制到纯英文工作路径。

- `BFL_API_KEY 未设置`：只影响真实 `run`；`validate/plan/status` 不需要 Key。
- `422`：项目字段不符合当前 API 严格 schema；根据返回详情修正，不要自动重试。
- `429`：脚本会区分提交和轮询；轮询 429 不会重复提交。
- 素材 URL 失效：优先使用本地 JPG/PNG；脚本会自动转成内联 data URL。
- 连续性漂移：先缩小单镜事件；固定镜头运动；一次只改变一个不变量。
