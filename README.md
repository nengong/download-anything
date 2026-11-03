# Download Anything (DA)

> **全能微资产（<500MB）提取与离线沉淀中枢**  
> 轻量极速 · 零虚假成功 · 全要素伴生 · 多源驱动插拔 · Agent 优先

---

## 🎯 核心定位与原则

市面上的下载工具普遍存在“专攻单一媒体类型”、“忽略复杂风控生态”、“粗暴单文件落盘丢失元数据”等问题。`Download Anything` 聚焦于解决 **500MB 以内高信息密度资产的精准摄取与离线沉淀**，专为 AI Agent 和人类知识沉淀者打造。

1. **输入杂质免疫（Dirty Link Immune）**：平台分享文本（广告、换行、中文、口令、短链）自动剥离净化，提取码自动捕获。
2. **伴生资产全要素沉淀（Sidecar Metadata）**：下载主资产时，同名伴生标准元数据 JSON、正文 Markdown、高清封面及 CC 字幕（`.srt`）。
3. **零虚假成功验收（Zero False-Positive Verification）**：拒绝“>10KB 即成功”，通过 `Content-Length` 比对与文件魔数（PDF EOF 签名、EPUB 容器、图片 PIL 检验、MP4 atom 检验、防 403 HTML 陷阱）严格自检。
4. **纯音频按需提取（Audio-First, `-a / --audio`）**：自动提取纯音频流（M4A/MP3），节省 80~90% 带宽与硬盘空间，专为 Agent 语音转写设计。
5. **带密码压缩包智能解压（Safe Unpacker, `--unzip`）**：全自动利用解析出的口令解压归档，内置 Zip-Slip 目录防逃逸保护与系统工具回退。
6. **批量全家桶支持（Batch Engine, `-i links.txt`）**：支持批量并发下载与错误隔离，输出聚合成功率与标准 JSON 数组。
7. **静默原子闭环（Headless Automation）**：针对网盘小文件的强制转存限制，后台自动完成 `静默转存 ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动销毁网盘副本`，云端零垃圾。
8. **国内镜像透明故障自愈（Domestic Mirror Failover）**：针对 GitHub、arXiv、HuggingFace、LibGen 等境外资源，网络不通时自动透明无缝切换国内高速镜像。
9. **环境自愈体检中心（`da doctor`）**：一键检测 Python 运行时、依赖包、系统工具并提供 `--fix` 自动自愈修复。
10. **双模输出（Dual-Mode Interface）**：
    - **人类模式（Human CLI）**：Rich 彩色状态卡、分块流式进度条。
    - **Agent 模式（Agent Skill JSON）**：带 `--json` 标志，向 stdout 输出标准资产 JSON 格式。

---

## 🚀 快速上手

### 1. 环境体检与依赖自检

```bash
# 执行自检诊断
da doctor

# 自动修复缺失的依赖
da doctor --fix
```

### 2. 基础下载命令

```bash
# 1. 任意复杂文本或链接下载（自动语义重命名与伴生落盘）
da "https://b23.tv/BV1xx411c7m9"

# 2. 只要音频（如讲座、播客、视频原声），极速提取 M4A/MP3
da "https://b23.tv/BV1xx411c7m9" -a

# 3. 批量全家桶下载
da -i links.txt

# 4. 微软商店离线包 / 安卓 APK 提取
da "https://apps.microsoft.com/detail/9nt1r1c2hh7j"
da "com.termux"
```

### 3. Agent Skill 模式（标准 JSON 输出）

```bash
da "<URL>" --json
```

---

## 📦 驱动矩阵 (21 个模块化驱动)

- **网盘微资产**：百度网盘 (`baidu`)、夸克网盘 (`quark`)、蓝奏云 (`lanzou`)
- **国内外社交媒体**：B站 (`bilibili`)、YouTube (`youtube`)、小红书 (`xiaohongshu`)、抖音 (`douyin`)、微博 (`weibo`)、Twitter/X (`twitter`)、Instagram (`instagram`)
- **播客音频**：小宇宙 (`xiaoyuzhou`)、Apple Podcasts (`apple_podcasts`)
- **学术与图书**：DOI 论文文献 (`doi`)、arXiv 预印本 (`arxiv`)、暗影图书馆/全本出版物 (`shadow_library`)、网络小说章节全本 (`novel`)
- **文章与文档防盗**：万能网页文章剥离 (`web_article`)、微信公众号 (`wechat`)
- **跨平台离线安装包**：微软商店原版离线安装包 (`ms_store`)、安卓官方 APK (`android_apk`)
- **开发者微资产**：GitHub 单目录/单文件精准提取 (`github`)
