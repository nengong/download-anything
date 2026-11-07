# 支持的平台与能力分级清单

本清单按 **核心场景（一级） → 目标平台（二级，每个平台合并视频/图文等全部形态，不重复拆分） → 具体交付产物与边界（三级）** 组织。命令行参数与 JSON 结构见 [cli.md](cli.md)。

## 1. 视频、图文与社交平台（单入口自动识别形态）

- **哔哩哔哩（B站）**
  - **支持输入**：标准视频链接（`bilibili.com/video/BV...`，支持 `?p=N` 指定分 P 合集集数）、移动端分享文本、`b23.tv` 短链
  - **交付产物**：声画同步 `.mp4` 视频、高清封面 `cover.jpg`、`.srt` 标准时间轴字幕（自动转换 CC / AI 字幕）
  - **附加能力**：支持 `-a` 直接提取独立 `.m4a` 纯音轨；多 P 课程合集与公开课归档规范详见 [education.md](education.md)（不支持 `bilibili.com/cheese` 付费课堂）
- **抖音（Douyin）**
  - **支持输入**：App 整段分享口令文本（自动剥离前后乱码与数字前缀）、`v.douyin.com` 短链、`douyin.com/video/...` 或 `douyin.com/note/...` 链接
  - **交付产物（自动识别视频或图文）**：
    - **视频作品**：免水印高清 `.mp4` 视频（最高支持 4K 声画同步双轨）、高清原画封面 `cover.jpg`、独立背景音乐/原声音轨 `audio.mp3`
    - **图文作品**：按顺序保存全部无水印高清 `.jpg` 图片及配套背景音乐 `audio.mp3`
    - **结构化元数据**：包含完整标题、话题标签、作者 UID 与点赞数的 `content.md` / `content.info.json`
- **小红书（Xiaohongshu）**
  - **支持输入**：笔记详情链接、App 分享口令文本与 `xhslink.com` / `xhslink.cn` 短链
  - **交付产物（自动识别视频、多图或实况图）**：
    - **视频笔记**：无水印 `.mp4` 视频、`cover.jpg` 封面
    - **多图与实况图（LivePhoto）**：按页面顺序保存全部高清 `.jpg` 图片（`image_01.jpg`...）；若含实况图，同步提取每一张对应的 `.mov` 动态视频流
    - **结构化元数据**：包含完整标题、正文与 `#话题标签` 的 `content.md` / `content.info.json`
- **X (Twitter)**
  - **支持输入**：`x.com/<user>/status/<id>` 或 `twitter.com` 推文链接
  - **交付产物（自动识别视频或多图）**：视频推文自动选轨合并高画质 `.mp4` 与 `cover.jpg`；多图推文自动过滤转推/评论干扰，按顺序提取原图级（`:orig`）高清图片；完整保留推文正文与互动计数
- **微博（Weibo）**
  - **支持输入**：`weibo.com` / `m.weibo.cn` 状态链接（支持自动生成访客会话免登录提取）
  - **交付产物（自动识别视频或九宫格多图）**：视频微博输出声画同步 `.mp4`；多图微博按顺序保存全部高清大图（如九图帖完整 9 张原图）；同步保存微博正文与作者信息
- **Instagram**
  - **支持输入**：`instagram.com/reel/...`、`instagram.com/p/...` 链接
  - **交付产物（自动识别 Reels 视频或 Carousel 多图）**：Reels 视频自动选轨合并 `.mp4` 与封面；多图帖配合本机已登录会话 Cookie（`DA_INSTAGRAM_COOKIE_FILE`）按顺序完整下载全部高清 `.jpg` 图片与帖子正文
- **YouTube**
  - **支持输入**：`youtube.com/watch?v=...`、`youtu.be/...`、`youtube.com/shorts/...`
  - **交付产物**：自动选轨合并的声画同步 `.mp4` 视频、`cover.jpg` 封面、频道与简介元数据
- **TikTok**
  - **支持输入**：TikTok 公开视频链接
  - **交付产物**：`.mp4` 视频、`cover.jpg` 封面与文案说明
- **通用流媒体（HLS / m3u8）**
  - **支持输入**：标准 `.m3u8` 播放列表链接
  - **交付产物**：分片拉取并合并后的 `.mp4` 视频，自动通过 `ffprobe` 校验时长与音视频轨

## 2. 播客、音乐与本地音频转换

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
- **可选语音转写（`--transcribe`）**
  - **支持输入**：任意音频任务或附加 `-a` 的视频任务（仅在已接入外部转写后端且用户明确要求文字稿时按需启用；核心下载、本地字幕提取与格式转换均 100% 纯本地免配置运行）
  - **交付产物**：自动压缩超限音频并生成带分段时间戳的 `<标题>.transcript.md`

## 3. 公众号、技术文章与知识库归档

