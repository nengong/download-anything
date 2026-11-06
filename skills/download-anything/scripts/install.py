#!/usr/bin/env python3
"""Install DA from a bundled wheel, source checkout, or matching release."""
import argparse
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import sysconfig

MIN_PYTHON = (3, 10)
SKILL_VERSION = "0.1.1"
REPOSITORY = "https://github.com/nengong/download-anything"
MANAGED_PYTHON = "3.12"
# Official PyPI first, then the mirrors most likely to work from mainland China.
PYPI_MIRRORS = (
    ("清华镜像", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云镜像", "https://mirrors.aliyun.com/pypi/simple/"),
)
PIP_TIMEOUT_SECONDS = 25
INSTALL_TIMEOUT_SECONDS = 1800


def _format_version(version):
    return ".".join(str(part) for part in version)


def _supported(version):
    return bool(version) and tuple(version[:2]) >= MIN_PYTHON


def _probe_python(command):
    """Return (major, minor, micro) for an interpreter command, or None."""
    try:
        result = subprocess.run(
            list(command) + ["-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return tuple(int(part) for part in result.stdout.strip().split(".")[:3])
    except ValueError:
        return None


def _python_candidates():
    """Yield interpreter commands, preferring common modern versions."""
    commands = [[sys.executable]]
    for minor in ("3.12", "3.13", "3.11", "3.10", "3.14"):
        commands.append(["python" + minor])
    commands.extend([["python3"], ["python"]])
    if os.name == "nt":
        for minor in ("3.12", "3.13", "3.11", "3.10", "3.14"):
            commands.append(["py", "-" + minor])
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            for tag in ("312", "313", "311", "310", "314"):
                commands.append([
                    str(Path(local_app_data) / "Programs" / "Python" / ("Python" + tag) / "python.exe")
                ])
    else:
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            for minor in ("3.12", "3.13", "3.11", "3.10", "3.14"):
                commands.append([prefix + "/python" + minor])
        pyenv_versions = Path.home() / ".pyenv" / "versions"
        if pyenv_versions.is_dir():
            for path in sorted(pyenv_versions.glob("3.1*/bin/python3"), reverse=True):
                commands.append([str(path)])
    seen = set()
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            yield command


def _find_compatible_python():
    if _supported(sys.version_info[:3]):
        return [sys.executable], tuple(sys.version_info[:3])
    for command in _python_candidates():
        version = _probe_python(command)
        if _supported(version):
            return command, version
    return None, None


def _display(command):
    return " ".join(command)


def _confirm(question):
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(question).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("", "y", "yes", "是", "好")


def _pip_sources():
    sources = []
    custom = os.environ.get("DA_PIP_INDEX_URL", "").strip()
    if custom:
        sources.append(("自定义源 DA_PIP_INDEX_URL", custom))
    sources.append(("官方 PyPI", None))
    sources.extend(PYPI_MIRRORS)
    return sources


def _install_with_mirrors(base_command, packages, apply_pip_timeout, label):
    """Run an install command, falling back to domestic mirrors on timeout/failure."""
    last_error = None
    env = os.environ.copy()
    env.setdefault("UV_HTTP_TIMEOUT", str(PIP_TIMEOUT_SECONDS * 2))
    for name, index_url in _pip_sources():
        command = list(base_command)
        if apply_pip_timeout:
            command += ["--timeout", str(PIP_TIMEOUT_SECONDS), "--retries", "0" if index_url is None else "2"]
        if index_url:
            command += ["--index-url", index_url]
        command += list(packages)
        print("[install] %s：%s ..." % (label, name), flush=True)
        try:
            subprocess.run(command, check=True, timeout=INSTALL_TIMEOUT_SECONDS, env=env)
            if index_url:
                print("[install] 已通过%s完成。" % name, flush=True)
            return True
        except subprocess.TimeoutExpired as exc:
            last_error = exc
            print("[install] %s超时。" % name, flush=True)
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print("[install] %s失败（退出码 %s）。" % (name, exc.returncode), flush=True)
        except OSError as exc:
            last_error = exc
            print("[install] 无法执行安装命令：%s" % exc, flush=True)
            break
        if index_url is None:
            print("[install] 官方源连接失败，自动切换到国内镜像……", flush=True)
        else:
            print("[install] 自动切换下一个镜像……", flush=True)
    print("[install] %s失败。最后错误：%s" % (label, last_error), flush=True)
    return False


def _locate_uv():
    found = shutil.which("uv")
    if found:
        return found
    names = ("uv.exe",) if os.name == "nt" else ("uv",)
    candidates = [Path(sysconfig.get_path("scripts")) / name for name in names]
    scheme = "nt_user" if os.name == "nt" else "posix_user"
    try:
        candidates.append(Path(sysconfig.get_path("scripts", scheme)) / names[0])
    except (KeyError, TypeError):
        pass
    user_base = getattr(site, "USER_BASE", None)
    if user_base:
        candidates.extend(Path(user_base) / "bin" / name for name in names)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _bootstrap_uv(auto_yes):
    print("[install] 当前 Python 低于 3.10，且本机没有找到可用的新版解释器。", flush=True)
    print("[install] 可以用 uv 下载独立 Python %s，不改动系统自带的 Python。" % MANAGED_PYTHON, flush=True)
    if not auto_yes and not _confirm("现在自动安装 uv 并准备 Python %s？[Y/n] " % MANAGED_PYTHON):
        return None
    base = [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check"]
    if not _install_with_mirrors(base, ["uv"], True, "安装 uv"):
        return None
    uv = _locate_uv()
    if not uv:
        print("[install] uv 已安装，但还不在 PATH 中。请重开终端，或直接用完整路径运行后重试。", flush=True)
    return uv


def _python_guidance():
    script = str(Path(__file__).resolve())
    rerun = 'python3.12 "%s"' % script
    if sys.platform == "darwin":
        steps = (
            "  brew install python@3.12\n"
            "  brew install uv   # 或者：python3 -m pip install --user uv"
        )
    elif sys.platform == "win32":
        steps = (
            "  winget install -e --id Python.Python.3.12\n"
            "  winget install -e --id astral-sh.uv"
        )
        rerun = 'py -3.12 "%s"' % script
    else:
        steps = (
            "  sudo apt install python3.12 python3.12-venv   # Debian/Ubuntu\n"
            "  sudo dnf install python3.12                   # Fedora\n"
            "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        )
    return (
        "Download Anything 需要 Python 3.10 或更高版本。\n"
        "macOS 自带的 python3 常年停留在 3.9，装过 Python 也可能被它挡住。\n"
        "请任选一种方式安装 3.10+（或用 uv 自动下载独立 Python）：\n%s\n"
        "完成后重新运行：%s\n"
        "非交互环境可加 --yes，允许脚本自动安装 uv 并准备 Python。"
        % (steps, rerun)
    )


def _create_venv(target, uv, interpreter, auto_yes=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    if interpreter and len(interpreter) > 1:
        # A Windows py launcher command is not a uv --python value. Use that
        # already-probed interpreter directly; do not silently download another.
        subprocess.run(list(interpreter) + ["-m", "venv", str(target)], check=True)
        return True
    if uv:
        if interpreter and len(interpreter) == 1:
            python_spec = interpreter[0]
        elif _supported(sys.version_info[:3]):
            python_spec = sys.executable
        else:
            python_spec = MANAGED_PYTHON
        if python_spec == MANAGED_PYTHON and interpreter is None and not auto_yes:
            if not _confirm(
                "本机没有找到可用的 Python 3.10+，是否让 uv 准备独立的 Python %s？[Y/n] "
                % MANAGED_PYTHON
            ):
                return False
        command = [uv, "venv", "--python", python_spec]
        if interpreter is not None:
            command += ["--no-python-downloads"]
        command += [str(target)]
        print("[install] 创建虚拟环境：%s" % _display(command), flush=True)
        try:
            subprocess.run(command, check=True)
            return True
        except (subprocess.CalledProcessError, OSError) as exc:
            print("[install] uv 创建环境失败：%s" % exc, flush=True)
            if python_spec == MANAGED_PYTHON and not os.environ.get("UV_PYTHON_INSTALL_MIRROR"):
                mirror = "https://gh-proxy.com/https://github.com/astral-sh/python-build-standalone/releases/download"
                print("[install] 尝试通过国内 GitHub 镜像下载 Python……", flush=True)
                env = os.environ.copy()
                env["UV_PYTHON_INSTALL_MIRROR"] = mirror
                try:
                    subprocess.run(command, check=True, env=env)
                    return True
                except (subprocess.CalledProcessError, OSError) as mirror_exc:
                    print("[install] 国内镜像下载 Python 也失败了：%s" % mirror_exc, flush=True)
            if not interpreter:
                return False
            print("[install] 改用本机 Python 创建环境。", flush=True)
    if not interpreter:
        return False
    command = list(interpreter) + ["-m", "venv", str(target)]
    print("[install] 创建虚拟环境：%s" % _display(command), flush=True)
    subprocess.run(command, check=True)
    return True


def _ensure_pip(python):
    probe = subprocess.run([str(python), "-m", "pip", "--version"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        # uv venv is unseeded. Repair it using the interpreter's bundled pip.
        subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], check=True)


def _remote_packages():
    tag = "v" + SKILL_VERSION
    wheel = "%s/releases/download/%s/download_anything-%s-py3-none-any.whl" % (REPOSITORY, tag, SKILL_VERSION)
    git = REPOSITORY + ".git@" + tag
    return [wheel, "https://gh-proxy.com/" + wheel,
            "git+" + git, "git+https://gh-proxy.com/" + git]


def main():
    # Legacy Windows consoles may not be able to encode the Chinese status text.
    # Keep the console's encoding, but never let a progress message abort installation.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=Path.home() / ".download-anything" / "venv")
    parser.add_argument("--yes", action="store_true", help="允许联网获取 CLI、uv 和独立 Python，不再交互询问")
    args = parser.parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    wheels = sorted((skill_dir / "assets").glob("download_anything-*.whl"))
    source = skill_dir.parent.parent
    if wheels:
        package = str(wheels[-1])
    elif (source / "pyproject.toml").is_file() and (source / "cli.py").is_file():
        package = str(source)
    else:
        package = None
        if not args.yes and not _confirm("未找到本地 CLI，是否联网下载匹配版本 v%s？[Y/n] " % SKILL_VERSION):
            sys.exit("未获准联网下载 CLI；请使用完整发布包或重新运行并确认。")

    target = args.venv.expanduser().resolve()
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file():
        existing_version = _probe_python([str(python)])
        if not _supported(existing_version):
            shown = _format_version(existing_version) if existing_version else "未知"
            remove_hint = (
                '  rmdir /s /q "%s"' % target
                if os.name == "nt"
                else '  rm -rf "%s"' % target
            )
            sys.exit(
                "现有环境 %s 使用的是 Python %s，低于 3.10。\n"
                "请用 --venv 指定一个新路径，或删除该环境后重试：\n%s"
                % (target, shown, remove_hint)
            )

    uv = _locate_uv()
    allow_python_download = args.yes
    if not python.is_file():
        interpreter, interpreter_version = _find_compatible_python()
        if interpreter:
            print(
                "[install] 使用 Python %s：%s" % (_format_version(interpreter_version), _display(interpreter)),
                flush=True,
            )
        if uv is None and interpreter is None:
            uv = _bootstrap_uv(args.yes)
            # The bootstrap prompt already covers preparing a managed Python.
            allow_python_download = allow_python_download or uv is not None
        if uv is None and interpreter is None:
            sys.exit(_python_guidance())
        if not _create_venv(target, uv, interpreter, auto_yes=allow_python_download):
            sys.exit(_python_guidance())
        created_version = _probe_python([str(python)])
        if not _supported(created_version):
            shown = _format_version(created_version) if created_version else "未知"
            sys.exit("新建环境仍是 Python %s，低于 3.10。请安装新版 Python 后重试。\n%s" % (shown, _python_guidance()))

    uv = uv or _locate_uv()
    if uv:
        base = [uv, "pip", "install", "--python", str(python)]
        pip_timeout = False
    else:
        _ensure_pip(python)
        base = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
        pip_timeout = True
    installed = False
    for candidate in [package] if package else _remote_packages():
        if _install_with_mirrors(base, [candidate], pip_timeout, "安装 DA 与依赖"):
            installed = True
            break
        if not package:
            print("[install] 尝试下一个匹配版本的下载地址……", flush=True)
    if not installed:
        sys.exit("安装失败。请检查网络；如使用自定义源，可设置 DA_PIP_INDEX_URL 后重试。")

    executable = target / ("Scripts/da.exe" if os.name == "nt" else "bin/da")
    subprocess.run([str(executable), "--help"], check=True, stdout=subprocess.DEVNULL)
    print("Installed: %s" % executable)
    print("Add its parent directory to PATH, or invoke the full path above.")


if __name__ == "__main__":
    main()
