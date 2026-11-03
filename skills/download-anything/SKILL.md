---
name: download-anything
description: Universal micro-asset (<500MB) extraction and offline archiving hub. Use when downloading books, papers/DOIs, unwatermarked videos/images (Xiaohongshu, Douyin, Bilibili, YouTube, Twitter/X, Instagram, Weibo), cloud drives (Baidu, Quark, Lanzou), podcasts (Xiaoyuzhou, Apple Podcasts), novels, web articles to clean Markdown, Microsoft Store (.msixbundle) or Android (.apk) offline packages, with full metadata sidecars, auto-unzip, audio-only extraction, and zero false-positive verification.
---

# Download Anything (DA)

CLI 命令行入口：`/Users/c.k/Documents/download-anything/bin/da`（全局软链命令：`da` 或 `dl`）。

## 1. 核心定位与设计哲学

专为人类创作者与 AI Agent 打造的 **500MB 以内高信息密度微资产提取与离线沉淀中枢**。
- **输入杂质免疫**：支持整段投喂移动端混合分享口令（包含广告文字、换行、提取码）。
- **智能语义重命名**：主文件自动基于提取到的标题重命名（如 `斯多亚哲学的极简日常实践.mp4`），杜绝一堆纯数字或无意义哈希。
- **全要素资产伴生**：主资产落盘的同时，同名伴生高清封面、字幕、`[标题].md` 正文文案与 `[标题].info.json`（Schema 1.0 机器可读标准）。
- **零虚假成功验收**：通过 `Verifier` 严格执行 `Content-Length` 比对与文件魔数深度校验（PDF EOF、EPUB 容器、图片 PIL 检验、MP4 atom 检验、防 403 HTML 陷阱）。
- **纯音频按需提取 (`-a / --audio`)**：音视频平台自动提取纯音频流（M4A/MP3），节省 80~90% 存储与带宽，专为 Agent 转写与人类收听设计。
- **带密码压缩包智能解压 (`--unzip`)**：下载完成后自动提取分享口令中解析出的密码进行解压，自带 Zip-Slip 路径防逃逸保护与系统工具透明回退。
- **批量全家桶支持 (`-i links.txt` 或多参数)**：一键批量并发提取多条资产，聚合报告成功率与标准 JSON 数组。
- **静默原子闭环**：百度网盘与夸克网盘后台实现 `静默转存 ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动销毁网盘临时副本`，云端零垃圾。
- **双模输出**：人类模式（彩色进度条与状态卡片）vs. Agent 模式（`--json` 标准 stdout 输出）。

---

## 2. Agent 启动规范：前置环境检查与小白依赖安装指引

当 Agent 在新环境中使用本 Skill 时，**必须优先执行环境健康自检**，并在必要时主动引导用户确认安装。

### 步骤一：环境自检 (Pre-flight Doctor Check)

执行诊断命令：
```bash
da doctor --json
```

核心检查清单：
- **Python Runtime**：>= 3.10
- **核心依赖包**：`requests`, `rich`, `click`, `pyyaml`, `beautifulsoup4`, `pillow`, `pypdf`, `cryptography`, `rookiepy`, `yt-dlp`
- **系统辅助工具**：`curl` (底层网络兜底), `ffmpeg` (音视频无损提取与合并)

### 步骤二：发现依赖缺失时的主动交互引导

如果发现核心依赖缺失（`all_required_ok == false`），**切勿直接报错崩溃**。Agent 应主动向用户说明：
> "检测到使用 Download Anything 需要安装 Python 基础依赖（用于音视频解析、图片魔数检测与浏览器 Cookie 读取）。是否需要我为你一键安装？"

并调用 `ask_question` 提供安装选项：
1. `(Recommended) 自动帮我安装全部依赖 (uv pip install / pip)`
2. `我稍后手动安装`

### 步骤三：标准一键修复命令

用户同意后，直接运行一键修复指令：
```bash
da doctor --fix
# 或直接通过 uv / pip 安装
uv pip install -e /Users/c.k/Documents/download-anything
```

---

## 3. 智能落盘目录与文件命名规范

