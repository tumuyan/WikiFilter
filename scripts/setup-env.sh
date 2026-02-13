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

if [ -n "$PYTHON" ]; then
    if $PYTHON -m pip --version &> /dev/null; then
        $PYTHON -m pip install --upgrade pip --break-system-packages 2>/dev/null || \
            $PYTHON -m pip install --upgrade pip
        $PYTHON -m pip install pytest OpenCC --break-system-packages 2>/dev/null || \
            $PYTHON -m pip install pytest OpenCC
    else
        echo "警告: 未找到 pip，跳过 Python 依赖安装"
    fi
fi

# 检查 Java
echo "检查 Java 环境..."
JAVA_REQUIRED=20

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
