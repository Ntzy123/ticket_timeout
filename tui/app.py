# tui/app.py — 入口与核心调度

import ctypes
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
from lib import api as lib_api
from lib.auto_assigner import auto_assign_single
from tui.common import (
    format_remaining, get_remaining_style, truncate, now_str,
    load_api_config, load_ignored_set, add_ignored,
)
from tui.detail_screen import DetailScreen
from tui.ignore_screen import IgnoreListScreen
from tui.auto_assign_screen import AutoAssignScreen

logger = logging.getLogger("ticket_timeout")

# 确保日志输出到文件（避免重复添加）
if not logger.handlers:
    _log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ticket_timeout.log")
    _fh = logging.FileHandler(_log_file, encoding="utf-8", mode="a")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_fh)
    logger.setLevel(logging.DEBUG)


def get_resource_path(relative_path: str) -> str:
    """获取资源文件路径（支持 PyInstaller 打包）"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def fetch_internet_time():
    """从互联网时间API获取当前东八区时间，失败则返回None"""
    tz_shanghai = timezone(timedelta(hours=8))
    apis = [
        "https://timeapi.io/api/Time/current/zone?timeZone=Asia/Shanghai",
        "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
    ]
    for api_url in apis:
        try:
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                dt_str = data.get("datetime") or data.get("dateTime")
                if dt_str:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    # 确保 datetime 带有时区信息
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=tz_shanghai)
                    return dt
        except Exception:
            continue
    return None


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
        Binding("ctrl+q", "quit", "退出", key_display="Ctrl+Q"),
        Binding("r", "force_refresh", "刷新", key_display="R"),
        Binding("i", "ignore_ticket", "忽略工单", key_display="I"),
        Binding("v", "manage_ignored", "忽略列表", key_display="V"),
        Binding("o", "open_auto_assign", "自动指派", key_display="O"),
    ]

    def __init__(self, wait_time: int = 120, end_time: tuple = None, **kwargs):
        super().__init__(**kwargs)
        self.wait_time = wait_time
        self.end_time = end_time
        self._lock = threading.Lock()
        self._latest_od_data = None
        self._latest_pm_data = None
        self._prev_od_ids: set = set()
        self._prev_pm_ids: set = set()
        self._notified_od_ids: set = set()
        self._notified_pm_ids: set = set()
        self._sound_loaded = False
        self._tkpm = None
        self._tkod = None
        self._pending_logs: deque = deque()
        self._api_headers: dict = {}
        self._api_project_id: str = "52010017"
        self._api_source: str = "02"
        self._selected_ticket: dict | None = None
        self._od_row_keys: list = []
        self._pm_row_keys: list = []
        self._ignored_set: set[str] = set()
        self._auto_assigned_od_ids: set[str] = set()      # 所有发起过指派的（用于去重）
        self._auto_assign_success_ids: set[str] = set()   # 仅指派成功的（用于首页过滤）

    # ── 日志推送（线程安全） ──────────────────────────────────
    def _log(self, msg: str):
        with self._lock:
            self._pending_logs.append(msg)

    def _flush_logs(self):
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
        init_app()
        self._ignored_set = load_ignored_set()

        try:
            self._log(f"[dim]{now_str()}[/dim]")
            self._log("[cyan]正在进行认证...[/cyan]")
            url = "https://kyrian.asia/api/get_auth"
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

        try:
            cfg = load_api_config()
            self._api_headers = cfg
            self._api_project_id = lib_api.DEFAULT_PROJECT_ID
            self._api_source = lib_api.DEFAULT_SOURCE
        except Exception:
            self._log("[bold red]API配置加载失败[/bold red]")

        try:
            sound_path = get_resource_path("res/sound.mp3")
            pygame.mixer.init()
            pygame.mixer.music.load(sound_path)
            self._sound_loaded = True
        except Exception:
            self._sound_loaded = False

        od_table = self.query_one("#od-table")
        od_table.add_column("工单编号", key="id", width=16)
        od_table.add_column("任务描述", key="desc")
        od_table.add_column("状态", key="status", width=8)
        od_table.add_column("剩余时间", key="time", width=10)
        od_table.cursor_type = "row"

        pm_table = self.query_one("#pm-table")
        pm_table.add_column("工单编号", key="id", width=16)
        pm_table.add_column("任务描述", key="desc")
        pm_table.add_column("处理人", key="handler", width=8)
        pm_table.add_column("状态", key="status", width=8)
        pm_table.add_column("剩余时间", key="time", width=10)
        pm_table.cursor_type = "row"

        self._log(f"[dim]{now_str()}[/dim]")
        self._log("[cyan]程序启动中...[/cyan]")
        self._log(f"[cyan]临时性工单查询间隔: {self.wait_time}秒[/cyan]")
        if self.end_time is not None:
            self._log(f"[cyan]程序将在 {self.end_time[0]:02d}:{self.end_time[1]:02d} 自动关闭[/cyan]")
        self._log("[green]程序启动完成！[/green]")
        self._log("")

        self._tkpm = TicketTimeoutPM()
        self._tkod = TicketTimeoutOD()

        t = threading.Thread(target=self._startup_sequence, daemon=True)
        t.start()

        if self.end_time is not None:
            t3 = threading.Thread(target=self._shutdown_watcher, daemon=True)
            t3.start()

        self.set_interval(1, self._flush_logs)
        self.set_interval(1, self._update_time_column)

    def _startup_sequence(self):
        threading.Thread(target=self._pm_query_loop, daemon=True).start()
        threading.Thread(target=self._od_query_loop, daemon=True).start()
        self._run_od_query()
        self._run_pm_query()

    def _pm_query_loop(self):
        time.sleep(300)
        while True:
            try:
                self._run_pm_query()
                time.sleep(300)
            except Exception as e:
                self._log(f"[bold red]PM周期异常: {e}[/bold red]")
                time.sleep(10)

    def _od_query_loop(self):
        time.sleep(self.wait_time)
        while True:
            try:
                self._run_od_query()
                time.sleep(self.wait_time)
            except Exception as e:
                self._log(f"[bold red]OD周期异常: {e}[/bold red]")
                time.sleep(10)

    def _run_od_query(self, suppress_notifications: bool = False):
        try:
            self._tkod.query()
            while self._tkod.content is None:
                time.sleep(1)
            with self._lock:
                self._latest_od_data = self._tkod.query_timeout()
            od_items = self._latest_od_data.get("data", [])
            od_count = len(od_items)
            msg = self._tkod.content.get("msg", "unknown") if self._tkod.content else "unknown"
            logger.info(f"[OD查询] msg={msg}, 超时工单数={od_count}")

            now = datetime.now()
            urgent_items = [i for i in od_items if (i['deadline'] - now).total_seconds() <= 900]
            urgent_ids = {i['workorderNo'] for i in urgent_items}
            new_urgent_ids = urgent_ids - self._notified_od_ids - self._ignored_set

            self._log(f"[dim]{now_str()}[/dim]")
            if od_count > 0:
                self._log(f"[bold red]发现 {od_count} 个即将超时的临时性工单[/bold red]")
                if urgent_ids and not suppress_notifications:
                    self._play_sound()
                if new_urgent_ids and not suppress_notifications:
                    self._show_popup(f"你有 {len(new_urgent_ids)} 条临时性工单即将超时，请及时处理！")
                    self._notified_od_ids.update(new_urgent_ids)
                # 自动指派：对所有新出现的临时工单启动后台指派（仅首次查询到时触发）
                if not suppress_notifications:
                    new_ids = {i['workorderNo'] for i in od_items} - self._auto_assigned_od_ids - self._ignored_set
                    if new_ids:
                        self._log(f"[dim]{now_str()}[/dim]")
                        self._log(f"[cyan]自动指派: 对 {len(new_ids)} 个临时工单发起指派...[/cyan]")
                        success_count = [0]
                        success_lock = threading.Lock()

                        def on_result(success, info):
                            if success:
                                with success_lock:
                                    success_count[0] += 1
                                with self._lock:
                                    self._auto_assign_success_ids.add(info["workorderNo"])

                        threads = []
                        for wo_no in new_ids:
                            etl_code = next(
                                (i.get('etlCode', '') for i in od_items if i['workorderNo'] == wo_no), ''
                            )
                            t = threading.Thread(
                                target=auto_assign_single,
                                args=(wo_no, etl_code,
                                      self._api_project_id, self._api_source),
                                kwargs={'callback': on_result},
                                daemon=True,
                            )
                            t.start()
                            threads.append(t)
                        # 立即加入去重集合，确保下次查询不重复发起
                        self._auto_assigned_od_ids.update(new_ids)
                        for t in threads:
                            t.join(timeout=20)
                        if success_count[0] > 0:
                            self._log(f"[green]自动指派完成: 成功 {success_count[0]} / {len(new_ids)} 个工单[/green]")
                        else:
                            self._log(f"[yellow]自动指派: 完成 0 / {len(new_ids)} 个工单（可能不满足指派条件）[/yellow]")
            else:
                self._log("[dim]暂无即将超时的临时性工单[/dim]")
            self._log("")
            self.call_from_thread(self._refresh_tables)
        except Exception as e:
            logger.error(f"[OD查询] 异常: {e}")
            self._log(f"[bold red]OD查询异常: {e}[/bold red]")

    def _run_pm_query(self, suppress_notifications: bool = False):
        try:
            self._tkpm.query()
            while self._tkpm.content is None:
                time.sleep(1)
            with self._lock:
                self._latest_pm_data = self._tkpm.query_timeout()
            pm_items = self._latest_pm_data.get("data", [])
            msg = self._tkpm.content.get("msg", "unknown") if self._tkpm.content else "unknown"
            logger.info(f"[PM查询] msg={msg}, 总工单数={len(pm_items)}")
            now = datetime.now()
            critical = [i for i in pm_items if (i['deadline'] - now).total_seconds() < 1800]
            new_critical_ids = {i['workorderNo'] for i in critical} - self._notified_pm_ids - self._ignored_set
            self._log(f"[dim]{now_str()}[/dim]")
            if critical:
                self._log(f"[bold yellow]发现 {len(critical)} 个即将超时的周期性工单（剩余 < 30 分钟）[/bold yellow]")
                if not suppress_notifications:
                    self._play_sound()
                if new_critical_ids and not suppress_notifications:
                    self._show_popup(f"你有 {len(new_critical_ids)} 条周期性工单即将超时，请及时处理！")
                    self._notified_pm_ids.update(new_critical_ids)
            else:
                self._log("[dim]周期性工单状态正常[/dim]")
            self._log("")
            self.call_from_thread(self._refresh_tables)
        except Exception as e:
            logger.error(f"[PM查询] 异常: {e}")
            self._log(f"[bold red]PM查询异常: {e}[/bold red]")

    # ── 界面刷新 ────────────────────────────────────────────
    def _refresh_tables(self):
        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data

        od_table = self.query_one("#od-table")
        pm_table = self.query_one("#pm-table")

        # 保存当前选中的工单号，刷新后恢复
        od_selected = self._get_selected_workorder_no(od_table)
        pm_selected = self._get_selected_workorder_no(pm_table)

        # 只清除行，保留列定义（避免游标和焦点重置）
        od_table.clear()
        self._od_row_keys.clear()
        if od_data is not None:
            od_count = int(od_data.get("num", 0))
            od_items = od_data.get("data", [])
            if od_count > 0:
                for item in od_items:
                    if item["workorderNo"] in self._ignored_set or item["workorderNo"] in self._auto_assign_success_ids:
                        continue
                    remaining_text = format_remaining(item["deadline"])
                    remaining_style = get_remaining_style(item["deadline"], "OD")
                    row = od_table.add_row(
                        item["workorderNo"],
                        truncate(item.get("workorderDescription", ""), 60),
                        item.get("workorderStatusName", ""),
                        Text(remaining_text, style=remaining_style),
                    )
                    self._od_row_keys.append(row)
                if not self._od_row_keys:
                    od_table.add_row("", "暂无即将超时的临时性工单", "", "")
            else:
                od_table.add_row("", "暂无即将超时的临时性工单", "", "")
        else:
            od_table.add_row("", "等待首次查询...", "", "")
        if od_selected:
            self._restore_table_cursor(od_table, od_selected, self._od_row_keys)

        pm_table.clear()
        self._pm_row_keys.clear()
        if pm_data is not None:
            pm_count = int(pm_data.get("num", 0))
            pm_items = pm_data.get("data", [])
            if pm_count > 0:
                for item in pm_items:
                    if item["workorderNo"] in self._ignored_set:
                        continue
                    remaining_text = format_remaining(item["deadline"])
                    remaining_style = get_remaining_style(item["deadline"], "PM")
                    handler = item.get("acceptName") or "None"
                    row = pm_table.add_row(
                        item["workorderNo"],
                        truncate(item.get("workorderDescription", ""), 60),
                        handler,
                        item.get("workorderStatusName", ""),
                        Text(remaining_text, style=remaining_style),
                    )
                    self._pm_row_keys.append(row)
            else:
                pm_table.add_row("", "暂无即将超时的周期性工单", "", "", "")
        else:
            pm_table.add_row("", "等待首次查询...", "", "")
        if pm_selected:
            self._restore_table_cursor(pm_table, pm_selected, self._pm_row_keys)

        self._update_headers()

    def _update_time_column(self):
        try:
            with self._lock:
                od_data = self._latest_od_data
                pm_data = self._latest_pm_data
            od_table = self.query_one("#od-table")
            if od_data and int(od_data.get("num", 0)) > 0:
                items = [i for i in od_data.get("data", [])
                         if i["workorderNo"] not in self._ignored_set
                         and i["workorderNo"] not in self._auto_assign_success_ids]
                for i, item in enumerate(items):
                    if i < len(self._od_row_keys):
                        remaining_text = format_remaining(item["deadline"])
                        remaining_style = get_remaining_style(item["deadline"], "OD")
                        od_table.update_cell(
                            self._od_row_keys[i], "time",
                            Text(remaining_text, style=remaining_style),
                        )
            pm_table = self.query_one("#pm-table")
            if pm_data and int(pm_data.get("num", 0)) > 0:
                items = [i for i in pm_data.get("data", []) if i["workorderNo"] not in self._ignored_set]
                for i, item in enumerate(items):
                    if i < len(self._pm_row_keys):
                        remaining_text = format_remaining(item["deadline"])
                        remaining_style = get_remaining_style(item["deadline"], "PM")
                        pm_table.update_cell(
                            self._pm_row_keys[i], "time",
                            Text(remaining_text, style=remaining_style),
                        )
            self._update_headers()
        except Exception:
            pass

    def _update_headers(self):
        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data
        if od_data:
            od_items = [i for i in od_data.get("data", [])
                        if i["workorderNo"] not in self._ignored_set
                        and i["workorderNo"] not in self._auto_assign_success_ids]
        else:
            od_items = []
        od_count = len(od_items) if od_data else -1
        if pm_data:
            pm_items = [i for i in pm_data.get("data", []) if i["workorderNo"] not in self._ignored_set]
        else:
            pm_items = []
        pm_count = len(pm_items) if pm_data else -1
        now = datetime.now()
        pm_critical = sum(1 for item in pm_items if (item['deadline'] - now).total_seconds() < 1800)
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
                f"↻ 即将超时 · 周期性工单    {'⚠ ' + str(pm_count) if pm_count > 0 else '— 无'}"
            )
        else:
            pm_header.update("↻ 即将超时 · 周期性工单    ⏳ 查询中")
        has_alert = (od_count > 0) or (pm_critical > 0)
        log_header.update(f"查询日志  {'● 告警' if has_alert else '● 正常'}")

    # ── 音频 ────────────────────────────────────────────────
    def _play_sound(self):
        if self._sound_loaded:
            try:
                pygame.mixer.music.play()
            except Exception:
                pass

    def _show_popup(self, msg: str):
        try:
            threading.Thread(
                target=lambda: ctypes.windll.user32.MessageBoxW(0, msg, "工单超时提醒", 0),
                daemon=True,
            ).start()
        except Exception:
            pass

    # ── 定时关机 ────────────────────────────────────────────
    def _shutdown_watcher(self):
        if self.end_time is None:
            return
        end_hour, end_minute = self.end_time
        tz_shanghai = timezone(timedelta(hours=8))

        def _should_trigger(now_shanghai):
            """判断是否应该触发关闭"""
            target = now_shanghai.replace(
                hour=end_hour, minute=end_minute, second=0, microsecond=0
            )
            diff = (target - now_shanghai).total_seconds()
            if diff > 0 and diff <= 120:
                return diff, True
            if -300 <= diff <= 0:
                return 0, True
            return None, False

        # 第一次检查
        try:
            local_now = datetime.now().astimezone(tz_shanghai)
            trigger_time, should = _should_trigger(local_now)
            if should:
                self._log(
                    f"[yellow]即将关闭，倒计时 {int(max(0, trigger_time))}s[/yellow]"
                )
                threading.Thread(
                    target=self._local_countdown_exit,
                    args=(max(0, trigger_time), end_hour, end_minute),
                    daemon=True,
                ).start()
                return
        except Exception as e:
            logger.exception(f"初始时间检查异常: {e}")

        # 后续巡检（全程使用本地时间）
        while True:
            try:
                now = datetime.now().astimezone(tz_shanghai)
                trigger_time, should = _should_trigger(now)
                if should:
                    self._log(
                        f"[yellow]即将关闭，倒计时 {int(max(0, trigger_time))}s[/yellow]"
                    )
                    threading.Thread(
                        target=self._local_countdown_exit,
                        args=(max(0, trigger_time), end_hour, end_minute),
                        daemon=True,
                    ).start()
                    return
                time.sleep(10)
            except Exception as e:
                logger.exception(f"巡检异常: {e}")
                time.sleep(10)

    def _local_countdown_exit(self, seconds: float, end_hour: int, end_minute: int):
        time.sleep(max(0, seconds))
        self._log(f"[bold red]已到达设定时间 {end_hour:02d}:{end_minute:02d}，程序退出[/bold red]")
        try:
            self.call_from_thread(self.exit)
        except Exception as e:
            logger.exception(f"Textual 退出异常: {e}")
            import sys as _sys
            _sys.exit(0)
        # 兜底：5秒后强制退出
        import sys as _sys
        def _force_exit():
            time.sleep(5)
            if self.is_running:
                _sys.exit(0)
        threading.Thread(target=_force_exit, daemon=True).start()

    # ── 表格游标辅助 ────────────────────────────────────────
    def _get_selected_workorder_no(self, table: DataTable) -> str | None:
        """获取当前选中行的工单号"""
        try:
            coord = table.cursor_coordinate
            if coord is None:
                return None
            row = table.get_row_at(coord[0])
            if row and row[0]:
                wo = str(row[0]).strip()
                _placeholders = {"暂无即将超时的临时性工单", "暂无即将超时的周期性工单",
                                 "等待首次查询...", "暂无数据", ""}
                if wo not in _placeholders and len(wo) >= 5:
                    return wo
        except Exception:
            pass
        return None

    def _restore_table_cursor(self, table: DataTable, wo_no: str, row_keys: list) -> None:
        """根据工单号恢复表格选中行"""
        for i, key in enumerate(row_keys):
            try:
                row = table.get_row(key)
                if row and str(row[0]).strip() == wo_no:
                    table.move_cursor(row=i, column=0)
                    break
            except Exception:
                continue

    # ── 动作 ────────────────────────────────────────────────
    def action_force_refresh(self):
        t = threading.Thread(target=self._force_refresh_all, daemon=True)
        t.start()

    def _force_refresh_all(self):
        self._run_od_query(suppress_notifications=True)
        self._run_pm_query(suppress_notifications=True)
        self._log("")
        self.call_from_thread(self._refresh_tables)

    # ── 忽略工单 ────────────────────────────────────────────
    def _find_focused_ticket(self) -> tuple[dict | None, str]:
        for table_id, data_source, wo_type in [
            ("#od-table", self._latest_od_data, "OD"),
            ("#pm-table", self._latest_pm_data, "PM"),
        ]:
            table = self.query_one(table_id)
            try:
                coord = table.cursor_coordinate
                if coord is None:
                    continue
                row = table.get_row_at(coord[0])
            except Exception:
                continue
            if not row or not row[0]:
                continue
            wo_no = str(row[0]).strip()
            _placeholders = {"暂无即将超时的临时性工单", "暂无即将超时的周期性工单",
                             "等待首次查询...", "暂无数据", ""}
            if wo_no in _placeholders or len(wo_no) < 5:
                continue
            if data_source:
                for item in data_source.get("data", []):
                    if item["workorderNo"] == wo_no:
                        return item, wo_type
            return {"workorderNo": wo_no}, wo_type
        return None, ""

    def action_ignore_ticket(self) -> None:
        ticket, wo_type = self._find_focused_ticket()
        if not ticket:
            self.notify("请在有效工单行上按 I 键忽略", severity="warning")
            return
        if wo_type != "OD":
            self.notify("仅临时性工单可忽略", severity="warning")
            return
        wo_no = ticket["workorderNo"]
        if wo_no in self._ignored_set:
            self.notify(f"工单 {wo_no} 已忽略", severity="information")
            return
        desc = ticket.get("workorderDescription", "")
        add_ignored(wo_no, description=desc)
        self._ignored_set.add(wo_no)
        self._notified_od_ids.discard(wo_no)
        self._notified_pm_ids.discard(wo_no)
        self._log(f"[yellow]工单 {wo_no} 已忽略[/yellow]")
        self.notify(f"工单 {wo_no} 已忽略", severity="information")
        self._refresh_tables()

    def action_manage_ignored(self) -> None:
        self.push_screen(
            IgnoreListScreen(),
            callback=lambda _: self._on_ignore_screen_dismissed(),
        )

    def _on_ignore_screen_dismissed(self) -> None:
        self._ignored_set = load_ignored_set()
        self._log("[dim]已忽略工单列表已更新[/dim]")
        self._refresh_tables()

    # ── 自动指派管理 ────────────────────────────────────────
    def action_open_auto_assign(self) -> None:
        self.push_screen(
            AutoAssignScreen(
                headers=self._api_headers,
                project_id=self._api_project_id,
                source=self._api_source,
            ),
        )

    # ── 工单详情 & 指派 ────────────────────────────────────
    def _on_detail_dismissed(self) -> None:
        threading.Timer(5, self._force_refresh_all).start()

    def _get_selected_ticket(self, table_id: str) -> dict | None:
        _placeholders = {"暂无即将超时的临时性工单", "暂无即将超时的周期性工单",
                         "等待首次查询...", "暂无数据", ""}
        table = self.query_one(table_id)
        try:
            coord = table.cursor_coordinate
            if coord is None:
                return None
            row = table.get_row_at(coord[0])
        except Exception:
            return None
        if not row or not row[0]:
            return None
        wo_no = str(row[0]).strip()
        if wo_no in _placeholders or len(wo_no) < 5:
            return None
        data_source = self._latest_od_data if table_id == "#od-table" else self._latest_pm_data
        if data_source:
            for item in data_source.get("data", []):
                if item["workorderNo"] == wo_no:
                    return item
        return {"workorderNo": wo_no}

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            table_id = event.control.id
            if table_id not in ("od-table", "pm-table"):
                return
            ticket = self._get_selected_ticket(f"#{table_id}")
            if not ticket:
                self.notify("当前行不是有效工单", severity="warning")
                return
            self._selected_ticket = ticket
            self.push_screen(
                DetailScreen(
                    workorder_no=ticket["workorderNo"],
                    headers=self._api_headers,
                    etl_code=ticket.get("etlCode", ""),
                    source=self._api_source,
                    project_id=self._api_project_id,
                    wo_type="PM" if table_id == "pm-table" else "OD",
                ),
                callback=lambda _: self._on_detail_dismissed(),
            )
        except Exception as e:
            self.notify(f"操作异常: {e}", severity="error")
