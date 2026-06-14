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
from lib import api as lib_api

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


def get_remaining_style(deadline: datetime, ticket_type: str = "PM") -> str:
    """根据剩余时间返回颜色样式"""
    remaining = deadline - datetime.now()
    total_minutes = remaining.total_seconds() / 60
    if total_minutes < 0:
        return "bold red"
    if ticket_type == "OD":
        if total_minutes < 5:
            return "red"
        elif total_minutes < 10:
            return "yellow"
        return "green"
    else:  # PM
        if total_minutes < 10:
            return "red"
        elif total_minutes < 30:
            return "yellow"
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
    """从配置文件加载 API 请求头（过滤掉固定字段）"""
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
    return headers


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
        height: auto;
        max-height: 12;
        border: none;
        overflow-y: auto;
        overflow-x: hidden;
    }

    #detail-info-body > .datatable--header {
        display: none;
    }

    #detail-info-body DataTable {
        width: 100%;
    }

    #detail-description {
        height: auto;
        max-height: 8;
        border: none;
        padding: 0 1;
        overflow-y: auto;
        overflow-x: hidden;
        margin-top: 1;
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
        Binding("r", "refresh_detail", "刷新", key_display="R"),
        Binding("q", "close", "返回", key_display="Q"),
        Binding("escape", "close", "返回"),
    ]

    def __init__(self, workorder_no: str, headers: dict, etl_code: str = "",
                 source: str = "", project_id: str = "",
                 wo_type: str = "PM") -> None:
        super().__init__()
        self.workorder_no = workorder_no
        self.headers = headers
        self.etl_code = etl_code
        self.source = source
        self.project_id = project_id
        self._wo_type = wo_type
        self._detail_data: dict | None = None
        self._deadline: datetime | None = None
        self._assignees: list = []
        self._selected_assignee: dict | None = None
        self._pending_assignee: dict | None = None
        self._confirm_mode = False
        self._assign_mode = False
        self._description_text = ""

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
                    yield DataTable(id="detail-info-body")
                    yield Static(id="detail-description")
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
        # 底部倒计时条改为静态装饰（颜色已移入表格）
        self.query_one("#detail-time-bar", Static).update("")
        # 详情表格：4列（左标签/左值/右标签/右值）无边框无光标
        detail_table = self.query_one("#detail-info-body", DataTable)
        detail_table.wrap = True
        detail_table.row_height = 1  # 描述已移出表格，不再需要撑高行
        detail_table.add_column("", key="ll", width=10)
        detail_table.add_column("", key="lv", width=30)
        detail_table.add_column("", key="rl", width=10)
        detail_table.add_column("", key="rv", width=30)
        detail_table.show_header = False
        detail_table.cursor_type = None
        detail_table.zebra_stripes = False
        detail_table.add_row("", "正在加载...", "", "")
        self._time_row_key = None  # 剩余时间行的key，用于每秒更新

        # 初始焦点给左侧日志，确保键盘绑定生效
        self.set_focus(self.query_one("#detail-left-log"))
        threading.Thread(target=self._fetch_detail, daemon=True).start()
        threading.Thread(target=self._fetch_assignees, daemon=True).start()
        self.set_interval(1, self._update_remaining_cell)

    def _log(self, msg: str) -> None:
        try:
            self.query_one("#detail-left-log", RichLog).write(msg)
        except Exception:
            pass

    # ── 详情 API ────────────────────────────────────────
    def _fetch_detail(self) -> None:
        try:
            url = lib_api.DETAIL_URL_TPL.format(etl_code=self.etl_code)
            resp = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if resp.status_code != 200:
                self.app.call_from_thread(
                    lambda: self._show_detail([("", f"[red]HTTP {resp.status_code}[/red]", "", "")])
                )
                return
            data = resp.json()
            if data.get("code") == 200 or data.get("msg") == "success":
                self._detail_data = data.get("data", {})
                rows = self._format_detail(self._detail_data)
            else:
                rows = [("", f"[red]{data.get('msg', '未知错误')}[/red]", "", "")]
            self.app.call_from_thread(lambda: self._show_detail(rows))
        except Exception as e:
            logger.error(f"[详情] 请求异常: {e}", exc_info=True)
            self.app.call_from_thread(lambda: self._show_detail([("", f"[red]请求异常: {e}[/red]", "", "")]))

    @staticmethod
    def _wrap_text(text: str, max_width: int = 30) -> str:
        """按视觉宽度裁切文本（中文=2，英文=1），超出自动换行"""
        lines = []
        cur = ""
        cur_w = 0
        for ch in text:
            w = 1 if ch.isascii() else 2
            if ch == '\n':
                lines.append(cur)
                cur = ""
                cur_w = 0
                continue
            if cur_w + w > max_width:
                lines.append(cur)
                cur = ch
                cur_w = w
            else:
                cur += ch
                cur_w += w
        if cur:
            lines.append(cur)
        return "\n".join(lines)

    def _format_detail(self, info: dict) -> list[tuple]:
        # 计算倒计时截止时间
        self._deadline = None
        timeout_label = "超时时间"
        if self._wo_type == "OD":
            create_time_str = info.get("createTime", "")
            if create_time_str:
                try:
                    create_time = datetime.strptime(create_time_str, "%Y-%m-%d %H:%M:%S")
                    self._deadline = create_time + timedelta(minutes=20)
                except (ValueError, TypeError):
                    pass
        else:
            feed_back = info.get("feedBackTime", "")
            timeout_label = "超时时间"
            if feed_back:
                try:
                    self._deadline = datetime.strptime(feed_back, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass

        if self._deadline:
            timeout_val = self._deadline.strftime("%Y-%m-%d %H:%M:%S")
            remaining_text = format_remaining(self._deadline)
            remaining_style = get_remaining_style(self._deadline, self._wo_type)
            remaining_cell = Text(remaining_text, style=remaining_style)
        else:
            timeout_val = "--:--:--"
            remaining_cell = ""

        rows = [
            ("工单编号：", info.get("workorderNo", ""), "", ""),
            ("工单类型：", info.get("workorderTypeName", ""), "", ""),
            ("所属项目：", info.get("projectName", ""), "地址：", info.get("address", "")),
            ("", "", "", ""),  # 工单描述移走后留空行
            ("报单人：", info.get("createName", ""), "电话：", info.get("createMobile", "")),
            ("接单人：", info.get("acceptName") or "未接单", "状态：", info.get("workorderStatusName", "")),
            ("创建时间：", info.get("createTime", ""), f"{timeout_label}：", timeout_val),
            ("", "", "剩余时间：", remaining_cell),
        ]
        # 工单描述单独存储，从表格中移除显示
        self._description_text = self._wrap_text(info.get("workorderDescription", ""), max_width=44)
        return rows

    def _show_detail(self, rows: list[tuple]) -> None:
        try:
            table = self.query_one("#detail-info-body", DataTable)
            table.clear()
            for i, (ll, lv, rl, rv) in enumerate(rows):
                key = table.add_row(ll, lv, rl, rv)
                # 剩余时间行现在是最后一行
                if i == len(rows) - 1:
                    self._time_row_key = key
            # 更新工单描述（表格下方单独显示）
            desc_widget = self.query_one("#detail-description", Static)
            if self._description_text:
                desc_widget.update(f"[bold]工单描述：[/bold]\n{self._description_text}")
            else:
                desc_widget.update("")
            self._log(f"[dim]{now_str()}[/dim]")
            self._log("[green]工单详情加载完成[/green]")
            self._log("")
            self._update_remaining_cell()
        except Exception as e:
            logger.error(f"[详情] 更新失败: {e}", exc_info=True)

    # ── 剩余时间单元格每秒更新 ──────────────────────────
    def _update_remaining_cell(self) -> None:
        """更新表格中剩余时间格的颜色和数值（与主表格同渲染路径）"""
        if not self._deadline or not self._time_row_key:
            return
        remaining = format_remaining(self._deadline)
        style = get_remaining_style(self._deadline, self._wo_type)
        try:
            table = self.query_one("#detail-info-body", DataTable)
            table.update_cell(self._time_row_key, "rv", Text(remaining, style=style))
        except Exception:
            pass

    # ── 指派 API ────────────────────────────────────────
    def _fetch_assignees(self) -> None:
        try:
            url = lib_api.ASSIGNEE_LIST_URL
            body = lib_api.build_assignee_list_body(
                project_code=self.project_id,
                workorder_no=self.workorder_no,
                source=self.source,
            )
            resp = requests.post(url, json=body, headers=self.headers, verify=False, timeout=10)
            if resp.status_code != 200:
                self._log("[red]指派列表请求失败[/red]")
                return
            data = resp.json()
            code = data.get("code")
            msg = data.get("msg", "未知")
            is_ok = data.get("isOk")
            if code in (200, "200") or msg == "success" or is_ok:
                records = data.get("data", {})
                if isinstance(records, dict):
                    records = records.get("records", [])
                if records:
                    self._assignees = records
                    self.app.call_from_thread(self._populate_assign_table, records)
                else:
                    self._log("[yellow]该工单无可指派人员[/yellow]")
            else:
                self._log(f"[red]获取指派列表失败: {msg}[/red]")
        except Exception as e:
            logger.error(f"[详情指派] 异常: {e}", exc_info=True)
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
            self._confirm_mode = False
            self._pending_assignee = None
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
        # 已处于确认模式 → 鼠标点击等同于按 Y 确认
        if self._confirm_mode:
            self._execute_assign()
            return
        try:
            table = event.control
            coord = table.cursor_coordinate
            if coord is None:
                return
            row_index = coord[0]
            row = table.get_row_at(row_index)
            if not row or not row[0]:
                return
            name = str(row[0]).strip()
            # 根据名字从原始列表匹配完整记录（含 userId 等隐藏字段）
            matched = next((r for r in self._assignees
                           if (r.get("userName", r.get("dealUserName", r.get("realName", ""))) == name)), None)
            if matched:
                self._pending_assignee = matched
                self._confirm_mode = True
                mobile = matched.get("mobile", "")
                self._log(f"[yellow]确认将该工单指派给 {name}（{mobile}）？[/yellow]")
                self.notify(f"确认指派给 {name}（{mobile}）？", severity="warning")
                # 焦点移到日志区域，防止 Enter 再次触发行选中
                self.set_focus(self.query_one("#detail-left-log"))
            else:
                self._log(f"[yellow]未找到人员完整信息，请重新选择[/yellow]")
        except Exception as e:
            self.notify(f"选择异常: {e}", severity="error")

    def action_close(self) -> None:
        if self._assign_mode:
            if self._confirm_mode:
                self._cancel_assign()
            else:
                # 指派模式下 ESC/Q → 返回日志视图
                self.action_toggle_assign()
        else:
            self.dismiss()

    # ── 确认/取消指派 ────────────────────────────────────
    def on_key(self, event) -> None:
        """拦截确认模式下的按键"""
        if self._assign_mode and self._confirm_mode:
            if event.key in ("enter", "y", "Y"):
                event.stop()
                self._execute_assign()
                return
            if event.key in ("escape", "q", "Q"):
                event.stop()
                self._cancel_assign()
                return

    def _cancel_assign(self) -> None:
        self._confirm_mode = False
        self._pending_assignee = None
        self._log("[dim]已取消指派[/dim]")
        self.set_focus(self.query_one("#detail-left-search"))

    def _execute_assign(self) -> None:
        """实际执行指派 API 请求"""
        if not self._pending_assignee:
            return
        assignee = self._pending_assignee
        name = assignee.get("userName", assignee.get("dealUserName", assignee.get("realName", "")))
        mobile = assignee.get("mobile", "")
        user_id = assignee.get("userId", assignee.get("dealUserId", ""))

        self._confirm_mode = False
        self._pending_assignee = None

        body = lib_api.build_assign_body(
            deal_user_id=user_id,
            deal_user_mobile=mobile,
            deal_user_name=name,
            project_code=self.project_id,
            workorder_no=self.workorder_no,
            wo_type=self._wo_type,
            source=self.source,
        )

        self._log(f"[cyan]正在指派给 {name}（{mobile}）...[/cyan]")

        def do_assign() -> None:
            try:
                resp = requests.post(
                    lib_api.ASSIGN_URL, json=body, headers=self.headers, verify=False, timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("isOk") or str(data.get("code", "")) in ("200",):
                        self.app.call_from_thread(lambda: self._on_assign_success(name))
                    else:
                        msg = data.get("msg", "未知错误")
                        self.app.call_from_thread(lambda: self._on_assign_fail(msg))
                else:
                    self.app.call_from_thread(lambda: self._on_assign_fail(f"HTTP {resp.status_code}"))
            except Exception as e:
                logger.error(f"[指派] 异常: {e}", exc_info=True)
                self.app.call_from_thread(lambda: self._on_assign_fail(str(e)))

        threading.Thread(target=do_assign, daemon=True).start()

    def _refresh_detail(self) -> None:
        """刷新工单详情和指派列表"""
        threading.Thread(target=self._fetch_detail, daemon=True).start()
        threading.Thread(target=self._fetch_assignees, daemon=True).start()

    def action_refresh_detail(self) -> None:
        """R键刷新"""
        self._log("[cyan]正在刷新...[/cyan]")
        self._refresh_detail()

    def _on_assign_success(self, name: str) -> None:
        self._log(f"[bold green]指派成功！已分配给 {name}[/bold green]")
        self.notify(f"指派成功！已分配给 {name}", severity="information")
        # 先切回详情日志视图
        self.action_toggle_assign()
        # 延迟5秒后刷新详情（等价于按 R 键）
        threading.Timer(5, lambda: self.app.call_from_thread(self.action_refresh_detail)).start()

    def _on_assign_fail(self, msg: str) -> None:
        self._log(f"[bold red]指派失败: {msg}，请稍后重试[/bold red]")
        self.notify(f"指派失败: {msg}", severity="error")


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
            self._api_headers = cfg
            self._api_project_id = lib_api.DEFAULT_PROJECT_ID
            self._api_source = lib_api.DEFAULT_SOURCE
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
        """先启动周期循环线程（互不依赖），再执行首次查询"""
        threading.Thread(target=self._pm_query_loop, daemon=True).start()
        threading.Thread(target=self._od_query_loop, daemon=True).start()
        # 首次查询，与周期循环互不阻塞
        self._run_od_query()
        self._run_pm_query()

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

    def _run_od_query(self, suppress_notifications: bool = False):
        """执行一次OD查询并输出结果日志
        suppress_notifications=True 时抑制弹窗和语音提醒（用于手动刷新）
        """
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
                if not suppress_notifications:
                    self._play_sound()
                if new_ids and not suppress_notifications:
                    self._show_popup(f"你有 {len(new_ids)} 条临时性工单即将超时，请及时处理！")
                    self._notified_od_ids.update(new_ids)
            else:
                self._log("[dim]暂无即将超时的临时性工单[/dim]")
            self._log("")
            self.call_from_thread(self._refresh_tables)
        except Exception as e:
            logger.error(f"[OD查询] 异常: {e}")
            self._log(f"[bold red]OD查询异常: {e}[/bold red]")

    def _run_pm_query(self, suppress_notifications: bool = False):
        """执行一次PM查询并输出结果日志（仅剩余<30分钟时告警）
        suppress_notifications=True 时抑制弹窗和语音提醒（用于手动刷新）
        """
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
        """新数据到达时刷新表格（重建列以重置列宽）"""
        with self._lock:
            od_data = self._latest_od_data
            pm_data = self._latest_pm_data

        # 重建OD表格（清空所有列和行，重新定义列宽）
        od_table = self.query_one("#od-table")
        od_table.clear(columns=True)
        od_table.add_column("工单编号", key="id", width=16)
        od_table.add_column("任务描述", key="desc")
        od_table.add_column("状态", key="status", width=8)
        od_table.add_column("剩余时间", key="time", width=10)
        od_table.cursor_type = "row"
        self._od_row_keys.clear()
        if od_data is not None:
            od_count = int(od_data.get("num", 0))
            od_items = od_data.get("data", [])
            if od_count > 0:
                for item in od_items:
                    remaining_text = format_remaining(item["deadline"])
                    remaining_style = get_remaining_style(item["deadline"], "OD")
                    row = od_table.add_row(
                        item["workorderNo"],
                        truncate(item.get("workorderDescription", ""), 60),
                        item.get("workorderStatusName", ""),
                        Text(remaining_text, style=remaining_style),
                    )
                    self._od_row_keys.append(row)
            else:
                od_table.add_row("", "暂无即将超时的临时性工单", "", "")
        else:
            od_table.add_row("", "等待首次查询...", "", "")

        # 重建PM表格
        pm_table = self.query_one("#pm-table")
        pm_table.clear(columns=True)
        pm_table.add_column("工单编号", key="id", width=16)
        pm_table.add_column("任务描述", key="desc")
        pm_table.add_column("处理人", key="handler", width=8)
        pm_table.add_column("状态", key="status", width=8)
        pm_table.add_column("剩余时间", key="time", width=10)
        pm_table.cursor_type = "row"
        self._pm_row_keys.clear()
        if pm_data is not None:
            pm_count = int(pm_data.get("num", 0))
            pm_items = pm_data.get("data", [])
            if pm_count > 0:
                for item in pm_items:
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
                        remaining_style = get_remaining_style(item["deadline"], "OD")
                        od_table.update_cell(
                            self._od_row_keys[i], "time",
                            Text(remaining_text, style=remaining_style),
                        )

            pm_table = self.query_one("#pm-table")
            if pm_data and int(pm_data.get("num", 0)) > 0:
                items = pm_data.get("data", [])
                for i, item in enumerate(items):
                    if i < len(self._pm_row_keys):
                        remaining_text = format_remaining(item["deadline"])
                        remaining_style = get_remaining_style(item["deadline"], "PM")
                        pm_table.update_cell(
                            self._pm_row_keys[i], "time",
                            Text(remaining_text, style=remaining_style),
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
        """Windows 弹窗提醒（独立线程，不阻塞调用方）"""
        try:
            threading.Thread(
                target=lambda: ctypes.windll.user32.MessageBoxW(0, msg, "工单超时提醒", 0),
                daemon=True,
            ).start()
        except Exception:
            pass

    # ── 定时关机 ────────────────────────────────────────────
    def _shutdown_watcher(self):
        """定期检查互联网时间(1分钟间隔)，距离目标2分钟内启动本地倒计时精确关闭"""
        if self.end_time is None:
            return
        end_hour, end_minute = self.end_time
        tz_shanghai = timezone(timedelta(hours=8))

        def _calc_remaining(now_shanghai):
            """计算当前到目标时间的剩余秒数，目标已过则视为次日"""
            target = now_shanghai.replace(
                hour=end_hour, minute=end_minute, second=0, microsecond=0
            )
            if target <= now_shanghai:
                target += timedelta(days=1)
            return (target - now_shanghai).total_seconds()

        while True:
            try:
                now = fetch_internet_time()
                if now is not None:
                    now_shanghai = now.astimezone(tz_shanghai)
                    remaining = _calc_remaining(now_shanghai)

                    if remaining <= 120:
                        self._log(
                            f"[yellow]距离关闭时间 {end_hour:02d}:{end_minute:02d} "
                            f"仅剩 {int(remaining)} 秒，启动本地倒计时精确关闭...[/yellow]"
                        )
                        threading.Thread(
                            target=self._local_countdown_exit,
                            args=(remaining, end_hour, end_minute),
                            daemon=True,
                        ).start()
                        return
                time.sleep(60)
            except Exception:
                time.sleep(60)

    def _local_countdown_exit(self, seconds: float, end_hour: int, end_minute: int):
        """本地精确定时休眠，到达后退出程序"""
        time.sleep(max(0, seconds))
        self._log(
            f"[bold red]已到达设定结束时间 {end_hour:02d}:{end_minute:02d}，程序退出中...[/bold red]"
        )
        self.call_from_thread(self.exit)

    # ── 动作 ────────────────────────────────────────────────
    def action_force_refresh(self):
        """强制刷新：串行执行一次OD + PM查询，日志按顺序输出"""
        t = threading.Thread(target=self._force_refresh_all, daemon=True)
        t.start()

    def _force_refresh_all(self):
        """串行执行OD和PM强制刷新（抑制弹窗和语音），确保日志顺序"""
        self._run_od_query(suppress_notifications=True)
        self._run_pm_query(suppress_notifications=True)

        self._log("")
        self.call_from_thread(self._refresh_tables)

    # ── 工单详情 & 指派 ────────────────────────────────────
    def _on_detail_dismissed(self) -> None:
        """从详情页返回时延迟5秒自动刷新主页面"""
        threading.Timer(5, self.action_force_refresh).start()

    def _get_selected_ticket(self, table_id: str) -> dict | None:
        """获取指定表格中光标所在行的工单数据"""
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
        # 从缓存数据找完整信息
        data_source = self._latest_od_data if table_id == "#od-table" else self._latest_pm_data
        if data_source:
            for item in data_source.get("data", []):
                if item["workorderNo"] == wo_no:
                    return item
        return {"workorderNo": wo_no}

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter → 查看工单详情"""
        try:
            table_id = event.control.id
            if table_id not in ("od-table", "pm-table"):
                return
            ticket = self._get_selected_ticket(f"#{table_id}")
            if not ticket:
                self.notify("当前行不是有效工单", severity="warning")
                return
            self._selected_ticket = ticket
            # 打开工单详情弹窗（内置指派功能），关闭后自动刷新主页面
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
