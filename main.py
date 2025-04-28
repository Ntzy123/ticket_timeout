# main.py

import json, requests, time, threading, os
from datetime import date, datetime, timedelta
from pprint import pprint as pp

class Ticket:
    
    # 加载配置文件
    def load(self,filename):
        """
        # 读取用户配置文件
        with open(toml_filename, 'rb') as file:
            self.content = self.config['query_content']
            self.time_range = self.config['query_time_range']
            self.shift = self.config['is_day_shift']
        """

        # 读取res配置文件
        with open(filename, 'r', encoding='utf-8') as file:
            config = json.load(file)
            self.url = config['url']
            self.headers = config['headers']
            self.json = config['json']
            current_date = str(date.today())
            yesterday_date = str(date.today() - timedelta(days=1))
            self.json['data1'] = [yesterday_date, current_date]
            self.json['startTime'] = f"{yesterday_date} 00:00:00"
            self.json['endTime'] = f"{current_date} 23:59:59"

    # 子方法 20分钟超时提醒
    def _timeout(self, record, timeout_ticket):
        current_time = datetime.now()
        target_time = datetime.strptime(record['feedBackTime'], "%Y-%m-%d %H:%M:%S")
        alert_time = target_time - timedelta(minutes=20)
        if current_time >= alert_time:
            # print("您有一条待处理的工单，任务即将超时请及时处理！")
            data = {
                'workorderTitle': record.get('workorderTitle'),
                'acceptName': record.get('acceptName'),
                'feedBackTime': record.get('workorderTitle')
            }
            timeout_ticket['data'].append(data)

    # 20分钟超时提醒
    def query_timeout(self):
        for record in self.data['data']['records']:
            timeout_ticket = {'data': []}
            self._timeout(record, timeout_ticket)
            timeout_ticket_num = len(timeout_ticket['data'])
            for data in timeout_ticket['data']:
                text = (
                f"任务描述：\t{record['workorderTitle']}\n"
                f"接单人：\t{record['acceptName']}\n"
                f"超时时间：\t{record['feedBackTime']}\n" 
                + "-" * 20 + "\n")
                #print("任务描述：\t", record['workorderTitle'])
                #print("接单人：\t", record['acceptName'])
                #print("超时时间：\t", record['feedBackTime'])
                #print("\n", "-" * 20, "\n")
                print(text)

    # 查询工单
    def query(self):
        res = requests.post(self.url, json=self.json, headers=self.headers)
        self.data = res.json()
        #查询
        for record in self.data['data']['records']:
            # 输出内容
            """
            print("任务描述：\t", record['workorderTitle'])
            print("状态：\t\t", record['workorderStatusName'])
            print("接单人：\t", record['acceptName'])
            print("超时时间：\t", record['feedBackTime'])
            print("\n", "-" * 50, "\n")
            """
            # 导出已查询工单
            config = {"data": []}
            data = {
                "workorderNo": record.get('workorderNo'),
                "workorderTitle": record.get('workorderTitle'),
                "workorderStatusName": record.get('workorderStatusName'),
                "acceptName": record.get('acceptName'),
                "feedBackTime": record.get('feedBackTime')
            }
            config['data'].append(data)
        with open ("export.json", "w", encoding="utf-8") as file:
            json.dump(config, file, indent=4, ensure_ascii=False)

# 循环查询
def poll(tk):
    while True:
        time.sleep(300)
        tk.query()
            
if __name__ == '__main__':
    tk = Ticket()
    tk.load(".config.json")
    tk.query()
    t = threading.Thread(target=poll,args=(tk,))
    while True:
        tk.load(".config.json")
        tk.query_timeout()
        time.sleep(60)
    
    #pprint(tk.config)