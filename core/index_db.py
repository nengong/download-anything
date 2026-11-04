"""
Local Deduplication and Asset Index Database
Built on Python standard sqlite3 (zero extra dependencies).
Prevents redundant downloads, tracks SHA256 checksums, and delivers instant cache hits.
"""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

class AssetIndexDB:
    """Lightweight SQLite-backed download index preventing duplicate downloads."""

    DB_DIR = Path.home() / ".download-anything"
    DB_PATH = DB_DIR / "index.db"

    @classmethod
    def _get_connection(cls) -> sqlite3.Connection:
        cls.DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(cls.DB_PATH))
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS asset_index (
                    url_key TEXT PRIMARY KEY,
                    original_url TEXT,
                    title TEXT,
                    platform TEXT,
                    output_dir TEXT,
                    primary_file TEXT,
                    size_bytes INTEGER,
                    sha256 TEXT,
                    sidecars_json TEXT,
                    created_at TEXT
                )
            """)
        return conn

    @classmethod
    def _compute_key(cls, url: str) -> str:
        clean = url.strip().lower()
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    @classmethod
    def query(cls, url: str) -> Optional[Dict[str, Any]]:
        """
        Check if target URL has already been downloaded and verified on disk.
        Returns dict if valid cache hit, or None.
        """
        key = cls._compute_key(url)
        try:
            with cls._get_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM asset_index WHERE url_key = ?",
                    (key,)
                )
                row = cur.fetchone()
                if row:
                    primary_path = Path(row["primary_file"])
                    # Check if file still exists on disk and is non-empty
                    if primary_path.exists() and primary_path.stat().st_size > 0:
                        sidecars = {}
                        if row["sidecars_json"]:
                            try:
                                sidecars = json.loads(row["sidecars_json"])
                            except Exception:
                                pass
                        return {
                            "status": "cached",
                            "cached": True,
                            "platform": row["platform"],
                            "title": row["title"],
                            "output_dir": row["output_dir"],
                            "primary_asset": row["primary_file"],
                            "size_bytes": row["size_bytes"],
                            "sha256": row["sha256"],
                            "sidecars": sidecars,
                            "created_at": row["created_at"],
                            "verification": {
                                "valid": True,
                                "detected_type": primary_path.suffix.lstrip(".").lower() or "binary",
                                "details": {"cached_from": row["created_at"]}
                            }
                        }
        except Exception:
            pass
        return None

    @classmethod
    def record(
        cls,
        url: str,
        platform: str,
        title: str,
        output_dir: Path,
        primary_file: Path,
        size_bytes: int,
        sidecars: Optional[Dict[str, str]] = None
    ):
        """Save a successful download to the index."""
        key = cls._compute_key(url)
        # Compute sha256 of primary file for integrity
        sha256_hash = ""
        try:
            h = hashlib.sha256()
            with open(primary_file, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            sha256_hash = h.hexdigest()
        except Exception:
            pass

        now = datetime.now().isoformat()
        sidecars_str = json.dumps(sidecars or {}, ensure_ascii=False)

        try:
            with cls._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO asset_index (
                        url_key, original_url, title, platform, output_dir, primary_file,
                        size_bytes, sha256, sidecars_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    key, url, title, platform, str(output_dir.resolve()),
                    str(primary_file.resolve()), size_bytes, sha256_hash,
                    sidecars_str, now
                ))
        except Exception:
            pass
