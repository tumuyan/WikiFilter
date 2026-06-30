#!/usr/bin/env python3
"""
Rime 词库优化工具 —— 检查并优化中英混输词条的编码格式。

主要功能：
1. 解析 ... 标记之后的 tab 分割词条
2. 检查词条各部分数量合法性（1-3 部分），非法统计并报警
3. 检查权重合法性（整数、小数、百分数），非法统计并报警
4. 过滤非 CJK 首字符词条（默认开启，可通过 --keep-non-cjk 关闭）
5. 编码预处理：
   - 规范化分隔符：多个连续分隔符合并为单个
   - 去除编码中的数字字符（可通过 --keep-digits 关闭）
6. 将词条文本按英文字母分段，检查编码中对应的英文部分：
   - 正确形式：_EnglishWord（保留大小写，带 _ 前缀）
   - 错误形式：E N G（字母逐一展开，干扰简拼）→ 自动修正
   - 对于全小写字母段（可能是拼音），仅当编码是逐字母展开时修正
7. 输出优化后的词库文件 + 分析报告

用法:
    python optimize_dict.py <词库文件路径> [选项]

选项:
    --delim <分隔符>         编码多段分隔符（默认空格）
    --output/-o <文件路径>   优化后词库输出路径
    --report/-r <文件路径>   分析报告输出路径
    --fix                    自动修正编码问题（默认仅报告不修改）
    --keep-digits            保留编码中的数字（默认去除数字）
    --keep-non-cjk           保留非 CJK 首字符的词条（默认过滤）

"""

import argparse
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path


# ──────────────────────────────────────────────
# 文本分段
# ──────────────────────────────────────────────

def split_text_into_segments(text: str):
    """
    将文本按英文字母（含大小写）分段。
    如果有非字母符号出现在字母中间（如 Eng-Jap），
    字母运行以非字母为界拆分为多个 EN 段。

    返回: [(segment_text, segment_type), ...]
        segment_type: 'EN' (英文字母) | 'OTHER' (非字母)
    """
    segments = []
    buf = ''
    buf_type = None

    for ch in text:
        is_letter = ch.isascii() and ch.isalpha()

        if buf_type is None:
            buf = ch
            buf_type = 'EN' if is_letter else 'OTHER'
        elif buf_type == 'EN' and is_letter:
            buf += ch
        elif buf_type == 'OTHER' and not is_letter:
            buf += ch
        else:
            segments.append((buf, buf_type))
            buf = ch
            buf_type = 'EN' if is_letter else 'OTHER'

    if buf:
        segments.append((buf, buf_type))

    return segments


def is_all_lowercase(s: str) -> bool:
    """检查字符串是否全为小写字母。"""
    return bool(s) and all(ch.isascii() and ch.islower() for ch in s)


# ──────────────────────────────────────────────
# 英文编码检测与修正
# ──────────────────────────────────────────────

def is_letter_by_letter(eng_word: str, code_slice: list) -> bool:
    """
    检查 code_slice 是否将 eng_word 展开为逐字母编码。
    例如 eng_word='Eng', code_slice=['E','N','G'] → True
         eng_word='AI',  code_slice=['A','I']      → True

    注意: 此处"逐字母"判定只看编码段形式，不区分这些单字母段
    原本是英文还是拼音音节。判定是否需要修正的责任在调用方
    analyze_english_coding —— eng_word 来自词文本的英文段切分，
    只要它出现在词文本中即明确是英文，因此编码中对应的逐字母
    序列都应合并为整体 _eng_word。详见 analyze_english_coding
    情况 2 的说明。
    """
    if len(code_slice) != len(eng_word):
        return False
    return all(c.upper() == e.upper() for c, e in zip(code_slice, eng_word))


