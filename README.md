<h1 style="text-align:center" align="center">Ticket Timeout</h1>

## ticket.py 工单查询库

- ## class Ticket:
  
  1. #### def load(self): #加载配置文件
     
     - 读取config文件里的url, json, headers数据
  
  2. #### def query(self): #查询工单
     
     - 用户传入search，status, fm_type, ticket_type, time_range参数（只解决了search和fm_type还有time_range的处理方法）
       - time_range参数：tuple: (start_time, end,time) 或 "today"
     - requests发起post请求(url, json, headers)，存储在self.data中
     - 格式化需要的几项信息存储在config里
     - return config: list[dict]    # 查询到的工单数据：任务描述，状态，接单人，超时时间
  
  3. #### def query_timeout(self, fm_type): #查询20分钟超时提醒
     
     - fm_type参数：FM or PM
     - 定义列表ticket_timeout存储 每一条超时工单数据
     - return ticket_timeout: list[dict]    # 超时工单数量
  
  4. #### def _timeout_pm(self): # pm子方法
     
     - 遍历self.data，利用datetime比较时间，将20分钟后超时的PM工单存入ticket_timeout
  
  5. #### def _timeout_fm(self): # fm子方法
     
     - 遍历self.data，利用datetime比较时间，将单子出现10分钟未指派的FM工单存入ticket_timeout

 

## ticket_timeout_pm.py PM工单超时提醒库

- #### def query(tk): # 循环执行tk.query查询
  
  - 循环执行tk.query查询，每1小时一次

- #### def query_timeout(tk): # 循环执行tk.query_timeout查询工单超时

  - 循环执行tk.query_timeout查询超时工单，每分钟一次



## ticket_timeout_od.py FM工单超时提醒库

- #### def query(tk): # 循环执行tk.query查询
  
  - 循环执行tk.query查询，每2分钟一次

- #### def query_timeout(tk): # 循环执行tk.query_timeout查询工单超时

  - 循环执行tk.query_timeout查询超时工单，每分钟一次



## run.py 主入口

-   #### 子线程用方法

    1.  def tkpm_query

    2.  def tkpm_query_timeout

    3.  def tkod_query

    4.  def tkod_query_timeout

-   #### 主进程入口

    -   将tkpm和tkod定义出来，分别用threading启动query，用tkinter的after启动query_timeout，然后启动tkinter，其中两个query_timeout内里写了messagebox弹窗

### 待做：

1. _query查询里应该对传入参数进行处理，将抽象参数转为可读参数_

2. _OD工单里设置工单“不再提醒”接口_

3. *隐藏启动窗口，做成托盘*

