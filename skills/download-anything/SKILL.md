---
name: download-anything
description: 面向个人与 AI Agent 的全能下载与结构化归档工具。当用户要求下载、提取、转换或归档社交视频与图文（B站、抖音、小红书、YouTube、X、微博、Instagram、TikTok、m3u8）、播客与音频（小宇宙、Apple Podcasts、网易云音乐、Spotify、Apple Music、本地 NCM 解密与 FLAC 转 MP3）、文章与知识库（微信公众号、知乎/掘金/CSDN/Medium 等技术社区、Obsidian 同步）、学术论文与电子书（arXiv、DOI 论文、ISBN/MD5 电子书）、百度/夸克网盘分享、GitHub 单文件或微软商店/安卓 APK 安装包时触发；也可在用户要求总结视频、播客或文章链接时调用，以提取本地字幕（.srt）、转写稿、Shownotes 或 Markdown 正文供 Agent 分析。
---

# Download Anything (DA)

调用 `da`（或 `dl`）将分享口令文本、链接、DOI、ISBN、MD5、包名或本地音频文件下载并结构化归档到本地。各平台详细输入输出规范见 [references/platforms.md](references/platforms.md)，完整 CLI 参数与 JSON 字段定义见 [references/cli.md](references/cli.md)。

## 1. 支持的能力与路由速查表（按平台合并，自动识别视频/图文）

| 类别 | 支持平台与输入形式 | 主文件产物（自动识别形态） | 自动生成的配套结构化文件（`sidecars` / `companion_files`） |
| :--- | :--- | :--- | :--- |
| **视频、图文与社交** | B站（链接/`b23.tv` 口令）、抖音（分享口令/`v.douyin.com`）、小红书（链接/`xhslink` 口令）、YouTube、X (Twitter)、微博、Instagram、TikTok、标准 `.m3u8` | 视频输出 `.mp4`（抖音支持免水印最高 4K；加 `-a` 提取纯音轨 `.m4a`/`.mp3`）；多图输出 `image_01.jpg` | `cover.jpg` 原画封面、`content.md`（正文/标签/互动数据）、`content.info.json`；**B站自动提取 `.srt` 字幕**；**抖音同步提取 `audio.mp3` 原声**；**小红书实况图提取配套 `.mov`**；多图其余图片按序存于 `companion_files` |
| **播客、音乐与音频** | 小宇宙单集、Apple Podcasts 单集、网易云音乐、Spotify、Apple Music、本地 `.ncm` 解密、本地 `.flac` 转码 | `.m4a` 或 `.mp3`（本地转换统一输出 `320kbps .mp3`） | 播客 `content.md`（完整 Shownotes 与时间轴）、音乐 `.lrc` 同步滚动歌词、高清专辑封面；加 `--transcribe` 生成 `.transcript.md` |
| **文章与知识库** | 微信公众号文章、主流技术社区（知乎/掘金/CSDN/博客园/Medium/Substack/少数派/简书/SegmentFault/开源中国/V2EX） | 干净 Markdown `article.md` | 正文全部防盗链图片本地化（`img_01.png`... 并重写相对路径）；加 `--vault` 自动注入 YAML frontmatter 同步至 Obsidian |
| **论文与电子书** | arXiv（链接或编号如 `2310.06825`）、DOI（如 `10.1186/...`）、电子书（10/13 位 ISBN 或 32 位 MD5） | 论文 `.pdf`、电子书 `.epub` / `.pdf` | 论文自动生成标准 `citation.bib` 引用文件与包含作者/摘要的 `content.md` |
| **网盘分享** | 百度网盘（含提取码口令）、夸克网盘（支持子目录递归与自动清理云端临时目录） | 分享原文件（ZIP/TAR 默认安全解压） | `extracted_files` 解压文件清单、`content.info.json` |
| **代码与安装包** | GitHub 单文件（`blob` 链接）、微软商店（链接或 12 位 Product ID，限免费 MSIX/Appx 应用）、安卓 APK（Play 链接或包名，基于 F-Droid/Aptoide 镜像） | 原代码文件、`.msixbundle`/`.appxbundle`、`.apk` | `content.md`（含 PowerShell 离线安装指令或 `adb install` 命令） |

