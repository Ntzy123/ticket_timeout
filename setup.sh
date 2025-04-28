#!/bin/bash

# 设置编码格式为UTF-8
export LANG=en_US.UTF-8

# 检查pip最新版本
echo "是否更换pip清华源？(y/n，默认n): "
read choice
if [ "$choice" == "y" ]; then
   pip install --upgrade pip
   pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
   echo "正在创建虚拟环境"
   python -m venv venv
   echo "venv环境创建成功！"
fi

# 激活虚拟环境并安装依赖包
source venv/bin/activate
echo "正在检查并安装依赖包"
python -m pip install --upgrade pip
pip install -r requirements.txt

# 选择操作
echo "============================"
echo "1. 打包为可执行文件"
echo "2. 退出"
echo "============================"
read operation

if [ "$operation" == "1" ]; then
    pyinstaller --onefile --name=auto-excel-schedule main.py
    read -p "打包完成，请按任意键继续..."
fi