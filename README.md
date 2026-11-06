<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="Download Anything (DA) — 面向个人与 AI Agent 的全能下载与结构化归档工具，支持 CLI 与 AI Agent Skill 双入口">
</p>

<p align="center">
  <a href="#快速上手">快速上手</a> ·
  <a href="#安装升级与卸载">安装部署</a> ·
  <a href="#支持的能力全景">支持平台矩阵</a> ·
  <a href="#工作机制与架构设计">架构与四步闭环</a> ·
  <a href="./skills/download-anything/references/cli.md">CLI 与 JSON 协议</a>
</p>

# Download Anything (DA)

**Download Anything (`da` / `dl`)** 是一个**面向个人与 AI Agent 的全能下载与结构化归档工具**，提供 **命令行 CLI** 与 **Agent Skill** 双入口。

无论是日常刷到的 **B站 / 抖音 / 小红书 / YouTube / X 视频与多图实况**、**小宇宙与 Apple Podcasts 长播客**、**本地加密音频（NCM）**，还是 **微信公众号长文、技术博客、百度/夸克网盘分享、arXiv/DOI 学术论文、ISBN/MD5 电子书、GitHub 单文件或应用安装包**，直接把链接或杂乱的 App 分享口令丢给它，即可自动完成：

1. **口令与脏链接剥离**：自动剔除分享文案中的乱码、表情与推广前缀，精准识别 URL、网盘提取码、DOI、ISBN 与 MD5。
2. **主文件与结构化附件同步落盘**：除视频/音频/PDF 主文件外，自动提取配套的 `.srt` 字幕、`cover.jpg` 原画封面、`audio.mp3` 独立音轨、`citation.bib` 引用文件、防盗链本地化配图与 `.info.json` / `.md` 元数据，可直接喂给 AI Agent 总结或归档至 Obsidian。
3. **文件完整性校验**：基于 `ffprobe` 校验音视频双轨与时长，基于 `pypdf` / `Pillow` / `zipfile` 校验文档、图像与 EPUB/ZIP 容器结构，杜绝将 HTML 报错页或残损文件误判为成功。

## 让 Agent 帮你安装

把这句话发给 Claude Code、Codex 等 Agent：

```text
帮我安装这个 Skill：https://github.com/nengong/download-anything.git
```

**给 Agent 的安装步骤：**

已有同名目录或环境时，先检查并保留原有内容。

1. 克隆仓库到持久位置，例如 `~/.download-anything/source`。
2. 检查 Python 3.10+。缺少时先询问用户，再按安装脚本提示准备 Python；运行仓库中的 `python3 skills/download-anything/scripts/install.py`。用户已同意安装且需要非交互执行时可以加 `--yes`。默认安装位置为 `~/.download-anything/venv`。
3. 将仓库的 `skills/download-anything` **整个文件夹**复制或链接到当前 Agent 的用户级技能目录：Codex 为 `~/.agents/skills/download-anything`，Claude Code 为 `~/.claude/skills/download-anything`。其他 Agent 放进该 Agent 的 skills 目录，不确定就问用户。链接应指向持久位置；新开会话加载 Skill。
4. 运行 `~/.download-anything/venv/bin/da doctor --json`（Windows：`%USERPROFILE%\\.download-anything\\venv\\Scripts\\da.exe doctor --json`），确认 `all_required_ok` 为 `true`。`da` 不在 PATH 时使用完整路径。音视频任务缺 FFmpeg 时，告知用户并询问后再安装。

