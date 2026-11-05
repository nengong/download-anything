---
name: download-anything
description: 下载并归档多平台数字内容到本地：覆盖视频（B站、小红书、YouTube、X、微博、Instagram Reels、TikTok、HLS/m3u8）、图片（小红书多图/实况图、X 多图、微博多图、Instagram 多图）、音频与播客（小宇宙、Apple Podcasts、网易云音乐、Spotify、Apple Music、本地 NCM/FLAC 转 MP3、B站提取音轨）、文档与文章（微信公众号、知乎/掘金/CSDN/Medium/博客园等技术社区、Obsidian 与 Notion 同步）、论文与电子书（arXiv、DOI 开放获取论文、ISBN/MD5 电子书）、网盘分享（百度网盘、夸克网盘）、代码仓库（GitHub 单文件）以及应用安装包（微软商店安装包、安卓 APK）。
---

# Download Anything

调用 `da`（或 `dl`）将链接、分享文本、DOI、ISBN、MD5 或本地音频文件下载并归档到本地。完整平台矩阵见 [references/platforms.md](references/platforms.md)，CLI 参数与 JSON 协议见 [references/cli.md](references/cli.md)。

## 支持的能力（按类型与平台）

### 1. 视频下载
- **哔哩哔哩（B站）**
  - 支持标准视频链接与 `b23.tv` 分享口令/短链自动清洗解析
  - 下载声画同步 MP4 视频、高清封面（`cover.jpg`）及 UP 主与互动数据
  - 自动提取 CC / AI 字幕并转换为标准 `.srt` 时间轴字幕文件
- **小红书**
  - 支持网页链接与 App 分享文本（`xhslink.com` / `xhslink.cn`）
  - 下载视频笔记 MP4，同步保存标题、正文、话题标签与封面
- **YouTube**
  - 支持标准视频与短链解析，自动选轨合并声画同步 MP4 并保存封面
- **X (Twitter)**
  - 下载推文视频（自动选轨合并高画质 MP4），保留推文正文、作者与封面
- **微博**
  - 免登录下载微博视频 MP4，同步归档微博正文与作者信息
- **Instagram Reels**
  - 下载 Reels 短视频（自动合并音视频轨输出 MP4），保留正文描述与封面
- **TikTok**
  - 下载公开视频 MP4，保留文案、标签与创作者信息
- **通用流媒体（HLS / m3u8）**
  - 支持标准 `.m3u8` 视频流分片拉取、自动合并与完整性校验

### 2. 图片与图文图集
- **小红书多图与实况图（LivePhoto）**
  - 按原笔记顺序批量下载全部高清 JPEG 图片
  - 实况图笔记自动提取配套的 `.mov` 动态视频组件
- **X (Twitter) 多图**
  - 提取推文内全部原图级（`:orig`）JPEG/PNG 图片，按序号完整落盘并归档正文
- **微博多图（九宫格/图集）**
  - 免登录提取微博全部大图，按顺序保存并生成伴生 Markdown 正文
- **Instagram 多图（Carousel）**
  - 配合本机已登录会话 Cookie（`DA_INSTAGRAM_COOKIE_FILE`），按顺序完整下载多图帖全部高清图片

### 3. 音频、播客与音乐
- **小宇宙播客**
  - 下载单集原档音频（`.m4a` / `.mp3`）、单集封面，完整提取节目 Shownotes 与时间轴笔记
- **Apple Podcasts**
  - 解析播客单集链接，下载原档音频与高清封面，提取节目简介与发布信息
- **哔哩哔哩纯音轨**
  - 通过 `-a` 参数直接提取视频纯音轨（`.m4a` / `.mp3`）
- **网易云音乐**
  - 公开曲目直接下载 MP3 与专辑封面，自动提取同步滚动歌词（`.lrc`）
  - 受限曲目自动提取原版封面、歌词与元数据，并通过公开音源匹配下载完整 MP3
- **Spotify & Apple Music**
  - 提取官方曲目元数据与高清专辑封面（Apple Music 支持 3000×3000px），通过公开音源匹配下载 MP3
- **本地加密与无损音频转换**
  - **网易云 `.ncm` 解密**：还原为标准 MP3，保留内嵌专辑封面与歌曲/歌手/专辑 ID3 标签
  - **无损 `.flac` 转码**：转换为标准 320kbps MP3，保留原文件
- **云端语音转写（可选，`--transcribe`）**
  - 配置 `GROQ_API_KEY`、`OPENAI_API_KEY` 或 `SILICONFLOW_KEY` 后，可将下载的播客或音轨转写为带时间戳的 `.transcript.md` 文字稿

### 4. 文档、文章与知识库归档
- **微信公众号文章**
  - 提取完整文章正文转换为干净 Markdown（`article.md`）
  - 自动绕过微信防盗链，将正文内全部插图下载至本地并替换为相对路径引用
