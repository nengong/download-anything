"""
GitHub Single Directory and File Precision Extractor Driver
"""
import re
from typing import Optional, List
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class GitHubDirDriver(BaseDriver):
    """
    Precision extractor for individual GitHub subdirectories or single files:
    - Avoids heavy `git clone` for the entire repository
    - Direct fast raw file or REST contents tree retrieval
    - Captures author, repository metadata, commit branch, and file trees
    """

    name = "github"
    category = "dev"

    URL_REGEX = re.compile(
        r"https?://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/(tree|blob)/([a-zA-Z0-9_.-]+)/(.*)",
        re.IGNORECASE
    )

    RAW_BASE = "https://raw.githubusercontent.com"
    API_BASE = "https://api.github.com/repos"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/vnd.github.v3+json",
    }

    def can_handle(self, url: str) -> bool:
        return "github.com" in url and bool(self.URL_REGEX.search(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        m = self.URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"URL is not a GitHub directory or blob path: {url}")

        owner, repo, kind, branch, path = m.groups()
        path = path.strip("/")

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Single Blob / File
        if kind == "blob":
            filename = path.split("/")[-1]
            raw_url = f"{self.RAW_BASE}/{owner}/{repo}/{branch}/{path}"
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