- **微信公众号文章**
  - **支持输入**：`mp.weixin.qq.com/s/...` 文章链接
  - **交付产物**：结构化 `article.md` 正文、防盗链本地化的全部正文插图（`img_01.png`...）与封面图，正文内图片自动重写为本地相对路径
- **主流技术社区与专栏文章**
  - **支持站点**：知乎（文章/回答）、掘金、CSDN、博客园（cnblogs）、Medium、Substack、少数派、简书、SegmentFault、开源中国、V2EX
  - **交付产物**：剥离导航栏与脚本后的干净 `article.md`（保留多级标题与代码块）及本地化配图
- **Obsidian 知识库同步（`--vault` / `--obsidian`）**
  - **交付产物**：将文章/媒体目录同步至指定 Obsidian Vault 的 `DownloadAnything/` 收件箱，自动在 Markdown 顶部注入标准 YAML frontmatter

## 4. 学术论文、公开课课件与电子书

- **arXiv 论文与名校公开课讲义（MIT OCW / `.edu`）**
  - **支持输入**：`arxiv.org/abs/...`、`arxiv.org/pdf/...`、纯编号（如 `2310.06825`）、MIT OCW 资源页/讲义直链（`ocw.mit.edu/courses/...`）或高校 `.edu` 公开讲义 PDF 链接
  - **交付产物**：官方全文 `.pdf`（经 `pypdf` 页数与结构校验）、`citation.bib` 标准 BibTeX 引用文件、包含摘要与作者信息的 Markdown（商业 MOOC 的 `not_for` 边界详见 [education.md](education.md)）
- **DOI 开放获取论文**
  - **支持输入**：标准 DOI 标识符（如 `10.1186/...`）或 `doi.org` 链接
  - **交付产物**：通过 Crossref 与 Unpaywall 解析并下载开放获取全文 `.pdf`、自动生成官方 `citation.bib` 引用文件与论文元数据摘要
- **电子书（ISBN / MD5）**
  - **支持输入**：10/13 位 ISBN（如 `9780141439518`）、32 位 MD5 哈希、或 Anna's Archive / LibGen 链接（若仅提供书名，可由 Agent 先查询对应的 ISBN 或 MD5 再传入下载）
  - **交付产物**：自动探测容器真实格式并保存为 `.epub` 或 `.pdf`，对 EPUB 执行 OPF 清单、章节脊柱（spine）与本地资源完整性校验（支持纯文字、图文混排及扫描版/SVG 章节）

## 5. 网盘分享文件

- **百度网盘**
  - **支持输入**：`pan.baidu.com/s/...` 分享链接或带 `提取码: xxxx` 的分享文本
  - **交付产物**：支持 `--check` 预检文件名与字节大小；结合本机登录态下载分享原文件（ZIP/TAR 默认自动安全解压）
- **夸克网盘**
  - **支持输入**：`pan.quark.cn/s/...` 分享链接（支持多层子目录自动查找）
  - **交付产物**：读取本机登录态，自动在云端创建任务独占的 `_da_temp_<uuid>` 临时目录完成转存与高速直链下载，下载结束后自动清理云端临时目录

## 6. 代码、开源字体与应用安装包

- **GitHub 单文件、Release 发行包与开源商用字体**
  - **支持输入**：`github.com/<owner>/<repo>/blob/<branch>/<path>` 单文件链接、`github.com/<owner>/<repo>/releases/download/...` 发行包直链、`raw.githubusercontent.com`、jsDelivr CDN 及阿里官方字体 CDN（`fonts.alibabadesign.com`）直链
  - **交付产物**：免克隆整个仓库直接下载目标代码或发行包；字体文件（`.ttf` / `.otf` / `.woff2`）自动执行二进制魔数校验，ZIP 字体包自动安全解压；开源商用字体实测梯队与直链速查表详见 [fonts.md](fonts.md)
- **微软商店（Microsoft Store）**
  - **支持输入**：`apps.microsoft.com/detail/...` 链接或 12 位 Product ID（如 `9N0DX20HK701`）
  - **交付产物**：借助 `store.rg-adguard.net` 解析并从微软官方 CDN（`delivery.mp.microsoft.com`）拉取 `.msixbundle` / `.appxbundle` 离线安装包、应用图标及 PowerShell 安装说明
  - **适用边界**：仅适用于提供标准 MSIX/Appx 离线包的免费商店应用（不支持付费应用或仅提供传统 Win32 `.exe` 安装器的应用），且依赖第三方解析服务在线可用
- **安卓应用（Android APK）**
  - **支持输入**：`play.google.com/store/apps/details?id=...` 链接、APKPure/Aptoide 链接或直接传入包名（如 `org.videolan.vlc`、`com.spotify.music`）
  - **交付产物**：从 F-Droid / Aptoide 公开镜像检索下载 `.apk` 安装包（经 ZIP/Manifest 结构校验）、应用图标及 `adb install` 命令行说明
  - **适用边界**：能否获取及具体版本号取决于公开镜像源收录情况，结构校验不等同于开发者签名认证
