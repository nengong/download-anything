"""
Sidecar Metadata and Markdown Generator
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

from drivers.base import AssetPackage

class SidecarWriter:
    """Writes standardized sidecar files (.info.json, .md, and .lrc) alongside downloaded media."""

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
        Generate and persist content.info.json, content.md, and optional .lrc into dest_dir.
        Returns a mapping of sidecar type -> Path.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.now(timezone.utc).isoformat()
        sidecars = {}
        # Sidecars must never overwrite any downloaded asset (including Markdown).
        reserved = {dest_dir / asset.filename for asset in package.assets}
        reserved.add(dest_dir / primary_filename)

        def sidecar_path(filename):
            candidate = dest_dir / filename
            while candidate in reserved:
                candidate = candidate.with_name(candidate.stem + ".metadata" + candidate.suffix)
            reserved.add(candidate)
            return candidate

        md_path = sidecar_path("content.md")

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
                "sidecar_text": md_path.name
            },
            "metrics": package.metadata.get("metrics", {})
        }

        if cover_filename:
            info_data["assets"]["cover"] = cover_filename
        if subtitle_filename:
            info_data["assets"]["subtitle"] = subtitle_filename

        # Optional synchronized lyrics (.lrc) companion file if present in metadata
        lyrics_text = package.metadata.get("lyrics")
        if lyrics_text and isinstance(lyrics_text, str) and lyrics_text.strip():
            base_stem = Path(primary_filename).stem if primary_filename else "content"
            lrc_filename = f"{base_stem}.lrc" if base_stem and base_stem != "content" else "lyrics.lrc"
            lrc_path = sidecar_path(lrc_filename)
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(lyrics_text.strip() + "\n")
            sidecars["lyrics"] = lrc_path
            info_data["assets"]["lyrics"] = lrc_path.name

        # Add any extra platform-specific metadata tags
        if "tags" in package.metadata:
            info_data["tags"] = package.metadata["tags"]
        if "extra" in package.metadata:
            info_data["extra"] = package.metadata["extra"]

        info_path = sidecar_path("content.info.json")
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(info_data, f, ensure_ascii=False, indent=2)
        sidecars["info_json"] = info_path

        # 2. Human-readable content.md
        md_lines = [
            f"# {package.title}",
            "",
            "> **文件元数据速览**",
            f"> - **平台来源**：`{package.platform}`",
            f"> - **作者**：`{info_data['author'].get('name', 'Unknown')}`",
            f"> - **原始链接**：<{info_data['original_url']}>",
            f"> - **提取时间**：`{now_iso}`",
            f"> - **主文件**：`{primary_filename}`",
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
        body_content = (package.raw_markdown or package.metadata.get("sidecar_text")
                        or package.metadata.get("description", ""))
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

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        sidecars["markdown"] = md_path

        # If primary_filename is named after the title (e.g. "Title.mp4"), also mirror named sidecars
        if primary_filename and primary_filename != "content.mp4":
            base_stem = Path(primary_filename).stem
            if base_stem and base_stem != "content":
                named_info = sidecar_path(f"{base_stem}.info.json")
                named_md = sidecar_path(f"{base_stem}.md")
                with open(named_info, "w", encoding="utf-8") as f:
                    json.dump(info_data, f, ensure_ascii=False, indent=2)
                with open(named_md, "w", encoding="utf-8") as f:
                    f.write("\n".join(md_lines))
                sidecars["named_info_json"] = named_info
                sidecars["named_markdown"] = named_md

        return sidecars
