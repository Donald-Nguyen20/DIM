# shutdown_calculation.py
"""
Dựng timeline & chuỗi phút cho giai đoạn SHUTDOWN theo profile cố định
(Time from 40% load to 0% load).

Profile (offset phút kể từ mốc 40%):
  (0,   1.00*MW40)   # hold @40%
  (40,  1.00*MW40)
  (50,  0.75*MW40)   # ramp xuống 0.75*MW40 trong 10'
  (105, 0.75*MW40)   # hold @0.75*MW40 trong 55'
  (135, 0.00)        # ramp xuống 0 trong 30'

Trả về:
- build_shutdown_timeline_from_t40(...)  -> timeline (DataFrame)
- build_shutdown_minutely_from_t40(...)  -> (timeline, minutely)
"""

from __future__ import annotations
from typing import Optional, Tuple, List
import pandas as pd


# Thay thế helper cũ bằng helper mới theo giây
def _time_to_reach_264_seconds(
    pre_mw: float,
    *,
    rate_mw_per_sec: float = 0.22,   # 13.2 MW/min = 0.22 MW/s
    allow_ramp_up_if_below: bool = False,
    tol_mw: float = 1e-6
) -> float:
    """
    Tính số GIÂY cần để từ pre_mw -> 264 MW với rate cố định (MW/s).
    - Nếu pre_mw > 264: giảm về 264.
    - Nếu pre_mw < 264: trả 0 trừ khi allow_ramp_up_if_below=True (kéo lên 264).
    Trả về: giây (float, >=0)
    """
    target = 264.0
    if abs(pre_mw - target) <= tol_mw:
        return 0.0
    if pre_mw > target:
        return (pre_mw - target) / max(rate_mw_per_sec, 1e-12)
    else:
        if allow_ramp_up_if_below:
            return (target - pre_mw) / max(rate_mw_per_sec, 1e-12)
        return 0.0


# Profile tương đối theo MW40 (40% tải)
# (offset_min, fraction_of_mw40)
_SHUTDOWN_PROFILE_REL: List[tuple[float, float]] = [
    (0.0,   1.00),
    (40.0,  1.00),
    (50.0,  0.75),
    (105.0, 0.75),
    (135.0, 0.00),
]


def _timeline_to_segments_df(timeline: pd.DataFrame) -> list[pd.DataFrame]:
    """
    Chuẩn hoá timeline -> danh sách 1 segment chuẩn có cột ['Thời điểm', 'MW'].
    Trả [] nếu không đủ điểm để nội suy.
    """
    if timeline is None or timeline.empty:
        return []
    t = timeline.copy()

    # Chuẩn tên cột thời gian
    if "Time" in t.columns and "Thời điểm" not in t.columns:
        t = t.rename(columns={"Time": "Thời điểm"})

    # Ép kiểu + lọc hợp lệ
    t["Thời điểm"] = pd.to_datetime(t["Thời điểm"], errors="coerce")
    t["MW"] = pd.to_numeric(t["MW"], errors="coerce")
    t = t.dropna(subset=["Thời điểm", "MW"]).sort_values("Thời điểm").reset_index(drop=True)

    return [t[["Thời điểm", "MW"]]] if len(t) >= 2 else []


