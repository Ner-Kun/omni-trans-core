import logging
from .. import settings
from ..localization_manager import loc_man
from .. import constants as const
from PySide6 import QtWidgets, QtCore, QtGui

logger = logging.getLogger(f'{settings.LOG_PREFIX}_CORE_UI.animations')

class AnimatableLabel(QtWidgets.QLabel):
    def __init__(
        self,
        text,
        parent=None,
        min_size=const.WAVE_SPINNER_MIN_DOT_SIZE,
        color=const.WAVE_SPINNER_DEFAULT_COLOR,
    ):
        super().__init__(text, parent)
        self._font_size = min_size
        self._color = color
        self.update_stylesheet()

    @QtCore.Property(int)
    def font_size(self):
        return self._font_size

    @font_size.setter
    def font_size(self, size):
        self._font_size = size
        self.update_stylesheet()

    def update_stylesheet(self):
        self.setStyleSheet(f"color: {self._color}; font-size: {self._font_size}px;")

class UIAnimator:
    @staticmethod
    def shake_widget(
        widget: QtWidgets.QWidget,
        shake_amount: int = const.DEFAULT_SHAKE_AMOUNT,
        duration_ms: int = const.DEFAULT_SHAKE_DURATION_MS,
    ):
        existing_anim = widget.findChild(QtCore.QPropertyAnimation, "shake_anim")
        if (
            existing_anim
            and existing_anim.state() == QtCore.QAbstractAnimation.State.Running
        ):
            return
        pos = widget.pos()
        animation = QtCore.QPropertyAnimation(widget, b"pos", parent=widget)
        animation.setObjectName("shake_anim")
        animation.setDuration(duration_ms)
        animation.setLoopCount(2)
        animation.setKeyValueAt(0.0, pos)
        animation.setKeyValueAt(0.1, pos + QtCore.QPoint(shake_amount, 0))
        animation.setKeyValueAt(0.2, pos)
        animation.setKeyValueAt(0.3, pos + QtCore.QPoint(-shake_amount, 0))
        animation.setKeyValueAt(0.4, pos)
        animation.setKeyValueAt(0.5, pos + QtCore.QPoint(shake_amount, 0))
        animation.setKeyValueAt(0.6, pos)
        animation.setKeyValueAt(0.7, pos + QtCore.QPoint(-shake_amount, 0))
        animation.setKeyValueAt(0.8, pos)
        animation.setKeyValueAt(0.9, pos + QtCore.QPoint(shake_amount, 0))
        animation.setKeyValueAt(1.0, pos)
        animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def flash_status_label(
        label: QtWidgets.QLabel,
        text: str,
        color: str = const.FLASH_SUCCESS_COLOR,
        duration_ms: int = const.DEFAULT_FLASH_DURATION_MS,
    ):
        label.setText(text)
        label.setStyleSheet(f"color: {color};")
        effect = label.graphicsEffect()
        if not isinstance(effect, QtWidgets.QGraphicsOpacityEffect):
            effect = QtWidgets.QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(effect)
        old_anim = label.findChild(QtCore.QSequentialAnimationGroup)
        if old_anim:
            old_anim.stop()
            old_anim.deleteLater()
        seq_anim = QtCore.QSequentialAnimationGroup(label)
        anim_in = QtCore.QPropertyAnimation(effect, b"opacity")
        anim_in.setDuration(const.DEFAULT_VISIBILITY_TOGGLE_DURATION_MS)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)
        anim_out = QtCore.QPropertyAnimation(effect, b"opacity")
        anim_out.setDuration(500)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        seq_anim.addAnimation(anim_in)
        seq_anim.addPause(duration_ms)
        seq_anim.addAnimation(anim_out)
        seq_anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

    @staticmethod
    def flash_table_row(
        table: QtWidgets.QTableWidget,
        rows: int | list[int],
        highlight_color_hex: str = const.DEFAULT_TABLE_ROW_HIGHLIGHT_COLOR,
        duration_ms: int = const.DEFAULT_TABLE_ROW_FLASH_DURATION_MS,
    ):
        if isinstance(rows, int):
            rows_to_process = [rows]
        else:
            rows_to_process = rows
        valid_rows = {r for r in rows_to_process if 0 <= r < table.rowCount()}
        if not valid_rows:
            return
        selection_model = table.selectionModel()
        selected_rows = {index.row() for index in selection_model.selectedRows()}
        highlight_color = QtGui.QColor(highlight_color_hex)
        selection_color = QtGui.QColor(const.TABLE_SELECTION_COLOR_HEX)
        all_items_to_animate = []
        coord_to_start_color_map = {}
        for row in valid_rows:
            items_in_row = []
            is_row_selected = row in selected_rows
            start_color = (
                selection_color if is_row_selected else QtGui.QColor(0, 0, 0, 0)
            )
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    table.setItem(row, col, item)
                items_in_row.append(item)
                coord_to_start_color_map[(row, col)] = start_color
            if items_in_row:
                old_animation = items_in_row[0].data(
                    QtCore.Qt.ItemDataRole.UserRole + 1
                )
                if (
                    isinstance(old_animation, QtCore.QAbstractAnimation)
                    and old_animation.state() == QtCore.QAbstractAnimation.State.Running
                ):
                    old_animation.stop()
            all_items_to_animate.extend(items_in_row)
        if selected_rows:
            selection_model.blockSignals(True)
            selection_model.clear()
            non_flashing_selected_rows = selected_rows - valid_rows
            for r in non_flashing_selected_rows:
                for c in range(table.columnCount()):
                    if item := table.item(r, c):
                        item.setBackground(selection_color)
            for item in all_items_to_animate:
                start_color = coord_to_start_color_map.get((item.row(), item.column()))
                if start_color:
                    item.setBackground(start_color)
            selection_model.blockSignals(False)
        animation_group = QtCore.QParallelAnimationGroup(table)
        for item in all_items_to_animate:
            start_color = coord_to_start_color_map.get((item.row(), item.column()))
            if not start_color:
                continue
            sequential_anim = QtCore.QSequentialAnimationGroup(animation_group)
            fade_in_anim = QtCore.QVariantAnimation(sequential_anim)
            fade_in_anim.setDuration(duration_ms // 2)
            fade_in_anim.setStartValue(start_color)
            fade_in_anim.setEndValue(highlight_color)
            fade_in_anim.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
            fade_out_anim = QtCore.QVariantAnimation(sequential_anim)
            fade_out_anim.setDuration(duration_ms // 2)
            fade_out_anim.setStartValue(highlight_color)
            fade_out_anim.setEndValue(start_color)
            fade_out_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutQuad)
            sequential_anim.addAnimation(fade_in_anim)
            sequential_anim.addAnimation(fade_out_anim)

            def create_update_func(it):
                return lambda color: it.setBackground(QtGui.QBrush(color))

            update_func = create_update_func(item)
            fade_in_anim.valueChanged.connect(update_func)
            fade_out_anim.valueChanged.connect(update_func)
            animation_group.addAnimation(sequential_anim)

        def on_group_finished():
            if all_items_to_animate:
                all_items_to_animate[0].setData(QtCore.Qt.UserRole + 1, None)
            rows_we_touched = selected_rows | valid_rows
            for r in rows_we_touched:
                for c in range(table.columnCount()):
                    if item := table.item(r, c):
                        item.setBackground(QtGui.QBrush())
            if selected_rows:
                selection_model.blockSignals(True)
                selection_model.clear()
                for r in selected_rows:
                    selection_model.select(
                        table.model().index(r, 0),
                        QtCore.QItemSelectionModel.Select
                        | QtCore.QItemSelectionModel.Rows,
                    )
                selection_model.blockSignals(False)

        animation_group.finished.connect(on_group_finished)
        animation_group.start(QtCore.QAbstractAnimation.DeleteWhenStopped)
        if all_items_to_animate:
            all_items_to_animate[0].setData(QtCore.Qt.UserRole + 1, animation_group)

    @staticmethod
    def toggle_visibility_animated(
        widget: QtWidgets.QWidget,
        show: bool,
        duration_ms: int = const.DEFAULT_VISIBILITY_TOGGLE_DURATION_MS,
    ):
        anim = QtCore.QPropertyAnimation(widget, b"maximumWidth", parent=widget)
        anim.setDuration(duration_ms)
        if show:
            widget.show()
            target_width = widget.sizeHint().width()
            anim.setStartValue(0)
            anim.setEndValue(target_width)
        else:
            start_width = widget.width()
            anim.setStartValue(start_width)
            anim.setEndValue(0)
            anim.finished.connect(widget.hide)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def toggle_visibility_animated_vertical(
        widget: QtWidgets.QWidget,
        show: bool,
        duration_ms: int = const.DEFAULT_VISIBILITY_TOGGLE_DURATION_MS,
    ):
        anim = QtCore.QPropertyAnimation(widget, b"maximumHeight", parent=widget)
        anim.setDuration(duration_ms)
        if show:
            widget.show()
            target_height = widget.sizeHint().height()
            anim.setStartValue(0)
            anim.setEndValue(target_height)
        else:
            start_height = widget.height()
            anim.setStartValue(start_height)
            anim.setEndValue(0)
            anim.finished.connect(widget.hide)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        return anim

class WaveSpinner(QtWidgets.QWidget):
    def __init__(
        self,
        parent=None,
        dot_count=const.WAVE_SPINNER_DOT_COUNT,
        dot_color=const.WAVE_SPINNER_DEFAULT_COLOR,
    ):
        super().__init__(parent)
        self.dot_count = dot_count
        self.animations = []
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(const.WAVE_SPINNER_SPACING)
        dot_char = "●"
        min_size = const.WAVE_SPINNER_MIN_DOT_SIZE
        max_size = const.WAVE_SPINNER_MAX_DOT_SIZE
        for i in range(self.dot_count):
            label = AnimatableLabel(dot_char, self, min_size=min_size, color=dot_color)
            layout.addWidget(label)
            anim_forward = QtCore.QPropertyAnimation(label, b"font_size")
            anim_forward.setDuration(const.WAVE_SPINNER_ANIM_DURATION_MS)
            anim_forward.setStartValue(min_size)
            anim_forward.setEndValue(max_size)
            anim_forward.setEasingCurve(QtCore.QEasingCurve.Type.InOutCubic)
            anim_backward = QtCore.QPropertyAnimation(label, b"font_size")
            anim_backward.setDuration(const.WAVE_SPINNER_ANIM_DURATION_MS)
            anim_backward.setStartValue(max_size)
            anim_backward.setEndValue(min_size)
            anim_backward.setEasingCurve(QtCore.QEasingCurve.Type.InOutCubic)
            seq_group = QtCore.QSequentialAnimationGroup()
            seq_group.addAnimation(anim_forward)
            seq_group.addAnimation(anim_backward)
            parallel_group = QtCore.QParallelAnimationGroup(self)
            delay_anim = QtCore.QVariantAnimation()
            delay_anim.setDuration(i * const.WAVE_SPINNER_DELAY_STEP_MS)
            parallel_group.addAnimation(delay_anim)

    def start(self):
        for anim in self.animations:
            anim.setLoopCount(-1)
            anim.start()

    def stop(self):
        for anim in self.animations:
            anim.stop()
            
class LoadingOverlay(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(parent.size())
        self.background = QtWidgets.QWidget(self)
        self.background.setStyleSheet(
            f"background-color: {const.LOADING_OVERLAY_BG_COLOR}; border-radius: {const.LOADING_OVERLAY_BORDER_RADIUS};"
        )
        self.background.setGeometry(0, 0, self.width(), self.height())
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(const.LOADING_OVERLAY_SPACING)
        self.spinner = WaveSpinner(self)
        self.text_label = QtWidgets.QLabel(self)
        self.text_label.setStyleSheet(
            f"color: #e0e0e0; font-size: {const.LOADING_OVERLAY_FONT_SIZE_PX}px; font-weight: bold;"
        )
        self.text_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.spinner)
        layout.addWidget(self.text_label)
        self.setLayout(layout)
        loc_man.register(self.text_label, "text", "widget.loading_overlay.default_text")
        self.hide()

    def start_animation(self, text):
        self.text_label.setText(text)
        self.spinner.start()
        self.show()

    def stop_animation(self):
        self.spinner.stop()
        self.hide()

    def resizeEvent(self, event):
        self.setFixedSize(self.parent().size())
        self.background.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

class AnimatedDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, duration=const.DEFAULT_DIALOG_ANIM_DURATION_MS):
        super().__init__(parent)
        self._animation_duration = duration
        self.animation = None
        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        super().setVisible(False)

    def setVisible(self, visible):
        if visible:
            self.opacity_effect.setOpacity(0.0)
            super().setVisible(True)
            self.animation = QtCore.QPropertyAnimation(self.opacity_effect, b"opacity")
            self.animation.setDuration(self._animation_duration)
            self.animation.setStartValue(0.0)
            self.animation.setEndValue(1.0)
            self.animation.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
            self.animation.start(
                QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped
            )
        else:
            super().setVisible(False)