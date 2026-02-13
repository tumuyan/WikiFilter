#!/bin/bash
# 拉取 upstream 的 main 分支到本地
# 用法: ./git_pull_upstream_main.sh [远程名称]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REMOTE_NAME="${1:-upstream}"
GITHUB_URL="https://github.com/tumuyan/WikiFilter.git"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "拉取 upstream 的 main 分支"
echo "=========================================="

# 检查远程仓库是否存在
if ! git remote | grep -q "^${REMOTE_NAME}$"; then
    echo "远程仓库 '$REMOTE_NAME' 不存在，正在添加..."
    git remote add "$REMOTE_NAME" "$GITHUB_URL"
    echo "已添加远程仓库: $REMOTE_NAME -> $GITHUB_URL"
else
    echo "远程仓库 '$REMOTE_NAME' 已存在"
fi

echo ""
echo "正在从 $REMOTE_NAME 拉取 main 分支..."
git fetch "$REMOTE_NAME" master

echo ""
echo "正在合并 main 分支..."
git merge "$REMOTE_NAME/master" --no-edit

echo ""
echo "=========================================="
echo "拉取完成!"
echo "=========================================="
