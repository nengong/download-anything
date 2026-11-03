---
name: download-anything
description: Universal micro-asset (<500MB) extraction and offline archiving hub. Use when the user wants to download books, unwatermarked videos/images (Xiaohongshu, Douyin, Bilibili), cloud drive files (Lanzou, Quark), podcasts (Xiaoyuzhou), or WeChat articles with full metadata and format self-verification.
---

# Download Anything (DA)

CLI 命令行入口：`/Users/c.k/Documents/download-anything/bin/da`（软链命令：`da` 或 `dl`）。

## 核心定位与原则

专为人类与 AI Agent 打造的 **500MB 以内高信息密度微资产提取与离线沉淀中枢**。
- **输入杂质免疫**：支持整段投喂移动端混合分享口令（包含中文、广告、换行、提取码）。
- **全要素资产伴生**：下载主资产的同时，伴生 `content.info.json`（机器可读 Schema 1.0）与 `content.md`（人类可读排版）、高清封面图、字幕。
- **零虚假成功验收**：通过 `Verifier` 严格执行 `Content-Length` 比对与文件魔数深度校验（PDF EOF、EPUB 容器、图片 PIL 检验、MP4 atom 检验、防 403 HTML 陷阱）。
- **双模输出**：默认 Human CLI 彩色状态卡，带 `--json` 输出 Agent 专用的结构化绝对路径摘要。

---

## 常用调用方式

### 1. Agent 专用调用（推荐，标准 JSON 输出）

```bash
/Users/c.k/Documents/download-anything/bin/da "<任意URL或口令>" --json
```

输出标准结构：
```json
{
  "status": "success",
  "platform": "xiaohongshu",
  "title": "资产标题",
  "output_dir": "/absolute/path/to/dir",
  "primary_asset": "/absolute/path/to/content.mp4",
  "size_bytes": 14105823,
  "sidecars": {
    "info_json": "/absolute/path/to/content.info.json",
    "markdown": "/absolute/path/to/content.md",
    "cover": "/absolute/path/to/cover.jpg"
  },
  "verification": {
    "valid": true,
    "detected_type": "video/mp4"
  }
}
```

### 2. 指定输出目录

```bash
/Users/c.k/Documents/download-anything/bin/da "<任意URL或口令>" -o "/自定义/绝对路径" --json
```

### 3. Dry-Run 预检探测（不实际下载大文件）

```bash
/Users/c.k/Documents/download-anything/bin/da "<任意URL或口令>" --check --json
```

---

## 平台覆盖矩阵

| 平台分类 | 驱动名称 | 支持输入特征 | 交付产物与标准 |
| :--- | :--- | :--- | :--- |
| **社交媒体** | `xiaohongshu` | `xhslink.com`, `xhslink.cn`, `xiaohongshu.com` | 无水印原图集 / LivePhoto (`.mov` + `.jpg`) / 原画视频 + 文案伴生 |
| | `douyin` | `v.douyin.com`, `douyin.com/video/` | 1080p 无水印 MP4 + 官方高清封面 + 伴生原声音轨 |
| | `bilibili` | `b23.tv`, `bilibili.com/video/BV...` | 原画视频 + 头图 + CC 伴生字幕转 `.srt` |
| **网盘微资产** | `lanzou` | `lanzou*.com`, `wwx.lanzoup.com` (含密码) | 免登录纯 HTTP 逆向 `ajaxm.php`，1秒提取 CDN 直链落盘 |
| | `quark` | `pan.quark.cn/s/` (含提取码) | 后台 API 静默转存至 `/_da_temp/` ➔ 提取高速直链 ➔ 本地落盘 ➔ 自动销毁网盘副本 |
| **图书文献** | `shadow_library` | MD5 哈希、`annas-archive.*`, `libgen.*` | 动态 Token 自动续期，自适应断点续传，彻底杜绝 60 秒硬超时截断 |
| **图文与播客** | `wechat` | `mp.weixin.qq.com/s/...` | 微信公众号防盗链图文转纯净 Markdown，自动下载全部内嵌插图至本地 |
| | `xiaoyuzhou` | `xiaoyuzhoufm.com/episode/...` | 高音质播客音频 (`.m4a` / `.mp3`) + 高清封面 + 完整 Shownotes 结构化 Markdown |
| **开发设计** | `github` | `github.com/{owner}/{repo}/(tree\|blob)/...` | 单子目录或单文件精确抓取，避免无谓的完整 `git clone` |
