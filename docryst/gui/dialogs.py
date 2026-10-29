"""关于 / 版权 / 方法说明对话框（家族风格）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from docryst.gui.resources import resource_path
from docryst.i18n import tr
from docryst.version import (
    APP_CONTACT_EMAIL,
    APP_CONTACT_URL,
    APP_NAME,
    APP_TAGLINE,
    __version__,
)

# 版权要点常量（对话框恒以「中文 + 英文」双语并列展示，语言无关）
COPYRIGHT_BODY_ZH = (
    "<p>© 2026 PolyXRD Team。本软件采用<b>双许可</b>发布："
    "<b>学术许可</b>（仅限非商业学术研究与教学，免费）或向版权持有人另行申请的"
    "<b>商业许可</b>。学术许可下可自由使用、复制、修改与分发，"
    "<b>不允许任何商业用途</b>；商用前必须联系版权持有人取得书面商业授权。</p>"
)
COPYRIGHT_BODY_EN = (
    "<p>Copyright © 2026 PolyXRD Team. This software is released under a "
    "<b>dual license</b>: the free <b>Academic License</b> (non-commercial "
    "academic research and education only) or a separately obtained "
    "<b>Commercial License</b>. The Academic License permits use, copying, "
    "modification and distribution <b>for non-commercial purposes only</b>; "
    "commercial use requires a separate written Commercial License.</p>"
)
COPYRIGHT_NOTE = (
    "完整许可文本见随附 LICENSE 与 LICENSE-CN 文件 / "
    "See the accompanying LICENSE and LICENSE-CN files for the full text."
)


class AboutDialog(QDialog):
    """关于对话框：logo、版本、tagline、特性 chip、联系方式与版权。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.about.title"))
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignHCenter)

        logo_path = resource_path("logo-horizontal.png")
        if logo_path.exists():
            logo = QLabel(self)
            logo.setPixmap(QPixmap(str(logo_path)).scaledToWidth(
                340, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignHCenter)
            root.addWidget(logo)
        else:
            name = QLabel(APP_NAME, self)
            name.setStyleSheet("font-size:22px; font-weight:700; color:#0284C7;")
            name.setAlignment(Qt.AlignHCenter)
            root.addWidget(name)

        self.lbl_version = QLabel(self)
        self.lbl_version.setAlignment(Qt.AlignHCenter)
        self.lbl_version.setStyleSheet("color:#64748B; font-size:12px;")
        root.addWidget(self.lbl_version)

        tag = QLabel(APP_TAGLINE, self)
        tag.setAlignment(Qt.AlignHCenter)
        tag.setWordWrap(True)
        root.addWidget(tag)

        chips = QHBoxLayout()
        chips.setAlignment(Qt.AlignHCenter)
        for key in ("dialog.about.chip_1", "dialog.about.chip_2",
                    "dialog.about.chip_3"):
            chip = QLabel(tr(key), self)
            chip.setStyleSheet(
                "font-size:11px; color:#0E7490; background:#ECFEFF;"
                "border:1px solid #CFFAFE; border-radius:10px; padding:3px 10px;")
            chips.addWidget(chip)
        root.addLayout(chips)

        self._contact_label = QLabel(self)
        self._contact_label.setTextFormat(Qt.RichText)
        self._contact_label.setOpenExternalLinks(True)
        self._contact_label.setAlignment(Qt.AlignHCenter)
        self._contact_label.setWordWrap(True)
        root.addWidget(self._contact_label)

        copyright_lbl = QLabel("© 2026 PolyXRD Team", self)
        copyright_lbl.setAlignment(Qt.AlignHCenter)
        copyright_lbl.setStyleSheet("color:#64748B; font-size:12px;")
        root.addWidget(copyright_lbl)

        btn = QPushButton(tr("dialog.close"), self)
        btn.clicked.connect(self.accept)
        root.addWidget(btn, 0, Qt.AlignHCenter)
        self.retranslate()

    def retranslate(self) -> None:
        """语言切换后刷新文本。"""
        self.setWindowTitle(tr("dialog.about.title"))
        self.lbl_version.setText(tr("dialog.about.version", version=__version__))
        self._contact_label.setText(
            f"{tr('dialog.about.contact')}"
            f"<a href='mailto:{APP_CONTACT_EMAIL}'>{APP_CONTACT_EMAIL}</a> · "
            f"<a href='{APP_CONTACT_URL}'>github.com/PolyXRD</a>"
        )


class CopyrightDialog(QDialog):
    """版权与许可对话框：双语要点 + 联系方式（QTextBrowser 富文本）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.copyright.title"))
        self.resize(560, 480)
        root = QVBoxLayout(self)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        root.addWidget(self.browser)
        btn = QPushButton(tr("dialog.close"), self)
        btn.clicked.connect(self.accept)
        root.addWidget(btn, 0, Qt.AlignHCenter)
        self.retranslate()

    def retranslate(self) -> None:
        """语言切换后刷新标题与正文框架（要点正文恒为中英双语）。"""
        self.setWindowTitle(tr("dialog.copyright.title"))
        html = (
            f"<h3 style='color:#0F172A;'>{tr('dialog.copyright.heading')}</h3>"
            f"{COPYRIGHT_BODY_ZH}"
            f"{COPYRIGHT_BODY_EN}"
            f"<p style='color:#64748B;'>{COPYRIGHT_NOTE}</p>"
            f"<hr>"
            f"<p>{tr('dialog.about.contact')}"
            f"<a href='mailto:{APP_CONTACT_EMAIL}'>{APP_CONTACT_EMAIL}</a> · "
            f"<a href='{APP_CONTACT_URL}'>{APP_CONTACT_URL}</a></p>"
            f"<p style='color:#64748B;'>© 2026 PolyXRD Team</p>"
        )
        self.browser.setHtml(html)

    def toPlainText(self) -> str:
        """供冒烟测试断言关键内容。"""
        return self.browser.toPlainText()


class MethodDialog(QDialog):
    """方法说明：结晶度公式、非晶判据、背景口径与注意事项（三语正文）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.method.title"))
        self.resize(640, 520)
        root = QVBoxLayout(self)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(False)
        root.addWidget(self.browser)
        btn = QPushButton(tr("dialog.close"), self)
        btn.clicked.connect(self.accept)
        root.addWidget(btn, 0, Qt.AlignHCenter)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(tr("dialog.method.title"))
        paras = [
            "<h3 style='color:#0F172A;'>{title}</h3>".format(
                title=tr("dialog.method.h_formula")),
            tr("dialog.method.formula"),
            tr("dialog.method.p_formula"),
            "<h3 style='color:#0F172A;'>{title}</h3>".format(
                title=tr("dialog.method.h_criterion")),
            tr("dialog.method.p_criterion"),
            "<h3 style='color:#0F172A;'>{title}</h3>".format(
                title=tr("dialog.method.h_bg")),
            tr("dialog.method.p_bg"),
            "<h3 style='color:#0F172A;'>{title}</h3>".format(
                title=tr("dialog.method.h_steps")),
            tr("dialog.method.p_steps"),
            "<h3 style='color:#0F172A;'>{title}</h3>".format(
                title=tr("dialog.method.h_refs")),
            tr("dialog.method.p_refs"),
        ]
        self.browser.setHtml("".join(paras))
