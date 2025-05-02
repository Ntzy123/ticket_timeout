# ticket_timeout_pm.py

import time, threading
from lib.ticket import Ticket

content = None
lock = threading.Lock()

# 循环查询
def loop_query(tk):
    while True:
        global content
        with lock:
            content = tk.query(time_range="today")
        print(content)
        time.sleep(300)
        
def loop_query_timeout(tk):
    while True:
        with lock:
            tk.load(".config.json")
            if content['msg'] == "success":
                tk.query_timeout("pm")
        time.sleep(60)

def ticket_timeout_pm():
    tk = Ticket()
    tk.load(".config.json")
    t1 = threading.Thread(target=loop_query, args=(tk,), daemon=True)
    t1.start()
    t2 = threading.Thread(taget = loop_query_timeout, args=(tk,), daemon=True)
    while content != None:
        time.sleep(1)
    t2.start()
    