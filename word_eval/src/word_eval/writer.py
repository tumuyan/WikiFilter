"""CSV 写入器，支持追加模式和 UTF-8 BOM。"""

import csv
import os

HEADER = ["置信度", "评分", "词条", "基础分类", "其他标签", "原因"]


def write_header(filepath: str) -> None:
    """如果文件不存在，写入 CSV 表头。"""
    if not os.path.exists(filepath):
        _write_rows(filepath, [HEADER], mode="w")


def append_rows(filepath: str, rows: list[list[str]]) -> None:
    """追加多行数据到 CSV 文件。"""
    _write_rows(filepath, rows, mode="a")


def _write_rows(filepath: str, rows: list[list[str]], mode: str) -> None:
    with open(filepath, mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def format_row(record: dict) -> list[str]:
    """将单条记录格式化为 CSV 行。"""
    return [
        str(record["confidence"]),
        str(record["score"]),
        record["word"],
        record["category"],
        record["tags"],
        record["reason"],
    ]
