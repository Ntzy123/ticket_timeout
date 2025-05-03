# run.py

import threading, time
from datetime import datetime
from gui.main_window import MainWindow
from tkinter import messagebox
from feature.ticket_timeout_pm import TicketTimeoutPM
from feature.ticket_timeout_od import TicketTimeoutOD

pm_data = {}
od_data = {}


def tkpm_query(tkpm):
    tkpm.query()
    time.sleep(1800)    

def tkpm_query_timeout(tkpm):
    global pm_data
    while tkpm.content == None:
        pass
    tkpm.content != None
    pm_data = tkpm.query_timeout()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if pm_data['num'] > 0:
        messagebox.showinfo("提示" ,f"{current_time}\n你有{pm_data['num']}条周期性工单即将超时，请及时处理！\n\n")
    pm_data = {}
    window.after(60000, tkpm_query_timeout, tkpm)

def tkod_query(tkpm):
    tkod.query()
    time.sleep(120)    

def tkod_query_timeout(tkpm):
    global od_data
    while tkpm.content == None:
        pass
    tkod.content != None
    od_data = tkod.query_timeout()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if od_data['num'] > 0:
        messagebox.showinfo("提示" ,f"{current_time}\n你有{od_data['num']}条临时性工单即将超时，请及时处理！\n\n")
    od_data = {}
    window.after(60000, tkod_query_timeout, tkpm)

if __name__ == '__main__':
    tkpm = TicketTimeoutPM()
    tkod = TicketTimeoutOD()
    t1 = threading.Thread(target=tkpm_query, args=(tkpm,), daemon=True)
    t2 = threading.Thread(target=tkod_query, args=(tkod,), daemon=True)
    t1.start()
    t2.start()
    
    window = MainWindow()
    window.after(1000, tkpm_query_timeout, tkpm)
    window.after(1000, tkod_query_timeout, tkod)
    window.mainloop()
    messagebox.showinfo("提示", "测试成功")