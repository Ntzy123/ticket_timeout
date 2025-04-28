@echo off
chcp 65001 >nul 2>&1

REM 检查pip最新版本

set /p choice="是否更换pip清华源？(y/n，默认n): "
if /i "%choice%"=="y" (
    python -m pip install --upgrade pip
    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
) else if /i "%choice%"=="n" (
    REM
) else (
    REM
)


if not exist venv (
    echo "正在创建虚拟环境"
    python -m venv venv
    echo "venv环境创建成功！"
    timeout /t 2 >nul
)

REM 激活虚拟环境并安装依赖包
call venv\Scripts\activate
echo "正在检查并安装依赖包"
python -m pip install --upgrade pip
pip install -r requirements.txt

REM 选择打包或退出
cls
echo ============================
echo 1. 打包为可执行文件
echo 2. 退出
echo ============================
choice /c 12 /n /m "请选择 [1 or 2]: "

if errorlevel 2 goto exit
if errorlevel 1 goto run_command

:run_command
pyinstaller --onefile --name=auto-excel-schedule main.py
    echo 打包完成，请按任意键继续...
    pause >nul
exit

:exit
    rem
exit

REM python main.py