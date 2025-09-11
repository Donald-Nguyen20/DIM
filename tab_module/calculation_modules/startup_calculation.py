#startup_calculation.py
"""
startup_calculation.py
Tính giờ & phân loại start-up, dựng timeline MW theo thời gian từ BĐTH.
Các mốc phút trong profile là OFFSET TUYỆT ĐỐI so với BĐTH (không cộng dồn).
"""

from __future__ import annotations
import pandas as pd
from typing import Optional, Dict, List

# =========================================================
# 1) PHÂN LOẠI THEO KHOẢNG GIỜ (Ngừng tổ máy -> BĐTH Khởi động lò)
# =========================================================

def classify_startup(df_startup: pd.DataFrame, unit: str = "") -> Dict[str, Optional[object]]:
    """
    Nhận DF_STARTUP (5 dòng quanh 'Khởi động lò') -> tính giờ & phân loại.
    Return: {'Unit','Hours','Type'}
    """
    idxs = df_startup.index[df_startup["Case"] == "Khởi động lò"].tolist()
    if not idxs:
        return {"Unit": unit, "Hours": None, "Type": None}

    i = idxs[0]  # lấy lần khởi động đầu tiên trong cửa sổ
    if i - 1 not in df_startup.index:
        return {"Unit": unit, "Hours": None, "Type": None}

    # mốc start = Thời điểm BĐTH của 'Khởi động lò'
    t_start = pd.to_datetime(df_startup.loc[i, "Thời điểm BĐTH"], errors="coerce", dayfirst=True)

    # mốc stop = ưu tiên 'Thời điểm hoàn thành' của dòng trước; nếu trống, dùng 'Thời điểm BĐTH'
    prev = df_startup.loc[i - 1]
    t_stop = pd.to_datetime(prev.get("Thời điểm hoàn thành"), errors="coerce", dayfirst=True)
    if pd.isna(t_stop):
        t_stop = pd.to_datetime(prev.get("Thời điểm BĐTH"), errors="coerce", dayfirst=True)

    if pd.isna(t_start) or pd.isna(t_stop):
        return {"Unit": unit, "Hours": None, "Type": None}

    hours = round((t_start - t_stop).total_seconds() / 3600.0, 4)

    # Phân loại
    if hours > 72:
        stype = "Initial Cold Start-up"
    elif 56 <= hours <= 72:
        stype = "Cold Start-up"
    elif 8 <= hours < 56:
        stype = "Warm Start-up"
    else:
        stype = "Hot Start-up"

    syn_minutes = _STARTUP_SYN_MINUTES.get(stype)
    return {"Unit": unit, "Hours": hours, "Type": stype, "SynMinutes": syn_minutes}


# =========================================================
# 2) PROFILE Syn→40% (các mốc là ABSOLUTE OFFSET kể từ BĐTH)
# =========================================================

_COL_TIME = "Time from Syn to 40% load (mins)"
_COL_MW   = "Net MW"
# === (NEW) Light-off -> Synchronise (minutes) theo loại start-up ===
_STARTUP_SYN_MINUTES: Dict[str, int] = {
    "Hot Start-up": 75,
    "Warm Start-up": 190,
    "Cold Start-up": 310,
    "Initial Cold Start-up": 385,
}

def get_syn_minutes_for_type(stype: Optional[str]) -> Optional[int]:
    """Tra cứu phút từ light-off tới synchronise theo loại start-up."""
    if not stype:
        return None
    return _STARTUP_SYN_MINUTES.get(stype)

_STARTUP_PROFILES: Dict[str, List[tuple[float, float]]] = {
    "Hot Start-up":              [(0, 0), (5, 0), (15, 71), (55, 71), (82, 264)],
    "Warm Start-up":             [(0, 0), (10, 0), (14, 14), (19, 14), (35, 71), (75, 71), (129, 264)],
    "Cold Start-up":             [(0, 0), (10, 0), (14, 14), (24, 14), (40, 71), (100, 71), (154, 264)],
    "Initial Cold Start-up":     [(0, 0), (10, 0), (14, 14), (74, 14), (90, 71), (150, 71), (204, 264)],
}

def _get_syn40_profile_df(stype: Optional[str]) -> pd.DataFrame:
    seq = _STARTUP_PROFILES.get(stype)
    if not seq:
        return pd.DataFrame(columns=[_COL_TIME, _COL_MW])
    return pd.DataFrame(seq, columns=[_COL_TIME, _COL_MW])


