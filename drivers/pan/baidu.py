"""
Baidu Netdisk (百度网盘) Headless Save-Download-Delete Driver
"""
import json
import re
import time
from typing import Optional, List
import requests

from core.credentials import credentials_manager
from core.exceptions import ExtractionError, AuthenticationRequiredError, CloudDriveError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class BaiduDriver(BaseDriver):
    """
    Automates Baidu Netdisk micro-asset extraction:
    1. Parse share_id / surl & passcode (提取码).
    2. Silent transfer to temporary folder `/_da_temp/`.
    3. Issue direct high-speed download link via PCS API.
    4. Download asset locally with Range resume.
    5. Cleanup hook: automatically delete remote file from `/_da_temp/`.
    """

    name = "baidu"
    category = "pan"

    SHARE_URL_REGEX = re.compile(r"https?://(?:pan|yun)\.baidu\.com/(?:s/1|share/init\?surl=)([a-zA-Z0-9_-]+)")

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://pan.baidu.com/",
        "Accept": "application/json, text/plain, */*",
    }

    def can_handle(self, url: str) -> bool:
        return "pan.baidu.com" in url or "yun.baidu.com" in url

    def _get_cookie(self) -> str:
        cookie = credentials_manager.get_credential("baidu", "cookie")
        if not cookie:
            raise AuthenticationRequiredError(
                "Baidu Netdisk download requires an authenticated session cookie (BDUSS).\n"
                "Auto-fetch options:\n"
                "  1. Grant Full Disk Access to Terminal in macOS System Settings so da can read Chrome cookies automatically\n"
                "  2. Run `da auth baidu` to log in via browser window with 0 manual copying\n"
                "  3. Set environment variable: export DA_BAIDU_COOKIE='BDUSS=...'"
            )
        return cookie

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.SHARE_URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid Baidu Netdisk share link: {url}")
        surl = m.group(1)
        passcode = (password or "").strip()

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Verify Passcode if required
        randsk = ""
        if passcode:
            verify_url = f"https://pan.baidu.com/share/verify?surl={surl}"
            verify_data = {"pwd": passcode, "vcode": "", "vcode_str": ""}
            try:
                vr = session.post(verify_url, data=verify_data, timeout=12)
                v_res = vr.json()
                if v_res.get("errno") == 0:
                    randsk = v_res.get("randsk", "")
                elif v_res.get("errno") == -9:
                    raise ExtractionError("Incorrect Baidu Netdisk 4-digit passcode (提取码错误).")
            except Exception as e:
                if isinstance(e, ExtractionError):
                    raise
                pass

        # 2. Get share page details / wxlist
        list_url = f"https://pan.baidu.com/share/wxlist?channel=weixin&version=2.2.2&op=record&surl={surl}"
        if randsk:
            session.cookies.set("BDCLND", randsk, domain=".pan.baidu.com")

        try:
            lr = session.get(list_url, timeout=15)
            list_data = lr.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Baidu Netdisk share list: {e}")

        if list_data.get("errno") != 0:
            msg = list_data.get("show_msg") or list_data.get("errmsg") or f"errno {list_data.get('errno')}"
            raise CloudDriveError(f"Baidu share access error: {msg}")

        records = list_data.get("data", {}).get("list", [])
        if not records:
            raise ExtractionError("No files found in Baidu share link (empty or expired).")

        target_file = records[0]
        fs_id = target_file.get("fs_id")
        filename = target_file.get("server_filename", "baidu_download.bin")
        filesize = target_file.get("size")
        share_id = list_data.get("data", {}).get("shareid") or target_file.get("share_id")
        uk = list_data.get("data", {}).get("uk") or target_file.get("uk")

        # 3. Requires BDUSS for Silent Transfer & PCS direct link download
        cookie = self._get_cookie()
        user_headers = dict(self.DEFAULT_HEADERS)
        user_headers["Cookie"] = cookie

        # Ensure temp directory `/_da_temp/` exists
        # Execute silent transfer
        transfer_url = f"https://pan.baidu.com/share/transfer?shareid={share_id}&from={uk}"
        transfer_payload = {
            "fsidlist": f"[{fs_id}]",
            "path": "/_da_temp"
        }
        try:
            tr = session.post(transfer_url, data=transfer_payload, headers=user_headers, timeout=15)
            t_res = tr.json()
        except Exception as e:
            raise CloudDriveError(f"Failed to transfer file to Baidu temp folder: {e}")

        # If errno == 12: directory doesn't exist, create it first
        if t_res.get("errno") == 12:
            self._create_temp_folder(session, user_headers)
            tr = session.post(transfer_url, data=transfer_payload, headers=user_headers, timeout=15)
            t_res = tr.json()

        if t_res.get("errno") != 0 and t_res.get("errno") != -8: # -8 means file already exists in dest
            raise CloudDriveError(f"Baidu silent transfer failed: {t_res.get('show_msg', t_res.get('errmsg'))}")

        # 4. Query new file metadata & obtain direct PCS download link (dlink)
        dlink = self._get_dlink(session, user_headers, filename)
        if not dlink:
            raise CloudDriveError(f"Failed to resolve PCS direct download link for `{filename}`.")

        primary_asset = TargetAsset(
            url=dlink,
            filename=filename,
            file_type="primary",
            expected_size=filesize,
            headers={
                "User-Agent": "pan.baidu.com",
                "Cookie": cookie
            }
        )

        return AssetPackage(
            title=filename,
            platform=self.name,
            assets=[primary_asset],
            metadata={
                "original_url": url,
                "author_name": "Baidu Netdisk User",
                "filesize_bytes": filesize,
                "share_id": share_id,
            },
            context={
                "headers": user_headers,
                "filename": filename
            },
            raw_markdown=f"百度网盘无感穿透解析文件: `{filename}`"
        )

    def _create_temp_folder(self, session: requests.Session, headers: dict):
        create_url = "https://pan.baidu.com/api/create"
        payload = {"path": "/_da_temp", "isdir": 1, "size": 0, "block_list": "[]"}
        try:
            session.post(create_url, data=payload, headers=headers, timeout=10)
        except Exception:
            pass

    def _get_dlink(self, session: requests.Session, headers: dict, filename: str) -> Optional[str]:
        """Query `/_da_temp` folder and obtain direct PCS dlink."""
        list_url = "https://pan.baidu.com/api/list?dir=/_da_temp&num=50&order=time&desc=1"
        try:
            r = session.get(list_url, headers=headers, timeout=10)
            data = r.json()
            if data.get("errno") == 0:
                for item in data.get("list", []):
                    if item.get("server_filename") == filename and item.get("dlink"):
                        return item["dlink"]
        except Exception:
            pass
        return None

    def cleanup(self, package: AssetPackage) -> None:
        """Post-download atomic cleanup: delete the file from `/_da_temp/`."""
        filename = package.context.get("filename")
        headers = package.context.get("headers")
        if not filename or not headers:
            return

        del_url = "https://pan.baidu.com/rest/2.0/xpan/file?method=filemanager&opera=delete"
        payload = {"filelist": f'["/_da_temp/{filename}"]'}
        try:
            requests.post(del_url, data=payload, headers=headers, timeout=10)
        except Exception:
            pass
