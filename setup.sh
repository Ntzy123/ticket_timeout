#!/bin/zsh

# 检查pip最新版本

echo -n "是否更换pip清华源？(y/n，默认n): "
read choice
if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
    python3 -m pip install --upgrade pip
    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
fi

# 创建虚拟环境
if [[ ! -d "venv" ]]; then
    echo "正在创建虚拟环境"
    python3 -m venv .venv
    echo "venv环境创建成功！"
    sleep 2
fi

# 激活虚拟环境并安装依赖包
source venv/bin/activate
echo "正在检查并安装依赖包"
python3 -m pip install --upgrade pip
pip install -r requirements.txt

# 选择打包或退出
clear
echo "============================"
echo "1. 打包为可执行文件"
echo "2. 退出"
echo "============================"
echo -n "请选择 [1 or 2]: "
read option

if [[ "$option" == "1" ]]; then
    timestamp=$(date +%Y%m%d%H%M%S)
    # Termux 下没有 .ico 支持，判断是否存在才添加 --icon 参数
    if [[ -f "res/ticket_timeout.ico" ]]; then
        pyinstaller --onefile --name="ticket_timeout_${timestamp}" --icon="res/ticket_timeout.ico" --add-data "res/sound.mp3:res" run.py
    else
        pyinstaller --onefile --name="ticket_timeout_${timestamp}" --add-data "res/sound.mp3:res" run.py
    fi
    echo "打包完成，请按任意键继续..."
    read -k1 -s
fi
