"""
Download Anything (DA) - Unified CLI & Agent Skill Entry Point
Supports single & batch downloads, audio extraction, password-protected archive unzipping,
and dual-mode presentation (Rich human cards & standard Agent JSON).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn, TextColumn
from rich.table import Table

from core.exceptions import DAError, VerificationError
from core.fetcher import Fetcher, FetcherOptions
from core.router import Router
from core.sidecar import SidecarWriter
from core.verifier import Verifier, detect_audio_container
from core.unpacker import Unpacker
from core.index_db import AssetIndexDB
from core.vault_sync import VaultSync
from core.transcriber import CloudTranscriber
from core.music_unlocker import MusicUnlocker
from core.path_resolver import resolve_output_directory, resolve_asset_path, sanitize_filename, get_system_downloads_dir
from drivers import get_default_drivers
from drivers.base import AssetPackage, TargetAsset

console = Console()
err_console = Console(stderr=True)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".flv", ".mov", ".ts", ".m4v"}

def _extract_audio_from_video(video_path: Path) -> Optional[Path]:
    """Extract audio track from video file using ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    # 1. Try lossless copy to .m4a
    audio_path = video_path.with_suffix(".m4a")
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-vn", "-c:a", "copy", str(audio_path)]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if res.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 1024:
            video_path.unlink(missing_ok=True)
            return audio_path
    except Exception:
        pass

    # 2. Fallback to high-quality MP3 re-encoding
    audio_path = video_path.with_suffix(".mp3")
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-vn", "-b:a", "192k", str(audio_path)]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        if res.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 1024:
            video_path.unlink(missing_ok=True)
            return audio_path
    except Exception:
        pass

    return None

