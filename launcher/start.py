import os
import sys
import json
import subprocess
import platform
import urllib.request
import zipfile
import tarfile
import shutil
import time
import argparse
from pathlib import Path
from typing import Tuple, Optional, List

ROOT_DIR = Path(__file__).parent.parent.resolve()
VENV_DIR = ROOT_DIR / ".venv"
LAUNCHER_DIR = ROOT_DIR / "launcher"
TOOL_DIR = LAUNCHER_DIR / "tool"
UV_DIR = TOOL_DIR / "uv"
UV_CACHE_DIR = TOOL_DIR / ".uv_cache"
IS_WINDOWS = platform.system() == "Windows"
VENV_PYTHON = (
    VENV_DIR / "Scripts" / "python.exe" if IS_WINDOWS else VENV_DIR / "bin" / "python"
)
UV_PATH = UV_DIR / "uv.exe" if IS_WINDOWS else UV_DIR / "uv"

CORE_REPO_URL = "https://github.com/Ner-Kun/omni-trans-core"
CORE_API_URL = "https://api.github.com/repos/Ner-Kun/omni-trans-core/releases/latest"
CORE_ASSET_NAME = "omni-trans-core.zip"
CORE_INSTALL_PATH = ROOT_DIR / "omni_trans_core"
APP_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/version.txt"
)
REQUIREMENTS_URL = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/requirements.txt"
)
LOCAL_REQUIREMENTS_PATH = TOOL_DIR / "requirements.txt"


def is_running_in_venv() -> bool:
    return sys.prefix == str(VENV_DIR)


def ensure_venv_and_relaunch():
    if is_running_in_venv():
        return
    print("INFO: Virtual environment (.venv) is not active.")
    if not VENV_DIR.exists():
        print(f"INFO: Creating virtual environment at '{VENV_DIR}'...")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
            print("INFO: Virtual environment created successfully.")
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Failed to create virtual environment: {e}")
            sys.exit(1)
    print("INFO: Relaunching script in the virtual environment...")
    try:
        launcher_script_path = LAUNCHER_DIR / "start.py"
        completed_process = subprocess.run(
            [str(VENV_PYTHON), str(launcher_script_path), *sys.argv[1:]]
        )
        sys.exit(completed_process.returncode)
    except FileNotFoundError:
        print(f"ERROR: Python interpreter not found at '{VENV_PYTHON}'.")
        sys.exit(1)

def get_uv_asset_info() -> Tuple[Optional[str], Optional[str]]:
    system, machine = platform.system(), platform.machine()
    if system == "Windows" and machine in ["AMD64", "x86_64"]:
        return "uv-x86_64-pc-windows-msvc.zip", "uv.exe"
    if system == "Linux" and machine == "x86_64":
        return "uv-x86_64-unknown-linux-gnu.tar.gz", "uv"
    if system == "Linux" and machine == "aarch64":
        return "uv-aarch64-unknown-linux-gnu.tar.gz", "uv"
    if system == "Darwin" and machine == "x86_64":
        return "uv-x86_64-apple-darwin.tar.gz", "uv"
    if system == "Darwin" and machine == "arm64":
        return "uv-aarch64-apple-darwin.tar.gz", "uv"
    return None, None


def ensure_uv_available():
    if UV_PATH.exists():
        return
    console.print("ℹ️  'uv' installer not found. Attempting to download it...")
    asset_name, executable_name = get_uv_asset_info()
    if not asset_name:
        console.print(
            f"[red]✗ ERROR: Your OS/architecture ({platform.system()}/{platform.machine()}) is not automatically supported.[/red]"
        )
        sys.exit(1)
    download_url = (
        f"https://github.com/astral-sh/uv/releases/latest/download/{asset_name}"
    )
    UV_DIR.mkdir(parents=True, exist_ok=True)
    temp_archive_path = UV_DIR / asset_name
    try:
        with console.status(
            "Downloading '[bold cyan]uv[/bold cyan]'...", spinner="dots"
        ):
            with (
                urllib.request.urlopen(download_url) as response,
                open(temp_archive_path, "wb") as out_file,
            ):
                shutil.copyfileobj(response, out_file)
        console.print("[green]✓[/green] Download complete.")

        with console.status(
            f"Extracting '[bold cyan]{asset_name}[/bold cyan]'...", spinner="dots"
        ):
            if temp_archive_path.suffix == ".zip":
                with zipfile.ZipFile(temp_archive_path, "r") as zf:
                    zf.extract(executable_name, path=UV_DIR)
            elif temp_archive_path.suffix == ".gz":
                with tarfile.open(temp_archive_path, "r:gz") as tf:
                    tf.extract(executable_name, path=UV_DIR)
            if not IS_WINDOWS:
                UV_PATH.chmod(0o755)
        console.print("[green]✓[/green] 'uv' installed successfully.")
    except Exception as e:
        console.print(f"[red]✗ ERROR: Failed to download or extract 'uv': {e}[/red]")
        sys.exit(1)
    finally:
        if temp_archive_path.exists():
            os.remove(temp_archive_path)

