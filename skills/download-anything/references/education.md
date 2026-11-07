# 公开课课件与教学视频归档指南（含 `not_for` 边界）

本文档基于对 B 站多 P 公开课、MIT OpenCourseWare（`ocw.mit.edu`）、高校 `.edu` 开放讲义 PDF 及商业 MOOC 平台的实测数据编写，明确了可稳定落盘的标准 SOP 与严禁越界的 `not_for` 清单。

## 1. B 站公开课合集与多 P 教程归档（已测通）

B 站（`bilibili.com/video/BV...`）是中文体系化技术课与大学公开课搬运的核心来源，`da` 支持精确到具体分 P（`?p=N`）的视频、纯音轨与字幕同步提取：

### 支持的能力与参数范式

- **单 P 精准定位（`?p=N`）**：
  - 当 URL 携带 `?p=2`（如 `https://www.bilibili.com/video/BV11s41167h6?p=2`）时，`da` 会自动解析 B 站 `pages` 列表，精准提取第 `N` 集专属的 `cid` 视频流，并将标题与文件名格式化为 `<主标题>_P<页码>_<分集标题>.mp4`，绝不会误下为第 1 集。
  - JSON 输出的 `metadata` 中包含 `"page"`（当前分 P）、`"part"`（分集子标题）与 `"total_pages"`（总分集数）。
- **播客化听课 / 极速纯音轨提取（`-a`）**：
  - 针对长达数十分钟的课程视频，若用户仅需听课或让 AI Agent 总结课堂内容，优先附加 `-a` 直接从 DASH 接口提取无水印独立 `.m4a` 音轨（体积仅为视频的 1/20 ~ 1/50），大幅降低下载耗时并规避超时。
- **CC / AI 字幕自动转 `.srt`**：
  - 自动抓取当前分 P 对应的字幕轨并转换为标准时间轴 `.srt` 文件（记录于 `sidecars.subtitle`），Agent 可直接读取 `.srt` 总结课程核心知识点。
  - **字幕登录态说明**：B 站对部分视频的 AI 字幕启用了登录态保护（未登录返回 `need_login_subtitle: true`）。若需完整提取此类视频字幕，可先在桌面环境运行 `da login bilibili --json` 导入本机浏览器登录会话。

```bash
# 下载公开课指定第 2 讲视频（含封面与可用 .srt 字幕）
da "https://www.bilibili.com/video/BV11s41167h6?p=2" --json

# 仅提取公开课第 2 讲纯音轨（.m4a，极速落盘供听课或转写总结）
da "https://www.bilibili.com/video/BV11s41167h6?p=2" -a --json

# 批量下载多讲：将 ?p=1, ?p=2, ?p=3 逐行写入 courses.txt 后串行归档
da -i courses.txt --json
```

---

## 2. 名校开放课程讲义与课件归档（MIT OCW / `.edu` / arXiv，已测通）

针对麻省理工学院开放式课程（MIT OpenCourseWare，`ocw.mit.edu`）、高校 `.edu` 课程主页及 arXiv 学术讲义，`da` 提供从讲义下载、格式校验到学术引用生成的完整闭环：

1. **MIT OCW 课件详情页与讲义 PDF / 课程包 ZIP**：
   - **支持输入**：
     - 资源详情页链接（如 `https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/resources/mit6_006s20_lec1/`）
     - 讲义 PDF 直链（如 `https://ocw.mit.edu/courses/.../477c78e0af2df61fa205bcc6cb613ceb_MIT6_006S20_lec1.pdf`）
     - 课程大纲与网页笔记（如 `https://ocw.mit.edu/courses/.../pages/syllabus/`，自动转为干净 `article.md`）
   - **交付产物与校验**：
     - 自动剥离 OCW 文件名前的 32 位哈希前缀，还原干净文件名（如 `MIT6_006S20_lec1.pdf`）；
     - 调用 `pypdf` 校验 PDF 头部、尾部 `%%EOF` 与有效页数（`verification.details.page_count`）；
     - 自动生成标准 BibTeX 引用文件 `citation.bib`（记录于 `companion_files`）与包含课程编号、来源链接的 `content.md`。
2. **高校公开课 `.edu` 讲义 PDF 与 arXiv 课程笔记**：
   - 支持直接传入高校课程公开讲义 PDF 链接（如 `https://cs229.stanford.edu/notes2022fall/main_notes.pdf`）或 arXiv 讲义编号，均自动执行 `pypdf` 页数校验并生成配套 `citation.bib` 与 Markdown 元数据。

```bash
# 从 MIT OCW 资源页直接提取讲义 PDF + citation.bib 引用文件
da "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/resources/mit6_006s20_lec1/" --json

# 将 MIT OCW 课程大纲（Syllabus）网页转换为本地干净 Markdown
da "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/pages/syllabus/" --json

# 下载高校公开课 PDF 讲义并校验页数与生成引用
da "https://cs229.stanford.edu/notes2022fall/main_notes.pdf" --json
```

---

## 3. 明确能力边界（`not_for` 安全与反幻觉红线）

> **重要警告（AI Agent 必读）**：对于下列受付费墙、强登录会话、私有协议或数字版权管理（DRM）加密保护的商业网课平台，**`da` 明确不支持，AI Agent 严禁向用户承诺可下载或盲目循环重试**。

### 坚决列入 `not_for` 的受限平台与场景

| 受限类别 | 典型平台 / 链接特征 | 实测阻断原因与技术边界 | Agent 正确应对方式 |
| :--- | :--- | :--- | :--- |
| **国际商业 MOOC 平台** | **Coursera** (`coursera.org/learn/...`)<br/>**edX** (`edx.org` / `courses.edx.org`)<br/>**Udemy** (`udemy.com/course/...`) | 1. 正课视频采用 Google Widevine / FairPlay DRM 强加密或动态签名流；<br/>2. 存在 Cloudflare 人机挑战（HTTP 403/503）与选课账户会话强制校验；<br/>3. edX 公开介绍页仅含 45 秒宣传片，切勿误当正课交付。 | 明确告知用户该商业课程受平台登录墙与 DRM 加密保护，不支持直接抓取；若用户寻找同类公开教材，可协助检索 MIT OCW、arXiv 或 B 站同名公开课。 |
| **国内商业 / 选课制慕课** | **中国大学MOOC / 爱课程** (`icourse163.org`)<br/>**学堂在线** (`xuetangx.com`) | 采用私有 RPC 协议（如 DWR）及与选课账户会话绑定的 AES-128 加密切片，无公开直链。 | 如实说明加密与选课鉴权限制，不调用 `da` 强行抓取。 |
| **B 站课堂付费课程** | **B 站课堂** (`bilibili.com/cheese/play/ss...` 或 `ep...`) | 属于付费专享内容，采用独立鉴权接口而非普通 `BV` 稿件，驱动会直接拒绝并报不支持错误。 | 提醒用户 `bilibili.com/cheese` 为付费专享课程，仅支持普通公开 `BV` 视频合集。 |
| **高校内网教务系统** | **Canvas / Blackboard / Moodle** 等校内私有部署站点 | 依赖学校 VPN 或 CAS 统一身份认证，外部无权限访问。 | 引导用户先从浏览器手动导出课件 PDF，再交由本地工具整理。 |
