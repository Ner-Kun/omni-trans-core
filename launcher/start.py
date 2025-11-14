import os
import sys
import subprocess
import platform
import urllib.request
import urllib.parse
import zipfile
import tarfile
import shutil
import time
import argparse
import logging
import traceback
import json
import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict

ROOT_DIR = Path(__file__).parent.parent.resolve()
LOG_FILE_PATH = ROOT_DIR / "launcher.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=LOG_FILE_PATH,
    filemode="w",
    encoding="utf-8",
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logging.getLogger().addHandler(console_handler)


def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    print("\n\nFATAL ERROR: The application crashed. See launcher.log for details.")
    print("This window will close in 15 seconds...")
    time.sleep(15)


sys.excepthook = handle_exception

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
CORE_API_URL = "https://api.github.com/repos/Ner-Kun/omni-trans-core/releases"
CORE_ASSET_NAME = "omni-trans-core.zip"
CORE_INSTALL_PATH = ROOT_DIR / "omni_trans_core"

APP_CATALOG_URL = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/launcher-manifest.txt"
REQUIREMENTS_URL = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/requirements.txt"
)
LOCAL_REQUIREMENTS_PATH = TOOL_DIR / "requirements.txt"


def is_running_in_venv() -> bool:
    return sys.prefix == str(VENV_DIR)


