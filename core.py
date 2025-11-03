import os
import logging
import webbrowser
import random
from PySide6 import QtWidgets, QtCore, QtGui
from . import settings, updater
from .interfaces import AbstractDataHandler, AbstractTab, AbstractPromptFormatter, AbstractResponseParser
from .localization_manager import LocalizationManager, loc_man, translate
from .cache_manager import CacheManager
from .ui.animations import LoadingOverlay
from .ui.widgets import NotificationBanner
from .ui.dialogs import SettingsDialog, AboutDialog, ModelInspectorDialog, ProgressDialog, DonationDialog
from .utils import DebounceTimer
from .response_parser import DefaultResponseParser
from .logger import LoggerManager
from typing import override


try:
    from .translation_manager import TranslationManager
except ImportError: 
    pass

try:
    from .developer_tools import DeveloperToolsManager
    dev_tools_available = True
except ImportError:
    dev_tools_available = False
    class _DeveloperToolsManagerStub(QtCore.QObject):
        def __init__(self, main_window: QtWidgets.QMainWindow, localization_manager: LocalizationManager):
            super().__init__(main_window)
            logger.debug("DeveloperToolsManager not found. Dev tools will be disabled.")
        def activate(self) -> None: pass
        def deactivate(self) -> None: pass
        def handle_language_change(self) -> None: pass

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE')

DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 850
DEFAULT_AUTOSAVE_INTERVAL_MS = 5000
DEFAULT_DEBOUNCE_INTERVAL_MS = 1000
STATUS_BAR_SHORT_TIMEOUT_MS = 3000
STATUS_BAR_MEDIUM_TIMEOUT_MS = 5000
STATUS_BAR_LONG_TIMEOUT_MS = 7000

