# Download Anything (DA)

> **全能微资产（<500MB）提取与离线沉淀中枢**  
> 极简轻量 · 零虚假成功 · 本地智能去重 · 知识库闭环 · 协同云文档 · 音乐解密转码 · Agent 优先

---

## 🎯 核心定位与设计原则

市面上的下载工具普遍存在“专攻单一媒体类型”、“忽略复杂风控生态”、“粗暴单文件落盘丢失元数据”等问题。`Download Anything` 聚焦于解决 **500MB 以内高信息密度资产的精准摄取与离线沉淀**，专为 AI Agent 和人类知识沉淀者打造。

1. **核心轻量，按需复用**：
   - 核心源码仅 **~750 KB**，**不需要打包分发几百兆甚至上 GB 的依赖**。
   - 运行时直接智能复用本机 Python 与既有依赖包；未安装时由 `da doctor --fix` 一键自动补齐。
2. **本地智能去重索引 (`AssetIndexDB`)**：
   - 内置轻量 SQLite 缓存（`~/.download-anything/index.db`），自动跟踪 `URL -> 校验和 -> 磁盘路径`。
   - 重复请求时 **5毫秒秒级命中缓存**，彻底杜绝重复下载与流量浪费。支持 `-f / --force` 强制覆盖。
3. **知识库下游闭环 (Obsidian & Notion)**：
   - 支持 `--vault <路径>` 或 `--obsidian`：一键自动将清洗后的 Markdown 笔记、高清插图及 YAML frontmatter 注入个人 Obsidian 知识库。
   - 支持 `--notion`：一键推送至指定 Notion Database。
4. **协同云文档与防盗脱壳**：
   - 支持抓取 **飞书公开云文档/Wiki (`feishu.cn`)**、**Notion 公开页面 (`notion.site`)** 以及微信公众号、知乎专栏，本地化插图并产出高密度 Markdown。
5. **极轻量云端语音转写挂钩 (`--transcribe`)**：
   - 绝不捆绑几 GB 的笨重本地模型，通过云端 Whisper 极速接口（Groq / OpenAI），数秒内将长音频转录为带精确时间轴的文字稿。
6. **音乐全生态与私有加密脱壳**：
   - 网易云免费直链、VIP 声学指纹检索对齐，同名伴生高清专辑封面与 `.lrc` 动态歌词。
   - Spotify 与 Apple Music 3000px 巨幅封面提取与标准 320kbps MP3 交付。
   - 本地客户端专有加密文件（`.ncm`）纯 Python 解密，FLAC/APE/WAV 批量转码。
7. **零虚假成功验收（Zero False-Positive Verification）**：拒绝“>10KB 即成功”，通过 `Content-Length` 比对与文件魔数（PDF EOF 签名、EPUB 容器、图片 PIL 检验、MP4 atom 检验、防 403 HTML 陷阱）严格自检。
8. **批量全家桶支持（Batch Engine, `-i links.txt`）**：支持批量并发下载与错误隔离，输出聚合成功率与标准 JSON 数组。
9. **静默原子闭环（Headless Automation）**：针对网盘小文件的强制转存限制，后台自动完成 `静默转存 ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动销毁网盘副本`，云端零垃圾。

---

## 🚀 快速上手

### 1. 基础下载与本地去重

```bash
# 正常下载（下载完成后自动加入本地索引库）
da "https://b23.tv/BV1xx411c7m9"

# 再次执行相同链接，立即触发本地缓存命中，秒级返回已有路径
da "https://b23.tv/BV1xx411c7m9"

# 强制重新下载（覆盖缓存）
da "https://b23.tv/BV1xx411c7m9" -f
```

### 2. 飞书云文档与 Notion 公开页面提取

```bash
# 抓取飞书公开云文档 / 知识库
da "https://bytedance.feishu.cn/docx/doxcn12345678"

# 抓取 Notion 公开页面
da "https://username.notion.site/My-Public-Guide-123456"
```

### 3. 闭环同步到 Obsidian / Notion 知识库

```bash
# 下载的同时自动将 Markdown 笔记与媒体同步至 Obsidian Vault 收件箱
da "https://music.163.com/#/song?id=33894312" --vault ~/Documents/Obsidian/Inbox

# 推送资产记录至 Notion Database
da "https://zhuanlan.zhihu.com/p/123456" --notion
```

### 4. 纯音频与极速语音转写

```bash
# 提取音轨并直接转写出带时间轴的文字稿 Markdown
da "https://b23.tv/BV1xx411c7m9" -a --transcribe
```

### 5. Agent Skill 模式（标准 JSON 输出）

```bash
da "<URL或文件路径>" --json
```

---

## 📦 驱动矩阵 (27 个模块化驱动)

- **协同文档与文章**：飞书云文档 (`feishu_doc`)、Notion 公开页 (`notion_public`)、万能网页文章 (`web_article`)、微信公众号 (`wechat`)
- **音乐与本地解密**：网易云音乐 (`music_163`)、Spotify & Apple Music (`spotify_apple`)、开源与公有领域音乐 (`open_music`)、本地加密与脏格式转码 (`local_audio`)
- **网盘微资产**：百度网盘 (`baidu`)、夸克网盘 (`quark`)、蓝奏云 (`lanzou`)
- **国内外社交媒体**：B站 (`bilibili`)、YouTube (`youtube`)、小红书 (`xiaohongshu`)、抖音 (`douyin`)、微博 (`weibo`)、Twitter/X (`twitter`)、Instagram (`instagram`)
- **播客音频**：小宇宙 (`xiaoyuzhou`)、Apple Podcasts (`apple_podcasts`)
- **学术与图书**：DOI 论文文献 (`doi`)、arXiv 预印本 (`arxiv`)、暗影图书馆/全本出版物 (`shadow_library`)、网络小说章节全本 (`novel`)
- **跨平台离线安装包**：微软商店原版离线安装包 (`ms_store`)、安卓官方 APK (`android_apk`)
- **开发者微资产**：GitHub 单目录/单文件精准提取 (`github`)
