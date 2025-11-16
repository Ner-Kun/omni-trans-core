import os
import sys
import subprocess
import platform
import urllib.request
import urllib.parse
from packaging.version import parse as parse_version
import zipfile
import tarfile
import shutil
import time
import argparse
import logging
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any

ROOT_DIR = Path(__file__).parent.parent.resolve()
LAUNCHER_DIR = ROOT_DIR / "launcher"
TOOL_DIR = LAUNCHER_DIR / "tool"
IS_WINDOWS = platform.system() == "Windows"


class Config:
    ROOT_DIR = ROOT_DIR
    LOG_FILE_PATH = ROOT_DIR / "launcher.log"

    VENV_DIR = ROOT_DIR / ".venv"
    LAUNCHER_DIR = LAUNCHER_DIR
    LAUNCHER_VERSION = "1.0.0-alpha"
    TOOL_DIR = TOOL_DIR

    IS_WINDOWS = IS_WINDOWS
    VENV_PYTHON = (
        VENV_DIR / "Scripts" / "python.exe"
        if IS_WINDOWS
        else VENV_DIR / "bin" / "python"
    )

    class UV:
        DIR = TOOL_DIR / "uv"
        CACHE_DIR = TOOL_DIR / ".uv_cache"
        PATH = DIR / "uv.exe" if IS_WINDOWS else DIR / "uv"

    class Core:
        API_URL = "https://api.github.com/repos/Ner-Kun/omni-trans-core/releases"
        ASSET_NAME = "omni-trans-core.zip"
        INSTALL_PATH = ROOT_DIR / "omni_trans_core"

    class App:
        CATALOG_URL = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/launcher-manifest.txt"
        LAUNCHER_URL = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/launcher/start.py"

    class Requirements:
        URL = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/main/requirements.txt"
        LOCAL_PATH = TOOL_DIR / "requirements.txt"


class ConsoleManager:
    def __init__(self):
        self.rich_available = False
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.prompt import Confirm, Prompt
            from rich.table import Table
            from rich.text import Text

            self.Console = Console
            self.Panel = Panel
            self.Confirm = Confirm
            self.Prompt = Prompt
            self.Table = Table
            self.Text = Text

            self.console = self.Console()
            self.rich_available = True
        except ImportError:
            logging.warning("Could not import 'rich'. Using fallback console.")

    def print(self, message: Any):
        if self.rich_available:
            self.console.print(message)
        else:
            clean_msg = re.sub(r"\[.*?\]", "", str(message))
            print(clean_msg)
            logging.info(f"[FallbackConsole]: {clean_msg}")

    def ask_confirm(self, prompt: str, default: bool = False) -> bool:
        if self.rich_available:
            return self.Confirm.ask(prompt, default=default)
        response = input(f"{prompt} [y/N]: ").lower().strip()
        return response == "y"

    def ask_prompt(self, prompt: str, default: str = "") -> str:
        if self.rich_available:
            return self.Prompt.ask(prompt, default=default)
        response = input(f"{prompt} [{default}]: ")
        return response.strip() or default

    def panel(self, *args, **kwargs):
        if self.rich_available:
            return self.Panel(*args, **kwargs)
        return " ".join(map(str, args))

    def panel_fit(self, *args, **kwargs):
        if self.rich_available:
            return self.Panel.fit(*args, **kwargs)
        return " ".join(map(str, args))

    def table(self, **kwargs):
        if self.rich_available:
            return self.Table(**kwargs)
        return None

    def text(self, *args, **kwargs):
        if self.rich_available:
            return self.Text(*args, **kwargs)
        return " ".join(args)


