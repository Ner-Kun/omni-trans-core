import json
import time
import random
import logging
import copy
import webbrowser
from PySide6 import QtWidgets, QtCore, QtGui
from .animations import AnimatedDialog
from .base_widgets import ShakeLineEdit, InfoButton
from ..localization_manager import loc_man, translate
from ..utils import wip_notification
from .. import settings
from ..runnables import FetchModelsWorker, ModelInfoWorker
try:
    from google import genai
except ImportError:
    genai = None

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE_UI.dialogs')

# Dialog Dimensions
ABOUT_DIALOG_MIN_WIDTH = 350
SETTINGS_DIALOG_MIN_WIDTH = 650
MANAGE_LANG_DIALOG_MIN_WIDTH = 350
PROVIDER_CONFIG_DIALOG_MIN_WIDTH = 850
PROVIDER_CONFIG_DIALOG_MIN_HEIGHT = 600
MODEL_INSPECTOR_DIALOG_MIN_WIDTH = 700
MODEL_INSPECTOR_DIALOG_MIN_HEIGHT = 650
MODEL_DETAILS_DIALOG_MIN_WIDTH = 500
MODEL_DETAILS_DIALOG_MIN_HEIGHT = 400
COMBINED_INFO_DIALOG_MIN_WIDTH = 600
COMBINED_INFO_DIALOG_MIN_HEIGHT = 500
PROGRESS_ANIMATION_DURATION_MS = 500

# Font Sizes
ABOUT_DIALOG_TITLE_FONT_SIZE = 16

# Spacing & Layout
ABOUT_DIALOG_MAIN_SPACING = 20
PROVIDER_CONFIG_MAIN_SPACING = 15
PROVIDER_GROUP_SPACING = 15
PROVIDER_CONFIG_SPLITTER_SIZES = [250, 600]
PROVIDER_MODELS_TABLE_MIN_HEIGHT = 140
PROVIDER_AVAIL_MODELS_COMBO_MIN_HEIGHT = 200
PROVIDER_TABLE_ROW_HEIGHT = 32
SETTINGS_TABLE_ACTION_BUTTON_SPACING = 5

# SpinBox & Validator Ranges
SETTINGS_RPM_LIMIT_MIN = 1
SETTINGS_RPM_LIMIT_MAX = 1000
SETTINGS_DELAY_SPIN_MIN = 0.1
SETTINGS_DELAY_SPIN_MAX = 60.0
SETTINGS_DELAY_SPIN_STEP = 0.1
SETTINGS_RPM_WARNING_MIN = 10
SETTINGS_RPM_WARNING_MAX = 95
PROVIDER_TIMEOUT_MIN = 10
PROVIDER_TIMEOUT_MAX = 3600
PROVIDER_DEFAULT_TIMEOUT = 600
PROVIDER_LIMIT_VALIDATOR_MAX = 1_000_000
PROVIDER_TPM_LIMIT_VALIDATOR_MAX = 100_000_000
CONN_ID_RANDOM_RANGE_MIN = 100
CONN_ID_RANDOM_RANGE_MAX = 999

# Colors and Styles
DIALOG_DELAY_WARNING_COLOR = "orange"
STATUS_INDICATOR_UNKNOWN_COLOR = "#888"
STATUS_INDICATOR_FETCHING_COLOR = "🟡"
STATUS_INDICATOR_SUCCESS_COLOR = "🟢"
STATUS_INDICATOR_FAIL_COLOR = "🔴"
STATUS_INDICATOR_INACTIVE_COLOR = "⚪️"
SETTINGS_ADD_NEW_BUTTON_STYLE = """
    QPushButton { border: none; background-color: transparent; padding: 5px; color: #888; font-style: italic; }
    QPushButton:hover { color: #ccc; }
"""
SETTINGS_TABLE_ACTION_BUTTON_STYLE = "QPushButton { border: none; background: transparent; font-size: 14px; }"

class AboutDialog(AnimatedDialog):
    def __init__(self, app_name: str, app_version: str, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.app_version = app_version
        self.setMinimumWidth(ABOUT_DIALOG_MIN_WIDTH)
        flags = self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        layout = QtWidgets.QVBoxLayout(self)
        self.title_label = QtWidgets.QLabel(app_name)
        title_font = self.title_label.font()
        title_font.setPointSize(ABOUT_DIALOG_TITLE_FONT_SIZE)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        self.version_label = QtWidgets.QLabel()
        self.version_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.version_label)
        layout.addSpacing(ABOUT_DIALOG_MAIN_SPACING)
        self.author_label = QtWidgets.QLabel()
        self.author_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.author_label)
        self.github_link_label = QtWidgets.QLabel()
        self.github_link_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.github_link_label.setOpenExternalLinks(True)
        layout.addWidget(self.github_link_label)
        layout.addStretch()
        self.ok_button = QtWidgets.QPushButton()
        self.ok_button.clicked.connect(self.accept)
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        loc_man.register(self, "windowTitle", "dialog.about.title", {'app_name': self.app_name, 'app_version': self.app_version})
        loc_man.register(self.version_label, "text", "dialog.about.version", {'app_version': self.app_version})
        loc_man.register(self.author_label, "text", "dialog.about.developed_by")
        loc_man.register(self.github_link_label, "text", "dialog.about.github_link")
        loc_man.register(self.ok_button, "text", "dialog.about.ok_button")

