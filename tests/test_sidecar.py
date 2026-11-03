"""
Unit Tests for Sidecar Metadata and Markdown Generator
"""
import json
from drivers.base import AssetPackage, TargetAsset
from core.sidecar import SidecarWriter

def test_sidecar_generation(tmp_path):
    primary = TargetAsset(
        url="https://example.com/file.pdf",
        filename="stoic.pdf",
        file_type="primary",
        expected_size=1024
    )
    package = AssetPackage(
        title="斯多亚哲学的极简日常实践",
        platform="xiaohongshu",
        assets=[primary],
        metadata={
            "original_url": "https://www.xiaohongshu.com/explore/12345",
            "author": {
                "id": "u_999",
                "name": "哲学小站"
            },
            "created_at": "2026-11-03T18:00:00Z",
            "metrics": {
                "likes": 12500,
                "collects": 8900
            },
            "tags": ["哲学", "斯多亚", "自律"]
        },
        raw_markdown="## 笔记重点\n1. 专注于能掌控之事\n2. 坦然面对不能掌控之事"
    )

    sidecars = SidecarWriter.write_sidecars(
        dest_dir=tmp_path,
        package=package,
        primary_filename="stoic.pdf"
    )

    assert "info_json" in sidecars
    assert "markdown" in sidecars
    assert sidecars["info_json"].exists()
    assert sidecars["markdown"].exists()

    with open(sidecars["info_json"], "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["schema_version"] == "1.0"
    assert data["source_platform"] == "xiaohongshu"
    assert data["title"] == "斯多亚哲学的极简日常实践"
    assert data["author"]["name"] == "哲学小站"
    assert data["assets"]["primary"] == "stoic.pdf"
    assert data["metrics"]["likes"] == 12500

    md_content = sidecars["markdown"].read_text(encoding="utf-8")
    assert "# 斯多亚哲学的极简日常实践" in md_content
    assert "哲学小站" in md_content
    assert "#哲学" in md_content
