@echo off
rem BioLiteratureKB 一键安装（Windows）
rem 用法：双击运行，或在命令行执行 install.bat
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo  BioLiteratureKB 安装
echo ==========================================

rem 1. 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYVER=%%v
echo [1/5] Python 版本: %PYVER%

rem 2. 创建 venv（如不存在）
if not exist ".venv\Scripts\python.exe" (
    echo [2/5] 创建虚拟环境 .venv ...
    python -m venv .venv
) else (
    echo [2/5] 虚拟环境已存在，跳过
)

rem 3. 安装依赖（清华镜像加速，失败自动回退官方源）
echo [3/5] 安装依赖（可能需要几分钟）...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --index-url https://pypi.tuna.tsinghua.edu.cn/simple -e . 2>nul
if errorlevel 1 (
    echo      清华镜像失败，改用官方源...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e .
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络
        pause
        exit /b 1
    )
)

rem 4. 初始化 .env（不覆盖已有配置）
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo [4/5] 已创建 .env（请编辑填入你的 LLM API key）
) else (
    echo [4/5] .env 已存在，保留你的配置
)

rem 5. 写入用户级 BIOKB_ROOT（供其他目录调用 biokb）
echo [5/5] 设置全局 BIOKB_ROOT...
setx BIOKB_ROOT "%cd%" >nul
echo %cd%> "%USERPROFILE%\.biokb_root"

echo.
echo ==========================================
echo  安装完成！
echo.
echo  下一步：
echo   1. 编辑 .env 填入 LLM API key
echo   2. 把你的 Zotero/Better BibTeX JSON 放进 zotero 目录
echo   3. 运行:  .venv\Scripts\biokb.exe doctor
echo   4. 运行:  .venv\Scripts\biokb.exe sync
echo ==========================================
pause
