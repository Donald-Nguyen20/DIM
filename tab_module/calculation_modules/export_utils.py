# export_utils.py
import pandas as pd

# ===== Helper: chuyển freq -> Timedelta an toàn ("T","S","H","30S","5T", Timedelta, ...) =====
def _freq_to_timedelta(freq):
    """
    Chuyển freq như 'T','S','H','30S','5T' hoặc Timedelta thành pd.Timedelta.
    Nếu freq chỉ là đơn vị (toàn chữ), tự động thêm '1' ở trước.
    """
    if isinstance(freq, pd.Timedelta):
        return freq
    if isinstance(freq, str):
        f = freq.strip()
        try:
            return pd.to_timedelta(f)          # '30S','5T' OK
        except Exception:
            if f.isalpha():                    # 'T','S','H'...
                return pd.to_timedelta("1" + f)
            raise
    return pd.to_timedelta(freq)

def minutely_to_hourly_avg(minutely_df: pd.DataFrame,
                           freq: str = "T",
                           drop_incomplete: bool = True,
                           return_energy: bool = False,
                           label: str = "left") -> pd.DataFrame:
    """
    TÍNH THEO HÌNH THANG (không nội suy).
    label="left": nhãn = đầu giờ -> [HH:00, HH+1:00)
    label="right": nhãn = cuối giờ -> (HH-1:00, HH]
    """
    if label not in ("left", "right"):
        raise ValueError("label phải là 'left' hoặc 'right'")
    col_val = "MWh" if return_energy else "MW"

    if (minutely_df is None or minutely_df.empty or
        "Thời điểm" not in minutely_df.columns or
        "MW" not in minutely_df.columns):
        return pd.DataFrame(columns=["Thời điểm", col_val])

    df = minutely_df.copy()
    df["Thời điểm"] = pd.to_datetime(df["Thời điểm"], errors="coerce")
    df["MW"] = pd.to_numeric(df["MW"], errors="coerce")
    df = df.dropna(subset=["Thời điểm", "MW"]).sort_values("Thời điểm").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=["Thời điểm", col_val])

    s = df.set_index("Thời điểm")["MW"].sort_index()

    hours, values = [], []
    one_hour = pd.Timedelta("1H")
    dt = _freq_to_timedelta(freq)
    if dt <= pd.Timedelta(0):
        raise ValueError("freq không hợp lệ.")
    dt_hours = float(dt / pd.Timedelta(hours=1))

    #for hour, grp in s.groupby(pd.Grouper(freq="H", label=label, closed=label)):# đang lấy từ 01-00
    for hour, grp in s.groupby(pd.Grouper(freq="H", label=label, closed=label)):
        # Xác định cửa sổ theo label
        if label == "left":
            left, right = hour, hour + one_hour       # [HH:00, HH+1:00)
        else:
            left, right = hour - one_hour, hour       # (HH-1:00, HH]

        # CẮT CỬA SỔ BAO GỒM CẢ HAI BIÊN: [left, right]
        window = s.loc[left:right]

        # Nếu cần “đủ mẫu” theo bước freq (ví dụ "T"): kỳ vọng = 1H/dt + 1 (gồm cả 2 biên)
        if drop_incomplete:
            expected_ticks = int(pd.Timedelta("1H") / dt) + 1
            if len(window) < expected_ticks:
                continue

        if window.empty:
            continue

        value = window.mean()  # TRUNG BÌNH GỒM CẢ MỐC HH:00 VÀ HH+1:00

        # Gán nhãn: với label="right" → nhãn giờ = HH+1:00; với "left" → = HH:00
        out_hour = hour
        hours.append(out_hour)
        values.append(float(value))


    hourly_series = pd.Series(values, index=hours).sort_index()
    if hourly_series.empty:
        return pd.DataFrame(columns=["Thời điểm", col_val])

    # if drop_incomplete:
    #     expected_intervals = int(pd.Timedelta("1H") / dt)  # N khoảng
    #     counts = s.resample("H", label=label, closed=label).count()  # đếm N tick trong cửa sổ
    #     hourly_series = hourly_series[
    #         counts.reindex(hourly_series.index).fillna(0).astype(int) >= expected_intervals
    #     ]

    out = hourly_series.reset_index()
    out.columns = ["Thời điểm", col_val]
    return out


