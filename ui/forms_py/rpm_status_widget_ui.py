# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'rpm_status_widget.ui'
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
from PySide6.QtWidgets import (QApplication, QHeaderView, QLabel, QProgressBar,
    QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_RPMStatusWidget(object):
    def setupUi(self, RPMStatusWidget):
        if not RPMStatusWidget.objectName():
            RPMStatusWidget.setObjectName(u"RPMStatusWidget")
        RPMStatusWidget.resize(400, 122)
        self.main_layout = QVBoxLayout(RPMStatusWidget)
        self.main_layout.setObjectName(u"main_layout")
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.stackedWidget = QStackedWidget(RPMStatusWidget)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.message_page = QWidget()
        self.message_page.setObjectName(u"message_page")
        self.verticalLayout_2 = QVBoxLayout(self.message_page)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.message_label = QLabel(self.message_page)
        self.message_label.setObjectName(u"message_label")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.message_label.setFont(font)
        self.message_label.setAlignment(Qt.AlignCenter)

        self.verticalLayout_2.addWidget(self.message_label)

        self.stackedWidget.addWidget(self.message_page)
        self.table_page = QWidget()
        self.table_page.setObjectName(u"table_page")
        self.table_page_layout = QVBoxLayout(self.table_page)
        self.table_page_layout.setSpacing(0)
        self.table_page_layout.setObjectName(u"table_page_layout")
        self.table_page_layout.setContentsMargins(0, 0, 0, 0)
        self.model_name_label = QLabel(self.table_page)
        self.model_name_label.setObjectName(u"model_name_label")
        font1 = QFont()
        font1.setBold(True)
        self.model_name_label.setFont(font1)
        self.model_name_label.setAlignment(Qt.AlignCenter)

        self.table_page_layout.addWidget(self.model_name_label)

        self.tableWidget = QTableWidget(self.table_page)
        self.tableWidget.setObjectName(u"tableWidget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tableWidget.sizePolicy().hasHeightForWidth())
        self.tableWidget.setSizePolicy(sizePolicy)

        self.table_page_layout.addWidget(self.tableWidget)

        self.progressBar = QProgressBar(self.table_page)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setValue(0)
        self.progressBar.setAlignment(Qt.AlignCenter)

        self.table_page_layout.addWidget(self.progressBar)

        self.stackedWidget.addWidget(self.table_page)

        self.main_layout.addWidget(self.stackedWidget)


        self.retranslateUi(RPMStatusWidget)

        self.stackedWidget.setCurrentIndex(1)


        QMetaObject.connectSlotsByName(RPMStatusWidget)
    # setupUi

    def retranslateUi(self, RPMStatusWidget):
        RPMStatusWidget.setWindowTitle(QCoreApplication.translate("RPMStatusWidget", u"Form", None))
        self.message_label.setText(QCoreApplication.translate("RPMStatusWidget", u"Initializing...", None))
        self.model_name_label.setText(QCoreApplication.translate("RPMStatusWidget", u"Model Name - Limits", None))
        self.progressBar.setFormat(QCoreApplication.translate("RPMStatusWidget", u"%p%", None))
    # retranslateUi

