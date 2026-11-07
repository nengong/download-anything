# 开源商用字体下载与梯队调度规范

本文档基于对 34 组开源商用字体源的四维实测数据（连通率、首字节延迟 TTFB、吞吐速率、二进制魔数与 ZIP 容器完整性校验，以及 100% 免登录免验证门槛）制定。当用户要求下载字体（只提供字体名称或提供直链）时，AI Agent 应按本规范匹配最优下载源并调用 `da` 完成下载、校验与自动解压。

## 1. 实测源梯队定级与网络选型

### 【首选源（Tier 1）】—— 权威全量、高吞吐、零门槛（实测评分 92 ~ 98）

1. **GitHub Releases 官方发布包直链（`github.com/<owner>/<repo>/releases/download/...`）**
   - **适用场景**：全量中文字体（> 20 MB，如霞鹜文楷、思源黑体/宋体、得意黑）及需一次获取全字重（Regular/Bold/Light）与 `OFL.txt` 授权文件的场景。
   - **实测表现**：HTTP 200，平均吞吐 `10 ~ 15 MB/s`；ZIP 归档由 `da` 自动执行安全解压并输出全部 `.ttf` / `.otf` / `.woff2` 路径至 `extracted_files`。
   - **网络回退**：海外/代理环境直连最佳；国内直连若遇超时，`da` 内置的 `MirrorRouter` 会自动故障转移至国内加速节点。
2. **西文与轻量字体公共 CDN（`cdn.jsdelivr.net/gh/<owner>/<repo>@<ref>/...`）**
   - **适用场景**：**单文件体积 < 20 MB** 的西文编程/UI 字体（JetBrains Mono、Inter、Fira Code）、站酷系列单文件，或单字重思源黑体 OTF（约 15.7 MB）。
   - **实测表现**：全球边缘节点加速，首包 TTFB 约 `540 ms`，吞吐速率达 `16 ~ 26 MB/s`，`.ttf`（`00010000`）/ `.otf`（`4F54544F`）魔数 100% 校验通过。
3. **阿里官方字体 CDN 直链（`fonts.alibabadesign.com/...`）**
   - **适用场景**：阿里巴巴普惠体 3.0、钉钉进步体、阿里妈妈数黑体/东方大楷/刀隶体等阿里系免费商用字体。
   - **实测表现**：国内 CDN 首包 TTFB 仅 `100 ~ 185 ms`，吞吐稳定 `9.8 ~ 10.8 MB/s`。`da` 驱动层已自动注入官方放行 `Referer: https://www.alibabafonts.com/` 请求头，无需人工干预。

### 【次选 / 国内加速源（Tier 2）】—— 突破大文件限制与分卷场景（实测评分 80 ~ 92）

1. **GitHub 专用透传加速镜像（`https://gh-proxy.com/https://github.com/...`）**
   - **适用场景**：国内直连网络下，下载 **> 20 MB** 的全量中文字体单文件（如霞鹜文楷 24.7 MB TTF）或百兆级整包 ZIP。
   - **实测表现**：不受 jsDelivr 20 MB 截断限制，TTFB 约 `840 ms`，吞吐稳定 `8+ MB/s`。
2. **NPM `@fontsource` / `unpkg.com` Webfont 源**
   - **适用场景**：前端项目显式需要 `.woff2` Webfont 切片或按 NPM 语义版本锁定的西文字体。

### 【应急兜底源（Tier 3）】—— 兼容性回退（实测评分 60 ~ 75）

1. **GitHub `blob` 单文件页面链接（`github.com/<owner>/<repo>/blob/...`）**：`da` 自动将 HTML 页面链接改写为 `raw.githubusercontent.com` 二进制流并执行字体魔数校验。
2. **国内免登录直连站（如站长之家字体直链）**：免登录可用，但源站存在约 `250 KB/s` 的带宽限速，仅在 GitHub 与加速镜像均不可达时兜底。

---

## 2. 已验证的主流开源商用字体直链速查表

以下直链均经实测连通并通过 `da` 的 `font-magic`（TTF `00010000` / OTF `4F54544F`）或 `zip` 容器完整性校验：

