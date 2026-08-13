#!/usr/bin/env bash
# BioLiteratureKB 一键安装（macOS / Linux）
set -e
cd "$(dirname "$0")"

echo "=========================================="
echo " BioLiteratureKB 安装"
echo "=========================================="

# 1. 检查 Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi
echo "[1/5] Python: $(python3 --version)"

# 2. 创建 venv
if [ ! -f ".venv/bin/python" ]; then
    echo "[2/5] 创建虚拟环境 .venv ..."
    python3 -m venv .venv
else
    echo "[2/5] 虚拟环境已存在，跳过"
fi

# 3. 安装依赖（清华镜像加速，失败自动回退官方源）
echo "[3/5] 安装依赖（可能需要几分钟）..."
if ! .venv/bin/python -m pip install --disable-pip-version-check -q --index-url https://pypi.tuna.tsinghua.edu.cn/simple -e . 2>/dev/null; then
    echo "      清华镜像失败，改用官方源..."
    .venv/bin/python -m pip install --disable-pip-version-check -q -e .
fi

# 4. 初始化 .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[4/5] 已创建 .env（请编辑填入你的 LLM API key）"
else
    echo "[4/5] .env 已存在，保留你的配置"
fi

# 5. 写入用户级 BIOKB_ROOT
echo "[5/5] 设置用户级 BIOKB_ROOT..."
echo "$(pwd)" > "$HOME/.biokb_root"
PROFILE="$HOME/.bashrc"
if [ -f "$HOME/.zshrc" ]; then PROFILE="$HOME/.zshrc"; fi
grep -q "BIOKB_ROOT" "$PROFILE" 2>/dev/null || echo "export BIOKB_ROOT=\"$(pwd)\"" >> "$PROFILE"
echo "  (已写入 $PROFILE，重启终端后生效；当前会话请先 export BIOKB_ROOT)"

echo
echo "=========================================="
echo " 安装完成！"
echo
echo " 下一步："
echo "  1. 编辑 .env 填入 LLM API key"
echo "  2. 把你的 Zotero/Better BibTeX JSON 放进 zotero 目录"
echo "  3. 运行:  .venv/bin/biokb doctor"
echo "  4. 运行:  .venv/bin/biokb sync"
echo "=========================================="
