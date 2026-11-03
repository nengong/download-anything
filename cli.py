"""
Download Anything (DA) - Unified CLI & Agent Skill Entry Point
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn, TextColumn
from rich.table import Table

from core.exceptions import DAError
from core.fetcher import Fetcher, FetcherOptions
from core.router import Router
from core.sidecar import SidecarWriter
from core.verifier import Verifier
from drivers import get_default_drivers
from drivers.base import AssetPackage, TargetAsset

console = Console()
err_console = Console(stderr=True)

def sanitize_folder_name(name: str) -> str:
    """Sanitize string for local directory creation."""
    s = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", name).strip()
    return s[:64] if len(s) > 64 else s

@click.command()
@click.argument("target", required=False)
@click.option("-o", "--output-dir", help="Output directory path (default: ~/Downloads/DA/<folder>)")
@click.option("-p", "--password", help="Explicit password/passcode if not embedded in input")
@click.option("--max-mb", default=500, type=int, help="Maximum allowed file size in MB (default: 500)")
@click.option("--check", is_flag=True, help="Dry run: inspect and extract metadata without downloading")
@click.option("--no-sidecar", is_flag=True, help="Disable generating sidecar metadata (.info.json and .md)")
@click.option("--json", "agent_mode", is_flag=True, help="Agent mode: output JSON result to stdout")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logs")
def main(
    target: Optional[str],
    output_dir: Optional[str],
    password: Optional[str],
    max_mb: int,
    check: bool,
    no_sidecar: bool,
    agent_mode: bool,
    verbose: bool
):
    """
    Download Anything (DA) - High-density micro-asset extraction & offline archiving hub.
    Input can be a URL, mobile share text, or book MD5.
    """
    if not target:
        # Check system clipboard on macOS if available and in interactive human mode
        if sys.platform == "darwin" and not agent_mode:
            try:
                import subprocess
                clip = subprocess.check_output(["pbpaste"], text=True, timeout=1).strip()
                if clip and ("http://" in clip or "https://" in clip or re.search(r"\b[0-9a-fA-F]{32}\b", clip) or re.search(r"\b[0-9]{4}\.[0-9]{4,5}\b", clip)):
                    console.print(f"[dim cyan]📋 Detected input from clipboard:[/dim cyan] [dim]{clip[:80]}...[/dim]")
                    target = clip
            except Exception:
                pass

    if not target:
        if agent_mode:
            print(json.dumps({"status": "error", "message": "No target URL or text provided"}, ensure_ascii=False))
            sys.exit(1)
        console.print("[bold red]Error:[/bold red] Please provide a target URL or share text.")
        console.print("Usage: [bold green]da \"<URL or share text>\"[/bold green]")
        sys.exit(1)

    # Output banner for Human mode
    if not agent_mode and not check:
        console.print(Panel.fit(
            "[bold cyan]Download Anything[/bold cyan] [dim](DA v0.1.0)[/dim]\n"
            "[dim]Universal Micro-Asset Extraction Hub[/dim]",
            border_style="cyan"
        ))

    # 1. Setup Router and Dispatcher
    router = Router(get_default_drivers())
    try:
        driver, clean_input = router.route(target, explicit_password=password)
    except DAError as e:
        _handle_error(e, agent_mode)
        sys.exit(1)

    if not agent_mode and verbose:
        console.print(f"[dim][*] Detected Driver: [bold]{driver.name}[/bold] ({driver.category})[/dim]")
        console.print(f"[dim][*] Clean URL: {clean_input.url}[/dim]")
        if clean_input.password:
            console.print(f"[dim][*] Passcode: {clean_input.password}[/dim]")

    # 2. Extract Assets & Metadata
    if not agent_mode:
        with console.status("[bold blue]Resolving direct asset links and metadata...[/bold blue]"):
            try:
                package = driver.extract(clean_input.url, password=clean_input.password)
            except Exception as e:
                _handle_error(e, agent_mode)
                sys.exit(1)
    else:
        try:
            package = driver.extract(clean_input.url, password=clean_input.password)
        except Exception as e:
            _handle_error(e, agent_mode)
            sys.exit(1)

    primary_asset = package.primary_asset
    if not primary_asset:
        err = DAError("Driver extracted 0 assets from target.")
        _handle_error(err, agent_mode)
        sys.exit(1)

    # 3. Dry-run Check Mode
    if check:
        if agent_mode:
            print(json.dumps({
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
            }, ensure_ascii=False, indent=2))
        else:
            table = Table(title="Extracted Asset Package (Dry-Run)")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")
            table.add_row("Platform", package.platform)
            table.add_row("Title", package.title)
            table.add_row("Primary File", primary_asset.filename)
            table.add_row("Expected Size", f"{primary_asset.expected_size or 'Unknown'} bytes")
            table.add_row("Direct Download URL", primary_asset.url[:80] + ("..." if len(primary_asset.url) > 80 else ""))
            console.print(table)
        sys.exit(0)

    # 4. Resolve Output Directory
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{date_prefix}_{sanitize_folder_name(package.title)}"
    if output_dir:
        base_dir = Path(os.path.expanduser(output_dir))
    else:
        base_dir = Path.home() / "Downloads" / "DA" / folder_name

    base_dir.mkdir(parents=True, exist_ok=True)

    # 5. Fetch Primary Asset
    fetcher = Fetcher(FetcherOptions(
        max_bytes=max_mb * 1024 * 1024,
        chunk_size=65536,
        inactivity_timeout=45
    ))

    dest_file = base_dir / primary_asset.filename
    try:
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

    except Exception as e:
        _handle_error(e, agent_mode)
        sys.exit(1)

    # 6. Fetch Companion Assets (e.g. Cover Image, Subtitles)
    cover_filename = None
    subtitle_filename = None
    for companion in package.assets:
        if companion.file_type == "primary":
            continue
        comp_dest = base_dir / companion.filename
        try:
            fetcher.download(
                url=companion.url,
                dest_path=comp_dest,
                headers=companion.headers,
                expected_size=companion.expected_size
            )
            companion.local_path = comp_dest
            if companion.file_type == "cover":
                cover_filename = companion.filename
            elif companion.file_type == "subtitle":
                subtitle_filename = companion.filename
        except Exception as e:
            if verbose and not agent_mode:
                console.print(f"[dim yellow]Warning: Failed to fetch companion {companion.filename}: {e}[/dim yellow]")

    # 7. Rigorous Verification
    verification = Verifier.verify(
        dest_file,
        expected_size=primary_asset.expected_size,
        expected_ext=dest_file.suffix
    )

    if not verification.valid:
        ver_err = DAError(
            f"Verification failed for {primary_asset.filename}: {verification.error_message}",
            details={"verification": verification.__dict__}
        )
        _handle_error(ver_err, agent_mode)
        sys.exit(1)

    primary_asset.verified = True

    # 8. Sidecar Generation
    sidecar_paths = {}
    if not no_sidecar:
        sidecar_paths = SidecarWriter.write_sidecars(
            dest_dir=base_dir,
            package=package,
            primary_filename=primary_asset.filename,
            cover_filename=cover_filename,
            subtitle_filename=subtitle_filename
        )

    # 9. Driver Post-Download Cleanup Hook (e.g. Cloud Drive zero-trace deletion)
    try:
        driver.cleanup(package)
    except Exception as e:
        if verbose and not agent_mode:
            console.print(f"[dim yellow]Warning: Cleanup hook failed: {e}[/dim yellow]")

    # 10. Deliver Success Output
    if agent_mode:
        sidecar_dict = {k: str(v.resolve()) for k, v in sidecar_paths.items()}
        if cover_filename:
            sidecar_dict["cover"] = str((base_dir / cover_filename).resolve())
        if subtitle_filename:
            sidecar_dict["subtitle"] = str((base_dir / subtitle_filename).resolve())

        agent_result = {
            "status": "success",
            "platform": package.platform,
            "title": package.title,
            "output_dir": str(base_dir.resolve()),
            "primary_asset": str(dest_file.resolve()),
            "size_bytes": downloaded_size,
            "sidecars": sidecar_dict,
            "verification": {
                "valid": verification.valid,
                "detected_type": verification.detected_type,
                "details": verification.details
            }
        }
        print(json.dumps(agent_result, ensure_ascii=False, indent=2))
    else:
        success_table = Table(show_header=False, box=None)
        success_table.add_row("[bold green]✔[/bold green] [bold]Primary Asset:[/bold]", str(dest_file.resolve()))
        success_table.add_row("[bold green]✔[/bold green] [bold]Verified Format:[/bold]", f"{verification.detected_type} ({downloaded_size / (1024*1024):.2f} MB)")
        success_table.add_row("[bold green]✔[/bold green] [bold]Asset Folder:[/bold]", str(base_dir.resolve()))
        if sidecar_paths:
            success_table.add_row("[bold green]✔[/bold green] [bold]Sidecars:[/bold]", "content.info.json, content.md")

        console.print(Panel(
            success_table,
            title="[bold green]Download Complete & Verified[/bold green]",
            border_style="green"
        ))

def _handle_error(err: Exception, agent_mode: bool):
    """Deliver uniform error outputs for human CLI and agent skill."""
    err_type = type(err).__name__
    err_msg = str(err)
    if agent_mode:
        print(json.dumps({
            "status": "error",
            "error_type": err_type,
            "message": err_msg
        }, ensure_ascii=False, indent=2))
    else:
        err_console.print(Panel(
            f"[bold red]{err_type}:[/bold red] {err_msg}",
            title="[bold red]Operation Failed[/bold red]",
            border_style="red"
        ))

if __name__ == "__main__":
    main()