# =========================================================
# 3) RAMP 40%→100% (MW/min) + HOLD @50%
# =========================================================

_STAGE_HOLD = "Hold@50%"

_RAMP_AFTER_40: Dict[str, List[Dict[str, float]]] = {
    "Hot Start-up": [
        {"Stage": "40%→50%",  "MW_per_min": 6.6, "Hold_mins": 0.0},
        {"Stage": _STAGE_HOLD, "MW_per_min": 0.0, "Hold_mins": 30.0},
        {"Stage": "50%→100%", "MW_per_min": 13.2, "Hold_mins": 0.0},
    ],
    "Warm Start-up": [
        {"Stage": "40%→50%",  "MW_per_min": 3.3, "Hold_mins": 0.0},
        {"Stage": _STAGE_HOLD, "MW_per_min": 0.0, "Hold_mins": 30.0},
        {"Stage": "50%→100%", "MW_per_min": 6.6, "Hold_mins": 0.0},
    ],
    "Cold Start-up": [
        {"Stage": "40%→50%",  "MW_per_min": 3.3, "Hold_mins": 0.0},
        {"Stage": _STAGE_HOLD, "MW_per_min": 0.0, "Hold_mins": 60.0},
        {"Stage": "50%→100%", "MW_per_min": 6.6, "Hold_mins": 0.0},
    ],
    "Initial Cold Start-up": [
        {"Stage": "40%→50%",  "MW_per_min": 3.3, "Hold_mins": 0.0},
        {"Stage": _STAGE_HOLD, "MW_per_min": 0.0, "Hold_mins": 60.0},
        {"Stage": "50%→100%", "MW_per_min": 6.6, "Hold_mins": 0.0},
    ],
}

def _get_after40_ramp_df(stype: Optional[str]) -> pd.DataFrame:
    rows = _RAMP_AFTER_40.get(stype)
    if not rows:
        return pd.DataFrame(columns=["Stage", "MW_per_min", "Hold_mins"])
    return pd.DataFrame(rows, columns=["Stage", "MW_per_min", "Hold_mins"])


# =========================================================
# 4) DỰNG TIMELINE ABSOLUTE (BĐTH → 100%)
# =========================================================