def analyze_english_coding(en_word: str, code_parts: list):
    """
    分析英文段 en_word 在编码分段列表中的情况。

    返回 (need_fix, new_code_parts, message):
        need_fix: bool 是否需要修正
        new_code_parts: 修正后的编码分段列表（无需修正则返回原列表）
        message: 描述信息
    """
    expected = f"_{en_word}"  # 期望的正确形式

    # ── 情况 1: 已经是 _EnglishWord 形式 ──
    if expected in code_parts:
        return (False, code_parts, f"已正确: {expected}")

    # ── 情况 2: 逐字母展开形式，如 E N G ──
    #
    # en_word 由 split_text_into_segments 从词文本中按"字母/非字母"
    # 切分得到，出现在词文本中的字母段即明确是英文（而非拼音——
    # 拼音只存在于编码列，不会出现在词文本列）。因此编码中与之逐
    # 字母对应的序列一律属于"逐字母展开"的错误形式，应合并为
    # 整体 _en_word。
    #
    # 例: 词文本"卡AI梦" → en_word='AI'，编码"ka a i meng"中
    #     ['a','i'] 逐字母对应 'AI'，应修正为"ka _AI meng"。
    #     这里 ['a','i'] 即便形式上像拼音音节，但词文本已明确
    #     该段为英文 AI，合并是正确行为，不是误判。
    #
    # 同理适用于任何长度的英文段（AI/OK/TV/IT/VIP/iPhone…）：
    # 词文本中的英文段越长，连续单字母段偶然匹配的概率越低，
    # 但只要匹配成立就应修正，方向恒为正确。
    for i in range(len(code_parts) - len(en_word) + 1):
        candidate = code_parts[i:i + len(en_word)]
        if is_letter_by_letter(en_word, candidate):
            new_parts = list(code_parts)
            new_parts[i:i + len(en_word)] = [expected]
            return (True, new_parts, f"字母展开 → {expected}")

    # ── 情况 3: 大小写不匹配的 _ 形式（如 _ENG 应为 _Eng） ──
    for i, cp in enumerate(code_parts):
        if cp.startswith('_') and cp[1:].upper() == en_word.upper() and cp != expected:
            new_parts = list(code_parts)
            new_parts[i] = expected
            return (True, new_parts, f"大小写修正: {cp} → {expected}")

    # ── 情况 4: 直接出现但无 _ 前缀 ──
    #    仅对非全小写段（即明确是英文的段）执行此项修正
    #    全小写段可能是拼音，不做此修正
    if not is_all_lowercase(en_word):
        for i, cp in enumerate(code_parts):
            if cp.upper() == en_word.upper() and cp != expected:
                new_parts = list(code_parts)
                new_parts[i] = expected
                return (True, new_parts, f"缺少 _ 前缀: {cp} → {expected}")

    # 不需修正
    return (False, code_parts, "无需修正")


# ──────────────────────────────────────────────
# 权重检查
# ──────────────────────────────────────────────

def _is_numeric(s: str) -> bool:
    if not s:
        return False
    try:
        return math.isfinite(float(s))
    except ValueError:
        return False


