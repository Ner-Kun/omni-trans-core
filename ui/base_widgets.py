import logging
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
from .animations import UIAnimator
from .. import settings

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE_UI.base_widgets')

TOOLTIP_STYLE_SHEET = """
    HelpTooltip {
        background-color: #383842;
        border: 1px solid #555;
        border-radius: 4px;
        color: #e0e0e0;
        padding: 8px;
    }
"""
INFO_BUTTON_STYLE_SHEET = """
    QPushButton {
        background-color: transparent;
        border: 1px solid #888;
        color: #888;
        font-size: 11px;
        font-weight: bold;
        padding: 0px;
        border-radius: 9px;
    }
    QPushButton:hover {
        color: #50fa7b;
        border-color: #50fa7b;
    }
"""
INFO_BUTTON_FIXED_SIZE = 18

class ShakeLineEdit(QtWidgets.QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.animation = QtCore.QPropertyAnimation(self, b"pos")

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        validator = self.validator()
        if not validator:
            super().keyPressEvent(event)
            return
        if event.key() in (QtCore.Qt.Key.Key_Backspace, QtCore.Qt.Key.Key_Delete):
            super().keyPressEvent(event)
            return
        if not event.text() or event.modifiers() & (
            QtCore.Qt.KeyboardModifier.ControlModifier
            | QtCore.Qt.KeyboardModifier.AltModifier
        ):
            super().keyPressEvent(event)
            return
        future_text = (
            self.text()[: self.cursorPosition()]
            + event.text()
            + self.text()[self.cursorPosition() :]
        )
        assert validator is not None
        state, _, _ = validator.validate(future_text, 0)
        if (
            state == QtGui.QValidator.State.Acceptable
            or state == QtGui.QValidator.State.Intermediate
        ):
            super().keyPressEvent(event)
        else:
            self._shake()
            event.accept()

    def _shake(self):
        UIAnimator.shake_widget(self)

class FocusOutTextEdit(QtWidgets.QTextEdit):
    focus_out = QtCore.Signal()

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        self.focus_out.emit()
        super().focusOutEvent(event)

class FilterableTableWidget(QtWidgets.QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._searchable_columns = []
        self._original_data_map = {}

    def set_searchable_columns(self, columns: list[int]):
        self._searchable_columns = columns

    def set_row_hidden_data(self, row: int, data: str):
        self._original_data_map[row] = data.lower()

    @QtCore.Slot(str)
    def filter(self, search_term: str):
        term = search_term.lower().strip()
        for row in range(self.rowCount()):
            should_be_visible = False
            if not term:
                should_be_visible = True
            else:
                columns_to_search = self._searchable_columns or range(
                    self.columnCount()
                )
                for col in columns_to_search:
                    item = self.item(row, col)
                    if item and term in item.text().lower():
                        should_be_visible = True
                        break
                if not should_be_visible and row in self._original_data_map:
                    if term in self._original_data_map[row]:
                        should_be_visible = True
            self.setRowHidden(row, not should_be_visible)

class HelpTooltip(QtWidgets.QWidget):
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(TOOLTIP_STYLE_SHEET)
        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel()
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.label.setWordWrap(True)
        self.label.setOpenExternalLinks(True)
        self.label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(self.label)

    def closeEvent(self, event):
        logger.debug("HelpTooltip closed.")
        if HelpTooltip._instance is self:
            HelpTooltip._instance = None
        self.deleteLater()
        super().closeEvent(event)

    @staticmethod
    def show_text(pos: QtCore.QPoint, text: str, parent_for_filter: QtWidgets.QWidget):
        if HelpTooltip._instance:
            HelpTooltip._instance.close()
        tooltip = HelpTooltip(None)
        HelpTooltip._instance = tooltip
        tooltip.label.setText(text)
        tooltip.adjustSize()
        screen_geometry = parent_for_filter.screen().availableGeometry()
        if pos.x() + tooltip.width() > screen_geometry.right():
            pos.setX(screen_geometry.right() - tooltip.width())
        if pos.y() + tooltip.height() > screen_geometry.bottom():
            pos.setY(pos.y() - tooltip.height() - 30)
        tooltip.move(pos)
        tooltip.show()
        logger.debug("HelpTooltip shown.")

class InfoButton(QtWidgets.QPushButton):
    def __init__(self, help_text, parent=None):
        super().__init__("i", parent)
        self._help_text = help_text
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet(INFO_BUTTON_STYLE_SHEET)
        self.setFixedSize(INFO_BUTTON_FIXED_SIZE, INFO_BUTTON_FIXED_SIZE)
        self.clicked.connect(self._show_help)

    def setHelpText(self, text: str):
        self._help_text = text

    def _show_help(self):
        if self._help_text.startswith("http://") or self._help_text.startswith(
            "https://"
        ):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._help_text))
        else:
            point = self.mapToGlobal(self.rect().bottomLeft())
            point.setY(point.y() + 2)
            parent_window = self.window()
            HelpTooltip.show_text(point, self._help_text, parent_window)