# epc_calculation.py
import pandas as pd
from datetime import timedelta


def build_epc_per_pair(
    df_step: pd.DataFrame,
    hold_up_at_429_sec: int = 30 * 60,    # Hold khi TĂNG qua 429
    hold_down_at_429_sec: int = 30 * 60,  # Hold khi GIẢM qua 429
    snap_tolerance_sec: int = 0,          # (để tương thích chữ ký; không ảnh hưởng cut)
    flag_col: str = "Dừng lệnh",          # (không ảnh hưởng đến cut)
    make_gap_pairs: bool = True,          # Khâu nối gap phẳng (hiếm gặp khi universal cut)
    gap_min_sec: int = 1                  # Ngưỡng tối thiểu tạo gap pair
):
    # ===== Tiền xử lý (giữ nguyên) =====
    if df_step.empty or "MW" not in df_step or "Thời điểm" not in df_step:
        return [], pd.DataFrame()

    df = df_step.copy()
    df["MW"] = pd.to_numeric(df["MW"], errors="coerce")
    df["Thời điểm"] = pd.to_datetime(df["Thời điểm"], errors="coerce")

    def _to_bool(x):
        if pd.isna(x): return False
        if isinstance(x, bool): return x
        if isinstance(x, (int, float)): return x != 0
        return str(x).strip().upper() in ("TRUE", "1", "T", "Y", "YES")

    if flag_col in df.columns:
        df["_FLAG_TRUE"] = df[flag_col].apply(_to_bool)
    else:
        df["_FLAG_TRUE"] = False

    df = df.dropna(subset=["MW", "Thời điểm"]).sort_values("Thời điểm").reset_index(drop=True)
    if len(df) < 2:
        return [], pd.DataFrame()

    # ===== Helper =====
    def ramp_dt(delta_mw, rate):  # rate: MW/s
        return timedelta(seconds=max(float(abs(delta_mw)) / float(rate), 0.0))

    def mw_at(
        time_point,
        t_start, mw_start,
        t_target, mw_tgt,
        hold_up_at_429_sec, hold_down_at_429_sec
    ) -> float:
        """
        MW theo quỹ đạo EPC tại 'time_point' khi đi từ (t_start, mw_start) -> (t_target, mw_tgt).
        Quy tắc EPC:
          - Lên: 0.11 dưới 330, 0.22 khi >=330; nếu băng 429 thì hold tại 429 (hold_up_at_429_sec).
          - Xuống: nếu băng 429 thì hold tại 429 (hold_down_at_429_sec); ngoài ra chọn rate
                   theo vùng 330: dùng 0.22 nếu có liên đới vùng >=330, ngược lại 0.11.
        """
        if time_point <= t_start:
            return float(mw_start)

        rate_low  = 0.11
        rate_fast = 0.22

        # LÊN
        if mw_tgt > mw_start:
            crosses_429 = (mw_start < 429.0 <= mw_tgt)
            if not crosses_429:
                rate = rate_fast if (mw_start >= 330.0 and mw_tgt >= 330.0) else rate_low
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(min(mw_start + rate * dt, mw_tgt))

            # có băng 429
            rate_to_429 = rate_low if (mw_start < 330.0) else rate_fast
            t_429 = t_start + ramp_dt(429.0 - mw_start, rate_to_429)
            if time_point <= t_429:
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(min(mw_start + rate_to_429 * dt, 429.0))

            # hold tại 429 nếu có
            if hold_up_at_429_sec > 0:
                hold_end = t_429 + timedelta(seconds=hold_up_at_429_sec)
                if time_point <= hold_end:
                    return 429.0
                dt_after = max((time_point - hold_end).total_seconds(), 0.0)
                return float(min(429.0 + rate_fast * dt_after, mw_tgt))
            else:
                dt_after = max((time_point - t_429).total_seconds(), 0.0)
                return float(min(429.0 + rate_fast * dt_after, mw_tgt))

        # XUỐNG
        if mw_tgt < mw_start:
            crosses_429 = (mw_start > 429.0 >= mw_tgt)
            if not crosses_429:
                # không băng 429
                rate = rate_fast if (mw_start >= 330.0 or mw_tgt >= 330.0) else rate_low
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(max(mw_start - rate * dt, mw_tgt))

            # có băng 429
            rate_to_429 = rate_fast if (mw_start >= 330.0) else rate_low
            t_429 = t_start + ramp_dt(mw_start - 429.0, rate_to_429)
            if time_point <= t_429:
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(max(mw_start - rate_to_429 * dt, 429.0))

            if hold_down_at_429_sec > 0:
                hold_end = t_429 + timedelta(seconds=hold_down_at_429_sec)
                if time_point <= hold_end:
                    return 429.0
                dt_after = max((time_point - hold_end).total_seconds(), 0.0)
                return float(max(429.0 - rate_fast * dt_after, mw_tgt))
            else:
                dt_after = max((time_point - t_429).total_seconds(), 0.0)
                return float(max(429.0 - rate_fast * dt_after, mw_tgt))

        # PHẲNG
        return float(mw_tgt)

    segments = []
    summary_rows = []

    # ===== Main loop =====
    for i in range(len(df) - 1):
        t_start = df.loc[i, "Thời điểm"]
        mw_start = float(df.loc[i, "MW"])
        t_next = df.loc[i + 1, "Thời điểm"]
        mw_tgt = float(df.loc[i + 1, "MW"])

        events, mws, times = [], [], []
        def push(ev, mw, t):
            events.append(ev); mws.append(float(mw)); times.append(t)

        push("start", mw_start, t_start)

        # ===== FINISH_T dự kiến (quỹ đạo EPC) =====
        hold_mw = None
        hold_start_t = None
        hold_end_t = None

        rate_low  = 0.11
        rate_fast = 0.22

        if mw_tgt > mw_start:
            if mw_start < 429.0 <= mw_tgt:
                rate_to_429 = rate_low if mw_start < 330.0 else rate_fast
                t_429 = t_start + ramp_dt(429.0 - mw_start, rate_to_429)
                if hold_up_at_429_sec > 0:
                    hold_mw = 429.0
                    hold_start_t = t_429
                    hold_end_t   = t_429 + timedelta(seconds=hold_up_at_429_sec)
                    push("hold_start", 429.0, hold_start_t)
                    push("hold_end",   429.0, hold_end_t)
                    t_after = hold_end_t
                else:
                    t_after = t_429
                finish_t = t_after if (mw_tgt == 429.0) else (t_after + ramp_dt(mw_tgt - 429.0, rate_fast))
                push("finish", mw_tgt, finish_t)
            else:
                rate = rate_fast if (mw_start >= 330.0 and mw_tgt >= 330.0) else rate_low
                finish_t = t_start + ramp_dt(mw_tgt - mw_start, rate)
                push("finish", mw_tgt, finish_t)

        elif mw_tgt < mw_start:
            if mw_start > 429.0 >= mw_tgt:
                rate_to_429 = rate_fast if mw_start >= 330.0 else rate_low
                t_429 = t_start + ramp_dt(mw_start - 429.0, rate_to_429)
                if hold_down_at_429_sec > 0:
                    hold_mw = 429.0
                    hold_start_t = t_429
                    hold_end_t   = t_429 + timedelta(seconds=hold_down_at_429_sec)
                    push("hold_start", 429.0, hold_start_t)
                    push("hold_end",   429.0, hold_end_t)
                    t_after = hold_end_t
                else:
                    t_after = t_429
                finish_t = t_after + ramp_dt(abs(429.0 - mw_tgt), rate_fast)
                push("finish", mw_tgt, finish_t)
            else:
                rate = rate_fast if (mw_start >= 330.0 or mw_tgt >= 330.0) else rate_low
                finish_t = t_start + ramp_dt(mw_start - mw_tgt, rate)
                push("finish", mw_tgt, finish_t)

        else:
            finish_t = t_next
            push("finish", mw_tgt, finish_t)

        # ===== UNIVERSAL CUT CHUẨN (y hệt PPA) =====
        if finish_t > t_next:
            mw_cut = mw_at(
                time_point=t_next,
                t_start=t_start, mw_start=mw_start,
                t_target=t_next, mw_tgt=mw_tgt,
                hold_up_at_429_sec=hold_up_at_429_sec,
                hold_down_at_429_sec=hold_down_at_429_sec,
            )
            # 1) cập nhật chính xác event 'finish' về t_next & MW_cut
            try:
                idx_fin_local = max(idx for idx, ev in enumerate(events) if ev == "finish")
                times[idx_fin_local] = t_next
                mws[idx_fin_local]   = float(mw_cut)
            except ValueError:
                push("finish", mw_cut, t_next)

            # 2) đánh dấu điểm cắt
            push("cut_by_overwrite", mw_cut, t_next)
            finish_t = t_next

        # ===== Sanitize hold markers sau CUT (đồng nhất với PPA) =====
        if hold_start_t is not None and hold_end_t is not None:
            if finish_t <= hold_start_t:
                # cắt trước khi tới hold -> bỏ cả hold_start/hold_end
                idxs = [k for k, ev in enumerate(events) if ev in ("hold_start", "hold_end")]
                for k in sorted(idxs, reverse=True):
                    del events[k]; del mws[k]; del times[k]
                hold_start_t = None; hold_end_t = None; hold_mw = None
            elif hold_start_t < finish_t < hold_end_t:
                # cắt trong hold -> kéo hold_end về finish_t
                for k, ev in enumerate(events):
                    if ev == "hold_end":
                        times[k] = finish_t
                        if hold_mw is not None:
                            mws[k] = float(hold_mw)
                hold_end_t = finish_t

        # ===== Bỏ mọi event > finish_t (trừ 'finish' vốn đã = finish_t) =====
        _keep = []
        for ev, t_val in zip(events, times):
            _keep.append((ev == "finish") or (t_val <= finish_t))
        events = [ev for ev, ok in zip(events, _keep) if ok]
        mws    = [mw for mw, ok in zip(mws, _keep) if ok]
        times  = [tt for tt, ok in zip(times, _keep) if ok]

        # ===== Lưu segment & summary =====
        seg = pd.DataFrame({"Event": events, "MW": mws, "Thời điểm": times})
        segments.append(seg)

        inside_hold_flag = False
        if (hold_start_t is not None) and (hold_end_t is not None):
            if hold_start_t <= finish_t <= hold_end_t:
                inside_hold_flag = True

        summary_rows.append({
            "idx_pair": i,
            "StartMW": round(float(mw_start), 3),
            "StartTime": t_start,
            "HoldMW": (round(float(hold_mw), 3) if hold_mw is not None else pd.NA),
            "HoldStart": (hold_start_t if hold_start_t is not None else pd.NA),
            "HoldEnd": (hold_end_t if hold_end_t is not None else pd.NA),
            "FinishMW": round(float(seg.loc[seg["Event"] == "finish", "MW"].iloc[0]), 3),
            "FinishTime": seg.loc[seg["Event"] == "finish", "Thời điểm"].iloc[0],
            "EndReason": ("cut_by_overwrite" if "cut_by_overwrite" in seg["Event"].values else "reach_target"),
            "InsideHold": inside_hold_flag,
        })

        # ===== GAP pair phẳng (nếu có) =====
        if make_gap_pairs:
            gap_sec = (t_next - finish_t).total_seconds()
            if gap_sec > max(float(gap_min_sec), 0.0):
                seg_gap = pd.DataFrame({
                    "Event": ["start", "finish"],
                    "MW": [mw_tgt, mw_tgt],
                    "Thời điểm": [finish_t, t_next]
                })
                segments.append(seg_gap)
                summary_rows.append({
                    "idx_pair": f"{i}_gap",
                    "StartMW": round(float(mw_tgt), 3),
                    "StartTime": finish_t,
                    "HoldMW": pd.NA,
                    "HoldStart": pd.NA,
                    "HoldEnd": pd.NA,
                    "FinishMW": round(float(mw_tgt), 3),
                    "FinishTime": t_next,
                    "IsGap": True,
                    "GapSec": int(gap_sec),
                    "EndReason": "flat_gap",
                })

    summary = pd.DataFrame(summary_rows)
    return segments, summary
