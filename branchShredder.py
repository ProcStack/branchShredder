
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from src.main import MainWindow


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Content areas (graph canvas, text editors, AI output) keep their own
    # explicit dark backgrounds and are not affected by these palette values.
    _p = QPalette()
    _p.setColor(QPalette.ColorRole.Window,          QColor("#404040"))  # panel / sidebar bg
    _p.setColor(QPalette.ColorRole.WindowText,      QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.Base,            QColor("#1e1e1e"))  # text-editor / list bg (kept dark)
    _p.setColor(QPalette.ColorRole.AlternateBase,   QColor("#353535"))
    _p.setColor(QPalette.ColorRole.ToolTipBase,     QColor("#363636"))
    _p.setColor(QPalette.ColorRole.ToolTipText,     QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.Text,            QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.Button,          QColor("#353535"))  # button / header bg
    _p.setColor(QPalette.ColorRole.ButtonText,      QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    _p.setColor(QPalette.ColorRole.Link,            QColor("#5c9fd8"))
    _p.setColor(QPalette.ColorRole.Highlight,       QColor("#2979cc"))
    _p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    _p.setColor(QPalette.ColorRole.Light,           QColor("#5e5e5e"))
    _p.setColor(QPalette.ColorRole.Midlight,        QColor("#545454"))
    _p.setColor(QPalette.ColorRole.Mid,             QColor("#4a4a4a"))
    _p.setColor(QPalette.ColorRole.Dark,            QColor("#2e2e2e"))
    _p.setColor(QPalette.ColorRole.Shadow,          QColor("#1a1a1a"))
    _p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#666666"))
    app.setPalette(_p)
    app.setStyleSheet("""
        QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 70);
            min-height: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(255, 255, 255, 130);
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
        }
        QScrollBar:horizontal {
            background: transparent;
            height: 6px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: rgba(255, 255, 255, 70);
            min-width: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:horizontal:hover {
            background: rgba(255, 255, 255, 130);
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: transparent;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
