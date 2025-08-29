# ppa_minutely.py
import math
import pandas as pd
from typing import List, Optional, Tuple

def ppa_segments_to_minutely(
    segments: List[pd.DataFrame],
    freq: str = "T",                   # "T" = 1 phút; ví dụ "30S", "5T"...
    include_pair_idx: bool = False,    # gắn pair_idx cho từng mốc phút
    include_edge_minutes: bool = True, # thêm mốc phút trùng EXACT với event trong segment
    eps: float = 1e-6,                 # nhận diện flat: |m1 - m0| <= eps
    gap_policy: str = "none",          # "none" | "nan" | "ffill" | "bridge_linear"
) -> pd.DataFrame:
    """
    Chuyển các segments (đã CUT/SNAP) thành chuỗi phút theo tần suất 'freq'.

    NGUYÊN TẮC CHÍNH (NO-BRIDGE):
      - Bên trong MỖI segment:
          * HOLD (m1≈m0): giữ phẳng.
          * RAMP: nội suy tuyến tính theo CHÍNH 2 mốc của segment.
      - GIỮA HAI segment (khoảng trống/gap): mặc định KHÔNG sinh dữ liệu.
        Có thể bật qua 'gap_policy':
          * "none"          : không tạo điểm trong gap.
          * "nan"           : tạo điểm phút trong gap với MW = NaN.
          * "ffill"         : tạo điểm phút trong gap và điền MW = MW cuối của segment trước.
          * "bridge_linear" : nội suy tuyến tính từ (t_end,m_end) -> (t_start_next,m_start_next).

    Ghi chú:
      - Nếu hai segment CHẠM BIÊN (t_end == t_start_next) → không có gap.
      - Nếu một mốc event trùng phút, tick ở biên sẽ thuộc segment tương ứng,
        không để gap lấn vào (đã xử lý biên trái/phải cho an toàn).
    """
    # ---------- Helpers ----------
    def _floor_tick(ts: pd.Timestamp, f: str) -> pd.Timestamp:
        return pd.to_datetime(ts).floor(f)

    def _ceil_tick(ts: pd.Timestamp, f: str) -> pd.Timestamp:
        ts = pd.to_datetime(ts)
        fl = ts.floor(f)
        return ts if fl == ts else fl + pd.tseries.frequencies.to_offset(f)

    def _freq_offset(f: str):
        return pd.tseries.frequencies.to_offset(f)

    def _normalize_segment(seg: pd.DataFrame) -> Optional[pd.DataFrame]:
        if seg is None or getattr(seg, "empty", True):
            return None
        s = seg.copy()
        s["Thời điểm"] = pd.to_datetime(s["Thời điểm"], errors="coerce")
        s["MW"] = pd.to_numeric(s["MW"], errors="coerce")
        s = s.dropna(subset=["Thời điểm", "MW"]).sort_values("Thời điểm").reset_index(drop=True)
        return s if len(s) >= 2 else None

    def _interp_segment(times: List[pd.Timestamp], mws: List[float], ticks: List[pd.Timestamp]) -> List[Tuple[pd.Timestamp, float]]:
        """Nội suy ticks CHỈ dựa vào timeline của 1 segment."""
        out = []
        if len(times) < 2 or not ticks:
            return out
        k = 0
        for tick in ticks:
            while k + 1 < len(times) and tick > times[k+1]:
                k += 1
            if k + 1 >= len(times):
                break
            t0, t1 = times[k], times[k+1]
            m0, m1 = mws[k],  mws[k+1]
            if tick < t0:
                val = m0
            else:
                dur = (t1 - t0).total_seconds()
                if dur <= 0:
                    val = m1
                elif abs(m1 - m0) <= eps:     # HOLD phẳng
                    val = m0 if tick < t1 else m1
                else:                          # RAMP tuyến tính
                    frac = (tick - t0).total_seconds() / dur
                    if frac < 0: frac = 0.0
                    if frac > 1: frac = 1.0
                    val = m0 + (m1 - m0) * frac
            out.append((tick, float(val)))
        return out

    def _gap_ticks(t_end: pd.Timestamp, t_start_next: pd.Timestamp, f: str) -> List[pd.Timestamp]:
        """Sinh ticks trong gap (loại trừ chồng biên với 2 segment)."""
        off = _freq_offset(f)
        # Bên trái: nếu t_end trùng phút → bắt đầu từ t_end + off
        left = _ceil_tick(t_end, f)
        if _floor_tick(t_end, f) == t_end:
            left = t_end + off
        # Bên phải: nếu t_start_next trùng phút → kết thúc ở t_start_next - off
        right = _floor_tick(t_start_next, f)
        if _floor_tick(t_start_next, f) == t_start_next:
            right = t_start_next - off
        if right < left:
            return []
        return list(pd.date_range(start=left, end=right, freq=f))

    # ---------- Chuẩn hóa toàn bộ segments ----------
    norm = []
    for i, seg in enumerate(segments):
        s = _normalize_segment(seg)
        if s is None:
            continue
        t0, t1 = s["Thời điểm"].iloc[0], s["Thời điểm"].iloc[-1]
        norm.append((i, s, t0, t1))

    if not norm:
        cols = ["pair_idx", "Thời điểm", "MW"] if include_pair_idx else ["Thời điểm", "MW"]
        return pd.DataFrame(columns=cols)

    # Bảo toàn thứ tự input (pair_idx tăng dần)
    rows: List[Tuple] = []

    # ---------- Lấy mẫu phút TRONG từng segment ----------
    for i, s, t0, t1 in norm:
        start_tick = _ceil_tick(t0, freq)
        end_tick   = _floor_tick(t1, freq)
        ticks = list(pd.date_range(start=start_tick, end=end_tick, freq=freq)) if end_tick >= start_tick else []

        if include_edge_minutes:
            # chỉ thêm các event trùng EXACT mốc phút, và phải nằm trong phạm vi segment
            edges = [t for t in s["Thời điểm"].tolist() if _floor_tick(t, freq) == t and t0 <= t <= t1]
            ticks = sorted(set(ticks + edges))

        times = s["Thời điểm"].tolist()
        mws   = s["MW"].astype(float).tolist()
        interp = _interp_segment(times, mws, ticks)

        if include_pair_idx:
            rows += [(i, t, v) for (t, v) in interp]
        else:
            rows += [(t, v) for (t, v) in interp]

    # ---------- Xử lý GAP giữa các segment (tùy chọn) ----------
    gp = (gap_policy or "none").lower()
    if gp not in {"none", "nan", "ffill", "bridge_linear"}:
        gp = "none"

    if gp != "none":
        for k in range(len(norm) - 1):
            i, s_i, t0_i, t1_i = norm[k]
            j, s_j, t0_j, t1_j = norm[k+1]
            # Chỉ là gap khi t1_i < t0_j
            if not (t1_i < t0_j):
                continue

            ticks_gap = _gap_ticks(t1_i, t0_j, freq)
            if not ticks_gap:
                continue

            if gp == "nan":
                if include_pair_idx:
                    rows += [(i, t, math.nan) for t in ticks_gap]
                else:
                    rows += [(t, math.nan) for t in ticks_gap]

            elif gp == "ffill":
                mw_last = float(s_i["MW"].iloc[-1])
                if include_pair_idx:
                    rows += [(i, t, mw_last) for t in ticks_gap]
                else:
                    rows += [(t, mw_last) for t in ticks_gap]

            elif gp == "bridge_linear":
                tL, mL = s_i["Thời điểm"].iloc[-1], float(s_i["MW"].iloc[-1])
                tR, mR = s_j["Thời điểm"].iloc[0],  float(s_j["MW"].iloc[0])
                dur = (tR - tL).total_seconds()
                for t in ticks_gap:
                    if dur <= 0:
                        val = mL
                    else:
                        frac = (t - tL).total_seconds() / dur
                        if frac < 0: frac = 0.0
                        if frac > 1: frac = 1.0
                        val = mL + (mR - mL) * frac
                    if include_pair_idx:
                        rows.append((i, t, float(val)))  # gán về pair trước theo quy ước cũ
                    else:
                        rows.append((t, float(val)))

    # ---------- Trả kết quả ----------
    cols = ["pair_idx", "Thời điểm", "MW"] if include_pair_idx else ["Thời điểm", "MW"]
    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out

    if include_pair_idx:
        out = (out.sort_values(["pair_idx", "Thời điểm"])
                 .drop_duplicates(subset=["pair_idx", "Thời điểm"], keep="last")
                 .reset_index(drop=True))
    else:
        out = (out.sort_values("Thời điểm")
                 .drop_duplicates(subset=["Thời điểm"], keep="last")
                 .reset_index(drop=True))
    return out
