# main_tab_window.py
from PySide6.QtWidgets import QTabWidget
from tab_module.main_window import MainWindow
from tab_module.calculation_tab import CalculationTab

class MainTabWindow(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Processing Dashboard")
        self.resize(1200, 800)

        # Tab 1: Load Data (có DF1/DF2)
        self.load_tab = MainWindow()

        # Tab 2: Calculation
        self.calc_tab = CalculationTab()

        # Truyền tham chiếu của load_tab sang calc_tab
        self.calc_tab.set_main_window_ref(self.load_tab)

        # Thêm tab
        self.addTab(self.load_tab, "Load Data")
        self.addTab(self.calc_tab, "Calculation")
