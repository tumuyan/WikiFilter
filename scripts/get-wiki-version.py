#!/usr/bin/env python3
"""
获取可用的维基百科 dump 版本号。

用法:
    python get-wiki-version.py [VERSION] [--check-file]

如果指定了 VERSION，直接使用该版本（不进行回退）。
否则，自动计算版本号并验证可用性，必要时回退到上一个版本。

选项:
    --check-file    检查实际下载文件是否可下载，失败时回退版本

输出:
    将版本号写入 stdout，格式为: VERSION=YYYYMMDD
    可用于设置环境变量: eval $(python get-wiki-version.py)
"""

import argparse
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Optional


def check_version_exists(version: str) -> bool:
    """检查指定版本是否存在（目录URL是否可访问）"""
    url = f"https://dumps.wikimedia.org/zhwiki/{version}/"
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'WikiFilter/1.0')
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def check_file_downloadable(version: str) -> tuple[bool, str]:
    """
    检查指定版本的文件是否可下载。

    检查两个文件:
    - zhwiki-{version}-pages-articles-multistream.xml.bz2 (wiki dump)
    - zhwiki-{version}-all-titles-in-ns0.gz (标题列表)

    返回: (是否全部可下载, 错误信息)
    """
    files = [
        f"zhwiki-{version}-pages-articles-multistream.xml.bz2",
        f"zhwiki-{version}-all-titles-in-ns0.gz",
    ]

    for filename in files:
        url = f"https://dumps.wikimedia.org/zhwiki/{version}/{filename}"
        try:
            req = urllib.request.Request(url, method='HEAD')
            req.add_header('User-Agent', 'WikiFilter/1.0')
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200:
                    return False, f"文件 {filename} 不可访问 (status: {response.status})"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            return False, f"文件 {filename} 不可下载: {e}"

    return True, ""


def calculate_initial_version(date: Optional[datetime] = None) -> str:
    """
    根据日期计算初始版本号。

    维基百科 dump 每月发布一次（每月1日左右）。
    为避免检查尚未完成的dump，使用64小时前的时间来确定版本。
    """
    if date is None:
        date = datetime.now()

    # 回退64小时，避免检查尚未完成的dump
    effective_date = date - timedelta(hours=64)

    year = effective_date.year
    month = effective_date.month

    return f"{year}{month:02d}01"


def get_previous_version(version: str) -> str:
    """获取上一个版本号（回退一个月）"""
    year = int(version[:4])
    month = int(version[4:6])

    if month == 1:
        year -= 1
        month = 12
    else:
        month -= 1

    return f"{year}{month:02d}01"


def find_available_version(initial_version: str, max_retries: int = 3) -> tuple[str, bool]:
    """
    查找可用的版本号。

    从初始版本开始，如果不可用则回退到上一个版本。
    最多尝试 max_retries 次。

    返回: (版本号, 是否发生回退)
    """
    version = initial_version
    fallback_occurred = False

    for attempt in range(max_retries):
        print(f"检查版本 {version} 的发布页...", file=sys.stderr)

        if check_version_exists(version):
            print(f"版本 {version} 可用", file=sys.stderr)
            return version, fallback_occurred

        print(f"版本 {version} 不可用，回退到上一个版本", file=sys.stderr)
        fallback_occurred = True
        version = get_previous_version(version)

    # 如果所有尝试都失败，返回最后一个尝试的版本
    print(f"警告: 无法找到可用版本，使用 {version}", file=sys.stderr)
    return version, True


def find_version_with_file_check(initial_version: str, max_retries: int = 3) -> tuple[str, bool]:
    """
    查找可用的版本号，并验证文件可下载。

    从初始版本开始，如果版本目录不存在或文件不可下载，则回退。
    最多尝试 max_retries 次。

    返回: (版本号, 是否发生回退)
    """
    version = initial_version
    fallback_occurred = False

    for attempt in range(max_retries):
        print(f"检查版本 {version}...", file=sys.stderr)

        # 检查版本目录
        if not check_version_exists(version):
            print(f"错误: 版本目录 {version} 不存在，回退到上一个版本", file=sys.stderr)
            fallback_occurred = True
            version = get_previous_version(version)
            continue

        # 检查文件是否可下载
        print(f"检查版本 {version} 的文件是否可下载...", file=sys.stderr)
        success, error_msg = check_file_downloadable(version)
        if success:
            print(f"版本 {version} 所有文件可下载", file=sys.stderr)
            return version, fallback_occurred

        print(f"错误: 版本 {version} {error_msg}，回退到上一个版本", file=sys.stderr)
        fallback_occurred = True
        version = get_previous_version(version)

    # 如果所有尝试都失败，返回最后一个尝试的版本
    print(f"警告: 无法找到可用版本，使用 {version}", file=sys.stderr)
    return version, True


def main():
    # 解析参数
    parser = argparse.ArgumentParser(description='获取可用的维基百科 dump 版本号')
    parser.add_argument('version', nargs='?', help='指定版本号（可选，不进行回退）')
    parser.add_argument('--check-file', action='store_true',
                        help='检查实际下载文件是否可下载，失败时回退版本')
    args = parser.parse_args()

    if args.version:
        # 用户指定版本，直接使用，不进行回退
        print(f"使用用户指定版本: {args.version}", file=sys.stderr)
        version = args.version
        fallback_occurred = False
    else:
        # 自动计算版本
        initial_version = calculate_initial_version()
        print(f"计算得到初始版本: {initial_version}", file=sys.stderr)

        if args.check_file:
            version, fallback_occurred = find_version_with_file_check(initial_version)
        else:
            version, fallback_occurred = find_available_version(initial_version)

    # 统一输出环境变量到 stdout（用于 eval）
    print(f"WIKI_VERSION={version}")
    print(f"WIKI_FALLBACK={'1' if fallback_occurred else ''}")


if __name__ == "__main__":
    main()
