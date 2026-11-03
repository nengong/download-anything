"""
Intelligent Domestic Mirror Routing and Failover Engine
Seamlessly routes foreign assets (GitHub, arXiv, Hugging Face, Shadow Libraries)
through high-speed domestic mirror stations when direct connections are slow or blocked.
"""
import re
from typing import Optional, List, Dict
from urllib.parse import urlparse

class MirrorRouter:
    """Manages domestic mirror resolution and fast failover routing."""

    # 1. GitHub Raw and Release Mirrors
    GITHUB_MIRRORS = [
        "https://gh-proxy.com/",
        "https://ghfast.top/",
        "https://mirror.ghproxy.com/",
    ]

    # 2. arXiv Domestic Mirrors
    ARXIV_CN_HOST = "cn.arxiv.org"

    # 3. Hugging Face Domestic Mirrors
    HF_MIRROR_HOST = "hf-mirror.com"

    # 4. Shadow Library Fallbacks
    LIBGEN_DOMAINS = ["libgen.is", "libgen.rs", "libgen.st", "libgen.la"]
    ANNAS_DOMAINS = ["annas-archive.li", "annas-archive.se", "annas-archive.pk", "annas-archive.gl"]

    @classmethod
    def get_mirrors(cls, url: str) -> List[str]:
        """
        Generate candidate mirror URLs for a foreign target link,
        ordered by domestic speed and reliability.
        """
        mirrors: List[str] = []
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path

        # Case A: GitHub raw or release download
        if "raw.githubusercontent.com" in host or ("github.com" in host and ("/releases/download/" in path or "/archive/" in path)):
            for prefix in cls.GITHUB_MIRRORS:
                mirrors.append(f"{prefix.rstrip('/')}/{url.lstrip('/')}")

        # Case B: arXiv paper
        elif "arxiv.org" in host and cls.ARXIV_CN_HOST not in host:
            cn_url = url.replace("arxiv.org", cls.ARXIV_CN_HOST)
            mirrors.append(cn_url)

        # Case C: Hugging Face
        elif "huggingface.co" in host:
            hf_url = url.replace("huggingface.co", cls.HF_MIRROR_HOST)
            mirrors.append(hf_url)

        # Case D: Library Genesis
        elif any(lg in host for lg in cls.LIBGEN_DOMAINS):
            current_domain = host
            for target_domain in cls.LIBGEN_DOMAINS:
                if target_domain not in current_domain:
                    mirrors.append(url.replace(current_domain, target_domain))

        # Case E: Anna's Archive
        elif any(aa in host for aa in cls.ANNAS_DOMAINS) or "annas-archive.org" in host:
            current_domain = host
            for target_domain in cls.ANNAS_DOMAINS:
                if target_domain not in current_domain:
                    mirrors.append(url.replace(current_domain, target_domain))

        return mirrors

    @classmethod
    def rewrite_to_fastest_mirror(cls, url: str) -> str:
        """
        Force-rewrite a URL to the best-known domestic mirror if available.
        """
        candidates = cls.get_mirrors(url)
        return candidates[0] if candidates else url