| 字体名称 | 授权协议 | 推荐级别 | 验证通过的直链 URL | 格式与体积 |
| :--- | :---: | :---: | :--- | :---: |
| **霞鹜文楷（LXGW WenKai）单文件** | SIL OFL 1.1 | Tier 1 | `https://github.com/lxgw/LxgwWenKai/releases/download/v1.530/LXGWWenKai-Regular.ttf` | TTF (`24.7 MB`) |
| **霞鹜文楷（国内加速直链）** | SIL OFL 1.1 | Tier 2 | `https://gh-proxy.com/https://github.com/lxgw/LxgwWenKai/releases/download/v1.530/LXGWWenKai-Regular.ttf` | TTF (`24.7 MB`) |
| **霞鹜文楷（全字重整包）** | SIL OFL 1.1 | Tier 1 | `https://github.com/lxgw/LxgwWenKai/releases/download/v1.530/lxgw-wenkai-v1.530.zip` | ZIP (`81.9 MB`) |
| **思源黑体（Noto Sans CJK SC 单重）** | SIL OFL 1.1 | Tier 1 | `https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf` | OTF (`15.7 MB`) |
| **思源黑体（Source Han Sans SC 全套）** | SIL OFL 1.1 | Tier 1 | `https://github.com/adobe-fonts/source-han-sans/releases/download/2.005R/09_SourceHanSansSC.zip` | ZIP (`125.8 MB`) |
| **思源宋体（Noto Serif CJK SC 全套）** | SIL OFL 1.1 | Tier 1 | `https://github.com/notofonts/noto-cjk/releases/download/Serif2.003/09_NotoSerifCJKsc.zip` | ZIP (`110.4 MB`) |
| **得意黑（Smiley Sans 全套）** | SIL OFL 1.1 | Tier 1 | `https://github.com/atelier-anchor/smiley-sans/releases/download/v2.0.1/smiley-sans-v2.0.1.zip` | ZIP (`5.5 MB`) |
| **阿里巴巴普惠体 3.0（55 Regular）** | 免费商用 | Tier 1 | `https://fonts.alibabadesign.com/AlibabaPuHuiTi-3/AlibabaPuHuiTi-3-55-Regular/AlibabaPuHuiTi-3-55-Regular.ttf` | TTF (`8.1 MB`) |
| **钉钉进步体（DingTalk JinBuTi）** | 免费商用 | Tier 1 | `https://fonts.alibabadesign.com/DingTalkJinBuTi/DingTalkJinBuTi-Regular/DingTalkJinBuTi-Regular.ttf` | TTF (`2.0 MB`) |
| **站酷快乐体（ZCOOL KuaiLe）** | SIL OFL 1.1 | Tier 1 | `https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf` | TTF (`1.4 MB`) |
| **JetBrains Mono（Regular 单文件）** | SIL OFL 1.1 | Tier 1 | `https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@master/fonts/ttf/JetBrainsMono-Regular.ttf` | TTF (`264 KB`) |
| **JetBrains Mono（全字重整包）** | SIL OFL 1.1 | Tier 1 | `https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip` | ZIP (`5.4 MB`) |
| **Inter（可变字体单文件）** | SIL OFL 1.1 | Tier 1 | `https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf` | TTF (`862 KB`) |
| **Inter（全套静态+可变整包）** | SIL OFL 1.1 | Tier 1 | `https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip` | ZIP (`32.2 MB`) |
| **Fira Code（全套编程连字整包）** | SIL OFL 1.1 | Tier 1 | `https://github.com/tonsky/FiraCode/releases/download/6.2/Fira_Code_v6.2.zip` | ZIP (`2.4 MB`) |

---

## 3. AI Agent 字体下载调度 SOP 与避坑规则

### 标准调度步骤

1. **名称转直链**：当用户仅给出字体名称（如“帮我下载霞鹜文楷”或“下载 JetBrains Mono 字体”）时，优先从上表匹配 **Tier 1 首选源直链**；若用户未出现在表中，检索其官方 GitHub Release `.ttf`/`.otf`/`.zip` 直链。
2. **执行下载与校验**：
   ```bash
   # 单字体文件（自动校验 TTF/OTF/WOFF2 魔数）
   da "https://github.com/lxgw/LxgwWenKai/releases/download/v1.530/LXGWWenKai-Regular.ttf" --json

   # 全字重 ZIP 归档（默认自动安全解压，所有字体路径记录在 extracted_files）
   da "https://github.com/atelier-anchor/smiley-sans/releases/download/v2.0.1/smiley-sans-v2.0.1.zip" --json
   ```
3. **异常降级**：若国内网络直连 GitHub Release 超时，立即切换至 **Tier 2**（在原 GitHub 直链前加 `https://gh-proxy.com/`，或对 < 20 MB 字体改用 `cdn.jsdelivr.net/gh/...`）。

### 三大必避陷阱（`not_for` 与防踩坑约束）

- **严禁将 > 20 MB 的中文字体指派给 jsDelivr**：`cdn.jsdelivr.net` 设有单文件 `20 MB` 硬上限，请求霞鹜文楷（24.7 MB）等大字体会直接返回 `HTTP 403 Forbidden (File size exceeded the configured limit of 20 MB)`。大于 20 MB 的字体必须走 GitHub Releases 或 `gh-proxy.com`。
- **勿直接把猫啃网（`maoken.com`）、`100font.com` 等国内聚合详情页当作字体直链**：此类站点自身不托管二进制字体，其页面链接多跳转至百度网盘、夸克网盘或要求关注公众号。若需下载其中收录的字体，应优先查找对应的官方 GitHub 仓库，或提取页面内的百度/夸克网盘分享链接再交由 `da` 的网盘驱动处理。
- **拒绝非开源商业授权盗版字体**：如方正、汉仪、蒙纳（Monotype）等受商业版权保护的收费字体，不在免授权开源下载范围内，请主动提醒用户版权风险并推荐思源、霞鹜文楷、阿里普惠体等免费商用替代方案。
