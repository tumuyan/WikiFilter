"""解析 LLM 返回的 JSON 响应为结构化记录。"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

CATEGORIES = {
    "名词", "动词", "形容词", "副词", "代词", "数词", "量词",
    "拟声词", "叹词", "成语", "专有名词", "短语", "网络用语", "其他",
}


def _extract_json(text: str) -> str:
    """从文本中提取 JSON 部分（处理 LLM 输出可能包含多余内容的情况）。"""
    # 先尝试找 ```json ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 尝试从第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text.strip()


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    """清理和验证单条记录。"""
    word = str(record.get("word", "")).strip()

    try:
        confidence = int(record.get("confidence", 0))
    except (ValueError, TypeError):
        confidence = 0
    confidence = max(0, min(10, confidence))

    try:
        score = int(record.get("score", 0))
    except (ValueError, TypeError):
        score = 0
    score = max(0, min(100, score))

    category = str(record.get("category", "其他")).strip()
    if category not in CATEGORIES:
        category = "其他"

    raw_tags = record.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split()
    tags = []
    for t in raw_tags:
        t = str(t).strip()
        if t and not t.startswith("#"):
            t = "#" + t
        if t:
            tags.append(t)

    reason = str(record.get("reason", "")).strip()

    return {
        "word": word,
        "confidence": confidence,
        "score": score,
        "category": category,
        "tags": " ".join(tags),
        "reason": reason,
    }


def parse_response(text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的文本，提取评估结果列表。"""
    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("JSON 解析失败，尝试修复")
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析 LLM 响应为 JSON: {e}") from e

    if isinstance(data, dict):
        results = data.get("results", data.get("result", []))
    elif isinstance(data, list):
        results = data
    else:
        raise ValueError(f"不支持的 JSON 结构: {type(data)}")

    if not isinstance(results, list):
        results = [results]

    return [_clean_record(r) for r in results if isinstance(r, dict) and r.get("word")]
