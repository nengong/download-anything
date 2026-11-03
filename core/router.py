"""
Smart Router and Dirty Input Cleaner
"""
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
from urllib.parse import urlparse, parse_qs

from core.exceptions import UrlNotSupportedError
from drivers.base import BaseDriver

@dataclass
class CleanInput:
    url: str
    password: Optional[str] = None
    original_text: str = ""
    extra_params: dict = None

class Router:
    """Intelligent input purifier and driver dispatcher."""

    URL_PATTERN = re.compile(r"https?://[a-zA-Z0-9][-a-zA-Z0-9+&@#/%?=~_|!:,.;]*[a-zA-Z0-9+&@#/%=~_|]")
    MD5_PATTERN = re.compile(r"(?:md5[:\s=]+)?([a-fA-F0-9]{32})\b")
    PASSWORD_PATTERN = re.compile(r"(?:提取码|密码|访问码|code|pwd)[：:\s]*([a-zA-Z0-9]{4,8})", re.IGNORECASE)

    def __init__(self, drivers: Optional[List[BaseDriver]] = None):
        self.drivers: List[BaseDriver] = drivers or []

    def register_driver(self, driver: BaseDriver):
        """Register a driver into the routing table."""
        self.drivers.append(driver)

    def clean_input(self, raw_text: str, explicit_password: Optional[str] = None) -> CleanInput:
        """
        Purify dirty link input: strips Chinese ads, emojis, spaces,
        and extracts canonical URL and embedded passwords/passcodes.
        """
        text = raw_text.strip()
        found_pwd = explicit_password

        # 1. Look for embedded password/passcode in text
        if not found_pwd:
            pwd_match = self.PASSWORD_PATTERN.search(text)
            if pwd_match:
                found_pwd = pwd_match.group(1).strip()

        # 2. Extract URL
        url_match = self.URL_PATTERN.search(text)
        if url_match:
            clean_url = url_match.group(0).strip()
            # If password wasn't found in text, check URL query params (e.g. ?pwd=xxxx)
            if not found_pwd:
                parsed = urlparse(clean_url)
                qs = parse_qs(parsed.query)
                for key in ("pwd", "password", "code", "passcode"):
                    if key in qs and qs[key]:
                        found_pwd = qs[key][0]
                        break

            return CleanInput(
                url=clean_url,
                password=found_pwd,
                original_text=raw_text,
                extra_params={}
            )

        # 3. Check for standalone MD5 hash (common for shadow library / book requests)
        md5_match = self.MD5_PATTERN.search(text)
        if md5_match and len(text.strip()) <= 40:
            md5_hash = md5_match.group(1).lower()
            return CleanInput(
                url=f"md5:{md5_hash}",
                password=None,
                original_text=raw_text,
                extra_params={"md5": md5_hash}
            )

        # Fallback to the raw string if no URL regex matched
        return CleanInput(
            url=text,
            password=found_pwd,
            original_text=raw_text,
            extra_params={}
        )

    def find_driver(self, clean_input: CleanInput) -> BaseDriver:
        """Find a suitable driver capable of handling the cleaned URL."""
        for driver in self.drivers:
            if driver.can_handle(clean_input.url):
                return driver
        raise UrlNotSupportedError(f"No driver found to handle URL: {clean_input.url}")

    def route(self, raw_text: str, explicit_password: Optional[str] = None) -> Tuple[BaseDriver, CleanInput]:
        """Complete pipeline: clean dirty input and dispatch to matched driver."""
        cleaned = self.clean_input(raw_text, explicit_password)
        driver = self.find_driver(cleaned)
        return driver, cleaned
