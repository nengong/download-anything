"""
Base Driver Specification and Data Structures
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

@dataclass
class TargetAsset:
    """Represents an individual asset within a package to be downloaded."""
    url: str
    filename: str
    file_type: str = "primary"  # 'primary', 'cover', 'subtitle', 'sidecar_text', 'extra'
    expected_size: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    cookies: Optional[Dict[str, str]] = None
    local_path: Optional[Path] = None
    downloaded_bytes: int = 0
    verified: bool = False
    # "http": the CLI fetcher downloads `url` directly.
    # "ytdlp": yt-dlp owns the transfer (needed for HLS/DASH manifests and merging).
    download_strategy: str = "http"
    download_options: Dict[str, Any] = field(default_factory=dict)
    cookie_jar: Any = None  # Preserve Domain/Path/Secure; never serialize as headers.
    local_source: Optional[Path] = None  # Set only by an explicit local-file driver.

AssetFile = TargetAsset

@dataclass
class AssetPackage:
    """Represents a complete structured asset package extracted from a source."""
    title: str
    platform: str
    original_url: Optional[str] = None
    assets: List[TargetAsset] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_markdown: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def primary_asset(self) -> Optional[TargetAsset]:
        for asset in self.assets:
            if asset.file_type == "primary":
                return asset
        return self.assets[0] if self.assets else None

class BaseDriver(ABC):
    """Abstract base class for all platform drivers."""
    name: str = "base"
    category: str = "general"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this driver can handle the given clean URL."""
        pass

    @abstractmethod
    def extract(self, url: str, **kwargs) -> AssetPackage:
        """
        Execute API/page analysis and reverse resolution.
        Returns the structured AssetPackage containing direct URLs and metadata.
        """
        pass

    def cleanup(self, package: AssetPackage) -> None:
        """
        Optional post-download cleanup hook.
        Used to silently delete cloud drive temporary files (e.g., Quark, Baidu).
        """
        pass

    def download_primary(
        self,
        asset: TargetAsset,
        dest_path: Path,
        max_bytes: int,
        progress_callback=None,
    ) -> Tuple[int, Path]:
        """
        Optional native downloader for assets whose transfer cannot be expressed
        as a single HTTP request (e.g. HLS/DASH manifests).

        Return ``(saved_byte_count, final_path)``, or raise if the transfer fails.
        ``final_path`` normally equals ``dest_path`` but may differ when the
        downloader produces a different container than the declared extension.
        """
        raise NotImplementedError(f"{self.name} does not provide a native downloader")

    def cleanup_after_error(self, package: AssetPackage, error: BaseException) -> None:
        """Preserve the original failure while surfacing any cleanup failure."""
        try:
            self.cleanup(package)
        except Exception as cleanup_error:
            details = dict(getattr(error, "details", {}) or {})
            details["cleanup_error"] = str(cleanup_error)
            error.details = details