# ========= Helper: reorder cột để "Thời điểm","MW" lên đầu =========
def _reorder(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    pref = [c for c in ["Thời điểm", "MW"] if c in cols]
    rest = [c for c in cols if c not in pref]
    return df[pref + rest]

# ========= Ghi CẢ phút + giờ =========
def export_ppa_minutely_to_excel(df_s1: pd.DataFrame,
                                 df_s2: pd.DataFrame,
                                 filepath: str,
                                 sheet_name: str = "PPA",
                                 freq: str = "T",
                                 drop_incomplete: bool = True,
                                 label: str = "right"):
    """
    Ghi S1/S2 phút và giờ trong cùng 1 sheet:
      - Phút:
          S1 -> A2 (A,B,...) ; S2 -> D2 (D,E,...)
      - Giờ (trung bình theo giờ, label='left' => nhãn đầu giờ; label='right' => nhãn cuối giờ):
          S1 -> G2 (G: Thời điểm, H: MW/MWh)
          S2 -> J2 (J: Thời điểm, K: MW/MWh)
    """
    # Chuẩn hóa phút
    df_s1_min = _reorder(df_s1.copy()) if df_s1 is not None else pd.DataFrame(columns=["Thời điểm","MW"])
    df_s2_min = _reorder(df_s2.copy()) if df_s2 is not None else pd.DataFrame(columns=["Thời điểm","MW"])

    # Tính giờ từ phút (TRUYỀN label xuống hàm tính)
    df_s1_hr = _reorder(minutely_to_hourly_avg(
        df_s1_min, freq=freq, drop_incomplete=drop_incomplete, label=label
    ))
    df_s2_hr = _reorder(minutely_to_hourly_avg(
        df_s2_min, freq=freq, drop_incomplete=drop_incomplete, label=label
    ))

    # Ghi Excel
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # ----- Blocks phút -----
        df_s1_min.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=0)  # A2
        df_s2_min.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=3)  # D2

        # ----- Blocks giờ -----
        df_s1_hr.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=6)   # G2
        df_s2_hr.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=9)   # J2

        # ----- Nhãn hàng 1 cho 4 block -----
        ws = writer.book[sheet_name]
        ws.cell(row=1, column=1,  value="S1 (minutely)")                # A1
        ws.cell(row=1, column=4,  value="S2 (minutely)")                # D1
        ws.cell(row=1, column=7,  value=f"S1 (hourly avg, {label})")    # G1
        ws.cell(row=1, column=10, value=f"S2 (hourly avg, {label})")    # J1


# ========= Alias: tham số tường minh =========
def export_ppa_minutely_and_hourly_to_excel(df_s1_minutely: pd.DataFrame,
                                            df_s2_minutely: pd.DataFrame,
                                            filepath: str,
                                            sheet_name: str = "PPA",
                                            freq: str = "T",
                                            drop_incomplete: bool = True):
    """Alias tường minh."""
    return export_ppa_minutely_to_excel(
        df_s1=df_s1_minutely,
        df_s2=df_s2_minutely,
        filepath=filepath,
        sheet_name=sheet_name,
        freq=freq,
        drop_incomplete=drop_incomplete
    )

# export_utils.py
# import pandas as pd

# # ===== Helper: chuyển freq -> Timedelta an toàn ("T","S","H","30S","5T", Timedelta, ...) =====
# def _freq_to_timedelta(freq):
#     """
#     Chuyển freq như 'T','S','H','30S','5T' hoặc Timedelta thành pd.Timedelta.
#     Nếu freq chỉ là đơn vị (toàn chữ), tự động thêm '1' ở trước.
#     """
#     if isinstance(freq, pd.Timedelta):
#         return freq
#     if isinstance(freq, str):
#         f = freq.strip()
#         try:
#             return pd.to_timedelta(f)          # '30S','5T' OK
#         except Exception:
#             if f.isalpha():                    # 'T','S','H'...
#                 return pd.to_timedelta("1" + f)
#             raise
#     return pd.to_timedelta(freq)

# def minutely_to_hourly_avg(minutely_df: pd.DataFrame,
#                            freq: str = "T",
#                            drop_incomplete: bool = True,
#                            return_energy: bool = False,
#                            label: str = "left") -> pd.DataFrame:
#     """
#     TÍNH THEO HÌNH THANG (không nội suy).
#     label="left": nhãn = đầu giờ -> [HH:00, HH+1:00)
#     label="right": nhãn = cuối giờ -> (HH-1:00, HH]
#     """
#     if label not in ("left", "right"):
#         raise ValueError("label phải là 'left' hoặc 'right'")
#     col_val = "MWh" if return_energy else "MW"

#     if (minutely_df is None or minutely_df.empty or
#         "Thời điểm" not in minutely_df.columns or
#         "MW" not in minutely_df.columns):
#         return pd.DataFrame(columns=["Thời điểm", col_val])

#     df = minutely_df.copy()
#     df["Thời điểm"] = pd.to_datetime(df["Thời điểm"], errors="coerce")
#     df["MW"] = pd.to_numeric(df["MW"], errors="coerce")
#     df = df.dropna(subset=["Thời điểm", "MW"]).sort_values("Thời điểm").reset_index(drop=True)
#     if df.empty:
#         return pd.DataFrame(columns=["Thời điểm", col_val])

#     s = df.set_index("Thời điểm")["MW"].sort_index()

#     hours, values = [], []
#     one_hour = pd.Timedelta("1H")
#     dt = _freq_to_timedelta(freq)
#     if dt <= pd.Timedelta(0):
#         raise ValueError("freq không hợp lệ.")
#     dt_hours = float(dt / pd.Timedelta(hours=1))

