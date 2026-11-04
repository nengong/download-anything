# Download Anything (DA)

> **全能微资产（<500MB）提取与离线沉淀中枢**  
> 轻量极速 · 零虚假成功 · 全要素伴生 · 多源驱动插拔 · 音乐解密转码 · Agent 优先

---

## 🎯 核心定位与原则

市面上的下载工具普遍存在“专攻单一媒体类型”、“忽略复杂风控生态”、“粗暴单文件落盘丢失元数据”等问题。`Download Anything` 聚焦于解决 **500MB 以内高信息密度资产的精准摄取与离线沉淀**，专为 AI Agent 和人类知识沉淀者打造。

1. **输入杂质免疫（Dirty Link Immune）**：平台分享文本（广告、换行、中文、口令、短链）自动剥离净化，提取码自动捕获。
2. **伴生资产全要素沉淀（Sidecar Metadata）**：下载主资产时，同名伴生标准元数据 JSON、正文 Markdown、高清封面及 CC 字幕（`.srt`）/ 动态歌词（`.lrc`）。
3. **音乐全生态与加密格式解锁**：
   - **国内音乐（网易云）**：免费直链秒下，VIP 独家歌曲自动声学指纹检索，同名伴生高清专辑封面与 `.lrc` 歌词。
   - **国外流媒体（Spotify / Apple Music）**：采用 SpotDL 架构，提取 3000×3000px 巨幅封面，音轨对齐输出 320kbps MP3。
   - **开源与公有领域音乐**：直接从 Free Music Archive、Internet Archive Audio、SoundCloud 提取 CC/PD 音频。
   - **客户端私有加密容器解密**：纯 Python 解密 `.ncm`，自动将各类本地音频格式（FLAC/APE/WAV）统一转码为标准 MP3。
4. **零虚假成功验收（Zero False-Positive Verification）**：拒绝“>10KB 即成功”，通过 `Content-Length` 比对与文件魔数（PDF EOF 签名、EPUB 容器、图片 PIL 检验、MP4 atom 检验、防 403 HTML 陷阱）严格自检。
5. **纯音频按需提取（Audio-First, `-a / --audio`）**：自动提取纯音频流（M4A/MP3），节省 80~90% 带宽与硬盘空间，专为 Agent 语音转写设计。
6. **带密码压缩包智能解压（Safe Unpacker, `--unzip`）**：全自动利用解析出的口令解压归档，内置 Zip-Slip 目录防逃逸保护与系统工具回退。
7. **批量全家桶支持（Batch Engine, `-i links.txt`）**：支持批量并发下载与错误隔离，输出聚合成功率与标准 JSON 数组。
8. **静默原子闭环（Headless Automation）**：针对网盘小文件的强制转存限制，后台自动完成 `静默转存 ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动销毁网盘副本`，云端零垃圾。
9. **国内镜像透明故障自愈（Domestic Mirror Failover）**：针对 GitHub、arXiv、HuggingFace、LibGen 等境外资源，网络不通时自动透明无缝切换国内高速镜像。
10. **环境自愈体检中心（`da doctor`）**：一键检测 Python 运行时、依赖包、系统工具并提供 `--fix` 自动自愈修复。

---

## 🚀 快速上手

### 1. 音乐下载与格式解锁

```bash
# 1. 网易云音乐单曲（自动拉取 320k MP3 + 封面 + 同步 .lrc 歌词）
da "https://music.163.com/#/song?id=33894312"

# 2. Apple Music 单曲/专辑（带 3000x3000px 视网膜高清封面）
da "https://music.apple.com/us/album/after-hours/1499378108?i=1499378607"

# 3. Spotify 单曲
da "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"

# 4. 解密本地网易云客户端缓存加密文件 (.ncm)
da "/Users/c.k/Music/favorite_song.ncm"
```

### 2. 基础综合下载

```bash
# 1. 视频 / 社交动态下载
da "https://b23.tv/BV1xx411c7m9"

# 2. 只要音频（如播客、长视频演讲提取）
da "https://b23.tv/BV1xx411c7m9" -a

# 3. 微软商店安装包 / 安卓 APK 提取
da "https://apps.microsoft.com/detail/9nt1r1c2hh7j"
da "com.termux"

# 4. 批量全家桶下载
da -i links.txt
```

### 3. Agent Skill 模式（标准 JSON 输出）

```bash
da "<URL或文件路径>" --json
```

---

## 📦 驱动矩阵 (25 个模块化驱动)

- **音乐与本地解密**：网易云音乐 (`music_163`)、Spotify & Apple Music (`spotify_apple`)、开源与公有领域音乐 (`open_music`)、本地加密与脏格式转码 (`local_audio`)
- **网盘微资产**：百度网盘 (`baidu`)、夸克网盘 (`quark`)、蓝奏云 (`lanzou`)
- **国内外社交媒体**：B站 (`bilibili`)、YouTube (`youtube`)、小红书 (`xiaohongshu`)、抖音 (`douyin`)、微博 (`weibo`)、Twitter/X (`twitter`)、Instagram (`instagram`)
- **播客音频**：小宇宙 (`xiaoyuzhou`)、Apple Podcasts (`apple_podcasts`)
- **学术与图书**：DOI 论文文献 (`doi`)、arXiv 预印本 (`arxiv`)、暗影图书馆/全本出版物 (`shadow_library`)、网络小说章节全本 (`novel`)
- **文章与文档防盗**：万能网页文章剥离 (`web_article`)、微信公众号 (`wechat`)
- **跨平台离线安装包**：微软商店原版离线安装包 (`ms_store`)、安卓官方 APK (`android_apk`)
- **开发者微资产**：GitHub 单目录/单文件精准提取 (`github`)
