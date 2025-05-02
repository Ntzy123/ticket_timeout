# ticket.py

import json, requests
from datetime import date, datetime, timedelta

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
            """ 查询并修改时间（弃用，转入query方法）
            current_date = str(date.today())
            yesterday_date = str(date.today() - timedelta(days=1))
            self.json['data1'] = [yesterday_date, current_date]
            self.json['startTime'] = f"{yesterday_date} 00:00:00"
            self.json['endTime'] = f"{current_date} 23:59:59"
            """

    # 查询工单
    def query(self, serach=None, status=None, fm_type=None, ticket_type=None, time_range=None):
        # 处理传入参数写入self.json
        input_param = [serach, status, fm_type, ticket_type, time_range]
        target_param = ["workorderTitle", "workorderStatus", "fmWoType", "workOrderTypeNoList", ["date1", "startTime", "endTime"]]
        workorderTitle = ""
        for i, key in enumerate(target_param):
            if i == 0 and input_param[i] != None:  # 处理工单标题
                workorderTitle = input_param[i]
            elif i == 1 and input_param[i] != None:  # 处理工单status
                self.json[key] = input_param[i]
            elif i == 3 and input_param[i] != None:  # 处理任务类型
                self.json[key] = input_param[i]
            elif i == 4 and input_param[i] != None:  # 处理时间范围
                if time_range == "today":  # 处理时间范围为今天
                    time_range = [str(date.today()), str(date.today())]
                self.json[key[0]] = time_range
                start = f"{time_range[0]} 00:00:00"
                end = f"{time_range[1]} 23:59:59"
                self.json[key[1]] = start
                self.json[key[2]] = end
            elif input_param[i] != None:   # 处理其他参数
                self.json[key] = input_param[i]
        print(self.json)
        # 发起POST请求并存储
        res = requests.post(self.url, json=self.json, headers=self.headers)
        self.data = res.json()

        # 处理返回数据
        config = {
            'msg': self.data['msg'],
            'data': []
        }
        # 获取数据失败直接return
        if config['msg'] != "success":
            return config
        
        for record in self.data['data']['records']:
            # 格式化输出内容
            """
            print("任务描述：\t", record['workorderTitle'])
            print("状态：\t\t", record['workorderStatusName'])
            print("接单人：\t", record['acceptName'])
            print("超时时间：\t", record['feedBackTime'])
            print("\n", "-" * 50, "\n")
            """
            # 导出已查询工单
            data = {
                "workorderNo": record.get('workorderNo'),
                "workorderTitle": record.get('workorderTitle'),
                "workorderStatusName": record.get('workorderStatusName'),
                "acceptName": record.get('acceptName'),
                "feedBackTime": record.get('feedBackTime')
            }
            if workorderTitle in data['workorderStatusName']:
                config['data'].append(data)
        return config
        # 到处export.json （已弃用）
        #with open ("export.json", "w", encoding="utf-8") as file:
            #json.dump(config, file, indent=4, ensure_ascii=False)

    # PM工单20分钟超时提醒
    def query_timeout(self, fm_type=None):
        timeout_ticket = {
            'num': '',
            'data': []
        }
        for record in self.data['data']['records']:
            if fm_type == "fm" or fm_type == "FM":
                self._timeout_fm(record, timeout_ticket)
            elif fm_type == "pm" or fm_type == "PM":
                self._timeout_pm(record, timeout_ticket)
            """ 测试用
            for data in timeout_ticket:
                
                text = (
                    f"任务描述：\t{record['workorderTitle']}\n"
                    f"接单人：\t{record['acceptName']}\n"
                    f"超时时间：\t{record['feedBackTime']}\n" 
                    + "-" * 20 + "\n"
                )
                print(text)
            """
        timeout_ticket['num'] = len(timeout_ticket['data'])
        return timeout_ticket

    # 子方法 FM工单20分钟超时提醒
    def _timeout_fm(self, record, timeout_ticket):
        current_time = datetime.now()
        target_time = datetime.strptime(record['createTime'], "%Y-%m-%d %H:%M:%S")
        alert_time = target_time + timedelta(minutes=10)
        if current_time >= alert_time:
            # print("您有一条待处理的工单，任务即将超时请及时处理！")
            data = {
                'workorderTitle': record.get('workorderTitle'),
                'acceptName': record.get('acceptName'),
                'feedBackTime': record.get('feedBackTime')
            }
            timeout_ticket['data'].append(data)

    # 子方法 PM工单20分钟超时提醒
    def _timeout_pm(self, record, timeout_ticket):
        current_time = datetime.now()
        target_time = datetime.strptime(record['feedBackTime'], "%Y-%m-%d %H:%M:%S")
        alert_time = target_time - timedelta(minutes=20)
        if current_time >= alert_time:
            # print("您有一条待处理的工单，任务即将超时请及时处理！")
            data = {
                'workorderTitle': record.get('workorderTitle'),
                'acceptName': record.get('acceptName'),
                'feedBackTime': record.get('feedBackTime')
            }
            timeout_ticket['data'].append(data)