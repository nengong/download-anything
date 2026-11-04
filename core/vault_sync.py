"""
Downstream Knowledge-Base Closed-Loop Sync Engine
Directly syncs extracted assets, Markdown notes, and covers into Obsidian Vaults and Notion databases.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests

class VaultSync:
    """Seamless bridge into personal knowledge bases (Obsidian & Notion)."""

    COMMON_OBSIDIAN_PATHS = [
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
        Path.home() / "Documents" / "Vault",
        Path.home() / "Vault"
    ]

    @classmethod
    def resolve_obsidian_vault(cls, custom_path: Optional[str] = None) -> Optional[Path]:
        """Detect or validate an Obsidian vault directory."""
        if custom_path:
            p = Path(custom_path).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p

        # Check environment variables
        env_val = os.getenv("OBSIDIAN_VAULT_PATH") or os.getenv("DA_VAULT_PATH")
        if env_val:
            p = Path(env_val).expanduser().resolve()
            if p.exists():
                return p

        # Check common locations
        for candidate in cls.COMMON_OBSIDIAN_PATHS:
            if candidate.exists() and (candidate / ".obsidian").exists():
                return candidate
            if candidate.exists() and candidate.is_dir():
                return candidate

        return None

    @classmethod
    def sync_to_obsidian(
        cls,
        asset_dir: Path,
        vault_path: Optional[str] = None,
        title: str = "Note",
        platform: str = "web",
        original_url: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Path]:
        """
        Sync asset directory and inject frontmatter-rich Markdown note into Obsidian.
        Returns the destination note path inside the vault.
        """
        vault = cls.resolve_obsidian_vault(vault_path)
        if not vault:
            return None

        # Create Inbox folder in Vault
        inbox_dir = vault / "DownloadAnything" / asset_dir.name
        inbox_dir.mkdir(parents=True, exist_ok=True)

        dest_note = None

        # Copy all asset files (images, covers, media, markdown)
        for item in asset_dir.iterdir():
            if item.is_file():
                target = inbox_dir / item.name
                shutil.copy2(item, target)
                if item.suffix.lower() == ".md":
                    dest_note = target

        # If markdown note exists, inject YAML frontmatter for Obsidian Dataview / Graph
        if dest_note and dest_note.exists():
            content = dest_note.read_text(encoding="utf-8")
            if not content.startswith("---"):
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                frontmatter = (
                    f"---\n"
                    f"title: \"{title}\"\n"
                    f"platform: \"{platform}\"\n"
                    f"source: \"{original_url}\"\n"
                    f"imported_at: \"{now_str}\"\n"
                    f"tags:\n"
                    f"  - download-anything\n"
                    f"  - micro-asset/{platform}\n"
                    f"---\n\n"
                )
                dest_note.write_text(frontmatter + content, encoding="utf-8")

        return dest_note or inbox_dir

    @classmethod
    def sync_to_notion(
        cls,
        title: str,
        markdown_body: str,
        platform: str = "web",
        original_url: str = "",
        cover_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Push asset record to Notion Database via official Notion API if keys exist.
        """
        api_key = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")
        database_id = os.getenv("NOTION_DATABASE_ID")

        if not api_key or not database_id:
            return {
                "success": False,
                "reason": "NOTION_API_KEY or NOTION_DATABASE_ID not configured in environment.",
                "tip": "Set NOTION_API_KEY and NOTION_DATABASE_ID to enable 1-click cloud sync."
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

        # Build basic Notion page creation payload
        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {"title": [{"text": {"content": title[:100]}}]},
                "Platform": {"select": {"name": platform[:50]}},
                "URL": {"url": original_url if original_url.startswith("http") else None}
            },
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": markdown_body[:1500]}}]
                    }
                }
            ]
        }
        if cover_url and cover_url.startswith("http"):
            payload["cover"] = {"type": "external", "external": {"url": cover_url}}

        try:
            resp = requests.post("https://api.notion.com/v1/pages", json=payload, headers=headers, timeout=12)
            if resp.status_code in (200, 201):
                page_data = resp.json()
                return {"success": True, "notion_page_url": page_data.get("url")}
            else:
                return {"success": False, "reason": f"Notion API error: {resp.status_code} {resp.text[:200]}"}
        except Exception as e:
            return {"success": False, "reason": str(e)}