def build_shutdown_timeline_from_t40(
    t40: Optional[pd.Timestamp],
    unit: str = "",
    *,
    mw40: float = 264.0,
    profile_rel: Optional[List[tuple[float, float]]] = None,

    # NEW: dữ liệu “dòng trước shutdown”
    pre_time: Optional[pd.Timestamp] = None,
    pre_mw: Optional[float] = None,

    # NEW: tốc độ ramp cố định theo giây
    pre_rate_mw_per_sec: float = 0.22,     # 13.2 MW/min
    allow_ramp_up_if_below: bool = False,  # có kéo lên 264 nếu đang dưới 264?
) -> pd.DataFrame:
    if (pre_time is None or pd.isna(pre_time)) and (t40 is None or pd.isna(t40)):
        return pd.DataFrame(columns=["Unit","Phase","Δt_min_abs","Time","MW"])

    prof = profile_rel if profile_rel is not None else _SHUTDOWN_PROFILE_REL
    rows: List[dict] = []

    # ---- 1) Tính mốc 40% hiệu lực = t_264 (giây) ----
    t_264 = None
    if (pre_time is not None) and (pre_mw is not None):
        t_prev = pd.to_datetime(pre_time, errors="coerce")
        if t_prev is not None and not pd.isna(t_prev):
            pre_mw_f = float(pre_mw)
            dt_sec = _time_to_reach_264_seconds(
                pre_mw_f,
                rate_mw_per_sec=pre_rate_mw_per_sec,
                allow_ramp_up_if_below=allow_ramp_up_if_below
            )
            t_264 = t_prev + pd.Timedelta(seconds=dt_sec)
            # Ghép pre-ramp/hold (độ phân giải giây)
            if dt_sec > 0:
                phase_name = "Pre→40% (ramp up)" if (pre_mw_f < mw40) else "Pre→40% (ramp)"
                rows.append({"Unit": unit, "Phase": phase_name, "Time": t_prev, "MW": round(pre_mw_f, 3)})

    # Fallback nếu thiếu pre_*: dùng t40 (backward compatible)
    if t_264 is None:
        if t40 is None or pd.isna(t40):
            return pd.DataFrame(columns=["Unit","Phase","Δt_min_abs","Time","MW"])
        t_264 = pd.to_datetime(t40)

    # ---- 2) Áp profile shutdown kể từ t_264 ----
    for offset_min, frac in prof:
        rows.append({
            "Unit": unit,
            "Phase": "Shutdown 40%→0%",
            "Time": t_264 + pd.Timedelta(minutes=float(offset_min)),
            "MW": round(float(mw40) * float(frac), 3),
        })

    out = pd.DataFrame(rows, columns=["Unit","Phase","Time","MW"])
    if out.empty:
        return out

    # Δt tính từ t_264 (vẫn biểu diễn bằng phút để hợp UI)
    out["Time"] = pd.to_datetime(out["Time"])
    out["Δt_min_abs"] = ((out["Time"] - t_264).dt.total_seconds() / 60.0).round(2)
    out = out.sort_values(["Δt_min_abs","Time"], kind="mergesort").reset_index(drop=True)
    return out