class CoreApp(QtWidgets.QMainWindow):
    logger_manager: LoggerManager
    app_name: str
    app_version: str
    data_handler: AbstractDataHandler
    prompt_formatter: AbstractPromptFormatter
    response_parser: AbstractResponseParser
    user_tabs: list[AbstractTab]
    loaded_tabs: dict[str, AbstractTab]
    thread_pool: QtCore.QThreadPool
    cache_manager: CacheManager
    translation_manager: "TranslationManager"
    recent_files: list[str]
    recent_menu: QtWidgets.QMenu | None
    progress_dialog: ProgressDialog | None
    model_inspector_window: ModelInspectorDialog | None
    auto_save_timer: DebounceTimer
    dev_tools_manager: "DeveloperToolsManager | _DeveloperToolsManagerStub"
    status_bar: QtWidgets.QStatusBar
    tab_widget: QtWidgets.QTabWidget
    notification_banner: NotificationBanner
    loading_overlay: LoadingOverlay
    new_action: QtGui.QAction
    open_action: QtGui.QAction
    save_action: QtGui.QAction
    exit_action: QtGui.QAction
    settings_action: QtGui.QAction
    toggleModelInspectorAction: QtGui.QAction
    about_action: QtGui.QAction
    clear_recent_action: QtGui.QAction
    file_menu: QtWidgets.QMenu
    view_menu: QtWidgets.QMenu
    help_menu: QtWidgets.QMenu

    def __init__(
        self,
        data_handler: AbstractDataHandler,
        tabs: list[AbstractTab],
        prompt_formatter: AbstractPromptFormatter,
        app_name: str,
        app_version: str,
        response_parser: AbstractResponseParser | None = None,
        app_version_url: str | None = None,
    ):
        super().__init__()
        self.logger_manager = LoggerManager(settings.current_settings)
        self.logger_manager.configure_logging()
        if app_version_url:
            updater.check_for_updates(
                app_name=app_name,
                app_version=app_version,
                app_version_url=app_version_url,
            )
        self.app_name = app_name
        self.app_version = app_version
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.data_handler = data_handler
        self.prompt_formatter = prompt_formatter
        self.response_parser = response_parser or DefaultResponseParser()
        self.user_tabs = tabs
        self.loaded_tabs = {}
        self.thread_pool = QtCore.QThreadPool()
        logger.debug(f"QThreadPool maxThreadCount: {self.thread_pool.maxThreadCount()}")
        self.cache_manager = CacheManager(self.data_handler)
        from .translation_manager import TranslationManager

        self.translation_manager = TranslationManager(
            self, self.prompt_formatter, self.response_parser
        )
        self.recent_files = settings.current_settings.get("recent_files", [])
        self.recent_menu = None
        self.progress_dialog = None
        self.model_inspector_window = None
        self.auto_save_timer = DebounceTimer(
            self.save_all_changes,
            int(
                settings.current_settings.get(
                    "auto_save_interval_ms", DEFAULT_AUTOSAVE_INTERVAL_MS
                )
            ),
            parent=self,
        )
        self.create_actions()
        self.create_menus()
        self.init_ui()
        if dev_tools_available:
            self.dev_tools_manager = DeveloperToolsManager(self, loc_man)
        else:
            self.dev_tools_manager = _DeveloperToolsManagerStub(self, loc_man)
        self._connect_signals()
        loc_man.language_changed.connect(self.retranslate_ui)
        loc_man.language_changed.connect(self.dev_tools_manager.handle_language_change)
        if settings.current_settings.get("translation_mode_enabled", False):
            self.dev_tools_manager.activate()
        self.set_active_connection_name(self.get_active_connection_name())
        self.translation_manager.apply_rpm_settings_effects()

    def log_initialization_complete(self) -> None:
        logger.info("Omnis Trans Core Initialized.")

    def init_ui(self) -> None:
        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        self.tab_widget = QtWidgets.QTabWidget()
        self.notification_banner = NotificationBanner(self)
        main_layout.addWidget(self.notification_banner)
        main_layout.addWidget(self.tab_widget)
        self.loading_overlay = LoadingOverlay(self.centralWidget())
        self.retranslate_ui()

    def get_available_connection_names(self) -> list[str]:
        connections = ["Google Gemini"]
        custom_connections = settings.current_settings.get("custom_connections", [])
        if custom_connections:
            custom_names = [
                conn.get("name")
                for conn in sorted(
                    custom_connections, key=lambda x: x.get("name", "").lower()
                )
            ]
            connections.extend(custom_names)
        return connections

    def get_active_connection_name(self) -> str:
        return settings.current_settings.get("active_connection_name", "Google Gemini")

    def get_current_gemini_model(self) -> str:
        return settings.current_settings.get("gemini_model", "")

    def get_active_model_full_id(self) -> str | None:
        conn_name = self.get_active_connection_name()
        active_model_id = settings.current_settings.get(
            "active_model_for_connection", {}
        ).get(conn_name)
        if not active_model_id:
            return None
        if conn_name == "Google Gemini":
            return f"gemini/{active_model_id}"
        conn_profile = next(
            (
                c
                for c in settings.current_settings.get("custom_connections", [])
                if c.get("name") == conn_name
            ),
            None,
        )
        if not conn_profile:
            return None
        provider = conn_profile.get("provider")
        provider_for_litellm = "openai" if provider == "openai_compatible" else provider
        return f"{provider_for_litellm}/{active_model_id}"

    def are_dev_tools_available(self) -> bool:
        return dev_tools_available

    def set_active_connection_name(self, name: str):
        settings.current_settings["active_connection_name"] = name
        self.translation_manager.set_active_connection(name)

    def browse_and_load_file(self):
        if self.translation_manager.active_translation_jobs > 0:
            QtWidgets.QMessageBox.warning(
                self,
                translate("app.warning.operation_in_progress.title"),
                translate("app.warning.operation_in_progress.text"),
            )
            return
        if self.data_handler.is_dirty():
            if not self._confirm_discard_changes():
                logger.debug("User cancelled file loading due to unsaved changes.")
                return
        file_filter = self.data_handler.get_file_filter()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            translate("app.dialog.open_file.title"),
            os.path.expanduser("~"),
            file_filter,
        )
        if path:
            logger.info(f"User selected file to open: {path}")
            self.load_file(path)

    def load_file(self, path: str):
        logger.info(f"Starting to load file: {path}")
        self.translation_manager.reset_state()
        for tab_instance in self.loaded_tabs.values():
            tab_instance.clear_view()
        self.loading_overlay.start_animation(
            translate("app.status.loading_file", filename=os.path.basename(path))
        )
        QtWidgets.QApplication.processEvents()
        self.data_handler.load(path)

    def save_all_changes(self):
        self.auto_save_timer.cancel()
        is_data_dirty = self.data_handler.is_dirty()
        is_cache_dirty = self.cache_manager.is_dirty()
        if not is_data_dirty and not is_cache_dirty:
            self.status_bar.showMessage(
                translate("app.status.no_changes_to_save"), STATUS_BAR_SHORT_TIMEOUT_MS
            )
            logger.debug(
                "save_all_changes called, but no components are dirty. No action taken."
            )
            return
        logger.debug("Calling on_before_save() for all loaded tabs.")
        for tab_name, tab_instance in self.loaded_tabs.items():
            try:
                tab_instance.on_before_save()
            except Exception as e:
                logger.error(
                    f"Error in on_before_save for tab '{tab_name}': {e}", exc_info=True
                )
        self.loading_overlay.start_animation(translate("app.status.saving_changes"))
        QtWidgets.QApplication.processEvents()
        try:
            if is_cache_dirty:
                self.cache_manager.save_cache()
            if is_data_dirty:
                self.data_handler.save()
            if is_cache_dirty:
                self.cache_manager.set_dirty_flag(False)
            self.status_bar.showMessage(
                translate("app.status.all_changes_saved"), STATUS_BAR_SHORT_TIMEOUT_MS
            )
            logger.info("Data and/or cache saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save changes via data_handler: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self,
                translate("app.dialog.save_error.title"),
                translate("app.dialog.save_error.text", error=e),
            )
            self.status_bar.showMessage(
                translate("app.status.save_failed"), STATUS_BAR_MEDIUM_TIMEOUT_MS
            )
        finally:
            self.loading_overlay.stop_animation()

    def _confirm_discard_changes(self) -> bool:
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(translate("app.dialog.unsaved_changes.title"))
        msg_box.setText(translate("app.dialog.unsaved_changes.text"))
        msg_box.setInformativeText(
            translate("app.dialog.unsaved_changes.informative_text")
        )
        msg_box.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Save)
        reply = msg_box.exec()
        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            logger.debug("User chose to cancel the operation with unsaved changes.")
            return False
        elif reply == QtWidgets.QMessageBox.StandardButton.Save:
            logger.debug("User chose to save unsaved changes.")
            self.save_all_changes()
        else:
            logger.debug("User chose to discard unsaved changes.")
        return True

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        logger.info("Close event received.")
        if self.translation_manager.active_translation_jobs > 0:
            reply = QtWidgets.QMessageBox.question(
                self,
                translate("app.dialog.confirm_exit.title"),
                translate(
                    "app.dialog.confirm_exit.text",
                    job_count=self.translation_manager.active_translation_jobs,
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                logger.info("Exit cancelled by user due to active jobs.")
                event.ignore()
                return
        if self.data_handler.is_dirty():
            if not self._confirm_discard_changes():
                event.ignore()
                return
        self.translation_manager.cancel_batch_translation(silent=True)
        models_dev_cache_path = settings.MODELS_DEV_CACHE_FILE
        if os.path.exists(models_dev_cache_path):
            try:
                os.remove(models_dev_cache_path)
                logger.debug(
                    f"Removed temporary models.dev cache: {models_dev_cache_path}"
                )
            except OSError as e:
                logger.error(f"Failed to remove temporary models.dev cache: {e}")
        settings.save_settings()
        self.logger_manager.save_log_to_file(settings.LOG_FILE)
        logger.info("Settings and cache saved. Application closing.")
        if self.model_inspector_window:
            self.model_inspector_window.close()
        self.dev_tools_manager.deactivate()
        event.accept()

    def _trigger_ui_update(self):
        QtCore.QCoreApplication.postEvent(self, QtCore.QEvent(QtCore.QEvent.LanguageChange))

    @override
    def changeEvent(self, event: QtCore.QEvent):
        if event.type() == QtCore.QEvent.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def load_user_tabs(self):
        if not self.user_tabs:
            logger.warning("No tabs provided to CoreApp.")
            return
        for tab_instance in self.user_tabs:
            tab_name = getattr(tab_instance, "TAB_NAME", "Unnamed Tab")
            self.tab_widget.addTab(tab_instance, tab_name)
            self.loaded_tabs[tab_name] = tab_instance
            logger.info(f"Tab loaded: '{tab_name}'.")
            if hasattr(tab_instance, "translation_requested"):
                tab_instance.translation_requested.connect(
                    self._on_translation_requested
                )
            if hasattr(tab_instance, "generation_params_updated"):
                tab_instance.generation_params_updated.connect(
                    self._on_generation_params_updated
                )

    @QtCore.Slot(str, dict)
    def _on_generation_params_updated(self, conn_name: str, params: dict):
        if not conn_name:
            return
        if conn_name == "Google Gemini":
            settings.current_settings["gemini_generation_params"].update(params)
            logger.debug("Updated generation params for Google Gemini.")
        else:
            custom_connections = settings.current_settings.get("custom_connections", [])
            for conn in custom_connections:
                if conn.get("name") == conn_name:
                    if "generation_params" not in conn:
                        conn["generation_params"] = (
                            settings.get_default_generation_params()
                        )
                    conn["generation_params"].update(params)
                    logger.debug(
                        f"Updated generation params for connection: {conn_name}"
                    )
                    break
        settings.save_settings()

    def retranslate_ui(self):
        loc_man.register(
            self,
            "windowTitle",
            "app.title",
            app_name=self.app_name,
            app_version=self.app_version,
        )
        self.status_bar.showMessage(translate("app.status.ready"))
        loc_man.register(self.file_menu, "title", "menu.file")
        loc_man.register(self.view_menu, "title", "menu.view")
        loc_man.register(self.help_menu, "title", "menu.help")
        loc_man.register(self.recent_menu, "title", "menu.open_recent")
        loc_man.register(self.new_action, "text", "action.new")
        loc_man.register(self.open_action, "text", "action.open")
        loc_man.register(self.save_action, "text", "action.save")
        loc_man.register(self.exit_action, "text", "action.exit")
        loc_man.register(self.settings_action, "text", "action.settings")
        loc_man.register(
            self.toggleModelInspectorAction, "text", "action.model_inspector"
        )
        loc_man.register(self.toggleModelInspectorAction, "statusTip", "action.model_inspector.tooltip",)
        loc_man.register(self.about_action, "text", "action.about")
        loc_man.register(self.clear_recent_action, "text", "action.clear_recent")
        for tab_name, tab_instance in self.loaded_tabs.items():
            if hasattr(tab_instance, "retranslate_ui") and callable(
                getattr(tab_instance, "retranslate_ui")
            ):
                try:
                    tab_instance.retranslate_ui()
                except Exception as e:
                    logger.error(
                        f"Error calling retranslate_ui for tab '{tab_name}': {e}"
                    )

    def create_actions(self):
        self.new_action = QtGui.QAction(self)
        self.new_action.setShortcut(QtGui.QKeySequence.New)
        self.open_action = QtGui.QAction(self)
        self.open_action.setShortcut(QtGui.QKeySequence.Open)
        self.open_action.triggered.connect(self.browse_and_load_file)
        self.save_action = QtGui.QAction(self)
        self.save_action.setShortcut(QtGui.QKeySequence.Save)
        self.save_action.triggered.connect(self.save_all_changes)
        self.save_action.setEnabled(False)
        self.exit_action = QtGui.QAction(self)
        self.exit_action.setShortcut(QtGui.QKeySequence.Quit)
        self.exit_action.triggered.connect(self.close)
        self.settings_action = QtGui.QAction(self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        self.toggleModelInspectorAction = QtGui.QAction(self, checkable=True)
        self.toggleModelInspectorAction.triggered.connect(self.toggle_model_inspector)
        self.about_action = QtGui.QAction(self)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.clear_recent_action = QtGui.QAction(self)
        self.clear_recent_action.triggered.connect(self._clear_recent_files)

    def create_menus(self):
        self.file_menu = self.menuBar().addMenu("")
        self.file_menu.addAction(self.new_action)
        self.file_menu.addAction(self.open_action)
        self.recent_menu = self.file_menu.addMenu("")
        self._update_recent_files_menu()
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.save_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.settings_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)
        self.view_menu = self.menuBar().addMenu("")
        self.view_menu.addAction(self.toggleModelInspectorAction)
        self.help_menu = self.menuBar().addMenu("")
        self.help_menu.addAction(self.about_action)

    def _update_recent_files(self, new_path: str):
        if not new_path:
            return
        if new_path in self.recent_files:
            self.recent_files.remove(new_path)
        self.recent_files.insert(0, new_path)
        self.recent_files = self.recent_files[: settings.MAX_RECENT_FILES]
        settings.current_settings["recent_files"] = self.recent_files
        settings.save_settings()
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
        if not self.recent_menu:
            return
        self.recent_menu.clear()
        self.recent_files = [
            p
            for p in settings.current_settings.get("recent_files", [])
            if p and os.path.exists(p)
        ]
        settings.current_settings["recent_files"] = self.recent_files
        if not self.recent_files:
            self.recent_menu.setEnabled(False)
            return
        self.recent_menu.setEnabled(True)
        for i, path in enumerate(self.recent_files):
            action = QtGui.QAction(f"&{i + 1}. {os.path.basename(path)}", self)
            action.setData(path)
            action.triggered.connect(self._load_from_recent)
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        self.recent_menu.addAction(self.clear_recent_action)

    @QtCore.Slot()
    def _load_from_recent(self):
        action = self.sender()
        if isinstance(action, QtGui.QAction):
            path = action.data()
            if path and os.path.exists(path):
                self.load_file(path)
            elif path:
                QtWidgets.QMessageBox.warning(
                    self,
                    translate("app.warning.file_not_found.title"),
                    translate("app.warning.file_not_found.text", path=path),
                )
                self._update_recent_files_menu()

    @QtCore.Slot(list, bool)
    def _on_translation_requested(self, items: list, force_regen: bool):
        target_lang = settings.current_settings.get("selected_target_language", "")
        op_name = (
            translate("app.op_name.regenerating")
            if force_regen
            else translate("app.op_name.translating")
        )
        self._start_translation_batch(items, op_name, target_lang, force_regen)

    @QtCore.Slot()
    def _clear_recent_files(self):
        self.recent_files.clear()
        settings.current_settings["recent_files"] = []
        settings.save_settings()
        self._update_recent_files_menu()

    @QtCore.Slot(dict)
    def _on_item_translated(self, update_data: dict):
        logger.debug(f"Received update_data: {update_data}")
        item_id = update_data.get("item_id")
        for tab_name, tab in self.loaded_tabs.items():
            logger.debug(f"Notifying tab: '{tab_name}'")
            if hasattr(tab, "update_item_display"):
                tab.update_item_display(update_data)
            if item_id and hasattr(tab, "flash_items"):
                tab.flash_items([item_id])

    def _connect_signals(self):
        self.data_handler.data_loaded.connect(self._on_data_loaded)
        self.data_handler.dirty_state_changed.connect(self._on_data_handler_dirty_state_changed)
        self.translation_manager.batch_progress_updated.connect(self._update_progress_dialog)
        self.translation_manager.batch_finished.connect(self._finalize_batch_translation)
        self.translation_manager.item_translated.connect(self._on_item_translated)
        self.translation_manager.model_capability_discovered.connect(self._on_model_capability_discovered)
        self.cache_manager.cache_dirty_state_changed.connect(self._on_cache_manager_dirty_state_changed)
        self.translation_manager.thinking_misconfigured.connect(self._show_thinking_misconfigured_banner)

    @QtCore.Slot(str, str)
    def _on_model_capability_discovered(self, model_id: str, capability: str):
        logger.debug(
            f"[_on_model_capability_discovered] Received for model '{model_id}': {capability}"
        )
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, "handle_model_capability_notice"):
            logger.debug("[_on_model_capability_discovered] Forwarding to current tab.")
            current_tab.handle_model_capability_notice(model_id, capability)

    def open_settings_dialog(self):
        dialog = SettingsDialog(
            settings.current_settings, self, dev_tools_available=dev_tools_available
        )
        dialog.clear_cache_requested.connect(self.cache_manager.clear_cache)
        available_langs = loc_man.get_available_languages()
        for lang_info in available_langs:
            dialog.language_combo.addItem(lang_info["name"], lang_info["code"])
        saved_lang_code = settings.current_settings.get("user_language", "en")
        index = dialog.language_combo.findData(saved_lang_code)
        if index != -1:
            dialog.language_combo.setCurrentIndex(index)
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.finished.connect(self._handle_settings_dialog_finished)
        dialog.open()

    def _handle_settings_dialog_finished(self, result: int):
        dialog = self.sender()
        if not isinstance(dialog, SettingsDialog):
            logger.warning("Sender for settings dialog is not of the expected type.")
            if dialog:
                dialog.deleteLater()
            return
        if result == QtWidgets.QDialog.Accepted:
            new_settings_data = dialog.get_settings()
            old_mode_enabled = settings.current_settings.get(
                "translation_mode_enabled", False
            )
            should_update_lang = new_settings_data.get(
                "user_language"
            ) != settings.current_settings.get("user_language")
            settings.current_settings.update(new_settings_data)
            settings.save_settings()
            logger.info("Settings updated and saved.")
            new_mode_enabled = settings.current_settings.get(
                "translation_mode_enabled", False
            )
            if new_mode_enabled != old_mode_enabled:
                if new_mode_enabled:
                    self.dev_tools_manager.activate()
                else:
                    self.dev_tools_manager.deactivate()
            if should_update_lang:
                loc_man.set_language(
                    settings.current_settings.get("user_language", "en")
                )
            if not new_mode_enabled:
                loc_man.set_display_mode("translated")
            self.logger_manager.configure_logging()
            self.translation_manager.apply_rpm_settings_effects()
            logger.debug("Notifying all loaded tabs about settings change...")
            for tab in self.loaded_tabs.values():
                if hasattr(tab, "on_settings_changed") and callable(
                    getattr(tab, "on_settings_changed")
                ):
                    try:
                        tab.on_settings_changed()
                    except Exception as e:
                        logger.error(
                            f"Error calling on_settings_changed for tab '{tab.TAB_NAME}': {e}"
                        )
        else:
            logger.info("Settings dialog cancelled, no changes applied.")
        dialog.deleteLater()

    def show_about_dialog(self):
        dialog = AboutDialog(
            app_name=self.app_name, app_version=self.app_version, parent=self
        )
        dialog.exec()

    def toggle_model_inspector(self):
        if not self.model_inspector_window:
            self.model_inspector_window = ModelInspectorDialog(self)
            self.translation_manager.inspector_update.connect(
                self.model_inspector_window.update_data
            )
        if self.model_inspector_window.isVisible():
            self.model_inspector_window.hide()
        else:
            self.model_inspector_window.show()

    @QtCore.Slot()
    def _on_data_loaded(self):
        self.loading_overlay.stop_animation()
        self.save_action.setEnabled(True)
        self.cache_manager.load_cache()
        for tab_name, tab_instance in self.loaded_tabs.items():
            if hasattr(tab_instance, "on_data_loaded"):
                try:
                    tab_instance.on_data_loaded()
                    logger.debug(f"Called on_data_loaded() for tab '{tab_name}'.")
                except Exception as e:
                    logger.error(
                        f"Error calling on_data_loaded() for tab '{tab_name}': {e}"
                    )
        project_name = self.data_handler.get_project_name()
        self._update_recent_files(self.data_handler.get_project_path())
        self.setWindowTitle(f"{self.app_name} v{self.app_version} - {project_name}")
        self.status_bar.showMessage(
            translate("app.status.loaded_project", project_name=project_name)
        )
        self.data_handler.set_dirty_flag(False)

    @QtCore.Slot(bool)
    def _on_data_handler_dirty_state_changed(self):
        self._update_dirty_state()

    @QtCore.Slot(bool)
    def _on_cache_manager_dirty_state_changed(self):
        self._update_dirty_state()

    def _update_dirty_state(self):
        is_app_dirty = self.data_handler.is_dirty() or self.cache_manager.is_dirty()
        self.save_action.setEnabled(is_app_dirty)
        title = self.windowTitle()
        if is_app_dirty:
            if not title.endswith("*"):
                self.setWindowTitle(f"{title}*")
            self.auto_save_timer.trigger()
        else:
            if title.endswith("*"):
                self.setWindowTitle(title[:-1])
            self.auto_save_timer.cancel()

    def _start_translation_batch(
        self, jobs_to_queue, op_name="Translating", target_lang="", force_regen=False
    ):
        queued_job_count = self.translation_manager.start_translation_batch(
            jobs_to_queue, op_name, target_lang, force_regen
        )
        if queued_job_count > 0:
            if self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog.deleteLater()
            label_text = translate(
                "app.progress_dialog.label",
                op_name=op_name,
                job_count=queued_job_count,
                target_lang=target_lang,
            )
            title_text = translate("app.progress_dialog.title", op_name=op_name)
            self.progress_dialog = ProgressDialog(
                title=title_text, label_text=label_text, parent=self
            )
            self.progress_dialog.set_maximum(queued_job_count)
            self.progress_dialog.set_button_text(
                translate("app.progress_dialog.cancel_button")
            )
            self.progress_dialog.cancel_clicked.connect(
                self.translation_manager.cancel_batch_translation
            )
            self.progress_dialog.show()

    def _update_progress_dialog(self, completed_count, total_count):
        if self.progress_dialog:
            if self.progress_dialog.maximum() != total_count:
                self.progress_dialog.set_maximum(total_count)
            self.progress_dialog.set_value(completed_count)

    def _finalize_batch_translation(self, reason: str = ""):
        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None
        completed = self.translation_manager.completed_jobs_for_progress
        total = self.translation_manager.total_jobs_for_progress
        status_msg = translate(
            "app.status.batch_finished", reason=reason, completed=completed, total=total
        )
        log_msg = f"Batch {reason}. Processed {completed}/{total}."
        if "cancel" in reason or "stop" in reason:
            cancelled_count = (
                total - self.translation_manager.completed_jobs_for_progress
            )
            if cancelled_count > 0:
                cancelled_msg_ui = translate(
                    "app.status.batch_cancelled_pending", count=cancelled_count
                )
                status_msg += f" {cancelled_msg_ui}"
                log_msg += f" {cancelled_count} pending cancelled."
        self.status_bar.showMessage(status_msg, STATUS_BAR_LONG_TIMEOUT_MS)
        logger.info(log_msg)
        translation_count = int(settings.current_settings.get("ux_t_count", 0))
        next_prompt_at = int(settings.current_settings.get("ux_next_prompt", 250))
        if translation_count >= next_prompt_at:
            is_dialog_shown_before = settings.current_settings.get(
                "ux_dialog_shown", False
            )
            if not is_dialog_shown_before:
                dialog = DonationDialog(self)
                dialog.exec()
                settings.current_settings["ux_dialog_shown"] = True
            else:
                self.notification_banner.show_banner(
                    text=translate("notification.donation.text"),
                    button_text=translate("notification.donation.button"),
                    on_click_action=lambda: webbrowser.open(
                        "https://nerkun.donatik.ua/"
                    ),
                )
            new_next_prompt_at = translation_count + 500 + random.randint(-150, 150)
            settings.current_settings["ux_next_prompt"] = new_next_prompt_at
            logger.debug(
                f"Donation prompt triggered. Next prompt will be at ~{new_next_prompt_at} translations."
            )

    @QtCore.Slot(str)
    def _open_connection_settings(self, connection_name: str):
        from .ui.dialogs import ProviderConfigDialog

        profile = next(
            (
                c
                for c in settings.current_settings.get("custom_connections", [])
                if c.get("name") == connection_name
            ),
            None,
        )
        if not profile:
            logger.warning(
                f"Could not find connection profile for '{connection_name}' to open settings."
            )
            return
        dialog = ProviderConfigDialog(existing_config=profile, parent=self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            updated_data = dialog.get_data()
            if updated_data:
                custom_connections = settings.current_settings.get(
                    "custom_connections", []
                )
                for i, conn in enumerate(custom_connections):
                    if conn.get("id") == updated_data.get("id"):
                        custom_connections[i] = updated_data
                        break
                settings.save_settings()
                for tab in self.loaded_tabs.values():
                    if hasattr(tab, "on_settings_changed"):
                        tab.on_settings_changed()
                logger.info(
                    f"Connection '{connection_name}' updated via banner dialog."
                )

    @QtCore.Slot(str, str)
    def _show_thinking_misconfigured_banner(self, conn_name: str, model_name: str):
        text = translate(
            "notification.thinking_misconfigured.text",
            conn_name=conn_name,
            model_name=model_name,
        )
        button_text = translate("notification.thinking_misconfigured.button")

        def on_click():
            return self._open_connection_settings(conn_name)

        self.notification_banner.show_banner(
            text, button_text, on_click, style="warning"
        )