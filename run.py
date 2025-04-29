# run.py

import time, threading
from lib.ticket import Ticket, poll


if __name__ == '__main__':
    tk = Ticket()
    tk.load(".config.json")
    tk.query()
    t = threading.Thread(target=poll,args=(tk,))
    while True:
        tk.load(".config.json")
        tk.query_timeout_pm()
        time.sleep(60)
    
    #print(tk.data)