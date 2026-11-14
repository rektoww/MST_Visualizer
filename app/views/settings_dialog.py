from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog

from app.i18n import translate


class SettingsDialog(QDialog):
    def __init__(self, current_theme: str, current_language: str, parent=None) -> None:
        super().__init__(parent)

        ui_path = (
            Path(__file__).resolve().parents[2]
            / "ui"
            / "settings_dialog.ui"
        )

        uic.loadUi(str(ui_path), self)

        self.comboTheme.setCurrentIndex(
            1 if current_theme == "dark" else 0
        )

        self.comboLanguage.setCurrentIndex(
            1 if current_language == "en" else 0
        )

        self.btnApplySettings.clicked.connect(self.accept)
        self.btnCancelSettings.clicked.connect(self.reject)

        self.comboLanguage.currentIndexChanged.connect(
            lambda _: self.update_language(self.selected_language())
        )

        self.update_language(current_language)

    def selected_theme(self) -> str:
        return "dark" if self.comboTheme.currentIndex() == 1 else "light"

    def selected_language(self) -> str:
        return "en" if self.comboLanguage.currentIndex() == 1 else "ru"

    def update_language(self, language: str) -> None:
        self.setWindowTitle(translate("settings", language))

        self.lblTheme.setText(translate("theme", language))
        self.lblLanguage.setText(translate("language", language))

        self.comboTheme.setItemText(0, translate("light", language))
        self.comboTheme.setItemText(1, translate("dark", language))

        self.lblLanguageHint.setText(
            translate("language_hint", language)
        )

        self.btnApplySettings.setText(translate("apply", language))
        self.btnCancelSettings.setText(translate("cancel", language))

