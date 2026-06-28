"""word-eval CLI 入口：argparse 参数解析和主流程编排。"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

from tqdm.asyncio import tqdm as atqdm

from . import prompt as pmt
from .llm_client import LLMClient
from .parser import parse_response
from .resume import ResumeManager
from .writer import HEADER, append_rows, format_row, write_header

# 屏蔽底层 HTTP 库的冗余日志（如 httpx 打印的 "HTTP Request: POST ..."）
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

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
        default=100,
        help="每批处理的词条数量（默认: 100）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="并发 API 请求数（默认: 1）",
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
        "--retry",
        type=int,
        default=3,
        help="API 请求失败时的重试次数（默认: 3）",
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
    parser.add_argument(
        "--dump-responses",
        metavar="FILE",
        help="将原始 LLM 响应保存到指定文件（用于 debug）",
    )
    parser.add_argument(
        "--dump-mode",
        default="on-error",
        choices=["on-error", "always"],
        help="保存模式：on-error 仅在 JSON 解析失败时保存，always 全部保存（默认: on-error）",
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
    max_retries: int = 3,
    dump_path: str | None = None,
    dump_mode: str = "on-error",
) -> int:
    """处理一批词条，写入 CSV。返回本批处理数。"""

    RETRY_DELAY = 2

    user_msg = pmt.build_user_message(batch)
    response_content = ""
    records = []
    stats_ref = client._stats  # 用于累加失败批次数

    for attempt in range(max_retries):
        try:
            response = await client.call(system_prompt, user_msg)
            response_content = client.extract_content(response)
            records = parse_response(response_content)
            break  # 成功

        except ValueError as e:
            # 解析失败后检查响应最后一行是否包含敏感内容——敏感内容不重试
            last_line = next(
                (l for l in reversed(response_content.strip().splitlines()) if l.strip()),
                "",
            )
            is_sensitive = "敏感内容" in last_line
            if is_sensitive:
                stats_ref["failed_calls"] += 1
                logger.error("第 %d 批处理失败: %s [敏感内容]", batch_idx + 1, e)
                if dump_path and response_content:
                    _append_dump(dump_path, batch_idx, batch, response_content)
                records = [
                    {"word": w, "confidence": 0, "score": 0, "category": "其他",
                     "tags": "", "reason": "评估失败: 内容包含敏感信息"}
                    for w in batch
                ]
                break  # 敏感内容不重试

            # 普通 JSON 解析失败，尝试重试
            if attempt < max_retries - 1:
                logger.warning(
                    "第 %d 批解析失败 (尝试 %d/%d): %s",
                    batch_idx + 1, attempt + 1, max_retries, e,
                )
                if dump_path and dump_mode == "on-error" and response_content:
                    _append_dump(dump_path, batch_idx, batch, response_content)
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue

            # 最后一次尝试也失败
            stats_ref["failed_calls"] += 1
            logger.error("第 %d 批处理失败: %s", batch_idx + 1, e)
            if dump_path and dump_mode == "on-error" and response_content:
                _append_dump(dump_path, batch_idx, batch, response_content)
            records = [
                {"word": w, "confidence": 0, "score": 0, "category": "其他",
                 "tags": "", "reason": f"评估失败: {e}"}
                for w in batch
            ]
            break

        except Exception as e:
            # API 层异常（HTTP 错误等）
            if attempt < max_retries - 1:
                logger.warning(
                    "第 %d 批 API 调用失败 (尝试 %d/%d): %s",
                    batch_idx + 1, attempt + 1, max_retries, e,
                )
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue
            stats_ref["failed_calls"] += 1
            logger.error("第 %d 批处理失败: %s", batch_idx + 1, e)
            if dump_path and dump_mode == "on-error" and response_content:
                _append_dump(dump_path, batch_idx, batch, response_content)
            records = [
                {"word": w, "confidence": 0, "score": 0, "category": "其他",
                 "tags": "", "reason": f"评估失败: {e}"}
                for w in batch
            ]
            break
    else:
        # 正常完成（走 records = ... 和 break 跳出，不会到这里）
        pass

    rows = [format_row(r) for r in records]
    append_rows(output_path, rows)
    return len(rows)


def _append_dump(dump_path: str, batch_idx: int, batch: list[str], content: str) -> None:
    """将原始 LLM 响应追加到 dump 文件。"""
    ts = datetime.now().strftime("%H:%M:%S")
    sep = f"\n{'='*60}\n# 批次 {batch_idx+1} @ {ts} ({len(batch)} 词条)\n"
    words = "\n".join(f"  {i+1}. {w}" for i, w in enumerate(batch))
    with open(dump_path, "a", encoding="utf-8") as f:
        f.write(sep)
        f.write(words + "\n---响应---\n")
        f.write(content)
        f.write("\n")


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
        max_retries=args.retry,
    )

    write_header(args.output)

    processed_so_far = start_idx
    task_list = [
        _process_batch(
            client, system_prompt,
            words_to_process[i:i + args.batch_size], i, args.output,
            max_retries=args.retry,
            dump_path=args.dump_responses, dump_mode=args.dump_mode,
        )
        for i in range(0, total, args.batch_size)
    ]

    pbar = atqdm(
        total=len(words),
        initial=start_idx,
        desc="评估进度",
        unit="item",
        ncols=80,
    )
    for coro in asyncio.as_completed(task_list):
        try:
            n = await coro
            processed_so_far += n
            resume_mgr.save(processed_so_far)
            pbar.set_postfix(token=f"{client.stats['total_tokens']:,}")
            pbar.update(n)
        except Exception as e:
            logger.error("批次处理异常: %s", e)
            pbar.update(args.batch_size)
    pbar.close()

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
