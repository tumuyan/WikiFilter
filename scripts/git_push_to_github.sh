#!/bin/bash
# 推送当前分支到 GitHub 上游仓库
# 用法: ./git_push_to_github.sh [远程名称]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REMOTE_NAME="${1:-upstream}"
GITHUB_URL="https://github.com/tumuyan/WikiFilter.git"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "推送当前分支到 GitHub"
echo "=========================================="

# 获取当前分支名
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "当前分支: $CURRENT_BRANCH"

# 检查远程仓库是否存在
if ! git remote | grep -q "^${REMOTE_NAME}$"; then
    echo "远程仓库 '$REMOTE_NAME' 不存在，正在添加..."
    git remote add "$REMOTE_NAME" "$GITHUB_URL"
    echo "已添加远程仓库: $REMOTE_NAME -> $GITHUB_URL"
else
    echo "远程仓库 '$REMOTE_NAME' 已存在"
fi

echo ""
echo "正在推送分支 '$CURRENT_BRANCH' 到 $REMOTE_NAME..."
git push "$REMOTE_NAME" "$CURRENT_BRANCH"

echo ""
echo "=========================================="
echo "推送完成!"
echo "=========================================="
