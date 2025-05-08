# ticket_timeout_od.py

import time, threading
from datetime import datetime
from lib.ticket import Ticket


class TicketTimeoutOD:
    # 构造函数
    def __init__(self):
        self.tk = Ticket()
        self.content = None
        self.lock = threading.Lock()

    # 循环查询
    def query(self):
        with self.lock:
            self.tk.load(".config.json")
            self.content = self.tk.query(status="['1', '1001', '1002', '1003', '1004', '1005', '1013', '1014', '4040']", fm_type="OD", ticket_type=[], time_range="today")
            
    def query_timeout(self):
        ticket_timeout = {
            'num': '0',
            'data': []
        }
        with self.lock:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if self.content['msg'] == "success":
                ticket_timeout = self.tk.query_timeout("od")
            """ 测试输出
                if int(ticket_timeout['num']) >= 1:
                    print(f"{current_time}\n你有{ticket_timeout['num']}条临时性工单即将超时，请及时处理！\n\n")
                else:
                    print(f"{current_time}\n暂无即将超时的临时性工单\n\n")
            else:
                print(f"{current_time}\n暂无即将超时的临时性工单\n\n")
            """
            return ticket_timeout