def is_valid_weight(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    if s.endswith('%'):
        return _is_numeric(s[:-1])
    return _is_numeric(s)


# ──────────────────────────────────────────────
# 核心处理逻辑
# ──────────────────────────────────────────────

class DictOptimizer:
    """Rime 词库优化器。"""

    def __init__(self, filepath: str, delimiter: str = " ",
                 output_path: str = None, report_path: str = None,
                 fix: bool = False, strip_digits: bool = True,
                 filter_non_cjk: bool = True):
        self.filepath = Path(filepath)
        self.delimiter = delimiter
        self.fix = fix
        self.strip_digits = strip_digits
        self.filter_non_cjk = filter_non_cjk

        stem = self.filepath.stem
        parent = self.filepath.parent
        self.output_path = Path(output_path) if output_path else \
            parent / f"{stem}_optimized{self.filepath.suffix}"
        self.report_path = Path(report_path) if report_path else \
            parent / f"{stem}_optimize_report.txt"

        # 统计
        self.total_entries = 0
        self.processed_entries = 0
        self.filtered_non_cjk_entries = []  # 被过滤的非 CJK 首字符词条
        self.invalid_parts_entries = []
        self.invalid_weight_entries = []
        self.eng_corrections = []          # (原文, 旧编码, 新编码, 原因)

        self.segment_counter = Counter()
        self.output_lines = []

    # ────────────────────────────────────────
    def run(self):
        raw_lines = self._read_lines()
        entry_start = self._find_entry_start(raw_lines)

        # 头部（... 之前）原样保留
        self.output_lines.extend(raw_lines[:entry_start])

        # 处理词条
        for line in raw_lines[entry_start:]:
            processed = self._process_entry_line(line)
            if processed:
                self.output_lines.append(processed)

        if self.fix:
            self._write_output()
        self._write_report()
        self._print_summary()

    def _read_lines(self) -> list:
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return f.readlines()
        except OSError as e:
            print(f"[错误] 无法读取词库文件 {self.filepath}: {e}", file=sys.stderr)
            sys.exit(1)

    def _find_entry_start(self, lines: list) -> int:
        for i, line in enumerate(lines):
            if line.strip() == '...':
                return i + 1
        print("[信息] 未找到 '...' 词条起始标记，将整个文件作为词库处理"
              "（头部非注释行可能被误判为词条）", file=sys.stderr)
        return 0

    # ────────────────────────────────────────
    def _process_entry_line(self, line: str) -> str:
        raw_line = line.rstrip('\n').rstrip('\r')
        original_line = raw_line  # 始终保留源文件原文，专供报告引用，永不改写
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('#'):
            return line

        self.total_entries += 1

        parts = stripped.split('\t')

        # ── 检查部分数 ──
        if len(parts) > 3:
            self.invalid_parts_entries.append(original_line)
            return line  # 非法条目不计入 processed_entries

        word = parts[0]

        # ── 过滤非 CJK 首字符词条（默认开启）──
        if self.filter_non_cjk:
            if not word or not self._is_cjk_char(word[0]):
                self.filtered_non_cjk_entries.append(original_line)
                return ''  # 过滤条目不计入 processed_entries（run 中跳过空返回值）

        original_code_str = parts[1] if len(parts) >= 2 else ''  # 源文件原文，专供报告引用
        weight_str = parts[2] if len(parts) == 3 else ''

        # ── 编码预处理 ──
        # 顺序：先去数字、再合并分隔符。否则 "a 1 b" 去数字后变 "a  b"，
        # 会残留多余分隔符污染输出文件。
        working_code = original_code_str
        if working_code:
            if self.strip_digits:
                working_code = self._strip_digits_from_code(working_code)
            working_code = self._normalize_delimiter(working_code)

            if working_code != original_code_str and self.fix:
                # 将预处理后的编码写回行中（仅用于输出，不影响报告原文）
                parts[1] = working_code
                raw_line = '\t'.join(parts)
                line = raw_line + '\n'

        # ── 检查权重 ──
        if weight_str:
            w = weight_str.strip()
            if not is_valid_weight(w):
                self.invalid_weight_entries.append((original_line, w))

        # ── 分析编码中的英文段 ──
        if working_code:
            code_parts = self._split_code(working_code)
            text_segments = split_text_into_segments(word)

            # 提取英文段
            en_segments = [(seg, idx) for idx, (seg, typ) in enumerate(text_segments)
                           if typ == 'EN']

            if en_segments:
                cur_parts = list(code_parts)
                all_messages = []
                any_fix = False

                for en_word, _ in en_segments:
                    need_fix, new_parts, msg = analyze_english_coding(en_word, cur_parts)
                    if need_fix:
                        cur_parts = new_parts
                        any_fix = True
                        all_messages.append(msg)

                if any_fix:
                    new_code_str = self.delimiter.join(cur_parts)
                    # 报告中"原编码"引用源文件原文 original_code_str，
                    # "新编码"为最终修正结果，保证仅检查模式下与源文件一致
                    self.eng_corrections.append(
                        (original_line, original_code_str, new_code_str, '; '.join(all_messages)))
                    code_parts = cur_parts

                    if self.fix:
                        new_parts_list = list(parts)
                        new_parts_list[1] = new_code_str
                        line = '\t'.join(new_parts_list) + '\n'

            # 统一统计编码分段（修正后或原始）
            self.segment_counter.update(code_parts)

        self.processed_entries += 1
        return line

    def _split_code(self, code: str) -> list:
        return [seg for seg in code.split(self.delimiter) if seg]

    # ── 编码预处理：去除数字 ──
    @staticmethod
    def _strip_digits_from_code(code: str) -> str:
        """去除编码字符串中的所有数字字符。"""
        return re.sub(r'[0-9]', '', code)

    # ── 编码预处理：规范化分隔符 ──
    def _normalize_delimiter(self, code: str) -> str:
        """将编码中多个连续分隔符合并为单个分隔符。"""
        return re.sub(re.escape(self.delimiter) + r'{2,}', self.delimiter, code)

    # ── CJK 字符检测 ──
    @staticmethod
    def _is_cjk_char(ch: str) -> bool:
        """判断单个字符是否为 CJK 文字（中日韩统一表意文字）。"""
        cp = ord(ch)
        # CJK 统一表意文字 (4E00-9FFF)
        # CJK 统一表意文字扩展 A (3400-4DBF)
        # CJK 统一表意文字扩展 B (20000-2A6DF)
        # CJK 统一表意文字扩展 C (2A700-2B73F)
        # CJK 统一表意文字扩展 D (2B740-2B81F)
        # CJK 统一表意文字扩展 E (2B820-2CEAF)
        # CJK 统一表意文字扩展 F (2CEB0-2EBEF)
        # CJK 兼容表意文字 (F900-FAFF)
        # CJK 兼容表意文字补充 (2F800-2FA1F)
        return (
            (0x4E00 <= cp <= 0x9FFF) or
            (0x3400 <= cp <= 0x4DBF) or
            (0x20000 <= cp <= 0x2A6DF) or
            (0x2A700 <= cp <= 0x2B73F) or
            (0x2B740 <= cp <= 0x2B81F) or
            (0x2B820 <= cp <= 0x2CEAF) or
            (0x2CEB0 <= cp <= 0x2EBEF) or
            (0xF900 <= cp <= 0xFAFF) or
            (0x2F800 <= cp <= 0x2FA1F)
        )

    # ────────────────────────────────────────
    def _write_output(self):
        try:
            with open(self.output_path, 'w', encoding='utf-8') as f:
                f.writelines(self.output_lines)
        except OSError as e:
            print(f"[错误] 无法写入优化后词库 {self.output_path}: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[输出] 优化后词库：{self.output_path}")

    def _write_report(self):
        try:
            f = self.report_path.open('w', encoding='utf-8')
        except OSError as e:
            print(f"[错误] 无法写入报告 {self.report_path}: {e}", file=sys.stderr)
            sys.exit(1)
        with f as w:
            w.write(f"# 词库优化报告 —— {self.filepath.name}\n")
            w.write(f"# 模式: {'修正模式 (--fix)' if self.fix else '仅检查'}\n")
            w.write(f"# 编码分隔符: {repr(self.delimiter)}\n")
            w.write(f"# 去除数字: {'是' if self.strip_digits else '否'}\n")
            w.write(f"# 过滤非 CJK 首字符: {'是' if self.filter_non_cjk else '否'}\n")
            w.write(f"# {'=' * 60}\n\n")

            w.write(f"总词条数（含非法）: {self.total_entries}\n")
            w.write(f"已处理词条数:       {self.processed_entries}\n")

            if self.filter_non_cjk:
                w.write(f"过滤非 CJK 首字符:  {len(self.filtered_non_cjk_entries)} 条\n")
                if self.filtered_non_cjk_entries:
                    w.write(f"┌─ [非 CJK 首字符词条] {len(self.filtered_non_cjk_entries)} 条\n")
                    for raw in self.filtered_non_cjk_entries[:30]:
                        w.write(f"│ {raw}\n")
                    if len(self.filtered_non_cjk_entries) > 30:
                        w.write(f"│ ... 共 {len(self.filtered_non_cjk_entries)} 条\n")
                    w.write("└─\n")
            w.write("\n")

            # 部分数不合规
            w.write(f"┌─ [部分数不合规词条] {len(self.invalid_parts_entries)} 条\n")
            if self.invalid_parts_entries:
                for raw in self.invalid_parts_entries[:30]:
                    w.write(f"│ {raw}\n")
                if len(self.invalid_parts_entries) > 30:
                    w.write(f"│ ... 共 {len(self.invalid_parts_entries)} 条\n")
            w.write("└─\n\n")

            # 权重不合规
            w.write(f"┌─ [权重不合规词条] {len(self.invalid_weight_entries)} 条\n")
            if self.invalid_weight_entries:
                for raw, wgt in self.invalid_weight_entries[:30]:
                    w.write(f"│ [权重={wgt}] {raw}\n")
                if len(self.invalid_weight_entries) > 30:
                    w.write(f"│ ... 共 {len(self.invalid_weight_entries)} 条\n")
            w.write("└─\n\n")

            # 英文编码修正/建议
            label = "已修正" if self.fix else "需修正"
            w.write(f"┌─ [英文编码{label}] {len(self.eng_corrections)} 条\n")
            for raw, old_c, new_c, reason in self.eng_corrections[:80]:
                w.write(f"│ 原: {raw}\n")
                w.write(f"│ 改: {old_c}\n")
                w.write(f"│  →: {new_c}\n")
                w.write(f"│  原因: {reason}\n\n")
            if len(self.eng_corrections) > 80:
                w.write(f"│ ... 共 {len(self.eng_corrections)} 条\n")
            w.write("└─\n\n")

            # 编码分段统计
            w.write(f"┌─ [编码分段统计]\n")
            w.write(f"│ 种类数: {len(self.segment_counter)}\n")
            w.write(f"│ 总次数: {sum(self.segment_counter.values())}\n\n")

            top_n = min(20, len(self.segment_counter))
            if top_n > 0:
                w.write(f"│ 出现最多的 {top_n} 种分段:\n")
                for seg, cnt in self.segment_counter.most_common(top_n):
                    w.write(f"│   {cnt:>8}  {seg}\n")

                bot_n = min(10, len(self.segment_counter))
                w.write(f"\n│ 出现最少的 {bot_n} 种分段:\n")
                for seg, cnt in self.segment_counter.most_common()[:-bot_n - 1:-1]:
                    w.write(f"│   {cnt:>8}  {seg}\n")
            w.write("└─\n")

    # ────────────────────────────────────────
    def _print_summary(self):
        print('\n' + '=' * 60)
        print(f"     词库优化报告 —— {self.filepath.name}")
        print(f"     {'修正模式 (--fix)' if self.fix else '仅检查模式'}")
        print('=' * 60)

        print(f"\n总词条数（含非法）: {self.total_entries}")
        print(f"已处理词条数:       {self.processed_entries}")
        if self.filter_non_cjk:
            print(f"过滤非 CJK 首字符: {len(self.filtered_non_cjk_entries)}")
        print(f"部分数不合规词条:   {len(self.invalid_parts_entries)}")
        print(f"权重不合规词条:     {len(self.invalid_weight_entries)}")

        if self.fix:
            print(f"已修正英文编码词条: {len(self.eng_corrections)} [OK]")
        else:
            print(f"需修正英文编码词条: {len(self.eng_corrections)} (使用 --fix 自动修正)")

        print(f"\n编码分段种类: {len(self.segment_counter)}")
        print(f"编码分段总次数: {sum(self.segment_counter.values())}")

        if self.invalid_parts_entries:
            print(f"\n! 部分数不合规示例（最多 5 条）:")
            for raw in self.invalid_parts_entries[:5]:
                print(f"  {raw}")

        if self.invalid_weight_entries:
            print(f"\n! 权重不合规示例（最多 5 条）:")
            for raw, wgt in self.invalid_weight_entries[:5]:
                print(f"  [权重={wgt}] {raw}")

        if self.eng_corrections:
            print(f"\n{'!' if not self.fix else '~'} 英文编码修正示例（最多 5 条）:")
            for raw, old_c, new_c, reason in self.eng_corrections[:5]:
                print(f"  原文: {raw}")
                print(f"  {old_c} → {new_c}")
                print(f"  原因: {reason}")

        print()

# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Rime 词库优化工具 —— 检查并优化中英混输词条编码格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 仅检查，生成报告（不修改文件）
    python optimize_dict.py pinyin_simp_liuxing.dict.yaml

    # 检查并自动修正
    python optimize_dict.py melt_eng.dict.yaml --fix

    # 指定编码分隔符为逗号
    python optimize_dict.py my_dict.txt --delim ,

    # 指定输出路径
    python optimize_dict.py input.dict.yaml --fix -o output.dict.yaml -r report.txt
        """)

    parser.add_argument('filepath', help='词库文件路径（.dict.yaml 或 .txt）')
    parser.add_argument('--delim', default=' ',
                        help='编码多段分隔符（默认空格）')
    parser.add_argument('-o', '--output', default=None,
                        help='优化后词库输出路径')
    parser.add_argument('-r', '--report', default=None,
                        help='分析报告输出路径')
    parser.add_argument('--fix', action='store_true',
                        help='自动修正编码问题（默认仅报告不修改）')
    parser.add_argument('--keep-digits', action='store_true', default=False,
                        help='保留编码中的数字（默认去除数字）')
    parser.add_argument('--keep-non-cjk', action='store_true', default=False,
                        help='保留非 CJK 首字符的词条（默认过滤）')

    args = parser.parse_args()

    if not os.path.isfile(args.filepath):
        print(f"错误：文件不存在 —— {args.filepath}", file=sys.stderr)
        sys.exit(1)

    optimizer = DictOptimizer(
        filepath=args.filepath,
        delimiter=args.delim,
        output_path=args.output,
        report_path=args.report,
        fix=args.fix,
        strip_digits=not args.keep_digits,
        filter_non_cjk=not args.keep_non_cjk,
    )
    optimizer.run()


if __name__ == '__main__':
    main()
