# calculation_tab.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox,
    QHBoxLayout, QFileDialog, QTableView
)
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt
import pandas as pd
from PySide6.QtGui import QColor
from tab_module.calculation_modules.ppa_calculation import build_ppa_per_pair
from tab_module.calculation_modules.epc_calculation import build_epc_per_pair  # EPC 429/429
from tab_module.calculation_modules.plot_ppa import draw_ppa_df  # hỗ trợ tuple (segments, summary)
from tab_module.calculation_modules.ppa_minutely import ppa_segments_to_minutely
# export phút + giờ trong 1 sheet
from tab_module.calculation_modules.export_utils import (
    export_ppa_minutely_and_hourly_to_excel,
    minutely_to_hourly_avg,   # <<< dùng để tính hourly cho dashboard
)

class CalculationTab(QWidget):
    def __init__(self, main_window_ref=None):
        super().__init__()
        self.main_window_ref = main_window_ref
        self._last_mode = None  # "PPA" hoặc "EPC"

        root = QVBoxLayout()
        #root.addWidget(QLabel("Chức năng tính toán PPA / EPC"))

        # ================= Hàng nút thao tác =================
        row_btns = QHBoxLayout()

        # --- PPA ---
        btn_calc_ppa = QPushButton("Calculate PPA")
        btn_calc_ppa.clicked.connect(self.calculate_ppa)
        row_btns.addWidget(btn_calc_ppa)

        btn_draw_df1_ppa = QPushButton("Draw DF1_PPA")
        btn_draw_df1_ppa.clicked.connect(self.draw_df1_ppa)
        row_btns.addWidget(btn_draw_df1_ppa)

        btn_draw_df2_ppa = QPushButton("Draw DF2_PPA")
        btn_draw_df2_ppa.clicked.connect(self.draw_df2_ppa)
        row_btns.addWidget(btn_draw_df2_ppa)

        # --- EPC ---
        btn_calc_epc = QPushButton("Calculate EPC")
        btn_calc_epc.clicked.connect(self.calculate_epc)
        row_btns.addWidget(btn_calc_epc)

        btn_draw_df1_epc = QPushButton("Draw DF1_EPC")
        btn_draw_df1_epc.clicked.connect(self.draw_df1_epc)
        row_btns.addWidget(btn_draw_df1_epc)

        btn_draw_df2_epc = QPushButton("Draw DF2_EPC")
        btn_draw_df2_epc.clicked.connect(self.draw_df2_epc)
        row_btns.addWidget(btn_draw_df2_epc)

        root.addLayout(row_btns)

        # ================= Dashboard (Hourly Preview) =================
        #root.addWidget(QLabel("Dashboard: Hourly preview (cập nhật sau khi Calculate)"))

        # Tiêu đề động cho dashboard
        self.lbl_dashboard_title = QLabel("—")
        font = self.lbl_dashboard_title.font()
        font.setBold(True)
        self.lbl_dashboard_title.setFont(font)
        root.addWidget(self.lbl_dashboard_title)

        # 2 bảng: S1 & S2
        row_dash = QHBoxLayout()
        self.table_hour_s1 = QTableView()
        self.table_hour_s2 = QTableView()

        # label cho từng bảng
        col = QVBoxLayout()
        self.lbl_s1 = QLabel("S1 hourly")
        col.addWidget(self.lbl_s1)
        col.addWidget(self.table_hour_s1)
        row_dash.addLayout(col)

        col2 = QVBoxLayout()
        self.lbl_s2 = QLabel("S2 hourly")
        col2.addWidget(self.lbl_s2)
        col2.addWidget(self.table_hour_s2)
        row_dash.addLayout(col2)

        root.addLayout(row_dash)

        self.setLayout(root)

    def set_main_window_ref(self, ref):
        self.main_window_ref = ref

    # ================= Helpers =================
    def _require_data(self):
        if not self.main_window_ref:
            QMessageBox.warning(self, "Thiếu tham chiếu", "Không tìm thấy dữ liệu DF1, DF2!")
            return None, None
        df1 = getattr(self.main_window_ref, "DF1", None)
        df2 = getattr(self.main_window_ref, "DF2", None)
        if df1 is None or df2 is None or df1.empty or df2.empty:
            QMessageBox.warning(self, "Thiếu dữ liệu", "DF1 hoặc DF2 rỗng!")
            return None, None
        return df1, df2

    def _df_to_model(self, df):
        """Chuyển pandas.DataFrame -> QStandardItemModel để hiển thị trên QTableView."""
        model = QStandardItemModel()
        if df is None or df.empty:
            return model

        # set header
        model.setColumnCount(len(df.columns))
        model.setRowCount(len(df.index))
        model.setHorizontalHeaderLabels([str(c) for c in df.columns])

        # fill data
        for r in range(len(df.index)):
            for c in range(len(df.columns)):
                val = df.iat[r, c]
                if pd.isna(val):
                    text = ""
                elif isinstance(val, (pd.Timestamp, )):
                    # format kiểu "20:00 12/30/24"
                    text = val.strftime("%H:%M %d/%m/%y")#("%H:%M %m/%d/%y")
                else:
                    text = str(val)

                item = QStandardItem(text)

                if isinstance(val, (int, float)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if df.columns[c] == "Δ%" and pd.notna(val):
                    try:
                        val_num = float(val)
                        if val_num > 2:
                            item.setBackground(QColor(144, 238, 144))  # xanh lá nhạt
                        elif val_num < -2:
                            item.setBackground(QColor(255, 182, 193))  # đỏ nhạt
                    except Exception:
                        pass
                model.setItem(r, c, item)
        return model
    def _merge_hour_with_contract(self, hour_df: pd.DataFrame, ct_df: pd.DataFrame) -> pd.DataFrame:
        """
        Ghép Sub-Contract vào hourly theo khóa thời gian dạng chuỗi '%H:%M %d/%m/%y'.
        Tính duy nhất cột Δ% theo yêu cầu.
        """
        if hour_df is None or hour_df.empty:
            return hour_df
        if ct_df is None or ct_df.empty or "Time" not in ct_df or "Output Power" not in ct_df:
            return hour_df

        # ===== Left: hourly =====
        tmp = hour_df.copy()

        # bảo đảm 'Thời điểm' là datetime trước khi format
        if "Thời điểm" in tmp.columns and not pd.api.types.is_datetime64_any_dtype(tmp["Thời điểm"]):
            tmp["Thời điểm"] = pd.to_datetime(tmp["Thời điểm"], errors="coerce")

        # format -> string khóa thống nhất
        tmp["TimeKey"] = pd.to_datetime(tmp["Thời điểm"], errors="coerce").dt.strftime("%H:%M %d/%m/%y")
        tmp = tmp.dropna(subset=["TimeKey"])
        tmp["TimeKey"] = tmp["TimeKey"].astype(str)

        # ===== Right: Sub-Contract =====
        ct = ct_df.copy()
        # nếu Time là datetime -> format; nếu là string -> vẫn ép datetime rồi format cho chắc
        ct["TimeKey"] = pd.to_datetime(ct["Time"], errors="coerce", dayfirst=True).dt.strftime("%H:%M %d/%m/%y")
        ct = ct.dropna(subset=["TimeKey"])
        ct["TimeKey"] = ct["TimeKey"].astype(str)

        ct["Output Power"] = pd.to_numeric(ct["Output Power"], errors="coerce")
        ct = ct.rename(columns={"Output Power": "Output Power_CT"})

        # xử lý trùng mốc thời gian: lấy bản ghi cuối cùng
        ct = ct.groupby("TimeKey", as_index=False).last()[["TimeKey", "Output Power_CT"]]

        # ===== Merge =====
        out = tmp.merge(ct, on="TimeKey", how="left")

        # ==== chỉ tính Δ% ====
        out["Δ%"] = (out["MW"] - out["Output Power_CT"]) / out["MW"] * 100
        out.loc[out["MW"].abs() <= 1e-9, "Δ%"] = None

        # sắp cột: Thời điểm, MW, Output Power_CT, Δ%
        pref = [c for c in ["Thời điểm", "MW", "Output Power_CT", "Δ%"] if c in out.columns]
        rest = [c for c in out.columns if c not in pref + ["TimeKey"]]
        out = out[pref + rest]
        return out


    def _update_dashboard_from_hourly(self, mode_title, s1_hour, s2_hour, subtitle="cached"):
        self.lbl_dashboard_title.setText(f"{mode_title} – Hourly ({subtitle})")

        # GHÉP Sub-Contract nếu có
        df1_ct = getattr(self.main_window_ref, "DF1_CT", None) if self.main_window_ref else None
        df2_ct = getattr(self.main_window_ref, "DF2_CT", None) if self.main_window_ref else None
        s1_view = self._merge_hour_with_contract(s1_hour, df1_ct) #df sau khi ghép
        s2_view = self._merge_hour_with_contract(s2_hour, df2_ct)

        self.table_hour_s1.setModel(self._df_to_model(s1_view))
        self.table_hour_s2.setModel(self._df_to_model(s2_view))
        self.table_hour_s1.resizeColumnsToContents()
        self.table_hour_s2.resizeColumnsToContents()

    def _update_dashboard(self, mode_title, s1_min, s2_min, freq="T", label="right", drop_incomplete=True):
        """Tính hourly từ minutely và cập nhật 2 bảng dashboard."""
        try:
            s1_hour = minutely_to_hourly_avg(s1_min, freq=freq, drop_incomplete=drop_incomplete, label=label)
            s2_hour = minutely_to_hourly_avg(s2_min, freq=freq, drop_incomplete=drop_incomplete, label=label)
        except Exception as ex:
            QMessageBox.critical(self, "Lỗi khi tổng hợp giờ", f"Đã xảy ra lỗi:\n{ex}")
            return

        self.lbl_dashboard_title.setText(f"{mode_title} – Hourly ({label})")
        self.table_hour_s1.setModel(self._df_to_model(s1_hour))
        self.table_hour_s2.setModel(self._df_to_model(s2_hour))
        # auto resize
        self.table_hour_s1.resizeColumnsToContents()
        self.table_hour_s2.resizeColumnsToContents()

    # ================== PPA ==================
    def calculate_ppa(self):
        df1, df2 = self._require_data()
        if df1 is None:
            return

        seg1, sum1 = build_ppa_per_pair(df1)
        seg2, sum2 = build_ppa_per_pair(df2)

        # lưu kết quả PPA
        self.main_window_ref.DF1_ppa = (seg1, sum1)
        self.main_window_ref.DF2_ppa = (seg2, sum2)

        # tạo DF phút
        s1_min = ppa_segments_to_minutely(seg1, freq="T", include_pair_idx=False)
        s2_min = ppa_segments_to_minutely(seg2, freq="T", include_pair_idx=False)
        self.main_window_ref.DF1_ppa_minutely = s1_min
        self.main_window_ref.DF2_ppa_minutely = s2_min

        # >>> tạo DF giờ trước
        s1_hour = minutely_to_hourly_avg(s1_min, freq="T", drop_incomplete=True, label="right")
        s2_hour = minutely_to_hourly_avg(s2_min, freq="T", drop_incomplete=True, label="right")
        self.main_window_ref.DF1_ppa_hourly = s1_hour
        self.main_window_ref.DF2_ppa_hourly = s2_hour

        # cập nhật dashboard từ DF giờ đã có
        self._last_mode = "PPA"
        self._update_dashboard_from_hourly("PPA", s1_hour, s2_hour)

        # hỏi lưu file
        path, _ = QFileDialog.getSaveFileName(self, "Lưu PPA (minutely + hourly)", "PPA_Hour.xlsx", "Excel Files (*.xlsx)")
        if not path:
            QMessageBox.information(self, "Đã tính xong", "Đã tạo DF1_ppa/DF2_ppa cùng dữ liệu phút + giờ (chưa lưu file).")
            return
        try:
            # export có thể dùng lại s1_min/s2_min và cả s1_hour/s2_hour
            export_ppa_minutely_and_hourly_to_excel(s1_min, s2_min, filepath=path, sheet_name="PPA", freq="T", drop_incomplete=True)
            QMessageBox.information(self, "Hoàn tất", f"Đã lưu file:\n{path}")
        except Exception as ex:
            QMessageBox.critical(self, "Lỗi khi xuất Excel", f"Đã xảy ra lỗi:\n{ex}")


    def draw_df1_ppa(self):
        if not self.main_window_ref or not hasattr(self.main_window_ref, "DF1_ppa"):
            QMessageBox.warning(self, "Chưa tính PPA", "Hãy bấm 'Calculate PPA' trước.")
            return
        draw_ppa_df(self.main_window_ref.DF1_ppa, "DF1_PPA – S1", parent=self)

    def draw_df2_ppa(self):
        if not self.main_window_ref or not hasattr(self.main_window_ref, "DF2_ppa"):
            QMessageBox.warning(self, "Chưa tính PPA", "Hãy bấm 'Calculate PPA' trước.")
            return
        draw_ppa_df(self.main_window_ref.DF2_ppa, "DF2_PPA – S2", parent=self)

    # ================== EPC ==================
    def calculate_epc(self):  # 429/429; tốc độ phụ thuộc 330 như ta đã thống nhất
        df1, df2 = self._require_data()
        if df1 is None:
            return

        seg1, sum1 = build_epc_per_pair(df1)
        seg2, sum2 = build_epc_per_pair(df2)

        # lưu kết quả EPC riêng để không đè PPA
        self.main_window_ref.DF1_epc = (seg1, sum1)
        self.main_window_ref.DF2_epc = (seg2, sum2)

        s1_min = ppa_segments_to_minutely(seg1, freq="T", include_pair_idx=False)
        s2_min = ppa_segments_to_minutely(seg2, freq="T", include_pair_idx=False)
        self.main_window_ref.DF1_epc_minutely = s1_min
        self.main_window_ref.DF2_epc_minutely = s2_min

        # cập nhật dashboard theo giờ
        # tạo & lưu DF giờ trước, rồi hiển thị từ cache (không tính lại)
        s1_hour = minutely_to_hourly_avg(s1_min, freq="T", drop_incomplete=True, label="right")
        s2_hour = minutely_to_hourly_avg(s2_min, freq="T", drop_incomplete=True, label="right")
        self.main_window_ref.DF1_epc_hourly = s1_hour
        self.main_window_ref.DF2_epc_hourly = s2_hour

        self._last_mode = "EPC"
        self._update_dashboard_from_hourly("EPC", s1_hour, s2_hour, subtitle="right")


        # hỏi lưu file
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu EPC (minutely + hourly)", "EPC_Hour.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            QMessageBox.information(self, "Đã tính xong",
                                    "Đã tạo DF1_epc/DF2_epc và dữ liệu theo phút (chưa lưu file).")
            return
        try:
            export_ppa_minutely_and_hourly_to_excel(
                df_s1_minutely=s1_min,
                df_s2_minutely=s2_min,
                filepath=path,
                sheet_name="EPC",
                freq="T",
                drop_incomplete=True
            )
            QMessageBox.information(self, "Hoàn tất", f"Đã lưu file:\n{path}")
        except PermissionError:
            QMessageBox.critical(self, "Không thể ghi file",
                                 "File đang mở trong Excel hoặc không có quyền ghi.\n"
                                 "Hãy đóng file rồi thử lại, hoặc lưu sang tên khác.")
        except Exception as ex:
            QMessageBox.critical(self, "Lỗi khi xuất Excel", f"Đã xảy ra lỗi:\n{ex}")

    def draw_df1_epc(self):
        if not self.main_window_ref or not hasattr(self.main_window_ref, "DF1_epc"):
            QMessageBox.warning(self, "Chưa tính EPC", "Hãy bấm 'Calculate EPC' trước.")
            return
        draw_ppa_df(self.main_window_ref.DF1_epc, "DF1_EPC – S1", parent=self)

    def draw_df2_epc(self):
        if not self.main_window_ref or not hasattr(self.main_window_ref, "DF2_epc"):
            QMessageBox.warning(self, "Chưa tính EPC", "Hãy bấm 'Calculate EPC' trước.")
            return
        draw_ppa_df(self.main_window_ref.DF2_epc, "DF2_EPC – S2", parent=self)
