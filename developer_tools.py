import re
import os
import logging
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from .ui.animations import UIAnimator
from .utils import DebounceTimer
from . import settings
from .localization_manager import LocalizationManager

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE.dev_tools')

class LocalizationToolbar(QtWidgets.QWidget):
    display_mode_changed = QtCore.Signal(str)
    language_selected = QtCore.Signal(str)
    check_code_keys_clicked = QtCore.Signal()
    check_target_keys_clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            QtCore.Qt.Window
            | QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint,
        )
        self.setWindowOpacity(0.9)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        frame = QtWidgets.QFrame(self)
        frame.setStyleSheet("""
            QFrame {
                background-color: rgba(45, 45, 45, 230);
                border: 1px solid #555;
                border-radius: 8px;}""")
        frame_layout = QtWidgets.QHBoxLayout(frame)
        frame_layout.setContentsMargins(8, 5, 8, 5)
        frame_layout.setSpacing(10)
        self.drag_handle = QtWidgets.QLabel(":::")
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        self.drag_handle.setStyleSheet("font-weight: bold; color: #888;")
        frame_layout.addWidget(self.drag_handle)
        self.lang_combo = QtWidgets.QComboBox()
        frame_layout.addWidget(self.lang_combo)
        self.check_code_keys_button = QtWidgets.QPushButton("🐍❓")
        self.check_code_keys_button.setCursor(Qt.PointingHandCursor)
        self.check_target_keys_button = QtWidgets.QPushButton("📖❓")
        self.check_target_keys_button.setCursor(Qt.PointingHandCursor)
        frame_layout.addWidget(self.check_code_keys_button)
        frame_layout.addWidget(self.check_target_keys_button)
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.VLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        frame_layout.addWidget(separator)
        self.original_button = QtWidgets.QPushButton("Original")
        self.key_button = QtWidgets.QPushButton("Key")
        self.translated_button = QtWidgets.QPushButton("Translated")
        self.original_button.setCheckable(True)
        self.key_button.setCheckable(True)
        self.translated_button.setCheckable(True)
        self.translated_button.setChecked(True)
        self.button_group = QtWidgets.QButtonGroup(self)
        self.button_group.addButton(self.original_button, 0)
        self.button_group.addButton(self.key_button, 1)
        self.button_group.addButton(self.translated_button, 2)
        self.button_group.setExclusive(True)
        frame_layout.addWidget(self.original_button)
        frame_layout.addWidget(self.key_button)
        frame_layout.addWidget(self.translated_button)
        layout.addWidget(frame)
        self.button_group.idClicked.connect(self._on_mode_button_clicked)
        self.lang_combo.activated.connect(self._on_language_selected_by_index)
        self.check_code_keys_button.clicked.connect(self.check_code_keys_clicked.emit)
        self.check_target_keys_button.clicked.connect(
            self.check_target_keys_clicked.emit
        )
        self._drag_position = None

    def set_available_languages(self, languages: list[dict]):
        self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        for lang_info in languages:
            self.lang_combo.addItem(lang_info["name"], lang_info["code"])
        self.lang_combo.blockSignals(False)

    def set_target_check_enabled(self, enabled: bool):
        self.check_target_keys_button.setEnabled(enabled)

    def set_current_language(self, lang_code: str):
        self.lang_combo.blockSignals(True)
        index = self.lang_combo.findData(lang_code)
        if index != -1:
            self.lang_combo.setCurrentIndex(index)
        self.lang_combo.blockSignals(False)

    def _on_mode_button_clicked(self, button_id):
        if button_id == 0:
            self.display_mode_changed.emit("original")
        elif button_id == 1:
            self.display_mode_changed.emit("key")
        else:
            self.display_mode_changed.emit("translated")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton and self._drag_position:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def _on_language_selected_by_index(self, index: int):
        lang_code = self.lang_combo.itemData(index)
        if lang_code:
            self.language_selected.emit(lang_code)

