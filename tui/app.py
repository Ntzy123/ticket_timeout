# tui/app.py

import threading
import time
import sys
import os
import pygame
import requests
import logging
from collections import deque
from datetime import datetime, timezone, timedelta

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, RichLog
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from rich.text import Text

from feature.ticket_timeout_pm import TicketTimeoutPM
from feature.ticket_timeout_od import TicketTimeoutOD
from lib.init_app import init_app

logger = logging.getLogger("ticket_timeout")


def format_remaining(deadline: datetime) -> str:
    """格式化剩余时间"""
    remaining = deadline - datetime.now()
    total_seconds = int(remaining.total_seconds())
    if total_seconds < 0:
        return "已超时"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_remaining_style(deadline: datetime) -> str:
    """根据剩余时间返回颜色样式"""
    remaining = deadline - datetime.now()
    total_minutes = remaining.total_seconds() / 60
    if total_minutes < 0:
        return "bold red"
    elif total_minutes < 30:
        return "red"
    elif total_minutes < 120:
        return "yellow"
    else:
        return "green"


def get_resource_path(relative_path: str) -> str:
    if not os.path.isfile("./sound.mp3"):
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
    return "./sound.mp3"


def fetch_internet_time():
    """从互联网时间API获取当前时间，失败则返回None"""
    apis = [
        "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
        "https://timeapi.io/api/Time/current/zone?timeZone=Asia/Shanghai",
    ]
    for api_url in apis:
        try:
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if "datetime" in data:
                    return datetime.fromisoformat(data["datetime"].replace("Z", "+00:00"))
                if "dateTime" in data:
                    return datetime.fromisoformat(data["dateTime"])
        except Exception:
            continue
    return None


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TicketMonitorApp(App):
    """工单超时监控终端 - TUI 应用"""

    TITLE = "工单超时监控终端"

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 36;
        border: tall $border;
        border-right: none;
        background: $surface;
    }

    #log-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
    }

    #query-log {
        height: 1fr;
        border: none;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #right-panel {
        layout: vertical;
        width: 1fr;
    }

    #od-panel {
        height: 1fr;
        border: tall $border;
        background: $surface;
    }

    #pm-panel {
        height: 1fr;
        border: tall $border;
        border-top: none;
        background: $surface;
    }

    #od-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
    }

    #pm-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
    }

    #od-table, #pm-table {
        height: 1fr;
    }

    Header {
        background: $primary-background;
    }

    Footer {
        background: $primary-background;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出", key_display="Q"),
        Binding("r", "force_refresh", "强制刷新", key_display="R"),
    ]

    def __init__(self, wait_time: int = 120, end_time: tuple = None, **kwargs):
        super().__init__(**kwargs)
        self.wait_time = wait_time
        self.end_time = end_time  # (hour, minute) or None
        self._lock = threading.Lock()
        self._latest_od_data = None
        self._latest_pm_data = None
        self._prev_od_ids: set = set()
        self._prev_pm_ids: set = set()
        self._sound_loaded = False
        self._tkpm = None
        self._tkod = None
        self._pending_logs: deque = deque()

    # ── 日志推送（线程安全） ──────────────────────────────────
    def _log(self, msg: str):
        """线程安全地向日志队列写入一条消息"""
        with self._lock:
            self._pending_logs.append(msg)

    def _flush_logs(self):
        """将队列中的日志刷到 RichLog 组件"""
        with self._lock:
            logs = list(self._pending_logs)
            self._pending_logs.clear()
        if not logs:
            return
        log = self.query_one("#query-log")
        for msg in logs:
            log.write(msg)

    # ── 界面组装 ────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Static("查询日志  ● 正常", id="log-header")
                yield RichLog(id="query-log", highlight=True, markup=True, wrap=True, max_lines=1000)
            with Vertical(id="right-panel"):
                with Vertical(id="od-panel"):
                    yield Static("▶ 即将超时 · 临时性工单", id="od-header")
                    yield DataTable(id="od-table")
                with Vertical(id="pm-panel"):
                    yield Static("↻ 即将超时 · 周期性工单", id="pm-header")
                    yield DataTable(id="pm-table")
        yield Footer()

    def on_mount(self) -> None:
        # 初始化配置
        init_app()

        # 认证检查
        try:
            self._log(f"[dim]{now_str()}[/dim]")
            self._log("[cyan]正在进行认证...[/cyan]")
            url = "http://kyrian.asia/api/get_auth"
            if requests.get(url, timeout=5).text != "OK":
                self._log("[bold red]认证失败，程序退出[/bold red]")
                self.exit()
                return
            self._log("[green]认证通过[/green]")
            self._log("")
        except Exception:
            self._log("[bold red]认证请求异常，程序退出[/bold red]")
            self.exit()
            return

        # 初始化音频
        try:
            sound_path = get_resource_path("res/sound.mp3")
            pygame.mixer.init()
            pygame.mixer.music.load(sound_path)
            self._sound_loaded = True
        except Exception:
            self._sound_loaded = False

        # 设置表格列
        od_table = self.query_one("#od-table")
        od_table.add_columns("工单编号", "任务描述", "状态", "剩余时间")
        pm_table = self.query_one("#pm-table")
        pm_table.add_columns("工单编号", "任务描述", "状态", "剩余时间")

        # 启动日志——先于查询输出
        self._log(f"[dim]{now_str()}[/dim]")
        self._log("[cyan]程序启动中...[/cyan]")
        self._log(f"[cyan]临时性工单查询间隔: {self.wait_time}秒[/cyan]")
        if self.end_time is not None:
            self._log(f"[cyan]程序将在 {self.end_time[0]:02d}:{self.end_time[1]:02d} 自动关闭[/cyan]")
        self._log("[green]程序启动完成！[/green]")
        self._log("")

        self._tkpm = TicketTimeoutPM()
        self._tkod = TicketTimeoutOD()

        # 启动一个后台线程，串行执行首次查询，然后保持周期轮询
        t = threading.Thread(target=self._startup_sequence, daemon=True)
        t.start()

        # 定时关机守护
        if self.end_time is not None:
            t3 = threading.Thread(target=self._shutdown_watcher, daemon=True)
            t3.start()

        # 定期刷新UI（1秒间隔，保证日志及时展示）
        self.set_interval(1, self._refresh_ui)

    def _startup_sequence(self):
        """首次查询串行执行：OD → PM，然后启动周期线程"""
        self._run_od_query()
        self._run_pm_query()
        # 首次查询完成后，启动周期循环线程
        threading.Thread(target=self._pm_query_loop, daemon=True).start()
        threading.Thread(target=self._od_query_loop, daemon=True).start()

    def _pm_query_loop(self):
        """PM工单周期查询循环（启动后先等待，避免与首次查询重复）"""
        time.sleep(300)  # 先等待一个周期
        while True:
            try:
                self._run_pm_query()
                time.sleep(300)
            except Exception as e:
                self._log(f"[bold red]PM周期异常: {e}[/bold red]")
                time.sleep(10)

    def _od_query_loop(self):
        """OD工单周期查询循环（启动后先等待，避免与首次查询重复）"""
        time.sleep(self.wait_time)  # 先等待一个周期
        while True:
            try:
                self._run_od_query()
                time.sleep(self.wait_time)
            except Exception as e:
                self._log(f"[bold red]OD周期异常: {e}[/bold red]")
                time.sleep(10)

    def _run_od_query(self):
        """执行一次OD查询并输出结果日志"""
        try:
            self._tkod.query()
            while self._tkod.content is None:
                time.sleep(1)
            with self._lock:
                self._latest_od_data = self._tkod.query_timeout()
            od_count = int(self._latest_od_data.get("num", 0))
            self._log(f"[dim]{now_str()}[/dim]")
            if od_count > 0:
                self._log(f"[bold red]发现 {od_count} 个即将超时的临时性工单[/bold red]")
            else:
                self._log("[dim]暂无即将超时的临时性工单[/dim]")
            self._log("")
        except Exception as e:
            self._log(f"[bold red]OD查询异常: {e}[/bold red]")

    def _run_pm_query(self):
        """执行一次PM查询并输出结果日志"""
        try:
            self._tkpm.query()
            while self._tkpm.content is None:
                time.sleep(1)
            with self._lock:
                self._latest_pm_data = self._tkpm.query_timeout()
            pm_count = int(self._latest_pm_data.get("num", 0))
            self._log(f"[dim]{now_str()}[/dim]")
            if pm_count > 0:
                self._log(f"[yellow]发现 {pm_count} 个即将超时的周期性工单[/yellow]")
            else:
                self._log("[dim]暂无即将超时的周期性工单[/dim]")
            self._log("")
        except Exception as e:
            self._log(f"[bold red]PM查询异常: {e}[/bold red]")

    # ── 界面刷新 ────────────────────────────────────────────
    def _refresh_ui(self):
        """每1秒刷一次：刷新日志 + 更新表格数据"""
        self._flush_logs()

        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data

        # 更新OD表格
        od_table = self.query_one("#od-table")
        od_table.clear()
        if od_data is not None:
            od_count = int(od_data.get("num", 0))
            od_items = od_data.get("data", [])
            if od_count > 0:
                for item in od_items:
                    remaining = format_remaining(item["deadline"])
                    style = get_remaining_style(item["deadline"])
                    od_table.add_row(
                        item["workorderNo"],
                        item.get("workorderDescription", ""),
                        item.get("workorderStatusName", ""),
                        Text(remaining, style=style),
                    )
            else:
                od_table.add_row("", "暂无即将超时的临时性工单", "", "")
        else:
            od_table.add_row("", "等待首次查询...", "", "")

        # 更新PM表格
        pm_table = self.query_one("#pm-table")
        pm_table.clear()
        if pm_data is not None:
            pm_count = int(pm_data.get("num", 0))
            pm_items = pm_data.get("data", [])
            if pm_count > 0:
                for item in pm_items:
                    remaining = format_remaining(item["deadline"])
                    style = get_remaining_style(item["deadline"])
                    pm_table.add_row(
                        item["workorderNo"],
                        item.get("workorderDescription", ""),
                        item.get("workorderStatusName", ""),
                        Text(remaining, style=style),
                    )
            else:
                pm_table.add_row("", "暂无即将超时的周期性工单", "", "")
        else:
            pm_table.add_row("", "等待首次查询...", "", "")

        # 更新标题栏
        self._update_headers()

    def _update_headers(self):
        """更新面板标题中的状态指示"""
        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data

        od_count = int(od_data.get("num", 0)) if od_data else -1
        pm_count = int(pm_data.get("num", 0)) if pm_data else -1

        od_header = self.query_one("#od-header")
        pm_header = self.query_one("#pm-header")
        log_header = self.query_one("#log-header")

        if od_count >= 0:
            od_header.update(
                f"▶ 即将超时 · 临时性工单    {'⚠ 待处理 ' + str(od_count) if od_count > 0 else '— 无'}"
            )
        else:
            od_header.update("▶ 即将超时 · 临时性工单    ⏳ 查询中")

        if pm_count >= 0:
            pm_header.update(
                f"↻ 即将超时 · 周期性工单    {'⚠ 待确认 ' + str(pm_count) if pm_count > 0 else '— 无'}"
            )
        else:
            pm_header.update("↻ 即将超时 · 周期性工单    ⏳ 查询中")

        has_alert = (od_count > 0) or (pm_count > 0)
        log_header.update(f"查询日志  {'● 告警' if has_alert else '● 正常'}")

    # ── 音频 ────────────────────────────────────────────────
    def _play_sound(self):
        """播放提醒音效"""
        if self._sound_loaded:
            try:
                pygame.mixer.music.play()
            except Exception:
                pass

    # ── 定时关机 ────────────────────────────────────────────
    def _shutdown_watcher(self):
        """定期检查互联网时间，到达指定时间后关闭程序"""
        if self.end_time is None:
            return
        end_hour, end_minute = self.end_time
        tz_shanghai = timezone(timedelta(hours=8))
        while True:
            try:
                now = fetch_internet_time()
                if now is not None:
                    now_shanghai = now.astimezone(tz_shanghai)
                    if now_shanghai.hour == end_hour and now_shanghai.minute >= end_minute:
                        self._log(f"[bold red]已到达设定结束时间 {end_hour:02d}:{end_minute:02d}，程序退出中...[/bold red]")
                        time.sleep(1)
                        os._exit(0)
                time.sleep(30)
            except Exception:
                time.sleep(60)

    # ── 动作 ────────────────────────────────────────────────
    def action_force_refresh(self):
        """强制刷新：串行执行一次OD + PM查询，日志按顺序输出"""
        t = threading.Thread(target=self._force_refresh_all, daemon=True)
        t.start()

    def _force_refresh_all(self):
        """串行执行OD和PM强制刷新，确保日志顺序"""
        self._run_od_query()
        self._run_pm_query()

        self._log("")
