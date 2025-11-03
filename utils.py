import logging
import os
import importlib
from pathlib import Path
from typing import Any, Callable, Protocol, cast
from . import settings
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QObject
from functools import wraps
from .localization_manager import translate

logger = logging.getLogger(f"{settings.LOG_PREFIX}_CORE.utils")

DEV_TOOLS_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "developer_tools.py"
)
IS_DEV_MODE: bool = os.path.exists(path=DEV_TOOLS_PATH)


def wip_notification(
    message_key: str, mode: str = "info", settings_key: str | None = None
):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if settings_key is not None and settings.current_settings.get(
                settings_key, False
            ):
                return func(*args, **kwargs)
            title = translate("dialog.wip.title")
            message = translate(message_key)
            if mode == "info":
                QtWidgets.QMessageBox.information(None, title, message)
                return func(*args, **kwargs)
            elif mode == "confirm":
                msg_box = QtWidgets.QMessageBox()
                msg_box.setWindowTitle(title)
                msg_box.setText(message)
                msg_box.setStandardButtons(
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.Cancel
                )
                msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
                msg_box.button(QtWidgets.QMessageBox.StandardButton.Yes).setText(
                    "Continue"
                )
                dont_show_again_checkbox = None
                if settings_key:
                    dont_show_again_checkbox = QtWidgets.QCheckBox(
                        translate("dialog.wip.checkbox_dont_show_again")
                    )
                    msg_box.setCheckBox(dont_show_again_checkbox)
                reply = msg_box.exec()
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    if (
                        dont_show_again_checkbox
                        and dont_show_again_checkbox.isChecked()
                        and settings_key is not None
                    ):
                        settings.current_settings[settings_key] = True
                        settings.save_settings()
                    return func(*args, **kwargs)
                else:
                    return None
            return func(*args, **kwargs)

        return wrapper

    return decorator


def mask_api_key(api_key_string: str) -> str:
    if not api_key_string:
        return "N/A_KEY"
    if len(api_key_string) > 7:
        return f"{api_key_string[:3]}...{api_key_string[-4:]}"
    elif len(api_key_string) > 0:
        return "****"
    return "EMPTY_KEY"


class UILoadingManager:
    _instance: "UILoadingManager | None" = None
    core_files: list[str] = []
    app_files: list[str] = []
    mode: str = "Developer" if IS_DEV_MODE else "Release"

    def __new__(cls) -> "UILoadingManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_load(self, scope: str, filename: str) -> None:
        if scope == "core" and filename not in self.core_files:
            self.core_files.append(filename)
        elif scope == "app" and filename not in self.app_files:
            self.app_files.append(filename)

    def log_summary(self) -> None:
        core_summary: str = (
            f"Core: {len(self.core_files)} | {', '.join(sorted(self.core_files))}"
            if self.core_files
            else "Core: 0"
        )
        app_summary: str = (
            f"App: {len(self.app_files)} | {', '.join(sorted(self.app_files))}"
            if self.app_files
            else "App: 0"
        )
        logger.debug(f"UI Loading ({self.mode}) - {core_summary}. {app_summary}.")


ui_loader_manager = UILoadingManager()


class UiFormProtocol(Protocol):
    def setupUi(self, target: QObject) -> None: ...


def load_ui(ui_file_name: str, instance: QObject, caller_path: str):
    caller_dir = Path(caller_path).parent
    if IS_DEV_MODE:
        try:
            from .developer_tools import load_ui_for_dev  # type: ignore

            ui_file_path = caller_dir / "forms" / ui_file_name
            load_ui_for_dev(str(ui_file_path), instance)
            ui_loader_manager.register_load("core", ui_file_name)
        except ImportError:
            logger.critical(
                "DEV MODE: Could not import 'load_ui_for_dev' from developer_tools.py."
            )
            raise
    else:
        base_name = os.path.splitext(ui_file_name)[0]
        compiled_module_name = f"{base_name}_ui"
        class_name = f"Ui_{instance.__class__.__name__}"
        module_path_parts = list(caller_dir.parts)
        try:
            core_index = module_path_parts.index("omni_trans_core")
            base_module_path = ".".join(module_path_parts[core_index:])
            module_path_prefix = f"{base_module_path}.forms_py"
        except ValueError:
            logger.critical(
                f"Could not determine module path from caller: {caller_path}"
            )
            raise ImportError(f"Could not construct UI module path for {ui_file_name}")

        full_module_path = f"{module_path_prefix}.{compiled_module_name}"
        try:
            UiModule = importlib.import_module(name=full_module_path)
            UiClass = cast(type[UiFormProtocol], getattr(UiModule, class_name))
            ui_instance = UiClass()
            ui_instance.setupUi(instance)
            for widget in instance.findChildren(QObject):
                widget_name = widget.objectName()
                if widget_name:
                    setattr(instance, widget_name, widget)
            ui_loader_manager.register_load(
                scope="core", filename=f"{compiled_module_name}.py"
            )
        except (ImportError, AttributeError) as e:
            logger.critical(
                f"RELEASE MODE: Failed to load compiled UI module '{full_module_path}' or class '{class_name}': {e}"
            )
            raise


class DebounceTimer(QtCore.QObject):
    _slot: Callable[[], None]
    _timer: QtCore.QTimer

    def __init__(
        self, slot: Callable[[], None], interval_ms: int, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._slot = slot
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        _ = self._timer.timeout.connect(self._slot)

    def trigger(self) -> None:
        self._timer.start()

    def force_run(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._slot()

    def cancel(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