也可以用 `npx skills add nengong/download-anything` 选择 Agent 安装 Skill；它只负责安装 Skill，仍需运行 Skill 中的 `scripts/install.py` 安装 CLI 并执行自检。Node.js 要求见 [skills 项目](https://github.com/vercel-labs/skills)。

## 快速上手

每个主流场景一条命令，直接把 App 分享口令、链接、DOI、ISBN、包名/Product ID 或本地音频路径交给 `da`：

```bash
# 1. 视频、多图与实况（B站 / 抖音 / 小红书 / YouTube / X，自动识别视频或图集并提取封面/字幕/原声）
da "https://www.bilibili.com/video/BV1xx411c7mD" --json
da "复制打开抖音，看看【示例作品】https://v.douyin.com/iABC123/" --json
da "https://www.xiaohongshu.com/explore/654321abcdef" --json

# 2. 播客、音乐与本地加密音频（小宇宙 / Apple Podcasts / 网易云 .ncm 解密 / .flac 转 MP3）
da "https://www.xiaoyuzhoufm.com/episode/65f..." --json
da "/path/to/music.ncm" --json

# 3. 公众号、技术文章与 Obsidian 归档（正文转干净 Markdown，防盗链配图自动本地化）
da "https://mp.weixin.qq.com/s/..." --vault ~/Documents/MyVault --json

# 4. 学术论文与电子书（arXiv / DOI 论文自动生成 citation.bib；支持按 ISBN / MD5 下载电子书）
da "https://arxiv.org/abs/2310.06825" --json
da "9780141439518" --json

# 5. 网盘分享文件（自动识别百度/夸克网盘分享文本中的链接与提取码）
da "通过网盘分享的文件：资料包.zip 链接: https://pan.baidu.com/s/1xxxx 提取码: a1b2" --json

# 6. GitHub 单文件与应用安装包（GitHub 单文件直下 / 微软商店 Product ID / Android APK 包名）
da "https://github.com/psf/requests/blob/main/README.md" --json
da "9N0DX20HK701" --json
```

## 安装、升级与卸载

### 环境要求

- **Python**：`3.10` 或更高版本。安装脚本会优先查找本机已有的 Python 3.10+，未找到时可按提示通过 `uv` 准备独立的 Python 3.12（非交互环境加 `--yes`）。
- **FFmpeg（音视频组件）**：用于 `ffprobe` 媒体双轨结构校验、`ffmpeg` 抽轨与转码、HLS/DASH 流合并。

### 从源码或发布包安装

从源码目录或解压后的 Skill 发布包安装到独立虚拟环境（默认位于 `~/.download-anything/venv`）：

```bash
python3 skills/download-anything/scripts/install.py
~/.download-anything/venv/bin/da doctor --json
```

- **配置 PATH**：将 `~/.download-anything/venv/bin`（Windows 为 `%USERPROFILE%\.download-anything\venv\Scripts`）加入系统 `PATH` 后，即可直接调用 `da` 或 `dl`。
- **依赖源与镜像**：安装依赖和 `da doctor --fix` 默认优先连接官方 PyPI，超时后自动切换清华、阿里云镜像；也可通过 `DA_PIP_INDEX_URL` 指定自定义源。
- **升级或修复依赖**：重新运行 `install.py` 即可升级或重建环境（可通过 `--venv /自定义路径` 指定位置）；CLI 已安装时也可运行 `da doctor --fix --json` 自动补齐缺失的 Python 依赖。

### 卸载

删除安装时创建的虚拟环境目录（如 `~/.download-anything/venv`）并移除对应的 `PATH` 配置即可。`~/.download-anything/index.db`（缓存索引）、`~/.download-anything/credentials.yaml`（`0600` 权限凭据配置）及已下载文件可按需保留或手动清理。

### 凭据管理与无头环境（Headless）运行

对于需要登录凭据的平台（如百度网盘、夸克网盘），DA 支持多层次凭据解析：
- **无头环境 / Docker / CI**：可通过安全方式注入 `DA_<PLATFORM>_COOKIE` 或 `<PLATFORM>_COOKIE`（如 `DA_BAIDU_COOKIE`、`QUARK_COOKIE`），或挂载 `~/.download-anything/credentials.yaml`；自行预置的凭据文件应设置为 `0600`。Instagram 多图使用 `DA_INSTAGRAM_COOKIE_FILE` 指向授权 Cookie 文件。
- **桌面环境**：可直接运行 `da login <平台>` 从本机主流浏览器（Chrome/Arc/Edge/Safari 等）或桌面端客户端安全提取 Cookie。

## 工作机制与架构设计

<p align="center">
  <img src="./assets/readme/architecture.svg" width="100%" alt="Download Anything 四步工作流：口令与脏链接净化、多源按需提取、安全边界与完整性校验、结构化归档与知识同步">
</p>

DA 将一次提取任务拆解为四个可验证阶段：

1. **口令与脏链接净化（`core/router.py`）**：自动剔除分享文本中的推广词、数字口令与表情符号，提取标准 URL 与内嵌密码（`提取码` / `pwd`），并识别学术 DOI、ISBN 与 MD5。
2. **多源按需分发（`drivers/*`）**：按目标类型匹配专属驱动；同一社交平台（如小红书、抖音、X、微博、Instagram）自动识别视频、多图或实况图，无需手动指定模式。
3. **安全边界与文件完整性校验（`core/verifier.py` & `core/unpacker.py`）**：
   - 默认单文件下载上限 `500 MB`（可通过 `--max-mb N` 调整）。
   - 针对 PDF（`pypdf`）、EPUB、图片（`Pillow`）、压缩包（`zipfile`）执行格式检查；借助 `ffprobe` 扫描音视频轨道与可读数据包（`media-structure` 级别，统计有效音视频流数量与 `has_audio` 状态）。
   - 支持 `ZIP` / `TAR` 归档自动解压与路径边界检查（总量上限 `500 MB` / `10,000` 个成员），可通过 `--no-unzip` 保留原压缩包。
4. **结构化归档与知识库同步（`core/sidecar.py` & `core/vault_sync.py`）**：主文件落盘后按需生成 `.info.json`、Markdown 正文、`.srt` 字幕、`.lrc` 歌词或 `citation.bib`，支持同步至本地 Obsidian 知识库及云端 Whisper 语音转写（`--transcribe`），并通过 SQLite 本地索引（`~/.download-anything/index.db`）实现缓存复用。

## 支持的能力全景

完整输入输出规范见 [`skills/download-anything/references/platforms.md`](./skills/download-anything/references/platforms.md)。

### 1. 视频、图文与社交平台（单入口自动识别视频 / 多图 / 实况）

- **哔哩哔哩（B站）**：解析标准链接、移动端分享口令与 `b23.tv` 短链；下载声画同步 `.mp4`（加 `-a` 直接提取 `.m4a` 纯音轨）、高清封面 `cover.jpg` 及 UP 主互动数据，自动获取 CC / AI 字幕并转换为标准 `.srt` 时间轴字幕。
- **抖音（Douyin）**：解析 App 整段分享口令、`v.douyin.com` 短链与网页链接；自动识别**视频**（提取免水印最高 4K `.mp4` + 原画封面 `cover.jpg`）或**图文笔记**（按序下载全部无水印高清大图），同步提取独立 BGM/原声音轨 `audio.mp3` 与作品文案。
- **小红书（Xiaohongshu）**：解析网页链接与 App 分享口令（`xhslink.com` / `xhslink.cn`）；自动识别**视频笔记**（无水印 `.mp4`）、**多图笔记**（按原顺序下载全部高清 `.jpg`）或**实况图 LivePhoto**（同步提取每张图配套的 `.mov` 动态视频流），完整保留标题、正文与 `#话题标签`。
- **X (Twitter) / 微博 / Instagram**：同一入口自动识别**视频**（选轨合并高画质 `.mp4`）或**多图帖**（X `:orig` 原图、微博免登录九宫格大图、Instagram Carousel 多图），同步归档正文与作者信息。
- **YouTube / TikTok / 通用 HLS (`.m3u8`)**：自动选轨或分片并发拉取合并为声画同步 `.mp4`，保存封面与简介并通过 `ffprobe` 双轨校验。

### 2. 播客、音乐与本地音频转换

- **小宇宙 & Apple Podcasts**：下载单集原档音频（`.m4a` / `.mp3`）与高清封面，完整提取节目 Shownotes、简介与时间轴笔记。
- **网易云音乐 / Spotify / Apple Music**：公开曲目直接下载 `.mp3`、超清专辑封面（Apple Music 支持 `3000×3000`）与同步滚动歌词（`.lrc`）；受限曲目自动提取官方封面、歌词与元数据并通过公开音源匹配下载完整 `.mp3`。
- **本地加密与无损音频转换**：网易云 `.ncm` 本地解密还原为标准 `.mp3`（保留内嵌专辑封面与 ID3 标签）；无损 `.flac` 转换为标准 `320kbps` `.mp3`（保留原文件）。
- **云端语音转写（`--transcribe`）**：配置 `GROQ_API_KEY`、`OPENAI_API_KEY` 或 `SILICONFLOW_KEY` 后，可将播客或视频音轨（`-a --transcribe`）转写为带分段时间戳的 `.transcript.md` 文字稿。

### 3. 公众号、技术文章与知识库归档

- **微信公众号文章**：提取完整正文转换为干净 Markdown（`article.md`），自动绕过微信防盗链将全部插图下载至本地并重写为相对路径引用。
- **主流技术社区与专栏文章**：支持知乎、掘金、CSDN、博客园、Medium、Substack、少数派、简书、SegmentFault、开源中国、V2EX；剥离页面导航与广告噪声，将正文代码块与配图本地化归档。
- **Obsidian 知识库同步（`--vault`）**：将下载的 Markdown、本地化配图与配套元数据同步至本地 Obsidian Vault，自动注入标准 YAML frontmatter。

### 4. 学术论文与电子书

- **arXiv & DOI 开放获取论文**：支持 `arxiv.org/abs/...`、纯编号（如 `2310.06825`）或标准 DOI（如 `10.1186/...`）；下载经 `pypdf` 校验的全文 `.pdf`，提取标题、作者与摘要，自动生成标准 `citation.bib` 引用文件。
- **电子书（ISBN / MD5）**：直接输入 10/13 位 ISBN（如 `9780141439518`）或 32 位 MD5（或由 Agent 根据书名查出 ISBN / MD5 后传入），自动检索镜像下载 `.epub` / `.pdf` 并执行 OPF 清单、章节脊柱与资源完整性校验。

### 5. 网盘分享文件

- **百度网盘**：自动识别分享文本中的链接与 4 位提取码，支持 `--check` 预检文件大小（不触发云端转存），结合本机登录态下载分享原文件（ZIP / TAR 归档默认自动安全解压）。
- **夸克网盘**：自动读取本机登录态、递归查找分享子目录文件、转存至任务专属临时目录 `_da_temp_<uuid>`，下载完成后自动清理云端临时目录。

### 6. 代码单文件与应用安装包

- **GitHub 单文件**：支持 `github.com/<owner>/<repo>/blob/<branch>/<path>` 链接，免 `git clone` 整个仓库直接按指定分支或 Commit 逐字节拉取目标原文件。
- **微软商店离线包（Microsoft Store）**：输入商店链接或 12 位 Product ID（如 `9N0DX20HK701` Windows Terminal），借助第三方目录解析服务获取微软官方 CDN（`delivery.mp.microsoft.com`）上的 `.msixbundle` / `.appxbundle` 离线安装包与 PowerShell 安装说明（仅适用于提供标准 MSIX/Appx 离线包的免费应用，不支持付费应用或传统 Win32 `.exe` 安装器）。
- **安卓应用安装包（Android APK）**：输入 Google Play 链接、APKPure/Aptoide 链接或直接传入包名（如 `org.videolan.vlc`），从 F-Droid / Aptoide 公开镜像检索下载经结构校验的 `.apk` 安装包与 `adb install` 命令（版本取决于公开镜像收录情况）。

## 常用参数与自动化结果协议

详细 CLI 规范见 [`skills/download-anything/references/cli.md`](./skills/download-anything/references/cli.md)。

| `status` 字段 | 单任务退出码 | 含义 |
| :--- | :---: | :--- |
| `success` | `0` | 主文件通过完整性校验，配套附件及后续同步步骤均已完成 |
| `cached` | `0` | 命中本地缓存记录（`cached-existence`），直接复用已有文件 |
| `dry_run` | `0` | 完成 `--check` 元数据预检 |
| `partial` | `2` | 主文件已保存，部分配套附件、同步或临时目录清理未完成；详见 `warnings` 与 `operations` |
| `error` | `1` | 下载或主文件校验失败；详见 `error_type` 与 `message` |

- **批量任务退出码**：批量结果（`-i links.txt`）若包含 `partial` 项则返回 `2`；否则至少一项成功返回 `0`，全部失败返回 `1`。
- **校验级别**：`verification.details.level` 标识实际执行的检查级别（如音视频 `media-structure`，含 `stream_count` 与 `has_audio`；常规格式 `basic`；缓存复用 `cached-existence`）。

## 开发与打包

```bash
# 安装开发依赖
uv pip install -e '.[dev]'

# 运行单元测试与工程回归
.venv/bin/python -m pytest tests -q

# 构建 dist/ 下的 CLI wheel 与完整 Skill 发布 ZIP
python3 scripts/build_release.py
```

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。