#     for hour, grp in s.groupby(pd.Grouper(freq="H", label=label, closed=label)):
#         if grp.empty:
#             continue

#         # Chọn cửa sổ theo label
#         if label == "left":
#             left, right = hour, hour + one_hour       # [HH:00, HH+1:00]
#         else:
#             left, right = hour - one_hour, hour       # (HH-1:00, HH]

#         # Lưới đủ 2 biên, không nội suy
#         grid = pd.date_range(start=left, end=right, freq=dt) 

#         # Bắt buộc đủ tất cả mốc trong dữ liệu gốc
#         if not grid.isin(s.index).all():
#             continue

#         v = s.loc[grid].to_numpy()  # N+1 mốc
#         energy_mwh = ((v[:-1] + v[1:]) * 0.5).sum() * dt_hours
#         value = float(energy_mwh if return_energy else energy_mwh / 1.0)

#         hours.append(hour)   # nhãn = left/right tương ứng
#         values.append(value)

#     hourly_series = pd.Series(values, index=hours).sort_index()
#     if hourly_series.empty:
#         return pd.DataFrame(columns=["Thời điểm", col_val])

#     if drop_incomplete:
#         expected_intervals = int(pd.Timedelta("1H") / dt)  # N khoảng
#         counts = s.resample("H", label=label, closed=label).count()  # đếm N tick trong cửa sổ
#         hourly_series = hourly_series[
#             counts.reindex(hourly_series.index).fillna(0).astype(int) >= expected_intervals
#         ]

#     out = hourly_series.reset_index()
#     out.columns = ["Thời điểm", col_val]
#     return out


# # ========= Helper: reorder cột để "Thời điểm","MW" lên đầu =========
# def _reorder(df: pd.DataFrame) -> pd.DataFrame:
#     cols = list(df.columns)
#     pref = [c for c in ["Thời điểm", "MW"] if c in cols]
#     rest = [c for c in cols if c not in pref]
#     return df[pref + rest]

# # ========= Ghi CẢ phút + giờ =========
# def export_ppa_minutely_to_excel(df_s1: pd.DataFrame,
#                                  df_s2: pd.DataFrame,
#                                  filepath: str,
#                                  sheet_name: str = "PPA",
#                                  freq: str = "T",
#                                  drop_incomplete: bool = True,
#                                  label: str = "right"):
#     """
#     Ghi S1/S2 phút và giờ trong cùng 1 sheet:
#       - Phút:
#           S1 -> A2 (A,B,...) ; S2 -> D2 (D,E,...)
#       - Giờ (trung bình theo giờ, label='left' => nhãn đầu giờ; label='right' => nhãn cuối giờ):
#           S1 -> G2 (G: Thời điểm, H: MW/MWh)
#           S2 -> J2 (J: Thời điểm, K: MW/MWh)
#     """
#     # Chuẩn hóa phút
#     df_s1_min = _reorder(df_s1.copy()) if df_s1 is not None else pd.DataFrame(columns=["Thời điểm","MW"])
#     df_s2_min = _reorder(df_s2.copy()) if df_s2 is not None else pd.DataFrame(columns=["Thời điểm","MW"])

#     # Tính giờ từ phút (TRUYỀN label xuống hàm tính)
#     df_s1_hr = _reorder(minutely_to_hourly_avg(
#         df_s1_min, freq=freq, drop_incomplete=drop_incomplete, label=label
#     ))
#     df_s2_hr = _reorder(minutely_to_hourly_avg(
#         df_s2_min, freq=freq, drop_incomplete=drop_incomplete, label=label
#     ))

#     # Ghi Excel
#     with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
#         # ----- Blocks phút -----
#         df_s1_min.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=0)  # A2
#         df_s2_min.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=3)  # D2

#         # ----- Blocks giờ -----
#         df_s1_hr.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=6)   # G2
#         df_s2_hr.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, startcol=9)   # J2

#         # ----- Nhãn hàng 1 cho 4 block -----
#         ws = writer.book[sheet_name]
#         ws.cell(row=1, column=1,  value="S1 (minutely)")                # A1
#         ws.cell(row=1, column=4,  value="S2 (minutely)")                # D1
#         ws.cell(row=1, column=7,  value=f"S1 (hourly avg, {label})")    # G1
#         ws.cell(row=1, column=10, value=f"S2 (hourly avg, {label})")    # J1


# # ========= Alias: tham số tường minh =========
# def export_ppa_minutely_and_hourly_to_excel(df_s1_minutely: pd.DataFrame,
#                                             df_s2_minutely: pd.DataFrame,
#                                             filepath: str,
#                                             sheet_name: str = "PPA",
#                                             freq: str = "T",
#                                             drop_incomplete: bool = True):
#     """Alias tường minh."""
#     return export_ppa_minutely_to_excel(
#         df_s1=df_s1_minutely,
#         df_s2=df_s2_minutely,
#         filepath=filepath,
#         sheet_name=sheet_name,
#         freq=freq,
#         drop_incomplete=drop_incomplete
#     )