def build_syn40_absolute_points(
    df_startup: pd.DataFrame,
    unit: str = "",
    *,
    sync_offset_min: float = 0.0,
    mw40_override: float | None = None
) -> pd.DataFrame:
    """
    Sinh các điểm Syn→40% với offset tuyệt đối từ BĐTH.
    - BỎ ĐIỂM offset=0 để không trùng marker Syn
    - MỐC 40% (264 MW) sẽ được chốt theo 'Thời điểm hoàn thành' trong dữ liệu nếu tìm thấy
    """
    meta = classify_startup(df_startup, unit)
    stype = meta.get("Type")
    if not stype:
        return pd.DataFrame(columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    # BĐTH (t0)
    idxs = df_startup.index[df_startup["Case"] == "Khởi động lò"].tolist()
    if not idxs:
        return pd.DataFrame(columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])
    i = idxs[0]
    t0 = pd.to_datetime(df_startup.loc[i, "Thời điểm BĐTH"], errors="coerce", dayfirst=True)
    if pd.isna(t0):
        return pd.DataFrame(columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    prof = _get_syn40_profile_df(stype)
    if prof.empty:
        return pd.DataFrame(columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    # BỎ mốc offset=0 để không trùng với marker Syn
    prof = prof[prof[_COL_TIME] > 0].reset_index(drop=True)
    if prof.empty:
        return pd.DataFrame(columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    # Tính scale nếu có override 40%
    mw40_prof = float(prof[_COL_MW].max()) if prof[_COL_MW].notna().any() else 0.0
    scale = 1.0 if (mw40_override is None or mw40_prof == 0.0) else (mw40_override / mw40_prof)

    out_rows: List[Dict] = []
    for _, r in prof.iterrows():
        dt_abs = float(r[_COL_TIME]) + float(sync_offset_min)
        mw_val = float(r[_COL_MW]) * scale
        out_rows.append({
            "Unit": unit,
            "Type": stype,
            "Phase": "Syn→40%",
            "Δt_min_abs": round(dt_abs, 2),
            "Time": t0 + pd.Timedelta(minutes=dt_abs),
            "MW": round(mw_val, 3),
        })
    syn40 = pd.DataFrame(out_rows, columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    # === CHỐT MỐC 40% THEO DỮ LIỆU (ưu tiên 'Thời điểm hoàn thành') ===
    import re
    def _get_40pct_time_from_data(dfi: pd.DataFrame, mw_target: float) -> Optional[pd.Timestamp]:
        dfi2 = dfi.copy()

        # 1) Ưu tiên theo text "40%"
        if "Case" in dfi2.columns:
            pat = re.compile(r"40\s*%|đạt\s*40\s*%|tới\s*40\s*%", re.IGNORECASE)
            m = dfi2["Case"].astype(str).str.contains(pat, na=False)
            cand = dfi2[m]
            if not cand.empty:
                t = pd.to_datetime(cand["Thời điểm hoàn thành"], errors="coerce", dayfirst=True).dropna()
                if not t.empty:
                    return t.iloc[0]
                t = pd.to_datetime(cand["Thời điểm BĐTH"], errors="coerce", dayfirst=True).dropna()
                if not t.empty:
                    return t.iloc[0]

        # 2) Không có text → dò theo MW (≥ ngưỡng ~ 40%)
        tol = 0.5
        for col in ["CS hoàn thành (MW)", "CS ra lệnh (MW)"]:
            if col in dfi2.columns:
                x = pd.to_numeric(dfi2[col], errors="coerce")
                m = x >= (mw_target - tol)
                cand = dfi2[m]
                if not cand.empty:
                    t = pd.to_datetime(cand["Thời điểm hoàn thành"], errors="coerce", dayfirst=True).dropna()
                    if not t.empty:
                        return t.iloc[0]
                    t = pd.to_datetime(cand["Thời điểm BĐTH"], errors="coerce", dayfirst=True).dropna()
                    if not t.empty:
                        return t.iloc[0]
        return None

    mw40_target = (float(prof[_COL_MW].max()) * scale) if prof[_COL_MW].notna().any() else (mw40_override or 264.0)
    t40_data = _get_40pct_time_from_data(df_startup, mw40_target)

    if t40_data is not None and t40_data >= t0 and not syn40.empty:
        # tìm hàng 40% (MW lớn nhất) và copy ra để sửa
        last_idx = syn40["MW"].idxmax()
        mw40_row = syn40.loc[[last_idx]].copy()

        # không cho 40% đi lùi so với các mốc trước
        prev_max = syn40["Δt_min_abs"].iloc[:-1].max() if len(syn40) > 1 else 0.0
        dt_abs_data = (t40_data - t0).total_seconds() / 60.0
        dt_abs_final = max(dt_abs_data, prev_max)

        # cập nhật chính hàng 40% theo thời gian dữ liệu
        mw40_row.loc[:, "Δt_min_abs"] = round(dt_abs_final, 2)
        mw40_row.loc[:, "Time"] = t40_data

        # === ĐÈ LỆNH: cắt bỏ mọi mốc Syn→40% sau mốc 40% ===
        # chỉ giữ các điểm trước 40% và ghép đúng 1 điểm 40% vào
        syn40 = pd.concat([
            syn40[syn40["Δt_min_abs"] < dt_abs_final],  # giữ < cutoff
            mw40_row                                    # thêm hàng 40% mới
        ], ignore_index=True)

    # sắp xếp ổn định lại
    syn40["Δt_min_abs"] = ((syn40["Time"] - t0).dt.total_seconds() / 60.0).round(2)
    syn40 = syn40.sort_values(by=["Δt_min_abs","Time"], kind="mergesort").reset_index(drop=True)

    return syn40
def _last_bdth_in_window_raw(dfi: pd.DataFrame) -> Optional[pd.Timestamp]:
    """
    Trả về CHÍNH XÁC 'Thời điểm BĐTH' của DÒNG CUỐI trong dfi (DF*_STARTUP).
    Không fallback sang 'Thời điểm hoàn thành'.
    """
    if dfi.empty or ("Thời điểm BĐTH" not in dfi.columns):
        return None
    t = pd.to_datetime(dfi.iloc[-1]["Thời điểm BĐTH"], errors="coerce", dayfirst=True)
    return None if pd.isna(t) else t



def build_startup_timeline(
    df_startup: pd.DataFrame,
    unit: str = "",
    *,
    sync_offset_min: float = 0.0,
    mw40_override: float | None = None,
    mw100_override: float | None = None
) -> pd.DataFrame:
    """
    BĐTH → (Syn→40% absolute, đã bỏ mốc trùng Syn & chốt 40% theo dữ liệu) 
         → ramp/hold sau 40% với:
           - ĐÍCH = 'CS hoàn thành (MW)' của LỆNH ĐẦU TIÊN xuất hiện SAU khi đạt 40%.
           - THỜI ĐIỂM BẮT ĐẦU ramp sau 40% = 'Thời điểm BĐTH' của lệnh đó.
    """
    # 1) Syn→40%
    syn40 = build_syn40_absolute_points(
        df_startup, unit,
        sync_offset_min=sync_offset_min,
        mw40_override=mw40_override
    )
    if syn40.empty:
        return syn40

    stype = syn40["Type"].iloc[0]

    # === Lấy lại mốc BĐTH làm gốc thời gian tuyệt đối
    idxs = df_startup.index[df_startup["Case"] == "Khởi động lò"].tolist()
    if not idxs:
        return syn40
    i0 = idxs[0]
    t_start = pd.to_datetime(df_startup.loc[i0, "Thời điểm BĐTH"], errors="coerce", dayfirst=True)
    if pd.isna(t_start):
        return syn40

    # 2) Thông tin mốc 40%
    t40_row_idx = syn40["Δt_min_abs"].idxmax()
    t40_abs  = float(syn40.loc[t40_row_idx, "Δt_min_abs"])
    t40_time = syn40.loc[t40_row_idx, "Time"]
    mw_40    = float(syn40.loc[t40_row_idx, "MW"])

    # 3) 50% suy từ rated_guess (vẫn dựa logic profile)
    rated_guess = mw100_override if (mw100_override is not None) else (mw_40 / 0.4)
    mw_50       = 0.5 * rated_guess

    # 4) Tìm LỆNH ĐẦU TIÊN sau khi đạt 40%: lấy (t_cmd_start = BĐTH), (mw_target = CS hoàn thành (MW))
    def _next_cmd_after(dfi: pd.DataFrame, t_after: pd.Timestamp) -> tuple[Optional[pd.Timestamp], Optional[float]]:
        dfi2 = dfi.copy()
        t_done = pd.to_datetime(dfi2.get("Thời điểm hoàn thành"), errors="coerce", dayfirst=True)
        t_bd   = pd.to_datetime(dfi2.get("Thời điểm BĐTH"),       errors="coerce", dayfirst=True)
        evt_t  = t_done.where(~t_done.isna(), t_bd)

        cand = dfi2.loc[evt_t > t_after].copy()
        if cand.empty:
            return None, None

        # BĐTH của lệnh
        t_cmd_start = pd.to_datetime(cand.get("Thời điểm BĐTH"), errors="coerce", dayfirst=True).dropna()
        if t_cmd_start.empty:
            t_cmd_start = pd.to_datetime(cand.get("Thời điểm hoàn thành"), errors="coerce", dayfirst=True).dropna()
        t_cmd_start = t_cmd_start.iloc[0] if not t_cmd_start.empty else None

        # MW đích của lệnh
        mw_target = None
        for col in ["CS hoàn thành (MW)", "CS ra lệnh (MW)"]:
            if col in cand.columns:
                v = pd.to_numeric(cand[col], errors="coerce").dropna()
                if not v.empty:
                    mw_target = float(v.iloc[0])
                    break

        return t_cmd_start, mw_target

    t_cmd_start, mw_target_data = _next_cmd_after(df_startup, t40_time)

    # Mốc bắt đầu ramp sau 40% = BĐTH của lệnh đó (đảm bảo không đi lùi mốc 40%)
    if t_cmd_start is not None:
        start_after40_abs = max((t_cmd_start - t_start).total_seconds() / 60.0, t40_abs)
    else:
        start_after40_abs = t40_abs  # không có lệnh → bắt đầu ngay tại 40%

    # Đích cuối cùng
    if mw100_override is not None:
        mw_target = mw100_override
    elif mw_target_data is not None:
        mw_target = mw_target_data
    else:
        mw_target = rated_guess  # fallback khi dữ liệu thô không có lệnh tiếp theo


        # >>> NEW: Marker BĐTH (dòng cuối cửa sổ) — dùng NGUYÊN 'Thời điểm BĐTH' của dòng cuối
    rows_extra: List[Dict] = []

    t_last_raw = _last_bdth_in_window_raw(df_startup)  # lấy đúng cột 'Thời điểm BĐTH' của DÒNG CUỐI cửa sổ
    if t_last_raw is not None:
        ins_time = t_last_raw  # GIỮ NGUYÊN timestamp

        # đảm bảo mốc này nằm SAU mốc 40% và (nếu có) TRƯỚC khi bắt đầu ramp sau 40%
        lo_time = t40_time
        hi_time = t_start + pd.Timedelta(minutes=start_after40_abs)

        # đẩy rất nhẹ 1 giây nếu cần để không trùng đúng với lo/hi
        if (lo_time is not None) and (ins_time <= lo_time):
            ins_time = lo_time + pd.Timedelta(seconds=1)
        if (hi_time is not None) and (hi_time > lo_time) and (ins_time >= hi_time):
            ins_time = hi_time - pd.Timedelta(seconds=1)

        # Δt tính NGƯỢC LẠI từ 'ins_time' (để Δt và Time luôn khớp)
        dt_abs = (ins_time - t_start).total_seconds() / 60.0

        rows_extra.append({
            "Unit": unit,
            "Type": stype,
            "Phase": "BĐTH (dòng cuối cửa sổ)",
            "Δt_min_abs": round(float(dt_abs), 2),
            "Time": ins_time,      # giữ nguyên timestamp (có thể chỉ cộng/trừ 1 giây nếu cần)
            "MW": 264.0,
        })


    # 5) RAMP/HOLD sau 40%
    ramp40 = _get_after40_ramp_df(stype)
    t_curr_abs = start_after40_abs
    mw_curr    = mw_40

    if not ramp40.empty:
        # 5.1 Ramp 40% → min(50%, đích)
        rate1   = float(ramp40.iloc[0]["MW_per_min"])
        end1_mw = min(mw_50, mw_target)
        if rate1 > 0 and end1_mw > mw_curr:
            t_need    = (end1_mw - mw_curr) / rate1
            t_curr_abs = start_after40_abs + t_need
            mw_curr    = end1_mw
            rows_extra.append({
                "Unit": unit, "Type": stype, "Phase": "40%→50% (end)",
                "Δt_min_abs": round(t_curr_abs, 2),
                "Time": t_start + pd.Timedelta(minutes=t_curr_abs),
                "MW": round(mw_curr, 3),
            })

        # 5.2 Hold @50% (chỉ khi còn đi tiếp lên >50%)
        hold_row = ramp40[ramp40["Stage"] == _STAGE_HOLD]
        if (mw_target > mw_50) and (not hold_row.empty):
            hold_mins = float(hold_row["Hold_mins"].iloc[0])
            if hold_mins > 0:
                t_curr_abs += hold_mins
                rows_extra.append({
                    "Unit": unit, "Type": stype, "Phase": "Hold@50% (end)",
                    "Δt_min_abs": round(t_curr_abs, 2),
                    "Time": t_start + pd.Timedelta(minutes=t_curr_abs),
                    "MW": round(mw_curr, 3),
                })

        # 5.3 Ramp 50% → đích (nếu đích > mw_curr)
        rate2 = float(ramp40.iloc[-1]["MW_per_min"])
        if rate2 > 0 and mw_target > mw_curr:
            t_need    = (mw_target - mw_curr) / rate2
            t_curr_abs += t_need
            mw_curr     = mw_target
            rows_extra.append({
                "Unit": unit, "Type": stype, "Phase": "50%→100% (end)",  # giữ label cũ cho UI
                "Δt_min_abs": round(t_curr_abs, 2),
                "Time": t_start + pd.Timedelta(minutes=t_curr_abs),
                "MW": round(mw_curr, 3),
            })

    after40_df = pd.DataFrame(rows_extra, columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    # 6) Gộp & sắp xếp
    out = pd.concat([syn40, after40_df], ignore_index=True)   # <- THÊM DÒNG NÀY

    if out.empty:
        return out

    # Đồng bộ lại Δt dựa trên Time để thứ tự liền mạch
    out["Δt_min_abs"] = ((out["Time"] - t_start).dt.total_seconds() / 60.0).round(2)
    # trị số âm rất nhỏ do cộng/trừ 1 giây để tránh trùng mốc -> kẹp về 0
    out.loc[out["Δt_min_abs"] < 0, "Δt_min_abs"] = 0.0
    out = out.sort_values(by=["Δt_min_abs", "Time"], kind="mergesort").reset_index(drop=True)
    return out






# =========================================================
# 5) TÓM TẮT NHANH HAI TỔ MÁY
# =========================================================

def compute_startup_table(df1_startup: pd.DataFrame, df2_startup: pd.DataFrame) -> pd.DataFrame:
    """
    Trả bảng 2 hàng: Unit | Hours | Type (để show nhanh trên UI)
    """
    r1 = classify_startup(df1_startup, "S1")
    r2 = classify_startup(df2_startup, "S2")
    return pd.DataFrame([r1, r2], columns=["Unit", "Hours", "Type"])


# =========================================================
# 6) MỐC BĐTH & SYN + OFFSET
# =========================================================

def _get_event_time(df_startup: pd.DataFrame, case_keyword: str):
    """
    Tìm thời điểm đầu tiên có Case chứa 'case_keyword' (không phân biệt hoa/thường).
    Ưu tiên 'Thời điểm BĐTH'; nếu trống thì fallback 'Thời điểm hoàn thành'.

    ĐẶC BIỆT: nếu case_keyword = 'Hòa lưới' mà KHÔNG tìm thấy theo text,
    sẽ FALLBACK lấy ngay dòng kế tiếp của 'Khởi động lò' (i+1) làm mốc Hòa lưới.
    """
    import re
    import unicodedata

    def _norm(s):
        return unicodedata.normalize("NFC", "" if pd.isna(s) else str(s)).strip()

    if "Case" not in df_startup.columns:
        return None

    dfi = df_startup.copy()
    dfi["Case"] = dfi["Case"].map(_norm)

    # 1) cố gắng match theo text trước
    if case_keyword.lower() == "hòa lưới":
        patterns = [
            r"\bHòa lưới\b", r"\bHoà lưới\b",
            r"\bHòa lưới\s*\(Syn\)\b", r"\bSyn\b",
            r"\bĐồng bộ\b", r"\bĐồng bộ máy phát\b",
        ]
        pat = re.compile("|".join(patterns), flags=re.IGNORECASE)
        m = dfi["Case"].str.contains(pat, na=False)
    elif case_keyword.lower() == "khởi động lò":
        m = dfi["Case"].str.contains(r"\bKhởi động lò\b", case=False, na=False)
    else:
        m = dfi["Case"].str.contains(re.escape(case_keyword), case=False, na=False)

    if m.any():
        i = m.idxmax()
        t_bd = pd.to_datetime(dfi.loc[i, "Thời điểm BĐTH"], errors="coerce", dayfirst=True)
        if pd.isna(t_bd):
            t_bd = pd.to_datetime(dfi.loc[i, "Thời điểm hoàn thành"], errors="coerce", dayfirst=True)
        return None if pd.isna(t_bd) else t_bd

    # 2) FALLBACK đặc thù: Hòa lưới = dòng kế tiếp của 'Khởi động lò'
    if case_keyword.lower() == "hòa lưới":
        m_kdl = dfi["Case"].str.contains(r"\bKhởi động lò\b", case=False, na=False)
        if m_kdl.any():
            i = m_kdl.idxmax()
            j = i + 1
            if j in dfi.index:
                t_bd = pd.to_datetime(dfi.loc[j, "Thời điểm BĐTH"], errors="coerce", dayfirst=True)
                if pd.isna(t_bd):
                    t_bd = pd.to_datetime(dfi.loc[j, "Thời điểm hoàn thành"], errors="coerce", dayfirst=True)
                return None if pd.isna(t_bd) else t_bd

    return None


def compute_start_and_sync(df_startup: pd.DataFrame) -> Dict[str, Optional[pd.Timestamp]]:
    """Trả về {'t_start': ..., 't_syn': ...} (có thể None)."""
    t_start = _get_event_time(df_startup, "Khởi động lò")
    t_syn   = _get_event_time(df_startup, "Hòa lưới")
    return {"t_start": t_start, "t_syn": t_syn}


def compute_sync_offset_minutes(t_start: Optional[pd.Timestamp],
                                t_syn: Optional[pd.Timestamp]) -> float:
    """Offset phút từ BĐTH -> Hòa lưới; thiếu mốc hoặc t_syn <= t_start → 0.0"""
    if (t_start is None) or (t_syn is None):
        return 0.0
    dt = (t_syn - t_start).total_seconds() / 60.0
    return float(dt) if dt > 0 else 0.0


def _make_start_sync_markers(unit: str,
                             stype: Optional[str],
                             t_start: Optional[pd.Timestamp],
                             t_syn: Optional[pd.Timestamp]) -> pd.DataFrame:
    """Tạo 2 dòng marker để gắn vào timeline."""
    rows: List[Dict] = []
    if t_start is not None:
        rows.append({
            "Unit": unit, "Type": stype, "Phase": "Khởi động lò (BĐTH)",
            "Δt_min_abs": 0.0, "Time": t_start, "MW": 0.0
        })
    if (t_start is not None) and (t_syn is not None) and (t_syn >= t_start):
        dt_min = (t_syn - t_start).total_seconds() / 60.0
        rows.append({
            "Unit": unit, "Type": stype, "Phase": "Hòa lưới (Syn)",
            "Δt_min_abs": round(float(dt_min), 2), "Time": t_syn, "MW": 0.0
        })
    return pd.DataFrame(rows, columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])


# =========================================================
# 7) TIMELINE + MARKERS (BĐTH & SYN) — WRAPPER TRỌN GÓI
# =========================================================

def build_startup_timeline_with_markers(
    df_startup: pd.DataFrame,
    unit: str = "",
    *,
    mw40_override: float | None = None,
    mw100_override: float | None = None,
    sync_mode: str = "expected",           # "observed" | "expected" | "override"
    expected_sync_minutes: float | None = None  # dùng khi sync_mode="override"
) -> pd.DataFrame:
    """
    Wrapper dựng timeline và chèn marker:
      - sync_mode="observed": dùng mốc Hòa lưới lấy từ dữ liệu gốc (mặc định cũ).
      - sync_mode="expected": dùng 'SynMinutes' tra theo loại start-up (light-off -> sync).
      - sync_mode="override": dùng 'expected_sync_minutes' do người dùng chỉ định.
    """

    # 1) BĐTH (light-off)
    t_dict = compute_start_and_sync(df_startup)
    t_start = t_dict["t_start"]        # bắt buộc phải có để làm mốc
    if t_start is None:
        # không có BĐTH thì không dựng được gì
        return pd.DataFrame(columns=["Unit","Type","Phase","Δt_min_abs","Time","MW"])

    # 2) Phân loại để gán Type & tra phút kỳ vọng
    meta  = classify_startup(df_startup, unit)   # {"Unit","Hours","Type","SynMinutes"}
    stype = meta.get("Type")
    syn_min_table = meta.get("SynMinutes")  # có thể None nếu chưa phân loại

    # 3) Quyết định offset phút BĐTH -> Syn theo mode
    if sync_mode == "observed":
        # lấy từ dữ liệu gốc như trước đây
        t_syn_obs = t_dict["t_syn"]
        sync_offset_min = compute_sync_offset_minutes(t_start, t_syn_obs)

        # dùng lại timestamp quan sát cho marker (nếu có), else marker Syn không hiện
        t_syn_for_marker = t_syn_obs if sync_offset_min > 0 else None

    elif sync_mode == "expected":
        # tra bảng theo loại start-up
        if syn_min_table is None:
            # không tra được → rơi về 0 phút (chỉ có marker BĐTH)
            sync_offset_min = 0.0
            t_syn_for_marker = None
        else:
            sync_offset_min = float(syn_min_table)
            t_syn_for_marker = t_start + pd.Timedelta(minutes=sync_offset_min)

    elif sync_mode == "override":
        # người dùng chỉ định trực tiếp phút từ light-off tới sync
        if expected_sync_minutes is None or expected_sync_minutes < 0:
            sync_offset_min = 0.0
            t_syn_for_marker = None
        else:
            sync_offset_min = float(expected_sync_minutes)
            t_syn_for_marker = t_start + pd.Timedelta(minutes=sync_offset_min)

    else:
        raise ValueError("sync_mode must be one of: 'observed', 'expected', 'override'")

    # 4) Build timeline với offset đã quyết định
    base = build_startup_timeline(
        df_startup, unit,
        sync_offset_min=sync_offset_min,
        mw40_override=mw40_override,
        mw100_override=mw100_override
    )

    # 5) Chèn markers (BĐTH luôn có; Syn chỉ khi xác định được)
    markers = _make_start_sync_markers(unit, stype, t_start, t_syn_for_marker)

    if base.empty and markers.empty:
        return base  # rỗng cả hai

    out = pd.concat([markers, base], ignore_index=True)
    out = out.sort_values(by=["Δt_min_abs", "Time"], kind="mergesort").reset_index(drop=True)
    return out

# =========================================================
# 8) TỪ TIMELINE → SEGMENTS → MINUTELY (và HOURLY nếu cần)
# =========================================================
import pandas as pd
from typing import Optional, Tuple

def _timeline_to_segments_df(timeline: pd.DataFrame) -> list[pd.DataFrame]:
    """
    Đưa timeline (cột 'Time'/'Thời điểm', 'MW') về 1 danh sách segment (ít nhất 2 điểm).
    Nếu timeline trống hoặc không đủ điểm → [].
    """
    if timeline is None or timeline.empty:
        return []
    t = timeline.copy()
    # Chuẩn hoá tên cột thời gian
    if "Time" in t.columns and "Thời điểm" not in t.columns:
        t = t.rename(columns={"Time": "Thời điểm"})
    # Ép kiểu
    t["Thời điểm"] = pd.to_datetime(t["Thời điểm"], errors="coerce")
    t["MW"] = pd.to_numeric(t["MW"], errors="coerce")
    t = t.dropna(subset=["Thời điểm", "MW"]).sort_values("Thời điểm").reset_index(drop=True)
    # Cần >=2 điểm để nội suy
    return [t[["Thời điểm", "MW"]]] if len(t) >= 2 else []

def build_startup_minutely_from_timeline(
    timeline: pd.DataFrame,
    *,
    freq: str = "T",
    include_edge_minutes: bool = True,
    gap_policy: str = "none",
    eps: float = 1e-6,
) -> pd.DataFrame:
    """
    Quy đổi một timeline đã dựng sang chuỗi phút (minutely).
    - `gap_policy`: "none" | "nan" | "ffill" | "bridge_linear"
    """
    segments = _timeline_to_segments_df(timeline)
    if not segments:
        return pd.DataFrame(columns=["Thời điểm", "MW"])

    # import cục bộ để tránh vòng phụ thuộc giữa các module
    from tab_module.calculation_modules.ppa_minutely import ppa_segments_to_minutely

    return ppa_segments_to_minutely(
        segments,
        freq=freq,
        include_pair_idx=False,
        include_edge_minutes=include_edge_minutes,
        eps=eps,
        gap_policy=gap_policy,
    )

def build_startup_minutely_from_df_startup(
    df_startup: pd.DataFrame,
    unit: str = "",
    *,
    freq: str = "T",
    include_edge_minutes: bool = True,
    gap_policy: str = "none",
    eps: float = 1e-6,
    # các override/mode nếu muốn đi cùng logic dựng timeline
    mw40_override: float | None = None,
    mw100_override: float | None = None,
    sync_mode: str = "expected",
    expected_sync_minutes: float | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    One-shot: DF*_STARTUP → (timeline, minutely)
    - Trả về (timeline, minutely). `timeline` là kết quả từ build_startup_timeline_with_markers.
    - `minutely` là chuỗi phút nội suy từ chính timeline đó.
    """
    timeline = build_startup_timeline_with_markers(
        df_startup, unit,
        mw40_override=mw40_override,
        mw100_override=mw100_override,
        sync_mode=sync_mode,
        expected_sync_minutes=expected_sync_minutes
    )
    minutely = build_startup_minutely_from_timeline(
        timeline,
        freq=freq,
        include_edge_minutes=include_edge_minutes,
        gap_policy=gap_policy,
        eps=eps,
    )
    return timeline, minutely

def build_startup_minutely_hourly_from_df_startup(
    df_startup: pd.DataFrame,
    unit: str = "",
    *,
    freq: str = "T",
    include_edge_minutes: bool = True,
    gap_policy: str = "none",
    eps: float = 1e-6,
    mw40_override: float | None = None,
    mw100_override: float | None = None,
    sync_mode: str = "expected",
    expected_sync_minutes: float | None = None,
    hourly_label: str = "right",
    drop_incomplete: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    One-shot: DF*_STARTUP → (timeline, minutely, hourly)
    - hourly dùng lại minutely_to_hourly_avg để tổng hợp giờ.
    """
    timeline, minutely = build_startup_minutely_from_df_startup(
        df_startup, unit,
        freq=freq,
        include_edge_minutes=include_edge_minutes,
        gap_policy=gap_policy,
        eps=eps,
        mw40_override=mw40_override,
        mw100_override=mw100_override,
        sync_mode=sync_mode,
        expected_sync_minutes=expected_sync_minutes,
    )

    # import cục bộ để tránh phụ thuộc cứng
    from tab_module.calculation_modules.export_utils import minutely_to_hourly_avg
    hourly = minutely_to_hourly_avg(
        minutely,
        freq=freq,
        drop_incomplete=drop_incomplete,
        label=hourly_label
    )
    return timeline, minutely, hourly
