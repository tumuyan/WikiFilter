"""构建系统提示词和用户消息。"""

import os

# 相对源码位置的路径（开发模式）
_SRC_RELATIVE = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    ".codebuddy",
    "skills",
    "ime-dict-evaluator",
    "references",
    "evaluation-criteria.md",
)

# 相对工作目录的路径（安装后使用）
_CWD_RELATIVE = os.path.join(
    ".codebuddy",
    "skills",
    "ime-dict-evaluator",
    "references",
    "evaluation-criteria.md",
)

SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "prompts", "system.md"
)


def _find_criteria() -> str:
    """查找 evaluation-criteria.md，支持多种路径。"""
    # 1. 环境变量覆盖
    env_path = os.environ.get("WORD_EVAL_CRITERIA_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. 相对源码路径（开发模式）
    if os.path.exists(_SRC_RELATIVE):
        return _SRC_RELATIVE

    # 3. 相对当前工作目录
    cwd_abs = os.path.abspath(_CWD_RELATIVE)
    if os.path.exists(cwd_abs):
        return cwd_abs

    raise FileNotFoundError(
        f"找不到 evaluation-criteria.md。\n"
        f"已尝试:\n"
        f"  - 环境变量 WORD_EVAL_CRITERIA_PATH\n"
        f"  - {_SRC_RELATIVE}\n"
        f"  - {cwd_abs}\n"
        f"请在项目根目录运行此工具，或设置 WORD_EVAL_CRITERIA_PATH 环境变量"
    )


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_system_prompt() -> str:
    """读取 system.md + evaluation-criteria.md，拼接成完整的 system prompt。"""
    system_part = _read_file(SYSTEM_PROMPT_PATH)
    criteria_path = _find_criteria()
    criteria_part = _read_file(criteria_path)
    return system_part + "\n\n" + criteria_part


def build_user_message(words: list[str]) -> str:
    """为一批词条构建用户消息。"""
    lines = [f"{i+1}. {w}" for i, w in enumerate(words)]
    return "请评估以下词条：\n" + "\n".join(lines)
