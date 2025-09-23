# ppa_minutely.py
import math
import pandas as pd
from typing import List, Optional, Tuple

def ppa_segments_to_minutely(
    segments: List[pd.DataFrame],
    freq: str = "T",                   # "T" = 1 phút; ví dụ "30S", "5T"...
    include_pair_idx: bool = False,    # gắn pair_idx cho từng mốc phút (ở đây sẽ trả theo pair nếu bật)
    include_edge_minutes: bool = True, # (không còn ảnh hưởng trong mode tích phân, giữ để tương thích)
    eps: float = 1e-6,                 # (giữ nguyên chữ ký)
    gap_policy: str = "none",          # "none" | "nan" (giữ lại các lựa chọn an toàn)
) -> pd.DataFrame:
    """
    Chuyển các segments (đã UNIVERSAL CUT) thành chuỗi phút time-weighted theo 'freq'.

    Quy tắc:
      - Binning LPRO: mỗi phút là [mm:00, mm+Δ) -> điểm đúng mm+Δ thuộc phút sau, tránh double-count.
      - Trong từng phút, chèn mọi mốc event rơi bên trong rồi tích phân theo đoạn:
            MW_minute = (1/Δ) * Σ (dt_i * (MW(t_i)+MW(t_{i+1}))/2)
      - Nếu phút giao nhiều segment: cộng dồn diện tích các phần rồi chia Δ.

    Lưu ý:
      - include_pair_idx=True: trả giá trị theo từng pair (một phút có thể có nhiều hàng với pair khác nhau).
      - gap_policy:
          * "none": chỉ sinh những phút có giao với ít nhất một segment.
          * "nan" : sinh đủ dải phút liên tục từ min_start đến max_end; phút không giao = NaN.
    """
    # ---------- Helpers giữ nguyên tên ----------
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

    # Nội suy giá trị tại đúng thời điểm bên trong 1 segment (ramp tuyến tính / hold phẳng)
    def _value_at_in_segment(ts: pd.Timestamp, times: List[pd.Timestamp], mws: List[float]) -> float:
        if ts <= times[0]:
            return float(mws[0])
        if ts >= times[-1]:
            return float(mws[-1])
        # tìm [k, k+1] sao cho times[k] <= ts <= times[k+1]
        lo, hi = 0, len(times) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if times[mid] <= ts:
                lo = mid
            else:
                hi = mid
        t0, t1 = times[lo], times[lo+1]
        m0, m1 = float(mws[lo]), float(mws[lo+1])
        dur = (t1 - t0).total_seconds()
        if dur <= 0:
            return m1
        if abs(m1 - m0) <= eps:  # hold phẳng
            return m0
        frac = (ts - t0).total_seconds() / dur
        if frac < 0: frac = 0.0
        if frac > 1: frac = 1.0
        return m0 + (m1 - m0) * frac

    # ---------- Chuẩn hóa segments ----------
    norm: List[Tuple[int, pd.DataFrame, pd.Timestamp, pd.Timestamp]] = []
    for i, seg in enumerate(segments):
        s = _normalize_segment(seg)
        if s is None:
            continue
        t0, t1 = s["Thời điểm"].iloc[0], s["Thời điểm"].iloc[-1]
        norm.append((i, s, t0, t1))

    cols = ["pair_idx", "Thời điểm", "MW"] if include_pair_idx else ["Thời điểm", "MW"]
    if not norm:
        return pd.DataFrame(columns=cols)

    # ---------- Khung thời gian & bins phút ----------
    step = _freq_offset(freq)
    global_start = min(t0 for _,_,t0,_ in norm)
    global_end   = max(t1 for _,_,_,t1 in norm)
    # Danh sách đầu phút toàn cục để phục vụ gap_policy="nan"
    minute_starts_all = list(pd.date_range(start=_floor_tick(global_start, freq),
                                           end=_floor_tick(global_end, freq),
                                           freq=freq))
    width_sec = int(pd.to_timedelta(step).total_seconds())

    # ---------- Tích phân theo phút ----------
    from collections import defaultdict

    if include_pair_idx:
        # tích phân riêng cho từng pair
        acc_pair = defaultdict(float)  # key=(pair_idx, minute_start) -> area (MW*sec)
        for i, s, seg_start, seg_end in norm:
            times = s["Thời điểm"].tolist()
            mws   = s["MW"].astype(float).tolist()

            m_cur = _floor_tick(seg_start, freq)
            m_last = _floor_tick(seg_end, freq)
            while m_cur <= m_last:
                m_start = m_cur
                m_end   = m_cur + step
                # phần giao thật sự
                a = max(m_start, seg_start)
                b = min(m_end, seg_end)
                if b > a:
                    # breakpoints trong (a,b): mọi mốc event của segment
                    events_inside = [t for t in times if (a < t < b)]
                    B = [a] + sorted(events_inside) + [b]
                    area = 0.0
                    for x, y in zip(B[:-1], B[1:]):
                        v0 = _value_at_in_segment(x, times, mws)
                        v1 = _value_at_in_segment(y, times, mws)
                        dt = (y - x).total_seconds()
                        area += dt * 0.5 * (v0 + v1)
                    acc_pair[(i, m_start)] += area
                m_cur = m_cur + step

        rows = []
        if (gap_policy or "none").lower() == "nan":
            # sinh đủ phút theo từng pair xuất hiện
            # (để đơn giản và an toàn: chỉ sinh phút có vùng segment cho pair đó;
            #  nếu muốn sinh full nan cho mọi phút giữa min/max toàn cục per pair, cần track min/max theo pair)
            for (i, m), area in sorted(acc_pair.items()):
                rows.append((i, m, float(area / width_sec)))
        else:
            for (i, m), area in sorted(acc_pair.items()):
                rows.append((i, m, float(area / width_sec)))

        out = pd.DataFrame(rows, columns=["pair_idx", "Thời điểm", "MW"])
        # bảo toàn 1 hàng / (pair_idx, Thời điểm)
        out = (out.sort_values(["pair_idx", "Thời điểm"])
                  .drop_duplicates(subset=["pair_idx", "Thời điểm"], keep="last")
                  .reset_index(drop=True))
        return out

    else:
        # tích phân gộp (không theo pair)
        acc = defaultdict(float)  # key=minute_start -> area (MW*sec)
        for _, s, seg_start, seg_end in norm:
            times = s["Thời điểm"].tolist()
            mws   = s["MW"].astype(float).tolist()

            m_cur = _floor_tick(seg_start, freq)
            m_last = _floor_tick(seg_end, freq)
            while m_cur <= m_last:
                m_start = m_cur
                m_end   = m_cur + step
                a = max(m_start, seg_start)
                b = min(m_end, seg_end)
                if b > a:
                    events_inside = [t for t in times if (a < t < b)]
                    B = [a] + sorted(events_inside) + [b]
                    area = 0.0
                    for x, y in zip(B[:-1], B[1:]):
                        v0 = _value_at_in_segment(x, times, mws)
                        v1 = _value_at_in_segment(y, times, mws)
                        dt = (y - x).total_seconds()
                        area += dt * 0.5 * (v0 + v1)
                    acc[m_start] += area
                m_cur = m_cur + step

        rows = []
        if (gap_policy or "none").lower() == "nan":
            for m in minute_starts_all:
                mw = (acc[m] / width_sec) if m in acc else float("nan")
                rows.append((m, float(mw)))
        else:
            for m, area in sorted(acc.items()):
                rows.append((m, float(area / width_sec)))

        out = pd.DataFrame(rows, columns=["Thời điểm", "MW"])
        out = (out.sort_values("Thời điểm")
                  .drop_duplicates(subset=["Thời điểm"], keep="last")
                  .reset_index(drop=True))
        return out

