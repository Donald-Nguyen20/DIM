# tab_module/calculation_modules/df_inventory.py
from __future__ import annotations
import pandas as pd
from typing import Dict, Tuple

EXCEL_SHEET_MAXLEN = 31
# Mapping tên DataFrame export
NAME_MAP = {
    "DF1_dashboard": "Data_dashboard_U1",
    "DF2_dashboard": "Data_dashboard_U2",
    "DF1_PPA_minutely": "Data_ppa_minutely_U1",
    "DF2_PPA_minutely": "Data_ppa_minutely_U2",
    "DF1_PPA_hourly": "Data_ppa_hourly_U1",
    "DF2_PPA_hourly": "Data_ppa_hourly_U2",
    "DF1_EPC_minutely": "Data_epc_minutely_U1",
    "DF2_EPC_minutely": "Data_epc_minutely_U2",
    "DF1_EPC_hourly": "Data_epc_hourly_U1",
    "DF2_EPC_hourly": "Data_epc_hourly_U2",
}

def _add_df(out: Dict[str, pd.DataFrame], name: str, df):
    """Chỉ nhận DataFrame không rỗng. Cắt tên sheet <= 31 ký tự."""
    if isinstance(df, pd.DataFrame) and not df.empty:
        export_name = NAME_MAP.get(name, name)   # <--- dùng mapping
        out[export_name[:EXCEL_SHEET_MAXLEN]] = df


def collect_available_dataframes(main_window_ref) -> Dict[str, pd.DataFrame]:
    """
    Quét các biến chuẩn hoá trong main_window_ref và gom về dict {sheet_name: DataFrame}.
    """
    out: Dict[str, pd.DataFrame] = {}
    mw = main_window_ref
    if not mw:
        return out

    # # Raw input
    # _add_df(out, "DF1_raw", getattr(mw, "DF1", None))
    # _add_df(out, "DF2_raw", getattr(mw, "DF2", None))

    # Dashboard views (đã merge hợp đồng)
    _add_df(out, "DF1_dashboard", getattr(mw, "DF1_dashboard", None))
    _add_df(out, "DF2_dashboard", getattr(mw, "DF2_dashboard", None))

    # PPA minutely/hourly
    _add_df(out, "DF1_PPA_minutely", getattr(mw, "DF1_ppa_minutely", None))
    _add_df(out, "DF2_PPA_minutely", getattr(mw, "DF2_ppa_minutely", None))
    _add_df(out, "DF1_PPA_hourly", getattr(mw, "DF1_ppa_hourly", None))
    _add_df(out, "DF2_PPA_hourly", getattr(mw, "DF2_ppa_hourly", None))

    # EPC minutely/hourly
    _add_df(out, "DF1_EPC_minutely", getattr(mw, "DF1_epc_minutely", None))
    _add_df(out, "DF2_EPC_minutely", getattr(mw, "DF2_epc_minutely", None))
    _add_df(out, "DF1_EPC_hourly", getattr(mw, "DF1_epc_hourly", None))
    _add_df(out, "DF2_EPC_hourly", getattr(mw, "DF2_epc_hourly", None))

    # # PPA/EPC segments & summary (tuple -> tách 2 DF)
    # ppa1 = getattr(mw, "DF1_ppa", None)
    # if isinstance(ppa1, tuple) and len(ppa1) == 2:
    #     _add_df(out, "DF1_PPA_segments", ppa1[0])
    #     _add_df(out, "DF1_PPA_summary", ppa1[1])
    # ppa2 = getattr(mw, "DF2_ppa", None)
    # if isinstance(ppa2, tuple) and len(ppa2) == 2:
    #     _add_df(out, "DF2_PPA_segments", ppa2[0])
    #     _add_df(out, "DF2_PPA_summary", ppa2[1])

    # epc1 = getattr(mw, "DF1_epc", None)
    # if isinstance(epc1, tuple) and len(epc1) == 2:
    #     _add_df(out, "DF1_EPC_segments", epc1[0])
    #     _add_df(out, "DF1_EPC_summary", epc1[1])
    # epc2 = getattr(mw, "DF2_epc", None)
    # if isinstance(epc2, tuple) and len(epc2) == 2:
    #     _add_df(out, "DF2_EPC_segments", epc2[0])
    #     _add_df(out, "DF2_EPC_summary", epc2[1])

    return out

def _safe_time_bounds(df: pd.DataFrame) -> Tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if "Thời điểm" in df.columns:
        s = pd.to_datetime(df["Thời điểm"], errors="coerce")
        s = s.dropna()
        if not s.empty:
            return s.min(), s.max()
    return None, None

def _safe_mw_minmax(df: pd.DataFrame) -> Tuple[float | None, float | None]:
    if "MW" in df.columns:
        s = pd.to_numeric(df["MW"], errors="coerce").dropna()
        if not s.empty:
            return float(s.min()), float(s.max())
    return None, None

def _memory_mb(df: pd.DataFrame) -> float:
    try:
        return float(df.memory_usage(deep=True).sum()) / (1024**2)
    except Exception:
        return float("nan")

def summarize_df_dict(df_map: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Tạo bảng inventory thống kê các DataFrame.
    Columns:
      Name | Rows | Cols | Memory_MB | Has_ThoiDiem | TimeStart | TimeEnd | Has_MW | MW_min | MW_max | NaN_cells | Columns
    """
    rows = []
    for name, df in df_map.items():
        r, c = df.shape
        mem_mb = _memory_mb(df)
        has_time = "Thời điểm" in df.columns
        t0, t1 = _safe_time_bounds(df)
        has_mw = "MW" in df.columns
        mw_min, mw_max = _safe_mw_minmax(df)
        nan_cells = int(df.isna().sum().sum())
        col_list = ", ".join(map(str, df.columns.tolist()))
        rows.append({
            "Name": name,
            "Rows": r,
            "Cols": c,
            "Memory_MB": round(mem_mb, 3) if pd.notna(mem_mb) else None,
            "Has_ThoiDiem": has_time,
            "TimeStart": t0,
            "TimeEnd": t1,
            "Has_MW": has_mw,
            "MW_min": mw_min,
            "MW_max": mw_max,
            "NaN_cells": nan_cells,
            "Columns": col_list[:300]  # rút gọn hiển thị
        })
    inv = pd.DataFrame(rows).sort_values(["Name"]).reset_index(drop=True)
    return inv