### 3.1 跨平台落盘目录优先级 (Directory Hierarchy)
引擎采用成熟的智能分层决策，绝不胡乱建文件夹：
1. **显式指定**：用户传入 `-o / --output-dir <path>` 优先使用指定路径。
2. **工作区语义感知 (Workspace Sensing)**：
   若当前运行在开发项目内（检测到 `.git`, `pyproject.toml`, `package.json` 等）：
   - 自动嗅探工作区中已存在的微资产目录：`downloads/`、`data/`、`assets/`、`media/`。
   - 优先直接落盘到项目既有的下载文件夹中！
3. **系统原生下载目录回退 (OS Native Fallback)**：
   脱离开发工作区时，自动落盘到系统官方下载目录：
   - **macOS**: `~/Downloads/DownloadAnything/[YYYY-MM-DD]_[标题]/`
   - **Windows**: `%USERPROFILE%\Downloads\DownloadAnything\[YYYY-MM-DD]_[标题]\`
   - **Linux**: `$XDG_DOWNLOAD_DIR/DownloadAnything/[YYYY-MM-DD]_[标题]/`

### 3.2 智能重命名规范
拒绝把视频或电子书保存为 `173829103948.mp4` 或 `content.mp4`：
- **主资产**：自动重命名为 `{清洗后的标题}.{ext}`（例如 `斯多亚哲学的极简日常实践.mp4`）。
- **纯音频资产**：`{清洗后的标题}.m4a` 或 `.mp3`。
- **高清封面**：`{清洗后的标题}.cover.jpg`。
- **伴生字幕**：`{清洗后的标题}.subtitle.srt`。
- **双模元数据**：同目录下同时生成 `{清洗后的标题}.info.json` 与 `content.info.json`，确保人类看文件名一目了然，Agent 自动化索引 100% 确定。

---

## 4. Agent 常用调用方式

### 4.1 标准 Agent 调用（JSON 输出，推荐）

```bash
da "<任意URL或口令>" --json
```

标准输出格式：
```json
{
  "status": "success",
  "platform": "xiaohongshu",
  "title": "斯多亚哲学的极简日常实践",
  "output_dir": "/Users/c.k/Downloads/DownloadAnything/2026-11-04_斯多亚哲学的极简日常实践",
  "primary_asset": "/Users/c.k/Downloads/DownloadAnything/2026-11-04_斯多亚哲学的极简日常实践/斯多亚哲学的极简日常实践.mp4",
  "size_bytes": 14105823,
  "sidecars": {
    "info_json": ".../content.info.json",
    "markdown": ".../content.md",
    "cover": ".../斯多亚哲学的极简日常实践.cover.jpg"
  },
  "extracted_files": [],
  "verification": {
    "valid": true,
    "detected_type": "video/mp4"
  }
}
```

### 4.2 纯音频提取模式 (`-a / --audio`)

对于长视频、访谈或演讲，如果用户仅需收听或输入给大模型做语音转写：
```bash
da "<视频URL>" -a --json
```
自动跳过视频高码率轨道，直接下载或无损转码为纯音频 `.m4a` / `.mp3`。

### 4.3 批量全家桶下载 (`-i links.txt` 或多参数)

```bash
# 从文本文件批量读取（每行一个链接或分享口令）
da -i links.txt --json

