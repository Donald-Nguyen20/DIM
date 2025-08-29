# plot_ppa.py
import pandas as pd
import matplotlib.pyplot as plt
from PySide6.QtWidgets import (
    QMessageBox, QDialog, QVBoxLayout, QListWidget, QListWidgetItem,
    QDialogButtonBox, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Qt
import mplcursors
from typing import List, Tuple, Union, Optional

# ========== Tiện ích ==========
def _normalize_segment(df: pd.DataFrame) -> pd.DataFrame:
    seg = df.copy()
    seg["Thời điểm"] = pd.to_datetime(seg["Thời điểm"], errors="coerce")
    seg = seg.dropna(subset=["MW", "Thời điểm"]).reset_index(drop=True)
    seg = seg.sort_values("Thời điểm")
    return seg

def _pair_label(i: int, seg: pd.DataFrame) -> str:
    try:
        s = float(seg.loc[seg["Event"] == "start", "MW"].iloc[0])
    except Exception:
        s = float(seg["MW"].iloc[0])
    try:
        f = float(seg.loc[seg["Event"] == "finish", "MW"].iloc[-1])
    except Exception:
        f = float(seg["MW"].iloc[-1])
    trend = "↑" if f > s else ("↓" if f < s else "→")
    return f"Pair {i}: {s:.1f} {trend} {f:.1f}"

# ========== Hộp thoại chọn cụm ==========
class SegmentPickerDialog(QDialog):
    def __init__(self, segments: List[pd.DataFrame], parent=None, title="Chọn cụm ppa để vẽ"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._segments = segments
        self.selected_indices: List[int] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Chọn các cụm (pair) muốn vẽ:", self))

        self.listw = QListWidget(self)
        for i, seg in enumerate(self._segments):
            label = _pair_label(i, _normalize_segment(seg))
            item = QListWidgetItem(label)
            # Cho phép tick chọn
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked)  # Checked mặc định
            self.listw.addItem(item)
        layout.addWidget(self.listw)

        # Buttons: Chọn hết / Bỏ chọn
        row_btns = QHBoxLayout()
        btn_all = QPushButton("Chọn hết")
        btn_none = QPushButton("Bỏ chọn")
        row_btns.addWidget(btn_all)
        row_btns.addWidget(btn_none)
        layout.addLayout(row_btns)

        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._clear_all)

        # OK / Cancel
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _select_all(self):
        for i in range(self.listw.count()):
            self.listw.item(i).setCheckState(Qt.Checked)

    def _clear_all(self):
        for i in range(self.listw.count()):
            self.listw.item(i).setCheckState(Qt.Unchecked)

    def _accept(self):
        sel = []
        for i in range(self.listw.count()):
            if self.listw.item(i).checkState() == Qt.Checked:
                sel.append(i)
        self.selected_indices = sel
        self.accept()

