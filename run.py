# run.py

import threading, time, signal, sys, os, ctypes, pygame, typer
from datetime import datetime
# from gui.main_window import MainWindow
# from tkinter import messagebox
from feature.ticket_timeout_pm import TicketTimeoutPM
from feature.ticket_timeout_od import TicketTimeoutOD

pm_data = {}
od_data = {}
time_interval = 0


# 获取资源的绝对路径，兼容开发环境和打包后的环境
def get_resource_path(relative_path):
    try:
        # 打包后的环境
        base_path = sys._MEIPASS
    except AttributeError:
        # 开发环境，使用当前文件所在目录
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

sound_path = get_resource_path("res/sound.mp3")
pygame.mixer.init()
pygame.mixer.music.load(sound_path)

# 初始化
"""def init():
    global time_interval
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--time", type=int, default=120, help="临时性工单查询间隔")
    args = parser.parse_args()
    time_interval = args.time"""

# 获取当前时间
def fetch_time():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return current_time

# 处理退出信号
def handle_signal(signum, frame):
    print(f"[INFO]    [{fetch_time()}] 程序退出中...")
    time.sleep(1)
    sys.exit(0)

# 信息提示框
def msg_box(msg):
    def run_msgbox(msg):
        pygame.mixer.music.play()
        ctypes.windll.user32.MessageBoxW(0, msg, "提示", 0)
    thread = threading.Thread(target=run_msgbox, args=(msg,), daemon=True)
    thread.start()

# 周期性工单查询
def tkpm_query(tkpm):
    tkpm.query()

    global pm_data
    while tkpm.content == None:
        pass
    pm_data = tkpm.query_timeout()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = ""
    if int(pm_data['num']) > 0:
        log = f"{current_time}\n你有{pm_data['num']}条周期性工单即将超时，请及时处理！\n\n"        
        msg_box(log)
        data = ''
        for item in od_data['data']:
            data = data + f"{item['workorderDescription']}\n工单编号：{item['workorderNo']}\n接单人：{item['acceptName']}\n超时时间：{item['feedBackTime']}\n\n"
        log = log + data
    else:
        log = f"{current_time}\n暂无即将超时的周期性工单\n\n"
    print(log)
    with open("ticket_timeout.log", "a") as file:
        file.write(log)
    pm_data = {}

    time.sleep(300)
    tkpm_query(tkpm)

# 临时性工单查询
def tkod_query(tkod):
    tkod.query()

    global od_data
    while tkod.content == None:
        pass
    od_data = tkod.query_timeout()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = ""
    if int(od_data['num']) > 0:
        log = f"{current_time}\n你有{od_data['num']}条临时性工单即将超时，请及时处理！\n\n"        
        msg_box(log)
        data = ''
        for item in od_data['data']:
            data = data + f"{item['workorderDescription']}\n工单编号：{item['workorderNo']}\n接单人：{item['acceptName']}\n超时时间：{item['feedBackTime']}\n\n"
        log = log + data
    else:
        log = f"{current_time}\n暂无即将超时的临时性工单\n\n"
    # 写入日志
    print(log)
    with open("ticket_timeout.log", "a") as file:
            file.write(log)
    od_data = {}

    time.sleep(time_interval)
    tkod_query(tkod)  


def main(
    wait_time: int = typer.Option(120, "--time", "-t", help="临时性工单查询间隔")
):
    """这是一个工单即将超时弹窗提醒的软件"""
    global time_interval
    time_interval = wait_time
    print(time_interval)
    print("=" * 50)
    print(f"[INFO]    [{fetch_time()}] 程序启动中...")
    tkpm = TicketTimeoutPM()
    tkod = TicketTimeoutOD()
    print(f"[INFO]    [{fetch_time()}] 正在加载配置...")
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    t1 = threading.Thread(target=tkpm_query, args=(tkpm,), daemon=True)
    t2 = threading.Thread(target=tkod_query, args=(tkod,), daemon=True)
    
    t1.start()
    t2.start()
    print(f"[SUCCESS] [{fetch_time()}] 程序启动完成！")
    print("=" * 50)
    while True:
        time.sleep(1)


if __name__ == '__main__':
    typer.run(main)