# data_utils.py
import os
import pandas as pd
import tempfile
from xlsx2csv import Xlsx2csv

POSITION_INDEXES = [2,3, 4, 5, 6, 7, 16]  # C, E, F, G, H
REQUIRED_COLS = [
    "Tổ máy",
    "Case",
    "CS ra lệnh (MW)",
    "CS hoàn thành (MW)",
    "Thời điểm BĐTH",
    "Thời điểm hoàn thành",
    "Dừng lệnh",
]

def double_col(df: pd.DataFrame, col: str) -> pd.Series:
    vals = df[col].values
    doubled = [v for v in vals for _ in range(2)]
    return pd.Series(doubled)

def interleave_cols(df: pd.DataFrame, col1: str, col2: str, dropna=False) -> pd.Series:
    return df[[col1, col2]].stack(dropna=dropna).reset_index(drop=True)

def read_any(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".csv":
        for enc in ["utf-8-sig", "utf-8", "cp1258", "cp1252"]:
            try:
                return pd.read_csv(path, encoding=enc)
            except Exception:
                continue
        return pd.read_csv(path)

    if ext == ".xlsx":
        try:
            return pd.read_excel(path, sheet_name=0, engine="openpyxl")
        except Exception:
            tmp_csv = os.path.join(tempfile.gettempdir(), "xlsx_fallback.csv")
            Xlsx2csv(path, outputencoding="utf-8").convert(tmp_csv, sheetid=1)
            return pd.read_csv(tmp_csv, encoding="utf-8")

    if ext == ".xls":
        return pd.read_excel(path, sheet_name=0, engine="xlrd")

    if ext == ".xlsb":
        return pd.read_excel(path, sheet_name=0, engine="pyxlsb")

    raise ValueError("Định dạng không hỗ trợ.")
