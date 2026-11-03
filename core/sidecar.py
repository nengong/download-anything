"""
Sidecar Metadata and Markdown Generator
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

from drivers.base import AssetPackage

class SidecarWriter:
    """Writes standardized sidecar files (.info.json and .md) alongside downloaded media."""

    SCHEMA_VERSION = "1.0"

    @classmethod
    def write_sidecars(
        cls,
        dest_dir: Path,
        package: AssetPackage,
        primary_filename: str,
        cover_filename: Optional[str] = None,
        subtitle_filename: Optional[str] = None
    ) -> Dict[str, Path]:
        """
        Generate and persist content.info.json and content.md into dest_dir.
        Returns a mapping of sidecar type -> Path.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.now(timezone.utc).isoformat()
        sidecars = {}

        # 1. Structure content.info.json
        info_data = {
            "schema_version": cls.SCHEMA_VERSION,
            "source_platform": package.platform,
            "original_url": package.metadata.get("original_url", ""),
            "title": package.title,
            "author": package.metadata.get("author", {
                "id": "",
                "name": package.metadata.get("author_name", "Unknown")
            }),
            "created_at": package.metadata.get("created_at", now_iso),
            "fetched_at": now_iso,
            "assets": {
                "primary": primary_filename,
                "sidecar_text": "content.md"
            },
            "metrics": package.metadata.get("metrics", {})
        }

        if cover_filename:
            info_data["assets"]["cover"] = cover_filename
        if subtitle_filename:
            info_data["assets"]["subtitle"] = subtitle_filename

        # Add any extra platform-specific metadata tags
        if "tags" in package.metadata:
            info_data["tags"] = package.metadata["tags"]
        if "extra" in package.metadata:
            info_data["extra"] = package.metadata["extra"]

        info_path = dest_dir / "content.info.json"
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info_data, f, ensure_ascii=False, indent=2)
        sidecars["info_json"] = info_path

        # 2. Human-readable content.md
        md_lines = [
            f"# {package.title}",
            "",
            "> **资产元数据速览**",
            f"> - **平台来源**：`{package.platform}`",
            f"> - **作者**：`{info_data['author'].get('name', 'Unknown')}`",
            f"> - **原始链接**：<{info_data['original_url']}>",
            f"> - **提取时间**：`{now_iso}`",
            f"> - **主资产文件**：`{primary_filename}`",
            ""
        ]

        # Metrics if available
        metrics = info_data.get("metrics")
        if metrics:
            md_lines.append("### 互动数据")
            for k, v in metrics.items():
                md_lines.append(f"- **{k}**: {v}")
            md_lines.append("")

        # Body text / description
        md_lines.append("## 正文说明 / 描述")
        body_content = package.raw_markdown or package.metadata.get("description", "")
        if body_content:
            md_lines.append(body_content)
        else:
            md_lines.append("*（无附加文案说明）*")
        md_lines.append("")

        # Tags if available
        tags = package.metadata.get("tags")
        if tags and isinstance(tags, list):
            md_lines.append("## 标签")
            md_lines.append(" ".join(f"`#{t}`" for t in tags))
            md_lines.append("")

        md_path = dest_dir / "content.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        sidecars["markdown"] = md_path

        return sidecars
