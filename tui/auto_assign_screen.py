"""自动指派管理全屏界面 + 配置页面"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, DataTable
from textual.containers import Horizontal, Vertical
from textual.binding import Binding

from lib.config_manager import (
    load_assign_config,
    load_butler_config,
    load_history,
    cleanup_history,
)
from tui.detail_screen import DetailScreen


class ConfigPanel(Vertical):
    """配置面板（左半区），通过 show_assignee/show_butler 切换显示内容"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._showing_assignee = True  # True=接单人配置, False=管家配置

    def compose(self) -> ComposeResult:
        yield DataTable(id="config-table")

    def on_mount(self) -> None:
        self._render_assignee()

    def _render_assignee(self) -> None:
        """渲染接单人配置表格"""
        table = self.query_one("#config-table", DataTable)
        table.clear(columns=True)
        table.add_column("部门", key="dept", width=4)
        table.add_column("地块", key="plot", width=6)
        table.add_column("接单人", key="name", width=8)
        table.add_column("电话", key="mobile", width=11)
        table.add_column("状态", key="status", width=7)
        table.cursor_type = "row"

        config = load_assign_config()
        for dept_name, dept_cfg in config.items():
            enabled = dept_cfg.get("enabled", False)
            status_text = "● 启用" if enabled else "○ 停用"
            assignees = dept_cfg.get("assignees", {})
            for plot, person in assignees.items():
                table.add_row(dept_name, plot, person['name'], person['mobile'], status_text)
        self._showing_assignee = True

    def _render_butler(self) -> None:
        """渲染管家配置表格"""
        table = self.query_one("#config-table", DataTable)
        table.clear(columns=True)
        table.add_column("创建人", key="name", width=20)
        table.add_column("所属地块", key="plot", width=20)
        table.cursor_type = "row"

        butlers = load_butler_config()
        for b in butlers:
            table.add_row(b.get("name", ""), b.get("plot", ""))
        self._showing_assignee = False

    def toggle(self) -> None:
        """在接单人配置和管家配置之间切换"""
        if self._showing_assignee:
            self._render_butler()
        else:
            self._render_assignee()


class AutoAssignScreen(ModalScreen):
    """自动指派管理全屏界面"""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #aa-config-split {
        layout: horizontal;
        height: 1fr;
    }

    #aa-config-panel {
        layout: vertical;
        width: 48;
        border: none;
        border-right: solid $border;
        background: $surface;
        display: none;
    }

    #aa-right-panel {
        layout: vertical;
        width: 1fr;
    }

    #config-table {
        height: 1fr;
    }

    #aa-header,
    #aa-config-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
        text-align: center;
    }

    #aa-config-header {
        display: none;
    }

    #aa-table {
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
        Binding("p", "toggle_config", "配置", key_display="P"),
        Binding("r", "refresh", "刷新", key_display="R"),
        Binding("tab", "toggle_config_tab", "切换管家配置"),
        Binding("q", "close", "返回", key_display="Q"),
        Binding("escape", "close", "返回"),
    ]

    def __init__(self, headers: dict, project_id: str, source: str, **kwargs):
        super().__init__(**kwargs)
        self._api_headers = headers
        self._api_project_id = project_id
        self._api_source = source
        self._config_mode = False
        self._history: list[dict] = []
        self._row_keys: list = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("═ 自动指派记录 ═", id="aa-header")
        yield Static("═ 自动指派配置 ═", id="aa-config-header")
        with Horizontal(id="aa-config-split"):
            with Vertical(id="aa-config-panel"):
                yield ConfigPanel()
            with Vertical(id="aa-right-panel"):
                yield DataTable(id="aa-table")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table(self.query_one("#aa-table", DataTable))
        self._refresh()

    def _setup_table(self, table: DataTable) -> None:
        table.add_column("指派时间", key="acceptTime", width=16)
        table.add_column("工单编号", key="id", width=16)
        table.add_column("任务描述", key="desc")
        table.add_column("处理人", key="handler", width=8)
        table.add_column("状态", key="status", width=8)
        table.cursor_type = "row"

    def _refresh(self) -> None:
        """重新加载历史并刷新表格（自动清理超过 48 小时的记录）"""
        cleanup_history(max_hours=48)
        self._history = load_history()
        self._rebuild_table(self.query_one("#aa-table", DataTable))

    def _rebuild_table(self, table: DataTable) -> None:
        table.clear()
        self._row_keys.clear()
        # 按指派时间降序排列
        sorted_history = sorted(
            self._history,
            key=lambda x: x.get("acceptTime", ""),
            reverse=True,
        )
        for item in sorted_history:
            row = table.add_row(
                item.get("acceptTime", ""),
                item.get("workorderNo", ""),
                item.get("workorderDescription", ""),
                item.get("assigneeName", ""),
                item.get("workorderStatusName", ""),
            )
            self._row_keys.append(row)

    # ── 动作 ────────────────────────────────────────────
    def action_close(self) -> None:
        self.dismiss()

    def action_refresh(self) -> None:
        self._refresh()
        self.notify("已刷新", severity="information")

    def action_toggle_config(self) -> None:
        """切换配置模式（P 键）"""
        aa_header = self.query_one("#aa-header", Static)
        aa_config_header = self.query_one("#aa-config-header", Static)
        config_panel = self.query_one("#aa-config-panel")

        if not self._config_mode:
            aa_header.styles.display = "none"
            aa_config_header.styles.display = "block"
            config_panel.styles.display = "block"
            self._config_mode = True
            aa_config_header.update("═ 接单人配置 ═")
        else:
            aa_header.styles.display = "block"
            aa_config_header.styles.display = "none"
            config_panel.styles.display = "none"
            self._config_mode = False

    def action_toggle_config_tab(self) -> None:
        """Tab 切换配置面板内容（仅在配置模式下生效）"""
        if not self._config_mode:
            return
        try:
            panel = self.query_one(ConfigPanel)
            panel.toggle()
            # 同步更新统一标题
            is_assignee = panel._showing_assignee
            title = "═ 接单人配置 ═" if is_assignee else "═ 管家配置 ═"
            self.query_one("#aa-config-header", Static).update(title)
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter → 查看工单详情（复用 DetailScreen）"""
        if event.control.id != "aa-table":
            return

        table = event.control
        try:
            coord = table.cursor_coordinate
            if coord is None:
                return
            row = table.get_row_at(coord[0])
        except Exception:
            return
        if not row or not row[1]:
            return

        wo_no = str(row[1]).strip()
        _placeholders = {"暂无数据", "", "等待首次查询..."}
        if wo_no in _placeholders or len(wo_no) < 5:
            return

        # 从历史中找 etlCode（如果有存储的话），没有则传空字符串
        matched = next((h for h in self._history if h.get("workorderNo") == wo_no), None)
        etl_code = matched.get("etlCode", "") if matched else ""

        self.push_screen(
            DetailScreen(
                workorder_no=wo_no,
                headers=self._api_headers,
                etl_code=etl_code,
                source=self._api_source,
                project_id=self._api_project_id,
                wo_type="OD",
            ),
        )
