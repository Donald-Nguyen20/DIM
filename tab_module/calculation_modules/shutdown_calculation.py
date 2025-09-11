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
) -> pd.DataFrame:
    """
    Dựng timeline tuyệt đối cho shutdown bắt đầu tại mốc 40% (t40).
    - t40: timestamp mốc 40% (ví dụ thời điểm 'Ngừng tổ máy' bạn đã trích)
    - mw40: công suất tại 40% (mặc định 264 MW)
    - profile_rel: tuỳ chọn, nếu muốn thay profile mặc định.

    Trả DataFrame cột: ['Unit','Phase','Δt_min_abs','Time','MW']
    """
    if t40 is None or pd.isna(t40):
        return pd.DataFrame(columns=["Unit", "Phase", "Δt_min_abs", "Time", "MW"])

    prof = profile_rel if profile_rel is not None else _SHUTDOWN_PROFILE_REL

    rows = []
    for offset_min, frac in prof:
        mw = float(mw40) * float(frac)
        rows.append({
            "Unit": unit,
            "Phase": "Shutdown 40%→0%",
            "Δt_min_abs": round(float(offset_min), 2),
            "Time": pd.to_datetime(t40) + pd.Timedelta(minutes=float(offset_min)),
            "MW": round(float(mw), 3),
        })

    out = pd.DataFrame(rows, columns=["Unit", "Phase", "Δt_min_abs", "Time", "MW"])
    if out.empty:
        return out

    # Đồng bộ lại Δt theo Time để đảm bảo nhất quán
    t0 = pd.to_datetime(t40)
    out["Δt_min_abs"] = ((pd.to_datetime(out["Time"]) - t0).dt.total_seconds() / 60.0).round(2)
    out = out.sort_values(by=["Δt_min_abs", "Time"], kind="mergesort").reset_index(drop=True)
    return out


def build_shutdown_minutely_from_t40(
    t40: Optional[pd.Timestamp],
    unit: str = "",
    *,
    mw40: float = 264.0,
    freq: str = "T",
    include_edge_minutes: bool = True,
    gap_policy: str = "none",
    eps: float = 1e-6,
    profile_rel: Optional[List[tuple[float, float]]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    One-shot: Từ mốc 40% (t40) -> (timeline, minutely).
    - timeline: dựng bằng build_shutdown_timeline_from_t40(...)
    - minutely: nội suy theo phút từ chính timeline đó, dùng ppa_segments_to_minutely
    """
    # 1) Dựng timeline
    timeline = build_shutdown_timeline_from_t40(
        t40, unit, mw40=mw40, profile_rel=profile_rel
    )

    if timeline.empty:
        return timeline, pd.DataFrame(columns=["Thời điểm", "MW"])

    # 2) Quy đổi ra chuỗi phút
    segments = _timeline_to_segments_df(timeline)

    # import cục bộ để tránh phụ thuộc vòng
    from tab_module.calculation_modules.ppa_minutely import ppa_segments_to_minutely

    minutely = ppa_segments_to_minutely(
        segments,
        freq=freq,
        include_pair_idx=False,
        include_edge_minutes=include_edge_minutes,
        eps=eps,
        gap_policy=gap_policy,
    )
    return timeline, minutely