class SettingsDialog(AnimatedDialog):
    clear_cache_requested = QtCore.Signal()
    def __init__(self, settings_data, parent=None, dev_tools_available=True):
        super().__init__(parent)
        self.cache_clear_was_requested_flag = False
        self.dev_tools_available = dev_tools_available
        self.setMinimumWidth(SETTINGS_DIALOG_MIN_WIDTH)
        self.settings_data = settings_data.copy()
        self.actual_api_keys_in_dialog = list(self.settings_data.get("api_keys", []))
        self.user_selected_log_level = self.settings_data.get("log_level", "INFO")
        main_layout = QtWidgets.QVBoxLayout(self)
        self.tab_widget = QtWidgets.QTabWidget(self)
        api_main_tab = self._create_api_tab()
        lang_tab = self._create_language_tab()
        log_tab = self._create_logging_tab()
        self.tab_widget.addTab(api_main_tab, "API")
        self.tab_widget.addTab(log_tab, "Logging")
        self.tab_widget.addTab(lang_tab, "Language")
        main_layout.addWidget(self.tab_widget)
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept_settings)
        self.buttonBox.rejected.connect(self.reject)
        self.save_button = self.buttonBox.button(QtWidgets.QDialogButtonBox.Save)
        self.cancel_button = self.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel)
        main_layout.addWidget(self.buttonBox)
        self.logToFileCheck.toggled.connect(self._update_log_level_state)
        self._update_log_level_state()
        self._setup_localizations()

    def _setup_localizations(self):
        loc_man.register(self, "windowTitle", "dialog.settings.title")
        loc_man.register(self.tab_widget, "tabText", "dialog.settings.api_tab", index=0)
        loc_man.register(self.tab_widget, "tabText", "dialog.settings.logging_tab", index=1)
        loc_man.register(self.tab_widget, "tabText", "dialog.settings.language_tab.title", index=2)
        loc_man.register(self.nested_tab_widget, "tabText", "dialog.settings.gemini_tab.title", index=0)
        loc_man.register(self.nested_tab_widget, "tabText", "dialog.settings.custom_tab.title", index=1)
        if self.save_button:
            loc_man.register(self.save_button, "text", "dialog.settings.button_box.save")
        if self.cancel_button:
            loc_man.register(self.cancel_button, "text", "dialog.settings.button_box.cancel")
        loc_man.register(self.language_label, "text", "dialog.settings.language_tab.select_language")
        loc_man.register(self.translation_mode_check, "text", "dialog.settings.language_tab.translation_mode_check")
        if self.dev_tools_available:
            loc_man.register(self.translation_mode_info_button, "helpText", "dialog.settings.language_tab.translation_mode_info")
        loc_man.register(self.logToFileCheck, "text", "dialog.settings.logging.log_to_file_check")
        loc_man.register(self.log_level_label, "text", "dialog.settings.logging.log_level_label")
        loc_man.register(self.api_keys_group, "title", "dialog.settings.gemini.api_keys_group")
        loc_man.register(self.apiKeysListWidget, "toolTip", "dialog.settings.gemini.api_keys_tooltip")
        loc_man.register(self.addApiKeyButton, "text", "dialog.settings.gemini.add_key_button")
        loc_man.register(self.fetchModelsButton, "text", "dialog.settings.gemini.fetch_models_button")
        loc_man.register(self.fetchModelsButton, "toolTip", "dialog.settings.gemini.fetch_models_tooltip")
        loc_man.register(self.removeApiKeyButton, "text", "dialog.settings.gemini.remove_key_button")
        loc_man.register(self.gemini_model_label, "text", "dialog.settings.gemini.model_label")
        loc_man.register(self.get_details_btn, "text", "dialog.settings.gemini.get_details_button")
        loc_man.register(self.get_details_btn, "toolTip", "dialog.settings.gemini.get_details_tooltip")
        loc_man.register(self.api_limiting_label, "text", "dialog.settings.gemini.api_limiting_label")
        loc_man.register(self.rpm_limit_label, "text", "dialog.settings.gemini.rpm_limit_label")
        loc_man.register(self.rpm_limit_info_button, "helpText", "dialog.settings.gemini.rpm_limit_info")
        loc_man.register(self.manualControlCheck, "text", "dialog.settings.gemini.manual_control_check")
        loc_man.register(self.manual_control_info_button, "helpText", "dialog.settings.gemini.manual_control_info")
        loc_man.register(self.manual_delay_label, "text", "dialog.settings.gemini.manual_delay_label")
        loc_man.register(self.warning_threshold_label, "text", "dialog.settings.gemini.warning_threshold_label")
        loc_man.register(self.warning_threshold_info_button, "helpText", "dialog.settings.gemini.warning_threshold_info")
        self._populate_connections_table()

    def _create_language_tab(self):
        lang_tab = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(lang_tab)
        self.language_label = QtWidgets.QLabel()
        self.language_combo = QtWidgets.QComboBox()
        layout.addRow(self.language_label, self.language_combo)
        self.translation_mode_check = QtWidgets.QCheckBox()
        info_layout = QtWidgets.QHBoxLayout()
        info_layout.addWidget(self.translation_mode_check)
        self.translation_mode_info_button = InfoButton("", self)
        info_layout.addWidget(self.translation_mode_info_button)
        info_layout.addStretch()
        if self.dev_tools_available:
            is_enabled_in_settings = self.settings_data.get("translation_mode_enabled", False)
            self.translation_mode_check.setChecked(is_enabled_in_settings)
        else:
            self.translation_mode_check.setChecked(False)
            self.translation_mode_check.setEnabled(False)
            unavailable_text = translate("dialog.settings.language_tab.dev_tools_unavailable_tooltip")
            self.translation_mode_check.setToolTip(unavailable_text)
            self.translation_mode_info_button.setHelpText(unavailable_text)
        layout.addRow(info_layout)
        return lang_tab

    def _create_api_tab(self):
        api_tab_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(api_tab_widget)
        self.nested_tab_widget = QtWidgets.QTabWidget()
        gemini_tab = self._create_gemini_tab()
        custom_providers_tab = self._create_custom_providers_tab()
        self.nested_tab_widget.addTab(gemini_tab, "Google Gemini")
        self.nested_tab_widget.addTab(custom_providers_tab, "Custom connections")
        layout.addWidget(self.nested_tab_widget)
        return api_tab_widget

    def _create_gemini_tab(self):
        gemini_tab = QtWidgets.QWidget()
        api_layout = QtWidgets.QFormLayout(gemini_tab)
        self.api_keys_group = QtWidgets.QGroupBox()
        api_keys_layout = QtWidgets.QVBoxLayout(self.api_keys_group)
        self.apiKeysListWidget = QtWidgets.QListWidget()
        self._populate_api_keys_list()
        api_keys_layout.addWidget(self.apiKeysListWidget)
        api_keys_buttons_layout = QtWidgets.QHBoxLayout()
        self.addApiKeyButton = QtWidgets.QPushButton()
        self.addApiKeyButton.clicked.connect(self.add_api_key)
        self.fetchModelsButton = QtWidgets.QPushButton()
        self.fetchModelsButton.clicked.connect(self.fetch_models_from_api)
        self.removeApiKeyButton = QtWidgets.QPushButton()
        self.removeApiKeyButton.clicked.connect(self.remove_api_key)
        api_keys_buttons_layout.addWidget(self.addApiKeyButton)
        api_keys_buttons_layout.addWidget(self.fetchModelsButton)
        api_keys_buttons_layout.addWidget(self.removeApiKeyButton)
        api_keys_layout.addLayout(api_keys_buttons_layout)
        api_layout.addRow(self.api_keys_group)
        self.modelCombo = QtWidgets.QComboBox()
        self._populate_models_combo()
        model_layout = QtWidgets.QHBoxLayout()
        model_layout.addWidget(self.modelCombo)
        self.get_details_btn = QtWidgets.QPushButton()
        self.get_details_btn.clicked.connect(self.get_selected_gemini_model_details)
        model_layout.addWidget(self.get_details_btn)
        self.gemini_model_label = QtWidgets.QLabel()
        api_layout.addRow(self.gemini_model_label, model_layout)
        self.api_limiting_label = QtWidgets.QLabel()
        api_layout.addRow(self.api_limiting_label)
        self.rpmLimitSpin = QtWidgets.QSpinBox()
        self.rpmLimitSpin.setRange(SETTINGS_RPM_LIMIT_MIN, SETTINGS_RPM_LIMIT_MAX)
        self.rpmLimitSpin.setValue(self.settings_data.get("rpm_limit", settings.default_settings["rpm_limit"]))
        rpm_label_widget = QtWidgets.QWidget()
        rpm_label_layout = QtWidgets.QHBoxLayout(rpm_label_widget)
        rpm_label_layout.setContentsMargins(0, 0, 0, 0)
        rpm_label_layout.setSpacing(5)
        self.rpm_limit_label = QtWidgets.QLabel()
        rpm_label_layout.addWidget(self.rpm_limit_label)
        self.rpm_limit_info_button = InfoButton("", self)
        rpm_label_layout.addWidget(self.rpm_limit_info_button)
        rpm_label_layout.addStretch()
        api_layout.addRow(rpm_label_widget, self.rpmLimitSpin)
        self.manualControlCheck = QtWidgets.QCheckBox()
        self.manualControlCheck.setChecked(self.settings_data.get("manual_rpm_control", settings.default_settings["manual_rpm_control"]))
        manual_control_layout = QtWidgets.QHBoxLayout()
        manual_control_layout.setContentsMargins(0, 0, 0, 0)
        manual_control_layout.addWidget(self.manualControlCheck)
        self.manual_control_info_button = InfoButton("", self)
        manual_control_layout.addWidget(self.manual_control_info_button)
        manual_control_layout.addStretch()
        api_layout.addRow(manual_control_layout)
        self.delaySpin = QtWidgets.QDoubleSpinBox()
        self.delaySpin.setRange(SETTINGS_DELAY_SPIN_MIN, SETTINGS_DELAY_SPIN_MAX)
        self.delaySpin.setSingleStep(SETTINGS_DELAY_SPIN_STEP)
        self.delaySpin.setValue(self.settings_data.get("api_request_delay", settings.default_settings["api_request_delay"]))
        loc_man.register(self.delaySpin, "suffix", "dialog.settings.gemini.delay_suffix")
        self.manual_delay_label = QtWidgets.QLabel()
        api_layout.addRow(self.manual_delay_label, self.delaySpin)
        self.delayWarningLabel = QtWidgets.QLabel("")
        self.delayWarningLabel.setStyleSheet(f"color: {DIALOG_DELAY_WARNING_COLOR};")
        self.delayWarningLabel.setWordWrap(True)
        api_layout.addRow(self.delayWarningLabel)
        self.rpmWarningSpin = QtWidgets.QSpinBox()
        self.rpmWarningSpin.setRange(SETTINGS_RPM_WARNING_MIN, SETTINGS_RPM_WARNING_MAX)
        self.rpmWarningSpin.setSuffix(" %")
        self.rpmWarningSpin.setValue(self.settings_data.get("rpm_warning_threshold_percent", settings.default_settings["rpm_warning_threshold_percent"]))
        rpm_warning_label_widget = QtWidgets.QWidget()
        rpm_warning_label_layout = QtWidgets.QHBoxLayout(rpm_warning_label_widget)
        rpm_warning_label_layout.setContentsMargins(0, 0, 0, 0)
        rpm_warning_label_layout.setSpacing(5)
        self.warning_threshold_label = QtWidgets.QLabel()
        rpm_warning_label_layout.addWidget(self.warning_threshold_label)
        self.warning_threshold_info_button = InfoButton("", self)
        rpm_warning_label_layout.addWidget(self.warning_threshold_info_button)
        rpm_warning_label_layout.addStretch()
        api_layout.addRow(rpm_warning_label_widget, self.rpmWarningSpin)
        self.manualControlCheck.toggled.connect(self.update_delay_control_state)
        self.delaySpin.valueChanged.connect(self.check_manual_delay_warning)
        self.rpmLimitSpin.valueChanged.connect(lambda: self.update_delay_control_state())
        self.update_delay_control_state(self.manualControlCheck.isChecked())
        self._update_fetch_button_state()
        return gemini_tab

    def _create_custom_providers_tab(self):
        custom_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(custom_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        self.connections_table = QtWidgets.QTableWidget()
        self.connections_table.setColumnCount(6)
        self.connections_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.connections_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.connections_table.verticalHeader().setVisible(False)
        self.connections_table.setShowGrid(True)
        header = self.connections_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.connections_table)
        return custom_tab

    def _populate_connections_table(self):
        headers = [
            translate("dialog.settings.custom.table_header.num"),
            translate("dialog.settings.custom.table_header.name"),
            translate("dialog.settings.custom.table_header.provider"),
            translate("dialog.settings.custom.table_header.models"),
            translate("dialog.settings.custom.table_header.total"),
            translate("dialog.settings.custom.table_header.actions")]
        self.connections_table.setHorizontalHeaderLabels(headers)
        self.connections_table.clearContents()
        self.connections_table.setRowCount(0)
        connections = self.settings_data.get("custom_connections", [])
        self.connections_table.setRowCount(len(connections) + 1)
        for row, conn in enumerate(connections):
            num_item = QtWidgets.QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.connections_table.setItem(row, 0, num_item)
            self.connections_table.setItem(row, 1, QtWidgets.QTableWidgetItem(conn.get("name", "N/A")))
            provider_id = conn.get("provider", "N/A")
            provider_display = settings.PROVIDER_DISPLAY_NAMES.get(provider_id, provider_id)
            self.connections_table.setItem(row, 2, QtWidgets.QTableWidgetItem(provider_display))
            
            model_configs = conn.get("configured_models", [])
            model_names = [m.get("model_id", "N/A").split('/')[-1] for m in model_configs]
            num_models = len(model_names)

            display_models_text = ", ".join(model_names[:2])
            if num_models > 2:
                display_models_text += ", ..."
            
            self.connections_table.setItem(row, 3, QtWidgets.QTableWidgetItem(display_models_text or "N/A"))
            
            total_item = QtWidgets.QTableWidgetItem(str(num_models))
            total_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.connections_table.setItem(row, 4, total_item)

            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 0, 5, 0)
            actions_layout.setSpacing(SETTINGS_TABLE_ACTION_BUTTON_SPACING)
            edit_button = QtWidgets.QPushButton("✏️")
            loc_man.register(edit_button, "toolTip", "dialog.settings.custom.edit_button_tooltip")
            delete_button = QtWidgets.QPushButton("🗑️")
            loc_man.register(delete_button, "toolTip", "dialog.settings.custom.delete_button_tooltip")
            edit_button.setStyleSheet(SETTINGS_TABLE_ACTION_BUTTON_STYLE)
            delete_button.setStyleSheet(SETTINGS_TABLE_ACTION_BUTTON_STYLE)
            edit_button.setCursor(QtCore.Qt.PointingHandCursor)
            delete_button.setCursor(QtCore.Qt.PointingHandCursor)
            edit_button.clicked.connect(lambda _, r=row: self._edit_connection(r))
            delete_button.clicked.connect(lambda _, r=row: self._remove_connection(r))
            actions_layout.addWidget(edit_button)
            actions_layout.addWidget(delete_button)
            actions_layout.addStretch()
            self.connections_table.setCellWidget(row, 5, actions_widget)
            self.connections_table.setRowHeight(row, PROVIDER_TABLE_ROW_HEIGHT)
        add_row_index = len(connections)
        add_button_container = QtWidgets.QWidget()
        add_button_layout = QtWidgets.QHBoxLayout(add_button_container)
        add_button_layout.setContentsMargins(0, 0, 0, 0)
        add_button = QtWidgets.QPushButton()
        loc_man.register(add_button, "text", "dialog.settings.custom.add_new_button")
        add_button.setStyleSheet(SETTINGS_ADD_NEW_BUTTON_STYLE)
        add_button.setCursor(QtCore.Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_connection)
        add_button_layout.addStretch()
        add_button_layout.addWidget(add_button)
        add_button_layout.addStretch()
        self.connections_table.setCellWidget(add_row_index, 0, add_button_container)
        self.connections_table.setSpan(add_row_index, 0, 1, 6)
        self.connections_table.setRowHeight(add_row_index, PROVIDER_TABLE_ROW_HEIGHT)

    def _add_connection(self):
        dialog = ProviderConfigDialog(parent=self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            config_data = dialog.get_data()
            if config_data:
                rand_val = random.randint(CONN_ID_RANDOM_RANGE_MIN, CONN_ID_RANDOM_RANGE_MAX)
                config_data["id"] = f"conn_{int(time.time())}_{rand_val}"
                if "custom_connections" not in self.settings_data:
                    self.settings_data["custom_connections"] = []
                self.settings_data["custom_connections"].append(config_data)
                self._populate_connections_table()
                logger.info(f"Successfully added new connection '{config_data['name']}'.")

    def _edit_connection(self, row):
        connections = self.settings_data.get("custom_connections", [])
        if not (0 <= row < len(connections)):
            return
        conn_to_edit = connections[row]
        dialog = ProviderConfigDialog(provider_to_edit=conn_to_edit.get("provider"), existing_config=conn_to_edit, parent=self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            updated_data = dialog.get_data()
            if updated_data:
                self.settings_data["custom_connections"][row] = updated_data
                self._populate_connections_table()
                logger.info(f"Successfully updated connection '{updated_data['name']}'.")

    def _remove_connection(self, row):
        connections = self.settings_data.get("custom_connections", [])
        if not (0 <= row < len(connections)):
            return
        conn_to_remove = connections[row]
        title = translate("dialog.settings.custom.remove_connection_title")
        text = translate("dialog.settings.custom.remove_connection_text", conn_name=conn_to_remove.get('name', 'N/A'))
        reply = QtWidgets.QMessageBox.question(self, title, text, QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No, QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            del self.settings_data["custom_connections"][row]
            self._populate_connections_table()
            logger.info(f"Removed connection '{conn_to_remove.get('name', 'N/A')}'.")

    def _create_logging_tab(self):
        log_tab = QtWidgets.QWidget()
        log_layout_main = QtWidgets.QVBoxLayout(log_tab)
        self.logToFileCheck = QtWidgets.QCheckBox()
        self.logToFileCheck.setChecked(self.settings_data.get("log_to_file", settings.default_settings["log_to_file"]))
        log_layout_main.addWidget(self.logToFileCheck)
        log_level_layout = QtWidgets.QHBoxLayout()
        self.log_level_label = QtWidgets.QLabel()
        log_level_layout.addWidget(self.log_level_label)
        self.logLevelCombo = QtWidgets.QComboBox()
        self.logLevelCombo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.logLevelCombo.setCurrentText(self.settings_data.get("log_level", settings.default_settings["log_level"]).upper())
        log_level_layout.addWidget(self.logLevelCombo)
        log_layout_main.addLayout(log_level_layout)
        log_layout_main.addStretch()
        return log_tab

    def _update_log_level_state(self):
        is_checked = self.logToFileCheck.isChecked()
        self.logLevelCombo.setEnabled(not is_checked)
        if is_checked:
            self.logLevelCombo.setCurrentText("DEBUG")
        else:
            self.logLevelCombo.setCurrentText(self.user_selected_log_level)

    def update_delay_control_state(self, is_manual=None):
        if is_manual is None:
            is_manual = self.manualControlCheck.isChecked()
        self.delaySpin.setEnabled(is_manual)
        if not is_manual:
            rpm_limit = self.rpmLimitSpin.value()
            calculated_delay = 60.0 / rpm_limit if rpm_limit > 0 else 60.0
            self.delaySpin.blockSignals(True)
            self.delaySpin.setValue(calculated_delay)
            self.delaySpin.blockSignals(False)
        self.check_manual_delay_warning()

    def check_manual_delay_warning(self):
        if not self.manualControlCheck.isChecked():
            self.delayWarningLabel.hide()
            return
        manual_delay, rpm_limit = self.delaySpin.value(), self.rpmLimitSpin.value()
        safe_delay = 60.0 / rpm_limit if rpm_limit > 0 else 60.0
        if manual_delay < safe_delay:
            self.delayWarningLabel.setText(translate("dialog.settings.gemini.delay_warning", safe_delay=f"{safe_delay:.2f}", rpm_limit=rpm_limit))
            self.delayWarningLabel.show()
        else: 
            self.delayWarningLabel.hide()

    def _mask_api_key_for_dialog(self, key):
        return f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"

    def _populate_api_keys_list(self):
        self.apiKeysListWidget.clear()
        for key in self.actual_api_keys_in_dialog:
            self.apiKeysListWidget.addItem(self._mask_api_key_for_dialog(key))

    def _update_fetch_button_state(self):
        self.fetchModelsButton.setEnabled(len(self.actual_api_keys_in_dialog) > 0)

    def add_api_key(self):
        title = translate("dialog.settings.add_api_key.title")
        label = translate("dialog.settings.add_api_key.label")
        key, ok = QtWidgets.QInputDialog.getText(self, title, label, QtWidgets.QLineEdit.Normal)
        if ok and key:
            self.actual_api_keys_in_dialog.append(key)
            self._populate_api_keys_list()
            self._update_fetch_button_state()

    def remove_api_key(self):
        row = self.apiKeysListWidget.currentRow()
        if row >= 0: 
            del self.actual_api_keys_in_dialog[row]
            self._populate_api_keys_list()
            self._update_fetch_button_state()

    def fetch_models_from_api(self):
        if not self.actual_api_keys_in_dialog: 
            return
        if not genai:
            title = translate("dialog.settings.fetch_models.error.library_missing_title")
            text = translate("dialog.settings.fetch_models.error.library_missing_text")
            QtWidgets.QMessageBox.critical(self, title, text)
            logger.error("Attempted to fetch models, but google.genai library is not available.")
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            fetched_models = []
            for key in self.actual_api_keys_in_dialog:
                try:
                    client = genai.Client(api_key=key)
                    models = [m.name.replace("models/", "") for m in client.models.list() if 'gemini' in m.name]
                    if models: 
                        fetched_models = sorted(list(set(models))) 
                        break
                except Exception: 
                    continue
            if fetched_models:
                self.settings_data["available_gemini_models"] = fetched_models
                self._populate_models_combo()
                title = translate("dialog.settings.fetch_models.success.title")
                text = translate("dialog.settings.fetch_models.success.text", model_count=len(fetched_models))
                QtWidgets.QMessageBox.information(self, title, text)
            else:
                title = translate("dialog.settings.fetch_models.error.generic_title")
                text = translate("dialog.settings.fetch_models.error.generic_text")
                QtWidgets.QMessageBox.warning(self, title, text)
        finally: 
            QtWidgets.QApplication.restoreOverrideCursor()

    def get_selected_gemini_model_details(self):
        if not self.actual_api_keys_in_dialog:
            QtWidgets.QMessageBox.warning(self, translate("dialog.settings.model_details.error.api_key_error_title"), translate("dialog.settings.model_details.error.no_key_added"))
            return
        if not genai:
            title = translate("dialog.settings.fetch_models.error.library_missing_title")
            text = translate("dialog.settings.fetch_models.error.library_missing_text")
            QtWidgets.QMessageBox.critical(self, title, text)
            return
        api_key = self.actual_api_keys_in_dialog[0]
        model_display_text = self.modelCombo.currentText()
        if not model_display_text:
            QtWidgets.QMessageBox.warning(self, translate("dialog.settings.model_details.error.model_error_title"), translate("dialog.settings.model_details.error.no_model_selected"))
            return
        clean_model_name = model_display_text.split(' (')[0]
        full_model_name = f"models/{clean_model_name}"
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            client = genai.Client(api_key=api_key)
            details = client.models.get(model=full_model_name)
            attributes_to_display = [
                "name", "display_name", "description", "version",
                "input_token_limit", "output_token_limit"]
            model_info = {attr: getattr(details, attr) for attr in attributes_to_display if hasattr(details, attr)}
            pretty_response = json.dumps(model_info, indent=4, default=str)
            result_dialog = QtWidgets.QDialog(self)
            dialog_title = translate("dialog.settings.model_details.dialog_title", clean_model_name=clean_model_name)
            result_dialog.setWindowTitle(dialog_title)
            result_dialog.setMinimumSize(MODEL_DETAILS_DIALOG_MIN_WIDTH, MODEL_DETAILS_DIALOG_MIN_HEIGHT)
            layout = QtWidgets.QVBoxLayout(result_dialog)
            text_edit = QtWidgets.QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(pretty_response)
            text_edit.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
            button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
            button_box.accepted.connect(result_dialog.accept)
            layout.addWidget(text_edit)
            layout.addWidget(button_box)
            result_dialog.exec()
        except Exception as e:
            title = translate("dialog.settings.model_details.error.request_failed", clean_model_name=clean_model_name, error_details=str(e))
            QtWidgets.QMessageBox.critical(self, translate("dialog.settings.model_details.error.request_failed_title"), title)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
    
    def _populate_models_combo(self):
        current_model = self.settings_data.get("gemini_model", settings.default_settings["gemini_model"])
        models = self.settings_data.get("available_gemini_models", [])
        if current_model and current_model not in models: 
            models.append(current_model)
        self.modelCombo.clear()
        self.modelCombo.addItems(sorted(list(set(models))))
        if current_model in models: 
            self.modelCombo.setCurrentText(current_model)
    
    def accept_settings(self):
        self.settings_data["api_keys"] = self.actual_api_keys_in_dialog
        if "active_model_for_connection" in self.settings_data:
            active_models = self.settings_data.get("active_model_for_connection", {})
            all_connections = self.settings_data.get("custom_connections", [])
            valid_models = set()
            for conn in all_connections:
                conn_name = conn.get("name")
                if conn_name:
                    for model in conn.get("configured_models", []):
                        model_id = model.get("model_id")
                        if model_id:
                            valid_models.add((conn_name, model_id))
            for conn_name, active_model_id in list(active_models.items()):
                if (conn_name, active_model_id) not in valid_models:
                    del self.settings_data["active_model_for_connection"][conn_name]
                    logger.debug(f"Removed stale active model entry: {conn_name} -> {active_model_id}")
        self.settings_data["gemini_model"] = self.modelCombo.currentText()
        self.settings_data["rpm_limit"] = self.rpmLimitSpin.value()
        self.settings_data["manual_rpm_control"] = self.manualControlCheck.isChecked()
        self.settings_data["api_request_delay"] = self.delaySpin.value()
        self.settings_data["rpm_warning_threshold_percent"] = self.rpmWarningSpin.value()
        self.settings_data["log_to_file"] = self.logToFileCheck.isChecked()
        self.settings_data["log_level"] = self.logLevelCombo.currentText()
        self.settings_data["user_language"] = self.language_combo.currentData()
        if self.dev_tools_available:
            self.settings_data["translation_mode_enabled"] = self.translation_mode_check.isChecked()
        else:
            self.settings_data["translation_mode_enabled"] = False
        if self.cache_clear_was_requested_flag:
            self.clear_cache_requested.emit()
        self.accept()

    def get_settings(self):
        return self.settings_data

class ProviderConfigDialog(AnimatedDialog):
    _BASE_URL_READONLY_STYLE = "QLineEdit { background-color: #282a36; border: 1px solid #44475a; color: #999; }"

    def __init__(self, provider_to_edit=None, existing_config=None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(
            PROVIDER_CONFIG_DIALOG_MIN_WIDTH, PROVIDER_CONFIG_DIALOG_MIN_HEIGHT
        )
        flags = self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        self.is_edit_mode = existing_config is not None
        self.existing_config = existing_config or {}
        self.provider_to_edit = provider_to_edit or self.existing_config.get("provider")
        self.configured_models = copy.deepcopy(
            self.existing_config.get("configured_models", [])
        )
        self.current_model_idx = -1
        self.fetched_models_cache = None
        self.placeholder_text = ""
        self.async_handler = ProviderConfigAsyncHandler(self)
        self.current_additional_params = {}
        self._build_ui()
        self._setup_localizations()
        self._connect_signals()
        self._initial_setup()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(PROVIDER_CONFIG_MAIN_SPACING)
        self.connection_group = QtWidgets.QGroupBox()
        connection_form_layout = QtWidgets.QFormLayout(self.connection_group)
        self.name_edit = QtWidgets.QLineEdit()
        self.provider_combo = QtWidgets.QComboBox()
        self.base_url_edit = QtWidgets.QLineEdit()
        self.base_url_edit.installEventFilter(self)
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.timeout_edit = ShakeLineEdit()
        self.timeout_edit.setValidator(
            QtGui.QIntValidator(PROVIDER_TIMEOUT_MIN, PROVIDER_TIMEOUT_MAX)
        )
        self.timeout_label = QtWidgets.QLabel()
        self.connection_name_label = QtWidgets.QLabel()
        self.provider_label = QtWidgets.QLabel()
        self.base_url_label = QtWidgets.QLabel()
        self.api_key_label = QtWidgets.QLabel()
        connection_form_layout.addRow(self.connection_name_label, self.name_edit)
        connection_form_layout.addRow(self.provider_label, self.provider_combo)
        connection_form_layout.addRow(self.base_url_label, self.base_url_edit)
        connection_form_layout.addRow(self.api_key_label, self.api_key_edit)
        connection_form_layout.addRow(self.timeout_label, self.timeout_edit)
        self.global_limits_group = QtWidgets.QGroupBox()
        global_limits_layout = QtWidgets.QGridLayout(self.global_limits_group)
        self.global_rpm_edit = ShakeLineEdit()
        self.global_rpd_edit = ShakeLineEdit()
        self.global_tpm_edit = ShakeLineEdit()
        int_validator_global = QtGui.QIntValidator(0, PROVIDER_LIMIT_VALIDATOR_MAX)
        self.global_rpm_edit.setValidator(int_validator_global)
        self.global_rpd_edit.setValidator(int_validator_global)
        self.global_tpm_edit.setValidator(
            QtGui.QIntValidator(0, PROVIDER_TPM_LIMIT_VALIDATOR_MAX)
        )
        self.global_rpm_label = QtWidgets.QLabel()
        self.global_rpd_label = QtWidgets.QLabel()
        self.global_tpm_label = QtWidgets.QLabel()
        global_limits_layout.addWidget(
            self.global_rpm_label, 0, 0, alignment=QtCore.Qt.AlignRight
        )
        global_limits_layout.addWidget(self.global_rpm_edit, 0, 1)
        global_limits_layout.addWidget(
            self.global_rpd_label, 0, 2, alignment=QtCore.Qt.AlignRight
        )
        global_limits_layout.addWidget(self.global_rpd_edit, 0, 3)
        global_limits_layout.addWidget(
            self.global_tpm_label, 1, 0, alignment=QtCore.Qt.AlignRight
        )
        global_limits_layout.addWidget(self.global_tpm_edit, 1, 1)
        self.wait_for_response_check = QtWidgets.QCheckBox()
        global_limits_layout.addWidget(self.wait_for_response_check, 1, 2, 1, 2)
        connection_form_layout.addRow(self.global_limits_group)
        main_layout.addWidget(self.connection_group)
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.models_group = QtWidgets.QGroupBox()
        models_group_layout = QtWidgets.QVBoxLayout(self.models_group)
        self.models_table = QtWidgets.QTableWidget()
        self.models_table.setColumnCount(2)
        self.models_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.models_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.models_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.models_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.setMinimumHeight(PROVIDER_MODELS_TABLE_MIN_HEIGHT)
        models_group_layout.addWidget(self.models_table)
        models_buttons_layout = QtWidgets.QHBoxLayout()
        self.add_model_btn = QtWidgets.QPushButton()
        self.remove_model_btn = QtWidgets.QPushButton()
        models_buttons_layout.addStretch()
        models_buttons_layout.addWidget(self.add_model_btn)
        models_buttons_layout.addWidget(self.remove_model_btn)
        models_group_layout.addLayout(models_buttons_layout)
        main_splitter.addWidget(self.models_group)
        self.model_editor_widget = QtWidgets.QGroupBox()
        editor_layout = QtWidgets.QVBoxLayout(self.model_editor_widget)
        form_layout = QtWidgets.QFormLayout()
        self.model_id_edit = QtWidgets.QLineEdit()
        self.model_id_editor_label = QtWidgets.QLabel()
        form_layout.addRow(self.model_id_editor_label, self.model_id_edit)
        self.available_models_combo = QtWidgets.QComboBox()
        self.available_models_combo.view().setMinimumHeight(
            PROVIDER_AVAIL_MODELS_COMBO_MIN_HEIGHT
        )
        self.available_models_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.available_models_combo.view().setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.AdjustToContents
        )
        self.available_models_label = QtWidgets.QLabel()
        form_layout.addRow(self.available_models_label, self.available_models_combo)
        actions_layout = QtWidgets.QHBoxLayout()
        self.info_button = QtWidgets.QPushButton()
        status_layout = QtWidgets.QHBoxLayout()
        self.status_indicator_icon = QtWidgets.QLabel("●")
        self.status_indicator_label = QtWidgets.QLabel()
        self.status_indicator_label.setStyleSheet(
            f"color: {STATUS_INDICATOR_UNKNOWN_COLOR};"
        )
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.addStretch()
        status_layout.addWidget(
            self.status_indicator_icon, alignment=QtCore.Qt.AlignRight
        )
        status_layout.addWidget(
            self.status_indicator_label, alignment=QtCore.Qt.AlignLeft
        )
        status_layout.addStretch()
        self.fetch_models_btn = QtWidgets.QPushButton()
        actions_layout.addWidget(self.info_button, 1)
        actions_layout.addLayout(status_layout, 0)
        actions_layout.addWidget(self.fetch_models_btn, 1)
        form_layout.addRow(actions_layout)
        self.parsing_group = QtWidgets.QGroupBox()
        tags_layout = QtWidgets.QHBoxLayout(self.parsing_group)
        self.start_tag_edit = QtWidgets.QLineEdit()
        self.end_tag_edit = QtWidgets.QLineEdit()
        self.start_tag_label = QtWidgets.QLabel()
        self.end_tag_label = QtWidgets.QLabel()
        tags_layout.addWidget(self.start_tag_label)
        tags_layout.addWidget(self.start_tag_edit)
        tags_layout.addSpacing(PROVIDER_GROUP_SPACING)
        tags_layout.addWidget(self.end_tag_label)
        tags_layout.addWidget(self.end_tag_edit)
        self.limits_group = QtWidgets.QGroupBox()
        limits_grid_layout = QtWidgets.QGridLayout(self.limits_group)
        top_limits_layout = QtWidgets.QHBoxLayout()
        self.reset_model_settings_btn = QtWidgets.QPushButton()
        top_limits_layout.addStretch()
        top_limits_layout.addWidget(self.reset_model_settings_btn)
        top_limits_layout.addStretch()
        limits_grid_layout.addLayout(top_limits_layout, 0, 0, 1, 4)
        self.use_global_limits_check = QtWidgets.QCheckBox()
        limits_grid_layout.addWidget(self.use_global_limits_check, 1, 0, 1, 4)
        self.rpm_edit = ShakeLineEdit()
        self.rpd_edit = ShakeLineEdit()
        self.tpm_edit = ShakeLineEdit()
        int_validator = QtGui.QIntValidator(0, PROVIDER_LIMIT_VALIDATOR_MAX)
        self.rpm_edit.setValidator(int_validator)
        self.rpd_edit.setValidator(int_validator)
        self.tpm_edit.setValidator(
            QtGui.QIntValidator(0, PROVIDER_TPM_LIMIT_VALIDATOR_MAX)
        )
        self.model_rpm_label = QtWidgets.QLabel()
        self.model_rpd_label = QtWidgets.QLabel()
        self.model_tpm_label = QtWidgets.QLabel()
        limits_grid_layout.addWidget(
            self.model_rpm_label, 2, 0, alignment=QtCore.Qt.AlignRight
        )
        limits_grid_layout.addWidget(self.rpm_edit, 2, 1)
        limits_grid_layout.addWidget(
            self.model_rpd_label, 2, 2, alignment=QtCore.Qt.AlignRight
        )
        limits_grid_layout.addWidget(self.rpd_edit, 2, 3)
        limits_grid_layout.addWidget(
            self.model_tpm_label, 3, 0, alignment=QtCore.Qt.AlignRight
        )
        limits_grid_layout.addWidget(self.tpm_edit, 3, 1, 1, 3)
        editor_layout.addLayout(form_layout)
        editor_layout.addWidget(self.parsing_group)

        self.thinking_mode_group = QtWidgets.QGroupBox()
        thinking_mode_layout = QtWidgets.QFormLayout(self.thinking_mode_group)

        self.thinking_mode_combo = QtWidgets.QComboBox()
        self.thinking_mode_label = QtWidgets.QLabel("Thinking Mode:")

        self.configure_params_btn = QtWidgets.QPushButton("Configure...")
        self.configure_params_btn.setVisible(False)

        thinking_mode_combo_layout = QtWidgets.QHBoxLayout()
        thinking_mode_combo_layout.setContentsMargins(0, 0, 0, 0)
        thinking_mode_combo_layout.addWidget(self.thinking_mode_combo, 1)
        thinking_mode_combo_layout.addWidget(self.configure_params_btn)

        thinking_mode_layout.addRow(
            self.thinking_mode_label, thinking_mode_combo_layout
        )

        editor_layout.addWidget(self.thinking_mode_group)

        self.thinking_commands_group = QtWidgets.QGroupBox()
        thinking_commands_layout = QtWidgets.QHBoxLayout(self.thinking_commands_group)
        self.enable_cmd_edit = QtWidgets.QLineEdit()
        self.disable_cmd_edit = QtWidgets.QLineEdit()
        self.enable_cmd_label = QtWidgets.QLabel()
        self.disable_cmd_label = QtWidgets.QLabel()
        thinking_commands_layout.addWidget(self.enable_cmd_label)
        thinking_commands_layout.addWidget(self.enable_cmd_edit)
        thinking_commands_layout.addSpacing(PROVIDER_GROUP_SPACING)
        thinking_commands_layout.addWidget(self.disable_cmd_label)
        thinking_commands_layout.addWidget(self.disable_cmd_edit)
        editor_layout.addWidget(self.thinking_commands_group)

        self.thinking_commands_group.setVisible(False)

        self.limits_group.setTitle("Model-Specific Settings")
        editor_layout.addWidget(self.limits_group)
        main_splitter.addWidget(self.model_editor_widget)
        main_splitter.setSizes(PROVIDER_CONFIG_SPLITTER_SIZES)
        main_layout.addWidget(main_splitter)
        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet(f"color: {STATUS_INDICATOR_UNKNOWN_COLOR};")
        self.info_label.setWordWrap(True)
        main_layout.addWidget(self.info_label)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        main_layout.addWidget(self.button_box)
        self.ok_button = self.button_box.button(QtWidgets.QDialogButtonBox.Ok)

    def eventFilter(self, watched, event):
        if watched is self.base_url_edit and event.type() == QtCore.QEvent.MouseButtonDblClick:
            if self.base_url_edit.isReadOnly():
                self.base_url_edit.setReadOnly(False)
                self.base_url_edit.setStyleSheet("")
                return True
        return super().eventFilter(watched, event)

    def _update_base_url_state(self):
        provider_id = self.provider_combo.currentData()
        is_cloud_provider = provider_id in settings.CLOUD_PROVIDERS
        is_readonly = is_cloud_provider and provider_id != "openai_compatible"
        self.base_url_edit.setReadOnly(is_readonly)
        if is_readonly:
            self.base_url_edit.setStyleSheet(self._BASE_URL_READONLY_STYLE)
            loc_man.register(
                self.base_url_edit,
                "toolTip",
                "dialog.provider_config.tooltip.base_url_cloud",
            )
        else:
            self.base_url_edit.setStyleSheet("")
            self.base_url_edit.setToolTip("")

    def _setup_localizations(self):
        conn_name = self.existing_config.get('name', '')
        if self.is_edit_mode:
            loc_man.register(self, "windowTitle", "dialog.provider_config.edit_title", conn_name=conn_name)
        else:
            loc_man.register(self, "windowTitle", "dialog.provider_config.add_title")
        loc_man.register(self.connection_group, "title", "dialog.provider_config.group.connection_profile")
        loc_man.register(self.connection_name_label, "text", "dialog.provider_config.label.connection_name")
        loc_man.register(self.name_edit, "placeholderText", "dialog.provider_config.placeholder.connection_name")
        loc_man.register(self.provider_label, "text", "dialog.provider_config.label.provider")
        loc_man.register(self.base_url_label, "text", "dialog.provider_config.label.base_url")
        loc_man.register(self.api_key_label, "text", "dialog.provider_config.label.api_key")
        loc_man.register(self.timeout_label, "text", "dialog.provider_config.label.timeout")
        loc_man.register(self.global_limits_group, "title", "dialog.provider_config.group.global_limits")
        loc_man.register(self.global_rpm_label, "text", "dialog.provider_config.label.rpm")
        loc_man.register(self.global_rpd_label, "text", "dialog.provider_config.label.rpd")
        loc_man.register(self.global_tpm_label, "text", "dialog.provider_config.label.tpm")
        loc_man.register(self.wait_for_response_check, "text", "dialog.provider_config.check.sequential_processing")
        loc_man.register(self.wait_for_response_check, "toolTip", "dialog.provider_config.tooltip.sequential_processing")
        loc_man.register(self.models_group, "title", "dialog.provider_config.group.configured_models")
        loc_man.register(self.add_model_btn, "text", "dialog.provider_config.button.add_model")
        loc_man.register(self.remove_model_btn, "text", "dialog.provider_config.button.remove_model")
        loc_man.register(self.model_editor_widget, "title", "dialog.provider_config.group.model_settings")
        loc_man.register(self.model_id_editor_label, "text", "dialog.provider_config.label.model_id_editor")
        loc_man.register(self.available_models_label, "text", "dialog.provider_config.label.available_models")
        loc_man.register(self.info_button, "text", "dialog.provider_config.button.info")
        loc_man.register(self.status_indicator_label, "text", "dialog.provider_config.label.status_unknown")
        loc_man.register(self.fetch_models_btn, "text", "dialog.provider_config.button.get_models")
        loc_man.register(self.parsing_group, "title", "dialog.provider_config.group.parsing")
        loc_man.register(self.start_tag_edit, "placeholderText", "dialog.provider_config.placeholder.start_tag")
        loc_man.register(self.end_tag_edit, "placeholderText", "dialog.provider_config.placeholder.end_tag")
        loc_man.register(self.start_tag_label, "text", "dialog.provider_config.label.start_tag")
        loc_man.register(self.end_tag_label, "text", "dialog.provider_config.label.end_tag")
        loc_man.register(self.thinking_commands_group, "title", "dialog.provider_config.group.thinking_commands")
        loc_man.register(self.enable_cmd_label, "text", "dialog.provider_config.label.enable_cmd")
        loc_man.register(self.disable_cmd_label, "text", "dialog.provider_config.label.disable_cmd")
        loc_man.register(self.enable_cmd_edit, "placeholderText", "dialog.provider_config.placeholder.enable_cmd")
        loc_man.register(self.disable_cmd_edit, "placeholderText", "dialog.provider_config.placeholder.disable_cmd")
        loc_man.register(self.limits_group, "title", "dialog.provider_config.group.model_limits")
        loc_man.register(self.reset_model_settings_btn, "text", "dialog.provider_config.button.reset_model")
        loc_man.register(self.reset_model_settings_btn, "toolTip", "dialog.provider_config.button.reset_model_tooltip")
        loc_man.register(self.use_global_limits_check, "text", "dialog.provider_config.check.use_global_limits")
        loc_man.register(self.model_rpm_label, "text", "dialog.provider_config.label.rpm")
        loc_man.register(self.model_rpd_label, "text", "dialog.provider_config.label.rpd")
        loc_man.register(self.model_tpm_label, "text", "dialog.provider_config.label.tpm")
        loc_man.register(self.thinking_mode_group, "title", "dialog.provider_config.group.thinking_mode")
        loc_man.register(self.thinking_mode_label, "text", "dialog.provider_config.label.thinking_mode")
        loc_man.register(self.configure_params_btn, "text", "dialog.provider_config.button.configure_params")
        self.thinking_mode_combo.setItemText(0, translate("dialog.provider_config.thinking_mode.none"))
        self.thinking_mode_combo.setItemText(1, translate("dialog.provider_config.thinking_mode.auto"))
        self.thinking_mode_combo.setItemText(2, translate("dialog.provider_config.thinking_mode.by_commands"))
        self.thinking_mode_combo.setItemText(3, translate("dialog.provider_config.thinking_mode.by_header_body"))
        self.placeholder_text = translate("dialog.provider_config.placeholder.provider")
        current_provider_text = self.provider_combo.currentText()
        if self.provider_combo.itemText(0) != self.placeholder_text:
            current_idx = self.provider_combo.currentIndex()
            self.provider_combo.blockSignals(True)
            self.provider_combo.setItemText(0, self.placeholder_text)
            self.provider_combo.setCurrentIndex(current_idx)
            self.provider_combo.blockSignals(False)
        model_headers = [
        translate("dialog.provider_config.header.model_id"),
        translate("dialog.provider_config.header.limits")]
        self.models_table.setHorizontalHeaderLabels(model_headers)
        self._populate_models_table()
        self._on_provider_changed(current_provider_text, from_retranslate=True)

    def _connect_signals(self):
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.name_edit.textChanged.connect(self._validate_form)
        self.api_key_edit.textChanged.connect(self._validate_form)
        self.models_table.itemSelectionChanged.connect(self._on_model_selection_changed)
        self.add_model_btn.clicked.connect(self._add_new_model)
        self.remove_model_btn.clicked.connect(self._remove_selected_model)
        self.fetch_models_btn.clicked.connect(self.async_handler.fetch_models_and_info)
        self.available_models_combo.currentTextChanged.connect(
            self._on_available_model_selected
        )
        self.reset_model_settings_btn.clicked.connect(
            self._reset_current_model_settings
        )
        self.info_button.clicked.connect(self.async_handler.show_combined_model_info)
        self.thinking_mode_combo.currentIndexChanged.connect(
            self._on_thinking_mode_changed
        )
        self.thinking_mode_combo.currentIndexChanged.connect(
            self._save_current_model_data
        )
        self.configure_params_btn.clicked.connect(self._open_additional_params_dialog)
        self.model_id_edit.textChanged.connect(self._on_model_id_edited)
        self.model_id_edit.editingFinished.connect(self._commit_model_id_from_editor)
        self.start_tag_edit.editingFinished.connect(self._save_current_model_data)
        self.end_tag_edit.editingFinished.connect(self._save_current_model_data)
        self.enable_cmd_edit.editingFinished.connect(self._save_current_model_data)
        self.disable_cmd_edit.editingFinished.connect(self._save_current_model_data)
        self.use_global_limits_check.toggled.connect(self._save_current_model_data)
        self.rpm_edit.editingFinished.connect(self._save_current_model_data)
        self.rpd_edit.editingFinished.connect(self._save_current_model_data)
        self.tpm_edit.editingFinished.connect(self._save_current_model_data)
        self.timeout_edit.textChanged.connect(self._validate_form)

    def _on_thinking_mode_changed(self, index: int):
        mode = self.thinking_mode_combo.itemData(index)
        self.thinking_commands_group.setVisible(mode == "command")
        self.configure_params_btn.setVisible(mode == "header_body")

    def _open_additional_params_dialog(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return

        dialog = AdditionalParametersDialog(self.current_additional_params, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.current_additional_params = dialog.get_data()
            self._save_current_model_data()

    def _update_thinking_controls_visibility(self, mode_text=""):
        if not mode_text:
            mode_text = self.thinking_mode_combo.currentText()
        is_command_mode = translate("dialog.provider_config.mode.command") in mode_text
        self.thinking_commands_group.setVisible(is_command_mode)

    def _save_current_model_data(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return

        def get_int_or_none(widget: QtWidgets.QLineEdit):
            text = widget.text().strip()
            return int(text) if text.isdigit() else None

        current_model = self.configured_models[self.current_model_idx]
        current_model["parsing_rules"] = {
            "start_tag": self.start_tag_edit.text().strip(),
            "end_tag": self.end_tag_edit.text().strip(),
        }

        thinking_config = current_model.get("thinking_config", {})
        thinking_config["mode"] = self.thinking_mode_combo.currentData()
        thinking_config["enable_cmd"] = self.enable_cmd_edit.text().strip()
        thinking_config["disable_cmd"] = self.disable_cmd_edit.text().strip()
        current_model["thinking_config"] = thinking_config

        current_model["additional_params"] = self.current_additional_params
        logger.debug(
            f"Saving additional_params into model config '{current_model.get('model_id')}': {self.current_additional_params}"
        )
        use_global_limits = self.use_global_limits_check.isChecked()
        current_model["limits"] = {
            "use_global_limits": use_global_limits,
            "rpm": get_int_or_none(self.rpm_edit),
            "rpd": get_int_or_none(self.rpd_edit),
            "tpm": get_int_or_none(self.tpm_edit),
        }
        self.rpm_edit.setEnabled(not use_global_limits)
        self.rpd_edit.setEnabled(not use_global_limits)
        self.tpm_edit.setEnabled(not use_global_limits)
        full_model_id = current_model.get("model_id", "")
        clean_model_id = (
            full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id
        )
        self.models_table.item(self.current_model_idx, 0).setText(clean_model_id)
        limits_status = (
            translate("dialog.provider_config.limits_status_global")
            if use_global_limits
            else translate("dialog.provider_config.limits_status_custom")
        )
        self.models_table.item(self.current_model_idx, 1).setText(limits_status)
        self._validate_form()

    def _add_new_model(self):
        new_model = {
            "model_id": f"new-model-{len(self.configured_models) + 1}",
            "parsing_rules": {"start_tag": "", "end_tag": ""},
            "limits": {
                "use_global_limits": True,
                "rpm": None,
                "rpd": None,
                "tpm": None,
            },
            "thinking_config": {"mode": "none", "enable_cmd": "", "disable_cmd": ""},
            "additional_params": {
                "include_body_params": "",
                "exclude_body_params": "",
                "include_headers": "",
            },
        }
        self.configured_models.append(new_model)
        self._populate_models_table()
        self.models_table.selectRow(self.models_table.rowCount() - 1)
        self.model_id_edit.selectAll()
        self.model_id_edit.setFocus()

    def _remove_selected_model(self):
        if self.current_model_idx == -1:
            return
        model_id_to_remove = self.configured_models[self.current_model_idx].get(
            "model_id", "N/A"
        )
        title = translate("dialog.provider_config.prompt.remove_model_title")
        text = translate(
            "dialog.provider_config.prompt.remove_model_text",
            model_id_to_remove=model_id_to_remove,
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            title,
            text,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            del self.configured_models[self.current_model_idx]
            self.current_model_idx = -1
            self._populate_models_table()
            self._validate_form()
            if self.models_table.rowCount() > 0:
                self.models_table.selectRow(0)
            else:
                self._clear_editor_fields()
                self.model_editor_widget.setEnabled(False)

    def _reset_current_model_settings(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return
        model_config = self.configured_models[self.current_model_idx]
        model_id = model_config.get("model_id", "N/A")
        title = translate("dialog.provider_config.prompt.reset_model_title")
        text = translate(
            "dialog.provider_config.prompt.reset_model_text", model_id=model_id
        )
        reply = QtWidgets.QMessageBox.question(
            self,
            title,
            text,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            logger.debug(f"Resetting settings for model '{model_id}'.")
            model_config["limits"] = {
                "use_global_limits": True,
                "rpm": None,
                "rpd": None,
                "tpm": None,
            }
            model_config["parsing_rules"] = {"start_tag": "", "end_tag": ""}
            model_config["thinking_config"] = {
                "mode": "none",
                "enable_cmd": "",
                "disable_cmd": "",
            }
            model_config["additional_params"] = {
                "include_body_params": "",
                "exclude_body_params": "",
                "include_headers": "",
            }
            self._load_model_data_into_editor(model_config)
            self._save_current_model_data()

    def _initial_setup(self):
        self.thinking_mode_combo.blockSignals(True)
        self.thinking_mode_combo.addItem(
            translate("dialog.provider_config.thinking_mode.none"), "none"
        )
        self.thinking_mode_combo.addItem(
            translate("dialog.provider_config.thinking_mode.auto"), "auto"
        )
        self.thinking_mode_combo.addItem(
            translate("dialog.provider_config.thinking_mode.by_commands"), "command"
        )
        self.thinking_mode_combo.addItem(
            translate("dialog.provider_config.thinking_mode.by_header_body"),
            "header_body",
        )
        self.thinking_mode_combo.blockSignals(False)

        self._set_status_indicator(
            STATUS_INDICATOR_INACTIVE_COLOR,
            translate("dialog.provider_config.label.status_unknown"),
        )
        self.provider_combo.blockSignals(True)
        self.provider_combo.addItem(self.placeholder_text, "")

        def add_providers_to_combo(provider_list):
            for provider_id in sorted(
                provider_list, key=lambda p: settings.PROVIDER_DISPLAY_NAMES.get(p, p)
            ):
                display_name = settings.PROVIDER_DISPLAY_NAMES.get(
                    provider_id, provider_id
                )
                self.provider_combo.addItem(display_name, provider_id)

        add_providers_to_combo(settings.CLOUD_PROVIDERS)
        self.provider_combo.insertSeparator(self.provider_combo.count())
        add_providers_to_combo(settings.LOCAL_PROVIDERS)
        self.provider_combo.blockSignals(False)
        self.timeout_edit.setText(str(PROVIDER_DEFAULT_TIMEOUT))
        self.wait_for_response_check.setChecked(True)
        if self.is_edit_mode:
            self.name_edit.setText(self.existing_config.get("name", ""))
            provider_id_to_find = self.provider_to_edit
            index = self.provider_combo.findData(provider_id_to_find)
            if index != -1:
                self.provider_combo.setCurrentIndex(index)
            else:
                self.provider_combo.setCurrentText(provider_id_to_find)
            self.base_url_edit.setText(self.existing_config.get("base_url", ""))
            self.timeout_edit.setText(
                str(self.existing_config.get("timeout", PROVIDER_DEFAULT_TIMEOUT))
            )
            self.api_key_edit.setText(self.existing_config.get("api_key", ""))
            self.wait_for_response_check.setChecked(
                self.existing_config.get("wait_for_response", True)
            )
            global_limits = self.existing_config.get("global_limits", {})
            rpm_val = global_limits.get("rpm")
            self.global_rpm_edit.setText(str(rpm_val) if rpm_val is not None else "")
            rpd_val = global_limits.get("rpd")
            self.global_rpd_edit.setText(str(rpd_val) if rpd_val is not None else "")
            tpm_val = global_limits.get("tpm")
            self.global_tpm_edit.setText(str(tpm_val) if tpm_val is not None else "")
        else:
            self._on_provider_changed(self.provider_combo.currentText())
        self._populate_models_table()
        self._update_base_url_state()
        self._validate_form()
        if self.models_table.rowCount() > 0:
            self.models_table.selectRow(0)
        else:
            self.model_editor_widget.setEnabled(False)

    @QtCore.Slot(str)
    def _on_provider_changed(self, provider_name, from_retranslate=False):
        provider_id = self.provider_combo.currentData()
        if (
            self.is_edit_mode
            and provider_id != self.provider_to_edit
            and not from_retranslate
        ):
            title = translate(
                "dialog.provider_config.prompt.confirm_provider_change_title"
            )
            text = translate(
                "dialog.provider_config.prompt.confirm_provider_change_text"
            )
            reply = QtWidgets.QMessageBox.question(
                self,
                title,
                text,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                self.provider_combo.blockSignals(True)
                index = self.provider_combo.findData(self.provider_to_edit)
                if index != -1:
                    self.provider_combo.setCurrentIndex(index)
                self.provider_combo.blockSignals(False)
                return
            else:
                self.configured_models.clear()
                self.provider_to_edit = provider_id

        is_provider_selected = bool(provider_id)
        self.base_url_edit.setEnabled(is_provider_selected)
        self.api_key_edit.setEnabled(is_provider_selected)
        self.fetch_models_btn.setEnabled(is_provider_selected)
        if is_provider_selected:
            self.base_url_edit.setText(settings.PROVIDER_API_BASES.get(provider_id, ""))
            self.info_label.setText(
                translate(
                    "dialog.provider_config.info_label.provider_selected",
                    provider_name=provider_name,
                )
            )
        else:
            self.base_url_edit.clear()
            self.info_label.setText(
                translate("dialog.provider_config.info_label.begin")
            )

        self.fetched_models_cache = None
        self._populate_models_table()
        self._set_status_indicator(
            "⚪️", translate("dialog.provider_config.label.status_unknown")
        )
        self._update_base_url_state()
        self._validate_form()

    def _populate_models_table(self):
        self.models_table.blockSignals(True)
        self.models_table.setRowCount(0)
        self.models_table.setRowCount(len(self.configured_models))
        for i, model_data in enumerate(self.configured_models):
            full_model_id = model_data.get("model_id", "N/A")
            clean_model_id = (
                full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id
            )
            model_id_item = QtWidgets.QTableWidgetItem(clean_model_id)
            limits = model_data.get("limits", {})
            use_global = limits.get("use_global_limits", True)
            limits_status = (
                translate("dialog.provider_config.limits_status_global")
                if use_global
                else translate("dialog.provider_config.limits_status_custom")
            )
            limits_item = QtWidgets.QTableWidgetItem(limits_status)
            limits_item.setTextAlignment(QtCore.Qt.AlignCenter)
            tooltip_text = f"{translate('dialog.provider_config.limits_status_global')}: {translate('dialog.provider_config.tooltip.limits_profile')}\n{translate('dialog.provider_config.limits_status_custom')}: {translate('dialog.provider_config.tooltip.limits_custom')}"
            limits_item.setToolTip(tooltip_text)
            self.models_table.setItem(i, 0, model_id_item)
            self.models_table.setItem(i, 1, limits_item)
        self.models_table.blockSignals(False)
        self.remove_model_btn.setEnabled(self.models_table.rowCount() > 0)
        if self.models_table.rowCount() == 0:
            self._clear_editor_fields()
            self.model_editor_widget.setEnabled(False)

    @QtCore.Slot(str)
    def _on_available_model_selected(self, model_display_name):
        if not self.model_editor_widget.isEnabled() or not model_display_name:
            return
        full_model_id = self.available_models_combo.currentData()
        if not full_model_id:
            return
        if 0 <= self.current_model_idx < len(self.configured_models):
            self.configured_models[self.current_model_idx]["model_id"] = full_model_id
            self.model_id_edit.setText(model_display_name)
            self._save_current_model_data()

    def _on_model_selection_changed(self):
        selected_items = self.models_table.selectedItems()
        is_selection_present = bool(selected_items)
        self.model_editor_widget.setEnabled(is_selection_present)
        if is_selection_present:
            self.current_model_idx = self.models_table.row(selected_items[0])
            if 0 <= self.current_model_idx < len(self.configured_models):
                model_data = self.configured_models[self.current_model_idx]
                self._load_model_data_into_editor(model_data)
        else:
            self.current_model_idx = -1
            self._clear_editor_fields()

    def _load_model_data_into_editor(self, model_data):
        logger.debug(f"Loading data into editor. Full model_data: {model_data}")
        full_model_id = model_data.get("model_id", "")
        clean_model_id = (
            full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id
        )
        self.model_id_edit.setText(clean_model_id)
        parsing_rules = model_data.get("parsing_rules", {})
        self.start_tag_edit.setText(parsing_rules.get("start_tag", ""))
        self.end_tag_edit.setText(parsing_rules.get("end_tag", ""))
        thinking_config = model_data.get("thinking_config", {})

        self.thinking_mode_combo.blockSignals(True)
        mode = thinking_config.get("mode", "none")
        if self.thinking_mode_combo.findData(mode) == -1:
            logger.warning(
                f"Found unknown thinking mode '{mode}' in settings. Defaulting to 'none'."
            )
            mode = "none"
        index = self.thinking_mode_combo.findData(mode)
        self.thinking_mode_combo.setCurrentIndex(index)
        self.thinking_mode_combo.blockSignals(False)

        self._on_thinking_mode_changed(index)

        self.enable_cmd_edit.setText(thinking_config.get("enable_cmd", ""))
        self.disable_cmd_edit.setText(thinking_config.get("disable_cmd", ""))

        default_additional_params = {
            "include_body_params": "",
            "exclude_body_params": "",
            "include_headers": "",
        }
        loaded_params = model_data.get("additional_params") or {}
        default_additional_params.update(loaded_params)
        self.current_additional_params = default_additional_params

        limits = model_data.get("limits", {})
        use_global = limits.get("use_global_limits", True)
        self.use_global_limits_check.setChecked(use_global)
        rpm_val = limits.get("rpm")
        self.rpm_edit.setText(str(rpm_val) if rpm_val is not None else "")
        rpd_val = limits.get("rpd")
        self.rpd_edit.setText(str(rpd_val) if rpd_val is not None else "")
        tpm_val = limits.get("tpm")
        self.tpm_edit.setText(str(tpm_val) if tpm_val is not None else "")
        is_custom_limits = not use_global
        self.rpm_edit.setEnabled(is_custom_limits)
        self.rpd_edit.setEnabled(is_custom_limits)
        self.tpm_edit.setEnabled(is_custom_limits)

    def _clear_editor_fields(self):
        self.model_id_edit.clear()
        self.available_models_combo.clear()
        self.start_tag_edit.clear()
        self.end_tag_edit.clear()
        self.enable_cmd_edit.clear()
        self.disable_cmd_edit.clear()
        self.use_global_limits_check.setChecked(True)
        self.rpm_edit.clear()
        self.rpd_edit.clear()
        self.tpm_edit.clear()

    @QtCore.Slot(str)
    def _on_model_id_edited(self, model_name):
        self.available_models_combo.blockSignals(True)
        index = self.available_models_combo.findText(
            model_name, QtCore.Qt.MatchFixedString
        )
        if index != -1:
            self.available_models_combo.setCurrentIndex(index)
        else:
            self.available_models_combo.setCurrentIndex(-1)
        self.available_models_combo.blockSignals(False)

    def _commit_model_id_from_editor(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return
        entered_text = self.model_id_edit.text().strip()
        if not entered_text:
            return
        index = self.available_models_combo.findText(
            entered_text, QtCore.Qt.MatchFixedString
        )
        if index != -1:
            full_model_id = self.available_models_combo.itemData(index)
            self.configured_models[self.current_model_idx]["model_id"] = full_model_id
        else:
            self.configured_models[self.current_model_idx]["model_id"] = entered_text
        self._save_current_model_data()

    def _validate_form(self):
        is_valid = bool(
            self.name_edit.text().strip() and
            self.provider_combo.currentText() != self.placeholder_text and
            self.api_key_edit.text().strip() and
            self.configured_models)
        self.ok_button.setEnabled(is_valid)

    def _set_status_indicator(self, emoji, tooltip):
        self.status_indicator_icon.setText(emoji)
        self.status_indicator_label.setText(tooltip)

    def get_data(self):
        provider_id = self.provider_combo.currentData()
        if not provider_id:
            return None

        def get_int_or_none(widget: QtWidgets.QLineEdit):
            text = widget.text().strip()
            return int(text) if text.isdigit() else None

        connection_data = {
            "id": self.existing_config.get(
                "id",
                f"conn_{int(time.time())}_{random.randint(CONN_ID_RANDOM_RANGE_MIN, CONN_ID_RANDOM_RANGE_MAX)}",
            ),
            "name": self.name_edit.text().strip(),
            "provider": provider_id,
            "api_key": self.api_key_edit.text().strip(),
            "base_url": self.base_url_edit.text().strip(),
            "timeout": get_int_or_none(self.timeout_edit) or PROVIDER_DEFAULT_TIMEOUT,
            "wait_for_response": self.wait_for_response_check.isChecked(),
            "global_limits": {
                "rpm": get_int_or_none(self.global_rpm_edit),
                "rpd": get_int_or_none(self.global_rpd_edit),
                "tpm": get_int_or_none(self.global_tpm_edit),
            },
            "headers": settings.PROVIDER_CUSTOM_HEADERS.get(provider_id, {}),
            "configured_models": self.configured_models,
            "generation_params": self.existing_config.get(
                "generation_params", settings.get_default_generation_params()
            ),
        }
        logger.debug(f"ProviderConfigDialog.get_data() is returning: {connection_data}")
        return connection_data

class ManageLanguagesDialog(AnimatedDialog):
    def __init__(self, language_type="Target", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(MANAGE_LANG_DIALOG_MIN_WIDTH)
        flags = self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        self.language_type = language_type
        if self.language_type == "Target":
            self.config_key = "target_languages"
        else:
            self.config_key = "available_source_languages"
        self.languages = list(settings.current_settings.get(self.config_key, []))
        layout = QtWidgets.QVBoxLayout(self)
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.addItems(self.languages)
        layout.addWidget(self.list_widget)
        input_layout = QtWidgets.QHBoxLayout()
        self.lang_input = QtWidgets.QLineEdit()
        input_layout.addWidget(self.lang_input)
        self.add_button = QtWidgets.QPushButton()
        self.add_button.clicked.connect(self.add_language)
        input_layout.addWidget(self.add_button)
        layout.addLayout(input_layout)
        self.remove_button = QtWidgets.QPushButton()
        self.remove_button.clicked.connect(self.remove_language)
        layout.addWidget(self.remove_button)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        loc_man.register(
            self,
            "windowTitle",
            "dialog.manage_languages.title",
            language_type=self.language_type,
        )
        loc_man.register(
            self.lang_input,
            "placeholderText",
            "dialog.manage_languages.placeholder.enter_language",
        )
        loc_man.register(self.add_button, "text", "dialog.manage_languages.button.add")
        loc_man.register(
            self.remove_button, "text", "dialog.manage_languages.button.remove"
        )

    def _save_and_update_settings(self):
        settings.current_settings[self.config_key] = self.languages
        if self.language_type == "Target":
            selected_lang = settings.current_settings.get(
                "selected_target_language", ""
            )
            if self.languages and selected_lang not in self.languages:
                settings.current_settings["selected_target_language"] = self.languages[
                    0
                ]
            elif not self.languages:
                settings.current_settings["selected_target_language"] = ""
        else:
            selected_lang = settings.current_settings.get(
                "selected_source_language", ""
            )
            if self.languages and selected_lang not in self.languages:
                settings.current_settings["selected_source_language"] = self.languages[
                    0
                ]
        settings.save_settings()
        logger.info(
            f"{self.language_type} languages updated and saved: {self.languages}"
        )

    def add_language(self):
        lang_name = self.lang_input.text().strip()
        if lang_name and lang_name not in self.languages:
            self.languages.append(lang_name)
            self.languages.sort()
            self.list_widget.clear()
            self.list_widget.addItems(self.languages)
            self.lang_input.clear()
            self._save_and_update_settings()
        elif lang_name in self.languages:
            title = translate("dialog.manage_languages.error.duplicate.title")
            text = translate(
                "dialog.manage_languages.error.duplicate.text", lang_name=lang_name
            )
            QtWidgets.QMessageBox.information(self, title, text)
        elif not lang_name:
            title = translate("dialog.manage_languages.error.empty.title")
            text = translate("dialog.manage_languages.error.empty.text")
            QtWidgets.QMessageBox.warning(self, title, text)

    def remove_language(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        if (
            self.language_type == "Source"
            and len(self.languages) - len(selected_items) < 1
        ):
            title = translate("dialog.manage_languages.error.cannot_remove.title")
            text = translate("dialog.manage_languages.error.cannot_remove.text")
            QtWidgets.QMessageBox.warning(self, title, text)
            return
        for item in selected_items:
            lang_to_remove = item.text()
            if lang_to_remove in self.languages:
                self.languages.remove(lang_to_remove)
        self.list_widget.clear()
        self.list_widget.addItems(self.languages)
        self._save_and_update_settings()

    def accept(self):
        if self.lang_input.text().strip():
            self.add_language()
        super().accept()

class ModelInspectorDialog(AnimatedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_data = None
        self.setMinimumSize(
            MODEL_INSPECTOR_DIALOG_MIN_WIDTH, MODEL_INSPECTOR_DIALOG_MIN_HEIGHT
        )
        flags = self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        layout = QtWidgets.QVBoxLayout(self)
        top_info_layout = QtWidgets.QHBoxLayout()
        self.prompt_label = QtWidgets.QLabel()
        self.model_name_label = QtWidgets.QLabel()
        self.model_name_label.setStyleSheet("color: #aaa;")
        top_info_layout.addWidget(self.prompt_label)
        top_info_layout.addStretch()
        top_info_layout.addWidget(self.model_name_label)
        layout.addLayout(top_info_layout)
        self.prompt_text_edit = QtWidgets.QTextEdit()
        self.prompt_text_edit.setReadOnly(True)
        layout.addWidget(self.prompt_text_edit, stretch=2)
        self.tokens_group = QtWidgets.QGroupBox()
        tokens_layout = QtWidgets.QHBoxLayout(self.tokens_group)
        self.prompt_tokens_label = QtWidgets.QLabel()
        self.thinking_tokens_label = QtWidgets.QLabel()
        self.response_tokens_label = QtWidgets.QLabel()
        self.total_tokens_label = QtWidgets.QLabel()
        tokens_layout.addWidget(self.prompt_tokens_label)
        tokens_layout.addStretch()
        tokens_layout.addWidget(self.thinking_tokens_label)
        tokens_layout.addStretch()
        tokens_layout.addWidget(self.response_tokens_label)
        tokens_layout.addStretch()
        tokens_layout.addWidget(self.total_tokens_label)
        layout.addWidget(self.tokens_group)
        self.thinking_groupbox = QtWidgets.QGroupBox()
        self.thinking_groupbox.setVisible(False)
        thinking_layout = QtWidgets.QVBoxLayout(self.thinking_groupbox)
        self.thinking_text_edit = QtWidgets.QTextEdit()
        self.thinking_text_edit.setReadOnly(True)
        thinking_layout.addWidget(self.thinking_text_edit)
        layout.addWidget(self.thinking_groupbox, stretch=3)
        self.processed_translation_label = QtWidgets.QLabel()
        self.processed_translation_text_edit = QtWidgets.QTextEdit()
        self.processed_translation_text_edit.setReadOnly(True)
        layout.addWidget(self.processed_translation_label)
        layout.addWidget(self.processed_translation_text_edit, stretch=1)
        self.setModal(False)
        self.retranslate_ui()
        self.clear_data()
        loc_man.language_changed.connect(self.retranslate_ui)
        
    def retranslate_ui(self):
        loc_man.register(self, "windowTitle", "dialog.model_inspector.title")
        loc_man.register(self.prompt_label, "text", "dialog.model_inspector.label.last_prompt")
        loc_man.register(self.tokens_group, "title", "dialog.model_inspector.group.usage_metadata")
        loc_man.register(self.thinking_groupbox, "title", "dialog.model_inspector.group.thinking")
        loc_man.register(self.processed_translation_label, "text", "dialog.model_inspector.label.final_translation")
        if self._last_data:
            self.update_data(*self._last_data)
        else:
            self.clear_data()
            na = translate("dialog.model_inspector.label.na")
            loc_man.register(self.model_name_label, "text", "dialog.model_inspector.label.model_name", model=na)

    @QtCore.Slot(str, str, str, dict)
    def update_data(
        self, model_name, prompt, final_translation_text, thinking_text, usage_metadata
    ):
        self._last_data = (
            model_name,
            prompt,
            final_translation_text,
            thinking_text,
            usage_metadata,
        )
        na = translate("dialog.model_inspector.label.na")
        self.model_name_label.setText(
            translate("dialog.model_inspector.label.model_name", model=model_name or na)
        )
        self.prompt_text_edit.setPlainText(prompt)
        self.processed_translation_text_edit.setPlainText(final_translation_text)
        prompt_tokens = usage_metadata.get("prompt", na)
        thoughts_tokens = usage_metadata.get("thoughts", na)
        candidates_tokens = usage_metadata.get("candidates", na)
        total_tokens = usage_metadata.get("total", na)
        self.prompt_tokens_label.setText(
            translate(
                "dialog.model_inspector.label.prompt_tokens", tokens=prompt_tokens
            )
        )
        self.thinking_tokens_label.setText(
            translate(
                "dialog.model_inspector.label.thinking_tokens", tokens=thoughts_tokens
            )
        )
        self.response_tokens_label.setText(
            translate(
                "dialog.model_inspector.label.response_tokens", tokens=candidates_tokens
            )
        )
        self.total_tokens_label.setText(
            translate("dialog.model_inspector.label.total_tokens", tokens=total_tokens)
        )
        self.thinking_tokens_label.setVisible("thoughts" in usage_metadata)
        if thinking_text and settings.current_settings.get(
            "enable_model_thinking", True
        ):
            self.thinking_groupbox.setVisible(True)
            self.thinking_text_edit.setPlainText(thinking_text)
        else:
            self.thinking_groupbox.setVisible(False)
            self.thinking_text_edit.clear()

    def clear_data(self):
        self._last_data = None
        self.prompt_text_edit.clear()
        self.processed_translation_text_edit.clear()
        self.thinking_text_edit.clear()
        self.thinking_groupbox.setVisible(False)
        na = translate("dialog.model_inspector.label.na")
        self.model_name_label.setText(
            translate("dialog.model_inspector.label.model_name", model=na)
        )
        self.prompt_tokens_label.setText(
            translate("dialog.model_inspector.label.prompt_tokens", tokens=na)
        )
        self.thinking_tokens_label.setText(
            translate("dialog.model_inspector.label.thinking_tokens", tokens=na)
        )
        self.response_tokens_label.setText(
            translate("dialog.model_inspector.label.response_tokens", tokens=na)
        )
        self.total_tokens_label.setText(
            translate("dialog.model_inspector.label.total_tokens", tokens=na)
        )

    def closeEvent(self, event):
        self.hide()
        event.ignore()

class DonationDialog(AnimatedDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("dialog.donation.title"))
        self.setMinimumWidth(400)
        flags = self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags | QtCore.Qt.WindowStaysOnTopHint)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        icon_label = QtWidgets.QLabel("❤️")
        font = icon_label.font()
        font.setPointSize(24)
        icon_label.setFont(font)
        icon_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(icon_label)
        text_label = QtWidgets.QLabel(translate("dialog.donation.text"))
        text_label.setWordWrap(True)
        text_label.setTextFormat(QtCore.Qt.RichText)
        text_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(text_label)
        button_layout = QtWidgets.QHBoxLayout()
        support_button = QtWidgets.QPushButton(
            translate("dialog.donation.button_support")
        )
        support_button.clicked.connect(self._on_support)
        support_button.setStyleSheet(
            "background-color: #50fa7b; color: #282a36; font-weight: bold;"
        )
        later_button = QtWidgets.QPushButton(translate("dialog.donation.button_later"))
        later_button.clicked.connect(self.accept)
        button_layout.addWidget(later_button)
        button_layout.addWidget(support_button)
        layout.addLayout(button_layout)

    def _on_support(self):
        webbrowser.open("https://nerkun.donatik.ua/")
        self.accept()

class ProviderConfigAsyncHandler(QtCore.QObject):
    def __init__(self, dialog: "ProviderConfigDialog"):
        super().__init__(dialog)
        self.dialog = dialog
        self.thread = None
        self.worker = None

    def _start_worker(
        self, worker_class, on_finished_slot, on_error_slot, *worker_args
    ):
        self.thread = QtCore.QThread()
        self.worker = worker_class(*worker_args)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_finished_slot)
        self.worker.error.connect(on_error_slot)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def fetch_models_and_info(self):
        dialog = self.dialog
        api_key, base_url = (
            dialog.api_key_edit.text().strip(),
            dialog.base_url_edit.text().strip(),
        )
        if not api_key or not base_url:
            QtWidgets.QMessageBox.warning(
                dialog,
                translate("dialog.provider_config.warning.missing_info.title"),
                translate(
                    "dialog.provider_config.warning.missing_info.text_api_key_base_url"
                ),
            )
            return
        dialog.fetch_models_btn.setEnabled(False)
        dialog.info_button.setEnabled(False)
        dialog._set_status_indicator(
            STATUS_INDICATOR_FETCHING_COLOR,
            translate("dialog.provider_config.status.fetching_info"),
        )
        self._start_worker(
            FetchModelsWorker,
            self.on_fetch_models_finished,
            self.on_fetch_models_error,
            api_key,
            base_url,
        )

    def on_fetch_models_finished(self, models_data):
        dialog = self.dialog
        dialog.fetched_models_cache = models_data
        dialog.available_models_combo.blockSignals(True)
        dialog.available_models_combo.clear()

        def clean_model_id(full_id):
            return full_id.split("/")[-1] if "/" in full_id else full_id

        sorted_models = sorted(models_data, key=lambda m: clean_model_id(m.id))
        for model in sorted_models:
            display_name = clean_model_id(model.id)
            dialog.available_models_combo.addItem(display_name, model.id)
        user_entered_model_id = dialog.model_id_edit.text().strip()
        index = dialog.available_models_combo.findData(user_entered_model_id)
        if index != -1:
            dialog.available_models_combo.setCurrentIndex(index)
        dialog.available_models_combo.blockSignals(False)
        dialog._set_status_indicator(
            STATUS_INDICATOR_SUCCESS_COLOR,
            translate("dialog.provider_config.status.models_loaded"),
        )
        dialog.fetch_models_btn.setEnabled(True)
        dialog.info_button.setEnabled(True)

    def on_fetch_models_error(self, error_message):
        dialog = self.dialog
        dialog._set_status_indicator(
            STATUS_INDICATOR_FAIL_COLOR,
            translate("dialog.provider_config.status.fetch_failed"),
        )
        logger.error(f"Failed to fetch models: {error_message}", exc_info=True)
        text = translate(
            "dialog.provider_config.error.failed_to_fetch_models",
            error_message=error_message,
        )
        QtWidgets.QMessageBox.critical(
            dialog, translate("dialog.settings.fetch_models.error.generic_title"), text
        )
        dialog.fetch_models_btn.setEnabled(True)
        dialog.info_button.setEnabled(True)

    @wip_notification("dialog.wip.text.model_info")
    def show_combined_model_info(self):
        dialog = self.dialog
        if not (0 <= dialog.current_model_idx < len(dialog.configured_models)):
            QtWidgets.QMessageBox.warning(
                dialog,
                translate(
                    "dialog.provider_config.error.missing_info.no_model_selected"
                ),
                translate(
                    "dialog.provider_config.error.missing_info.no_model_selected"
                ),
            )
            return
        model_config = dialog.configured_models[dialog.current_model_idx]
        full_model_id = model_config.get("model_id", "").strip()
        provider_id = dialog.provider_combo.currentData()
        api_key, api_base = (
            dialog.api_key_edit.text().strip(),
            dialog.base_url_edit.text().strip(),
        )
        if not full_model_id or not provider_id:
            QtWidgets.QMessageBox.warning(
                dialog,
                translate(
                    "dialog.provider_config.error.missing_info.provider_and_model_id_required"
                ),
                translate(
                    "dialog.provider_config.error.missing_info.provider_and_model_id_required"
                ),
            )
            return
        is_cloud = (
            provider_id in settings.CLOUD_PROVIDERS
            or provider_id not in settings.LOCAL_PROVIDERS
        )
        if is_cloud and (not api_key or not api_base):
            QtWidgets.QMessageBox.warning(
                dialog,
                translate(
                    "dialog.provider_config.error.missing_info.api_key_and_base_url_required"
                ),
                translate(
                    "dialog.provider_config.error.missing_info.api_key_and_base_url_required"
                ),
            )
            return
        dialog.info_button.setEnabled(False)
        dialog.fetch_models_btn.setEnabled(False)
        dialog._set_status_indicator(
            STATUS_INDICATOR_FETCHING_COLOR,
            translate("dialog.provider_config.status.fetching_info"),
        )
        self._start_worker(
            ModelInfoWorker,
            self.on_model_info_finished,
            self.on_model_info_error,
            full_model_id,
            provider_id,
            api_key,
            api_base,
        )

    def on_model_info_finished(self, combined_info):
        dialog = self.dialog
        dialog._set_status_indicator(
            STATUS_INDICATOR_SUCCESS_COLOR,
            translate("dialog.provider_config.status.info_loaded"),
        )
        dialog.info_button.setEnabled(True)
        dialog.fetch_models_btn.setEnabled(True)
        pretty_response = json.dumps(combined_info, indent=4)
        result_dialog = QtWidgets.QDialog(dialog)
        title = translate(
            "dialog.provider_config.dialog.combined_info_title",
            model_id=dialog.model_id_edit.text().strip(),
        )
        result_dialog.setWindowTitle(title)
        result_dialog.setMinimumSize(
            COMBINED_INFO_DIALOG_MIN_WIDTH, COMBINED_INFO_DIALOG_MIN_HEIGHT
        )
        layout = QtWidgets.QVBoxLayout(result_dialog)
        text_edit = QtWidgets.QTextEdit(
            readOnly=True,
            plainText=pretty_response,
            lineWrapMode=QtWidgets.QTextEdit.NoWrap,
        )
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        button_box.accepted.connect(result_dialog.accept)
        layout.addWidget(text_edit)
        layout.addWidget(button_box)
        result_dialog.exec()

    def on_model_info_error(self, error_message):
        dialog = self.dialog
        dialog._set_status_indicator(
            STATUS_INDICATOR_FAIL_COLOR,
            translate("dialog.provider_config.status.info_fetch_failed"),
        )
        dialog.info_button.setEnabled(True)
        dialog.fetch_models_btn.setEnabled(True)
        logger.error(f"Failed to get model info: {error_message}", exc_info=True)
        text = translate(
            "dialog.provider_config.error.failed_to_get_model_info",
            error_message=error_message,
        )
        QtWidgets.QMessageBox.critical(
            dialog, translate("dialog.settings.fetch_models.error.generic_title"), text
        )

class ProgressDialog(AnimatedDialog):
    cancel_clicked = QtCore.Signal()

    def __init__(self, title: str, label_text: str, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(400)
        self.setWindowTitle(title)
        self.setModal(True)
        flags = self.windowFlags()
        flags &= ~QtCore.Qt.WindowContextHelpButtonHint
        flags |= QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel(label_text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m")
        layout.addWidget(self.progress_bar)
        self.cancel_button = QtWidgets.QPushButton()
        self.cancel_button.clicked.connect(self.cancel_clicked.emit)
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def set_label_text(self, text: str):
        self.label.setText(text)

    def set_button_text(self, text: str):
        self.cancel_button.setText(text)
        
    def set_maximum(self, value: int):
        self.progress_bar.setMaximum(value)

    def set_value(self, value: int):
        current_val = self.progress_bar.value()
        self.progress_bar.setFormat(f"{value} / {self.progress_bar.maximum()}")
        animation = QtCore.QPropertyAnimation(self.progress_bar, b"value", self)
        animation.setDuration(PROGRESS_ANIMATION_DURATION_MS)
        animation.setStartValue(current_val)
        animation.setEndValue(value)
        animation.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        
    def maximum(self) -> int:
        return self.progress_bar.maximum()

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.cancel_clicked.emit()
        event.ignore()

class AdditionalParametersDialog(AnimatedDialog):
    def __init__(self, params: dict[str, str], parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 500)
        flags = self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)

        main_layout = QtWidgets.QVBoxLayout(self)

        presets_layout = QtWidgets.QHBoxLayout()
        self.insert_presets_btn = QtWidgets.QPushButton()
        presets_layout.addWidget(self.insert_presets_btn)
        presets_layout.addStretch()
        main_layout.addLayout(presets_layout)

        self.include_body_group = QtWidgets.QGroupBox()
        include_body_layout = QtWidgets.QVBoxLayout(self.include_body_group)
        self.include_body_edit = QtWidgets.QTextEdit()
        self.include_body_edit.setPlainText(params.get("include_body_params", ""))
        include_body_layout.addWidget(self.include_body_edit)
        main_layout.addWidget(self.include_body_group)

        self.exclude_body_group = QtWidgets.QGroupBox()
        exclude_body_layout = QtWidgets.QVBoxLayout(self.exclude_body_group)
        self.exclude_body_edit = QtWidgets.QTextEdit()
        self.exclude_body_edit.setPlainText(params.get("exclude_body_params", ""))
        exclude_body_layout.addWidget(self.exclude_body_edit)
        main_layout.addWidget(self.exclude_body_group)

        self.include_headers_group = QtWidgets.QGroupBox()
        include_headers_layout = QtWidgets.QVBoxLayout(self.include_headers_group)
        self.include_headers_edit = QtWidgets.QTextEdit()
        self.include_headers_edit.setPlainText(params.get("include_headers", ""))
        include_headers_layout.addWidget(self.include_headers_edit)
        main_layout.addWidget(self.include_headers_group)

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        main_layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.insert_presets_btn.clicked.connect(self._insert_presets)

        self._setup_localizations()

    def _setup_localizations(self):
        loc_man.register(self, "windowTitle", "dialog.additional_params.title")
        loc_man.register(
            self.insert_presets_btn,
            "text",
            "dialog.additional_params.button.insert_presets",
        )
        loc_man.register(
            self.include_body_group,
            "title",
            "dialog.additional_params.group.include_body",
        )
        loc_man.register(
            self.include_body_edit,
            "placeholderText",
            "dialog.additional_params.placeholder.include_body",
        )
        loc_man.register(
            self.exclude_body_group,
            "title",
            "dialog.additional_params.group.exclude_body",
        )
        loc_man.register(
            self.exclude_body_edit,
            "placeholderText",
            "dialog.additional_params.placeholder.exclude_body",
        )
        loc_man.register(
            self.include_headers_group,
            "title",
            "dialog.additional_params.group.include_headers",
        )
        loc_man.register(
            self.include_headers_edit,
            "placeholderText",
            "dialog.additional_params.placeholder.include_headers",
        )

    def _insert_presets(self):
        header_preset = "X-Enable-Thinking: true"
        body_preset = "chat_template_kwargs:\n  thinking: true"

        self.include_headers_edit.setPlainText(header_preset)
        self.include_body_edit.setPlainText(body_preset)

    def get_data(self) -> dict[str, str]:
        return {
            "include_body_params": self.include_body_edit.toPlainText(),
            "exclude_body_params": self.exclude_body_edit.toPlainText(),
            "include_headers": self.include_headers_edit.toPlainText(),
        }