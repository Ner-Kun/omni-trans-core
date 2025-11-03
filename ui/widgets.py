import logging
from PySide6 import QtWidgets, QtCore
from functools import wraps
from .. import settings
from .dialogs import ManageLanguagesDialog
from .base_widgets import FilterableTableWidget
from .animations import UIAnimator
from ..localization_manager import loc_man, translate
from ..utils import DebounceTimer, load_ui
from ..interfaces import IControlWidgetActions, TranslatableItem

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE_UI.widgets')

# GenerationParamsWidget
GEN_PARAMS_MAIN_SPACING = 10
GEN_PARAMS_NOTICE_COLOR = "#f1fa8c"
GEN_PARAMS_NOTICE_STYLE = "font-style: italic;"
GEN_PARAMS_NOTICE_LEFT_MARGIN = 15
GEN_PARAMS_THINKING_WIDGET_LEFT_MARGIN = 15
GEN_PARAMS_BUDGET_LABEL_MIN_WIDTH = 50
GEN_PARAMS_COMMON_SPACING = 10
SLIDER_TO_SPINBOX_FACTOR = 100.0
TEMP_SLIDER_RANGE = (0, 200)
TEMP_SPINBOX_RANGE = (0.0, 2.0)
PRECISION_SPINBOX_STEP = 0.01
TOP_P_SLIDER_RANGE = (0, 100)
TOP_P_SPINBOX_RANGE = (0.0, 1.0)
MAX_TOKENS_SPINBOX_RANGE = (0, 1_000_000)
MAX_TOKENS_SPINBOX_STEP = 64
PENALTY_SLIDER_RANGE = (-200, 200)
PENALTY_SPINBOX_RANGE = (-2.0, 2.0)
GEMINI_PRO_MAX_BUDGET = 32768
GEMINI_FLASH_MAX_BUDGET = 24576
GEMINI_BUDGET_STEP = 512

# TranslationControlWidget
EDIT_DEBOUNCE_INTERVAL_MS = 1000
EDITING_STATUS_FLASH_DURATION_MS = 800
EDITING_STATUS_FLASH_COLOR = "#f1fa8c"

class RPMStatusWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui("rpm_status_widget.ui", self, __file__)
        self._height_is_set = False
        self.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tableWidget.setRowCount(1)
        self.tableWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tableWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        loc_man.register(self, "toolTip", "widget.rpm_status.tooltip")
        self.update_status({"message": translate("widget.rpm_status.initializing"), "color": "#FFFFFF"})

    @QtCore.Slot(dict)
    def update_status(self, data: dict):
        if "message" in data:
            self.message_label.setText(data["message"])
            self.message_label.setStyleSheet(f"color: {data.get('color', '#FFFFFF')}; font-weight: bold;")
            self.stackedWidget.setCurrentWidget(self.message_page)
            return
        self.stackedWidget.setCurrentWidget(self.table_page)
        model_name = data.get("model_name", "N/A")
        self.model_name_label.setText(translate("widget.rpm_status.model_limits_header", model_name=model_name))
        limits = data.get("limits", [])
        rpm_data = None
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(1)
        if not limits:
            self.tableWidget.setColumnCount(0)
        else:
            self.tableWidget.setColumnCount(len(limits))
            headers = [limit.get('name', '') for limit in limits]
            self.tableWidget.setHorizontalHeaderLabels(headers)
            for i, limit in enumerate(limits):
                value_text = f"{limit.get('current', 0)} / {limit.get('total', 0)}"
                item = QtWidgets.QTableWidgetItem(value_text)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.tableWidget.setItem(0, i, item)
                if limit.get('name', '').upper() == 'RPM':
                    rpm_data = limit
        if not self._height_is_set and self.tableWidget.columnCount() > 0:
            header_height = self.tableWidget.horizontalHeader().height()
            row_height = self.tableWidget.rowHeight(0)
            total_height = header_height + row_height + self.tableWidget.frameWidth() * 2
            self.tableWidget.setMaximumHeight(total_height)
            self._height_is_set = True
        if rpm_data:
            current, total = rpm_data.get('current', 0), rpm_data.get('total', 1)
            self.progressBar.setRange(0, total)
            self.progressBar.setValue(current)
            usage_percent = (current / total) * 100 if total > 0 else 0
            self.progressBar.setFormat(f"{usage_percent:.0f}%")
            if usage_percent > 95: 
                color = "#ff5555"
            elif usage_percent > 75: 
                color = "#f1fa8c"
            else: 
                color = "#50fa7b"
            self.progressBar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid #555; border-radius: 4px; text-align: center;
                    background-color: #282a36; color: #f8f8f2; font-weight: bold;
                }}
                QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}
            """)
        else:
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.progressBar.setFormat(translate("widget.rpm_status.rpm_na"))
            self.progressBar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #555; border-radius: 4px; text-align: center;
                    background-color: #282a36; color: #f8f8f2; font-weight: bold;
                }
            """)

