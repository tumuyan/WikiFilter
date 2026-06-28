"""word-eval CLI 入口：argparse 参数解析和主流程编排。"""

import argparse
import asyncio
import logging
import os
import sys

from . import prompt as pmt
from .llm_client import LLMClient
from .parser import parse_response
from .resume import ResumeManager
from .writer import HEADER, append_rows, format_row, write_header

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("word-eval")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="word-eval",
        description="输入法词条评估工具 - 调用 LLM API 评估词条是否适合列入输入法词典",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="输入文件路径（留空则从 stdin 读取）",
    )
    parser.add_argument(
        "-o", "--output",
        default="output.csv",
        help="输出 CSV 文件路径（默认: output.csv）",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("DEEPSEEK_API_KEY", ""),
        help="API Key（默认: DEEPSEEK_API_KEY 环境变量）",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("API_BASE_URL", "https://api.deepseek.com"),
        help="API 基础 URL（默认: https://api.deepseek.com）",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("API_MODEL", "deepseek-chat"),
        help="模型名称（默认: deepseek-chat）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=15,
        help="每批处理的词条数量（默认: 15，建议 10-20）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="并发 API 请求数（默认: 3）",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="起始行号（从 0 开始，默认: 0）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理的词条数（0 表示不限制）",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从上次中断位置继续（自动检测 resume 文件）",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="忽略已有的 resume 文件，从头开始",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        default=False,
        help="使用流式 API（CNB IDE API 需要此选项）",
    )
    return parser


def _read_words(filepath: str | None) -> list[str]:
    """从文件或 stdin 读取词条，每行一个。"""
    if filepath:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    else:
        lines = [line.strip() for line in sys.stdin if line.strip()]
    return lines


async def _process_batch(
    client: LLMClient,
    system_prompt: str,
    batch: list[str],
    batch_idx: int,
    output_path: str,
) -> int:
    """处理一批词条，写入 CSV。返回本批处理数。"""
    user_msg = pmt.build_user_message(batch)
    try:
        response = await client.call(system_prompt, user_msg)
        content = client.extract_content(response)
        records = parse_response(content)
    except Exception as e:
        logger.error("第 %d 批处理失败: %s", batch_idx + 1, e)
        records = [
            {"word": w, "confidence": 0, "score": 0, "category": "其他",
             "tags": "", "reason": f"评估失败: {e}"}
            for w in batch
        ]

    rows = [format_row(r) for r in records]
    append_rows(output_path, rows)
    return len(rows)


async def _process_all(
    words: list[str],
    args: argparse.Namespace,
) -> None:
    """主处理流程。"""
    system_prompt = pmt.build_system_prompt()
    logger.info("系统提示词已构建（包含评估标准）")

    resume_mgr = ResumeManager()
    start_idx = args.start
    if args.resume and not args.no_resume:
        processed = resume_mgr.load()
        if processed > 0:
            start_idx = max(start_idx, processed)
            logger.info("从检查点恢复：已处理 %d 条，从第 %d 条继续", processed, start_idx)

    words_to_process = words[start_idx:]
    if args.limit > 0:
        words_to_process = words_to_process[: args.limit]

    total = len(words_to_process)
    if total == 0:
        logger.info("没有需要处理的词条")
        return

    logger.info("共 %d 条词条待评估（批次大小: %d, 并发: %d）",
                total, args.batch_size, args.concurrency)

    client = LLMClient(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        max_concurrency=args.concurrency,
        stream=args.stream,
    )

    write_header(args.output)

    processed_so_far = start_idx
    task_list = [
        _process_batch(client, system_prompt, words_to_process[i:i + args.batch_size], i, args.output)
        for i in range(0, total, args.batch_size)
    ]

    for coro in asyncio.as_completed(task_list):
        try:
            n = await coro
            processed_so_far += n
            resume_mgr.save(processed_so_far)
            logger.info("进度: %d / %d", processed_so_far - start_idx, total)
        except Exception as e:
            logger.error("批次处理异常: %s", e)

    await client.close()

    logger.info("处理完成！结果已写入: %s", args.output)
    logger.info("API 调用统计: %s", client.stats)

    resume_mgr.clear()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.getLogger("word-eval").setLevel(getattr(logging, args.log_level.upper()))

    if not args.api_key:
        logger.error("请提供 API Key：通过 --api-key 参数或 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    words = _read_words(args.input)
    if not words:
        logger.error("没有读取到任何词条")
        sys.exit(1)

    logger.info("读取到 %d 条词条（来源: %s）", len(words), args.input or "stdin")

    asyncio.run(_process_all(words, args))


if __name__ == "__main__":
    main()
