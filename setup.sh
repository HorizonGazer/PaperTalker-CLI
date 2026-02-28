#!/bin/bash
# PaperTalker-CLI macOS/Linux 一键安装脚本

set -e

echo "================================"
echo "  PaperTalker-CLI 安装向导"
echo "================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检测操作系统
OS_TYPE=$(uname -s)
if [[ "$OS_TYPE" == "Darwin" ]]; then
    OS_NAME="macOS"
    MINICONDA_URL="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
elif [[ "$OS_TYPE" == "Linux" ]]; then
    OS_NAME="Linux"
    MINICONDA_URL="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh"
else
    echo -e "${RED}[ERROR] 不支持的操作系统: $OS_TYPE${NC}"
    exit 1
fi

echo "检测到操作系统: $OS_NAME"
echo ""

# Step 1: 检测/安装 Conda
echo "================================"
echo "Step 1: 检测 Conda 环境"
echo "================================"

if command -v conda &> /dev/null; then
    CONDA_PATH=$(which conda)
    echo -e "${GREEN}✓ 已检测到 Conda: $CONDA_PATH${NC}"
    CONDA_BASE=$(conda info --base)
else
    echo -e "${YELLOW}未检测到 Conda，开始安装 Miniconda...${NC}"

    # 下载 Miniconda
    INSTALLER="/tmp/miniconda_installer.sh"
    echo "正在从清华镜像下载 Miniconda..."
    curl -L -o "$INSTALLER" "$MINICONDA_URL"

    # 安装
    echo "正在安装 Miniconda..."
    bash "$INSTALLER" -b -p "$HOME/miniconda3"

    # 初始化
    echo "正在初始化 Conda..."
    "$HOME/miniconda3/bin/conda" init bash
    if [[ "$OS_NAME" == "macOS" ]]; then
        "$HOME/miniconda3/bin/conda" init zsh
    fi

    # 设置环境变量
    export PATH="$HOME/miniconda3/bin:$PATH"
    CONDA_BASE="$HOME/miniconda3"

    # 清理安装文件
    rm -f "$INSTALLER"

    echo -e "${GREEN}✓ Miniconda 安装完成${NC}"
fi

# 配置镜像源
echo ""
echo "配置清华镜像源..."
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes

# 配置 pip 镜像
mkdir -p ~/.pip
cat > ~/.pip/pip.conf << EOF
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
[install]
trusted-host = pypi.tuna.tsinghua.edu.cn
EOF

echo -e "${GREEN}✓ 镜像源配置完成${NC}"
echo ""

# Step 2: 创建环境
echo "================================"
echo "Step 2: 创建 papertalker 环境"
echo "================================"

if conda env list | grep -q "^papertalker "; then
    # 检查环境是否有效
    if [[ -f "$CONDA_BASE/envs/papertalker/bin/python" ]]; then
        echo -e "${GREEN}✓ 环境已存在且有效${NC}"
    else
        echo -e "${YELLOW}检测到无效环境，正在重建...${NC}"
        conda env remove -n papertalker -y
        conda create -n papertalker python=3.11 -y
        echo -e "${GREEN}✓ 环境创建完成${NC}"
    fi
else
    echo "正在创建环境..."
    conda create -n papertalker python=3.11 -y
    echo -e "${GREEN}✓ 环境创建完成${NC}"
fi

echo ""

# Step 3: 安装依赖
echo "================================"
echo "Step 3: 安装依赖包"
echo "================================"

# 激活环境并安装依赖
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate papertalker

echo "正在安装 notebooklm-py..."
pip install -e deps/notebooklm-py

echo "正在安装 paper-search-mcp..."
pip install -e deps/paper-search-mcp

echo "正在安装其他依赖..."
pip install python-dotenv httpx rich playwright

echo "正在安装 Chromium 浏览器..."
python -m playwright install chromium

echo -e "${GREEN}✓ 所有依赖安装完成${NC}"
echo ""

# Step 4: 验证安装
echo "================================"
echo "Step 4: 验证安装"
echo "================================"

if [[ -f "$HOME/.notebooklm/storage_state.json" ]]; then
    echo -e "${GREEN}✓ NotebookLM 认证文件已存在${NC}"
else
    echo -e "${YELLOW}! 未检测到 NotebookLM 认证文件${NC}"
    echo "  请运行: notebooklm login"
fi

echo ""
echo "================================"
echo "  安装完成！"
echo "================================"
echo ""
echo "下一步操作："
echo ""
echo "1. 激活环境："
echo "   conda activate papertalker"
echo ""
echo "2. 首次登录 NotebookLM："
echo "   notebooklm login"
echo ""
echo "3. 配置代理（编辑 .env 文件）："
echo "   HTTPS_PROXY=http://127.0.0.1:7897"
echo ""
echo "4. 生成视频："
echo "   python quick_video.py \"你的主题\""
echo ""
echo "详细文档请查看 README.md"
echo ""
