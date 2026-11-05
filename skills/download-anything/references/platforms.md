# 支持的平台与能力分级清单

本清单按 **内容形态（一级） → 目标平台（二级） → 具体交付能力与产物（三级）** 组织。命令行参数与 JSON 结构见 [cli.md](cli.md)。

## 1. 视频下载

- **哔哩哔哩（B站）**
  - **支持输入**：标准视频链接（`bilibili.com/video/BV...`）、移动端分享文本、`b23.tv` 短链
  - **交付产物**：声画同步 `.mp4` 视频、高清封面 `cover.jpg`、`.srt` 标准时间轴字幕（自动转换 CC / AI 字幕）
  - **附加能力**：支持 `-a` 直接提取独立 `.m4a` 纯音轨；伴生文件记录 UP 主、播放/点赞/投币/收藏等数据
- **小红书（视频笔记）**
  - **支持输入**：笔记详情链接、App 分享文本与 `xhslink.com` / `xhslink.cn` 短链
  - **交付产物**：`.mp4` 视频、`cover.jpg` 封面、包含完整标题与正文及 `#话题标签` 的伴生 Markdown
- **YouTube**
  - **支持输入**：`youtube.com/watch?v=...`、`youtu.be/...`、`youtube.com/shorts/...`
  - **交付产物**：自动选轨合并的声画同步 `.mp4` 视频、`cover.jpg` 封面、频道与简介元数据
- **X (Twitter)**
  - **支持输入**：`x.com/<user>/status/<id>` 或 `twitter.com` 推文链接
  - **交付产物**：自动选轨合并的高画质 `.mp4` 视频、`cover.jpg` 封面、推文正文与互动计数
- **微博（视频微博）**
  - **支持输入**：`weibo.com` / `m.weibo.cn` 状态链接（支持自动生成访客会话免登录提取）
  - **交付产物**：声画同步 `.mp4` 视频、微博正文 Markdown 与作者信息
- **Instagram Reels**
  - **支持输入**：`instagram.com/reel/...`、`instagram.com/p/...` 视频链接
  - **交付产物**：自动选轨合并的 `.mp4` 视频、`cover.jpg` 封面与帖子描述
- **TikTok**
  - **支持输入**：TikTok 公开视频链接
  - **交付产物**：`.mp4` 视频、`cover.jpg` 封面与文案说明
- **通用流媒体（HLS / m3u8）**
  - **支持输入**：标准 `.m3u8` 播放列表链接
  - **交付产物**：分片并发拉取并合并后的 `.mp4` 视频，自动通过 `ffprobe` 校验时长与音视频轨

## 2. 图片与图文图集

- **小红书（多图与实况图笔记）**
  - **支持输入**：图文笔记链接或 App 分享口令文本
  - **交付产物**：按页面顺序命名的全部高清 `.jpg` 图片（`content.jpg`、`image_02.jpg`...）；若为实况图（LivePhoto），同步提取每一张对应的 `.mov` 动态视频流
- **X (Twitter) 多图推文**
  - **支持输入**：含单图或多图的推文链接
  - **交付产物**：自动过滤转推/评论干扰，按顺序提取原图级（`:orig`）高清图片，完整保存推文正文
- **微博多图（九宫格 / 相册）**
  - **支持输入**：微博图文链接（免手动导入登录态）
  - **交付产物**：按顺序保存全部 `.jpg` 大图（如九图帖完整 9 张原图），同步保存微博正文
- **Instagram 多图帖（Carousel）**
  - **支持输入**：Instagram 多图帖子链接（配合本机已登录会话 Cookie）
  - **交付产物**：按顺序保存全部高清 `.jpg` 图片与帖子正文

## 3. 音频、播客与音乐

- **小宇宙播客（Xiaoyuzhou）**
  - **支持输入**：`xiaoyuzhoufm.com/episode/...` 单集链接
  - **交付产物**：原档播客音频（`.m4a` / `.mp3`）、单集高清封面、包含完整节目介绍与时间轴的 Shownotes Markdown
- **Apple Podcasts**
  - **支持输入**：`podcasts.apple.com/.../id...?i=...` 播客或单集链接
  - **交付产物**：官方源站原档音频（`.mp3` / `.m4a`）、播客封面、单集简介与发布日期元数据
- **网易云音乐**
  - **支持输入**：`music.163.com` 歌曲链接、`163cn.tv` 分享短链
  - **交付产物**：公开曲目直接下载 `.mp3` 音频、专辑封面与同步滚动歌词（`.lrc`）；受限曲目自动提取原版封面与 `.lrc` 歌词，并通过公开音源搜索匹配下载完整 `.mp3`
- **Spotify & Apple Music**
  - **支持输入**：`open.spotify.com/track/...`、`music.apple.com/...` 单曲链接
  - **交付产物**：提取官方歌曲元数据与超清专辑封面（Apple Music 自动升级至 `3000x3000` 分辨率），通过公开音源匹配下载 `.mp3`
