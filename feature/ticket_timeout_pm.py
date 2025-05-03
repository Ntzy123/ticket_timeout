# ticket_timeout_pm.py

import time, threading
from lib.ticket import Ticket

content = None
lock = threading.Lock()

# 循环查询
def loop_query(tk):
    global content
    while True:
        with lock:
            content = tk.query(time_range="today")
        time.sleep(1800)
        
def loop_query_timeout(tk):
    while True:
        with lock:
            tk.load(".config.json")
            if content['msg'] == "success":
                ticket_timeout = tk.query_timeout("pm")
                
                if int(ticket_timeout['num']) >= 1:
                    print(f"你有{ticket_timeout['num']}条周期性工单即将超时，请及时处理！")
                else:
                    print("暂无即将超时的周期性工单")
        time.sleep(60)

def ticket_timeout_pm():
    tk = Ticket()
    tk.load(".config.json")
    t1 = threading.Thread(target=loop_query, args=(tk,), daemon=True)
    t1.start()
    t2 = threading.Thread(target=loop_query_timeout, args=(tk,), daemon=True)
    while content != None:
        time.sleep(1)
    t2.start()

    while True:
        pass
    