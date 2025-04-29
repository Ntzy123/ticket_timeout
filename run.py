# run.py

from feature.ticket_timeout_pm import ticket_timeout_pm


if __name__ == '__main__':
    ticket_timeout_pm()
    
    
    
    
    # 仅测试
    """tk = Ticket()
    tk.load(".config.json")
    tk.query()
    t = threading.Thread(target=poll,args=(tk,))
    while True:
        tk.load(".config.json")
        tk.query_timeout_pm()
        time.sleep(60)
    
    #print(tk.data)"""