## 2. AI Agent 执行工作流（重要）

### 第一步：环境检查与安装确认（首次调用必检）
在执行下载前，**先确认本机是否已安装 `da` 及其运行依赖，未安装时必须先询问用户确认，不要静默修改系统环境**：

1. **定位可执行文件**：优先查找 `PATH` 中的 `da`（或 `dl`），若无则检查默认独立虚拟环境 `~/.download-anything/venv/bin/da`（Windows 为 `%USERPROFILE%\.download-anything\venv\Scripts\da.exe`）。
2. **未安装 `da` 或缺少 Python 3.10+ 时（先询问用户）**：
   - 若上述路径均不存在，先检查本机是否有 `python3`（需 `3.10` 及以上版本；注意 macOS 系统自带 `python3` 常为 `3.9`）。
   - **主动向用户询问确认**：告知用户本机尚未初始化 `da` 运行环境（或缺少 Python 3.10+），询问是否允许运行本 Skill 目录下的安装脚本 `python3 <Skill目录>/scripts/install.py`（若无 Python 3.10+，脚本可通过 `uv` 下载独立的 Python 3.12 并创建 `~/.download-anything/venv` 隔离环境，不污染系统 Python）。**待用户同意后**，再执行 `python3 <Skill目录>/scripts/install.py --yes`。
3. **运行环境自检（`da doctor --json`）**：
   - 首次安装后或遇到环境报错时，运行 `da doctor --json` 检查 `all_required_ok` 与 `media_ready`。
   - **缺少 Python 依赖包**：若 `all_required_ok` 为 `false`，询问用户后运行 `da doctor --fix --json` 自动补齐（官方 PyPI 超时会自动切换清华/阿里云镜像）。
   - **音视频任务缺少 `ffmpeg` / `ffprobe`**：若当前任务涉及视频或音频，而 `media_ready` 为 `false`（未安装 FFmpeg），请明确告知用户“文档、图片、论文、电子书与网盘功能不受影响，但音视频合并、转码与双轨校验需要 FFmpeg”，并**询问用户是否需要代为执行安装命令**（macOS：`brew install ffmpeg`；Windows：`winget install -e --id Gyan.FFmpeg`；Linux：`sudo apt install ffmpeg`）。

### 第二步：前置转换与工具边界判断
当用户只提供名称而非直接链接/ID 时，**Agent 应先自行检索出精确标识符，再传给 `da`**：
- **电子书**：若用户只给书名（如“帮我下《傲慢与偏见》英文原版”），不要直接传书名模糊搜索；请先查出该书目标版本的 **10/13 位 ISBN**（如 `9780141439518`）或 **32 位 MD5**，再执行 `da "<ISBN或MD5>" --json`。
- **学术论文**：若用户只给论文标题，先查出对应的 **arXiv 编号**（如 `2310.06825`）或 **开放获取 DOI**，再执行 `da "<arXiv编号或DOI>" --json`。
- **应用安装包**：若用户只给应用名称，先查出对应的 **Android 包名**（如 `org.videolan.vlc`）或 **Microsoft Store 12 位 Product ID**（如 `9N0DX20HK701`），再交给 `da`。
- **GitHub 仓库与目录**：若用户需要克隆整个仓库或拉取多文件目录，优先使用环境中已有的 `gh` CLI、`git` 或 GitHub MCP；仅单文件直下（`github.com/.../blob/...`）使用 `da`。

### 第三步：执行下载命令
**自动化调用始终附加 `--json`**，从 `stdout` 解析结构化 JSON：

