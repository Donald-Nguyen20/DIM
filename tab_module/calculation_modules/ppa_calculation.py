# ppa_calculation.py
import pandas as pd
from datetime import timedelta


def build_ppa_per_pair(
    df_step: pd.DataFrame,
    hold_up_at_330_sec: int = 30 * 60,    # Hold khi TĂNG qua 330
    hold_down_at_462_sec: int = 30 * 60,  # Hold khi GIẢM qua 462
    snap_tolerance_sec: int = 0,          # (không còn dùng cho cut, giữ lại để tương thích chữ ký)
    flag_col: str = "Dừng lệnh",          # (không còn ảnh hưởng đến cut)
    make_gap_pairs: bool = True,          # Bật khâu nối gap (chỉ có ý nghĩa nếu finish_t < t_next)
    gap_min_sec: int = 1                  # Ngưỡng tối thiểu tạo gap pair
):
    """
    Tính danh sách các segment (start/hold/finish/...) cho từng cặp lệnh kế tiếp.
    Triết lý mới: UNIVERSAL CUT -> hễ có lệnh kế tiếp (mốc t_next) xuất hiện TRƯỚC thời điểm finish_t
    thì dừng cặp hiện tại NGAY TẠI t_next (cắt đuôi), bất kể flag TRUE/FALSE.

    Input df_step yêu cầu cột:
      - 'Thời điểm' (datetime-like)
      - 'MW'       (numeric)

    Returns:
      - segments: List[pd.DataFrame] mỗi phần tử là table Event/MW/Thời điểm của 1 cặp
      - summary : pd.DataFrame tóm tắt cho từng cặp
    """
    # ===== Kiểm tra đầu vào =====
    if df_step.empty or "MW" not in df_step or "Thời điểm" not in df_step:
        return [], pd.DataFrame()

    df = df_step.copy()

    # Chuẩn hóa kiểu dữ liệu
    df["MW"] = pd.to_numeric(df["MW"], errors="coerce")
    df["Thời điểm"] = pd.to_datetime(df["Thời điểm"], errors="coerce")

    # Chuẩn hóa cờ (để giữ tương thích, nhưng không ảnh hưởng đến cut)
    def _to_bool(x):
        if pd.isna(x):
            return False
        if isinstance(x, bool):
            return x
        if isinstance(x, (int, float)):
            return x != 0
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

    def mw_at(time_point, t_start, mw_start, t_next, mw_tgt,
              hold_up_at_330_sec, hold_down_at_462_sec) -> float:
        """
        Trả về MW *theo quỹ đạo vật lý* tại 'time_point' khi đi từ
        (t_start, mw_start) -> (t_next, mw_tgt), gồm ramp 0.11/0.22 và hold 330/462.
        """
        # Bảo toàn biên
        if time_point <= t_start:
            return float(mw_start)

        # LÊN
        if mw_tgt > mw_start:
            crosses_330 = (mw_start < 330.0 <= mw_tgt)
            if not crosses_330:
                rate = 0.22 if (mw_start >= 330.0 and mw_tgt >= 330.0) else 0.11
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(min(mw_start + rate * dt, mw_tgt))

            # có băng 330
            t_330 = t_start + ramp_dt(330.0 - mw_start, 0.11)
            if time_point <= t_330:
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(min(mw_start + 0.11 * dt, 330.0))

            if hold_up_at_330_sec > 0:
                hold_end = t_330 + timedelta(seconds=hold_up_at_330_sec)
                if time_point <= hold_end:
                    return 330.0
                dt_after = max((time_point - hold_end).total_seconds(), 0.0)
                return float(min(330.0 + 0.22 * dt_after, mw_tgt))
            else:
                dt_after = max((time_point - t_330).total_seconds(), 0.0)
                return float(min(330.0 + 0.22 * dt_after, mw_tgt))

        # XUỐNG
        if mw_tgt < mw_start:
            crosses_462 = (mw_start > 462.0 >= mw_tgt)
            if not crosses_462:
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(max(mw_start - 0.22 * dt, mw_tgt))

            # có băng 462
            t_462 = t_start + ramp_dt(mw_start - 462.0, 0.22)
            if time_point <= t_462:
                dt = max((time_point - t_start).total_seconds(), 0.0)
                return float(max(mw_start - 0.22 * dt, 462.0))

            if hold_down_at_462_sec > 0:
                hold_end = t_462 + timedelta(seconds=hold_down_at_462_sec)
                if time_point <= hold_end:
                    return 462.0
                dt_after = max((time_point - hold_end).total_seconds(), 0.0)
                return float(max(462.0 - 0.22 * dt_after, mw_tgt))
            else:
                dt_after = max((time_point - t_462).total_seconds(), 0.0)
                return float(max(462.0 - 0.22 * dt_after, mw_tgt))

        # PHẲNG
        return float(mw_tgt)

    EPS = 1e-6
    segments = []
    summary_rows = []

    # ===== Main loop: từng cặp i -> i+1 =====
    for i in range(len(df) - 1):
        t_start = df.loc[i, "Thời điểm"]
        mw_start = float(df.loc[i, "MW"])
        t_next = df.loc[i + 1, "Thời điểm"]
        mw_tgt = float(df.loc[i + 1, "MW"])

        events, mws, times = [], [], []

        def push(ev, mw, t):
            events.append(ev)
            mws.append(float(mw))
            times.append(t)

        # luôn bắt đầu cặp
        push("start", mw_start, t_start)

        # ===== TÍNH FINISH_T THEO QUỸ ĐẠO (chưa xét cắt đuôi) =====
        hold_mw = None
        hold_start_t = None
        hold_end_t = None

        if mw_tgt > mw_start:
            # TĂNG
            if mw_start < 330.0 <= mw_tgt:
                # Lên tới 330 ở 0.11 MW/s
                t_330 = t_start + ramp_dt(330.0 - mw_start, 0.11)
                if hold_up_at_330_sec > 0:
                    hold_mw = 330.0
                    hold_start_t = t_330
                    hold_end_t = t_330 + timedelta(seconds=hold_up_at_330_sec)
                    push("hold_start", 330.0, hold_start_t)
                    push("hold_end", 330.0, hold_end_t)
                    t_after = hold_end_t
                else:
                    t_after = t_330

                if mw_tgt == 330.0:
                    finish_t = t_after
                else:
                    finish_t = t_after + ramp_dt(mw_tgt - 330.0, 0.22)
                push("finish", mw_tgt, finish_t)

            else:
                # không băng 330
                rate = 0.22 if (mw_start >= 330.0 and mw_tgt >= 330.0) else 0.11
                finish_t = t_start + ramp_dt(mw_tgt - mw_start, rate)
                push("finish", mw_tgt, finish_t)

        elif mw_tgt < mw_start:
            # GIẢM
            if mw_start > 462.0 >= mw_tgt:
                # Giảm tới 462 ở 0.22 MW/s
                t_462 = t_start + ramp_dt(mw_start - 462.0, 0.22)
                if hold_down_at_462_sec > 0:
                    hold_mw = 462.0
                    hold_start_t = t_462
                    hold_end_t = t_462 + timedelta(seconds=hold_down_at_462_sec)
                    push("hold_start", 462.0, hold_start_t)
                    push("hold_end", 462.0, hold_end_t)
                    t_after = hold_end_t
                else:
                    t_after = t_462

                if mw_tgt >= 330.0:
                    finish_t = t_after + ramp_dt(462.0 - mw_tgt, 0.22)
                else:
                    t_330 = t_after + ramp_dt(462.0 - 330.0, 0.22)
                    finish_t = t_330 + ramp_dt(330.0 - mw_tgt, 0.22)
                push("finish", mw_tgt, finish_t)

            elif mw_start >= 330.0 and mw_tgt < 330.0:
                # Giảm, băng 330 theo 0.22
                t_330 = t_start + ramp_dt(mw_start - 330.0, 0.22)
                finish_t = t_330 + ramp_dt(330.0 - mw_tgt, 0.22)
                push("finish", mw_tgt, finish_t)

            else:
                # Giảm, không băng 462
                finish_t = t_start + ramp_dt(mw_start - mw_tgt, 0.22)
                push("finish", mw_tgt, finish_t)

        else:
            # PHẲNG
            finish_t = t_next  # mặc định kết thúc ở mốc kế tiếp
            # Nếu phẳng trong suốt hold (hiếm), vẫn tôn trọng t_next
            push("finish", mw_tgt, finish_t)

        # ===== UNIVERSAL CUT: lệnh mới đến thì cắt ngay tại t_next =====
        if finish_t > t_next:
            mw_cut = mw_at(
                time_point=t_next,
                t_start=t_start, mw_start=mw_start,
                t_next=t_next, mw_tgt=mw_tgt,
                hold_up_at_330_sec=hold_up_at_330_sec,
                hold_down_at_462_sec=hold_down_at_462_sec,
            )

            # cập nhật 'finish' của segment hiện tại về t_next + MW cắt
            try:
                idx_fin_local = max(idx for idx, ev in enumerate(events) if ev == "finish")
                times[idx_fin_local] = t_next
                mws[idx_fin_local] = float(mw_cut)
            except ValueError:
                push("finish", mw_cut, t_next)

            # gắn event đánh dấu
            push("cut_by_overwrite", mw_cut, t_next)
            finish_t = t_next
        # --- Sanitize hold markers sau universal cut ---
        if hold_start_t is not None and hold_end_t is not None:
            if finish_t <= hold_start_t:
                # cắt trước khi tới hold -> bỏ cả hold_start/hold_end đã push
                idxs = [k for k, ev in enumerate(events) if ev in ("hold_start", "hold_end")]
                for k in sorted(idxs, reverse=True):
                    del events[k]; del mws[k]; del times[k]
                hold_start_t = None
                hold_end_t   = None
                hold_mw      = None
            elif hold_start_t < finish_t < hold_end_t:
                # cắt ngay trong khoảng hold -> giữ hold_start, kéo hold_end về finish_t
                for k, ev in enumerate(events):
                    if ev == "hold_end":
                        times[k] = finish_t
                        if hold_mw is not None:
                            mws[k] = float(hold_mw)
                hold_end_t = finish_t

        # (tuỳ chọn) loại mọi event vượt quá finish_t (trừ 'finish' vốn đã = finish_t)
        _keep = []
        for ev, t_val in zip(events, times):
            _keep.append((ev == "finish") or (t_val <= finish_t))
        events = [ev for ev, ok in zip(events, _keep) if ok]
        mws    = [mw for mw, ok in zip(mws, _keep) if ok]
        times  = [tt for tt, ok in zip(times, _keep) if ok]

        # ===== Ghi segment gốc =====
        seg = pd.DataFrame({"Event": events, "MW": mws, "Thời điểm": times})
        segments.append(seg)
        inside_hold_flag = False
        if hold_start_t is not None and hold_end_t is not None:
            if hold_start_t <= finish_t <= hold_end_t:
                inside_hold_flag = True
        # Chuẩn bị summary row cho cặp chính
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

        # ===== GAP PAIR (phẳng) giữa finish_t và t_next (thường = 0 giây khi universal cut xảy ra) =====
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
