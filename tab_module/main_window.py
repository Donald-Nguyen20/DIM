# main_window.py
import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QLabel, QFileDialog, QMessageBox, QGroupBox
)
from tab_module.main_window_modules.pandas_model import PandasModel
from tab_module.main_window_modules.data_utils import (
    POSITION_INDEXES, REQUIRED_COLS, double_col, interleave_cols, read_any
)
from tab_module.main_window_modules.plot_utils import draw_df
from tab_module.calculation_modules.startup_calculation import (
    compute_startup_table, compute_start_and_sync,
    build_startup_timeline_with_markers,build_startup_minutely_from_df_startup
)
from tab_module.calculation_modules.shutdown_calculation import (
    build_shutdown_minutely_from_t40,
)




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard S1 / S2 – Draw DF1/DF2")
        self.DF1 = pd.DataFrame()
        self.DF2 = pd.DataFrame()
        self.DF1_CT = pd.DataFrame()   # Sub-Contract S1
        self.DF2_CT = pd.DataFrame()   # Sub-Contract S2
        # >>> THÊM (giá trị khởi tạo)
        self.DF1_startup_timeline  = pd.DataFrame()
        self.DF2_startup_timeline  = pd.DataFrame()
        self.DF1_startup_minutely  = pd.DataFrame()
        self.DF2_startup_minutely  = pd.DataFrame()

        self.DF1_shutdown_timeline  = pd.DataFrame()
        self.DF2_shutdown_timeline  = pd.DataFrame()
        self.DF1_shutdown_minutely  = pd.DataFrame()
        self.DF2_shutdown_minutely  = pd.DataFrame()


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

        # ==== Chuẩn hoá sớm để sort/so sánh ổn định ====
        df["Tổ máy"] = df["Tổ máy"].astype(str).str.strip().str.upper()
        df["Case"]   = df["Case"].astype(str).str.strip()

        # === 1) SORT trước bằng cột thời gian TẠM (không đụng dữ liệu gốc) ===
        _ts_bd = pd.to_datetime(df["Thời điểm BĐTH"], errors="coerce", dayfirst=True)
        _ts_ht = pd.to_datetime(df["Thời điểm hoàn thành"], errors="coerce", dayfirst=True)
        df = df.assign(_ts_bd=_ts_bd, _ts_ht=_ts_ht).sort_values(
            by=["Tổ máy", "_ts_bd", "_ts_ht"],
            kind="mergesort"
        ).drop(columns=["_ts_bd", "_ts_ht"]).reset_index(drop=True)

        # === 2) XỬ LÝ ô trống (trước khi ép số) — giữ dữ liệu thô ===
        def _is_empty(s: pd.Series) -> pd.Series:
            return s.isna() | (s.astype(str).str.strip() == "")

        mask_empty_hoanthanh = _is_empty(df["CS hoàn thành (MW)"])
        mask_empty_ralenh    = _is_empty(df["CS ra lệnh (MW)"])

        # Rule PRE: Case != "Thay đổi công suất" & cả 2 MW trống -> fill 0
        mask_fill0 = (df["Case"].ne("Thay đổi công suất")) & mask_empty_hoanthanh & mask_empty_ralenh
        df.loc[mask_fill0, ["CS hoàn thành (MW)", "CS ra lệnh (MW)"]] = 0
        print(f"[PRE] Fill-0 (non-TĐCS & both MW empty): {int(mask_fill0.sum())} rows")

        # === 3) CỬA SỔ 5 DÒNG QUANH 'Khởi động lò' (dùng DF thô) ===
        def _get_startup_windows(dfi: pd.DataFrame, unit: str) -> pd.DataFrame:
            dfi_unit = dfi[dfi["Tổ máy"] == unit].reset_index(drop=True)
            idxs = dfi_unit.index[dfi_unit["Case"] == "Khởi động lò"].tolist()
            if not idxs:
                return dfi_unit.iloc[0:0].copy()
            keep = []
            for i in idxs:
                start = max(i - 1, 0)
                end   = min(i + 4, len(dfi_unit))  # i, i+1, i+2, i+3
                keep.extend(range(start, end))
            keep = sorted(set(keep))
            return dfi_unit.loc[keep].reset_index(drop=True)
        def _get_shutdown_windows(dfi: pd.DataFrame, unit: str) -> pd.DataFrame:
            """
            Lấy cửa sổ vài dòng quanh mốc 'Ngừng tổ máy' cho 1 tổ máy.
            Mặc định lấy i-2..i+3 (bạn đổi biên tuỳ ý).
            """
            import re
            dfi_unit = dfi[dfi["Tổ máy"] == unit].reset_index(drop=True)
            if "Case" not in dfi_unit.columns or dfi_unit.empty:
                return dfi_unit.iloc[0:0].copy()

            # Nhận nhiều biến thể tên gọi:
            pat = re.compile(r"ngừng tổ máy|dừng tổ máy|shutdown", re.IGNORECASE)
            idxs = dfi_unit.index[dfi_unit["Case"].astype(str).str.contains(pat, na=False)].tolist()
            if not idxs:
                return dfi_unit.iloc[0:0].copy()

            keep = []
            for i in idxs:
                start = max(i - 2, 0)
                end   = min(i + 4, len(dfi_unit))  # i, i+1, i+2, i+3
                keep.extend(range(start, end))
            keep = sorted(set(keep))
            return dfi_unit.loc[keep].reset_index(drop=True)
        def _first_shutdown_time(win: pd.DataFrame):
            """Lấy đúng thời điểm của hàng có 'Ngừng tổ máy' trong window:
            ưu tiên 'Thời điểm BĐTH', fallback 'Thời điểm hoàn thành'."""
            import re
            if win is None or win.empty or "Case" not in win.columns:
                return None
            pat = re.compile(r"ngừng tổ máy|dừng tổ máy|shutdown", re.IGNORECASE)
            m = win["Case"].astype(str).str.contains(pat, na=False)
            if not m.any():
                return None
            i = m.idxmax()  # hàng đầu tiên match trong window
            t = pd.to_datetime(win.loc[i, "Thời điểm BĐTH"], errors="coerce", dayfirst=True)
            if pd.isna(t):
                t = pd.to_datetime(win.loc[i, "Thời điểm hoàn thành"], errors="coerce", dayfirst=True)
            return None if pd.isna(t) else t


        # === 3b) CỬA SỔ quanh 'Ngừng tổ máy' ===
        self.DF1_SHUTDOWN = _get_shutdown_windows(df, "S1")
        self.DF2_SHUTDOWN = _get_shutdown_windows(df, "S2")
        print("\n=== Shutdown S1 (window quanh 'Ngừng tổ máy') ===")
        print(self.DF1_SHUTDOWN.head(10))
        print("\n=== Shutdown S2 (window quanh 'Ngừng tổ máy') ===")
        print(self.DF2_SHUTDOWN.head(10))


        self.DF1_STARTUP = _get_startup_windows(df, "S1")
        self.DF2_STARTUP = _get_startup_windows(df, "S2")
        print("\n=== Startup S1 (5 dòng quanh 'Khởi động lò') ===")
        print(self.DF1_STARTUP.head(10))
        print("\n=== Startup S2 (5 dòng quanh 'Khởi động lò') ===")
        print(self.DF2_STARTUP.head(10))
        # ===== SHUTDOWN: lấy mốc 'Ngừng tổ máy' làm t40 (bắt đầu profile 40%->0) =====
        t40_s1 = _first_shutdown_time(self.DF1_SHUTDOWN)
        t40_s2 = _first_shutdown_time(self.DF2_SHUTDOWN)
        print("\n=== SHUTDOWN Timestamps (mốc 'Ngừng tổ máy') ===")
        print("S1 t40:", t40_s1.strftime("%Y-%m-%d %H:%M:%S") if t40_s1 is not None else None)
        print("S2 t40:", t40_s2.strftime("%Y-%m-%d %H:%M:%S") if t40_s2 is not None else None)


        # === 4) Mốc BĐTH/Syn + timeline + summary (wrapper trọn gói) ===
        s1_mocs = compute_start_and_sync(self.DF1_STARTUP)
        s2_mocs = compute_start_and_sync(self.DF2_STARTUP)
        print("S1 mốc:", s1_mocs)
        print("S2 mốc:", s2_mocs)

        timeline_s1 = build_startup_timeline_with_markers(self.DF1_STARTUP, "S1")
        timeline_s2 = build_startup_timeline_with_markers(self.DF2_STARTUP, "S2")
        print("\n=== Timeline S1 ===\n", timeline_s1)
        print("\n=== Timeline S2 ===\n", timeline_s2)
        self.DF1_startup_timeline = timeline_s1
        self.DF2_startup_timeline = timeline_s2
        # >>> THÊM: chỉ quy ra phút
        tl1, s1_min = build_startup_minutely_from_df_startup(
            self.DF1_STARTUP, "S1",
            freq="T",
            include_edge_minutes=True,
            gap_policy="none"
        )
        tl2, s2_min = build_startup_minutely_from_df_startup(
            self.DF2_STARTUP, "S2",
            freq="T",
            include_edge_minutes=True,
            gap_policy="none"
        )

        self.DF1_startup_timeline = tl1
        self.DF2_startup_timeline = tl2
        self.DF1_startup_minutely = s1_min
        self.DF2_startup_minutely = s2_min

        print("\n=== STARTUP S1 MINUTELY (head) ===\n", self.DF1_startup_minutely.tail(100))
        print("\n=== STARTUP S2 MINUTELY (head) ===\n", self.DF2_startup_minutely.tail(100))


        summary = compute_startup_table(self.DF1_STARTUP, self.DF2_STARTUP)
        print("\n=== STARTUP SUMMARY ===\n", summary)

        # === 5) ÉP SỐ sau rule PRE ===
        for col in ["CS ra lệnh (MW)", "CS hoàn thành (MW)"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(4)

        # === 6) DROP TĐCS nếu 'CS hoàn thành (MW)' vẫn NaN ===
        mask_drop = df["Case"].eq("Thay đổi công suất") & df["CS hoàn thành (MW)"].isna()
        dropped = int(mask_drop.sum())
        df = df[~mask_drop].reset_index(drop=True)
        print(f"[POST] Dropped (TĐCS & CS hoàn thành NaN): {dropped} rows")

        # (Tuỳ chọn) re-sort nhẹ để đảm bảo thứ tự ổn định
        _ts_bd = pd.to_datetime(df["Thời điểm BĐTH"], errors="coerce", dayfirst=True)
        _ts_ht = pd.to_datetime(df["Thời điểm hoàn thành"], errors="coerce", dayfirst=True)
        df = df.assign(_ts_bd=_ts_bd, _ts_ht=_ts_ht).sort_values(
            by=["Tổ máy", "_ts_bd", "_ts_ht"], kind="mergesort"
        ).drop(columns=["_ts_bd", "_ts_ht"]).reset_index(drop=True)

        # === 7) Format thời gian để HIỂN THỊ ===
        for col in ["Thời điểm BĐTH", "Thời điểm hoàn thành"]:
            tmp_dt = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
            df[col] = tmp_dt.dt.strftime("%Y-%m-%d %H:%M:%S")

        # === 8) TÁCH S1/S2 & build DF1/DF2 cho nút Draw ===
        df_s1 = df[df["Tổ máy"] == "S1"].reset_index(drop=True)
        df_s2 = df[df["Tổ máy"] == "S2"].reset_index(drop=True)
        if len(df_s1) > 1:
            df_s1.loc[1:, "Thời điểm hoàn thành"] = "0"
        if len(df_s2) > 1:
            df_s2.loc[1:, "Thời điểm hoàn thành"] = "0"

        if t40_s1 is not None:
            sd1_tl, sd1_min = build_shutdown_minutely_from_t40(t40_s1, unit="S1", mw40=264.0)
            self.DF1_shutdown_timeline = sd1_tl
            self.DF1_shutdown_minutely = sd1_min
            print("\n=== SHUTDOWN S1 TIMELINE ===\n", sd1_tl)
            print("\n=== SHUTDOWN S1 MINUTELY (tail 100) ===\n", sd1_min.tail(100))
        else:
            self.DF1_shutdown_timeline = pd.DataFrame()
            self.DF1_shutdown_minutely = pd.DataFrame()
            print("\n[WARN] Không tìm thấy mốc 'Ngừng tổ máy' cho S1.")

        if t40_s2 is not None:
            sd2_tl, sd2_min = build_shutdown_minutely_from_t40(t40_s2, unit="S2", mw40=264.0)
            self.DF2_shutdown_timeline = sd2_tl
            self.DF2_shutdown_minutely = sd2_min
            print("\n=== SHUTDOWN S2 TIMELINE ===\n", sd2_tl)
            print("\n=== SHUTDOWN S2 MINUTELY (tail 100) ===\n", sd2_min.tail(100))
        else:
            self.DF2_shutdown_timeline = pd.DataFrame()
            self.DF2_shutdown_minutely = pd.DataFrame()
            print("\n[WARN] Không tìm thấy mốc 'Ngừng tổ máy' cho S2.")



        def make_df(dfi):
            mw = double_col(dfi, "CS hoàn thành (MW)")
            t  = interleave_cols(dfi, "Thời điểm BĐTH", "Thời điểm hoàn thành")

            if "Dừng lệnh" in dfi.columns:
                stop_start = dfi["Dừng lệnh"].where(dfi["Dừng lệnh"].notna(), None).reset_index(drop=True)
            else:
                stop_start = pd.Series([None] * len(dfi), dtype=object)

            stop_vals = stop_start.repeat(2).reset_index(drop=True)
            stop_vals.iloc[1::2] = None
            stop_vals = pd.concat([pd.Series([None], dtype=object), stop_vals], ignore_index=True)

            if {"Case BĐTH", "Case hoàn thành"}.issubset(set(dfi.columns)):
                case_series = interleave_cols(dfi, "Case BĐTH", "Case hoàn thành")
            elif "Case" in dfi.columns:
                case_start = dfi["Case"].astype(object).reset_index(drop=True)
                case_series = case_start.repeat(2).reset_index(drop=True)
                case_series.iloc[1::2] = None
            else:
                case_series = pd.Series([None] * (len(dfi) * 2), dtype=object)

            t  = t[1:].reset_index(drop=True)
            mw = mw[:-1].reset_index(drop=True)

            stop_vals = stop_vals.iloc[:len(t)].reset_index(drop=True)
            case_out  = case_series[1:].reset_index(drop=True)
            case_out  = case_out.iloc[:len(t)].reset_index(drop=True)

            return pd.DataFrame({
                "MW": mw,
                "Thời điểm": t,
                "Case": case_out,
                "Dừng lệnh": stop_vals
            })

        self.DF1 = make_df(df_s1)
        self.DF2 = make_df(df_s2)

        print("\n====== DF1 (S1) ======"); print(self.DF1)
        print("\n====== DF2 (S2) ======"); print(self.DF2)

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

            QMessageBox.information(
                self, "Import Sub-Contract",
                f"Đã import thành công:\nS1: {len(self.DF1_CT)} dòng\nS2: {len(self.DF2_CT)} dòng"
            )

        except Exception as e:
            QMessageBox.critical(self, "Lỗi import Sub-Contract", str(e))
            return
