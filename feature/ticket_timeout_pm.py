# ticket_timeout_pm.py

import time, threading
from lib.ticket import Ticket

content = None
lock = threading.Lock()

# 循环查询
def poll(tk):
    while True:
        global content
        with lock:
            content = tk.query(time_range="today")
        print(content)
        time.sleep(300)

def ticket_timeout_pm():
    tk = Ticket()
    tk.load(".config.json")
    t = threading.Thread(target=poll, args=(tk,), daemon=True)
    t.start()
    while content != None:
        time.sleep(1)
    while True:
        with lock:
            tk.load(".config.json")
            if content['msg'] == "success":
                tk.query_timeout("pm")
        time.sleep(60)