"""检查点/断点续评支持。"""

import json
import os

DEFAULT_RESUME_FILE = ".word-eval-resume.json"


class ResumeManager:
    """管理评估进度，支持断点续评。"""

    def __init__(self, filepath: str = DEFAULT_RESUME_FILE) -> None:
        self.filepath = filepath
        self._data: dict = {}

    def load(self) -> int:
        """加载已处理的词条数量。返回 processed_count。"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                return self._data.get("processed_count", 0)
            except (json.JSONDecodeError, OSError):
                return 0
        return 0

    def save(self, processed_count: int) -> None:
        """保存当前进度。"""
        self._data["processed_count"] = processed_count
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        """清除检查点文件。"""
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
        self._data = {}
