# tui/app.py

import ctypes
import json
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
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, DataTable, RichLog, Input
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from rich.text import Text

from feature.ticket_timeout_pm import TicketTimeoutPM
from feature.ticket_timeout_od import TicketTimeoutOD
from lib.init_app import init_app

logger = logging.getLogger("ticket_timeout")

# 确保日志输出到文件（避免重复添加）
if not logger.handlers:
    _log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ticket_timeout.log")
    _fh = logging.FileHandler(_log_file, encoding="utf-8", mode="a")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_fh)
    logger.setLevel(logging.DEBUG)


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


def truncate(text: str, max_len: int = 60) -> str:
    """过长文本截断，末尾加..."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."

def ralign(text: str, width: int = 10) -> str:
    """右对齐填充"""
    text = str(text)
    return text.rjust(width) if len(text) < width else text


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


def load_api_config() -> dict:
    """从配置文件加载 API 请求头、projectId、source（过滤掉请求体相关的固定字段）"""
    config_path = ".config.json"
    if not os.path.isfile(config_path):
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        config_path = os.path.join(base, ".config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    headers = cfg.get("headers", {})
    # 移除固定值字段，避免干扰不同 API 请求
    for k in ("Content-Length", "Accept-Encoding"):
        headers.pop(k, None)
    return {
        "headers": headers,
        "project_id": cfg.get("json", {}).get("projectId", "52010017"),
        "source": "02",
    }


# ── 工单详情界面（带指派） ─────────────────────────────
class DetailScreen(ModalScreen):
    """工单详情（含可指派人员切换）"""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #detail-container {
        layout: horizontal;
        height: 1fr;
    }

    #detail-left {
        width: 36;
        border: tall $border;
        border-right: none;
        background: $surface;
    }

    #detail-left-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
    }

    #detail-left-log {
        height: 1fr;
        border: none;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #detail-left-assign {
        height: 1fr;
    }

    #detail-left-search {
        display: none;
        border: solid $border;
        margin: 0 1;
    }

    #detail-right {
        layout: vertical;
        width: 1fr;
    }

    #detail-info {
        height: 1fr;
        border: tall $border;
        border-left: none;
        background: $surface;
    }

    #detail-info-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
    }

    #detail-info-body {
        height: 1fr;
        padding: 1;
        overflow-y: auto;
        overflow-x: auto;
    }

    #detail-time-bar {
        height: 3;
        border: tall $border;
        border-top: none;
        border-left: none;
        background: $surface;
        padding: 0 1;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("a", "toggle_assign", "指派人员", key_display="A"),
        Binding("q", "close", "返回", key_display="Q"),
        Binding("escape", "close", "返回"),
    ]

    def __init__(self, workorder_no: str, headers: dict, etl_code: str = "",
                 source: str = "", project_id: str = "") -> None:
        super().__init__()
        self.workorder_no = workorder_no
        self.headers = headers
        self.etl_code = etl_code
        self.source = source
        self.project_id = project_id
        self._detail_data: dict | None = None
        self._assignees: list = []
        self._selected_assignee: dict | None = None
        self._assign_mode = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="detail-container"):
            with Vertical(id="detail-left"):
                yield Static("详情日志", id="detail-left-header")
                yield Input(placeholder="搜索姓名...", id="detail-left-search")
                yield RichLog(id="detail-left-log", highlight=True, markup=True, wrap=True, max_lines=1000)
                yield DataTable(id="detail-left-assign")
            with Vertical(id="detail-right"):
                with Vertical(id="detail-info"):
                    yield Static("════ 工单详情 ════", id="detail-info-header")
                    yield Static("正在加载...", id="detail-info-body")
                yield Static(id="detail-time-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._log("[dim]加载工单详情...[/dim]")
        # 搜索框默认隐藏
        self.query_one("#detail-left-search", Input).styles.display = "none"
        # 指派表格：姓名、岗位、电话
        assign_table = self.query_one("#detail-left-assign")
        assign_table.add_column("姓名", key="name", width=8)
        assign_table.add_column("岗位", key="role", width=16)
        assign_table.add_column("电话", key="mobile", width=13)
        assign_table.cursor_type = "row"
        assign_table.styles.display = "none"
        # 初始焦点给左侧日志，确保键盘绑定生效
        self.set_focus(self.query_one("#detail-left-log"))
        threading.Thread(target=self._fetch_detail, daemon=True).start()
        threading.Thread(target=self._fetch_assignees, daemon=True).start()
        self.set_interval(1, self._update_time_bar)

    def _log(self, msg: str) -> None:
        try:
            self.query_one("#detail-left-log", RichLog).write(msg)
        except Exception:
            pass

    # ── 详情 API ────────────────────────────────────────
    def _fetch_detail(self) -> None:
        try:
            url = f"https://heimdallr.onewo.com/api/datacenter/workOrder-etl/api/workOrder-etl/feign/getFmWorkOrderDetail/{self.etl_code}"
            logger.info(f"[详情] 请求 URL: {url}")
            resp = requests.get(url, headers=self.headers, verify=False, timeout=10)
            logger.info(f"[详情] HTTP {resp.status_code}, 响应长度={len(resp.text)}")
            if resp.status_code != 200:
                self.app.call_from_thread(lambda: self._show_detail(f"[red]HTTP {resp.status_code}[/red]"))
                return
            data = resp.json()
            if data.get("code") == 200 or data.get("msg") == "success":
                self._detail_data = data.get("data", {})
                text = self._format_detail(self._detail_data)
            else:
                text = f"[red]请求失败: {data.get('msg', '未知错误')}[/red]"
            self.app.call_from_thread(lambda: self._show_detail(text))
        except Exception as e:
            logger.error(f"[详情] 请求异常: {e}", exc_info=True)
            self.app.call_from_thread(lambda: self._show_detail(f"[red]请求异常: {e}[/red]"))

    def _format_detail(self, info: dict) -> str:
        feed_back = info.get("feedBackTime", "")
        deadline = None
        try:
            if feed_back:
                deadline = datetime.strptime(feed_back, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass
        remaining_str = "--:--:--"
        remaining_style = "green"
        if deadline:
            remaining_str = format_remaining(deadline)
            remaining_style = get_remaining_style(deadline)
        lines = [
            f"[bold]工单编号:[/bold]  {info.get('workorderNo', '')}",
            f"[bold]工单类型:[/bold]  {info.get('workorderTypeName', '')}    "
            f"[bold]来源:[/bold]  {info.get('sourceName', info.get('source', ''))}",
            f"[bold]所属项目:[/bold]  {info.get('projectName', '')}",
            f"[bold]地    址:[/bold]  {info.get('address', '')}",
            f"[bold]工单描述:[/bold]  {info.get('workorderDescription', '')}",
            "",
            f"[bold]接 单 人:[/bold]  {info.get('acceptName') or '未接单'}    "
            f"[bold]状  态:[/bold]  {info.get('workorderStatusName', '')}",
            "",
            f"[bold]创建时间:[/bold]  {info.get('createTime', '')}",
            f"[bold]超时时间:[/bold]  {feed_back}    "
            f"剩余: [{remaining_style}]{remaining_str}[/{remaining_style}]",
        ]
        return "\n".join(lines)

    def _show_detail(self, text: str) -> None:
        try:
            self.query_one("#detail-info-body", Static).update(text)
            self._log(f"[dim]{now_str()}[/dim]")
            self._log("[green]工单详情加载完成[/green]")
            self._log("")
            self._update_time_bar()
        except Exception as e:
            logger.error(f"[详情] 更新失败: {e}", exc_info=True)

    # ── 倒计时条 ────────────────────────────────────────
    def _update_time_bar(self) -> None:
        if not self._detail_data:
            return
        feed_back = self._detail_data.get("feedBackTime", "")
        try:
            deadline = datetime.strptime(feed_back, "%Y-%m-%d %H:%M:%S") if feed_back else None
        except (ValueError, TypeError):
            deadline = None
        if deadline:
            remaining = format_remaining(deadline)
            style = get_remaining_style(deadline)
            text = f"[{style}]超时倒计时: {remaining}[/{style}]"
        else:
            text = "[dim]超时倒计时: 未知[/dim]"
        try:
            self.query_one("#detail-time-bar", Static).update(text)
        except Exception:
            pass

    # ── 指派 API ────────────────────────────────────────
    def _fetch_assignees(self) -> None:
        try:
            url = "https://heimdallr.onewo.com/api/task/courier/admin/task/work-order/assignmentList"
            body = {
                "bodyForm": {
                    "projectCode": self.project_id,
                    "queryParam": "",
                    "workOrderNo": self.workorder_no,
                },
                "source": self.source,
            }
            logger.info(f"[详情指派] 请求 URL: {url}")
            logger.info(f"[详情指派] 请求体: {json.dumps(body, ensure_ascii=False)}")
            resp = requests.post(url, json=body, headers=self.headers, verify=False, timeout=10)
            logger.info(f"[详情指派] HTTP {resp.status_code}, 响应长度={len(resp.text)}")
            if resp.status_code != 200:
                self._log("[red]指派列表请求失败[/red]")
                return
            data = resp.json()
            code = data.get("code")
            msg = data.get("msg", "未知")
            is_ok = data.get("isOk")
            logger.info(f"[详情指派] 响应解析: code={code}, msg={msg}, isOk={is_ok}")
            if code in (200, "200") or msg == "success" or is_ok:
                # 处理两种响应结构：{code:"200", data:{records:[]}} 或 {isOk:true, data:[]}
                records = data.get("data", {})
                if isinstance(records, dict):
                    records = records.get("records", [])
                if records:
                    self._assignees = records
                    self.app.call_from_thread(self._populate_assign_table, records)
                    self._log(f"[green]已加载 {len(records)} 位可指派人员[/green]")
                else:
                    self._log("[yellow]该工单无可指派人员[/yellow]")
            else:
                self._log(f"[red]获取指派列表失败: {msg}[/red]")
        except Exception as e:
            logger.error(f"[详情指派] 异常: {e}")
            self._log(f"[red]指派列表异常: {e}[/red]")

    def _populate_assign_table(self, records: list = None) -> None:
        """填充指派表格，records=None 时用 self._assignees（用于搜索后重绘）"""
        data = records if records is not None else self._assignees
        assign_table = self.query_one("#detail-left-assign", DataTable)
        assign_table.clear()
        for r in data:
            name = r.get("userName", r.get("dealUserName", r.get("realName", "未知")))
            role = r.get("roleName", "")
            mobile = r.get("mobile", "")
            assign_table.add_row(name, role, mobile)

    # ── 指派模式切换 ────────────────────────────────────
    def action_toggle_assign(self) -> None:
        header = self.query_one("#detail-left-header", Static)
        search_input = self.query_one("#detail-left-search", Input)
        left_panel = self.query_one("#detail-left")
        log = self.query_one("#detail-left-log", RichLog)
        assign_table = self.query_one("#detail-left-assign", DataTable)

        if self._assign_mode:
            # 切回日志模式（缩窄左侧面板）
            left_panel.styles.width = 36
            header.update("详情日志")
            search_input.styles.display = "none"
            log.styles.display = "block"
            assign_table.styles.display = "none"
            self._assign_mode = False
            self.set_focus(log)
        else:
            # 切换到指派模式（展宽左侧面板）
            if not self._assignees:
                self._log("[yellow]无可指派人员或尚未加载[/yellow]")
                return
            left_panel.styles.width = 50
            header.update(f"→ 可指派人员（{len(self._assignees)} 人）")
            search_input.value = ""
            search_input.styles.display = "block"
            log.styles.display = "none"
            assign_table.styles.display = "block"
            self._populate_assign_table()
            self._assign_mode = True
            self.set_focus(search_input)

    # ── 实时搜索 ────────────────────────────────────────
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.control.id != "detail-left-search":
            return
        keyword = event.value.strip()
        if not keyword:
            self._populate_assign_table(self._assignees)
            return
        filtered = [r for r in self._assignees
                    if keyword.lower() in (r.get("userName", r.get("dealUserName", r.get("realName", "")))).lower()
                    or keyword.lower() in r.get("roleName", "").lower()
                    or keyword in r.get("mobile", "")]
        self._populate_assign_table(filtered)

    # ── 指派表格选中事件 ──────────────────────────────────
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id != "detail-left-assign":
            return
        try:
            coord = event.cursor_coordinate
            if coord is None:
                return
            row = event.control.get_row_at(coord[0])
            if not row or not row[0]:
                return
            name = str(row[0]).strip()
            # 根据名字从原始列表匹配完整记录（含 userId 等隐藏字段）
            matched = next((r for r in self._assignees
                           if (r.get("userName", r.get("dealUserName", r.get("realName", ""))) == name)), None)
            if matched:
                self._selected_assignee = matched
                role = matched.get("roleName", "")
                mobile = matched.get("mobile", "")
                self._log(f"[green]已选: {name} ({role})[/green]")
                self.notify(f"已选择: {name} | {role} | {mobile}", severity="information")
            else:
                self._log(f"[green]已选: {name}[/green]")
                self._selected_assignee = {"userName": name}
        except Exception as e:
            self.notify(f"选择异常: {e}", severity="error")

    def action_close(self) -> None:
        self.dismiss()


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
        self._notified_od_ids: set = set()
        self._notified_pm_ids: set = set()
        self._sound_loaded = False
        self._tkpm = None
        self._tkod = None
        self._pending_logs: deque = deque()
        self._api_headers: dict = {}
        self._api_project_id: str = "52010017"
        self._api_source: str = "02"
        self._selected_ticket: dict | None = None  # 当前按Enter选中的工单
        self._od_row_keys: list = []  # OD表格行key（用于原地更新剩余时间）
        self._pm_row_keys: list = []  # PM表格行key

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

        # 加载 API 配置
        try:
            cfg = load_api_config()
            self._api_headers = cfg["headers"]
            self._api_project_id = cfg["project_id"]
            self._api_source = cfg["source"]
        except Exception:
            self._log("[bold red]API配置加载失败[/bold red]")

        # 初始化音频
        try:
            sound_path = get_resource_path("res/sound.mp3")
            pygame.mixer.init()
            pygame.mixer.music.load(sound_path)
            self._sound_loaded = True
        except Exception:
            self._sound_loaded = False

        # 设置表格列 + 行光标支持
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

        # 定期冲刷日志（1秒间隔），表格仅在有新数据时才刷新
        self.set_interval(1, self._flush_logs)
        # 每秒更新剩余时间（原地更新，不影响光标位置）
        self.set_interval(1, self._update_time_column)

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
            od_items = self._latest_od_data.get("data", [])
            od_count = len(od_items)
            msg = self._tkod.content.get("msg", "unknown") if self._tkod.content else "unknown"
            logger.info(f"[OD查询] msg={msg}, 超时工单数={od_count}")
            new_ids = {i['workorderNo'] for i in od_items} - self._notified_od_ids
            self._log(f"[dim]{now_str()}[/dim]")
            if od_count > 0:
                self._log(f"[bold red]发现 {od_count} 个即将超时的临时性工单[/bold red]")
                self._play_sound()
                if new_ids:
                    self._show_popup(f"你有 {len(new_ids)} 条临时性工单即将超时，请及时处理！")
                    self._notified_od_ids.update(new_ids)
            else:
                self._log("[dim]暂无即将超时的临时性工单[/dim]")
            self._log("")
            self.call_from_thread(self._refresh_tables)
        except Exception as e:
            logger.error(f"[OD查询] 异常: {e}")
            self._log(f"[bold red]OD查询异常: {e}[/bold red]")

    def _run_pm_query(self):
        """执行一次PM查询并输出结果日志（仅剩余<30分钟时告警）"""
        try:
            self._tkpm.query()
            while self._tkpm.content is None:
                time.sleep(1)
            with self._lock:
                self._latest_pm_data = self._tkpm.query_timeout()
            pm_items = self._latest_pm_data.get("data", [])
            msg = self._tkpm.content.get("msg", "unknown") if self._tkpm.content else "unknown"
            logger.info(f"[PM查询] msg={msg}, 总工单数={len(pm_items)}")
            # 仅统计剩余时间 < 30 分钟的作为"即将超时"
            now = datetime.now()
            critical = [i for i in pm_items if (i['deadline'] - now).total_seconds() < 1800]
            new_critical_ids = {i['workorderNo'] for i in critical} - self._notified_pm_ids
            self._log(f"[dim]{now_str()}[/dim]")
            if critical:
                self._log(f"[bold yellow]发现 {len(critical)} 个即将超时的周期性工单（剩余 < 30 分钟）[/bold yellow]")
                self._play_sound()
                if new_critical_ids:
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
        """新数据到达时刷新表格"""
        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data

        # 更新OD表格
        od_table = self.query_one("#od-table")
        od_table.clear()
        self._od_row_keys.clear()
        if od_data is not None:
            od_count = int(od_data.get("num", 0))
            od_items = od_data.get("data", [])
            if od_count > 0:
                for item in od_items:
                    remaining_text = format_remaining(item["deadline"])
                    remaining_style = get_remaining_style(item["deadline"])
                    row = od_table.add_row(
                        item["workorderNo"],
                        truncate(item.get("workorderDescription", ""), 60),
                        ralign(item.get("workorderStatusName", ""), 10),
                        Text(ralign(remaining_text, 10), style=remaining_style),
                    )
                    self._od_row_keys.append(row)
            else:
                od_table.add_row("", "暂无即将超时的临时性工单", "", "")
        else:
            od_table.add_row("", "等待首次查询...", "", "")

        # 更新PM表格
        pm_table = self.query_one("#pm-table")
        pm_table.clear()
        self._pm_row_keys.clear()
        if pm_data is not None:
            pm_count = int(pm_data.get("num", 0))
            pm_items = pm_data.get("data", [])
            if pm_count > 0:
                for item in pm_items:
                    remaining_text = format_remaining(item["deadline"])
                    remaining_style = get_remaining_style(item["deadline"])
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

        # 更新标题栏
        self._update_headers()

    def _update_time_column(self):
        """每秒更新剩余时间列（原地更新单元格，不移动光标）"""
        try:
            with self._lock:
                od_data = self._latest_od_data
                pm_data = self._latest_pm_data

            od_table = self.query_one("#od-table")
            if od_data and int(od_data.get("num", 0)) > 0:
                items = od_data.get("data", [])
                for i, item in enumerate(items):
                    if i < len(self._od_row_keys):
                        remaining_text = format_remaining(item["deadline"])
                        remaining_style = get_remaining_style(item["deadline"])
                        od_table.update_cell(
                            self._od_row_keys[i], "time",
                            Text(ralign(remaining_text, 10), style=remaining_style),
                        )

            pm_table = self.query_one("#pm-table")
            if pm_data and int(pm_data.get("num", 0)) > 0:
                items = pm_data.get("data", [])
                for i, item in enumerate(items):
                    if i < len(self._pm_row_keys):
                        remaining_text = format_remaining(item["deadline"])
                        remaining_style = get_remaining_style(item["deadline"])
                        pm_table.update_cell(
                            self._pm_row_keys[i], "time",
                            Text(ralign(remaining_text, 10), style=remaining_style),
                        )

            # 同步更新标题栏中的超时状态颜色
            self._update_headers()
        except Exception:
            pass

    def _update_headers(self):
        """更新面板标题中的状态指示"""
        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data

        od_count = int(od_data.get("num", 0)) if od_data else -1
        pm_count = int(pm_data.get("num", 0)) if pm_data else -1

        # PM临界数量（剩余 < 30 分钟）
        now = datetime.now()
        pm_critical = 0
        if pm_data:
            for item in pm_data.get("data", []):
                if (item['deadline'] - now).total_seconds() < 1800:
                    pm_critical += 1

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

        # 日志告警标志：OD有超时 或 PM有临界（< 30分钟）
        has_alert = (od_count > 0) or (pm_critical > 0)
        log_header.update(f"查询日志  {'● 告警' if has_alert else '● 正常'}")

    # ── 音频 ────────────────────────────────────────────────
    def _play_sound(self):
        """播放提醒音效"""
        if self._sound_loaded:
            try:
                pygame.mixer.music.play()
            except Exception:
                pass

    def _show_popup(self, msg: str):
        """Windows 弹窗提醒（后台线程安全）"""
        try:
            ctypes.windll.user32.MessageBoxW(0, msg, "工单超时提醒", 0)
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
                        self.call_from_thread(self.exit)
                        return
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
        self.call_from_thread(self._refresh_tables)

    # ── 工单详情 & 指派 ────────────────────────────────────
    def _get_selected_ticket(self) -> dict | None:
        """获取当前光标所在行的工单数据，仅返回有效工单"""
        # 占位提示文字
        _placeholders = {"暂无即将超时的临时性工单", "暂无即将超时的周期性工单",
                         "等待首次查询...", "暂无数据", ""}
        for table_id in ("#od-table", "#pm-table"):
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
            # 过滤占位提示文字
            if wo_no in _placeholders or len(wo_no) < 5:
                continue
            # 从缓存数据找完整信息
            for data in (self._latest_od_data, self._latest_pm_data):
                if data:
                    for item in data.get("data", []):
                        if item["workorderNo"] == wo_no:
                            return item
            return {"workorderNo": wo_no}
        return None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter → 查看工单详情"""
        try:
            if event.control.id not in ("od-table", "pm-table"):
                return
            ticket = self._get_selected_ticket()
            if not ticket:
                self.notify("当前行不是有效工单", severity="warning")
                return
            self._selected_ticket = ticket
            # 打开工单详情弹窗（内置指派功能）
            self.push_screen(DetailScreen(
                workorder_no=ticket["workorderNo"],
                headers=self._api_headers,
                etl_code=ticket.get("etlCode", ""),
                source=self._api_source,
                project_id=self._api_project_id,
            ))
        except Exception as e:
            self.notify(f"操作异常: {e}", severity="error")