class DeveloperToolsManager(QtCore.QObject):
    def __init__(
        self,
        main_window: QtWidgets.QMainWindow,
        localization_manager: LocalizationManager,
    ):
        super().__init__(main_window)
        self.main_window = main_window
        self.loc_man = localization_manager
        self.toolbar = None
        self.event_filter = None
        self.key_pattern_1 = re.compile(r"translate\(['\"]([^'\"]+)['\"]")
        self.key_pattern_2 = re.compile(
            r"loc_man\.register\([^,]+, *['\"][^'\"]+['\"], *['\"]([^'\"]+)['\"]"
        )
        self.file_watcher = QtCore.QFileSystemWatcher(self)
        self.reload_timer = DebounceTimer(self._perform_hot_reload, 250, self)
        logger.debug("DeveloperToolsManager initialized.")

    def _handle_app_state_change(self, state):
        if not self.toolbar:
            return
        if state == Qt.ApplicationActive:
            self.toolbar.show()
        elif state == Qt.ApplicationInactive:
            self.toolbar.hide()

    def activate(self):
        logger.debug("Activating developer tools...")
        if self.toolbar:
            logger.debug("Developer tools already active.")
            return
        app_instance = QtCore.QCoreApplication.instance()
        if not app_instance:
            logger.error(
                "Could not find a QCoreApplication instance to install event filter."
            )
            return
        self.event_filter = LocalizationEventFilter(self.loc_man)
        app_instance.installEventFilter(self.event_filter)
        logger.debug("LocalizationEventFilter installed.")
        self.toolbar = LocalizationToolbar(None)
        self.toolbar.display_mode_changed.connect(self.loc_man.set_display_mode)
        self.toolbar.language_selected.connect(self._on_toolbar_language_change)
        self.toolbar.check_code_keys_clicked.connect(self._check_code_vs_source)
        self.toolbar.check_target_keys_clicked.connect(self._check_source_vs_target)
        app_instance.applicationStateChanged.connect(self._handle_app_state_change)
        self.file_watcher.fileChanged.connect(self._on_watched_file_changed)
        self.loc_man.language_changed.connect(self._update_watched_files)
        self._update_watched_files()
        available_langs = self.loc_man.get_available_languages()
        self.toolbar.set_available_languages(available_langs)
        self.handle_language_change()
        main_window_geo = self.main_window.geometry()
        toolbar_size = self.toolbar.sizeHint()
        self.toolbar.move(
            main_window_geo.right() - toolbar_size.width() - 20,
            main_window_geo.top() + 50,
        )
        self.toolbar.show()

    def deactivate(self):
        if not self.toolbar:
            return
        logger.debug("Deactivating developer tools...")
        self.toolbar.close()
        self.toolbar = None
        app_instance = QtCore.QCoreApplication.instance()
        if not app_instance:
            logger.error(
                "Could not find a QCoreApplication instance to perform full deactivation."
            )
            return
        if self.event_filter:
            try:
                app_instance.applicationStateChanged.disconnect(
                    self._handle_app_state_change
                )
            except (RuntimeError, TypeError):
                logger.debug(
                    "Could not disconnect applicationStateChanged, maybe already disconnected."
                )
            app_instance.removeEventFilter(self.event_filter)
            logger.debug("LocalizationEventFilter removed.")
            self.event_filter = None
        current_paths = self.file_watcher.files()
        if current_paths:
            self.file_watcher.removePaths(current_paths)
        try:
            self.file_watcher.fileChanged.disconnect(self._on_watched_file_changed)
            self.reload_timer.cancel()
            self.loc_man.language_changed.disconnect(self._update_watched_files)
        except (RuntimeError, TypeError):
            logger.debug(
                "Could not disconnect file watcher signals, maybe already disconnected."
            )

    @QtCore.Slot()
    def handle_language_change(self):
        if self.toolbar:
            current_lang = settings.current_settings.get("user_language", "en")
            self.toolbar.set_current_language(current_lang)
            is_source = (
                self.loc_man._current_language == self.loc_man.SOURCE_CODE_LANGUAGE
            )
            self.toolbar.set_target_check_enabled(not is_source)

    @QtCore.Slot(str)
    def _on_toolbar_language_change(self, lang_code: str):
        settings.current_settings["user_language"] = lang_code
        self.loc_man.set_language(lang_code)

    def _show_results_dialog(
        self, title: str, header: str, missing_key_data: dict[str, list[str]]
    ):
        dialog = QtWidgets.QDialog(self.main_window)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(600, 400)
        layout = QtWidgets.QVBoxLayout(dialog)
        header_label = QtWidgets.QLabel(header)
        layout.addWidget(header_label)
        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        if missing_key_data:
            display_lines = []
            for key, locations in sorted(missing_key_data.items()):
                display_lines.append(key)
                for loc in sorted(locations):
                    display_lines.append(f"  - {loc}")
                display_lines.append("")
            text_edit.setPlainText("\n".join(display_lines))
        else:
            text_edit.setText("No issues found. Everything is in sync.")
        layout.addWidget(text_edit)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        dialog.exec()

    def _check_code_vs_source(self):
        scan_dir = os.path.dirname(settings.APP_DIR)
        code_key_locations = {}
        for root, _, files in os.walk(scan_dir):
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, scan_dir).replace("\\", "/")
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line_num, line_content in enumerate(f, 1):
                            found1 = self.key_pattern_1.findall(line_content)
                            found2 = self.key_pattern_2.findall(line_content)
                            for key in found1 + found2:
                                location_str = f"{relative_path}:{line_num}"
                                if key not in code_key_locations:
                                    code_key_locations[key] = []
                                code_key_locations[key].append(location_str)
                except Exception as e:
                    logger.error(f"Could not read or process {file_path}: {e}")
        source_keys = set(self.loc_man._source_data.keys())
        code_keys = set(code_key_locations.keys())
        missing_from_source_file = code_keys - source_keys
        missing_keys_with_locations = {
            key: code_key_locations[key] for key in missing_from_source_file
        }
        source_lang_code = self.loc_man.SOURCE_CODE_LANGUAGE
        header = f"Found {len(missing_keys_with_locations)} key(s) in code that are missing from the source '{source_lang_code}.json' file:"
        self._show_results_dialog(
            "Code vs. Source File Check", header, missing_keys_with_locations
        )

    def _check_source_vs_target(self):
        source_keys = set(self.loc_man._source_data.keys())
        target_keys = set(self.loc_man._target_data.keys())
        missing_from_target_file = source_keys - target_keys
        target_lang_code = self.loc_man._current_language
        source_lang_code = self.loc_man.SOURCE_CODE_LANGUAGE
        header = f"Found {len(missing_from_target_file)} key(s) from '{source_lang_code}.json' that are missing from the target '{target_lang_code}.json' file:"
        missing_keys_for_dialog = {key: [] for key in missing_from_target_file}
        self._show_results_dialog(
            "Source vs. Target File Check", header, missing_keys_for_dialog
        )

    @QtCore.Slot()
    def _update_watched_files(self):
        current_paths = self.file_watcher.files()
        if current_paths:
            self.file_watcher.removePaths(current_paths)
        new_paths_to_watch = self.loc_man.get_current_file_paths()
        if new_paths_to_watch:
            self.file_watcher.addPaths(list(new_paths_to_watch.values()))
            logger.debug(
                f"Hot Reload: Now watching files: {list(new_paths_to_watch.values())}"
            )

    @QtCore.Slot(str)
    def _on_watched_file_changed(self, path: str):
        logger.debug(f"File changed: {path}. Starting debounce timer.")
        self.reload_timer.trigger()

    @QtCore.Slot()
    def _perform_hot_reload(self):
        logger.info("Hot Reload: Performing reload...")
        self.loc_man.set_language(self.loc_man._current_language)

