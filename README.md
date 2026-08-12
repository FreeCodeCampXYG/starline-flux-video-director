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
- 支持人工操作，也支持受保护的 Playground 自动化：复用指定 Chrome profile、按人工节奏填表、上传接力帧、提交、等待和下载。
- 精确识别当前 Prompt 任务；处理 502/503/504、Rate limited 和未知状态，避免重复提交。
- 浏览器下载失败时使用 `yt-dlp` 经代理回退，并用 MP4 容器头和 FFprobe 验证后原子落盘。
- 默认仅预览；双重付费确认和最大提交数防止失控循环。
- 提供“AI 学习 → Skill → GitHub 开源成果”的 60 秒 STAR 示例。

## Installation｜安装与快速开始

要求 Python 3.10+。纯 API 规划和末帧脚本只使用标准库；Playground 浏览器回退需要 Playwright。

### Prerequisites｜前置条件检查清单

- [ ] Python 3.10+ 可运行，并已安装 `requirements.txt`。
- [ ] Playground 自动化已安装 Playwright；使用外部 Chrome 时无需下载 Playwright Chromium。
- [ ] `ffmpeg` 与 `ffprobe` 均可用，或已在项目 JSON 配置绝对路径。
- [ ] 已准备一个用户明确授权复用的 Chrome profile；运行自动化前关闭占用该 profile 的其他 Chrome。
- [ ] BFL Playground 已由用户完成登录；脚本不读取账号、密码或验证码。
- [ ] 需要代理时已确认 SOCKS5 地址；示例 Windows 环境为 `127.0.0.1:10808`。
- [ ] 自动下载回退需要 `yt-dlp`；可通过 `--yt-dlp <绝对路径>` 指定。
- [ ] 真实生成前已确认额度、活动规则、镜头数和最大提交次数。

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### FFmpeg / FFprobe（连续视频必需）

这个技能会从每段 MP4 提取末帧，作为下一段首帧，所以必须同时安装 `ffmpeg` 与 `ffprobe`。先检查：

```powershell
python scripts/setup_ffmpeg.py
```

如未安装，且你同意让脚本联网调用系统包管理器下载，运行：

```powershell
python scripts/setup_ffmpeg.py --install
```

脚本按平台调用：Windows `winget install --id Gyan.FFmpeg.Shared --exact`，macOS `brew install ffmpeg`，Ubuntu/Debian `apt-get install ffmpeg`，Fedora `dnf install ffmpeg`，Arch `pacman -S ffmpeg`。它不会自行下载，也不会修改现有 FFmpeg。若已有自定义安装，在项目 JSON 设置 `ffmpeg_path` 与 `ffprobe_path` 为两个可执行文件的绝对路径。

### yt-dlp（自动下载回退，可选）

先检测现有工具，不联网：

```powershell
python scripts/setup_ytdlp.py
```

只有在你明确同意联网安装后运行：

```powershell
python scripts/setup_ytdlp.py --install
```

获取规则：只从开源项目 [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) 官方 GitHub Release 下载；按 Windows、macOS、Linux 与 CPU 架构选择二进制；同时读取同一 Release 的 `SHA2-256SUMS` 并验证 SHA-256；校验成功后才原子安装到用户级 Starline 工具目录。脚本不访问第三方下载站、不静默覆盖；升级托管版本必须显式使用 `--install --force`。无法自动识别的平台会停止，并要求用户核对官方 Release 后通过 `--asset` 指定。

已有自定义工具时无需复制或重装：

```powershell
python scripts/playground_loop.py project.json --yt-dlp "D:\path\to\yt-dlp.exe"
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

先在操作系统的用户环境变量界面配置 BFL 凭据；不要把凭据写进命令、项目 JSON、日志或仓库。重新打开终端后运行：

```powershell
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

当 API 明确不可用、但免费 Playground 可用时，可切换到受保护的浏览器回退模式。严格顺序为：启动冷却 → 等待无活动任务 → Reset 并确认 Prompt 归零 → 随机等待 10–20 秒 → 上传首帧并验证 CDN → 填 Prompt → 设置非时长参数 → 最后设置 Duration → 提交前冷却 → 正常点击并确认当前 Prompt 新任务。Generate 为 disabled 时只等待；运行中禁止 Reset、强制点击或无证据重交。

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

- `Generating...` 后任务消失：该文字只是按钮瞬态。v1.2.0 必须等待当前 Prompt 对应的新任务卡并稳定；未确认时标记 unknown，不重复点击。
- `/api/playground/generate` 返回 `502/503/504`，或匹配任务出现 `system_error / Service issue / over capacity`：只执行有界恢复。未知状态绝不自动重交。
- 控制台出现 React 418、preload、CSP 或 iframe 警告：这些不是 BFL 任务失败证据，不触发重试。
- 找不到 Generate：页面文字嵌套在多层 `span` 中，脚本会从精确文字向上解析真正的 `button`；不要直接对最内层 span 发送点击。
- Start frame 没上传：脚本通过 `Attach start frame` 打开文件选择器，并等待 `Replace/Remove start frame` 与 CDN 缩略图三重证据；三者未出现时停止提交。中文源路径会先复制到纯英文工作路径。
- 页面提示发送太快：脚本打开页面后冷却 30–45 秒、Reset 后随机等待 10–20 秒，再按“先上传首帧、再填 Prompt、最后改 Duration”的顺序错峰设置；Generate 前再冷却 30–45 秒。
- 错误卡出现 `Rate limited` 和 `Retry`：不要 Reset 或重新上传。脚本先点击错误卡 Retry，确认主 Generate 恢复后随机等待 10–20 秒，再点击一次主 Generate；恢复模式为 `--retry-rate-limited --rate-limit-cooldown-min 10 --rate-limit-cooldown-max 20`。
- 自动下载损坏：脚本不再抓页面最后一个视频。它只取当前 Prompt 任务 URL，浏览器下载失败则调用 `yt-dlp` 走 10808 SOCKS5H 代理，并在原子落盘前检查 MP4 头和 FFprobe。

- `BFL_API_KEY 未设置`：只影响真实 `run`；`validate/plan/status` 不需要 Key。
- `422`：项目字段不符合当前 API 严格 schema；根据返回详情修正，不要自动重试。
- `429`：脚本会区分提交和轮询；轮询 429 不会重复提交。
- 素材 URL 失效：优先使用本地 JPG/PNG；脚本会自动转成内联 data URL。
- 连续性漂移：先缩小单镜事件；固定镜头运动；一次只改变一个不变量。

## License｜许可证

本项目采用 [MIT License](LICENSE)。你可以在保留版权与许可证声明的前提下使用、修改和再分发。
