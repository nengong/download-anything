"""
Universal Academic Paper & Chinese Journal DOI Extractor Driver
Supports Crossref metadata resolution, automated BibTeX citation伴生, and OpenAccess PDF retrieval.
"""
import re
import base64
from typing import Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError

class DOIDriver(BaseDriver):
    """Driver for extracting Chinese and International academic papers via DOI."""

    DOI_REGEX = re.compile(
        r"(?:https?://(?:dx\.)?doi\.org/|doi:)?(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)",
        re.IGNORECASE
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.DOI_REGEX.search(url.strip()))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.DOI_REGEX.search(url.strip())
        if not m:
            raise ExtractionError(f"Invalid DOI format: {url}")
        doi = m.group(1).rstrip(".")
        canonical_url = f"https://doi.org/{doi}"

        headers = {
            "User-Agent": "Download-Anything/0.1.0 (mailto:agent@antigravity.local)"
        }

        # 1. Fetch official BibTeX citation
        bibtex_str = ""
        try:
            r_bib = requests.get(canonical_url, headers={"Accept": "application/x-bibtex", "User-Agent": headers["User-Agent"]}, timeout=8)
            if r_bib.status_code == 200 and r_bib.text.strip().startswith("@"):
                bibtex_str = r_bib.text.strip()
        except Exception:
            pass

        # 2. Fetch metadata from Crossref API
        title = f"paper_{doi.replace('/', '_')}"
        authors = []
        journal = ""
        abstract = ""
        published_date = ""

        try:
            r_meta = requests.get(f"https://api.crossref.org/works/{doi}", headers=headers, timeout=8)
            if r_meta.status_code == 200:
                msg = r_meta.json().get("message", {})
                titles = msg.get("title", [])
                if titles:
                    title = titles[0]
                for a in msg.get("author", []):
                    name = f"{a.get('family', '')} {a.get('given', '')}".strip()
                    if name:
                        authors.append(name)
                containers = msg.get("container-title", [])
                if containers:
                    journal = containers[0]
                abstract = msg.get("abstract") or ""
                # Clean JATS XML tags if present
                if abstract and "<" in abstract:
                    abstract = BeautifulSoup(abstract, "html.parser").get_text().strip()
                date_parts = msg.get("published-print", {}).get("date-parts") or msg.get("published-online", {}).get("date-parts")
                if date_parts and date_parts[0]:
                    published_date = "-".join(str(p).zfill(2) for p in date_parts[0])
        except Exception:
            pass

        # 3. Locate Full-Text PDF URL
        pdf_url = None
        # Try Unpaywall
        try:
            r_oa = requests.get(f"https://api.unpaywall.org/v2/{doi}?email=da@agent.local", timeout=6)
            if r_oa.status_code == 200:
                oa_data = r_oa.json()
                best_loc = oa_data.get("best_oa_location") or {}
                if best_loc.get("url_for_pdf"):
                    pdf_url = best_loc["url_for_pdf"]
        except Exception:
            pass

        # Try Sci-Hub mirror fallback if Unpaywall did not return direct PDF
        if not pdf_url:
            sci_hub_mirrors = ["https://sci-hub.se", "https://sci-hub.ru", "https://sci-hub.st"]
            for mirror in sci_hub_mirrors:
                try:
                    r_sh = requests.get(f"{mirror}/{doi}", headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                    if r_sh.status_code == 200:
                        soup = BeautifulSoup(r_sh.text, "html.parser")
                        # Look for iframe#pdf or embed#pdf
                        el = soup.select_one("iframe#pdf, embed#pdf, #buttons a")
                        if el and el.get("src"):
                            src = el["src"]
                            if src.startswith("//"):
                                pdf_url = "https:" + src
                            elif src.startswith("/"):
                                pdf_url = mirror + src
                            else:
                                pdf_url = src
                            break
                        elif el and el.get("href"):
                            href = el["href"]
                            pdf_url = href if href.startswith("http") else (mirror + href)
                            break
                except Exception:
                    continue

        if not pdf_url:
            raise ExtractionError(
                f"No open-access full-text PDF found for DOI '{doi}'.\n"
                f"Paper: {title}\n"
                f"Publisher site: {canonical_url}\n"
                f"Tip: This paper may require institutional/university library access (知网/高校VPN)."
            )

        assets = [
            AssetFile(
                filename="content.pdf",
                url=pdf_url,
                file_type="primary",
                headers={"User-Agent": "Mozilla/5.0"}
            )
        ]

        # Companion BibTeX citation file
        if bibtex_str:
            b64_bib = base64.b64encode(bibtex_str.encode("utf-8")).decode("utf-8")
            assets.append(
                AssetFile(
                    filename="citation.bib",
                    url=f"data:text/plain;charset=utf-8;base64,{b64_bib}",
                    file_type="companion",
                    expected_size=len(bibtex_str.encode("utf-8"))
                )
            )

        sidecar_text = (
            f"# {title}\n\n"
            f"**DOI**: [{doi}]({canonical_url})\n\n"
            f"**Authors**: {', '.join(authors) if authors else 'Unknown'}\n\n"
            f"**Journal**: {journal}\n\n"
            f"**Published**: {published_date}\n\n"
        )
        if abstract:
            sidecar_text += f"## Abstract\n\n{abstract}\n\n"
        if bibtex_str:
            sidecar_text += f"## BibTeX Citation\n\n```bibtex\n{bibtex_str}\n```\n"

        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {
                "id": doi,
                "name": authors[0] if authors else "Academic Author",
            },
            "created_at": published_date,
            "metrics": {
                "authors_count": len(authors),
            },
            "sidecar_text": sidecar_text,
        }

        return AssetPackage(
            platform="doi",
            title=title,
            original_url=canonical_url,
            assets=assets,
            metadata=metadata
        )
