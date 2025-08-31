#!/usr/bin/env python3
import ast
from pathlib import Path

# ==== quét 1 file .py ====
def scan_file(py_file: Path):
    try:
        src = py_file.read_text(encoding="utf-8")
    except Exception:
        src = py_file.read_text(errors="ignore")
    try:
        tree = ast.parse(src, filename=str(py_file))
    except SyntaxError:
        return []

    results = []

    class Visitor(ast.NodeVisitor):
        def visit_Assign(self, node):
            # Nếu bên phải là gọi hàm
            if isinstance(node.value, ast.Call):
                func = node.value.func
                func_name = None
                if isinstance(func, ast.Attribute):
                    func_name = func.attr
                elif isinstance(func, ast.Name):
                    func_name = func.id

                if func_name in ("DataFrame", "read_csv", "read_excel"):
                    # Lấy tên biến bên trái
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            results.append(t.id)
            self.generic_visit(node)

    Visitor().visit(tree)
    return results

# ==== quét toàn bộ thư mục project ====
def scan_root(root: Path):
    all_vars = set()
    for py in root.rglob("*.py"):
        if any(part in (".git","__pycache__","venv",".venv") for part in py.parts):
            continue
        all_vars.update(scan_file(py))
    return sorted(all_vars)

if __name__ == "__main__":
    root = Path(".").resolve()
    df_names = scan_root(root)
    print("Các biến DataFrame tìm thấy trong code:")
    for name in df_names:
        print(" -", name)
