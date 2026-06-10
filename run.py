# run.py

import requests, threading, time, signal, sys, os, ctypes, pygame, typer, logging
from datetime import datetime, timezone, timedelta
# from gui.main_window import MainWindow
# from tkinter import messagebox
from feature.ticket_timeout_pm import TicketTimeoutPM
from feature.ticket_timeout_od import TicketTimeoutOD
from lib.init_app import init_app

pm_data = {}
od_data = {}
time_interval = 0

# 配置 logging
logger = logging.getLogger("ticket_timeout")
logger.setLevel(logging.INFO)
logger.handlers.clear()

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(message)s"))

_file_handler = logging.FileHandler("ticket_timeout.log", encoding="utf-8", mode="a")
_file_handler.setFormatter(logging.Formatter("%(message)s"))

logger.addHandler(_stream_handler)
logger.addHandler(_file_handler)


# 获取资源的绝对路径，兼容开发环境和打包后的环境
def get_resource_path(relative_path):
    if not os.path.isfile("./sound.mp3"):
        try:
            # 打包后的环境
            base_path = sys._MEIPASS
        except AttributeError:
            # 开发环境，使用当前文件所在目录
            base_path = os.path.abspath(".")
    
        return os.path.join(base_path, relative_path)
    return "./sound.mp3"

sound_path = get_resource_path("res/sound.mp3")
pygame.mixer.init()
pygame.mixer.music.load(sound_path)

# 获取当前时间
def fetch_time():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return current_time

# 通过互联网API获取当前时间
def fetch_internet_time():
    """从互联网时间API获取当前时间，失败则返回None"""
    apis = [
        "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
        "https://timeapi.io/api/Time/current/zone?timeZone=Asia/Shanghai",
    ]
    for api_url in apis:
        try:
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # WorldTimeAPI 返回 datetime 字段
                if "datetime" in data:
                    return datetime.fromisoformat(data["datetime"].replace("Z", "+00:00"))
                # TimeAPI.io 返回 dateTime 字段
                if "dateTime" in data:
                    return datetime.fromisoformat(data["dateTime"])
        except Exception:
            continue
    return None

# 定时关机守护线程
def shutdown_watcher(end_hour, end_minute):
    """定期检查互联网时间，到达指定时间后关闭程序"""
    tz_shanghai = timezone(timedelta(hours=8))
    while True:
        try:
            now = fetch_internet_time()
            if now is not None:
                # 统一转到东八区比较
                now_shanghai = now.astimezone(tz_shanghai)
                if now_shanghai.hour == end_hour and now_shanghai.minute >= end_minute:
                    logger.info(f"[INFO]    [{fetch_time()}] 已到达设定结束时间 {end_hour:02d}:{end_minute:02d}，程序退出中...")
                    time.sleep(1)
                    os._exit(0)
            time.sleep(30)
        except Exception:
            time.sleep(60)

# 处理退出信号
def handle_signal(signum, frame):
    logger.info(f"[INFO]    [{fetch_time()}] 程序退出中...")
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
    while True:
        try:
            tkpm.query()
            
            global pm_data
            while tkpm.content == None:
                time.sleep(1)
            pm_data = tkpm.query_timeout()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log = ""
            if int(pm_data.get('num', 0)) > 0:
                log = f"{current_time}\n你有{pm_data['num']}条周期性工单即将超时，请及时处理！\n\n"        
                msg_box(log)
                data = ''
                for item in pm_data['data']:
                    data = data + f"{item['workorderDescription']}\n工单编号：{item['workorderNo']}\n接单人：{item['acceptName']}\n超时时间：{item['feedBackTime']}\n\n"
                log = log + data
            else:
                log = f"{current_time}\n暂无即将超时的周期性工单\n\n"
            logger.info(log)
            pm_data = {}

            time.sleep(300)
        except Exception as e:
            time.sleep(10)
            logger.error(f"[ERROR]   [{fetch_time()}] tkpm_query线程异常: {e}")
            logger.info(f"[INFO]    [{fetch_time()}] 正在重启tkpm_query线程...")
            continue

# 临时性工单查询
def tkod_query(tkod):
    while True:
        try:
            tkod.query()

            while tkod.content is None:
                time.sleep(1)

            global od_data
            while tkod.content == None:
                pass
            od_data = tkod.query_timeout()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log = ""
            if int(od_data.get('num', 0)) > 0:
                log = f"{current_time}\n你有{od_data['num']}条临时性工单即将超时，请及时处理！\n\n"        
                msg_box(log)
                data = ''
                for item in od_data['data']:
                    data = data + f"{item['workorderDescription']}\n工单编号：{item['workorderNo']}\n接单人：{item['acceptName']}\n超时时间：{item['feedBackTime']}\n\n"
                log = log + data
            else:
                log = f"{current_time}\n暂无即将超时的临时性工单\n\n"
            logger.info(log)
            od_data = {}

            time.sleep(time_interval)
        except Exception as e:
            time.sleep(10)
            logger.error(f"[ERROR]   [{fetch_time()}] tkod_query线程异常: {e}")
            logger.info(f"[INFO]    [{fetch_time()}] 正在重启tkod_query线程...")
            continue


def main(
    wait_time: int = typer.Option(120, "--time", "-t", help="临时性工单查询间隔（秒）"),
    end_time: str = typer.Option(None, "--end", "-e", help="程序结束时间（24小时制，例如 8:30 或 20:30），不指定则不自动关闭"
)):
    """这是一个工单即将超时弹窗提醒的软件"""
    global time_interval
    time_interval = wait_time

    # 解析 end_time
    if end_time is not None:
        try:
            parts = end_time.strip().replace("：", ":").split(":")
            end_hour = int(parts[0])
            end_minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            logger.error("[ERROR]   结束时间格式错误，请使用 HH:MM 格式（例如 8:30 或 20:30）")
            return

    url = "http://kyrian.asia/api/get_auth"
    if requests.get(url).text != "OK":
            return
    logger.info("=" * 50)
    logger.info(f"[INFO]    [{fetch_time()}] 程序启动中...")
    init_app()
    tkpm = TicketTimeoutPM()
    tkod = TicketTimeoutOD()
    logger.info(f"[INFO]    [{fetch_time()}] 正在加载配置...")
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    t1 = threading.Thread(target=tkpm_query, args=(tkpm,), daemon=True)
    t2 = threading.Thread(target=tkod_query, args=(tkod,), daemon=True)
    
    t1.start()
    t2.start()
    if end_time is not None:
        t3 = threading.Thread(target=shutdown_watcher, args=(end_hour, end_minute), daemon=True)
        t3.start()
        logger.info(f"[INFO]    [{fetch_time()}] 程序将在 {end_hour:02d}:{end_minute:02d} 自动关闭")
    logger.info(f"[SUCCESS] [{fetch_time()}] 程序启动完成！")
    logger.info("=" * 50)
    while True:
        time.sleep(1)


if __name__ == '__main__':
    typer.run(main)