def ensure_venv_and_relaunch():
    if is_running_in_venv():
        return
    logging.info("Virtual environment (.venv) is not active.")
    if not VENV_DIR.exists():
        logging.info(f"Creating virtual environment at '{VENV_DIR}'...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(VENV_DIR)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            logging.debug(f"Venv creation stdout: {result.stdout}")
            logging.info("Virtual environment created successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to create virtual environment: {e}")
            logging.error(f"Stderr: {e.stderr}")
            sys.exit(1)

    logging.info("Relaunching script in the virtual environment...")
    try:
        launcher_script_path = LAUNCHER_DIR / "start.py"
        completed_process = subprocess.run(
            [str(VENV_PYTHON), str(launcher_script_path), *sys.argv[1:]]
        )
        sys.exit(completed_process.returncode)
    except FileNotFoundError:
        logging.error(f"Python interpreter not found at '{VENV_PYTHON}'.")
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


def download_and_extract_asset(
    download_url: str,
    asset_name: str,
    destination_dir: Path,
    post_extract_callback: callable = None,
) -> bool:
    destination_dir.mkdir(parents=True, exist_ok=True)
    temp_archive_path = destination_dir / asset_name

    try:
        logging.info(f"Downloading '{asset_name}' from {download_url}")
        req = urllib.request.Request(
            download_url, headers={"User-Agent": "Omni-Trans-Launcher"}
        )
        with (
            urllib.request.urlopen(req) as response,
            open(temp_archive_path, "wb") as out_file,
        ):
            shutil.copyfileobj(response, out_file)
        logging.info(f"Download complete for '{asset_name}'.")

        logging.info(f"Extracting '{asset_name}'...")
        if temp_archive_path.suffix == ".zip":
            with zipfile.ZipFile(temp_archive_path, "r") as zf:
                zf.extractall(path=destination_dir)
        elif temp_archive_path.suffix == ".gz":
            with tarfile.open(temp_archive_path, "r:gz") as tf:
                tf.extractall(path=destination_dir)
        logging.info("Extraction complete.")

        if post_extract_callback:
            if not post_extract_callback(destination_dir):
                return False
        return True
    except Exception as e:
        logging.error(
            f"Failed to download or extract '{asset_name}': {e}", exc_info=True
        )
        return False
    finally:
        if temp_archive_path.exists():
            os.remove(temp_archive_path)


def ensure_uv_available():
    if UV_PATH.exists():
        return
    logging.info("'uv' installer not found. Attempting to download it...")
    asset_name, executable_name = get_uv_asset_info()
    if not asset_name:
        logging.error(
            f"Your OS/architecture ({platform.system()}/{platform.machine()}) is not automatically supported."
        )
        sys.exit(1)

    download_url = (
        f"https://github.com/astral-sh/uv/releases/latest/download/{asset_name}"
    )

    def post_extract_uv(extract_dir: Path) -> bool:
        extracted_executable = extract_dir / executable_name
        if not extracted_executable.exists():
            found = list(extract_dir.glob(f"*/{executable_name}"))
            if not found:
                logging.error(
                    f"Could not find '{executable_name}' in the extracted archive."
                )
                return False
            extracted_executable = found[0]

        shutil.move(str(extracted_executable), str(UV_PATH))
        if not IS_WINDOWS:
            UV_PATH.chmod(0o755)

        for item in extract_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file() and item.name != UV_PATH.name:
                os.remove(item)

        logging.info("'uv' installed successfully.")
        return True

    if not download_and_extract_asset(
        download_url, asset_name, UV_DIR, post_extract_uv
    ):
        sys.exit(1)


def run_uv_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(UV_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def manage_requirements(args: argparse.Namespace, console, Panel) -> bool:
    if args.skip_deps:
        logging.warning("--skip-deps flag detected. Skipping dependency management.")
        return True

    console.print(
        Panel(
            "Managing Dependencies",
            title="[bold cyan]Step 1[/bold cyan]",
            border_style="cyan",
        )
    )
    try:
        logging.info(f"Fetching latest requirements from {REQUIREMENTS_URL}")
        with urllib.request.urlopen(REQUIREMENTS_URL, timeout=5) as response:
            content = response.read()
        LOCAL_REQUIREMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_REQUIREMENTS_PATH, "wb") as f:
            f.write(content)
        logging.info("Successfully downloaded requirements.txt.")
        console.print(
            "[green]✓[/green] Successfully downloaded [bold]requirements.txt[/bold]."
        )
    except Exception as e:
        logging.warning(f"Could not fetch latest requirements.txt: {e}")
        if not LOCAL_REQUIREMENTS_PATH.exists():
            logging.error("No local copy of requirements.txt found. Cannot proceed.")
            console.print(
                "[red]✗ ERROR: No local copy of requirements.txt found. Cannot proceed.[/red]"
            )
            return False
        logging.info("Using previously downloaded local copy of requirements.txt.")
        console.print(
            "ℹ️  Using previously downloaded local copy of [bold]requirements.txt[/bold]."
        )

    command = ["pip", "install", "-r", str(LOCAL_REQUIREMENTS_PATH)]
    if args.force_update:
        logging.info("--force-update flag detected. Re-installing all packages.")
        console.print(
            "[yellow]ℹ️  --force-update flag detected. Re-installing all packages.[/yellow]"
        )
        command.append("--reinstall")

    result = run_uv_command(command)

    if result.stdout:
        logging.debug(f"uv stdout:\n{result.stdout}")
    if result.stderr:
        logging.warning(f"uv stderr:\n{result.stderr}")

    if result.returncode != 0:
        logging.error("Failed to install dependencies.")
        console.print(
            "[red]✗ Failed to install dependencies. See launcher.log for details.[/red]"
        )
        return False

    logging.info("Dependencies are up to date.")
    console.print("[green]✓[/green] Dependencies are up to date.")
    return True


def handle_clean_argument(console, Text, Panel, Confirm):
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


def install_core(console, Panel, Confirm) -> bool:
    console.print(
        Panel(
            "📦 Installing Omni Trans Core",
            title="[bold cyan]Step 2[/bold cyan]",
            border_style="cyan",
        )
    )
    temp_extract_dir = ROOT_DIR / "temp_extract_core"
    try:
        logging.info(f"Fetching latest release info from {CORE_API_URL}")
        req = urllib.request.Request(
            CORE_API_URL, headers={"User-Agent": "Omni-Trans-Launcher"}
        )
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                logging.error(f"Failed to fetch release info (HTTP {response.status}).")
                console.print(
                    f"[red]✗ Failed to fetch release info (HTTP {response.status}).[/red]"
                )
                return False
            release_data = json.loads(response.read().decode())

        if not release_data:
            logging.error(
                "No releases (including pre-releases) found in the repository."
            )
            console.print(
                "[red]✗ No releases (including pre-releases) found in the repository.[/red]"
            )
            return False

        latest_release = release_data[0]

        is_prerelease = latest_release.get("prerelease", False)
        if is_prerelease:
            release_tag = latest_release.get("tag_name", "latest pre-release")
            console.print(
                Panel(
                    f"🟡 [bold]Pre-release Version Detected: {release_tag}[/bold]\n\n"
                    "This is a development version and may contain bugs or unfinished features. "
                    "It is recommended for testing or advanced users.",
                    title="[yellow]Heads Up![/yellow]",
                    border_style="yellow",
                )
            )
            if not Confirm.ask(
                "\nDo you want to proceed with installing this pre-release version?",
                default=False,
            ):
                logging.warning(
                    "Installation of pre-release version cancelled by user."
                )
                console.print(
                    "[yellow]Installation of pre-release version cancelled by user.[/yellow]"
                )
                return False

        asset_url = next(
            (
                asset.get("browser_download_url")
                for asset in latest_release.get("assets", [])
                if asset.get("name") == CORE_ASSET_NAME
            ),
            None,
        )

        if not asset_url:
            logging.error(
                f"Could not find asset '{CORE_ASSET_NAME}' in the latest release."
            )
            console.print(
                f"[red]✗ Could not find asset '{CORE_ASSET_NAME}' in the latest release.[/red]"
            )
            return False

        def post_extract_core(extract_dir: Path) -> bool:
            core_source_path = next(
                (
                    Path(root) / "omni_trans_core"
                    for root, dirs, _ in os.walk(extract_dir)
                    if "omni_trans_core" in dirs
                ),
                None,
            )

            if not core_source_path or not core_source_path.exists():
                logging.error(
                    "'omni_trans_core' folder not found in the downloaded archive."
                )
                console.print(
                    "[red]✗ 'omni_trans_core' folder not found in the downloaded archive.[/red]"
                )
                return False

            shutil.move(str(core_source_path), str(CORE_INSTALL_PATH))
            logging.info("Omni Trans Core installed successfully!")
            console.print("[green]✓ Omni Trans Core installed successfully![/green]")
            shutil.rmtree(extract_dir)
            return True

        if not download_and_extract_asset(
            asset_url, CORE_ASSET_NAME, temp_extract_dir, post_extract_core
        ):
            return False

        return True

    except Exception as e:
        logging.error(
            f"An unexpected error occurred during core installation: {e}", exc_info=True
        )
        console.print(
            f"[red]✗ An unexpected error occurred during core installation: {e}[/red]"
        )
        return False
    finally:
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)