class GenerationParamsWidget(QtWidgets.QGroupBox):
    params_changed = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gemini_possible_budget_values = []
        load_ui("generation_params_widget.ui", self, __file__)
        self.thinking_budget_container.hide()
        self.retranslate_ui()
        self.connect_signals()
        loc_man.language_changed.connect(self.retranslate_ui)
        logger.debug("GenerationParamsWidget initialized")

    def _update_thinking_budget_visibility(self):
        is_gemini_active = self.thinking_stacked_widget.currentIndex() == 0
        is_thinking_enabled = self.enable_thinking_check.isChecked()
        should_show = is_gemini_active and is_thinking_enabled
        if self.thinking_budget_container.isVisible() != should_show:
            UIAnimator.toggle_visibility_animated_vertical(self.thinking_budget_container, show=should_show)

    def retranslate_ui(self):
        loc_man.register(self, "title", "widget.generation_params.title")
        loc_man.register(self.useContentContextCheck, "text", "widget.generation_params.use_content_context")
        loc_man.register(self.useContentContextCheck, "toolTip", "widget.generation_params.use_content_context.tooltip")
        loc_man.register(self.enable_thinking_check, "text", "widget.generation_params.enable_model_thinking")
        loc_man.register(self.enable_thinking_check, "toolTip", "widget.generation_params.enable_model_thinking.tooltip")
        loc_man.register(self.gemini_budget_slider, "toolTip", "widget.generation_params.thinking_budget.tooltip")
        loc_man.register(self.thinking_budget_label_for_layout, "text", "widget.generation_params.thinking_budget.label")
        loc_man.register(self.temperature_label, "text", "widget.generation_params.temperature.label")
        loc_man.register(self.top_p_label, "text", "widget.generation_params.top_p.label")
        loc_man.register(self.max_output_tokens_label, "text", "widget.generation_params.max_output_tokens.label")
        loc_man.register(self.max_tokens_spinbox, "toolTip", "widget.generation_params.max_output_tokens.tooltip")
        loc_man.register(self.frequency_penalty_label, "text", "widget.generation_params.frequency_penalty.label")
        loc_man.register(self.presence_penalty_label, "text", "widget.generation_params.presence_penalty.label")
        self._update_budget_label(self.gemini_budget_slider.value())
        if self.capability_notice_label.isVisible():
            self.show_capability_notice('thoughts_unsupported')

    def connect_signals(self):
        self.temp_slider.valueChanged.connect(lambda v: self.temp_spinbox.setValue(v / SLIDER_TO_SPINBOX_FACTOR))
        self.temp_spinbox.valueChanged.connect(lambda v: self.temp_slider.setValue(int(v * SLIDER_TO_SPINBOX_FACTOR)))
        self.top_p_slider.valueChanged.connect(lambda v: self.top_p_spinbox.setValue(v / SLIDER_TO_SPINBOX_FACTOR))
        self.top_p_spinbox.valueChanged.connect(lambda v: self.top_p_slider.setValue(int(v * SLIDER_TO_SPINBOX_FACTOR)))
        self.freq_penalty_slider.valueChanged.connect(lambda v: self.freq_penalty_spinbox.setValue(v / SLIDER_TO_SPINBOX_FACTOR))
        self.freq_penalty_spinbox.valueChanged.connect(lambda v: self.freq_penalty_slider.setValue(int(v * SLIDER_TO_SPINBOX_FACTOR)))
        self.pres_penalty_slider.valueChanged.connect(lambda v: self.pres_penalty_spinbox.setValue(v / SLIDER_TO_SPINBOX_FACTOR))
        self.pres_penalty_spinbox.valueChanged.connect(lambda v: self.pres_penalty_slider.setValue(int(v * SLIDER_TO_SPINBOX_FACTOR)))
        self.temp_slider.sliderReleased.connect(self._on_param_changed)
        self.top_p_slider.sliderReleased.connect(self._on_param_changed)
        self.freq_penalty_slider.sliderReleased.connect(self._on_param_changed)
        self.pres_penalty_slider.sliderReleased.connect(self._on_param_changed)
        self.useContentContextCheck.toggled.connect(self._on_param_changed)
        self.enable_thinking_check.toggled.connect(self._update_thinking_budget_visibility)
        self.enable_thinking_check.toggled.connect(self._on_param_changed)
        self.gemini_budget_slider.valueChanged.connect(self._update_budget_label)
        self.gemini_budget_slider.sliderReleased.connect(self._on_param_changed)
        self.temp_spinbox.editingFinished.connect(self._on_param_changed)
        self.top_p_spinbox.editingFinished.connect(self._on_param_changed)
        self.max_tokens_spinbox.editingFinished.connect(self._on_param_changed)
        self.freq_penalty_spinbox.editingFinished.connect(self._on_param_changed)
        self.pres_penalty_spinbox.editingFinished.connect(self._on_param_changed)

    def set_params(self, params: dict):
        self.blockSignals(True)
        defaults = settings.get_default_generation_params()
        self.useContentContextCheck.setChecked(params.get("use_content_as_context", defaults["use_content_as_context"]))
        is_thinking_enabled = params.get("enable_model_thinking", defaults["enable_model_thinking"])
        self.enable_thinking_check.setChecked(is_thinking_enabled)
        self.temp_spinbox.setValue(params.get("temperature", defaults["temperature"]))
        self.top_p_spinbox.setValue(params.get("top_p", defaults["top_p"]))
        self.max_tokens_spinbox.setValue(params.get("max_output_tokens", defaults["max_output_tokens"]))
        self.freq_penalty_spinbox.setValue(params.get("frequency_penalty", defaults["frequency_penalty"]))
        self.pres_penalty_spinbox.setValue(params.get("presence_penalty", defaults["presence_penalty"]))
        if self.thinking_stacked_widget.currentIndex() == 0:
            budget_value = params.get("thinking_budget_value", defaults["thinking_budget_value"])
            try:
                target_index = self.gemini_possible_budget_values.index(budget_value)
                self.gemini_budget_slider.setValue(target_index)
            except ValueError:
                self.gemini_budget_slider.setValue(0)
            self._update_budget_label(self.gemini_budget_slider.value())
        self.blockSignals(False)

    @QtCore.Slot()
    def _on_param_changed(self):
        params = {
            "use_content_as_context": self.useContentContextCheck.isChecked(),
            "enable_model_thinking": self.enable_thinking_check.isChecked(),
            "temperature": self.temp_spinbox.value(),
            "top_p": self.top_p_spinbox.value(),
            "max_output_tokens": self.max_tokens_spinbox.value(),
            "frequency_penalty": self.freq_penalty_spinbox.value(),
            "presence_penalty": self.pres_penalty_spinbox.value(),}
        if self.thinking_stacked_widget.currentIndex() == 0:
            current_index = self.gemini_budget_slider.value()
            if 0 <= current_index < len(self.gemini_possible_budget_values):
                params["thinking_budget_value"] = self.gemini_possible_budget_values[current_index]
            else:
                params["thinking_budget_value"] = -1
        else:
            params["thinking_budget_value"] = -1
        self.params_changed.emit(params)

    def _update_budget_label(self, value):
        if 0 <= value < len(self.gemini_possible_budget_values):
            budget = self.gemini_possible_budget_values[value]
            display_text = translate("widget.generation_params.thinking_budget.auto") if budget == -1 else str(budget)
            self.gemini_budget_label.setText(display_text)

    def _update_gemini_thinking_options(self, model_name: str, generation_params: dict):
        model_name_lower = model_name.lower()
        is_pro = "pro" in model_name_lower
        max_budget = GEMINI_PRO_MAX_BUDGET if is_pro else GEMINI_FLASH_MAX_BUDGET
        budget_range = range(GEMINI_BUDGET_STEP, max_budget + 1, GEMINI_BUDGET_STEP)
        self.gemini_possible_budget_values = [-1] + list(budget_range)
        self.gemini_budget_slider.blockSignals(True)
        self.gemini_budget_slider.setRange(0, len(self.gemini_possible_budget_values) - 1)
        self.gemini_budget_slider.blockSignals(False)
        if is_pro:
            self.enable_thinking_check.setChecked(True)
            self.enable_thinking_check.setEnabled(False)
        else:
            self.enable_thinking_check.setEnabled(True)
            self.enable_thinking_check.setChecked(generation_params.get("enable_model_thinking", True))
        self.set_params(generation_params)
        self._update_budget_label(self.gemini_budget_slider.value())

    def set_connection_type(self, connection_name: str, model_name: str = ""):
        self.blockSignals(True)
        self.capability_notice_label.hide()
        is_gemini = (connection_name == "Google Gemini")
        if is_gemini:
            logger.debug(f"Setting GenerationParams for Gemini (Model: {model_name})")
            self.thinking_stacked_widget.setCurrentIndex(0)
            params = settings.current_settings.get("gemini_generation_params", settings.get_default_generation_params())
            self._update_gemini_thinking_options(model_name, params)
        else:
            logger.debug(f"Setting GenerationParams for Custom Connection: {connection_name}")
            self.thinking_stacked_widget.setCurrentIndex(1)
            conn = next((c for c in settings.current_settings.get("custom_connections", []) if c.get("name") == connection_name), None)
            params = conn.get("generation_params", settings.get_default_generation_params()) if conn else settings.get_default_generation_params()
            self.enable_thinking_check.setEnabled(True)
            self.set_params(params)
        if is_gemini:
            self._update_budget_label(self.gemini_budget_slider.value())
        self.blockSignals(False)
        self._update_thinking_budget_visibility()
        self._on_param_changed()

    def show_capability_notice(self, capability: str):
        if capability == 'thoughts_unsupported':
            notice_text = translate("widget.generation_params.capability_notice.thoughts_unsupported")
            self.capability_notice_label.setText(notice_text)
            UIAnimator.toggle_visibility_animated_vertical(self.capability_notice_label, show=True, duration_ms=400)

