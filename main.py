import sys

from PyQt6.QtWidgets import QApplication
from app.views.main_window import MainWindow
from pathlib import Path

def main():
    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    theme = "dark"

    theme_path = (
            Path(__file__).resolve().parent
            / "styles"
            / f"{theme}.qss"
    )

    app.setStyleSheet(
        theme_path.read_text(encoding="utf-8")
    )

    window = MainWindow()
    window.show()

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