class AssetManager:
    def __init__(self, console_manager: ConsoleManager):
        self.console = console_manager

    def _get_json_from_url(self, url: str) -> Optional[List[Dict[str, Any]]]:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Omni-Trans-Launcher"}
            )
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    return json.loads(response.read().decode())
        except Exception as e:
            logging.error(f"Failed to fetch or parse JSON from {url}: {e}")
        return None

    def _download_and_extract(
        self,
        download_url: str,
        asset_name: str,
        destination_dir: Path,
        post_extract_callback: Optional[Callable[[Path], bool]] = None,
    ) -> bool:
        destination_dir.mkdir(parents=True, exist_ok=True)
        temp_archive_path = destination_dir / asset_name

        try:
            self.console.print(f"Downloading [cyan]'{asset_name}'[/cyan]...")
            logging.info(
                f"Downloading '{asset_name}' from {download_url}"
            )

            req = urllib.request.Request(
                download_url, headers={"User-Agent": "Omni-Trans-Launcher"}
            )
            with (
                urllib.request.urlopen(req) as response,
                open(temp_archive_path, "wb") as out_file,
            ):
                shutil.copyfileobj(response, out_file)

            self.console.print(
                f"[green]✓[/green] Download complete for [cyan]'{asset_name}'[/cyan]."
            )
            logging.info(f"Download complete for '{asset_name}'.")

            self.console.print(f"Extracting [cyan]'{asset_name}'[/cyan]...")
            logging.info(f"Extracting '{asset_name}'...")

            if temp_archive_path.suffix == ".zip":
                with zipfile.ZipFile(temp_archive_path, "r") as zf:
                    zf.extractall(path=destination_dir)
            elif temp_archive_path.suffix == ".gz":
                with tarfile.open(temp_archive_path, "r:gz") as tf:
                    tf.extractall(path=destination_dir)

            self.console.print("[green]✓[/green] Extraction complete.")
            logging.info("Extraction complete.")

            if post_extract_callback:
                return post_extract_callback(destination_dir)
            return True
        except Exception as e:
            logging.error(
                f"Failed to download or extract '{asset_name}': {e}", exc_info=True
            )
            self.console.print(
                f"[red]✗ Error during download/extraction of '{asset_name}'. See log for details.[/red]"
            )
            return False
        finally:
            if temp_archive_path.exists():
                os.remove(temp_archive_path)

    def ensure_uv_available(self) -> bool:
        if Config.UV.PATH.exists():
            return True
        
        self.console.print("🔧 'uv' installer not found. Attempting to download it...")
        logging.info("'uv' installer not found. Attempting to download it...")
        
        system, machine = platform.system(), platform.machine()
        
        asset_map = {
            ("Windows", "AMD64"): ("uv-x86_64-pc-windows-msvc.zip", "uv.exe"),
            ("Windows", "x86_64"): ("uv-x86_64-pc-windows-msvc.zip", "uv.exe"),
            ("Linux", "x86_64"): ("uv-x86_64-unknown-linux-gnu.tar.gz", "uv"),
            ("Linux", "aarch64"): ("uv-aarch64-unknown-linux-gnu.tar.gz", "uv"),
            ("Darwin", "x86_64"): ("uv-x86_64-apple-darwin.tar.gz", "uv"),
            ("Darwin", "arm64"): ("uv-aarch64-apple-darwin.tar.gz", "uv"),
        }
        
        asset_info = asset_map.get((system, machine))
        if not asset_info:
            logging.error(f"Your OS/architecture ({system}/{machine}) is not automatically supported.")
            self.console.print(f"[red]✗ Your OS/architecture ({system}/{machine}) is not supported for automatic 'uv' installation.[/red]")
            return False
            
        asset_name, executable_name = asset_info
        download_url = f"https://github.com/astral-sh/uv/releases/latest/download/{asset_name}"

        def post_extract_uv(extract_dir: Path) -> bool:
            extracted_executable = extract_dir / executable_name
            if not extracted_executable.exists():
                found = list(extract_dir.glob(f"*/{executable_name}"))
                if not found: 
                    return False
                extracted_executable = found[0]

            shutil.move(str(extracted_executable), str(Config.UV.PATH))
            if not Config.IS_WINDOWS:
                Config.UV.PATH.chmod(0o755)

            for item in extract_dir.iterdir():
                if item.is_dir(): 
                    shutil.rmtree(item)
                elif item.is_file() and item.name != Config.UV.PATH.name: 
                    os.remove(item)
            
            self.console.print("[green]✓[/green] 'uv' installed successfully.")
            logging.info("'uv' installed successfully.")
            return True

        return self._download_and_extract(download_url, asset_name, Config.UV.DIR, post_extract_uv)

    def install_core(self) -> bool:
        release_data = self._get_json_from_url(Config.Core.API_URL)
        if not release_data:
            self.console.print("[red]✗ Could not fetch core release info.[/red]")
            return False

        latest_release = release_data[0]
        if latest_release.get("prerelease", False):
            release_tag = latest_release.get("tag_name", "latest pre-release")
            self.console.print(
                self.console.panel(
                    f"🟡 [bold]Pre-release Version Detected: {release_tag}[/bold]\n\nThis is a development version and may contain bugs.",
                    title="[yellow]Heads Up![/yellow]",
                    border_style="yellow",
                )
            )
            if not self.console.ask_confirm(
                "\nProceed with pre-release installation?", default=False
            ):
                return False

        asset_url = next(
            (
                a.get("browser_download_url")
                for a in latest_release.get("assets", [])
                if a.get("name") == Config.Core.ASSET_NAME
            ),
            None,
        )
        if not asset_url:
            self.console.print(
                f"[red]✗ Could not find asset '{Config.Core.ASSET_NAME}' in release.[/red]"
            )
            return False

        temp_extract_dir = Config.ROOT_DIR / "temp_extract_core"

        def post_extract_core(extract_dir: Path) -> bool:
            core_source = next(
                (p for p in extract_dir.rglob("omni_trans_core") if p.is_dir()), None
            )
            if not core_source or not core_source.exists():
                self.console.print(
                    "[red]✗ 'omni_trans_core' folder not found in the archive.[/red]"
                )
                return False
            shutil.move(str(core_source), str(Config.Core.INSTALL_PATH))
            shutil.rmtree(extract_dir)
            return True

        success = self._download_and_extract(
            asset_url, Config.Core.ASSET_NAME, temp_extract_dir, post_extract_core
        )
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
        return success

    def install_app(self, app_info: Dict[str, str]) -> bool:
        display_name, repo_url = app_info["name"], app_info["repo_url"]

        repo_path_match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
        if not repo_path_match:
            self.console.print(
                f"[red]✗ Invalid GitHub repository URL format: {repo_url}[/red]"
            )
            return False

        owner, repo = repo_path_match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        asset_name = f"{repo}.zip"

        release_data = self._get_json_from_url(api_url)
        if not release_data:
            self.console.print(f"[red]✗ No releases found for {display_name}.[/red]")
            return False

        latest_release = release_data[0]
        asset = next(
            (
                a
                for a in latest_release.get("assets", [])
                if a.get("name") == asset_name
            ),
            None,
        )

        if not asset or not asset.get("browser_download_url"):
            self.console.print(
                f"[red]✗ Could not find asset '{asset_name}' in the latest release of {display_name}.[/red]"
            )
            return False

        return self._download_and_extract(
            asset["browser_download_url"], asset_name, Config.ROOT_DIR
        )


