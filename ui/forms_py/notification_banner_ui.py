# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'notification_banner.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QWidget)

class Ui_NotificationBanner(object):
    def setupUi(self, NotificationBanner):
        if not NotificationBanner.objectName():
            NotificationBanner.setObjectName(u"NotificationBanner")
        NotificationBanner.resize(600, 50)
        NotificationBanner.setFrameShape(QFrame.NoFrame)
        NotificationBanner.setFrameShadow(QFrame.Raised)
        self.horizontalLayout = QHBoxLayout(NotificationBanner)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(15, 10, 15, 10)
        self.text_label = QLabel(NotificationBanner)
        self.text_label.setObjectName(u"text_label")

        self.horizontalLayout.addWidget(self.text_label)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.action_button = QPushButton(NotificationBanner)
        self.action_button.setObjectName(u"action_button")
        self.action_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.horizontalLayout.addWidget(self.action_button)

        self.close_button = QPushButton(NotificationBanner)
        self.close_button.setObjectName(u"close_button")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.close_button.sizePolicy().hasHeightForWidth())
        self.close_button.setSizePolicy(sizePolicy)
        self.close_button.setMinimumSize(QSize(20, 20))
        self.close_button.setMaximumSize(QSize(20, 20))
        self.close_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.horizontalLayout.addWidget(self.close_button)


        self.retranslateUi(NotificationBanner)

        QMetaObject.connectSlotsByName(NotificationBanner)
    # setupUi

    def retranslateUi(self, NotificationBanner):
        NotificationBanner.setWindowTitle(QCoreApplication.translate("NotificationBanner", u"Frame", None))
        self.text_label.setText(QCoreApplication.translate("NotificationBanner", u"Notification Text", None))
        self.action_button.setText(QCoreApplication.translate("NotificationBanner", u"Action", None))
        self.close_button.setText("")
        self.close_button.setObjectName(QCoreApplication.translate("NotificationBanner", u"close_button", None))
    # retranslateUi

