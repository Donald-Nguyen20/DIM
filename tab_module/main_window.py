# main_window.py
import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QLabel, QFileDialog, QMessageBox, QGroupBox
)
from tab_module.main_window_modules.pandas_model import PandasModel
from tab_module.main_window_modules.data_utils import POSITION_INDEXES, REQUIRED_COLS, double_col, interleave_cols, read_any
from tab_module.main_window_modules.plot_utils import draw_df

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard S1 / S2 – Draw DF1/DF2")
        self.DF1 = pd.DataFrame()
        self.DF2 = pd.DataFrame()
        self.DF1_CT = pd.DataFrame()   # NEW: Sub-Contract S1
        self.DF2_CT = pd.DataFrame()   # NEW: Sub-Contract S2

        # Layout chính
        root = QWidget()
        root_layout = QVBoxLayout(root)

        # ===== Dòng top: Import file =====
        row_top = QHBoxLayout()
        self.btn_import = QPushButton("Import file…")
        self.btn_import.clicked.connect(self.import_file)
        row_top.addWidget(self.btn_import)

        # NEW: Nút Import Sub Ct
        self.btn_import_subct = QPushButton("Import Sub Ct")
        self.btn_import_subct.clicked.connect(self.import_sub_contract)
        row_top.addWidget(self.btn_import_subct)

        row_top.addStretch()
        root_layout.addLayout(row_top)

        # Nút vẽ
        btn_draw_df1 = QPushButton("Draw DF1")
        btn_draw_df1.clicked.connect(lambda: draw_df(self.DF1, "DF1 – S1", parent=self))
        btn_draw_df2 = QPushButton("Draw DF2")
        btn_draw_df2.clicked.connect(lambda: draw_df(self.DF2, "DF2 – S2", parent=self))
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_draw_df1)
        btn_row.addWidget(btn_draw_df2)
        root_layout.addLayout(btn_row)

        # Hai bảng
        self.view_s1 = QTableView()
        self.model_s1 = PandasModel()
        self.view_s1.setModel(self.model_s1)
        box_s1 = QGroupBox("Bảng gốc – Tổ máy = S1")
        lay_s1 = QVBoxLayout(box_s1)
        self.lbl_s1 = QLabel("0 dòng")
        lay_s1.addWidget(self.lbl_s1)
        lay_s1.addWidget(self.view_s1)

        self.view_s2 = QTableView()
        self.model_s2 = PandasModel()
        self.view_s2.setModel(self.model_s2)
        box_s2 = QGroupBox("Bảng gốc – Tổ máy = S2")
        lay_s2 = QVBoxLayout(box_s2)
        self.lbl_s2 = QLabel("0 dòng")
        lay_s2.addWidget(self.lbl_s2)
        lay_s2.addWidget(self.view_s2)

        row = QHBoxLayout()
        row.addWidget(box_s1)
        row.addWidget(box_s2)
        root_layout.addLayout(row)

        self.setCentralWidget(root)
        self.resize(1200, 700)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file dữ liệu", "",
            "Data files (*.xlsx *.xls *.xlsb *.csv);;All files (*.*)"
        )
        if not path:
            return
        try:
            df_raw = read_any(path)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc file", str(e))
            return

        if df_raw.shape[1] <= max(POSITION_INDEXES):
            QMessageBox.critical(self, "Thiếu cột", "File không đủ số cột yêu cầu.")
            return

        df = df_raw.iloc[:, POSITION_INDEXES].copy()
        df.columns = REQUIRED_COLS
        for col in ["Thời điểm BĐTH", "Thời điểm hoàn thành"]:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

        # Nếu có cả 2 mốc, sort theo BĐTH rồi đến Hoàn thành (NaT để cuối)
        df = df.sort_values(
            by=["Tổ máy", "Thời điểm BĐTH", "Thời điểm hoàn thành"],
            na_position="last",
            kind="mergesort"
        ).reset_index(drop=True)
        for col in ["CS ra lệnh (MW)", "CS hoàn thành (MW)"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(4)
        df = df.dropna(subset=["CS hoàn thành (MW)"]).reset_index(drop=True)

        for col in ["Thời điểm BĐTH", "Thời điểm hoàn thành"]:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")

        df["Tổ máy"] = df["Tổ máy"].astype(str).str.strip().str.upper()

        df_s1 = df[df["Tổ máy"] == "S1"].reset_index(drop=True)
        df_s2 = df[df["Tổ máy"] == "S2"].reset_index(drop=True)
        if len(df_s1) > 1:
            df_s1.loc[1:, "Thời điểm hoàn thành"] = "0"
        if len(df_s2) > 1:
            df_s2.loc[1:, "Thời điểm hoàn thành"] = "0"

        def make_df(dfi):
            # MW dạng bậc thang từ "CS hoàn thành (MW)"
            mw = double_col(dfi, "CS hoàn thành (MW)")

            # Chuỗi thời điểm interleave (BĐTH, Hoàn thành, ...)
            t = interleave_cols(dfi, "Thời điểm BĐTH", "Thời điểm hoàn thành")

            # --- Dừng lệnh theo BĐTH, hoàn thành = None, chèn None đầu ---
            if "Dừng lệnh" in dfi.columns:
                stop_start = dfi["Dừng lệnh"].where(dfi["Dừng lệnh"].notna(), None).reset_index(drop=True)
            else:
                stop_start = pd.Series([None] * len(dfi), dtype=object)

            # nhân đôi để khớp step, rồi đặt xen kẽ [flag, None, flag, None, ...]
            stop_vals = stop_start.repeat(2).reset_index(drop=True)
            stop_vals.iloc[1::2] = None

            # chèn None vào đầu (pandas >= 2.0 dùng concat thay append)
            stop_vals = pd.concat([pd.Series([None], dtype=object), stop_vals], ignore_index=True)

            # ======= XỬ LÝ CỘT CASE TƯƠNG TỰ CỘT THỜI ĐIỂM =======
            if {"Case BĐTH", "Case hoàn thành"}.issubset(set(dfi.columns)):
                case_series = interleave_cols(dfi, "Case BĐTH", "Case hoàn thành")
            elif "Case" in dfi.columns:
                case_start = dfi["Case"].astype(object).reset_index(drop=True)
                case_series = case_start.repeat(2).reset_index(drop=True)
                case_series.iloc[1::2] = None  # vị trí hoàn thành để None
            else:
                # không có thông tin Case
                case_series = pd.Series([None] * (len(dfi) * 2), dtype=object)

            # Căn hàng: bỏ phần tử đầu của thời điểm, bỏ phần tử cuối của MW
            t = t[1:].reset_index(drop=True)
            mw = mw[:-1].reset_index(drop=True)
            # >>> FIX: Ép lại "Thời điểm hoàn thành" của dòng đầu = dữ liệu gốc (không lệch giây)
            if len(t) > 0 and len(dfi) > 0:
                raw_end0 = dfi.iloc[0]["Thời điểm hoàn thành"]
                if pd.notna(raw_end0) and raw_end0 != "0":
                    t.iloc[0] = pd.to_datetime(raw_end0, errors="coerce", dayfirst=True)


            # Cắt/khớp độ dài stop_vals & case_series theo thời điểm
            stop_vals = stop_vals.iloc[:len(t)].reset_index(drop=True)
            case_out  = case_series[1:].reset_index(drop=True)  # bỏ phần tử đầu để song song với t
            case_out  = case_out.iloc[:len(t)].reset_index(drop=True)

            return pd.DataFrame({
                "MW": mw,
                "Thời điểm": t,
                "Case": case_out,
                "Dừng lệnh": stop_vals
            })

        self.DF1 = make_df(df_s1)
        self.DF2 = make_df(df_s2)

        print("\n====== DF1 (S1) ======")
        print(self.DF1)
        print("\n====== DF2 (S2) ======")
        print(self.DF2)

        self.model_s1.setDataFrame(df_s1)
        self.model_s2.setDataFrame(df_s2)
        self.lbl_s1.setText(f"{len(df_s1)} dòng, {len(df_s1.columns)} cột")
        self.lbl_s2.setText(f"{len(df_s2)} dòng, {len(df_s2.columns)} cột")
        self.view_s1.resizeColumnsToContents()
        self.view_s2.resizeColumnsToContents()

    # NEW: Import Sub-Contract (Sheet1=S1 → DF1_CT, Sheet2=S2 → DF2_CT)
    def import_sub_contract(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Sub-Contract", "",
            "Excel files (*.xlsx *.xls *.xlsb);;All files (*.*)"
        )
        if not path:
            return

        try:
            # Sheet1 (index 0) -> S1
            df1 = pd.read_excel(path, sheet_name=0, usecols=[0, 1])
            df1.columns = ["Time", "Output Power"]
            df1["Time"] = pd.to_datetime(df1["Time"], errors="coerce", dayfirst=True)
            df1["Output Power"] = pd.to_numeric(df1["Output Power"], errors="coerce")

            # Sheet2 (index 1) -> S2
            df2 = pd.read_excel(path, sheet_name=1, usecols=[0, 1])
            df2.columns = ["Time", "Output Power"]
            df2["Time"] = pd.to_datetime(df2["Time"], errors="coerce", dayfirst=True)
            df2["Output Power"] = pd.to_numeric(df2["Output Power"], errors="coerce")

            # Lưu vào thuộc tính
            self.DF1_CT = df1.dropna(subset=["Time", "Output Power"]).reset_index(drop=True)
            self.DF2_CT = df2.dropna(subset=["Time", "Output Power"]).reset_index(drop=True)

            # Log nhanh
            print("\n===== DF1_CT (S1 – Sub Ct) =====")
            print(self.DF1_CT.head())
            print("\n===== DF2_CT (S2 – Sub Ct) =====")
            print(self.DF2_CT.head())

            # (Tùy chọn) Hiển thị lên view riêng nếu anh có model/view cho Sub Ct
            # self.model_s1_ct.setDataFrame(self.DF1_CT)
            # self.model_s2_ct.setDataFrame(self.DF2_CT)
            # self.view_s1_ct.resizeColumnsToContents()
            # self.view_s2_ct.resizeColumnsToContents()

            # (Tùy chọn) Thông báo
            QMessageBox.information(self, "Import Sub-Contract",
                                    f"Đã import thành công:\nS1: {len(self.DF1_CT)} dòng\nS2: {len(self.DF2_CT)} dòng")

        except Exception as e:
            QMessageBox.critical(self, "Lỗi import Sub-Contract", str(e))
            return