```bash
# 通用下载（直接传入分享口令、URL、DOI、ISBN、MD5、包名/Product ID 或本地音频路径）
da "<目标输入>" --json

# 仅提取纯音轨 / 结合云端语音转写（转写会调用云端 API，仅在用户要求转写或急需文字稿且已配置 Key 时启用）
da "<视频或播客链接>" -a --json
da "<视频或播客链接>" -a --transcribe --json

# 归档至本地 Obsidian 知识库
da "<公众号或文章链接>" --vault "/path/to/vault" --json

# 仅预检目标标题、大小与元数据（网盘预检不会触发云端转存或创建目录）
da "<目标链接>" --check --json

# 捕获或导入本机浏览器/客户端的目标平台登录 Cookie
da login <平台名称> --json
```

可选参数：`-o <目录>` 指定输出目录，`-p <密码>` 指定提取码或解压密码，`-f` 忽略缓存强制重下，`--max-mb N` 调整单文件大小上限（默认 500 MB），`--no-unzip` 保留原压缩包不自动解压，`--no-sidecar` 不生成额外配套文件。

### 第四步：消费结构化归档产物（赋能下游分析）
下载完成后，**不要直接读取 `.mp4` / `.m4a` 等二进制媒体文件**，应直接利用 JSON 返回的结构化文本文件完成用户的总结、提炼或问答需求：
- **总结视频 / 播客**：直接读取 JSON 中 `sidecars.subtitle`（`.srt` 字幕）、`sidecars.transcript`（`.transcript.md` 转写稿）或 `sidecars.markdown`（节目 Shownotes、视频简介、时间戳与互动数据）。
- **精读公众号 / 技术文章**：直接读取 `primary_asset`（`article.md`），正文内插图已转为同目录下的本地图片文件。
- **整理学术文献**：读取 `primary_asset`（`.pdf`）的同时，可直接读取 `companion_files` 中的 `citation.bib` 获取标准 BibTeX 引用，以及 `sidecars.markdown` 获取摘要与作者元数据。

## 3. 状态判定与异常自愈 SOP

解析 `--json` 输出的 `status` 与退出码，如实反馈并按规则自愈：

- **`status: "success"`（退出码 `0`）**：主文件已通过格式/媒体结构校验（见 `verification.details.level`），所有配套文件与同步步骤均已完成。
- **`status: "cached"`（退出码 `0`）**：命中本地 SQLite 缓存（`~/.download-anything/index.db`）且本地文件完整，直接使用返回的 `primary_asset` 与 `sidecars` 路径，无需重复下载（除非用户要求强制刷新才加 `-f`）。
- **`status: "partial"`（退出码 `2`）**：**主文件已成功下载并通过校验**，仅部分附属文件（如某张配图、字幕 429）或后处理步骤（转写、清理）未完成。
  - **处理准则**：**切勿将 `partial` 当作失败去盲目重下主文件！** 直接使用已落盘的 `primary_asset`，并读取 `warnings` 与 `operations` 字段向用户说明哪项附属步骤未完成及其原因。
- **`status: "dry_run"`（退出码 `0`）**：仅完成 `--check` 预检，未实际落盘文件。
- **`status: "error"`（退出码 `1`）**：根据 `error_type` 执行有限自愈，严禁把失败或预检汇报为下载成功：
  - `AuthenticationRequiredError`：目标平台（如百度网盘、夸克网盘、小红书视频、Instagram 多图）需要登录态。运行 `da login <平台> --json` 自动提取本机已登录会话，或提示用户先在浏览器登录目标站点。严禁在输出中打印 Cookie、Token 或 API Key 明文。
  - `FileTooLargeError`：超过默认 500 MB 上限。若用户明确需要下载该大文件，调高 `--max-mb N` 重试一次。
  - `ExtractionError`（含压缩包格式限制）：自动解压仅支持受限的 `ZIP` / `TAR`；若因 `7z`、`RAR` 或特殊加密方式报错而用户只需保存原压缩包，加上 `--no-unzip` 重试一次。
