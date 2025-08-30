# main.py
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
from main_tab_window import MainTabWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # ===== Tạo palette pastel olive =====
    palette = QPalette()

    pastel_olive = QColor("#A3B18A")  # olive pastel
    pastel_olive_light = QColor("#DAD7CD")  # olive sáng
    pastel_olive_dark = QColor("#588157")   # olive đậm
    matcha_dark = QColor("#344E41")   # matcha đậm

    palette.setColor(QPalette.Window, pastel_olive_light)
    palette.setColor(QPalette.WindowText, matcha_dark)
    palette.setColor(QPalette.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.AlternateBase, pastel_olive)
    palette.setColor(QPalette.ToolTipBase, pastel_olive_light)
    palette.setColor(QPalette.ToolTipText, matcha_dark)
    palette.setColor(QPalette.Text, matcha_dark)
    palette.setColor(QPalette.Button, pastel_olive)
    palette.setColor(QPalette.ButtonText, matcha_dark)
    palette.setColor(QPalette.Highlight, pastel_olive_dark)
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))

    app.setPalette(palette)

    # ===== Thêm QSS tinh chỉnh =====
    app.setStyleSheet("""
        QWidget {
            font-size: 14px;
        }
        QPushButton {
            background-color: #A3B18A;
            color: #344E41;
            border-radius: 6px;
            padding: 5px 10px;
        }
        QPushButton:hover {
            background-color: #B5C99A;
        }
        QTabWidget::pane {
            border: 1px solid #A3B18A;
        }
        QHeaderView::section {
            background-color: #A3B18A;
            color: #344E41;
            padding: 4px;
            border: 1px solid #B5C99A;
        }
                      QTabBar::tab {
    background: #DAD7CD;   /* tab chưa chọn */
    color: #344E41;
    padding: 8px 16px;
    border: 1px solid #A3B18A;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #8B5E3C;   /* tab chọn: cacao/socola nhạt */
    color: white;
    font-weight: bold;
}

QTabBar::tab:hover {
    background: #B5C99A;   /* hover olive nhạt để cân bằng */
}

    """)

    w = MainTabWindow()
    w.resize(1500, 800)
    w.show()
    sys.exit(app.exec())