# 或直接传入多个链接
da "https://b23.tv/xxx" "com.termux" "10.1038/nature12373" --json
```
返回聚合 JSON：
```json
{
  "batch": true,
  "total": 3,
  "success_count": 3,
  "results": [...]
}
```

### 4.4 预检模式（Dry-Run）

在不实际下载大文件的前提下，探测直链与元数据大小：
```bash
da "<任意URL或口令>" --check --json
```

### 4.5 凭据一键捕获（针对网盘平台）

```bash
da login baidu     # 自动检测本地客户端/浏览器凭据，若无则拉起轻量登录窗口捕获
da login quark     # 夸克网盘凭据一键捕获
```

---

## 5. 全平台驱动矩阵覆盖一览 (共 21 个专属驱动)

| 资产分类 | 驱动名 | 支持特征与输入示例 | 交付产物与标准 |
| :--- | :--- | :--- | :--- |
| **网盘微资产** | `baidu` | `pan.baidu.com/s/1xxxx` (含提取码) | 静默转存至云端 `/_da_temp/` ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动删除云端副本 |
| | `quark` | `pan.quark.cn/s/xxxx` (含提取码) | 后台 API 静默转存下载闭环，云端零垃圾 |
| | `lanzou` | `pan.lanzou*.com/xxxx`, `wwx.lanzoup.com` | 免登录逆向 `ajaxm.php`，1秒提取 CDN 直链 |
| **国内外社交媒体** | `youtube` | `youtube.com/watch?v=...`, `youtu.be/...`, `shorts/...` | 500MB 以内最高画质 MP4 + 高清封面 + 官方/自动双语字幕（`.vtt`/`.srt`），支持 `-a` 纯音频 |
| | `twitter` | `twitter.com/.../status/...`, `x.com/...` | 单条推文视频、多图集、博主正文纯净 Markdown |
| | `instagram` | `instagram.com/p/...`, `reel/...` | Reels 视频、多图轮播（Carousel）、文案伴生 |
| | `weibo` | `weibo.com/...`, `m.weibo.cn/detail/...` | 无水印 MP4 / 九宫格大图 / LivePhoto 实况双文件 / 访客免登正文 |
| | `xiaohongshu`| `xhslink.cn/...`, `xiaohongshu.com/...` | 无水印大图 / LivePhoto (`.mov` + `.jpg`) / 原画视频 + 笔记正文与标签 |
| | `douyin` | `v.douyin.com/...`, `douyin.com/...` | 1080p 无水印 MP4 + 官方高清封面 + 伴生原声音轨 |
| | `bilibili` | `b23.tv/...`, `bilibili.com/video/BV...` | 原画视频 / DASH 原生音频 (`-a`) + 头图 + CC 伴生字幕转 `.srt` |
| **播客音频** | `apple_podcasts` | `podcasts.apple.com/.../id12345?i=67890` | 原声母带 MP3/M4A 音频 + 600x600 封面 + 完整 Shownotes Markdown |
| | `xiaoyuzhou` | `xiaoyuzhoufm.com/episode/...` | 高音质播客音频 + 时间戳与 Shownotes Markdown |
| **电子书与学术** | `doi` | `10.xxxx/...`, `doi.org/10.xxxx/...` | 自动 Crossref 元数据解析 + 官方 BibTeX 引用项 + OpenAccess/Sci-Hub PDF |
| | `shadow_library` | MD5 哈希、`annas-archive.*`, `libgen.*` | 全本中文出版书/网络小说/外文专著，国内镜像轮换加速 |
| | `novel` | 笔趣阁/69书吧等小说目录页 | 自动解析目录、并发抓取章节、过滤广告并汇编为结构化小说 |
| | `arxiv` | `arxiv.org/abs/...`, `arxiv.org/pdf/...` | 论文 PDF + 官方 BibTeX 伴生项 + `cn.arxiv.org` 国内镜像透明加速 |
| **万能文章防盗** | `web_article` | 知乎、掘金、CSDN、Medium、Substack、博客园等 | 剥离防盗脚本与侧边广告，自动下载文章插图到本地，产出纯净 GFM Markdown |
| | `wechat` | `mp.weixin.qq.com/s/...` | 微信公众号正文纯净 Markdown + 图片本地化防外链失效 |
| **跨系统离线安装包** | `ms_store` | `apps.microsoft.com/detail/...` (微软商店链接/PID) | 提取官方原版受信任 `.msixbundle` / `.appxbundle` 离线安装包，附带 1 键 PowerShell 安装命令 |
| | `android_apk` | `com.termux`, `play.google.com/...`, `org.videolan.vlc` | 免 Google Play 登录，从 F-Droid 与官方镜像提取官方 `.apk`，附带 ADB 安装指令 |
| **代码与开发** | `github` | `github.com/{owner}/{repo}/(tree\|blob)/...` | 单目录/单文件精准抓取，免全量 `git clone`，附带 `gh-proxy` 国内镜像 |
