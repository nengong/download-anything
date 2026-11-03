"""
Microsoft Store Package Extractor Driver (.msixbundle / .appxbundle)
Fetches offline installer packages directly from official Microsoft Delivery CDN,
enabling installation on LTSC, Enterprise, or unlicensed Windows systems without Store login.
"""
import re
from typing import Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from drivers.base import BaseDriver, AssetPackage, TargetAsset
from core.exceptions import ExtractionError

class MicrosoftStoreDriver(BaseDriver):
    """Driver for extracting offline UWP / MSIX app packages from Microsoft Store."""

    name = "ms_store"
    category = "software"

    STORE_URL_REGEX = re.compile(
        r"(?:https?://)?(?:apps|www)\.microsoft\.com/(?:[a-zA-Z-]+/)?(?:detail/|store/productId/|p/[^/]+/)?(?P<id>[a-zA-Z0-9]{12})\b",
        re.IGNORECASE
    )

    RAW_PID_REGEX = re.compile(r"^9[a-zA-Z0-9]{11}$", re.IGNORECASE)

    def can_handle(self, url: str) -> bool:
        clean = url.strip()
        return bool(self.STORE_URL_REGEX.search(clean)) or bool(self.RAW_PID_REGEX.match(clean))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        clean = url.strip()
        m = self.STORE_URL_REGEX.search(clean)
        if m:
            pid = m.group("id").lower()
        elif self.RAW_PID_REGEX.match(clean):
            pid = clean.lower()
        else:
            raise ExtractionError(f"Invalid Microsoft Store URL or Product ID: {url}")

        canonical_url = f"https://apps.microsoft.com/detail/{pid}"

        # 1. Fetch Official Product Metadata from DisplayCatalog API
        title = pid
        publisher = "Unknown Publisher"
        icon_url = None
        description = ""

        try:
            cat_url = f"https://displaycatalog.mp.microsoft.com/v7.0/products/{pid}?market=US&languages=en-us"
            r_cat = requests.get(cat_url, timeout=8)
            if r_cat.status_code == 200:
                data = r_cat.json()
                props = data.get("Product", {}).get("LocalizedProperties", [{}])[0]
                title = props.get("ProductTitle") or pid
                publisher = props.get("PublisherName") or "Microsoft Store Developer"
                description = props.get("ProductDescription") or ""
                for img in props.get("Images", []):
                    if img.get("ImagePurpose") in ("Logo", "Poster", "Tile", "BoxArt"):
                        uri = img.get("Uri", "")
                        if uri.startswith("//"):
                            icon_url = "https:" + uri
                        else:
                            icon_url = uri
                        break
        except Exception:
            pass

        # 2. Query adguard FE3 resolver for official Microsoft CDN links
        adg_url = "https://store.rg-adguard.net/api/GetFiles"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://store.rg-adguard.net/",
            "Origin": "https://store.rg-adguard.net",
        }
        data = {
            "type": "url",
            "url": canonical_url,
            "ring": "RP"
        }

        try:
            r_adg = requests.post(adg_url, headers=headers, data=data, timeout=15)
            r_adg.raise_for_status()
            soup = BeautifulSoup(r_adg.text, "html.parser")
            raw_links = [(a.text.strip(), a.get("href")) for a in soup.find_all("a") if a.get("href")]
        except Exception as e:
            raise ExtractionError(f"Failed to query Microsoft Store package resolver: {e}")

        # Filter executable packages (.msixbundle, .appxbundle, .msix, .appx), ignoring .BlockMap
        packages = [
            l for l in raw_links 
            if not l[0].endswith(".BlockMap") and any(l[0].endswith(ext) for ext in (".msixbundle", ".appxbundle", ".msix", ".appx"))
        ]

        if not packages:
            raise ExtractionError(
                f"No offline installation packages (.msixbundle/.appxbundle) found for Microsoft Store product '{title}' ({pid})."
            )

        # Prefer neutral .msixbundle or .appxbundle, or x64 architecture
        primary_pkg = None
        for p in packages:
            fname = p[0].lower()
            if ("neutral" in fname or "x64" in fname) and (fname.endswith(".msixbundle") or fname.endswith(".appxbundle")):
                primary_pkg = p
                break
        if not primary_pkg:
            for p in packages:
                if p[0].endswith(".msixbundle") or p[0].endswith(".appxbundle"):
                    primary_pkg = p
                    break
        if not primary_pkg:
            primary_pkg = packages[0]

        pkg_filename, pkg_download_url = primary_pkg

        assets: List[TargetAsset] = [
            TargetAsset(
                filename=pkg_filename,
                url=pkg_download_url,
                file_type="primary",
                headers={"User-Agent": "Mozilla/5.0"}
            )
        ]

        if icon_url:
            assets.append(
                TargetAsset(
                    filename="cover.png",
                    url=icon_url,
                    file_type="cover",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )

        # Generate sidecar documentation including PowerShell install instructions
        sidecar_text = (
            f"# {title} (Microsoft Store 离线安装包)\n\n"
            f"> - **产品名称**：`{title}`\n"
            f"> - **开发商**：`{publisher}`\n"
            f"> - **Product ID**：`{pid}`\n"
            f"> - **官方主页**：<{canonical_url}>\n"
            f"> - **安装包格式**：`{pkg_filename.split('.')[-1]}` ({pkg_filename})\n\n"
            f"---\n\n"
            f"## 🛠 在无微软商店 / 盗版 / 精简版 / LTSC Windows 上一键离线安装指引\n\n"
            f"由于本安装包是直接从微软官方 CDN（`delivery.mp.microsoft.com`）拉取的原版受信任数字签名包，免登录微软账号即可直接安装：\n\n"
            f"### 方法一：图形化双击安装（推荐）\n"
            f"在 Windows 10/11 系统中，直接双击 `{pkg_filename}` 文件，系统自带的「应用安装程序 (App Installer)」会自动弹出并点击「安装」即可。\n\n"
            f"### 方法二：PowerShell 一键免登命令行安装\n"
            f"以管理员身份打开 PowerShell，进入当前下载目录执行：\n\n"
            f"```powershell\n"
            f"Add-AppxPackage -Path .\\{pkg_filename}\n"
            f"```\n\n"
            f"如果提示缺少 `Microsoft.VCLibs` 或 `WindowsAppRuntime` 基础依赖框架，请先安装同目录下伴生的依赖包即可。\n\n"
            f"---\n\n"
            f"## 软件简介\n\n{description[:500]}..."
        )

        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {"id": pid, "name": publisher},
            "sidecar_text": sidecar_text,
        }

        return AssetPackage(
            platform="ms_store",
            title=title,
            original_url=canonical_url,
            assets=assets,
            metadata=metadata
        )
