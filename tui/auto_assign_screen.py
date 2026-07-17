"""自动指派管理全屏界面 + 配置页面"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, DataTable
from textual.containers import Horizontal, Vertical
from textual.binding import Binding

from lib.config_manager import (
    load_assign_config,
    write_assign_config,
    load_butler_config,
    load_history,
    cleanup_history,
)
from tui.detail_screen import DetailScreen
from tui.person_edit_screen import PersonEditScreen


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
        """第一层：显示部门·地块·接单人（每岗一行，共 6 行）"""
        table = self.query_one("#config-table", DataTable)
        table.clear(columns=True)
        table.add_column("部门", key="dept", width=4)
        table.add_column("地块", key="plot", width=6)
        table.add_column("接单人", key="name", width=8)
        table.add_column("可选", key="avail", width=6)
        table.add_column("状态", key="status", width=8)
        table.cursor_type = "row"

        config = load_assign_config()
        for dept_name, dept_cfg in config.items():
            assignees = dept_cfg.get("assignees", {})
            # 计算该部门总人数（去重，含部门级备份 + 各岗位级备份）
            all_people: set[str] = set()
            for _plot, person in assignees.items():
                all_people.add(person["name"])
                for b in person.get("backups", []):
                    all_people.add(b["name"])
            for b in dept_cfg.get("backups", []):
                all_people.add(b["name"])
            avail_str = f"{len(all_people)} 人"
            for plot, person in assignees.items():
                is_on = person.get("enabled", True)
                status_text = "● 启用" if is_on else "○ 停用"
                table.add_row(
                    dept_name, plot,
                    person['name'],
                    avail_str,
                    status_text,
                )
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
        Binding("space", "toggle_enabled", "启用/停用", key_display="Space"),
        Binding("up", "nav_up", "上移", show=False),
        Binding("down", "nav_down", "下移", show=False),
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

    def action_toggle_enabled(self) -> None:
        """Space 键：切换选中岗位的启用/停用状态"""
        if not self._config_mode:
            return
        try:
            table = self.query_one("#config-table", DataTable)
            coord = table.cursor_coordinate
            if coord is None:
                return
            row = table.get_row_at(coord[0])
            if not row or len(row) < 2:
                return
            dept = str(row[0]).strip()
            plot = str(row[1]).strip()
            config = load_assign_config()
            dept_cfg = config.get(dept)
            if not dept_cfg:
                return
            assignees = dept_cfg.setdefault("assignees", {})
            person = assignees.get(plot)
            if not person:
                return
            current = person.get("enabled", True)
            person["enabled"] = not current
            write_assign_config(config)
            # 记住当前选中的行号，重绘后恢复
            saved_row = coord[0]
            panel = self.query_one(ConfigPanel)
            panel._render_assignee()
            # 恢复光标
            new_table = self.query_one("#config-table", DataTable)
            new_coord = min(saved_row, new_table.row_count - 1)
            if new_coord >= 0:
                new_table.move_cursor(row=new_coord, column=0)
            status = "启用" if person["enabled"] else "停用"
            self.notify(f"{dept}·{plot} 已{status}", severity="information")
        except Exception as e:
            self.notify(f"切换失败: {e}", severity="error")

    # ── 循环滚动（Binding 拦截 pre-handler，避免与 DataTable 冲突）───
    def _move_cursor_in_table(self, direction: str) -> None:
        """通用的光标移动：配置模式循环滚动，历史模式正常移动"""
        table = self.focused
        if not isinstance(table, DataTable):
            return
        coord = table.cursor_coordinate
        if coord is None or table.row_count <= 1:
            return
        r, c = coord[0], coord[0]

        if direction == "up":
            target = table.row_count - 1 if r == 0 else r - 1
        else:
            target = 0 if r == table.row_count - 1 else r + 1
        table.move_cursor(row=target, column=0)

    def action_nav_up(self) -> None:
        self._move_cursor_in_table("up")

    def action_nav_down(self) -> None:
        self._move_cursor_in_table("down")

    def _open_person_edit(self, row: tuple) -> None:
        """打开第二层：该岗位的人员选择与管理界面"""
        dept = str(row[0]).strip()
        plot = str(row[1]).strip()
        config = load_assign_config()
        self.app.push_screen(
            PersonEditScreen(config, dept, plot),
            callback=lambda _: self._reload_config(),
        )

    def _reload_config(self) -> None:
        """关闭 PersonEditScreen 后重新加载配置并刷新"""
        panel = self.query_one(ConfigPanel)
        if panel._showing_assignee:
            panel._render_assignee()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter → 查看工单详情，或打开人员管理"""
        table_id = event.control.id
        if table_id not in ("aa-table", "config-table"):
            return

        table = event.control
        try:
            coord = table.cursor_coordinate
            if coord is None:
                return
            row = table.get_row_at(coord[0])
        except Exception:
            return
        if not row:
            return

        # ── 配置模式：打开岗位人员管理 ─────────────
        if table_id == "config-table":
            self._open_person_edit(row)
            return

        # ── 历史模式：查看工单详情 ─────────────────
        if not row[1]:
            return
        wo_no = str(row[1]).strip()
        _placeholders = {"暂无数据", "", "等待首次查询..."}
        if wo_no in _placeholders or len(wo_no) < 5:
            return

        # 从历史中找 etlCode（如果有存储的话），没有则传空字符串
        matched = next((h for h in self._history if h.get("workorderNo") == wo_no), None)
        etl_code = matched.get("etlCode", "") if matched else ""

        self.app.push_screen(
            DetailScreen(
                workorder_no=wo_no,
                headers=self._api_headers,
                etl_code=etl_code,
                source=self._api_source,
                project_id=self._api_project_id,
                wo_type="OD",
            ),
        )
