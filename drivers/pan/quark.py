"""
Quark Cloud Drive (夸克网盘) Headless Silent Save-Download-Delete Driver
"""
import re
import time
import uuid
from typing import Optional, List
import requests

from core.credentials import credentials_manager
from core.exceptions import ExtractionError, AuthenticationRequiredError, CloudDriveError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class QuarkDriver(BaseDriver):
    """
    Penetrates Quark Cloud Drive強制转存 restrictions via headless API lifecycle:
    1. Parse share_id / passcode & query file metadata.
    2. Silent transfer to temporary folder `/_da_temp/`.
    3. Issue high-speed direct CDN URL via /file/download.
    4. Download asset locally.
    5. Cleanup hook: automatically delete remote file from `/_da_temp/`.
    """

    name = "quark"
    category = "pan"

    SHARE_URL_REGEX = re.compile(r"https?://pan\.quark\.cn/s/([a-zA-Z0-9]+)")
    API_BASE = "https://drive.quark.cn/1/clouddrive"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Referer": "https://pan.quark.cn/",
        "Origin": "https://pan.quark.cn",
        "Accept": "application/json, text/plain, */*",
    }

    def can_handle(self, url: str) -> bool:
        return bool(self.SHARE_URL_REGEX.search(url))

    def _get_cookie(self) -> str:
        cookie = credentials_manager.get_credential("quark", "cookie")
        if not cookie:
            raise AuthenticationRequiredError(
                "Quark Cloud Drive download requires authentication cookie.\n"
                "Please configure via one of the following methods:\n"
                "  1. Set environment variable: export DA_QUARK_COOKIE='<your_cookie>'\n"
                "  2. Add to config/credentials.yaml under pan.quark.cookie\n"
                "  3. Save to macOS Keychain under service 'quark'"
            )
        return cookie

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        match = self.SHARE_URL_REGEX.search(url)
        if not match:
            raise ExtractionError(f"Invalid Quark share link: {url}")
        pwd_id = match.group(1)
        passcode = password or ""

        cookie = self._get_cookie()
        headers = dict(self.DEFAULT_HEADERS)
        headers["Cookie"] = cookie

        # 1. Query Share File Metadata
        detail_url = f"{self.API_BASE}/share/sharepage/detail"
        params = {"pwd_id": pwd_id, "passcode": passcode, "pr": "ucpro", "fr": "pc"}
        try:
            r = requests.get(detail_url, params=params, headers=headers, timeout=15)
            data = r.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Quark share details: {e}")

        if data.get("status") != 200:
            msg = data.get("message", "Unknown error")
            raise CloudDriveError(f"Quark API query error ({data.get('status')}): {msg}")

        share_data = data.get("data", {})
        file_list = share_data.get("list", [])
        if not file_list:
            raise ExtractionError(f"No files found in Quark share link (expired or empty).")

        # Pick target file (first file in share)
        target_item = file_list[0]
        share_fid = target_item.get("fid")
        filename = target_item.get("file_name", "quark_download.bin")
        filesize = target_item.get("size")

        if kwargs.get("inspect_only"):
            return AssetPackage(title=filename, platform=self.name, assets=[TargetAsset(
                url="", filename=filename, expected_size=filesize,
            )], metadata={"original_url": url, "requires_transfer": True,
                         "direct_url_available": False})

        # 2. Get or create temporary folder `/_da_temp/`
        temp_dir_fid = self._get_or_create_temp_folder(headers)

        owned_package = AssetPackage(title=filename, platform=self.name, context={"owned_temp_dir": temp_dir_fid, "headers": headers})
        try:
            # 3. Silent transfer to temporary folder
            save_url = f"{self.API_BASE}/share/sharepage/save?pr=ucpro&fr=pc"
            save_payload = {
                "pwd_id": pwd_id,
                "passcode": passcode,
                "fid_list": [share_fid],
                "to_pdir_fid": temp_dir_fid
            }
            try:
                save_r = requests.post(save_url, json=save_payload, headers=headers, timeout=20)
                save_resp = save_r.json()
            except Exception as e:
                raise CloudDriveError(f"Failed to execute silent transfer on Quark: {e}")

            if save_resp.get("status") != 200:
                raise CloudDriveError(f"Quark silent transfer failed: {save_resp.get('message')}")

            task_id = save_resp.get("data", {}).get("task_id")
            saved_fid = self._poll_task_completion(task_id, temp_dir_fid, filename, headers)

            # 4. Request direct high-speed CDN download URL
            dl_url_endpoint = f"{self.API_BASE}/file/download?pr=ucpro&fr=pc"
            dl_payload = {"fids": [saved_fid]}
            try:
                dl_r = requests.post(dl_url_endpoint, json=dl_payload, headers=headers, timeout=15)
                dl_resp = dl_r.json()
            except Exception as e:
                raise CloudDriveError(f"Failed to issue direct download link from Quark: {e}")

            if dl_resp.get("status") != 200:
                raise CloudDriveError(f"Failed to get download URL: {dl_resp.get('message')}")

            dl_data = dl_resp.get("data", [])
            if not dl_data or "download_url" not in dl_data[0]:
                raise CloudDriveError("Quark did not return a valid download_url.")

            direct_download_url = dl_data[0]["download_url"]

            primary_asset = TargetAsset(
                url=direct_download_url,
                filename=filename,
                file_type="primary",
                expected_size=filesize,
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": "https://pan.quark.cn/"}
            )

            return AssetPackage(
                title=filename,
                platform=self.name,
                assets=[primary_asset],
                metadata={
                    "original_url": url,
                    "author_name": share_data.get("share_title", "Quark User"),
                    "filesize_bytes": filesize,
                    "quark_fid": saved_fid,
                    "temp_dir_fid": temp_dir_fid
                },
                context={
                    "quark_fid": saved_fid,
                    "headers": headers,
                    "owned_temp_dir": temp_dir_fid,
                },
                raw_markdown=f"夸克网盘无感穿透解析文件: `{filename}`"
            )
        except BaseException as exc:
            self.cleanup_after_error(owned_package, exc)
            raise

    def _get_or_create_temp_folder(self, headers: dict) -> str:
        """Create a task-owned directory; never reuse a user directory or root."""
        create_url = f"{self.API_BASE}/file?pr=ucpro&fr=pc"
        payload = {"pdir_fid": "0", "file_name": "_da_temp_" + uuid.uuid4().hex, "dir": True}
        try:
            cr = requests.post(create_url, json=payload, headers=headers, timeout=10)
            cdata = cr.json()
            fid = cdata.get("data", {}).get("fid")
            if cdata.get("status") == 200 and fid and str(fid) != "0":
                return fid
        except Exception as exc:
            raise CloudDriveError("Could not create an owned Quark temporary directory") from exc
        raise CloudDriveError("Quark refused creation of an owned temporary directory")

    def _poll_task_completion(self, task_id: Optional[str], temp_dir_fid: str, filename: str, headers: dict) -> str:
        """Poll task until transferred file fid is visible in temp folder."""
        # If task_id provided, query task status
        for _ in range(10):
            list_url = f"{self.API_BASE}/file/sort?pr=ucpro&fr=pc"
            params = {"pdir_fid": temp_dir_fid, "_page": 1, "_size": 20}
            try:
                r = requests.get(list_url, params=params, headers=headers, timeout=10)
                data = r.json()
                if data.get("status") == 200:
                    for item in data.get("data", {}).get("list", []):
                        if item.get("file_name") == filename:
                            return item["fid"]
            except Exception:
                pass
            time.sleep(1.0)

        raise CloudDriveError(f"Timed out waiting for file `{filename}` to appear in Quark temp folder.")

    def cleanup(self, package: AssetPackage) -> None:
        """
        Post-download atomic cleanup: silently destroy the cloud copy in `/_da_temp/`.
        Guarantees zero residual junk in user's cloud drive.
        """
        saved_fid = package.context.get("owned_temp_dir")
        headers = package.context.get("headers")
        if not saved_fid or str(saved_fid) == "0" or not headers:
            return

        del_url = f"{self.API_BASE}/file/delete?pr=ucpro&fr=pc"
        payload = {"action_type": 2, "file_ids": [saved_fid]}
        response = requests.post(del_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        if response.json().get("status") != 200:
            raise CloudDriveError("Quark temporary directory cleanup was not confirmed")
