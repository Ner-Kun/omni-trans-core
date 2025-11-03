# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'generation_params_widget.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QSizePolicy, QSlider, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget)

class Ui_GenerationParamsWidget(object):
    def setupUi(self, GenerationParamsWidget):
        if not GenerationParamsWidget.objectName():
            GenerationParamsWidget.setObjectName(u"GenerationParamsWidget")
        GenerationParamsWidget.resize(478, 302)
        GenerationParamsWidget.setAlignment(Qt.AlignCenter)
        self.gridLayout = QGridLayout(GenerationParamsWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.useContentContextCheck = QCheckBox(GenerationParamsWidget)
        self.useContentContextCheck.setObjectName(u"useContentContextCheck")

        self.horizontalLayout_2.addWidget(self.useContentContextCheck)

        self.enable_thinking_check = QCheckBox(GenerationParamsWidget)
        self.enable_thinking_check.setObjectName(u"enable_thinking_check")

        self.horizontalLayout_2.addWidget(self.enable_thinking_check)


        self.gridLayout.addLayout(self.horizontalLayout_2, 0, 0, 1, 1)

        self.capability_notice_label = QLabel(GenerationParamsWidget)
        self.capability_notice_label.setObjectName(u"capability_notice_label")
        self.capability_notice_label.setStyleSheet(u"color: #f1fa8c; font-style: italic;")
        self.capability_notice_label.setWordWrap(True)
        self.capability_notice_label.setMargin(0)
        self.capability_notice_label.setIndent(15)

        self.gridLayout.addWidget(self.capability_notice_label, 1, 0, 1, 1)

        self.thinking_budget_container = QWidget(GenerationParamsWidget)
        self.thinking_budget_container.setObjectName(u"thinking_budget_container")
        self.horizontalLayout_3 = QHBoxLayout(self.thinking_budget_container)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.thinking_budget_label_for_layout = QLabel(self.thinking_budget_container)
        self.thinking_budget_label_for_layout.setObjectName(u"thinking_budget_label_for_layout")

        self.horizontalLayout_3.addWidget(self.thinking_budget_label_for_layout)

        self.thinking_stacked_widget = QStackedWidget(self.thinking_budget_container)
        self.thinking_stacked_widget.setObjectName(u"thinking_stacked_widget")
        self.gemini_widget = QWidget()
        self.gemini_widget.setObjectName(u"gemini_widget")
        self.gemini_budget_layout = QHBoxLayout(self.gemini_widget)
        self.gemini_budget_layout.setObjectName(u"gemini_budget_layout")
        self.gemini_budget_layout.setContentsMargins(0, 0, 0, 0)
        self.gemini_budget_slider = QSlider(self.gemini_widget)
        self.gemini_budget_slider.setObjectName(u"gemini_budget_slider")
        self.gemini_budget_slider.setOrientation(Qt.Horizontal)

        self.gemini_budget_layout.addWidget(self.gemini_budget_slider)

        self.gemini_budget_label = QLabel(self.gemini_widget)
        self.gemini_budget_label.setObjectName(u"gemini_budget_label")
        self.gemini_budget_label.setMinimumSize(QSize(50, 0))
        self.gemini_budget_label.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.gemini_budget_layout.addWidget(self.gemini_budget_label)

        self.thinking_stacked_widget.addWidget(self.gemini_widget)
        self.custom_widget = QWidget()
        self.custom_widget.setObjectName(u"custom_widget")
        self.thinking_stacked_widget.addWidget(self.custom_widget)

        self.horizontalLayout_3.addWidget(self.thinking_stacked_widget)


        self.gridLayout.addWidget(self.thinking_budget_container, 2, 0, 1, 1)

        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.max_output_tokens_label = QLabel(GenerationParamsWidget)
        self.max_output_tokens_label.setObjectName(u"max_output_tokens_label")

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.max_output_tokens_label)

        self.max_tokens_spinbox = QSpinBox(GenerationParamsWidget)
        self.max_tokens_spinbox.setObjectName(u"max_tokens_spinbox")
        self.max_tokens_spinbox.setMaximum(1000000)
        self.max_tokens_spinbox.setSingleStep(64)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.max_tokens_spinbox)


        self.verticalLayout_2.addLayout(self.formLayout)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.temperature_label = QLabel(GenerationParamsWidget)
        self.temperature_label.setObjectName(u"temperature_label")

        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.LabelRole, self.temperature_label)

        self.temp_layout = QHBoxLayout()
        self.temp_layout.setObjectName(u"temp_layout")
        self.temp_slider = QSlider(GenerationParamsWidget)
        self.temp_slider.setObjectName(u"temp_slider")
        self.temp_slider.setMaximum(200)
        self.temp_slider.setOrientation(Qt.Horizontal)

        self.temp_layout.addWidget(self.temp_slider)

        self.temp_spinbox = QDoubleSpinBox(GenerationParamsWidget)
        self.temp_spinbox.setObjectName(u"temp_spinbox")
        self.temp_spinbox.setDecimals(2)
        self.temp_spinbox.setMaximum(2.000000000000000)
        self.temp_spinbox.setSingleStep(0.010000000000000)

        self.temp_layout.addWidget(self.temp_spinbox)


        self.formLayout_2.setLayout(0, QFormLayout.ItemRole.FieldRole, self.temp_layout)


        self.horizontalLayout.addLayout(self.formLayout_2)

        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.top_p_label = QLabel(GenerationParamsWidget)
        self.top_p_label.setObjectName(u"top_p_label")

        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.LabelRole, self.top_p_label)

        self.top_p_layout = QHBoxLayout()
        self.top_p_layout.setObjectName(u"top_p_layout")
        self.top_p_slider = QSlider(GenerationParamsWidget)
        self.top_p_slider.setObjectName(u"top_p_slider")
        self.top_p_slider.setMaximum(100)
        self.top_p_slider.setOrientation(Qt.Horizontal)

        self.top_p_layout.addWidget(self.top_p_slider)

        self.top_p_spinbox = QDoubleSpinBox(GenerationParamsWidget)
        self.top_p_spinbox.setObjectName(u"top_p_spinbox")
        self.top_p_spinbox.setDecimals(2)
        self.top_p_spinbox.setMaximum(1.000000000000000)
        self.top_p_spinbox.setSingleStep(0.010000000000000)

        self.top_p_layout.addWidget(self.top_p_spinbox)


        self.formLayout_3.setLayout(0, QFormLayout.ItemRole.FieldRole, self.top_p_layout)


        self.horizontalLayout.addLayout(self.formLayout_3)


        self.verticalLayout_2.addLayout(self.horizontalLayout)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.freq_penalty_layout = QHBoxLayout()
        self.freq_penalty_layout.setObjectName(u"freq_penalty_layout")
        self.freq_penalty_slider = QSlider(GenerationParamsWidget)
        self.freq_penalty_slider.setObjectName(u"freq_penalty_slider")
        self.freq_penalty_slider.setMinimum(-200)
        self.freq_penalty_slider.setMaximum(200)
        self.freq_penalty_slider.setOrientation(Qt.Horizontal)

        self.freq_penalty_layout.addWidget(self.freq_penalty_slider)

        self.freq_penalty_spinbox = QDoubleSpinBox(GenerationParamsWidget)
        self.freq_penalty_spinbox.setObjectName(u"freq_penalty_spinbox")
        self.freq_penalty_spinbox.setDecimals(2)
        self.freq_penalty_spinbox.setMinimum(-2.000000000000000)
        self.freq_penalty_spinbox.setMaximum(2.000000000000000)
        self.freq_penalty_spinbox.setSingleStep(0.010000000000000)

        self.freq_penalty_layout.addWidget(self.freq_penalty_spinbox)


        self.formLayout_4.setLayout(0, QFormLayout.ItemRole.FieldRole, self.freq_penalty_layout)

        self.frequency_penalty_label = QLabel(GenerationParamsWidget)
        self.frequency_penalty_label.setObjectName(u"frequency_penalty_label")

        self.formLayout_4.setWidget(0, QFormLayout.ItemRole.LabelRole, self.frequency_penalty_label)


        self.verticalLayout.addLayout(self.formLayout_4)

        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName(u"formLayout_5")
        self.presence_penalty_label = QLabel(GenerationParamsWidget)
        self.presence_penalty_label.setObjectName(u"presence_penalty_label")

        self.formLayout_5.setWidget(0, QFormLayout.ItemRole.LabelRole, self.presence_penalty_label)

        self.pres_penalty_layout = QHBoxLayout()
        self.pres_penalty_layout.setObjectName(u"pres_penalty_layout")
        self.pres_penalty_slider = QSlider(GenerationParamsWidget)
        self.pres_penalty_slider.setObjectName(u"pres_penalty_slider")
        self.pres_penalty_slider.setMinimum(-200)
        self.pres_penalty_slider.setMaximum(200)
        self.pres_penalty_slider.setOrientation(Qt.Horizontal)

        self.pres_penalty_layout.addWidget(self.pres_penalty_slider)

        self.pres_penalty_spinbox = QDoubleSpinBox(GenerationParamsWidget)
        self.pres_penalty_spinbox.setObjectName(u"pres_penalty_spinbox")
        self.pres_penalty_spinbox.setDecimals(2)
        self.pres_penalty_spinbox.setMinimum(-2.000000000000000)
        self.pres_penalty_spinbox.setMaximum(2.000000000000000)
        self.pres_penalty_spinbox.setSingleStep(0.010000000000000)

        self.pres_penalty_layout.addWidget(self.pres_penalty_spinbox)


        self.formLayout_5.setLayout(0, QFormLayout.ItemRole.FieldRole, self.pres_penalty_layout)


        self.verticalLayout.addLayout(self.formLayout_5)


        self.verticalLayout_2.addLayout(self.verticalLayout)


        self.gridLayout.addLayout(self.verticalLayout_2, 3, 0, 1, 1)


        self.retranslateUi(GenerationParamsWidget)

        self.thinking_stacked_widget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(GenerationParamsWidget)
    # setupUi

    def retranslateUi(self, GenerationParamsWidget):
        GenerationParamsWidget.setWindowTitle(QCoreApplication.translate("GenerationParamsWidget", u"GroupBox", None))
        GenerationParamsWidget.setTitle(QCoreApplication.translate("GenerationParamsWidget", u"Generation Parameters", None))
        self.useContentContextCheck.setText(QCoreApplication.translate("GenerationParamsWidget", u"Use content as context", None))
        self.enable_thinking_check.setText(QCoreApplication.translate("GenerationParamsWidget", u"Enable Model Thinking", None))
        self.capability_notice_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Note: This model does not support 'thoughts'.", None))
        self.thinking_budget_label_for_layout.setText(QCoreApplication.translate("GenerationParamsWidget", u"Thinking Budget (tokens):", None))
        self.gemini_budget_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Auto", None))
        self.max_output_tokens_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Max Output Tokens:", None))
        self.temperature_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Temperature:", None))
        self.top_p_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Top-P:", None))
        self.frequency_penalty_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Frequency Pen:", None))
        self.presence_penalty_label.setText(QCoreApplication.translate("GenerationParamsWidget", u"Presence Pen.:", None))
    # retranslateUi