class DataTableWidget(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns_config = []
        self._data = []
        self._unique_id_key = None
        self._id_to_row_map = {}
        self._row_to_id_map = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QtWidgets.QLineEdit()
        self.table = FilterableTableWidget()
        layout.addWidget(self.search_input)
        layout.addWidget(self.table)
        self.search_input.textChanged.connect(self.table.filter)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        loc_man.register(self.search_input, "placeholderText", "widget.searchable_table.search_placeholder")

    def configure(self, columns: list[dict]):
        self._columns_config = columns
        self.table.setColumnCount(len(columns))
        headers = [col.get('header', '') for col in columns]
        self.table.setHorizontalHeaderLabels(headers)
        header_view = self.table.horizontalHeader()
        for i, col_config in enumerate(columns):
            resize_mode = col_config.get('resize_mode', QtWidgets.QHeaderView.ResizeMode.Interactive)
            header_view.setSectionResizeMode(i, resize_mode)

    def set_data(self, data: list[dict], unique_id_key: str):
        self._data = data
        self._unique_id_key = unique_id_key
        self._id_to_row_map.clear()
        self._row_to_id_map.clear()
        self.table.setRowCount(0)
        if not data:
            return
        self.table.setRowCount(len(data))
        try:
            self.table.setUpdatesEnabled(False)
            for row_idx, row_data in enumerate(data):
                row_id = row_data.get(unique_id_key)
                if row_id is None:
                    continue
                self._id_to_row_map[row_id] = row_idx
                self._row_to_id_map[row_idx] = row_id
                full_search_text_parts = []
                for col_idx, col_config in enumerate(self._columns_config):
                    data_key = col_config.get('key')
                    if not data_key:
                        continue
                    cell_value = str(row_data.get(data_key, ''))
                    item = QtWidgets.QTableWidgetItem(cell_value)
                    self.table.setItem(row_idx, col_idx, item)
                    full_search_text_parts.append(cell_value)
                self.table.set_row_hidden_data(row_idx, " ".join(full_search_text_parts))
        finally:
            self.table.setUpdatesEnabled(True)

    def update_row_by_id(self, row_id, new_row_data: dict):
        row_idx = self._id_to_row_map.get(row_id)
        if row_idx is None:
            return
        self._data[row_idx].update(new_row_data)
        full_search_text_parts = []
        for col_idx, col_config in enumerate(self._columns_config):
            data_key = col_config.get('key')
            if not data_key:
                continue
            cell_value = str(self._data[row_idx].get(data_key, ''))
            item = self.table.item(row_idx, col_idx)
            if item:
                item.setText(cell_value)
            else:
                self.table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(cell_value))
            full_search_text_parts.append(cell_value)
        self.table.set_row_hidden_data(row_idx, " ".join(full_search_text_parts))

    def get_selected_rows_data(self) -> list[dict]:
        selected_rows_indices = {idx.row() for idx in self.table.selectedIndexes()}
        if not selected_rows_indices:
            return []
        selected_data = []
        for row_idx in sorted(list(selected_rows_indices)):
            row_id = self._row_to_id_map.get(row_idx)
            if row_id:
                selected_data.append(self._data[row_idx])
        return selected_data

    def flash_row_by_id(self, row_ids: str | list[str], color: str | None = None):
        if isinstance(row_ids, str):
            ids_to_process = [row_ids]
        else:
            ids_to_process = row_ids
        row_indices = []
        for row_id in ids_to_process:
            row_idx = self._id_to_row_map.get(row_id)
            if row_idx is not None:
                row_indices.append(row_idx)
        if not row_indices:
            return
        if color:
            UIAnimator.flash_table_row(self.table, row_indices, highlight_color_hex=color)
        else:
            UIAnimator.flash_table_row(self.table, row_indices)

    def scroll_to_row_by_id(self, row_id):
        row_idx = self._id_to_row_map.get(row_id)
        if row_idx is not None:
            item = self.table.item(row_idx, 0)
            if item:
                self.table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    @QtCore.Slot()
    def _on_selection_changed(self):
        selected_data = self.get_selected_rows_data()
        self.selection_changed.emit(selected_data)