class LocalizationEventFilter(QtCore.QObject):
    def __init__(self, localization_manager):
        super().__init__()
        self.loc_man = localization_manager

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if not (
            event.type() == QtCore.QEvent.Type.MouseButtonPress
            and QtWidgets.QApplication.keyboardModifiers()
            & QtCore.Qt.KeyboardModifier.ControlModifier
            and settings.current_settings.get("translation_mode_enabled", False)
        ):
            return super().eventFilter(watched, event)
        if isinstance(watched, QtWidgets.QTabBar):
            tab_index = watched.tabAt(event.position().toPoint())
            if tab_index != -1:
                tab_widget = watched.parentWidget()
                if isinstance(tab_widget, QtWidgets.QTabWidget):
                    key_data = self.loc_man._registered_widgets.get(tab_widget)
                    if key_data:
                        internal_prop_name = f"tabText_{tab_index}"
                        if internal_prop_name in key_data:
                            key_to_copy = key_data[internal_prop_name][0]
                            clipboard = QtWidgets.QApplication.clipboard()
                            clipboard.setText(key_to_copy)
                            logger.info(
                                f"Copied localization key '{key_to_copy}' for tab index {tab_index}"
                            )
                            UIAnimator.shake_widget(tab_widget)
                            return True
        target_widget = None
        if isinstance(watched, QtWidgets.QWidget):
            target_widget = watched.childAt(event.position().toPoint()) or watched
        key_data = None
        widget_with_key = None
        current_widget = target_widget
        while current_widget:
            if current_widget in self.loc_man._registered_widgets:
                key_data = self.loc_man._registered_widgets[current_widget]
                widget_with_key = current_widget
                break
            current_widget = current_widget.parentWidget()
        if key_data and widget_with_key:
            key_to_copy = None
            prop_priority = [
                "text",
                "title",
                "windowTitle",
                "placeholderText",
                "toolTip",
                "helpText",
            ]
            for prop in prop_priority:
                if prop in key_data:
                    key_to_copy = key_data[prop][0]
                    break
            if not key_to_copy:
                key_to_copy = list(key_data.values())[0][0]
            if key_to_copy:
                clipboard = QtWidgets.QApplication.clipboard()
                clipboard.setText(key_to_copy)
                logger.info(f"Copied localization key to clipboard: '{key_to_copy}'")
                UIAnimator.shake_widget(widget_with_key)
                return True
        return super().eventFilter(watched, event)

def load_ui_for_dev(ui_file_path: str, instance: QtCore.QObject):
    if not os.path.exists(ui_file_path):
        logger.error(f"[DEV_TOOLS] UI file not found at provided path: {ui_file_path}")
        raise FileNotFoundError(f"UI file not found: {ui_file_path}")
    loader = QUiLoader()
    file = QFile(ui_file_path)
    file.open(QFile.ReadOnly)
    loaded_widget = loader.load(file)
    file.close()
    instance.setLayout(loaded_widget.layout())
    for widget in instance.findChildren(QtCore.QObject):
        widget_name = widget.objectName()
        if widget_name:
            setattr(instance, widget_name, widget)