def run_uv_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(UV_PATH), *args], check=False, text=True)

def manage_requirements(args: argparse.Namespace) -> bool:
    if args.skip_deps:
        console.print(
            "[yellow]ℹ️  --skip-deps flag detected. Skipping dependency management.[/yellow]"
        )
        return True

    console.print(
        Panel(
            "Managing Dependencies",
            title="[bold cyan]Step 1[/bold cyan]",
            border_style="cyan",
        )
    )
    try:
        with console.status(
            f"Fetching latest requirements from [link={REQUIREMENTS_URL}]GitHub[/link]...",
            spinner="dots",
        ):
            with urllib.request.urlopen(REQUIREMENTS_URL, timeout=5) as response:
                content = response.read()
        LOCAL_REQUIREMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_REQUIREMENTS_PATH, "wb") as f:
            f.write(content)
        console.print(
            "[green]✓[/green] Successfully downloaded [bold]requirements.txt[/bold]."
        )
    except Exception as e:
        console.print(
            f"[yellow]⚠ WARNING: Could not fetch latest requirements.txt: {e}[/yellow]"
        )
        if not LOCAL_REQUIREMENTS_PATH.exists():
            console.print(
                "[red]✗ ERROR: No local copy of requirements.txt found. Cannot proceed.[/red]"
            )
            return False
        console.print(
            "ℹ️  Using previously downloaded local copy of [bold]requirements.txt[/bold]."
        )

    command = ["pip", "install", "-r", str(LOCAL_REQUIREMENTS_PATH)]
    if args.force_update:
        console.print(
            "[yellow]ℹ️  --force-update flag detected. Re-installing all packages.[/yellow]"
        )
        command.append("--reinstall")

    result = run_uv_command(command)

    if result.returncode != 0:
        console.print(
            "[red]✗ Failed to install dependencies. See the output above for details.[/red]"
        )
        return False

    console.print("[green]✓[/green] Dependencies are up to date.")
    return True

def handle_clean_argument():
    console.print(
        Panel("[bold yellow]--clean operation[/bold yellow]", title="✨ Clean Install")
    )
    targets = [VENV_DIR, TOOL_DIR, CORE_INSTALL_PATH]

    text = Text("This will remove the following directories to ensure a fresh start:\n")
    for target in targets:
        text.append("\n • ", style="yellow")
        text.append(str(target), style="cyan")

    console.print(Panel(text, border_style="yellow"))

    if Confirm.ask("\nAre you sure you want to proceed?", default=False):
        for target in targets:
            if target.exists():
                try:
                    console.print(f"Removing {target}...")
                    shutil.rmtree(target)
                    console.print(f"[green]✓ Removed {target}.[/green]")
                except OSError as e:
                    console.print(f"[red]✗ Error removing {target}: {e}[/red]")
        console.print(
            "\n[bold green]Clean operation complete. Please run the launcher again to reinstall.[/bold green]"
        )
    else:
        console.print("[yellow]Clean operation cancelled.[/yellow]")
    sys.exit(0)


def check_core_installed() -> bool:
    return CORE_INSTALL_PATH.exists() and (CORE_INSTALL_PATH / "__init__.py").exists()