# ========== Vẽ nhiều cụm (có chọn) ==========
def draw_ppa(segments_or_result, title: str, parent=None,
             indices=None,
             show_cut_lines: bool = True,   # <<< đổi: hiển thị vạch tại vị trí bị đè
             return_fig_ax: bool = False):

    """
    Vẽ ppa nhiều cụm với lựa chọn:
      - segments_or_result: list[pd.DataFrame] hoặc (segments, summary)
      - indices: danh sách index cụm muốn vẽ. Nếu None -> bật hộp thoại chọn.
      - show_hold_lines: vẽ vạch dọc tại hold_start / hold_end (nếu có).
      - return_fig_ax: nếu True trả về (fig, ax) thay vì chỉ plt.show().

    Mỗi segment (DF) kỳ vọng cột: ["Event", "MW", "Thời điểm"] với các event:
    start / hold_start? / hold_end? / finish.
    """
    # Chuẩn hoá segments
    if isinstance(segments_or_result, tuple):
        segments = segments_or_result[0] or []
    else:
        segments = segments_or_result or []

    if not segments or all(s is None or getattr(s, "empty", True) for s in segments):
        if parent:
            QMessageBox.warning(parent, "Chưa có dữ liệu", f"{title} đang rỗng.")
        return None

    # Nếu không truyền indices -> bật hộp thoại chọn
    if indices is None:
        dlg = SegmentPickerDialog(segments, parent=parent, title="Chọn cụm ppa để vẽ")
        if dlg.exec() != QDialog.Accepted:
            return None  # người dùng bấm Cancel
        indices = dlg.selected_indices

    if not indices:
        if parent:
            QMessageBox.information(parent, "Thông báo", "Chưa chọn cụm nào để vẽ.")
        return None

    # Vẽ
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_title(title)
    ax.set_xlabel("Thời điểm")
    ax.set_ylabel("MW")
    ax.grid(True, alpha=0.3)

    xs_all, ys_all, tips_all = [], [], []

    for i in indices:
        if i < 0 or i >= len(segments):
            continue
        seg = segments[i]
        if seg is None or getattr(seg, "empty", True):
            continue
        seg = _normalize_segment(seg)

        # Hướng
        try:
            s = float(seg.loc[seg["Event"] == "start", "MW"].iloc[0])
        except Exception:
            s = float(seg["MW"].iloc[0])
        try:
            f = float(seg.loc[seg["Event"] == "finish", "MW"].iloc[-1])
        except Exception:
            f = float(seg["MW"].iloc[-1])

        direction = "Up" if f > s else ("Down" if f < s else "Flat")
        ax.plot(seg["Thời điểm"], seg["MW"], marker="o", linewidth=1.5, label=f"Pair {i} · {direction}")

        if show_cut_lines:
            cut_times = pd.to_datetime(seg.loc[seg["Event"] == "cut_by_overwrite", "Thời điểm"], errors="coerce").dropna()
            for tcut in cut_times:
                ax.axvline(tcut, linestyle="--", alpha=0.6)    # vạch đứng nét đứt tại điểm bị đè
                # (tuỳ chọn) đánh dấu thêm marker cho dễ thấy:
                ax.scatter([tcut], [seg.loc[seg["Thời điểm"] == tcut, "MW"].astype(float).iloc[0]],
                        marker="x", s=40)

        # Tooltip từng điểm
        for _, r in seg.iterrows():
            xs_all.append(pd.to_datetime(r["Thời điểm"]))
            ys_all.append(float(r["MW"]))
            ev = str(r.get("Event", "point"))
            tips_all.append(
                f"Pair {i} · {ev}\n"
                f"Thời điểm: {pd.to_datetime(r['Thời điểm']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"MW: {float(r['MW']):.2f}"
            )

    # Scatter ẩn để cursor chỉ bám vào điểm
    pts = ax.scatter(xs_all, ys_all, s=1, alpha=0)
    cursor = mplcursors.cursor(pts, hover=True)

    @cursor.connect("add")
    def _on_add(sel):
        idx = sel.index
        sel.annotation.set_text(tips_all[idx])
        sel.annotation.get_bbox_patch().set(fc="white", alpha=0.9)

    fig._cursor = cursor
    #ax.legend() #bảng chú thích
    fig.tight_layout()

    if return_fig_ax:
        return fig, ax
    plt.show()
    return None

# ========== Tương thích ngược (1 DF) ==========
def draw_ppa_df(df, title: str, parent=None):
    """
    API cũ: vẽ 1 DataFrame ppa (một cụm).
    Đồng thời chấp nhận:
      - list[pd.DataFrame]  -> vẽ nhiều cụm (mở hộp thoại chọn)
      - (segments, summary) -> vẽ nhiều cụm (mở hộp thoại chọn)
    """
    # Nếu là tuple/list -> giao cho draw_ppa (cho phép chọn cụm)
    if isinstance(df, tuple):
        segments = df[0] or []
        return draw_ppa(segments, title=title, parent=parent, indices=None)
    if isinstance(df, list):
        return draw_ppa(df, title=title, parent=parent, indices=None)

    # Còn lại: 1 DataFrame (hành vi cũ)
    if df is None or getattr(df, "empty", True):
        if parent:
            QMessageBox.warning(parent, "Chưa có dữ liệu", f"{title} đang rỗng.")
        return
    return draw_ppa([df], title=title, parent=parent, indices=[0], show_hold_lines=True, return_fig_ax=False)