class TranslationControlWidget(QtWidgets.QGroupBox):
    item_edited = QtCore.Signal(str, str)

    def __init__(self, actions_handler: IControlWidgetActions, parent=None):
        super().__init__(parent)
        self.actions_handler = actions_handler
        self.current_item_id = None
        self.current_translation_in_editor = None
        self.debounce_timer = DebounceTimer(self._apply_edited_translation, EDIT_DEBOUNCE_INTERVAL_MS, self)
        self._init_ui()
        self._connect_signals()
        self.retranslate_ui()
        loc_man.language_changed.connect(self.retranslate_ui)
        initial_lang = settings.current_settings.get("selected_target_language", "")
        self.set_active_language(initial_lang)

    def _init_ui(self):
        layout = QtWidgets.QFormLayout(self)
        orig_key_layout = QtWidgets.QHBoxLayout()
        orig_key_layout.setContentsMargins(0, 0, 0, 0)
        self.orig_label = QtWidgets.QLabel()
        self.orig_label.setWordWrap(True)
        orig_key_layout.addWidget(self.orig_label)
        orig_key_layout.addStretch(1)
        self.save_status_label = QtWidgets.QLabel()
        self.save_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        orig_key_layout.addWidget(self.save_status_label)
        self.original_text_label = QtWidgets.QLabel()
        layout.addRow(self.original_text_label, orig_key_layout)
        self.trans_edit = QtWidgets.QLineEdit()
        self.translation_label = QtWidgets.QLabel()
        layout.addRow(self.translation_label, self.trans_edit)
        action_buttons_layout = QtWidgets.QHBoxLayout()
        self.regenerate_btn = QtWidgets.QPushButton()
        translate_button_layout = QtWidgets.QHBoxLayout()
        translate_button_layout.setSpacing(0)
        translate_button_layout.setContentsMargins(0, 0, 0, 0)
        self.translate_selected_btn = QtWidgets.QPushButton()
        self.translate_selected_btn.setStyleSheet("border-top-right-radius: 0px; border-bottom-right-radius: 0px;")
        self.translate_all_btn = QtWidgets.QPushButton()
        self.translate_all_btn.setStyleSheet("border-top-left-radius: 0px; border-bottom-left-radius: 0px;")
        self.translate_all_btn.setFixedWidth(50)
        translate_button_layout.addWidget(self.translate_selected_btn)
        translate_button_layout.addWidget(self.translate_all_btn)
        delete_button_layout = QtWidgets.QHBoxLayout()
        delete_button_layout.setSpacing(0)
        delete_button_layout.setContentsMargins(0, 0, 0, 0)
        self.delete_selected_btn = QtWidgets.QPushButton()
        self.delete_selected_btn.setStyleSheet("border-top-right-radius: 0px; border-bottom-right-radius: 0px;")
        self.delete_all_btn = QtWidgets.QPushButton()
        self.delete_all_btn.setStyleSheet("border-top-left-radius: 0px; border-bottom-left-radius: 0px;")
        self.delete_all_btn.setFixedWidth(50)
        delete_button_layout.addWidget(self.delete_selected_btn)
        delete_button_layout.addWidget(self.delete_all_btn)
        action_buttons_layout.addWidget(self.regenerate_btn)
        action_buttons_layout.addStretch()
        action_buttons_layout.addLayout(translate_button_layout)
        action_buttons_layout.addStretch()
        action_buttons_layout.addLayout(delete_button_layout)
        layout.addRow(action_buttons_layout)
        self.clear_selection()
        self.translate_all_btn.setEnabled(False)
        self.delete_all_btn.setEnabled(False)

    def _require_items(requirement_type: str):
        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                items = []
                if requirement_type == 'selected':
                    items = self.actions_handler.get_selected_items()
                    if not items:
                        title = translate("widget.control.error.no_selection.title")
                        text = translate("widget.control.error.no_selection.text")
                        self.actions_handler.show_info_message(title, text)
                        return
                elif requirement_type == 'all':
                    items = self.actions_handler.get_all_items()
                    if not items:
                        title = translate("widget.control.error.no_data.title")
                        text = translate("widget.control.error.no_data.text")
                        self.actions_handler.show_info_message(title, text)
                        return
                return func(self, items, *args, **kwargs)
            return wrapper
        return decorator

    def retranslate_ui(self):
        loc_man.register(self, "title", "widget.control.group_title")
        loc_man.register(self.original_text_label, "text", "widget.control.original_label")
        loc_man.register(self.trans_edit, "placeholderText", "widget.control.edit_placeholder")
        loc_man.register(self.regenerate_btn, "text", "widget.control.button_regenerate")
        loc_man.register(self.translate_selected_btn, "text", "widget.control.button_translate_selected")
        loc_man.register(self.translate_selected_btn, "toolTip", "widget.control.button_translate_tooltip_selected")
        loc_man.register(self.translate_all_btn, "text", "widget.control.button_translate_all")
        loc_man.register(self.translate_all_btn, "toolTip", "widget.control.button_translate_tooltip_all")
        loc_man.register(self.delete_selected_btn, "text", "widget.control.button_delete_selected")
        loc_man.register(self.delete_selected_btn, "toolTip", "widget.control.button_delete_tooltip_selected")
        loc_man.register(self.delete_all_btn, "text", "widget.control.button_delete_all")
        loc_man.register(self.delete_all_btn, "toolTip", "widget.control.button_delete_tooltip_all")
        if self.current_item_id is None:
            self.save_status_label.setText(translate("widget.control.status_no_selection"))

    def _connect_signals(self):
        self.trans_edit.textChanged.connect(self._on_text_changed)
        self.trans_edit.editingFinished.connect(self.on_before_save)
        self.actions_handler.data_availability_changed.connect(self.translate_all_btn.setEnabled)
        self.actions_handler.data_availability_changed.connect(self.delete_all_btn.setEnabled)
        self.regenerate_btn.clicked.connect(self._on_regenerate)
        self.translate_selected_btn.clicked.connect(self._on_translate_selected)
        self.translate_all_btn.clicked.connect(self._on_translate_all)
        self.delete_selected_btn.clicked.connect(self._on_delete)
        self.delete_all_btn.clicked.connect(self._on_delete_all)

    def set_active_language(self, lang_name: str):
        if lang_name:
            self.translation_label.setText(translate("widget.control.translation_label_template", lang_name=lang_name))
        else:
            self.translation_label.setText(translate("widget.control.translation_label_default"))

    def block_all_signals(self, block: bool):
        self.trans_edit.blockSignals(block)
        self.regenerate_btn.blockSignals(block)
        self.translate_selected_btn.blockSignals(block)
        self.translate_all_btn.blockSignals(block)
        self.delete_selected_btn.blockSignals(block)
        self.delete_all_btn.blockSignals(block)

    def set_data(self, item_id: str, original_text: str, translated_text: str):
        self.debounce_timer.cancel()
        self.current_item_id = item_id
        self.current_translation_in_editor = translated_text
        self.block_all_signals(True)
        self.orig_label.setText(original_text)
        self.trans_edit.setText(translated_text)
        self.regenerate_btn.setEnabled(True)
        self.delete_selected_btn.setEnabled(True)
        self.translate_selected_btn.setEnabled(True)
        self.trans_edit.setEnabled(True)
        self.block_all_signals(False)
        UIAnimator.flash_status_label(self.save_status_label, translate("widget.control.status_saved"))

    def clear_selection(self):
        self.debounce_timer.cancel()
        self.current_item_id = None
        self.current_translation_in_editor = None
        self.block_all_signals(True)
        self.orig_label.clear()
        self.trans_edit.clear()
        self.regenerate_btn.setEnabled(False)
        self.delete_selected_btn.setEnabled(False)
        self.translate_selected_btn.setEnabled(False)
        self.trans_edit.setEnabled(False)
        self.save_status_label.setText(translate("widget.control.status_no_selection"))
        self.block_all_signals(False)

    def update_item_display(self, item_id: str, new_text: str):
        if self.current_item_id == item_id:
            self.trans_edit.blockSignals(True)
            self.trans_edit.setText(new_text)
            self.trans_edit.blockSignals(False)
            self.current_translation_in_editor = new_text
            UIAnimator.flash_status_label(self.save_status_label, translate("widget.control.status_saved"))

    @QtCore.Slot()
    def on_before_save(self):
        self.debounce_timer.force_run()
    
    @QtCore.Slot()
    def _on_text_changed(self):
        if self.current_item_id is not None:
            UIAnimator.flash_status_label(
                self.save_status_label,
                translate("widget.control.status_editing"),
                color=EDITING_STATUS_FLASH_COLOR,
                duration_ms=EDITING_STATUS_FLASH_DURATION_MS)
            self.debounce_timer.trigger()

    @QtCore.Slot()
    def _apply_edited_translation(self):
        if self.current_item_id is None:
            return
        new_text = self.trans_edit.text().strip()
        if new_text != self.current_translation_in_editor:
            self.current_translation_in_editor = new_text
            self.item_edited.emit(self.current_item_id, new_text)
            UIAnimator.flash_status_label(self.save_status_label, translate("widget.control.status_saved"))

    @QtCore.Slot()
    @_require_items('selected')
    def _on_translate_selected(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=False)

    @QtCore.Slot()
    @_require_items('all')
    def _on_translate_all(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=False)

    @QtCore.Slot()
    @_require_items('selected')
    def _on_regenerate(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=True)

    @QtCore.Slot()
    @_require_items('selected')
    def _on_delete(self, items: list[TranslatableItem]):
        self.actions_handler.handle_deletion_request(items)
        
    @QtCore.Slot()
    @_require_items('all')
    def _on_delete_all(self, items: list[TranslatableItem]):
        self.actions_handler.handle_deletion_request(items)