def install_core() -> bool:
    console.print(
        Panel(
            "📦 Installing Omni Trans Core",
            title="[bold cyan]Step 2[/bold cyan]",
            border_style="cyan",
        )
    )
    temp_archive_path = ROOT_DIR / CORE_ASSET_NAME
    temp_extract_dir = ROOT_DIR / "temp_extract"

    try:
        with console.status(
            "Fetching latest release info from [bold blue]GitHub API[/bold blue]..."
        ):
            req = urllib.request.Request(
                CORE_API_URL, headers={"User-Agent": "Omni-Trans-Launcher"}
            )
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    console.print(
                        f"[red]✗ Failed to fetch release info (HTTP {response.status}).[/red]"
                    )
                    return False
                release_data = json.loads(response.read().decode())

        asset_url = None
        for asset in release_data.get("assets", []):
            if asset.get("name") == CORE_ASSET_NAME:
                asset_url = asset.get("browser_download_url")
                break

        if not asset_url:
            console.print(
                f"[red]✗ Could not find asset '{CORE_ASSET_NAME}' in the latest release.[/red]"
            )
            console.print(
                "[yellow]ℹ️  Please ensure a release exists and contains the correct ZIP file.[/yellow]"
            )
            return False

        console.print(f"Downloading core from: [cyan]{asset_url}[/cyan]")
        with console.status(
            "Downloading '[bold cyan]Omni Trans Core[/bold cyan]'...", spinner="dots"
        ):
            with (
                urllib.request.urlopen(asset_url) as response,
                open(temp_archive_path, "wb") as out_file,
            ):
                shutil.copyfileobj(response, out_file)
        console.print("[green]✓[/green] Core downloaded successfully.")

        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
        temp_extract_dir.mkdir()

        with console.status(
            f"Extracting '[bold cyan]{CORE_ASSET_NAME}[/bold cyan]'...", spinner="dots"
        ):
            with zipfile.ZipFile(temp_archive_path, "r") as zf:
                zf.extractall(temp_extract_dir)

        core_source_path = None
        for root, dirs, _ in os.walk(temp_extract_dir):
            if "omni_trans_core" in dirs:
                core_source_path = Path(root) / "omni_trans_core"
                break

        if not core_source_path or not core_source_path.exists():
            console.print(
                "[red]✗ 'omni_trans_core' folder not found in the downloaded archive.[/red]"
            )
            return False

        shutil.move(str(core_source_path), str(CORE_INSTALL_PATH))
        console.print("[green]✓ Omni Trans Core installed successfully![/green]")
        return True

    except Exception as e:
        console.print(
            f"[red]✗ An unexpected error occurred during core installation: {e}[/red]"
        )
        return False
    finally:
        if temp_archive_path.exists():
            os.remove(temp_archive_path)
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)


def check_git_installed() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def fetch_app_manifest() -> Optional[List[dict]]:
    try:
        with console.status(
            f"Fetching app manifest from [link={APP_MANIFEST_URL}]GitHub[/link]..."
        ):
            with urllib.request.urlopen(APP_MANIFEST_URL, timeout=5) as response:
                content = response.read().decode("utf-8")

        apps = []
        for line in content.splitlines():
            if line.strip().upper().startswith("APP_"):
                try:
                    _, value = line.split("=", 1)
                    name, folder = value.strip().split(";")
                    apps.append({"name": name.strip(), "folder": folder.strip()})
                except ValueError:
                    console.print(
                        f"[yellow]⚠ Warning: Could not parse app line: {line}[/yellow]"
                    )

        if apps:
            console.print(f"[green]✓ Found {len(apps)} app(s) in manifest.[/green]")
            table = Table(
                title="[bold magenta]Available Applications[/bold magenta]",
                border_style="magenta",
            )
            table.add_column("App Name", style="cyan", no_wrap=True)
            table.add_column("Folder", style="green")
            for app in apps:
                table.add_row(app["name"], app["folder"])
            console.print(table)
            return apps
        console.print("[yellow]⚠ No applications found in the manifest.[/yellow]")
        return None
    except Exception as e:
        console.print(f"[yellow]⚠ Could not fetch app manifest: {e}[/yellow]")
        return None


