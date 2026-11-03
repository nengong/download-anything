"""
Android APK Direct Extraction Driver
Extracts official signed Android .apk packages from F-Droid and Aptoide mirrors
without Google Play login or device account bindings.
Generates companion install guide and adb commands.
"""
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class AndroidAPKDriver(BaseDriver):
    """
    Driver for downloading Android application packages (.apk):
    - Supports Google Play Store links (play.google.com/store/apps/details?id=...)
    - Supports APKPure / Aptoide links
    - Supports direct package names (e.g. com.termux, org.videolan.vlc)
    - Generates 1-click ADB offline install commands
    """

    name = "android_apk"
    category = "software"

    PACKAGE_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip()
        if "play.google.com/store/apps/details" in clean:
            return True
        if "apkpure." in clean or "aptoide.com" in clean:
            return True
        if clean.startswith("apk:") or clean.startswith("package:"):
            return True
        # Check if bare package name like com.termux or org.videolan.vlc
        if not clean.startswith("http://") and not clean.startswith("https://"):
            if self.PACKAGE_REGEX.match(clean) and "." in clean and len(clean.split(".")) >= 2:
                # Discard common non-package strings (like domain names or filenames)
                if not any(clean.endswith(ext) for ext in [".com", ".cn", ".org", ".net", ".io", ".py", ".md", ".json", ".txt"]):
                    return True
        return False

    def _extract_package_name(self, target: str) -> str:
        clean = target.strip()
        if "play.google.com" in clean:
            parsed = urlparse(clean)
            qs = parse_qs(parsed.query)
            pkg = qs.get("id", [None])[0]
            if pkg:
                return pkg

        if "apkpure." in clean:
            # e.g. https://apkpure.com/termux/com.termux
            parts = clean.rstrip("/").split("/")
            last_part = parts[-1]
            if self.PACKAGE_REGEX.match(last_part):
                return last_part

        if "aptoide.com" in clean:
            # e.g. https://com-termux.en.aptoide.com/app
            match = re.search(r"https?://([a-zA-Z0-9_\-]+)\.en\.aptoide\.com", clean)
            if match:
                return match.group(1).replace("-", ".")

        if clean.startswith("apk:") or clean.startswith("package:"):
            return clean.split(":", 1)[1].strip()

        return clean

    def extract(self, url: str, **kwargs) -> AssetPackage:
        pkg_name = self._extract_package_name(url)
        if not pkg_name:
            raise ExtractionError(f"Could not parse valid Android package name from '{url}'")

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Try F-Droid (Fastest, verified open-source builds)
        info = self._query_fdroid(pkg_name, session)

        # 2. Try Aptoide mirror (Vast consumer catalog)
        if not info:
            info = self._query_aptoide(pkg_name, session)

        if not info:
            raise ExtractionError(
                f"Could not locate official APK download mirror for package '{pkg_name}'. "
                "Ensure package name is correct and publicly listed."
            )

        app_name = info.get("name") or pkg_name
        version = info.get("version") or "latest"
        download_url = info["url"]
        size_bytes = info.get("size")
        icon_url = info.get("icon")

        primary_filename = f"{pkg_name}_{version}.apk"
        assets: List[TargetAsset] = [
            TargetAsset(
                filename=primary_filename,
                url=download_url,
                file_type="primary",
                expected_size=size_bytes,
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
        ]

        if icon_url:
            assets.append(TargetAsset(
                filename="icon.png",
                url=icon_url,
                file_type="cover",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

        markdown_body = (
            f"# {app_name} (Android APK)\n\n"
            f"> - **包名 (Package Name)**: `{pkg_name}`\n"
            f"> - **版本 (Version)**: `{version}`\n"
            f"> - **镜像源 (Source)**: `{info['source']}`\n"
            f"> - **安装包文件名**: `{primary_filename}`\n\n"
            f"---\n\n"
            f"### 🚀 离线安装指南 (ADB 命令行)\n\n"
            f"将手机连接电脑并开启 USB 调试，运行以下命令即可直接免商店安装：\n\n"
            f"```bash\n"
            f"# 安装或覆盖升级 (-r 保留数据)\n"
            f"adb install -r \"{primary_filename}\"\n"
            f"```\n\n"
            f"### 📱 手机端本地安装\n"
            f"将 `{primary_filename}` 传输至手机存储，在文件管理器中点击即可完成安装。"
        )

        metadata = {
            "title": f"{app_name} v{version}",
            "original_url": url,
            "package_name": pkg_name,
            "version": version,
            "source": info["source"],
            "sidecar_text": markdown_body,
            "author": {"name": info.get("developer", "Unknown")},
            "metrics": {"size_bytes": size_bytes or 0}
        }

        return AssetPackage(
            platform="android_apk",
            title=f"{app_name}_{version}",
            original_url=url,
            assets=assets,
            metadata=metadata
        )

    def _query_fdroid(self, pkg_name: str, session: requests.Session) -> Optional[Dict[str, Any]]:
        api_url = f"https://f-droid.org/api/v1/packages/{pkg_name}"
        try:
            r = session.get(api_url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                vc = data.get("suggestedVersionCode")
                packages = data.get("packages", [])
                ver = "latest"
                for p in packages:
                    if p.get("versionCode") == vc:
                        ver = p.get("versionName")
                        break
                apk_url = f"https://f-droid.org/repo/{pkg_name}_{vc}.apk"
                icon = None
                icon_name = data.get("icon")
                if icon_name:
                    icon = f"https://f-droid.org/repo/icons-640/{icon_name}"
                return {
                    "source": "F-Droid",
                    "name": data.get("name") or pkg_name,
                    "version": ver,
                    "url": apk_url,
                    "icon": icon,
                    "developer": data.get("authorName", "Open Source")
                }
        except Exception:
            pass
        return None

    def _query_aptoide(self, pkg_name: str, session: requests.Session) -> Optional[Dict[str, Any]]:
        search_url = f"https://ws75.aptoide.com/api/7/apps/search/query={pkg_name}"
        try:
            r = session.get(search_url, timeout=10)
            if r.status_code == 200:
                dl = r.json().get("datalist", {}).get("list", [])
                for item in dl:
                    if item.get("package") == pkg_name:
                        file_info = item.get("file", {})
                        apk_url = file_info.get("path") or file_info.get("path_alt")
                        if apk_url:
                            return {
                                "source": "Aptoide CDN",
                                "name": item.get("name") or pkg_name,
                                "version": file_info.get("vername") or "latest",
                                "size": item.get("size"),
                                "url": apk_url,
                                "icon": item.get("icon"),
                                "developer": item.get("developer", {}).get("name", "Unknown")
                            }
        except Exception:
            pass
        return None