class _BaseLanguageWidget(QtWidgets.QGroupBox):
    language_changed = QtCore.Signal(str)
    def __init__(self, title_key: str, lang_type: str, parent=None):
        super().__init__(parent)
        if lang_type not in ["source", "target"]:
            raise ValueError("lang_type must be 'source' or 'target'")
        self.title_key = title_key
        self.lang_type = lang_type
        self.config_key = "available_source_languages" if lang_type == "source" else "target_languages"
        self.selected_lang_key = "selected_source_language" if lang_type == "source" else "selected_target_language"
        self.init_ui()
        self.retranslate_ui()
        self.connect_signals()
        self.update_language_combo()
        loc_man.language_changed.connect(self.retranslate_ui)

    def init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        self.combo = QtWidgets.QComboBox()
        self.manage_button = QtWidgets.QPushButton()
        layout.addWidget(self.combo)
        layout.addWidget(self.manage_button)

    def connect_signals(self):
        self.combo.currentTextChanged.connect(self._on_language_change)
        self.manage_button.clicked.connect(self._open_manage_dialog)

    def retranslate_ui(self):
        loc_man.register(self, "title", self.title_key)
        loc_man.register(self.manage_button, "text", "widget.language.manage_button")
        self.update_language_combo()

    def update_language_combo(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        languages = settings.current_settings.get(self.config_key, [])
        if languages:
            self.combo.addItems(languages)
            selected_lang = settings.current_settings.get(self.selected_lang_key, "")
            if selected_lang and selected_lang in languages:
                self.combo.setCurrentText(selected_lang)
            elif languages:
                self.combo.setCurrentIndex(0)
        else:
            placeholder_key = f"widget.language.no_languages_placeholder.{self.lang_type}"
            self.combo.setPlaceholderText(translate(placeholder_key))
            settings.current_settings[self.selected_lang_key] = ""
        self.combo.blockSignals(False)
        self._on_language_change(self.combo.currentText())

    @QtCore.Slot(str)
    def _on_language_change(self, lang_name: str):
        current_selection = settings.current_settings.get(self.selected_lang_key)
        if current_selection != lang_name:
            settings.current_settings[self.selected_lang_key] = lang_name
            settings.save_settings()
            logger.info(f"Selected {self.lang_type} language changed to: '{lang_name}'")
        self.language_changed.emit(lang_name)

    @QtCore.Slot()
    def _open_manage_dialog(self):
        dialog = ManageLanguagesDialog(self.lang_type.capitalize(), self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.update_language_combo()
            
class SourceLanguageWidget(_BaseLanguageWidget):
    def __init__(self, parent=None):
        super().__init__("widget.language.source_title", "source", parent)

class TargetLanguageWidget(_BaseLanguageWidget):
    def __init__(self, parent=None):
        super().__init__("widget.language.target_title", "target", parent)

class ConnectionSelectionWidget(QtWidgets.QGroupBox):
    connection_changed = QtCore.Signal(str)
    model_changed = QtCore.Signal(str, str)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        layout = QtWidgets.QHBoxLayout(self)
        self.connection_combo = QtWidgets.QComboBox()
        self.model_combo = QtWidgets.QComboBox()
        layout.addWidget(self.connection_combo, 2)
        layout.addWidget(self.model_combo, 3)
        self.connection_combo.currentTextChanged.connect(self._on_connection_changed)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        loc_man.register(self, "title", "widget.connection_selection.title")
        loc_man.register(self.connection_combo, "toolTip", "widget.connection_selection.connection_combo.tooltip")
        loc_man.register(self.model_combo, "toolTip", "widget.connection_selection.model_combo.tooltip")

    def update_connections(self):
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        all_connections = self.main_window.get_available_connection_names()
        if "Google Gemini" in all_connections:
            self.connection_combo.addItem("Google Gemini")
        custom_connections = [name for name in all_connections if name != "Google Gemini"]
        if custom_connections:
            self.connection_combo.insertSeparator(self.connection_combo.count())
            self.connection_combo.addItems(custom_connections)
        active_connection = self.main_window.get_active_connection_name()
        if self.connection_combo.findText(active_connection) != -1:
            self.connection_combo.setCurrentText(active_connection)
        elif self.connection_combo.count() > 0:
            self.connection_combo.setCurrentIndex(0)
        self.connection_combo.blockSignals(False)
        self._on_connection_changed(self.connection_combo.currentText())

    @QtCore.Slot(str)
    def _on_connection_changed(self, connection_name: str):
        if not connection_name:
            self.model_combo.clear()
            return
        self.main_window.set_active_connection_name(connection_name)
        self.connection_changed.emit(connection_name)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        last_used_model = settings.current_settings.get("active_model_for_connection", {}).get(connection_name)
        if connection_name == "Google Gemini":
            available_models = settings.current_settings.get("available_gemini_models", [])
            gemini_default = settings.current_settings.get("gemini_model")
            if available_models:
                self.model_combo.addItems(available_models)
            elif gemini_default and gemini_default not in available_models:
                self.model_combo.addItem(gemini_default)
            target_model = last_used_model or gemini_default
            if self.model_combo.findText(target_model) != -1:
                self.model_combo.setCurrentText(target_model)
        else:
            conn = next((c for c in settings.current_settings.get("custom_connections", []) if c.get("name") == connection_name), None)
            if conn:
                configured_models = conn.get("configured_models", [])
                if configured_models:
                    for model_config in configured_models:
                        full_model_id = model_config.get("model_id")
                        if full_model_id:
                            clean_name = full_model_id.split('/')[-1] if '/' in full_model_id else full_model_id
                            self.model_combo.addItem(clean_name, full_model_id)
                    if last_used_model:
                        index = self.model_combo.findData(last_used_model)
                        if index != -1:
                            self.model_combo.setCurrentIndex(index)
                        elif self.model_combo.count() > 0:
                            self.model_combo.setCurrentIndex(0)
                    elif self.model_combo.count() > 0:
                        self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)
        if self.model_combo.count() > 0:
            self._on_model_changed(self.model_combo.currentText())
        else:
            self.model_changed.emit(connection_name, "")

    @QtCore.Slot(str)
    def _on_model_changed(self, displayed_text: str):
        if not displayed_text:
            active_conn_name = self.connection_combo.currentText()
            self.model_changed.emit(active_conn_name, "")
            return
        active_conn_name = self.connection_combo.currentText()
        model_id_to_use = self.model_combo.currentData() or displayed_text
        if "active_model_for_connection" not in settings.current_settings:
            settings.current_settings["active_model_for_connection"] = {}
        settings.current_settings["active_model_for_connection"][active_conn_name] = model_id_to_use
        logger.debug(f"Active model for '{active_conn_name}' set to '{model_id_to_use}'.")
        self.model_changed.emit(active_conn_name, model_id_to_use)
        
class NotificationBanner(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui("notification_banner.ui", self, __file__)
        self._current_action = None
        close_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton)
        self.close_button.setIcon(close_icon)
        self.close_button.setToolTip(translate("widget.notification.close_button.tooltip"))
        self.close_button.clicked.connect(self.hide_banner)
        self.action_button.clicked.connect(self._on_action_clicked)
        self.action_button.clicked.connect(self.hide_banner)
        self.animation = UIAnimator.toggle_visibility_animated_vertical(self, False, duration_ms=300)
        self.hide()

    def show_banner(self, text: str, button_text: str, on_click_action, style: str = 'info'):
        if style == 'warning':
            bg_color = "#f1fa8c"
            text_color = "#282a36"
            btn_bg_color = "#e0e078"
            btn_hover_color = "#ffffa8"
            btn_text_color = "#282a36"
        else:
            bg_color = "#44689e"
            text_color = "#f8f8f2"
            btn_bg_color = "#6272a4"
            btn_hover_color = "#7d88b3"
            btn_text_color = "#f8f8f2"
        self.setStyleSheet(f"""
            NotificationBanner {{
                background-color: {bg_color};
                border-bottom: 1px solid #333;
            }}
            QLabel {{
                color: {text_color};
                font-size: 14px;
            }}
            QPushButton#action_button {{
                background-color: {btn_bg_color};
                color: {btn_text_color};
                border: 1px solid #777;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }}
            QPushButton#action_button:hover {{
                background-color: {btn_hover_color};
            }}
            QPushButton#close_button {{
                border: none;
                background: transparent;
                border-radius: 4px;
                padding: 0px;
            }}
            QPushButton#close_button:hover {{
                background-color: rgba(0, 0, 0, 0.15);
            }}
            QPushButton#close_button:pressed {{
                background-color: rgba(0, 0, 0, 0.2);
            }}
        """)
        
        self.text_label.setText(text)
        self.action_button.setText(button_text)
        self._current_action = on_click_action
        self.animation = UIAnimator.toggle_visibility_animated_vertical(self, True, duration_ms=400)

    def hide_banner(self):
        if self.isVisible():
            self.animation = UIAnimator.toggle_visibility_animated_vertical(self, False, duration_ms=300)

    def _on_action_clicked(self):
        if callable(self._current_action):
            self._current_action()