- **主流技术社区与专栏文章**
  - 支持知乎、掘金、CSDN、博客园、Medium、Substack、少数派、简书、SegmentFault、开源中国、V2EX
  - 自动剥离网页导航与广告噪声，将正文代码块与配图本地化归档为 Markdown
- **Obsidian 知识库同步（`--vault`）**
  - 将下载的 Markdown、配图与伴生资产一键考入本地 Obsidian Vault，自动注入 YAML frontmatter（标题、来源、标签、导入时间）
- **Notion 数据库同步（可选，`--notion`）**
  - 配置 `NOTION_API_KEY` 与 `NOTION_DATABASE_ID` 后，自动在 Notion 数据库创建归档记录卡片

### 5. 学术论文与电子书
- **arXiv 学术论文**
  - 支持 `arxiv.org/abs/...`、`arxiv.org/pdf/...` 或纯编号（如 `2310.06825`）
  - 下载官方 PDF，提取标题、作者与摘要，自动生成 `citation.bib` 引用文件
- **DOI 开放获取论文**
  - 识别标准 DOI（如 `10.1186/...`），查询 Crossref 与 Unpaywall 下载开放获取全文 PDF，同步生成 `citation.bib`
- **电子书（ISBN / MD5）**
  - 直接输入 10/13 位 ISBN（如 `9780141439518`）或 32 位 MD5，自动检索镜像下载 EPUB / PDF 电子书并执行容器结构校验

### 6. 网盘分享文件
- **百度网盘**
  - 自动识别分享文本中的链接与 4 位提取码，支持 `--check` 预检文件大小，结合本机登录态下载分享原文件（ZIP / TAR 归档默认自动安全解压）
- **夸克网盘**
  - 自动读取登录态、递归查找分享子目录文件、转存至任务专属临时目录 `_da_temp_<uuid>`，下载完成后自动清理云端临时目录

### 7. 代码与开发资产
- **GitHub 单文件**
  - 支持 `github.com/<owner>/<repo>/blob/<branch>/<path>` 链接
  - 免 `git clone` 整个仓库，直接按指定分支或 Commit 精准拉取目标代码、配置或文档原文件

### 8. 应用与软件安装包
- **微软商店离线安装包（Microsoft Store）**
  - 输入商店链接或 12 位 Product ID（如 `9n0dx20hk701`），直接从微软官方 CDN 下载 `.msixbundle` / `.appxbundle` 离线安装包及 PowerShell 安装指引
- **安卓应用安装包（Android APK）**
  - 输入 Google Play 链接、APKPure/Aptoide 链接或应用包名（如 `com.spotify.music`），自动检索镜像下载 `.apk` 安装包并生成 ADB 安装命令

## 安装与环境

1. 优先使用 `PATH` 中的 `da`（或 `dl`），或默认虚拟环境 `~/.download-anything/venv/bin/da`（Windows 为 `%USERPROFILE%\.download-anything\venv\Scripts\da.exe`）。
2. 首次使用时，用 Python 3.10+ 运行本 Skill 目录下的 `scripts/install.py`（非交互环境加 `--yes`）自动完成环境创建与依赖安装。
3. 可通过 `da doctor --json` 检查环境状态，或用 `da doctor --fix --json` 自动补齐缺失的 Python 包。音视频合并、抽轨、转码与结构校验使用系统 `ffmpeg` / `ffprobe`。

## 常用调用命令

```bash
# 单目标下载（支持链接、分享口令、DOI、ISBN、MD5、包名、本地 NCM/FLAC 路径）
da "<目标输入>" --json

# 提取视频纯音轨 / 配合云端转写
da "<视频或播客链接>" -a --json
da "<视频或播客链接>" -a --transcribe --json

# 归档至本地 Obsidian 知识库
da "<公众号或文章链接>" --vault "/path/to/vault" --json

# 仅预检目标标题、大小与元数据
da "<目标链接>" --check --json

# 提取或捕获本机浏览器/客户端的目标平台登录 Cookie
da login <平台名称> --json

# 批量串行下载（一行一个目标，支持 # 注释）
da -i links.txt --json
```

可选参数：`-o <目录>` 指定保存目录，`-p <密码>` 指定提取码或解压密码，`-f` 跳过本地缓存强制重下，`--no-unzip` 保留原压缩包不自动解压，`--no-sidecar` 不生成额外伴生元数据文件。

## 结果状态与退出码

- `success`（`0`）：主文件与附属步骤全部完成并通过格式/媒体结构校验。
- `cached`（`0`）：命中 `~/.download-anything/index.db` 本地缓存，直接返回已有文件路径。
- `dry_run`（`0`）：返回 `--check` 预检元数据。
- `partial`（`2`）：主文件已保存，部分伴生文件或后续步骤见 `warnings` 与 `operations`。
- `error`（`1`）：任务未完成，原因见 `error_type` 与 `message`。