- **本地加密与无损音频转换**
  - **网易云 `.ncm` 本地解密**：传入本地 `.ncm` 文件路径，AES/RC4 解密还原音频流并封装为标准 `.mp3`，保留内嵌封面图与标题/歌手/专辑标签
  - **无损 `.flac` 本地转码**：传入本地 `.flac` 文件路径，转换为标准 `320kbps` `.mp3`（保留原文件）
- **云端语音转写（`--transcribe`）**
  - **支持输入**：任意音频任务或附加 `-a` 的视频任务（需配置 `GROQ_API_KEY`、`OPENAI_API_KEY` 或 `SILICONFLOW_KEY`）
  - **交付产物**：自动压缩超限音频并调用 Whisper 接口，输出带分段时间戳的 `<标题>.transcript.md`

## 4. 文档、文章与知识库归档

- **微信公众号文章**
  - **支持输入**：`mp.weixin.qq.com/s/...` 文章链接
  - **交付产物**：结构化 `article.md` 正文、防盗链本地化的全部正文插图（`img_01.png`...）与封面图，正文内图片自动重写为本地相对路径
- **主流技术社区与专栏文章**
  - **支持站点**：知乎（文章/回答）、掘金、CSDN、博客园（cnblogs）、Medium、Substack、少数派、简书、SegmentFault、开源中国、V2EX
  - **交付产物**：剥离导航栏与脚本后的干净 `article.md`（保留多级标题与代码块）及本地化配图
- **Obsidian 知识库同步（`--vault` / `--obsidian`）**
  - **交付产物**：将文章/媒体目录同步至指定 Obsidian Vault 的 `DownloadAnything/` 收件箱，自动在 Markdown 顶部注入标准 YAML frontmatter
- **Notion 数据库同步（`--notion`）**
  - **交付产物**：配置 `NOTION_API_KEY` 与 `NOTION_DATABASE_ID` 后，自动向指定数据库写入包含标题、平台、原始链接、封面与正文的页面记录

## 5. 学术论文与电子书

- **arXiv 论文**
  - **支持输入**：`arxiv.org/abs/...`、`arxiv.org/pdf/...` 或纯编号（如 `2310.06825`）
  - **交付产物**：官方全文 `.pdf`（经 `pypdf` 页数与结构校验）、`citation.bib` 标准 BibTeX 引用文件、包含摘要与作者信息的 Markdown
- **DOI 开放获取论文**
  - **支持输入**：标准 DOI 标识符（如 `10.1186/...`）或 `doi.org` 链接
  - **交付产物**：通过 Crossref 与 Unpaywall 解析并下载开放获取全文 `.pdf`、自动生成官方 `citation.bib` 引用文件与论文元数据摘要
- **电子书（ISBN / MD5）**
  - **支持输入**：10/13 位 ISBN（如 `9780141439518`）、32 位 MD5 哈希、或 Anna's Archive / LibGen 链接
  - **交付产物**：自动探测容器真实格式并保存为 `.epub` 或 `.pdf`，对 EPUB 执行 OPF 清单、章节脊柱（spine）与本地资源完整性校验（支持纯文字、图文混排及扫描版/SVG 章节）

## 6. 网盘分享文件

- **百度网盘**
  - **支持输入**：`pan.baidu.com/s/...` 分享链接或带 `提取码: xxxx` 的分享文本
  - **交付产物**：支持 `--check` 预检文件名与字节大小；结合本机登录态下载分享原文件（ZIP/TAR 默认自动安全解压）
- **夸克网盘**
  - **支持输入**：`pan.quark.cn/s/...` 分享链接（支持多层子目录自动查找）
  - **交付产物**：读取本机登录态，自动在云端创建任务独占的 `_da_temp_<uuid>` 临时目录完成转存与高速直链下载，下载结束后自动清理云端临时目录

## 7. 代码与开发资产

- **GitHub 单文件**
  - **支持输入**：`github.com/<owner>/<repo>/blob/<branch>/<path>` 单文件链接
  - **交付产物**：免克隆整个仓库，直接按指定分支或 Commit 下载与原仓库逐字节一致的目标代码、配置或 Markdown 文件

## 8. 应用与软件安装包

- **微软商店（Microsoft Store）**
  - **支持输入**：`apps.microsoft.com/detail/...` 链接或 12 位 Product ID（如 `9n0dx20hk701`）
  - **交付产物**：从微软官方 CDN（`delivery.mp.microsoft.com`）直接拉取 `.msixbundle` / `.appxbundle` 离线安装包、应用图标及 PowerShell 安装说明
- **安卓应用（Android APK）**
  - **支持输入**：`play.google.com/store/apps/details?id=...` 链接、APKPure/Aptoide 链接或直接传入包名（如 `com.spotify.music`）
  - **交付产物**：从 F-Droid / Aptoide 官方镜像下载 `.apk` 安装包（经 ZIP/Manifest 结构校验）、应用图标及 `adb install` 命令行说明