def find_launchable_app() -> Optional[Path]:
    console.print(
        Panel(
            "🔍 Searching for a launchable application...",
            title="[bold cyan]Step 3[/bold cyan]",
            border_style="cyan",
        )
    )

    app_manifest = fetch_app_manifest()

    if app_manifest:
        console.print("ℹ️  Searching for apps listed in the manifest...")
        for app_info in app_manifest:
            app_folder = ROOT_DIR / app_info["folder"]
            runner_path = app_folder / "runner.py"
            if runner_path.exists():
                console.print(
                    f"[green]✓ Found '{app_info['name']}' via manifest at: {app_folder}[/green]"
                )
                return runner_path

    console.print(
        "ℹ️  Manifest not available or no listed apps found locally. Scanning folders..."
    )
    excluded_dirs = {
        ".git",
        ".venv",
        "launcher",
        "omni_trans_core",
        "tool",
        "__pycache__",
    }
    for item in ROOT_DIR.iterdir():
        if item.is_dir() and item.name not in excluded_dirs:
            runner_path = item / "runner.py"
            if runner_path.exists():
                console.print(
                    f"[green]✓ Found launchable app by scanning at: {item}[/green]"
                )
                return runner_path

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Launcher for Omni Trans based applications."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove .venv, tool, and omni_trans_core for a clean reinstall.",
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force re-installation of all Python dependencies.",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip all dependency installation and checks.",
    )
    args = parser.parse_args()

    if not is_running_in_venv() and not args.clean:
        ensure_venv_and_relaunch()

    os.environ["UV_CACHE_DIR"] = str(UV_CACHE_DIR)

    if not args.skip_deps:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich"],
            capture_output=True,
            check=False,
        )

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Confirm
        from rich.status import Status
        from rich.table import Table
        from rich.text import Text

        console = Console()
    except ImportError:
        class FallbackConsole:
            def print(self, msg):
                import re

                print(re.sub(r"\[.*?\]", "", msg))

        console = FallbackConsole()

    if args.clean:
        handle_clean_argument()

    console.print(
        Panel.fit(
            "[bold green]Omni Trans Launcher[/bold green]",
            subtitle="[cyan]v1.0.0-alpha[/cyan]",
            border_style="green",
        )
    )

    if not check_git_installed():
        console.print(
            Panel(
                "[red]Git is not installed or not in PATH.[/red]\n[yellow]Please install Git and ensure it is available in your system's PATH to proceed.[/yellow]",
                title="[bold red]✗ Requirement Missing[/bold red]",
            )
        )
        sys.exit(1)

    if not manage_requirements(args):
        sys.exit(1)

    if not check_core_installed():
        console.print(
            Panel("[yellow]⚠ Omni Trans Core not found.[/yellow]", title="Core Missing")
        )
        if Confirm.ask("\nDo you want to install Omni Trans Core now?", default=True):
            if not install_core():
                console.print("[red]✗ Core installation failed. Exiting.[/red]")
                sys.exit(1)
        else:
            console.print("[red]✗ Cannot proceed without the core. Exiting.[/red]")
            sys.exit(1)
    else:
        console.print("[green]✓ Omni Trans Core is already installed.[/green]")

    try:
        runner_path = find_launchable_app()
        if not runner_path:
            console.print(
                Panel(
                    "[red]Fatal: No launchable application found. Could not find a 'runner.py' in any application folder.[/red]",
                    title="[bold red]✗ Launch Error[/bold red]",
                )
            )
            time.sleep(10)
            sys.exit(1)

        console.print(
            Panel(
                f"🚀 Launching [bold green]{runner_path.parent.name}[/bold green]...",
                title="[bold blue]Starting Application[/bold blue]",
            )
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)

        result = subprocess.run(
            [sys.executable, str(runner_path)], check=False, env=env
        )

        if result.returncode != 0:
            console.print(
                f"[yellow]⚠ Application exited with a non-zero code: {result.returncode}[/yellow]"
            )
        else:
            console.print("[green]✓ Application finished successfully.[/green]")
        sys.exit(result.returncode)

    except KeyboardInterrupt:
        console.print("\n[yellow]👋 Application interrupted by user. Exiting.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(
            f"[red]✗ An unexpected error occurred while starting the application: {e}[/red]"
        )
        time.sleep(10)
        sys.exit(1)
