---
name: download-anything
description: Universal micro-asset (<500MB) extraction and offline archiving hub. Use when downloading books, papers/DOIs, unwatermarked videos/images (Xiaohongshu, Douyin, Bilibili, YouTube, Twitter/X, Instagram, Weibo), music (NetEase Cloud Music, Spotify, Apple Music, Open/CC audio), cloud docs (Feishu/Lark docs, Notion public pages, WeChat articles), proprietary formats (NCM decrypting), podcasts, with automatic local deduplication, Obsidian vault sync, cloud Whisper transcription, and zero false-positive verification.
---

# Download Anything (DA)

CLI 命令行入口：`/Users/c.k/Documents/download-anything/bin/da`（全局软链命令：`da` 或 `dl`）。

## 1. 核心定位与极简设计哲学

专为人类创作者与 AI Agent 打造的 **500MB 以内高信息密度微资产提取与离线沉淀中枢**。
- **极度轻量，按需复用**：
  - 核心源码**不到 1 MB**（约 750KB），**绝不捆绑几 GB 的臃肿 AI 模型权重**。
  - **无需自带打包 `.venv`**：DA 优先自动复用本机或 Python 宿主环境既有的依赖包，零侵入、零冗余。
- **本地去重索引库 (`AssetIndexDB`)**：
  - 基于 Python 原生标准库 SQLite，自动记录 `URL -> SHA256 -> 本地路径`（`~/.download-anything/index.db`）。
  - 重复投喂同一链接时 **5 毫秒内命中缓存直接返回**，不消耗网络带宽。支持 `-f / --force` 强制刷新。
- **个人知识库闭环 (Obsidian & Notion Vault)**：
  - 支持 `--vault <路径>` 或 `--obsidian`：一键自动将生成的 Markdown 笔记、高清封面与媒体注入用户的 Obsidian Vault，自动补全 YAML frontmatter（含来源、标签、日期）。
  - 支持 `--notion`：一键推送到用户的个人 Notion Database。
- **极轻量云端语音转写挂钩 (`--transcribe`)**：
  - 采用轻量 API 钩子（支持 Groq / OpenAI / 硅基流动 Whisper）。
  - 云端大模型转写质量远超本地轻量 CPU 模型，2秒完成播客或演讲全文转写并生成 `[标题].transcript.md`。
- **输入杂质免疫**：支持整段投喂移动端混合分享口令（包含广告文字、换行、提取码）。
- **全要素资产伴生**：主资产落盘的同时，同名伴生高清封面、字幕/歌词（`.srt` / `.lrc`）、`[标题].md` 正文文案与 `[标题].info.json`（Schema 1.0 机器可读标准）。
- **零虚假成功验收**：通过 `Verifier` 严格执行 `Content-Length` 比对与文件魔数深度校验（PDF EOF、EPUB 容器、图片 PIL 检验、MP4 atom 检验、防 403 HTML 陷阱）。

---

## 2. 依赖环境与小白自愈说明（关于环境是否必须带）

> [!NOTE]
> **运行环境必须打包附带吗？**
> **完全不需要！** 
> 1. 本工程在 Git 中已严格忽略 `.venv`，Skill 交付物仅为 pure-Python 代码（<1MB）。
> 2. `da` 会直接检测用户系统现有的 Python 环境。若用户本机已有 `requests`, `rich` 等，直接就地运行，**不强占任何额外磁盘**。
> 3. 若发现缺失依赖，通过 `da doctor --fix` 一键由 pip/uv 快速安装补齐。

---

## 3. 常用命令速查

### 3.1 基础与去重命令
```bash
# 1. 正常下载（自动索引并去重）
da "https://b23.tv/BV1xx411c7m9"

# 2. 命中本地缓存后，如需强制重新下载：追加 -f
da "https://b23.tv/BV1xx411c7m9" -f
```

### 3.2 协同云文档抓取（飞书公开文档、Notion 公开页）
```bash
# 抓取飞书公开云文档 / Wiki 并本地化插图产出 Markdown
da "https://bytedance.feishu.cn/docx/doxcn12345678"

# 抓取 Notion 公开页面并本地化图片
da "https://username.notion.site/My-Public-Guide-123456"
```