def check_git_installed() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def find_launchable_app(console, Panel) -> Optional[Path]:
    console.print(
        Panel(
            "🔍 Searching for a local application...",
            title="[bold cyan]Step 3[/bold cyan]",
            border_style="cyan",
        )
    )
    logging.info("Scanning for local application...")
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
                logging.info(f"Found launchable app by scanning at: {item}")
                console.print(f"[green]✓ Found launchable app at: {item}[/green]")
                return runner_path
    logging.info("No local application found.")
    return None


def fetch_app_catalog(console) -> Optional[List[Dict[str, str]]]:
    try:
        logging.info(f"Fetching app catalog from {APP_CATALOG_URL}")
        req = urllib.request.Request(
            APP_CATALOG_URL, headers={"User-Agent": "Omni-Trans-Launcher"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")

        apps = []
        for line in content.splitlines():
            if line.strip().upper().startswith("APP_"):
                try:
                    _, value = line.split("=", 1)
                    parts = [p.strip() for p in value.strip().split(";")]
                    if len(parts) == 3:
                        apps.append(
                            {"name": parts[0], "folder": parts[1], "repo_url": parts[2]}
                        )
                except ValueError:
                    logging.warning(f"Could not parse app line in manifest: {line}")

        if apps:
            logging.info(f"Found {len(apps)} app(s) in catalog.")
            return apps
        else:
            logging.warning("No applications found in the catalog.")
            return None
    except Exception as e:
        logging.warning(f"Could not fetch app catalog: {e}")
        console.print(f"[yellow]⚠ Could not fetch app catalog: {e}[/yellow]")
        return None


def install_application(console, Panel, Confirm, app_info: Dict[str, str]) -> bool:
    display_name = app_info["name"]
    repo_url = app_info["repo_url"]

    console.print(
        Panel(
            f"📦 Installing {display_name}",
            title="[bold cyan]Application Installation[/bold cyan]",
            border_style="cyan",
        )
    )

    try:
        parsed_url = urllib.parse.urlparse(repo_url)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) < 2:
            console.print(f"[red]✗ Invalid GitHub repository URL: {repo_url}[/red]")
            return False

        owner, repo = path_parts[0], path_parts[1]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        asset_name = f"{repo}.zip"

        logging.info(f"Fetching release info for {display_name} from {api_url}")
        req = urllib.request.Request(
            api_url, headers={"User-Agent": "Omni-Trans-Launcher"}
        )
        with urllib.request.urlopen(req) as response:
            release_data = json.loads(response.read().decode())

        if not release_data:
            console.print(f"[red]✗ No releases found for {display_name}.[/red]")
            return False

        latest_release = release_data[0]
        if latest_release.get("prerelease", False):
            if not Confirm.ask(
                f"\n[yellow]The latest version of {display_name} is a pre-release. Install anyway?[/yellow]",
                default=False,
            ):
                console.print("[yellow]Installation cancelled.[/yellow]")
                return False

        asset = next(
            (
                asset
                for asset in latest_release.get("assets", [])
                if asset.get("name") == asset_name
            ),
            None,
        )
        if not asset or not asset.get("browser_download_url"):
            console.print(
                f"[red]✗ Could not find download asset '{asset_name}' in the latest release of {display_name}.[/red]"
            )
            return False

        download_url = asset["browser_download_url"]

        def post_extract_app(extract_dir: Path) -> bool:
            console.print(f"[green]✓ {display_name} installed successfully![/green]")
            return True

        return download_and_extract_asset(
            download_url, asset_name, ROOT_DIR, post_extract_app
        )

    except Exception as e:
        logging.error(
            f"Failed to install application {display_name}: {e}", exc_info=True
        )
        console.print(f"[red]✗ Failed to install {display_name}: {e}[/red]")
        return False


def prompt_and_install_app(console, Panel, Table, Confirm, Prompt) -> bool:
    console.print(
        Panel(
            "No local application found. Searching for installable apps...",
            title="[yellow]Setup Required[/yellow]",
            border_style="yellow",
        )
    )

    apps = fetch_app_catalog(console)
    if not apps:
        console.print(
            "[red]✗ Could not find any applications to install. Please check your connection or the manifest file.[/red]"
        )
        return False

    table = Table(
        title="[bold magenta]Available Applications for Installation[/bold magenta]"
    )
    table.add_column("Num", style="cyan")
    table.add_column("Application Name", style="green")

    for i, app in enumerate(apps):
        table.add_row(str(i + 1), app["name"])

    console.print(table)

    choice = Prompt.ask(
        "\nEnter the number of the application to install (or 'q' to quit)", default="q"
    )

    if choice.lower() == "q":
        return False

    try:
        choice_index = int(choice) - 1
        if 0 <= choice_index < len(apps):
            selected_app = apps[choice_index]
            return install_application(console, Panel, Confirm, selected_app)
        else:
            console.print("[red]Invalid selection.[/red]")
            return False
    except ValueError:
        console.print("[red]Invalid input. Please enter a number.[/red]")
        return False


if __name__ == "__main__":
    logging.info("Launcher started.")
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
        logging.info("Ensuring 'rich' is installed...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        if result.returncode != 0:
            logging.warning(
                f"Could not install rich automatically. Stderr: {result.stderr}"
            )

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Confirm, Prompt
        from rich.table import Table
        from rich.text import Text

        console = Console()
    except ImportError:
        logging.warning("Could not import 'rich'. Using fallback console.")

        class FallbackConsole:
            def print(self, msg):
                clean_msg = re.sub(r"\[.*?\]", "", str(msg))
                print(clean_msg)
                logging.info(f"[FallbackConsole]: {clean_msg}")

        console = FallbackConsole()

    try:
        if args.clean:
            handle_clean_argument(console, Text, Panel, Confirm)

        console.print(
            Panel.fit(
                "[bold green]Omni Trans Launcher[/bold green]",
                subtitle="[cyan]v1.0[/cyan]",
                border_style="green",
            )
        )
        ensure_uv_available()

        if not check_git_installed():
            logging.error("Git is not installed or not in PATH.")
            console.print(
                Panel(
                    "[red]Git is not installed or not in PATH.[/red]\n[yellow]Please install Git and ensure it is available in your system's PATH to proceed.[/yellow]",
                    title="[bold red]✗ Requirement Missing[/bold red]",
                )
            )
            sys.exit(1)

        if not manage_requirements(args, console, Panel):
            sys.exit(1)

        if not check_core_installed():
            logging.warning("Omni Trans Core not found.")
            console.print(
                Panel(
                    "[yellow]⚠ Omni Trans Core not found.[/yellow]",
                    title="Core Missing",
                )
            )
            if Confirm.ask(
                "\nDo you want to install Omni Trans Core now?", default=True
            ):
                if not install_core(console, Panel, Confirm):
                    logging.error("Core installation failed. Exiting.")
                    console.print("[red]✗ Core installation failed. Exiting.[/red]")
                    sys.exit(1)
            else:
                logging.warning("User declined core installation. Exiting.")
                console.print("[red]✗ Cannot proceed without the core. Exiting.[/red]")
                sys.exit(1)
        else:
            logging.info("Omni Trans Core is already installed.")
            console.print("[green]✓ Omni Trans Core is already installed.[/green]")

        runner_path = find_launchable_app(console, Panel)

        if not runner_path:
            was_installed = prompt_and_install_app(
                console, Panel, Table, Confirm, Prompt
            )
            if was_installed:
                runner_path = find_launchable_app(console, Panel)
            else:
                logging.info("No application selected or installation failed. Exiting.")
                console.print("No application selected. Exiting.")
                time.sleep(3)
                sys.exit(0)

        if not runner_path:
            logging.critical(
                "Could not find a runner.py even after installation attempt."
            )
            console.print(
                Panel(
                    "[red]Fatal: Application could not be found after installation. The downloaded archive might be structured incorrectly.[/red]",
                    title="[bold red]✗ Launch Error[/bold red]",
                )
            )
            sys.exit(1)

        logging.info(f"Launching application: {runner_path}")
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
            logging.warning(
                f"Application exited with a non-zero code: {result.returncode}"
            )
            console.print(
                f"[yellow]⚠ Application exited with a non-zero code: {result.returncode}[/yellow]"
            )
        else:
            logging.info("Application finished successfully.")
            console.print("[green]✓ Application finished successfully.[/green]")

        sys.exit(result.returncode)

    except KeyboardInterrupt:
        logging.warning("Application interrupted by user. Exiting.")
        console.print("\n[yellow]👋 Application interrupted by user. Exiting.[/yellow]")
        sys.exit(130)
    except Exception as e:
        logging.critical(
            f"An unexpected error occurred in launcher: {e}", exc_info=True
        )
        console.print(f"[red]✗ An unexpected error occurred: {e}[/red]")
        console.print(f"[bold red]See {LOG_FILE_PATH} for details.[/bold red]")
        sys.exit(1)
