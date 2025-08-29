# plot_utils.py
import pandas as pd
import matplotlib.pyplot as plt
from PySide6.QtWidgets import QMessageBox
import mplcursors

def draw_df(df: pd.DataFrame, title: str, parent=None):
    if df is None or df.empty:
        if parent:
            QMessageBox.warning(parent, "Chưa có dữ liệu", f"{title} đang rỗng.")
        return
    try:
        df_plot = df.copy()
        df_plot["Thời điểm"] = pd.to_datetime(df_plot["Thời điểm"], errors="coerce")
        df_plot = df_plot.dropna(subset=["MW", "Thời điểm"]).reset_index(drop=True)
        if df_plot.empty:
            if parent:
                QMessageBox.warning(parent, "Chưa có dữ liệu", f"{title} không có điểm hợp lệ.")
            return

        fig, ax = plt.subplots(figsize=(10, 5))
        # Vẽ line bình thường
        ax.plot(df_plot["Thời điểm"], df_plot["MW"], marker='o', label=title)
        ax.set_title(title)
        ax.set_xlabel("Thời điểm")
        ax.set_ylabel("MW")
        ax.grid(True)

        # Scatter “ẩn” để cursor chỉ bám vào CÁC ĐIỂM (không trôi trên đoạn line)
        pts = ax.scatter(df_plot["Thời điểm"], df_plot["MW"], s=1, alpha=0)
        cursor = mplcursors.cursor(pts, hover=True)

        @cursor.connect("add")
        def _on_add(sel):
            i = sel.index
            x = pd.to_datetime(df_plot["Thời điểm"].iloc[i])
            y = float(df_plot["MW"].iloc[i])
            sel.annotation.set_text(f"Thời điểm: {x.strftime('%Y-%m-%d %H:%M:%S')}\nMW: {y:.2f}")
            sel.annotation.get_bbox_patch().set(fc="white", alpha=0.9)

        # Giữ tham chiếu tránh GC
        fig._cursor = cursor

        fig.tight_layout()
        plt.show()

    except Exception as e:
        if parent:
            QMessageBox.critical(parent, "Lỗi vẽ biểu đồ", str(e))