def build_shutdown_minutely_from_t40(
    t40: Optional[pd.Timestamp],
    unit: str = "",
    *,
    mw40: float = 264.0,
    freq: str = "T",                       # có thể chuyển "S" để mịn hơn
    include_edge_minutes: bool = True,
    gap_policy: str = "none",
    eps: float = 1e-6,
    profile_rel: Optional[List[tuple[float, float]]] = None,

    pre_time: Optional[pd.Timestamp] = None,
    pre_mw: Optional[float] = None,
    pre_rate_mw_per_sec: float = 0.22,     # 13.2 MW/min
    allow_ramp_up_if_below: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    timeline = build_shutdown_timeline_from_t40(
        t40, unit,
        mw40=mw40, profile_rel=profile_rel,
        pre_time=pre_time, pre_mw=pre_mw,
        pre_rate_mw_per_sec=pre_rate_mw_per_sec,
        allow_ramp_up_if_below=allow_ramp_up_if_below,
    )
    if timeline.empty:
        return timeline, pd.DataFrame(columns=["Thời điểm","MW"])

    segments = _timeline_to_segments_df(timeline)
    from tab_module.calculation_modules.ppa_minutely import ppa_segments_to_minutely
    # 1) Kết quả mặc định (time-weighted) từ ppa_segments_to_minutely
    # 1) Kết quả mặc định (time-weighted) từ ppa_segments_to_minutely
    minutely = ppa_segments_to_minutely(
        segments, freq=freq, include_pair_idx=False,
        include_edge_minutes=include_edge_minutes, eps=eps, gap_policy=gap_policy,
    )

    # Không có segment thì trả luôn
    if not segments:
        return timeline, minutely

    # Hợp nhất các điểm gãy để nội suy MW(t) tuyến tính
    import numpy as np
    seg = segments[0].sort_values("Thời điểm").copy()
    seg["Thời điểm"] = pd.to_datetime(seg["Thời điểm"], errors="coerce")
    seg = seg.dropna(subset=["Thời điểm"])

    # Mảng thời gian & giá trị (kiểu datetime64[ns] để searchsorted an toàn)
    ts = seg["Thời điểm"].values.astype("datetime64[ns]")
    ys = seg["MW"].to_numpy(dtype=float)

    def mw_at_vector(tq_arr):
        """
        Nội suy MW tại các thời điểm tq_arr (np.ndarray of datetime64[ns]).
        - Tuyến tính giữa 2 mốc lân cận.
        - Clamp trước mốc đầu và sau mốc cuối.
        """
        tq64 = tq_arr.astype("datetime64[ns]")

        # mask trước/sau khoảng
        mask_before = tq64 < ts[0]
        mask_after  = tq64 >= ts[-1]

        # idx điểm trái cho mỗi tq (right-1)
        idx = np.searchsorted(ts, tq64, side="right") - 1
        # kẹp về [0, len(ts)-2] để lấy cặp (idx, idx+1)
        idx = np.clip(idx, 0, len(ts) - 2)

        t0 = ts[idx]
        t1 = ts[idx + 1]
        y0 = ys[idx]
        y1 = ys[idx + 1]

        dt = (t1 - t0).astype("timedelta64[ns]").astype(np.int64)
        # tránh chia 0: w=1 nếu dt=0 (coi dính vào điểm phải)
        w = np.zeros_like(dt, dtype=np.float64)
        nz = dt != 0
        w[nz] = ((tq64[nz] - t0[nz]).astype("timedelta64[ns]").astype(np.int64)) / dt[nz]
        w[~nz] = 1.0

        y = y0 + (y1 - y0) * w
        # clamp trước/sau
        y[mask_before] = ys[0]
        y[mask_after]  = ys[-1]
        return y

    # 2) Nếu freq = "S": left-sample tại chính biên trái mỗi giây
    if str(freq).upper() == "S":
        minutely = minutely.copy()
        ts_sec = pd.to_datetime(minutely["Thời điểm"], errors="coerce").values.astype("datetime64[ns]")
        minutely["MW"] = mw_at_vector(ts_sec)

    # 3) Nếu freq = "T": LẤY CUỐI PHÚT (m:59) cho từng phút
    elif str(freq).upper() == "T":
        minutely = minutely.copy()

        # 1) Lấy mốc "Pre→40%" (nếu có), nếu không có thì lấy mốc nhỏ nhất của timeline
        pre_rows = timeline[timeline["Phase"].astype(str).str.contains("Pre→40%", na=False)]
        if not pre_rows.empty:
            t_pre = pd.to_datetime(pre_rows["Time"].min())
        else:
            t_pre = pd.to_datetime(timeline["Time"].min())

        # 2) Mốc phút BẮT ĐẦU = phút liền sau t_pre (ví dụ 18:01:57 -> 18:02:00)
        m0 = t_pre.floor("T") + pd.Timedelta(minutes=1)

        # 3) Mốc phút KẾT THÚC: phút của thời điểm lớn nhất trong profile shutdown
        m_end = pd.to_datetime(timeline["Time"].max()).floor("T")

        if m0 <= m_end:
            # Dải phút m0 .. m_end
            tmins = pd.date_range(m0, m_end, freq="T")

            # Lấy "giá trị tại m:59" cho mỗi phút (right-edge sampling)
            import numpy as np
            edges = (tmins + pd.to_timedelta(59, unit="s")).values.astype("datetime64[ns]")
            mw_edges = mw_at_vector(edges)   # dùng hàm nội suy đã định nghĩa ở trên

            # Xuất time tại m:00 để tiện merge theo phút
            minutely = pd.DataFrame({"Thời điểm": tmins, "MW": mw_edges})
        else:
            minutely = pd.DataFrame(columns=["Thời điểm", "MW"])



    return timeline, minutely





