# main.py

import json, requests
from pprint import pprint

class Ticket:
    def load(self, filename):
        with open(filename, 'r', encoding='utf-8') as file:
            self.config = json.load(file)
            #self.content = self.config['query_content']
            #self.time_range = self.config['query_time_range']
            self.url = self.config['url']
            self.headers = self.config['headers']
            self.json = self.config['json']
            


if __name__ == '__main__':
    tk = Ticket()
    tk.load('config.json')   
    pprint(tk.config)