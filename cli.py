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
from core.path_resolver import resolve_output_directory, sanitize_filename, get_system_downloads_dir
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
@click.argument("subtarget", required=False)
@click.option("-o", "--output-dir", help="Output directory path (default: ~/Downloads/DA/<folder>)")
@click.option("-p", "--password", help="Explicit password/passcode if not embedded in input")
@click.option("--max-mb", default=500, type=int, help="Maximum allowed file size in MB (default: 500)")
@click.option("--check", is_flag=True, help="Dry run: inspect and extract metadata without downloading")
@click.option("--no-sidecar", is_flag=True, help="Disable generating sidecar metadata (.info.json and .md)")
@click.option("--json", "agent_mode", is_flag=True, help="Agent mode: output JSON result to stdout")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logs")
def main(
    target: Optional[str],
    subtarget: Optional[str],
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
    if target in ("login", "auth"):
        platform_name = (subtarget or "quark").lower()
        _handle_login(platform_name)
        sys.exit(0)

    if target in ("doctor", "check-env", "diagnose"):
        _handle_doctor(subtarget, agent_mode)
        sys.exit(0)

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

    # 4. Resolve Output Directory (Workspace sensing -> OS Native Downloads)
    base_dir = resolve_output_directory(output_dir, title=package.title, create_subfolder=True)
    base_dir.mkdir(parents=True, exist_ok=True)

    # 4.1 Smart File Renaming (Refuse meaningless digits and generic names)
    clean_title = sanitize_filename(package.title, max_length=70)
    raw_ext = Path(primary_asset.filename).suffix
    if not raw_ext:
        raw_ext = ".mp4"

    is_generic_name = (
        primary_asset.filename.startswith("content.") or 
        primary_asset.filename.startswith("article.") or
        primary_asset.filename.startswith("video.") or
        primary_asset.filename[0].isdigit()
    )
    if is_generic_name and clean_title and clean_title != "untitled_asset":
        primary_asset.filename = f"{clean_title}{raw_ext}"

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
        comp_ext = Path(companion.filename).suffix
        if companion.file_type == "cover":
            companion.filename = f"{clean_title}.cover{comp_ext or '.jpg'}" if clean_title != "untitled_asset" else "cover.jpg"
            cover_filename = companion.filename
        elif companion.file_type == "subtitle":
            companion.filename = f"{clean_title}.subtitle{comp_ext or '.srt'}" if clean_title != "untitled_asset" else "subtitle.srt"
            subtitle_filename = companion.filename

        comp_dest = base_dir / companion.filename
        try:
            fetcher.download(
                url=companion.url,
                dest_path=comp_dest,
                headers=companion.headers,
                expected_size=companion.expected_size
            )
            companion.local_path = comp_dest
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

def _handle_login(platform: str):
    """Automated login helper: harvests from browser or triggers headless capture."""
    import shutil
    import subprocess
    from core.credentials import credentials_manager

    platform = platform.lower()
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
        console.print(Panel(
            f"[bold green]✔ 成功直接从默认浏览器中捕获到 {platform} 的登录 Cookie！已自动保存。[/bold green]\n"
            "[dim]现在直接运行 da \"<网盘链接>\" 即可免登极速下载。[/dim]",
            border_style="green"
        ))
        return

    # 2. Check native desktop app databases
    cookie = credentials_manager._harvest_from_desktop_apps(platform)
    if cookie:
        credentials_manager.save_credential(platform, cookie)
        console.print(Panel(
            f"[bold green]✔ 成功从本地桌面客户端数据库捕获到 {platform} 凭据！已自动保存。[/bold green]",
            border_style="green"
        ))
        return

    # 3. Automated Browser Capture window (zero manual copying)
    console.print("[dim yellow]macOS 提示：默认浏览器 Cookies 受系统保护。即将弹出登录窗口，登录后脚本将自动抓取凭据，无需手动复制！[/dim yellow]")
    login_urls = {
        "quark": "https://pan.quark.cn/",
        "baidu": "https://pan.baidu.com/",
    }
    target_url = login_urls.get(platform, f"https://pan.{platform}.com/")
    domain = domains[0]

    grab_bin = shutil.which("grab-cookie") or "/Users/c.k/coding-agent-hub/bin/grab-cookie"
    if os.path.exists(grab_bin):
        try:
            cmd = [grab_bin, target_url, "--domain", domain, "--no-probe"]
            subprocess.run(cmd)
            console.print("[bold green]✔ 凭据捕获完成！现在可直接下载。[/bold green]")
        except Exception as e:
            console.print(f"[bold red]自动弹窗抓取失败: {e}[/bold red]")
    else:
        console.print(
            "[bold yellow]💡 一劳永逸全自动方法：[/bold yellow]\n"
            "在 macOS『系统设置 ➔ 隐私与安全性 ➔ 完全磁盘访问权限』中勾选当前终端/IDE，\n"
            "da 就能永久静默自动读取 Chrome/Safari 中的百度/夸克 Cookie，无需任何操作！"
        )

def _handle_doctor(subtarget: Optional[str], agent_mode: bool):
    """Diagnose Python environment, dependencies, and external utilities."""
    from core.doctor import Doctor
    fix = (subtarget in ("--fix", "-f") or "--fix" in sys.argv)
    if fix:
        if not agent_mode:
            console.print("[bold yellow]正在自动修复缺失的 Python 依赖包...[/bold yellow]")
        Doctor.auto_repair()

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
