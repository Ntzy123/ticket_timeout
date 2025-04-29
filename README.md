
<h1 style="text-align:center" align="center">Ticket Timeout</h1>

## ticket.py 工单查询库

- ## class Ticket:

    1. #### def load(self): #加载配置文件
        - 读取config文件里的url, json, headers数据，并修改查询时间（这段需要分离出def方法）
    
    2.  #### def query(self): #查询工单
        - 用户传入search，status, fm_type, ticket_type, time_range(start, end)参数  
        - requests发起post请求(url, json, headers)，存储在self.data中  
        - ~~for处理返回data数据导出export.json~~   ：***待做***

    3. #### def query_timeout_pm(self): #查询20分钟超时提醒
        - 定义列表ticket_timeout存储 每一条超时工单数据 ：***待做***  
        - 然后统计数量return dict超时工单数量，data数据dict

    4. #### def _timeout_pm(self): #子方法
        - 遍历self.data，利用datetime比较时间，将超时工单存入ticket_timeout
        - return text（暂定）

    5. #### 同以上两个方法，不过是提醒FM工单接单超时

## ticket_timeout_pm.py

- ## def ticket_timeout_pm
    - 123