### 3.3 知识库直通与双链闭环（Obsidian & Notion）
```bash
# 下载的同时自动将 Markdown、封面与 frontmatter 写入指定 Obsidian 知识库
da "https://music.163.com/#/song?id=33894312" --vault ~/Documents/Obsidian/Inbox

# 推送资产记录至 Notion Database
da "https://zhuanlan.zhihu.com/p/123456" --notion
```

### 3.4 纯音频与极速语音转写
```bash
# 提取音轨并直接通过云端 Whisper 转写为全文稿
da "https://b23.tv/BV1xx411c7m9" -a --transcribe
```

### 3.5 批量全家桶与 Agent JSON
```bash
da -i links.txt --json
```

---

## 4. 全平台驱动矩阵覆盖一览 (共 27 个专属驱动)

| 资产分类 | 驱动名 | 支持特征与输入示例 | 交付产物与标准 |
| :--- | :--- | :--- | :--- |
| **协同文档与文章** | `feishu_doc` | `feishu.cn/docx/...`, `larksuite.com/wiki/...` | 剥离 Web App 骨架，本地化插图，产出纯净 GFM Markdown |
| | `notion_public` | `notion.so/...`, `notion.site/...` | 提取 Notion 公开页面全文与插图，转为结构化 Markdown |
| | `web_article` | 知乎、掘金、CSDN、Medium、Substack、博客园等 | 剥离防盗脚本与侧边广告，自动下载插图，产出 Markdown |
| | `wechat` | `mp.weixin.qq.com/s/...` | 微信公众号正文纯净 Markdown + 图片本地化防外链失效 |
| **音乐与解密** | `music_163` | `music.163.com/song?id=...`, `163cn.tv/...` | 320kbps MP3 + 原版封面图 + 逐句时间轴 `.lrc` 歌词 |
| | `spotify_apple` | `open.spotify.com/track/...`, `music.apple.com/...` | SpotDL 架构：3000×3000 视网膜封面 + 官方音轨对齐 320kbps MP3 |
| | `open_music` | `archive.org/details/...`, `soundcloud.com/...` | 公有领域/CC 授权 MP3 + 创作者版权声明 Markdown |
| | `local_audio` | 本地 `.ncm`、`.flac`、`.ape`、`.wav` 文件路径 | 纯 Python 解密 NCM 容器，自动转码为标准 320k MP3 并抽取内嵌封面 |
| | `apple_podcasts` | `podcasts.apple.com/.../id12345?i=67890` | 原声母带 MP3/M4A 音频 + 600x600 封面 + 完整 Shownotes Markdown |
| | `xiaoyuzhou` | `xiaoyuzhoufm.com/episode/...` | 高音质播客音频 + 时间戳与 Shownotes Markdown |
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
| **电子书与学术** | `doi` | `10.xxxx/...`, `doi.org/10.xxxx/...` | 自动 Crossref 元数据解析 + 官方 BibTeX 引用项 + OpenAccess/Sci-Hub PDF |
| | `shadow_library` | MD5 哈希、`annas-archive.*`, `libgen.*` | 全本中文出版书/网络小说/外文专著，国内镜像轮换加速 |
| | `novel` | 笔趣阁/69书吧等小说目录页 | 自动解析目录、并发抓取章节、过滤广告并汇编为结构化小说 |
| | `arxiv` | `arxiv.org/abs/...`, `arxiv.org/pdf/...` | 论文 PDF + 官方 BibTeX 伴生项 + `cn.arxiv.org` 国内镜像透明加速 |
| **跨系统离线安装包**| `ms_store` | `apps.microsoft.com/detail/...` (微软商店链接/PID) | 提取官方原版受信任 `.msixbundle` / `.appxbundle` 离线安装包，附带 1 键 PowerShell 安装命令 |
| | `android_apk` | `com.termux`, `play.google.com/...`, `org.videolan.vlc` | 免 Google Play 登录，从 F-Droid 与官方镜像提取官方 `.apk`，附带 ADB 安装指令 |
| **代码与开发** | `github` | `github.com/{owner}/{repo}/(tree\|blob)/...` | 单目录/单文件精准抓取，免全量 `git clone`，附带 `gh-proxy` 国内镜像 |
