"""
Shadow Library (Anna's Archive & LibGen) Resilient Driver
Supports direct MD5, Anna/LibGen links, and book title / author / ISBN search with
conversation-aware language prioritization (Chinese / English).
"""
import os
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, quote_plus
import requests
from bs4 import BeautifulSoup

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class ShadowLibraryDriver(BaseDriver):
    """
    High-resilience book extractor for Anna's Archive and LibGen.
    Supports title/author/ISBN search with language prioritization,
    eliminates 60-second timeouts, handles dynamic token keys (ads.php -> get.php),
    and captures companion cover visuals and metadata.
    """

    name = "shadow_library"
    category = "books"

    ANNA_DOMAINS = [
        "annas-archive.li",
        "annas-archive.gl",
        "annas-archive.pk",
        "annas-archive.gd",
        "annas-archive.se",
        "annas-archive.org",
    ]

    LIBGEN_MIRRORS = [
        "https://libgen.la",
        "http://libgen.la",
        "https://libgen.li",
        "https://libgen.is",
        "https://libgen.rs",
    ]

    SEARCH_MIRRORS = [
        "http://libgen.la",
        "http://libgen.li",
        "https://libgen.is",
        "https://libgen.rs",
    ]

    MD5_REGEX = re.compile(r"(?:/md5/|md5:)([a-fA-F0-9]{32})", re.IGNORECASE)
    PLAIN_MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip()
        if not clean:
            return False

        # Explicit book / library search prefixes
        if clean.lower().startswith(("book:", "isbn:", "libgen:", "anna:", "annas:")):
            return True

        if self.MD5_REGEX.search(clean) or self.PLAIN_MD5_REGEX.match(clean):
            return True
        for d in self.ANNA_DOMAINS:
            if d in clean:
                return True
        for m in ["libgen.is", "libgen.rs", "libgen.st", "libgen.la", "libgen.li"]:
            if m in clean:
                return True

        # Non-URL plain text queries (search by title / author)
        # 1. If it has a URL scheme, it is a web URL for another driver, not a plain query
        if re.search(r"^[a-zA-Z0-9+.-]+://", clean):
            return False
        # 2. If it is an existing local file path, leave it to local audio or unpacker
        try:
            if os.path.exists(clean):
                return False
        except Exception:
            pass
        # 3. Exclude DOI identifier pattern (e.g. 10.1038/...)
        if re.match(r"^10\.\d{4,9}/", clean):
            return False
        # 4. Exclude arXiv identifier pattern (e.g. arxiv:...)
        if clean.lower().startswith("arxiv:"):
            return False

        # Any non-URL plain text query with at least 2 chars is considered a book query
        return len(clean) >= 2

    def _extract_md5(self, url: str) -> Optional[str]:
        m = self.MD5_REGEX.search(url)
        if m:
            return m.group(1).lower()
        if self.PLAIN_MD5_REGEX.match(url.strip()):
            return url.strip().lower()
        # Query parameter ?md5=xxxx
        param_match = re.search(r"[?&]md5=([a-fA-F0-9]{32})", url, re.IGNORECASE)
        if param_match:
            return param_match.group(1).lower()
        return None

    @staticmethod
    def _normalize_language_pref(preferred_lang: Optional[str], query: str) -> str:
        """
        Normalize language preference based on conversation context:
        - If user converses in Chinese -> 'zh'
        - If user converses in English -> 'en'
        - If not explicitly set, auto-detect from query content.
        """
        if preferred_lang:
            p = preferred_lang.strip().lower()
            if p in ["zh", "chinese", "cn", "zh-cn", "zh-hans", "中文"]:
                return "zh"
            if p in ["en", "english", "us", "uk", "英文"]:
                return "en"
            return p

        # Auto-detect from query characters
        if re.search(r"[\u4e00-\u9fff]", query):
            return "zh"
        return "en"

    def _search_libgen(self, query: str) -> List[Dict[str, Any]]:
        """Search across LibGen mirrors and return candidate records."""
        headers = dict(self.DEFAULT_HEADERS)
        candidates = []

        for mirror in self.SEARCH_MIRRORS:
            if "is" in mirror or "rs" in mirror:
                search_url = f"{mirror}/search.php?req={quote_plus(query)}&open=0&res=25&view=simple&phrase=1&column=def"
            else:
                search_url = f"{mirror}/index.php?req={quote_plus(query)}"

            try:
                r = requests.get(search_url, headers=headers, timeout=8)
                if r.status_code != 200 or not r.text:
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                table = soup.find("table", {"id": "tablelibgen"}) or soup.find("table", {"class": "c"}) or soup.find("table")
                if not table:
                    continue

                rows = table.find_all("tr")
                for row in rows[1:]:
                    tds = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                    if len(tds) < 8:
                        continue

                    links = [a["href"] for a in row.find_all("a", href=True)]
                    md5_match = re.search(r"md5=([a-fA-F0-9]{32})", " ".join(links))
                    if not md5_match:
                        continue

                    cand_md5 = md5_match.group(1).lower()

                    # Clean title: strip trailing hashes or book IDs
                    raw_title = tds[0]
                    clean_title = re.sub(r"\b(978[0-9-]{10,14}|[0-9]{9,13}|bf\s*\d+|bl\s*\d+)\b", "", raw_title).strip()
                    if not clean_title:
                        clean_title = raw_title

                    candidates.append({
                        "title": clean_title,
                        "author": tds[1] if len(tds) > 1 else "",
                        "publisher": tds[2] if len(tds) > 2 else "",
                        "year": tds[3] if len(tds) > 3 else "",
                        "language": tds[4] if len(tds) > 4 else "",
                        "size": tds[6] if len(tds) > 6 else "",
                        "extension": tds[7].lower() if len(tds) > 7 else "epub",
                        "md5": cand_md5,
                        "source": mirror
                    })

                if candidates:
                    return candidates
            except Exception:
                continue

        return candidates

    @staticmethod
    def _rank_candidates(
        candidates: List[Dict[str, Any]],
        query: str,
        preferred_lang: str = "zh",
        preferred_ext: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Rank search candidates according to user conversation language preference,
        file format quality, and title/author relevance.
        """
        query_words = [w.lower() for w in re.findall(r"[\w\u4e00-\u9fff]+", query)]

        def get_score(c: Dict[str, Any]) -> float:
            score = 0.0
            cand_lang = c.get("language", "").strip().lower()

            # 1. User Conversation Language Priority (Dominant Weight)
            if preferred_lang == "zh":
                if any(k in cand_lang for k in ["chinese", "zh", "mandarin", "中文"]):
                    score += 150.0
                elif any(k in cand_lang for k in ["english", "en"]):
                    score += 20.0
            elif preferred_lang == "en":
                if any(k in cand_lang for k in ["english", "en"]):
                    score += 150.0
                elif any(k in cand_lang for k in ["chinese", "zh"]):
                    score += 20.0
            else:
                if preferred_lang in cand_lang:
                    score += 150.0

            # 2. File Format / Reading Quality Priority
            ext = c.get("extension", "").strip().lower()
            if preferred_ext and ext == preferred_ext.lower():
                score += 80.0
            else:
                ext_scores = {
                    "epub": 40.0,
                    "pdf": 30.0,
                    "azw3": 25.0,
                    "mobi": 20.0,
                    "txt": 10.0,
                }
                score += ext_scores.get(ext, 5.0)

            # 3. Title & Author Match Relevance
            title = c.get("title", "").lower()
            author = c.get("author", "").lower()
            for w in query_words:
                if w in title:
                    score += 20.0
                if w in author:
                    score += 10.0

            # 4. Publication recency (tie-breaker)
            year_str = re.search(r"\b(19\d\d|20\d\d)\b", c.get("year", ""))
            if year_str:
                try:
                    score += min(max(int(year_str.group(1)) - 1900, 0), 130) * 0.05
                except Exception:
                    pass

            return score

        return sorted(candidates, key=get_score, reverse=True)

    def _extract_by_search(self, query: str, preferred_lang: Optional[str] = None, **kwargs) -> AssetPackage:
        """Execute search, prioritize by conversation language, and resolve download."""
        lang = self._normalize_language_pref(preferred_lang, query)
        candidates = self._search_libgen(query)

        if not candidates:
            lang_display = "中文 (Chinese)" if lang == "zh" else "英文 (English)"
            raise ExtractionError(f"未找到与关键词「{query}」相关的电子书资源 (偏好语言: {lang_display})")

        ranked_candidates = self._rank_candidates(candidates, query, preferred_lang=lang)

        # Iterate top candidates and resolve the first available direct mirror
        for cand in ranked_candidates:
            cand_md5 = cand.get("md5")
            if not cand_md5:
                continue

            pkg = self._resolve_via_libgen(cand_md5) or self._resolve_via_anna(cand_md5, f"search:{query}")
            if pkg:
                # Fill missing title / author from search metadata if unresolved
                if pkg.title.startswith("Book_") or pkg.title == "Unknown Book":
                    if cand.get("title"):
                        pkg.title = cand["title"]
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", pkg.title)
                        ext = cand.get("extension", "epub")
                        pkg.assets[0].filename = f"{safe_title}.{ext}"

                pkg.metadata["search_query"] = query
                pkg.metadata["preferred_lang"] = lang
                pkg.metadata["search_candidate"] = cand
                pkg.metadata["total_candidates_found"] = len(candidates)

                lang_tag = "中文" if lang == "zh" else "英文"
                pkg.raw_markdown = (
                    f"### 📚 电子书检索与下载产物\n"
                    f"- **检索关键词**：`{query}` (基于对话语言设定优先级：{lang_tag})\n"
                    f"- **匹配书名**：{cand.get('title') or pkg.title}\n"
                    f"- **作者**：{cand.get('author') or pkg.metadata.get('author_name', '未知')}\n"
                    f"- **版本语言**：{cand.get('language') or '未知'}\n"
                    f"- **文件格式**：{cand.get('extension', '').upper()}\n"
                    f"- **MD5 校验**：`{cand_md5}`\n"
                )
                return pkg

        raise ExtractionError(f"找到 {len(candidates)} 个候选版本，但所有镜像直链均未能成功解析下载")

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
        md5_hash = self._extract_md5(clean)

        # If not an explicit MD5, treat as a book search query
        if not md5_hash:
            query = clean
            for prefix in ("book:", "isbn:", "libgen:", "anna:", "annas:"):
                if query.lower().startswith(prefix):
                    query = query[len(prefix):].strip()
                    break

            kwargs_copy = dict(kwargs)
            preferred_lang = kwargs_copy.pop("preferred_lang", None) or kwargs_copy.pop("lang", None)
            return self._extract_by_search(query, preferred_lang=preferred_lang, **kwargs_copy)

        # 1. Resolve via LibGen ads.php -> get.php key mechanism
        resolved = self._resolve_via_libgen(md5_hash)
        if resolved:
            return resolved

        # 2. Fallback to Anna's Archive page scrape
        resolved_anna = self._resolve_via_anna(md5_hash, url)
        if resolved_anna:
            return resolved_anna

        raise ExtractionError(f"Unable to find working download mirror for book MD5: {md5_hash}")

    def _resolve_via_libgen(self, md5: str) -> Optional[AssetPackage]:
        headers = dict(self.DEFAULT_HEADERS)
        for mirror in self.LIBGEN_MIRRORS:
            ads_url = f"{mirror}/ads.php?md5={md5}"
            try:
                r = requests.get(ads_url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                html = r.text

                # Parse key-based download link
                get_match = re.search(r'href="(get\.php\?md5=[^"]+)"', html)
                if not get_match:
                    continue

                get_rel_url = get_match.group(1)
                direct_url = f"{mirror}/{get_rel_url}"

                # Extract metadata
                title = "Unknown Book"
                author = "Unknown Author"
                ext = "pdf"

                title_match = re.search(r"Title:\s*([^<]+)", html) or re.search(r"<h1>([^<]+)</h1>", html)
                if title_match:
                    title = title_match.group(1).strip()

                author_match = re.search(r"Author\(s\):\s*([^<]+)", html)
                if author_match:
                    author = author_match.group(1).strip()

                ext_match = re.search(r"Extension:\s*([a-zA-Z0-9]+)", html)
                if ext_match:
                    ext = ext_match.group(1).strip().lower()

                # Clean filename
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
                primary_filename = f"{safe_title}.{ext}"

                # NOTE: We deliberately do NOT perform pre-flight HEAD requests here.
                # CDNs like cdn3.booksdl.lc hang indefinitely on HEAD requests, burning the one-time token.
                # The streaming GET in Fetcher will read Content-Length on the first response frame safely.
                primary_asset = TargetAsset(
                    url=direct_url,
                    filename=primary_filename,
                    file_type="primary",
                    expected_size=None,
                    headers={"User-Agent": headers["User-Agent"], "Referer": ads_url}
                )

                assets = [primary_asset]

                # Check for cover image in ads.php
                cover_match = re.search(r'<img\s+[^>]*src="(/covers/[^"]+)"', html)
                if cover_match:
                    cover_url = f"{mirror}{cover_match.group(1)}"
                    assets.append(TargetAsset(
                        url=cover_url,
                        filename="cover.jpg",
                        file_type="cover",
                        headers={"User-Agent": headers["User-Agent"], "Referer": ads_url}
                    ))

                return AssetPackage(
                    title=title,
                    platform=self.name,
                    assets=assets,
                    metadata={
                        "original_url": ads_url,
                        "md5": md5,
                        "author_name": author,
                        "author": {"id": "", "name": author},
                        "extension": ext,
                        "mirror": mirror
                    },
                    raw_markdown=f"### 书籍信息\n- **书名**：{title}\n- **作者**：{author}\n- **格式**：{ext.upper()}\n- **MD5**：`{md5}`"
                )

            except Exception:
                continue

        return None

    def _resolve_via_anna(self, md5: str, original_url: str) -> Optional[AssetPackage]:
        headers = dict(self.DEFAULT_HEADERS)
        for mirror in self.ANNA_DOMAINS:
            anna_url = f"https://{mirror}/md5/{md5}"
            try:
                r = requests.get(anna_url, headers=headers, timeout=12)
                if r.status_code != 200:
                    continue
                html = r.text

                # Extract Title
                title = f"Book_{md5[:8]}"
                title_match = re.search(r'<div class="text-2xl font-bold[^>]*>([^<]+)</div>', html) or re.search(r"<title>([^<]+)</title>", html)
                if title_match:
                    title = title_match.group(1).strip()

                # Extract LibGen download links embedded in Anna page
                libgen_links = re.findall(r'href="(https?://[^"]*(?:libgen|get\.php)[^"]*)"', html)
                if libgen_links:
                    chosen_link = libgen_links[0]
                    ext = "pdf"
                    if ".epub" in chosen_link or "epub" in html.lower():
                        ext = "epub"

                    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
                    filename = f"{safe_title}.{ext}"

                    primary_asset = TargetAsset(
                        url=chosen_link,
                        filename=filename,
                        file_type="primary",
                        headers={"User-Agent": headers["User-Agent"], "Referer": anna_url}
                    )

                    return AssetPackage(
                        title=title,
                        platform=self.name,
                        assets=[primary_asset],
                        metadata={
                            "original_url": original_url,
                            "md5": md5,
                            "anna_mirror": mirror
                        },
                        raw_markdown=f"### Anna's Archive 解析产物\n- **书名**：{title}\n- **MD5**：`{md5}`"
                    )

            except Exception:
                continue

        return None
