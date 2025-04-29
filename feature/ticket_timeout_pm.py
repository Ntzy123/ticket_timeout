# ticket_timeout_pm.py

import time, threading
from lib.ticket import Ticket, poll

lock = threading.Lock()

# 循环查询
def poll(tk):
    while True:
        time.sleep(300)
        with lock:
            content = tk.query(time_range="today")

def ticket_timeout_pm():
    tk = Ticket()
    tk.load(".config.json")
    content = tk.query(time_range="today")
    print(content)
    t = threading.Thread(target=poll,args=(tk,))
    t.start()
    while True:
        with lock:
            tk.load(".config.json")
            if content['msg'] == "success":
                tk.query_timeout("pm")
        time.sleep(60)