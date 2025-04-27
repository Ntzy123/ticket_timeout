#!/bin/bash

# 设置编码格式为UTF-8
export LANG=en_US.UTF-8

# 检查pip最新版本
echo "是否更换pip清华源？(y/n，默认n): "
read choice
if [ "$choice" == "y" ]; then
   pip install --upgrade pip
   pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
else
   echo "使用默认源"
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
   echo "正在创建虚拟环境"
   python -m venv venv
   echo "venv环境创建成功！"
   source venv/bin/activate
else
   echo "虚拟环境已存在，跳过创建"
   source venv/bin/activate
fi

# 检查并安装依赖包
python -m pip install --upgrade pip
pip install -r requirements.txt

# 选择操作
echo "请选择操作："
echo "1. 安装依赖包"
echo "2. 退出"
read operation

if [ "$operation" == "1" ]; then
   echo "正在检查并安装依赖包"
   pip install --upgrade pip
   pip install -r requirements.txt
else
   echo "退出程序"
fi