class Launcher:
    def __init__(self):
        self._setup_logging()
        self.args = self._parse_args()
        self.console = ConsoleManager()
        self.asset_manager = AssetManager(self.console)

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename=Config.LOG_FILE_PATH,
            filemode="w",
            encoding="utf-8",
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(
            logging.DEBUG
        )
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(console_handler)
        sys.excepthook = self._handle_exception



    def _handle_exception(self, exc_type, exc_value, exc_traceback):
        logging.error(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
        )
        self.console.print(
            "\n\n[bold red]FATAL ERROR: The application crashed. See launcher.log for details.[/bold red]"
        )
        time.sleep(15)

    def _parse_args(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Launcher for Omni Trans based applications."
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Remove generated files for a clean reinstall.",
        )
        parser.add_argument(
            "--force-update",
            action="store_true",
            help="Force re-installation of dependencies.",
        )
        parser.add_argument(
            "--skip-deps", action="store_true", help="Skip dependency installation."
        )
        parser.add_argument(
            "--rich-bootstrapped", action="store_true", help=argparse.SUPPRESS
        )
        return parser.parse_args()

    def _check_for_self_update(self):
        self.console.print("🔍 Checking for launcher updates...")
        try:
            with urllib.request.urlopen(Config.App.CATALOG_URL, timeout=5) as response:
                content = response.read().decode("utf-8")

            remote_version_str = None
            for line in content.splitlines():
                if line.strip().upper().startswith("LAUNCHER_VERSION"):
                    remote_version_str = line.split("=", 1)[1].strip()
                    break

            if not remote_version_str:
                self.console.print(
                    "[yellow]Could not find launcher version in manifest. Skipping update.[/yellow]"
                )
                return

            if parse_version(remote_version_str) > parse_version(
                Config.LAUNCHER_VERSION
            ):
                self.console.print(
                    f"✨ New launcher version available: [bold green]{remote_version_str}[/bold green]. Updating..."
                )

                new_launcher_path = Config.LAUNCHER_DIR / "start.py.new"
                updater_script_path = Config.LAUNCHER_DIR / "_updater.py"

                with urllib.request.urlopen(
                    Config.App.LAUNCHER_URL, timeout=15
                ) as response:
                    with open(new_launcher_path, "wb") as f:
                        f.write(response.read())

                _updater_script_content = f"""
import sys
import os
import time
import subprocess

old_path = {repr(str(Config.LAUNCHER_DIR / "start.py"))}
new_path = {repr(str(new_launcher_path))}
original_args = {sys.argv[1:]}

time.sleep(1)

try:
    if os.path.exists(old_path):
        os.remove(old_path)
    os.rename(new_path, old_path)
    
    subprocess.Popen([sys.executable, old_path] + original_args)
    
finally:
    if os.path.exists(__file__):
        try:
            os.remove(__file__)
        except OSError:
            pass
"""
                with open(updater_script_path, "w", encoding="utf-8") as f:
                    f.write(_updater_script_content)

                subprocess.Popen(
                    [sys.executable, str(updater_script_path)],
                    creationflags=subprocess.DETACHED_PROCESS,
                    close_fds=True,
                )
                sys.exit(0)
            else:
                self.console.print("[green]✓[/green] Launcher is up to date.")

        except Exception as e:
            logging.error(f"Launcher update check failed: {e}")
            self.console.print(
                "[yellow]⚠ Could not check for launcher updates. Continuing with current version.[/yellow]"
            )

    def _is_running_in_venv(self) -> bool:
        return sys.prefix == str(Config.VENV_DIR)

    def _ensure_not_in_venv_and_relaunch(self):
        if self._is_running_in_venv():
            return

        if not Config.VENV_DIR.exists():
            self.console.print(
                f"Creating virtual environment at '{Config.VENV_DIR}'..."
            )
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", str(Config.VENV_DIR)],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to create virtual environment: {e.stderr}")
                sys.exit(1)

        self.console.print("Relaunching script in the virtual environment...")
        try:
            launcher_script_path = Config.LAUNCHER_DIR / "start.py"
            result = subprocess.run(
                [str(Config.VENV_PYTHON), str(launcher_script_path), *sys.argv[1:]]
            )
            sys.exit(result.returncode)
        except FileNotFoundError:
            logging.error(f"Python interpreter not found at '{Config.VENV_PYTHON}'.")
            sys.exit(1)

    def _handle_clean_argument(self):
        if not self.args.clean:
            return

        self.console.print(
            self.console.panel(
                "[bold yellow]--clean operation[/bold yellow]", title="✨ Clean Install"
            )
        )
        targets = [Config.VENV_DIR, Config.TOOL_DIR, Config.Core.INSTALL_PATH]

        text = self.console.text("This will remove:\n")
        for target in targets:
            text.append("\n • ", style="yellow")
            text.append(str(target), style="cyan")

        self.console.print(self.console.panel(text, border_style="yellow"))

        if self.console.ask_confirm(
            "\nAre you sure you want to proceed?", default=False
        ):
            for target in targets:
                if target.exists():
                    self.console.print(f"Removing {target}...")
                    shutil.rmtree(target, ignore_errors=True)
            self.console.print(
                "\n[bold green]Clean operation complete. Please run the launcher again.[/bold green]"
            )
        else:
            self.console.print("[yellow]Clean operation cancelled.[/yellow]")
        sys.exit(0)

    def _manage_dependencies(self) -> bool:
        if self.args.skip_deps:
            self.console.print(
                "[yellow]ℹ️  --skip-deps flag detected. Skipping dependency management.[/yellow]"
            )
            return True

        self.console.print(
            self.console.panel_fit(
                "Managing Dependencies",
                title="[bold cyan]Step 1[/bold cyan]",
                border_style="cyan",
            )
        )

        try:
            with urllib.request.urlopen(Config.Requirements.URL, timeout=5) as response:
                Config.Requirements.LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(Config.Requirements.LOCAL_PATH, "wb") as f:
                    f.write(response.read())
            self.console.print(
                "[green]✓[/green] Successfully downloaded [bold]requirements.txt[/bold]."
            )
        except Exception as e:
            logging.warning(f"Could not fetch latest requirements.txt: {e}")
            if not Config.Requirements.LOCAL_PATH.exists():
                self.console.print(
                    "[red]✗ ERROR: No local copy of requirements.txt found. Cannot proceed.[/red]"
                )
                return False
            self.console.print(
                "ℹ️  Using previously downloaded local copy of [bold]requirements.txt[/bold]."
            )

        command = ["pip", "install", "-r", str(Config.Requirements.LOCAL_PATH)]
        if self.args.force_update:
            command.append("--reinstall")

        result = subprocess.run([str(Config.UV.PATH), *command], check=False)

        if result.returncode != 0:
            logging.error("uv failed to install dependencies.")
            self.console.print(
                "[red]✗ Failed to install dependencies. See launcher.log for details.[/red]"
            )
            return False

        self.console.print("[green]✓[/green] Dependencies are up to date.")
        return True

    def _manage_core(self) -> bool:
        self.console.print(
            self.console.panel_fit(
                "Checking Omni Trans Core",
                title="[bold cyan]Step 2[/bold cyan]",
                border_style="cyan",
            )
        )

        if (
            Config.Core.INSTALL_PATH.exists()
            and (Config.Core.INSTALL_PATH / "__init__.py").exists()
        ):
            self.console.print("[green]✓ Omni Trans Core is already installed.[/green]")
            return True

        self.console.print(
            "📦 [yellow]Omni Trans Core not found. Attempting to install...[/yellow]"
        )
        if self.asset_manager.install_core():
            self.console.print(
                "[green]✓ Omni Trans Core installed successfully![/green]"
            )
            return True
        else:
            self.console.print("[red]✗ Core installation failed.[/red]")
            return False

    def _find_local_app(self) -> Optional[Path]:
        excluded = {
            ".git",
            ".venv",
            "launcher",
            "omni_trans_core",
            "tool",
            "__pycache__",
        }
        for item in Config.ROOT_DIR.iterdir():
            if item.is_dir() and item.name not in excluded:
                runner = item / "runner.py"
                if runner.exists():
                    return runner
        return None

    def _prompt_for_app_installation(self) -> bool:
        self.console.print(
            self.console.panel(
                "No local application found. Searching for installable apps...",
                title="[yellow]Setup Required[/yellow]",
                border_style="yellow",
            )
        )

        try:
            with urllib.request.urlopen(Config.App.CATALOG_URL, timeout=10) as response:
                content = response.read().decode("utf-8")
        except Exception as e:
            self.console.print(f"[yellow]⚠ Could not fetch app catalog: {e}[/yellow]")
            return False

        apps = []
        for line in content.splitlines():
            if line.strip().upper().startswith("APP_"):
                try:
                    _, value = line.split("=", 1)
                    name, folder, repo = [p.strip() for p in value.split(";")]
                    apps.append({"name": name, "folder": folder, "repo_url": repo})
                except ValueError:
                    continue

        if not apps:
            self.console.print(
                "[red]✗ Could not find any applications to install.[/red]"
            )
            return False

        table = self.console.table(
            title="[bold magenta]Available Applications[/bold magenta]"
        )
        if table is not None:
            table.add_column("Num", style="cyan")
            table.add_column("Application Name", style="green")
            for i, app in enumerate(apps):
                table.add_row(str(i + 1), app["name"])
            self.console.print(table)

        choice = self.console.ask_prompt(
            "\nEnter the number of the app to install (or 'q' to quit)", default="q"
        )
        if choice.lower() == "q":
            return False

        try:
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(apps):
                return self.asset_manager.install_app(apps[choice_index])
        except ValueError:
            pass

        self.console.print("[red]Invalid selection.[/red]")
        return False

    def _launch_application(self) -> None:
        self.console.print(
            self.console.panel_fit(
                "Searching for application...",
                title="[bold cyan]Step 3[/bold cyan]",
                border_style="cyan",
            )
        )

        runner_path = self._find_local_app()
        if not runner_path:
            was_installed = self._prompt_for_app_installation()
            if was_installed:
                runner_path = self._find_local_app()
            else:
                self.console.print(
                    "No application selected or installation failed. Exiting."
                )
                time.sleep(3)
                sys.exit(0)

        if not runner_path:
            self.console.print(
                self.console.panel(
                    "[red]Fatal: Application could not be found after installation attempt.[/red]",
                    title="[bold red]✗ Launch Error[/bold red]",
                )
            )
            sys.exit(1)

        self.console.print(
            self.console.panel_fit(
                f"🚀 Launching [bold green]{runner_path.parent.name}[/bold green]...",
                title="[bold blue]Starting Application[/bold blue]",
            )
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(Config.ROOT_DIR)

        result = subprocess.run(
            [sys.executable, str(runner_path)], check=False, env=env
        )

        if result.returncode != 0:
            self.console.print(
                f"[yellow]⚠ Application exited with code: {result.returncode}[/yellow]"
            )
        else:
            self.console.print("[green]✓ Application finished successfully.[/green]")
        sys.exit(result.returncode)

    def run(self):
        try:
            self._handle_clean_argument()
            self._ensure_not_in_venv_and_relaunch()

            os.environ["UV_CACHE_DIR"] = str(Config.UV.CACHE_DIR)

            if not self.asset_manager.ensure_uv_available():
                self.console.print("[red]✗ Failed to setup 'uv'. Cannot proceed.[/red]")
                sys.exit(1)

            import importlib.util

            if not self.args.rich_bootstrapped and not importlib.util.find_spec("rich"):
                self.console.print("Bootstrapping rich...")
                result = subprocess.run(
                    [str(Config.UV.PATH), "pip", "install", "rich"], check=False
                )

                if result.returncode != 0:
                    self.console.print(
                        "[yellow]Warning: Failed to install 'rich'. Continuing with basic.[/yellow]"
                    )
                else:
                    self.console.print("Restarting launcher to activate rich...")
                    os.execv(
                        sys.executable,
                        [sys.executable] + sys.argv + ["--rich-bootstrapped"],
                    )
            self.console.print(
                self.console.panel_fit(
                    "[bold green]Omni Trans Launcher[/bold green]",
                    subtitle=f"[cyan]v{Config.LAUNCHER_VERSION}[/cyan]",
                    border_style="green",
                )
            )
            
            self._check_for_self_update()

            if not self._manage_dependencies():
                sys.exit(1)

            if not self._manage_core():
                self.console.print(
                    self.console.panel(
                        "[bold red]Omni Trans Core is a required component, but it has not been installed. Exit.[/bold red]",
                        title="[bold red]Installation canceled[/bold red]",
                    )
                )
                time.sleep(5)
                sys.exit(1)


            self._launch_application()

        except KeyboardInterrupt:
            if self.console:
                self.console.print(
                    "\n[yellow]👋 Application interrupted by user. Exiting.[/yellow]"
                )
            else:
                print("\nApplication interrupted by user. Exiting.")
            sys.exit(130)

if __name__ == "__main__":
    launcher = Launcher()
    launcher.run()
