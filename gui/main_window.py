# main_window.py

import tkinter as tk
from tkinter import messagebox


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ticket Timeout")
        #获取屏幕尺寸 and 窗口尺寸，居中启动
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = 400
        window_height = 300
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.resizable(False, False)
        self.withdraw()



# 测试
if __name__ == '__main__':
    window = MainWindow()
    window.mainloop()
    messagebox.showinfo("提示", "测试成功")