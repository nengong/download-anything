"""
GitHub Single Directory and File Precision Extractor Driver
"""
import re
from pathlib import Path
from typing import Optional, List
from urllib.parse import unquote, urlparse
import requests

from core.exceptions import ExtractionError
from core.url_policy import is_http_url
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class GitHubDirDriver(BaseDriver):
    """
    Precision extractor for individual GitHub subdirectories, single files,
    release assets, and open-source font CDN binaries:
    - Avoids heavy `git clone` for the entire repository
    - Direct fast raw file, release binary, or REST contents tree retrieval
    - Captures author, repository metadata, commit branch, and file trees
    """

    name = "github"
    category = "dev"

    URL_REGEX = re.compile(
        r"https?://(?:(?:gh-proxy\.com|ghfast\.top)/https?://)?github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/(tree|blob)/([a-zA-Z0-9_.-]+)/(.*)",
        re.IGNORECASE
    )
    RELEASE_REGEX = re.compile(
        r"https?://(?:(?:gh-proxy\.com|ghfast\.top)/https?://)?github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/releases/download/([^/?#]+)/([^?#]+)",
        re.IGNORECASE
    )
    RAW_REGEX = re.compile(
        r"https?://(?:(?:gh-proxy\.com|ghfast\.top)/https?://)?raw\.githubusercontent\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/([^/?#]+)/([^?#]+)",
        re.IGNORECASE
    )
    FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".woff", ".woff2")
    CDN_DOMAINS = ("cdn.jsdelivr.net", "unpkg.com", "fonts.gstatic.com", "fonts.alibabadesign.com")

    RAW_BASE = "https://raw.githubusercontent.com"
    API_BASE = "https://api.github.com/repos"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/vnd.github.v3+json",
    }

    @classmethod
    def _is_direct_font_or_cdn_url(cls, url: str) -> bool:
        clean = (url or "").strip()
        if not clean.lower().startswith(("http://", "https://")):
            return False
        parsed = urlparse(clean)
        path_lower = unquote(parsed.path).lower()
        if path_lower.endswith(cls.FONT_EXTENSIONS):
            return True
        if is_http_url(clean, cls.CDN_DOMAINS) and path_lower.endswith((".zip", ".tar.gz", ".tgz")):
            return True
        return False

    def can_handle(self, url: str) -> bool:
        clean = (url or "").strip()
        if ("github.com" in clean or "raw.githubusercontent.com" in clean) and (
            bool(self.URL_REGEX.search(clean))
            or bool(self.RELEASE_REGEX.search(clean))
            or bool(self.RAW_REGEX.search(clean))
        ):
            return True
        return self._is_direct_font_or_cdn_url(clean)

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
        proxy_prefix = ""
        for prefix in ("https://gh-proxy.com/", "http://gh-proxy.com/", "https://ghfast.top/", "http://ghfast.top/"):
            if clean.lower().startswith(prefix):
                proxy_prefix = clean[:len(prefix)]
                break

        # 0A. GitHub Releases Direct Asset
        rel_match = self.RELEASE_REGEX.search(clean)
        if rel_match:
            owner, repo, tag, asset_path = rel_match.groups()
            filename = unquote(asset_path.strip("/").split("/")[-1])
            stem = Path(filename).stem or filename
            primary = TargetAsset(
                url=clean,
                filename=filename,
                file_type="primary",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
            return AssetPackage(
                title=f"{repo}_{stem}",
                platform=self.name,
                assets=[primary],
                metadata={
                    "original_url": clean,
                    "repository": f"{owner}/{repo}",
                    "tag": unquote(tag),
                    "path": unquote(asset_path),
                    "kind": "release"
                },
                raw_markdown=f"GitHub Release 发行包直下: `{owner}/{repo}` (`{unquote(tag)}` - `{filename}`)"
            )

        # 0B. GitHub Raw Single File
        raw_match = self.RAW_REGEX.search(clean)
        if raw_match:
            owner, repo, branch, path = raw_match.groups()
            path = path.strip("/")
            filename = unquote(path.split("/")[-1])
            primary = TargetAsset(
                url=clean,
                filename=filename,
                file_type="primary",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
            return AssetPackage(
                title=f"{repo}_{filename}",
                platform=self.name,
                assets=[primary],
                metadata={
                    "original_url": clean,
                    "repository": f"{owner}/{repo}",
                    "branch": unquote(branch),
                    "path": unquote(path),
                    "kind": "file"
                },
                raw_markdown=f"GitHub Raw 单文件直下: `{owner}/{repo}/{unquote(path)}` (`{unquote(branch)}`)"
            )

        # 0C. Direct Open-Source Font / CDN Binary URL
        if not self.URL_REGEX.search(clean) and self._is_direct_font_or_cdn_url(clean):
            parsed = urlparse(clean)
            filename = unquote(Path(parsed.path).name) or "font.ttf"
            headers = {"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            if is_http_url(clean, ("fonts.alibabadesign.com", "alibabafonts.com")):
                headers["Referer"] = "https://www.alibabafonts.com/"
                headers["Origin"] = "https://www.alibabafonts.com"
            title = Path(filename).stem or filename
            primary = TargetAsset(
                url=clean,
                filename=filename,
                file_type="primary",
                headers=headers
            )
            return AssetPackage(
                title=title,
                platform="font",
                assets=[primary],
                metadata={
                    "original_url": clean,
                    "host": parsed.netloc,
                    "filename": filename,
                    "kind": "font"
                },
                raw_markdown=f"开源字体直链提取: `{filename}`\n\n- **来源节点**：`{parsed.netloc}`\n- **原始链接**：<{clean}>"
            )

        m = self.URL_REGEX.search(clean)
        if not m:
            raise ExtractionError(f"URL is not a GitHub directory, blob, or release path: {url}")

        owner, repo, kind, branch, path = m.groups()
        path = path.strip("/")

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Single Blob / File
        if kind == "blob":
            filename = unquote(path.split("/")[-1])
            raw_url = f"{proxy_prefix}{self.RAW_BASE}/{owner}/{repo}/{branch}/{path}"
            primary = TargetAsset(
                url=raw_url,
                filename=filename,
                file_type="primary",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
            return AssetPackage(
                title=f"{repo}_{filename}",
                platform=self.name,
                assets=[primary],
                metadata={
                    "original_url": url,
                    "repository": f"{owner}/{repo}",
                    "branch": branch,
                    "path": path,
                    "kind": "file"
                },
                raw_markdown=f"GitHub 单文件精准抓取: `{owner}/{repo}/{path}` (`{branch}` 分支)"
            )

        # 2. Directory / Tree
        api_url = f"{self.API_BASE}/{owner}/{repo}/contents/{path}"
        try:
            resp = session.get(api_url, params={"ref": branch}, timeout=15)
            if resp.status_code == 404:
                raise ExtractionError(f"GitHub path not found: {owner}/{repo}/{path} on branch {branch}")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query GitHub contents API: {e}")

        if isinstance(data, dict) and data.get("type") == "file":
            # Direct file returned
            filename = data.get("name", path.split("/")[-1])
            raw_url = data.get("download_url") or f"{self.RAW_BASE}/{owner}/{repo}/{branch}/{path}"
            primary = TargetAsset(
                url=raw_url,
                filename=filename,
                file_type="primary",
                expected_size=data.get("size")
            )
            return AssetPackage(
                title=f"{repo}_{filename}",
                platform=self.name,
                assets=[primary],
                metadata={
                    "original_url": url,
                    "repository": f"{owner}/{repo}",
                    "branch": branch,
                    "path": path,
                    "kind": "file"
                }
            )

        if not isinstance(data, list) or not data:
            raise ExtractionError(f"No contents found in GitHub directory: {path}")

        assets: List[TargetAsset] = []
        folder_name = path.split("/")[-1] or repo

        for item in data:
            if item.get("type") == "file":
                f_name = item.get("name")
                dl_url = item.get("download_url")
                if not dl_url:
                    continue
                file_type = "primary" if not assets else "extra"
                assets.append(TargetAsset(
                    url=dl_url,
                    filename=f_name,
                    file_type=file_type,
                    expected_size=item.get("size")
                ))

        if not assets:
            raise ExtractionError(f"No regular files found directly under directory: {path}")

        return AssetPackage(
            title=f"{repo}_{folder_name}",
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": url,
                "repository": f"{owner}/{repo}",
                "branch": branch,
                "path": path,
                "file_count": len(assets),
                "kind": "directory"
            },
            raw_markdown=f"GitHub 单目录精准抓取: `{owner}/{repo}/{path}`\n\n共提取 {len(assets)} 个直接文件。"
        )