def process_download(
    target_text: str,
    output_dir: Optional[str] = None,
    password: Optional[str] = None,
    max_mb: int = 500,
    check: bool = False,
    no_sidecar: bool = False,
    agent_mode: bool = False,
    verbose: bool = False,
    audio_only: bool = False,
    auto_unzip: bool = True,
    force: bool = False,
    vault: Optional[str] = None,
    notion: bool = False,
    transcribe: bool = False,
    lang: Optional[str] = None
) -> Dict[str, Any]:
    """Core download pipeline for a single target."""
    router = Router(get_default_drivers())
    prelim_clean = router.clean_input(target_text, explicit_password=password)

    # A pure download cache hit must not suppress explicitly requested post-processing.
    cache_variant = "audio-only" if audio_only else "default"
    has_postprocessing = bool(
        transcribe
        or notion
        or vault
        or output_dir
        or os.getenv("OBSIDIAN_VAULT_PATH")
        or os.getenv("DA_VAULT_PATH")
    )
    if not check and not force and not has_postprocessing:
        cached = AssetIndexDB.query(prelim_clean.url, variant=cache_variant) or AssetIndexDB.query(target_text, variant=cache_variant)
        if cached:
            if not agent_mode:
                console.print(Panel(
                    f"[bold green]✔ [本地缓存命中][/bold green] 该资产本地已存在，跳过重复下载：\n"
                    f"[dim]• 主资产:[/dim] {cached['primary_asset']}\n"
                    f"[dim]• 目录:[/dim] {cached['output_dir']}\n"
                    f"[dim]• 归档时间:[/dim] {cached['created_at']}\n"
                    f"[dim]提示: 如需强制重新下载，可追加 --force 或 -f[/dim]",
                    border_style="green"
                ))
            return cached

    driver = router.find_driver(prelim_clean)
    clean_input = prelim_clean

    if not agent_mode and verbose:
        console.print(f"[dim][*] Detected Driver: [bold]{driver.name}[/bold] ({driver.category})[/dim]")
        console.print(f"[dim][*] Clean URL: {clean_input.url}[/dim]")
        if clean_input.password:
            console.print(f"[dim][*] Passcode: {clean_input.password}[/dim]")

    # Extract assets with optional audio_only hint and preferred language
    package = driver.extract(
        clean_input.url,
        password=clean_input.password,
        audio_only=audio_only,
        inspect_only=check,
        preferred_lang=lang,
        lang=lang
    )
    warnings = []
    operations = {}
    result = None
    try:
        primary_asset = package.primary_asset
        if not primary_asset:
            raise DAError("Driver extracted 0 assets from target.")

        # Dry-run inspection
        if check:
            return {
                "status": "dry_run",
                "platform": package.platform,
                "title": package.title,
                "primary_asset": {
                    "filename": primary_asset.filename,
                    "url": primary_asset.url,
                    "expected_size": primary_asset.expected_size,
                    "file_type": primary_asset.file_type
                },
                "total_assets": len(package.assets),
                "metadata": package.metadata
            }

        # Resolve output directory
        base_dir = resolve_output_directory(output_dir, title=package.title, create_subfolder=True)
        base_dir.mkdir(parents=True, exist_ok=True)

        # Smart file naming
        clean_title = sanitize_filename(package.title, max_length=70)
        raw_ext = Path(primary_asset.filename).suffix
        if not raw_ext:
            raw_ext = ".m4a" if audio_only else ".mp4"

        is_generic_name = (
            primary_asset.filename.startswith("content.") or
            primary_asset.filename.startswith("article.") or
            primary_asset.filename.startswith("video.") or
            (len(primary_asset.filename) > 0 and primary_asset.filename[0].isdigit())
        )
        if is_generic_name and clean_title and clean_title != "untitled_asset":
            primary_asset.filename = f"{clean_title}{raw_ext}"

        fetcher = Fetcher(FetcherOptions(
            max_bytes=max_mb * 1024 * 1024,
            chunk_size=65536,
            inactivity_timeout=45
        ))

        dest_file = resolve_asset_path(base_dir, primary_asset.filename)
        primary_asset.filename = str(dest_file.relative_to(base_dir.resolve()))

        # Fetch Primary Asset
        if not agent_mode:
            with Progress(
                TextColumn("[bold blue]{task.fields[filename]}", justify="left"),
                BarColumn(bar_width=40),
                "[progress.percentage]{task.percentage:>3.1f}%",
                "•",
                DownloadColumn(),
                "•",
                TransferSpeedColumn(),
                "•",
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task_id = progress.add_task(
                    "download",
                    filename=primary_asset.filename,
                    total=primary_asset.expected_size or 0
                )

                def update_progress(current, total):
                    if total and progress.tasks[task_id].total != total:
                        progress.update(task_id, total=total)
                    progress.update(task_id, completed=current)

                downloaded_size = fetcher.download(
                    url=primary_asset.url,
                    dest_path=dest_file,
                    headers=primary_asset.headers,
                    expected_size=primary_asset.expected_size,
                    progress_callback=update_progress
                )
        else:
            downloaded_size = fetcher.download(
                url=primary_asset.url,
                dest_path=dest_file,
                headers=primary_asset.headers,
                expected_size=primary_asset.expected_size
            )

        primary_asset.local_path = dest_file
        primary_asset.downloaded_bytes = downloaded_size

        # Fetch Companions (Cover, Subtitles, Extra Images, BibTeX, etc.)
        cover_filename = None
        subtitle_filename = None
        companion_files: List[str] = []
        for companion in package.assets:
            if companion is primary_asset or companion.file_type == "primary":
                continue
            comp_ext = Path(companion.filename).suffix
            if companion.file_type == "cover":
                companion.filename = f"{clean_title}.cover{comp_ext or '.jpg'}" if clean_title != "untitled_asset" else "cover.jpg"
                cover_filename = companion.filename
            elif companion.file_type == "subtitle":
                companion.filename = f"{clean_title}.subtitle{comp_ext or '.srt'}" if clean_title != "untitled_asset" else "subtitle.srt"
                subtitle_filename = companion.filename

            comp_dest = resolve_asset_path(base_dir, companion.filename)
            companion.filename = str(comp_dest.relative_to(base_dir.resolve()))
            try:
                fetcher.download(
                    url=companion.url,
                    dest_path=comp_dest,
                    headers=companion.headers,
                    expected_size=companion.expected_size
                )
                companion_verification = Verifier.verify(comp_dest, expected_size=companion.expected_size)
                if not companion_verification.valid:
                    raise VerificationError(companion_verification.error_message)
                companion.local_path = comp_dest
                if companion.file_type not in ("cover", "subtitle") and comp_dest.exists():
                    companion_files.append(str(comp_dest.resolve()))
            except Exception as e:
                warnings.append({"stage": "companion", "asset": companion.filename,
                                 "error_type": type(e).__name__, "message": str(e)})
                if companion.file_type == "cover":
                    cover_filename = None
                elif companion.file_type == "subtitle":
                    subtitle_filename = None
                if verbose and not agent_mode:
                    console.print(f"[dim yellow]Warning: Failed to fetch companion {companion.filename}: {e}[/dim yellow]")

        # Audio-only post-processing if primary asset is a video
        if audio_only and dest_file.suffix.lower() in VIDEO_EXTENSIONS:
            if not agent_mode:
                console.print("[dim cyan]🎵 提取纯音频流中 (FFmpeg)...[/dim cyan]")
            extracted_audio = _extract_audio_from_video(dest_file)
            if extracted_audio and extracted_audio.exists():
                dest_file = extracted_audio
                primary_asset.filename = dest_file.name
                primary_asset.local_path = dest_file
                downloaded_size = dest_file.stat().st_size
                primary_asset.downloaded_bytes = downloaded_size
            else:
                raise DAError(
                    f"Audio extraction failed for {primary_asset.filename}; "
                    "the original video was preserved. Check ffmpeg availability and the source audio track."
                )

        # Normalize non-MP3 audio streams saved with an .mp3 suffix.
        expected_verify_size = primary_asset.expected_size if not audio_only else None
        if dest_file.suffix.lower() == ".mp3" and dest_file.exists() and dest_file.stat().st_size > 16:
            with open(dest_file, "rb") as f_head:
                h16 = f_head.read(16)
            container = detect_audio_container(h16)
            if container and container != "mp3":
                tmp_raw = dest_file.with_suffix(".raw_audio")
                dest_file.replace(tmp_raw)
                cover_p = (base_dir / cover_filename) if cover_filename and (base_dir / cover_filename).exists() else None
                if MusicUnlocker.transcode_to_mp3(tmp_raw, dest_file, cover_path=cover_p, metadata={"title": package.title}):
                    tmp_raw.unlink(missing_ok=True)
                    downloaded_size = dest_file.stat().st_size
                    primary_asset.downloaded_bytes = downloaded_size
                    expected_verify_size = None
                else:
                    # Preserve a playable asset with its real extension instead of mislabeling it as MP3.
                    dest_file.unlink(missing_ok=True)
                    dest_file = dest_file.with_suffix(f".{container}")
                    tmp_raw.replace(dest_file)
                    primary_asset.filename = dest_file.name
                    primary_asset.local_path = dest_file

        # Rigorous Verification
        verification = Verifier.verify(
            dest_file,
            expected_size=expected_verify_size,
            expected_ext=dest_file.suffix
        )

        if not verification.valid:
            raise VerificationError(
                f"Verification failed for {primary_asset.filename}: {verification.error_message}",
                details={"verification": verification.__dict__}
            )

        primary_asset.verified = True

        # Automatic Archive Unpacking (with auto password support)
        extracted_files = []
        if auto_unzip and Unpacker.is_archive(dest_file):
            if not agent_mode:
                console.print(f"[dim cyan]📦 检测到压缩归档，正在自动解压提取 (密码: {clean_input.password or '无'})...[/dim cyan]")
            extract_dest = base_dir / f"extracted_{clean_title}"
            extracted_files = Unpacker.unpack(
                archive_path=dest_file,
                dest_dir=extract_dest,
                password=clean_input.password
            )
            if extracted_files:
                package.metadata["extracted_files"] = [str(f.name) for f in extracted_files]
                package.metadata["extracted_count"] = len(extracted_files)

        # Sidecar Generation
        sidecar_paths = {}
        if not no_sidecar:
            sidecar_paths = SidecarWriter.write_sidecars(
                dest_dir=base_dir,
                package=package,
                primary_filename=primary_asset.filename,
                cover_filename=cover_filename,
                subtitle_filename=subtitle_filename
            )

        sidecar_dict: Dict[str, Any] = {k: str(v.resolve()) for k, v in sidecar_paths.items()}
        if cover_filename and (base_dir / cover_filename).exists():
            sidecar_dict["cover"] = str((base_dir / cover_filename).resolve())
        if subtitle_filename and (base_dir / subtitle_filename).exists():
            sidecar_dict["subtitle"] = str((base_dir / subtitle_filename).resolve())
        if companion_files:
            sidecar_dict["companion_files"] = companion_files

        # 10. Cloud Speech Transcription Hook (Whisper API without local heavy models)
        if transcribe and (audio_only or dest_file.suffix.lower() in {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}):
            if not agent_mode:
                console.print("[dim cyan]🎙️ 正在调用轻量云端 Whisper 极速转写生成全文稿...[/dim cyan]")
            try:
                transcript_file = CloudTranscriber.transcribe(dest_file, base_dir, clean_title)
            except Exception as exc:
                transcript_file = None
                operations["transcription"] = {"status": "error", "reason": str(exc)}
            if transcript_file:
                operations["transcription"] = {"status": "success"}
                sidecar_dict["transcript"] = str(transcript_file.resolve())
                if not agent_mode:
                    console.print(f"[bold green]✔ [语音文字稿就绪][/bold green] {transcript_file.name}")
            else:
                operations.setdefault("transcription", {"status": "error", "reason": "Transcription produced no result"})
                warnings.append({"stage": "transcription", "message": operations["transcription"]["reason"]})
        elif transcribe:
            operations["transcription"] = {"status": "skipped", "reason": "Use -a to extract an audio track before transcription"}
            warnings.append({"stage": "transcription", "message": operations["transcription"]["reason"]})

        # 11. Downstream Personal Knowledge-Base Sync (Obsidian & Notion)
        obsidian_note = None
        if vault or os.getenv("OBSIDIAN_VAULT_PATH") or os.getenv("DA_VAULT_PATH"):
            try:
                obsidian_note = VaultSync.sync_to_obsidian(
                    asset_dir=base_dir,
                    vault_path=vault,
                    title=package.title,
                    platform=package.platform,
                    original_url=clean_input.url
                )
            except Exception as exc:
                obsidian_note = None
                operations["obsidian"] = {"status": "error", "reason": str(exc)}
            if obsidian_note:
                operations["obsidian"] = {"status": "success"}
                sidecar_dict["obsidian_vault_note"] = str(obsidian_note.resolve())
                if not agent_mode:
                    console.print(f"[bold green]✔ [Obsidian 双链库同步成功][/bold green] {obsidian_note}")
            else:
                operations.setdefault("obsidian", {"status": "error", "reason": "Obsidian vault could not be resolved"})
                warnings.append({"stage": "obsidian", "message": operations["obsidian"]["reason"]})

        if notion:
            try:
                notion_res = VaultSync.sync_to_notion(
                    title=package.title,
                    markdown_body=package.raw_markdown or package.metadata.get("sidecar_text", "") or package.metadata.get("description", ""),
                    platform=package.platform,
                    original_url=clean_input.url,
                    cover_url=package.assets[1].url if len(package.assets) > 1 else None
                )
            except Exception as exc:
                notion_res = {"success": False, "reason": str(exc)}
                operations["notion"] = {"status": "error", "reason": str(exc)}
            if notion_res.get("success"):
                operations["notion"] = {"status": "success"}
                sidecar_dict["notion_page"] = notion_res.get("notion_page_url", "pushed")
                if not agent_mode:
                    console.print(f"[bold green]✔ [Notion 页面推送成功][/bold green] {notion_res.get('notion_page_url')}")
            else:
                operations["notion"] = {"status": "error", "reason": notion_res.get("reason", "Notion sync failed")}
                warnings.append({"stage": "notion", "message": operations["notion"]["reason"]})

        result = {
            "status": "partial" if warnings else "success",
            "platform": package.platform,
            "title": package.title,
            "output_dir": str(base_dir.resolve()),
            "primary_asset": str(dest_file.resolve()),
            "size_bytes": downloaded_size,
            "sidecars": sidecar_dict,
            "companion_files": companion_files,
            "extracted_files": [str(p.resolve()) for p in extracted_files] if extracted_files else [],
            "verification": {
                "valid": verification.valid,
                "detected_type": verification.detected_type,
                "details": verification.details
            },
            "warnings": warnings,
            "operations": operations,
        }
        return result
    finally:
        if not check:
            active_error = sys.exc_info()[1]
            try:
                driver.cleanup(package)
                operations["cleanup"] = {"status": "success"}
            except Exception as exc:
                operations["cleanup"] = {"status": "error", "reason": str(exc)}
                warnings.append({"stage": "cleanup", "message": str(exc)})
                if result is not None:
                    result["status"] = "partial"
                if active_error is not None:
                    details = dict(getattr(active_error, "details", {}) or {})
                    details["cleanup_error"] = str(exc)
                    active_error.details = details
            if result is not None and result["status"] == "success":
                AssetIndexDB.record(
                    url=clean_input.url, platform=package.platform, title=package.title,
                    output_dir=base_dir, primary_file=dest_file, size_bytes=downloaded_size,
                    sidecars=sidecar_dict, variant=cache_variant,
                )


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.argument("targets", nargs=-1)
@click.option("-i", "--input-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Batch download URLs from a file (one per line)")
@click.option("-o", "--output-dir", help="Output directory path (default: ~/Downloads/DA/<folder>)")
@click.option("-p", "--password", help="Explicit password/passcode if not embedded in input")
@click.option("-a", "--audio", "--audio-only", is_flag=True, help="Extract audio-only stream (.mp3/.m4a) to save bandwidth and storage")
@click.option("-f", "--force", is_flag=True, help="Force re-download even if already present in local asset cache")
@click.option("--vault", "--obsidian", help="Sync downloaded notes, media, and frontmatter to Obsidian Vault path")
@click.option("--notion", is_flag=True, help="Sync note record to Notion database (requires NOTION_API_KEY)")
@click.option("--transcribe", is_flag=True, help="Transcribe speech/podcast audio using ultra-light cloud Whisper API")
@click.option("--unzip/--no-unzip", default=True, help="Automatically extract password-protected or standard archives upon download (default: True)")
@click.option("--max-mb", default=500, type=click.IntRange(min=1), help="Maximum allowed file size in MB (default: 500)")
@click.option("--check", is_flag=True, help="Dry run: inspect and extract metadata without downloading")
@click.option("--no-sidecar", is_flag=True, help="Disable generating sidecar metadata (.info.json and .md)")
@click.option("--lang", default=None, help="Preferred language for search & extraction (e.g. 'zh', 'en'). Follows user conversation language.")
@click.option("--fix", is_flag=True, help="Auto-repair and install missing dependencies in doctor mode")
@click.option("--json", "agent_mode", is_flag=True, help="Agent mode: output JSON result to stdout")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logs")
def main(
    targets: Tuple[str, ...],
    input_file: Optional[Path],
    output_dir: Optional[str],
    password: Optional[str],
    audio: bool,
    force: bool,
    vault: Optional[str],
    notion: bool,
    transcribe: bool,
    unzip: bool,
    max_mb: int,
    check: bool,
    no_sidecar: bool,
    lang: Optional[str],
    fix: bool,
    agent_mode: bool,
    verbose: bool
):
    """
    Download Anything (DA) - High-density micro-asset extraction & offline archiving hub.
    Input can be a URL, mobile share text, book MD5, or batch file (-i links.txt).
    """
    targets_list = list(targets)

    # 1. Handle special subcommands
    if len(targets_list) >= 1 and targets_list[0] in ("login", "auth"):
        platform_name = (targets_list[1] if len(targets_list) > 1 else "quark").lower()
        login_ok = _handle_login(platform_name, agent_mode=agent_mode)
        sys.exit(0 if login_ok else 1)

    if len(targets_list) >= 1 and targets_list[0] in ("doctor", "check-env", "diagnose"):
        sub = targets_list[1] if len(targets_list) > 1 else None
        is_fix = fix or (sub in ("--fix", "-f")) or ("--fix" in sys.argv)
        _handle_doctor(sub, agent_mode, fix=is_fix)
        sys.exit(0)

    # 2. Collect input targets from input_file or clipboard
    if input_file:
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        targets_list.append(s)
        except Exception as e:
            _handle_error(e, agent_mode)
            sys.exit(1)

    if not targets_list:
        # Check system clipboard on macOS if available and in interactive human mode
        if sys.platform == "darwin" and not agent_mode:
            try:
                clip = subprocess.check_output(["pbpaste"], text=True, timeout=1).strip()
                if clip and ("http://" in clip or "https://" in clip or re.search(r"\b[0-9a-fA-F]{32}\b", clip) or re.search(r"\b[0-9]{4}\.[0-9]{4,5}\b", clip)):
                    console.print(f"[dim cyan]📋 Detected input from clipboard:[/dim cyan] [dim]{clip[:80]}...[/dim]")
                    targets_list.append(clip)
            except Exception:
                pass

    if not targets_list:
        if agent_mode:
            print(json.dumps({
                "status": "error",
                "error_type": "InvalidInputError",
                "message": "No target URL, text, or input file provided"
            }, ensure_ascii=False, indent=2))
            sys.exit(1)
        console.print("[bold red]Error:[/bold red] Please provide a target URL, share text, or batch file (-i).")
        console.print("Usage: [bold green]da \"<URL or share text>\"[/bold green] or [bold green]da -i links.txt[/bold green]")
        sys.exit(1)

    # Output banner for Human mode
    if not agent_mode and not check:
        console.print(Panel.fit(
            "[bold cyan]Download Anything[/bold cyan] [dim](DA v0.1.0)[/dim]\n"
            f"[dim]Universal Micro-Asset Extraction Hub ({len(targets_list)} target{'s' if len(targets_list) > 1 else ''})[/dim]",
            border_style="cyan"
        ))

    # Single Download Flow
    if len(targets_list) == 1:
        single_target = targets_list[0]
        try:
            res = process_download(
                target_text=single_target,
                output_dir=output_dir,
                password=password,
                max_mb=max_mb,
                check=check,
                no_sidecar=no_sidecar,
                agent_mode=agent_mode,
                verbose=verbose,
                audio_only=audio,
                auto_unzip=unzip,
                force=force,
                vault=vault,
                notion=notion,
                transcribe=transcribe,
                lang=lang
            )
        except Exception as e:
            _handle_error(e, agent_mode)
            sys.exit(1)

        if agent_mode:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif check:
            table = Table(title="Extracted Asset Package (Dry-Run)")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")
            table.add_row("Platform", res["platform"])
            table.add_row("Title", res["title"])
            table.add_row("Primary File", res["primary_asset"]["filename"])
            table.add_row("Expected Size", f"{res['primary_asset']['expected_size'] or 'Unknown'} bytes")
            table.add_row("Direct Download URL", res["primary_asset"]["url"][:80] + ("..." if len(res["primary_asset"]["url"]) > 80 else ""))
            console.print(table)
        else:
            success_table = Table(show_header=False, box=None)
            success_table.add_row("[bold green]✔[/bold green] [bold]Primary Asset:[/bold]", res["primary_asset"])
            success_table.add_row("[bold green]✔[/bold green] [bold]Verified Format:[/bold]", f"{res['verification']['detected_type']} ({res['size_bytes'] / (1024*1024):.2f} MB)")
            success_table.add_row("[bold green]✔[/bold green] [bold]Asset Folder:[/bold]", res["output_dir"])
            if res.get("sidecars"):
                success_table.add_row("[bold green]✔[/bold green] [bold]Sidecars:[/bold]", "content.info.json, content.md")
            if res.get("extracted_files"):
                success_table.add_row("[bold green]✔[/bold green] [bold]Auto-Unpacked:[/bold]", f"Extracted {len(res['extracted_files'])} files")

            console.print(Panel(
                success_table,
                title="Download Partially Complete" if res["status"] == "partial" else "Download Complete & Verified",
                border_style="yellow" if res["status"] == "partial" else "green"
            ))
            for warning in res.get("warnings", []):
                err_console.print(f"[yellow]{warning['stage']}: {warning['message']}[/yellow]")
        sys.exit(2 if res["status"] == "partial" else 0)

    # Batch Download Flow (Multiple Targets)
    results = []
    success_count = 0
    partial_count = 0
    total = len(targets_list)

    for idx, target in enumerate(targets_list, 1):
        if not agent_mode:
            console.print(f"\n[bold cyan]─── [{idx}/{total}] Processing: {target[:60]}... ───[/bold cyan]")
        try:
            item_res = process_download(
                target_text=target,
                output_dir=output_dir,
                password=password,
                max_mb=max_mb,
                check=check,
                no_sidecar=no_sidecar,
                agent_mode=agent_mode,
                verbose=verbose,
                audio_only=audio,
                auto_unzip=unzip,
                force=force,
                vault=vault,
                notion=notion,
                transcribe=transcribe,
                lang=lang
            )
            item_res["target"] = target
            results.append(item_res)
            if item_res["status"] == "partial":
                partial_count += 1
            else:
                success_count += 1
            if not agent_mode:
                console.print(f"[{idx}/{total}] {item_res['status']}: {item_res.get('title', 'Done')}")
        except Exception as e:
            err_dict = {
                "status": "error",
                "target": target,
                "error_type": type(e).__name__,
                "message": str(e)
            }
            if getattr(e, "details", None):
                err_dict["details"] = e.details
            results.append(err_dict)
            if not agent_mode:
                console.print(f"[bold red]✘ [{idx}/{total}] Failed:[/bold red] {e}")

    if agent_mode:
        batch_output = {
            "batch": True,
            "total": total,
            "success_count": success_count,
            "partial_count": partial_count,
            "results": results
        }
        print(json.dumps(batch_output, ensure_ascii=False, indent=2))
    else:
        summary_table = Table(title=f"Batch Download Summary ({success_count}/{total} Successful)", border_style="cyan")
        summary_table.add_column("#", justify="center")
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Title / Target")
        summary_table.add_column("Details")

        for idx, r in enumerate(results, 1):
            if r.get("status") in ("success", "cached", "dry_run"):
                summary_table.add_row(
                    str(idx),
                    "[bold green]✔ OK[/bold green]",
                    r.get("title") or r.get("target") or "N/A",
                    f"{r.get('size_bytes', 0)/(1024*1024):.2f} MB"
                )
            elif r.get("status") == "partial":
                summary_table.add_row(str(idx), "[yellow]Partial[/yellow]", r.get("title", ""),
                                      "; ".join(w["message"] for w in r.get("warnings", [])))
            else:
                summary_table.add_row(
                    str(idx),
                    "[bold red]✘ Fail[/bold red]",
                    r.get("target") or "N/A",
                    r.get("message") or "Unknown error"
                )
        console.print(summary_table)

    sys.exit(2 if partial_count else (0 if success_count > 0 else 1))


def _report_login_result(
    platform: str,
    agent_mode: bool,
    success: bool,
    message: str,
    human_message: Any,
    source: Optional[str] = None,
) -> bool:
    """Build and emit one login result while preserving the process exit semantics."""
    result: Dict[str, Any] = {
        "status": "success" if success else "error",
        "platform": platform,
    }
    if source:
        result["source"] = source
    result["message"] = message
    if agent_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console.print(human_message)
    return success


def _handle_login(platform: str, agent_mode: bool = False) -> bool:
    """Automated login helper: harvests from browser or triggers headless capture."""
    from core.credentials import credentials_manager

    platform = platform.lower()
    if not agent_mode:
        console.print(Panel(
            f"[bold cyan]正在自动探测 {platform} 登录凭据...[/bold cyan]\n"
            "[dim]优先尝试从本地 Chrome/Safari/Edge 浏览器提取...[/dim]",
            border_style="cyan"
        ))

    # 1. Check if rookiepy can get it directly from browsers
    domains = credentials_manager.PLATFORM_DOMAINS.get(platform, [f"{platform}.com"])
    cookie = credentials_manager._harvest_from_browsers(domains)
    if cookie:
        credentials_manager.save_credential(platform, cookie)
        return _report_login_result(
            platform,
            agent_mode,
            True,
            "Cookie harvested from default browser and saved",
            Panel(
                f"[bold green]✔ 成功直接从默认浏览器中捕获到 {platform} 的登录 Cookie！已自动保存。[/bold green]\n"
                "[dim]现在直接运行 da \"<网盘链接>\" 即可免登极速下载。[/dim]",
                border_style="green"
            ),
            source="browser",
        )

    # 2. Check native desktop app databases
    cookie = credentials_manager._harvest_from_desktop_apps(platform)
    if cookie:
        credentials_manager.save_credential(platform, cookie)
        return _report_login_result(
            platform,
            agent_mode,
            True,
            "Cookie harvested from desktop app database and saved",
            Panel(
                f"[bold green]✔ 成功从本地桌面客户端数据库捕获到 {platform} 凭据！已自动保存。[/bold green]",
                border_style="green"
            ),
            source="desktop_app",
        )

    # 3. Automated Browser Capture window (zero manual copying)
    if not agent_mode:
        console.print("[dim yellow]macOS 提示：默认浏览器 Cookies 受系统保护。即将弹出登录窗口，登录后脚本将自动抓取凭据，无需手动复制！[/dim yellow]")
    login_urls = {
        "quark": "https://pan.quark.cn/",
        "baidu": "https://pan.baidu.com/",
    }
    target_url = login_urls.get(platform, f"https://pan.{platform}.com/")
    domain = domains[0]

    grab_bin = shutil.which("grab-cookie") or os.getenv("DA_GRAB_COOKIE_BIN", "")
    if grab_bin and os.path.exists(grab_bin):
        try:
            cmd = [grab_bin, target_url, "--domain", domain, "--no-probe"]
            result = subprocess.run(cmd, **({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE} if agent_mode else {}))
            if result.returncode == 0:
                return _report_login_result(
                    platform,
                    agent_mode,
                    True,
                    "Captured credentials via grab-cookie",
                    "[bold green]✔ 凭据捕获完成！现在可直接下载。[/bold green]",
                    source="grab-cookie",
                )

            msg = f"grab-cookie exited with code {result.returncode}"
            return _report_login_result(
                platform,
                agent_mode,
                False,
                msg,
                f"[bold red]自动弹窗抓取失败: {msg}[/bold red]",
            )
        except Exception as e:
            msg = f"Auto-capture failed: {e}"
            return _report_login_result(
                platform,
                agent_mode,
                False,
                msg,
                f"[bold red]自动弹窗抓取失败: {e}[/bold red]",
            )
    else:
        msg = (
            f"未检测到本地已登录凭据。可在 macOS『系统设置 ➔ 隐私与安全性 ➔ 完全磁盘访问权限』中勾选终端，"
            f"或手动设置环境变量: export DA_{platform.upper()}_COOKIE='...'"
        )
        return _report_login_result(
            platform,
            agent_mode,
            False,
            msg,
            (
                "[bold yellow]💡 一劳永逸全自动方法：[/bold yellow]\n"
                "在 macOS『系统设置 ➔ 隐私与安全性 ➔ 完全磁盘访问权限』中勾选当前终端/IDE，\n"
                f"da 就能永久静默自动读取 Chrome/Safari 中的 {platform} Cookie，无需任何操作！"
            ),
        )


def _handle_doctor(subtarget: Optional[str], agent_mode: bool, fix: bool = False):
    """Diagnose Python environment, dependencies, and external utilities."""
    from core.doctor import Doctor
    if fix or (subtarget in ("--fix", "-f")) or ("--fix" in sys.argv):
        if not agent_mode:
            console.print("[bold yellow]正在自动修复缺失的 Python 依赖包...[/bold yellow]")
        Doctor.auto_repair(capture_output=agent_mode)

    report = Doctor.check_all()
    if agent_mode:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report["all_required_ok"] else 1)

    table = Table(title="Download Anything (DA) 环境与依赖诊断报告", border_style="cyan")
    table.add_column("组件 / 工具", style="bold cyan")
    table.add_column("状态", justify="center")
    table.add_column("版本 / 路径", style="dim")
    table.add_column("说明", style="white")

    py_status = "[bold green]✔ 就绪[/bold green]" if report["python_version"]["ok"] else "[bold red]✘ 版本过低[/bold red]"
    table.add_row("Python 运行时", py_status, report["python_version"]["version"], f"要求 {report['python_version']['required']}")

    for name, item in report["dependencies"].items():
        status = "[bold green]✔ 就绪[/bold green]" if item["installed"] else "[bold red]✘ 缺失[/bold red]"
        table.add_row(item["pip_name"].split(">=")[0], status, item["version"] or "-", item["description"])

    for name, item in report["external_tools"].items():
        status = "[bold green]✔ 就绪[/bold green]" if item["installed"] else ("[dim yellow]可选[/dim yellow]" if not item["required"] else "[bold red]✘ 缺失[/bold red]")
        table.add_row(name, status, item["path"] or "-", item["description"])

    if report.get("mac_fda"):
        fda_status = "[bold green]✔ 已启用[/bold green]" if report["mac_fda"]["enabled"] else "[dim yellow]未授权(可选)[/dim yellow]"
        table.add_row("macOS 完全磁盘访问", fda_status, "-", report["mac_fda"]["description"])

    console.print(table)
    if not report["all_required_ok"]:
        console.print(Panel(
            "[bold yellow]检测到有缺失的核心依赖！[/bold yellow]\n"
            "你可以直接运行 [bold green]da doctor --fix[/bold green] 一键全自动补全安装，\n"
            "或者在当前目录运行: [cyan]uv pip install -e .[/cyan] 或 [cyan]pip install -e .[/cyan]",
            border_style="yellow"
        ))
        sys.exit(1)
    else:
        console.print("[bold green]✔ 所有核心环境与依赖均已就绪，运行状态良好！[/bold green]")
        sys.exit(0)


def _handle_error(err: Exception, agent_mode: bool):
    """Deliver uniform error outputs for human CLI and agent skill."""
    err_type = type(err).__name__
    err_msg = str(err)
    err_dict: Dict[str, Any] = {
        "status": "error",
        "error_type": err_type,
        "message": err_msg
    }
    if hasattr(err, "details") and err.details:
        err_dict["details"] = err.details
    if agent_mode:
        print(json.dumps(err_dict, ensure_ascii=False, indent=2))
    else:
        err_console.print(Panel(
            f"[bold red]{err_type}:[/bold red] {err_msg}",
            title="[bold red]Operation Failed[/bold red]",
            border_style="red"
        ))


if __name__ == "__main__":
    main()
