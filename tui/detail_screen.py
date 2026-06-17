"""工单详情界面（带指派功能）"""

import logging
import threading
import requests
from datetime import datetime, timedelta
from threading import Event

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, DataTable, RichLog, Input
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from rich.text import Text

from lib import api as lib_api
from tui.common import format_remaining, get_remaining_style, now_str

logger = logging.getLogger("ticket_timeout")


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

    #detail-loading {
        height: 1;
        padding: 0 1;
        background: $boost;
        text-style: italic;
        display: none;
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
        self._detail_loaded = Event()
        self._assignees_loaded = Event()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="detail-container"):
            with Vertical(id="detail-left"):
                yield Static("详情日志", id="detail-left-header")
                yield Input(placeholder="搜索姓名...", id="detail-left-search")
                yield RichLog(id="detail-left-log", highlight=True, markup=True, wrap=True, max_lines=1000)
                yield DataTable(id="detail-left-assign")
                yield Static(id="detail-loading")
            with Vertical(id="detail-right"):
                with Vertical(id="detail-info"):
                    yield Static("════ 工单详情 ════", id="detail-info-header")
                    yield DataTable(id="detail-info-body")
                    yield Static(id="detail-description")
                yield Static(id="detail-time-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._log("[dim]加载工单详情...[/dim]")
        self.query_one("#detail-left-search", Input).styles.display = "none"
        assign_table = self.query_one("#detail-left-assign")
        assign_table.add_column("姓名", key="name", width=8)
        assign_table.add_column("岗位", key="role", width=16)
        assign_table.add_column("电话", key="mobile", width=13)
        assign_table.cursor_type = "row"
        assign_table.styles.display = "none"
        self.query_one("#detail-time-bar", Static).update("")
        self.query_one("#detail-loading", Static).update("正在加载工单详情和可指派人员...")
        self.query_one("#detail-loading", Static).styles.display = "block"
        detail_table = self.query_one("#detail-info-body", DataTable)
        detail_table.wrap = True
        detail_table.row_height = 1
        detail_table.add_column("", key="ll", width=10)
        detail_table.add_column("", key="lv", width=30)
        detail_table.add_column("", key="rl", width=10)
        detail_table.add_column("", key="rv", width=30)
        detail_table.show_header = False
        detail_table.cursor_type = None
        detail_table.zebra_stripes = False
        detail_table.add_row("", "正在加载...", "", "")
        self._time_row_key = None
        self.set_focus(self.query_one("#detail-left-log"))
        threading.Thread(target=self._fetch_detail, daemon=True).start()
        threading.Thread(target=self._fetch_assignees, daemon=True).start()
        self.set_interval(1, self._update_remaining_cell)

    def _log(self, msg: str) -> None:
        try:
            self.query_one("#detail-left-log", RichLog).write(msg)
        except Exception:
            pass

    def _update_loading_status(self) -> None:
        """根据加载完成情况更新加载指示器"""
        try:
            widget = self.query_one("#detail-loading", Static)
            detail_done = self._detail_loaded.is_set()
            assign_done = self._assignees_loaded.is_set()
            if not detail_done and not assign_done:
                widget.update("正在加载工单详情和可指派人员...")
                widget.styles.display = "block"
            elif not detail_done:
                widget.update("正在加载工单详情...")
                widget.styles.display = "block"
            elif not assign_done:
                widget.update("正在加载可指派人员...")
                widget.styles.display = "block"
            else:
                widget.styles.display = "none"
        except Exception:
            pass

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
        finally:
            self._detail_loaded.set()
            self.app.call_from_thread(self._update_loading_status)

    @staticmethod
    def _wrap_text(text: str, max_width: int = 30) -> str:
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
            ("", "", "", ""),
            ("报单人：", info.get("createName", ""), "电话：", info.get("createMobile", "")),
            ("接单人：", info.get("acceptName") or "未接单", "状态：", info.get("workorderStatusName", "")),
            ("创建时间：", info.get("createTime", ""), f"{timeout_label}：", timeout_val),
            ("", "", "剩余时间：", remaining_cell),
        ]
        self._description_text = self._wrap_text(info.get("workorderDescription", ""), max_width=44)
        return rows

    def _show_detail(self, rows: list[tuple]) -> None:
        try:
            table = self.query_one("#detail-info-body", DataTable)
            table.clear()
            for i, (ll, lv, rl, rv) in enumerate(rows):
                key = table.add_row(ll, lv, rl, rv)
                if i == len(rows) - 1:
                    self._time_row_key = key
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

    def _update_remaining_cell(self) -> None:
        if not self._deadline or not self._time_row_key:
            return
        remaining = format_remaining(self._deadline)
        style = get_remaining_style(self._deadline, self._wo_type)
        try:
            table = self.query_one("#detail-info-body", DataTable)
            table.update_cell(self._time_row_key, "rv", Text(remaining, style=style))
        except Exception:
            pass

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
        finally:
            self._assignees_loaded.set()
            self.app.call_from_thread(self._update_loading_status)

    def _populate_assign_table(self, records: list = None) -> None:
        data = records if records is not None else self._assignees
        assign_table = self.query_one("#detail-left-assign", DataTable)
        assign_table.clear()
        for r in data:
            name = r.get("userName", r.get("dealUserName", r.get("realName", "未知")))
            role = r.get("roleName", "")
            mobile = r.get("mobile", "")
            assign_table.add_row(name, role, mobile)

    def action_toggle_assign(self) -> None:
        header = self.query_one("#detail-left-header", Static)
        search_input = self.query_one("#detail-left-search", Input)
        left_panel = self.query_one("#detail-left")
        log = self.query_one("#detail-left-log", RichLog)
        assign_table = self.query_one("#detail-left-assign", DataTable)
        if self._assign_mode:
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id not in ("detail-left-assign",):
            return
        if self._confirm_mode:
            self._execute_assign()
            return
        try:
            header = self.query_one("#detail-left-header", Static)
            table = event.control
            coord = table.cursor_coordinate
            if coord is None:
                return
            row_index = coord[0]
            row = table.get_row_at(row_index)
            if not row or not row[0]:
                return
            name = str(row[0]).strip()
            matched = next((r for r in self._assignees
                           if (r.get("userName", r.get("dealUserName", r.get("realName", ""))) == name)), None)
            if matched:
                self._pending_assignee = matched
                self._confirm_mode = True
                mobile = matched.get("mobile", "")
                header.update(f"确认指派给 {name}（{mobile}）？ Enter/Y 确认  Esc 取消")
                self._log(f"[yellow]确认将该工单指派给 {name}（{mobile}）？[/yellow]")
                self.notify(f"确认指派给 {name}（{mobile}）？", severity="warning")
                # 焦点留在可见的 header 区域，on_key 全局捕获确认/取消按键
            else:
                self._log(f"[yellow]未找到人员完整信息，请重新选择[/yellow]")
        except Exception as e:
            self.notify(f"选择异常: {e}", severity="error")

    def action_close(self) -> None:
        if self._assign_mode:
            if self._confirm_mode:
                self._cancel_assign()
            else:
                self.action_toggle_assign()
        else:
            self.dismiss()

    def on_key(self, event) -> None:
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
        header = self.query_one("#detail-left-header", Static)
        header.update(f"→ 可指派人员（{len(self._assignees)} 人）")
        self._log("[dim]已取消指派[/dim]")
        self.set_focus(self.query_one("#detail-left-search"))

    def _execute_assign(self) -> None:
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
        threading.Thread(target=self._fetch_detail, daemon=True).start()
        threading.Thread(target=self._fetch_assignees, daemon=True).start()

    def action_refresh_detail(self) -> None:
        self._log("[cyan]正在刷新...[/cyan]")
        self._refresh_detail()

    def _on_assign_success(self, name: str) -> None:
        self._log(f"[bold green]指派成功！已分配给 {name}[/bold green]")
        self.notify(f"指派成功！已分配给 {name}", severity="information")
        self.action_toggle_assign()
        threading.Timer(5, lambda: self.app.call_from_thread(self.action_refresh_detail)).start()

    def _on_assign_fail(self, msg: str) -> None:
        self._log(f"[bold red]指派失败: {msg}，请稍后重试[/bold red]")
        self.notify(f"指派失败: {msg}", severity="error")
