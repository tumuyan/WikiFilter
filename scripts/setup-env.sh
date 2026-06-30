#!/bin/bash
# 设置环境脚本
# 安装构建和处理所需的依赖

set -e

echo "=== 设置环境 ==="

# 检测是否需要使用 sudo
if command -v sudo &> /dev/null && [ "$(id -u)" != "0" ]; then
    SUDO="sudo"
else
    SUDO=""
fi

# 检测系统包管理器
if command -v apt-get &> /dev/null; then
    echo "使用 apt-get 安装系统依赖..."
    $SUDO apt-get update
    $SUDO apt-get -y install wget p7zip-full ripgrep opencc g++ curl jq
elif command -v yum &> /dev/null; then
    echo "使用 yum 安装系统依赖..."
    $SUDO yum -y install wget p7zip ripgrep opencc gcc-c++ curl jq
elif command -v brew &> /dev/null; then
    echo "使用 brew 安装系统依赖..."
    brew install wget p7zip ripgrep opencc gcc curl jq
else
    echo "警告: 无法识别的包管理器，请手动安装: wget, p7zip, ripgrep, opencc, g++, curl, jq"
fi

# Python 依赖
echo "安装 Python 依赖..."
# 检测可用的 Python 命令
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo "Python 未安装，正在安装..."
    if command -v apt-get &> /dev/null; then
        $SUDO apt-get -y install python3 python3-pip
        PYTHON="python3"
    elif command -v yum &> /dev/null; then
        $SUDO yum -y install python3 python3-pip
        PYTHON="python3"
    elif command -v brew &> /dev/null; then
        brew install python3
        PYTHON="python3"
    else
        echo "警告: 无法自动安装 Python"
        PYTHON=""
    fi
fi

# 检测是否为 externally-managed 环境（Debian 12+/Ubuntu 23.04+）
IS_EXTERNALLY_MANAGED=false
for _marker in /usr/lib/python3*/EXTERNALLY-MANAGED; do
    if [ -f "$_marker" ]; then
        IS_EXTERNALLY_MANAGED=true
        break
    fi
done

if [ -n "$PYTHON" ]; then
    # pip 额外参数：externally-managed 环境需 --break-system-packages
    PIP_EXTRA=""
    if $IS_EXTERNALLY_MANAGED; then
        echo "检测到 externally-managed 环境，安装时使用 --break-system-packages"
        PIP_EXTRA="--break-system-packages"
    fi

    # 升级 pip
    if $PYTHON -m pip install --upgrade pip $PIP_EXTRA; then
        echo "pip 已升级"
    else
        echo "警告: pip 升级失败，将使用当前版本继续"
    fi

    # 安装通用 Python 包
    if $PYTHON -m pip install pytest OpenCC $PIP_EXTRA; then
        echo "Python 通用依赖已安装"
    else
        echo "警告: Python 通用依赖安装失败，部分功能可能不可用"
    fi

    # 安装 word_eval 包
    if [ -d word_eval ]; then
        if $PYTHON -m pip install -e word_eval $PIP_EXTRA; then
            echo "word-eval 工具已安装"
        else
            echo "错误: word-eval 安装失败，请检查后重试"
        fi
    else
        echo "警告: word_eval/ 目录不存在，跳过安装"
    fi
fi

# 检查 Java
echo "检查 Java 环境..."
JAVA_REQUIRED=21

check_java_version() {
    if ! command -v java &> /dev/null; then
        echo "0"
        return
    fi
    java -version 2>&1 | grep -oP 'version "?(1\.)?\K[0-9]+' | head -1
}

JAVA_VERSION=$(check_java_version)
echo "当前 Java 版本: ${JAVA_VERSION:-未安装}"

if [ -z "$JAVA_VERSION" ] || [ "$JAVA_VERSION" -lt "$JAVA_REQUIRED" ]; then
    echo "需要 Java $JAVA_REQUIRED 或更高版本，正在下载安装..."
    
    # 使用 Adoptium Temurin JDK 21
    JDK_URL="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.2%2B13/OpenJDK21U-jdk_x64_linux_hotspot_21.0.2_13.tar.gz"
    
    echo "下载 JDK 21..."
    wget -q --show-progress "$JDK_URL" -O /tmp/jdk21.tar.gz
    
    if [ -f /tmp/jdk21.tar.gz ] && [ -s /tmp/jdk21.tar.gz ]; then
        echo "解压 JDK..."
        $SUDO mkdir -p /usr/lib/jvm
        $SUDO tar -xzf /tmp/jdk21.tar.gz -C /usr/lib/jvm
        JDK_DIR=$(ls -d /usr/lib/jvm/jdk-21* 2>/dev/null | head -1)
        if [ -n "$JDK_DIR" ]; then
            $SUDO ln -sf "$JDK_DIR/bin/java" /usr/bin/java
            $SUDO ln -sf "$JDK_DIR/bin/javac" /usr/bin/javac 2>/dev/null || true
            echo "JDK 安装到: $JDK_DIR"
        fi
        rm -f /tmp/jdk21.tar.gz
    else
        echo "警告: JDK 下载失败"
    fi
fi

# 再次检查 Java 是否安装成功
if command -v java &> /dev/null; then
    JAVA_VERSION=$(check_java_version)
    JAVA_FULL=$(java -version 2>&1 | head -1)
    echo "Java 已安装: $JAVA_FULL"
    if [ -n "$JAVA_VERSION" ] && [ "$JAVA_VERSION" -lt "$JAVA_REQUIRED" ]; then
        echo "警告: Java 版本 $JAVA_VERSION 低于要求的 $JAVA_REQUIRED，处理词库功能可能失败"
    fi
else
    echo "警告: Java 安装失败，处理词库功能可能不可用"
fi

echo "=== 环境设置完成 ==="
