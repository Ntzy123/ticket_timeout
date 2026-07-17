"""第二层：部门人员选择与管理（含 CRUD）"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, DataTable, Input
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from rich.text import Text

from lib.config_manager import write_assign_config


class PersonEditScreen(ModalScreen):
    """部门人员选择与管理弹窗"""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #pe-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
        text-align: center;
    }

    #pe-table {
        height: 1fr;
    }

    #pe-form {
        layout: horizontal;
        height: 5;
        padding: 0 1;
        background: $panel;
        border-top: tall $border;
        display: none;
    }

    #pe-form > Vertical {
        margin: 0 1;
    }

    #pe-form Input {
        width: 20;
    }

    #pe-form-buttons {
        width: auto;
        height: 100%;
        align: center middle;
    }

    Header {
        background: $primary-background;
    }

    Footer {
        background: $primary-background;
    }
    """

    BINDINGS = [
        Binding("a", "add_person", "增加", key_display="A"),
        Binding("c", "copy_person", "复制", key_display="C"),
        Binding("e", "edit_person", "修改", key_display="E"),
        Binding("d", "delete_person", "删除", key_display="D"),
        Binding("up", "nav_up", "上移", show=False),
        Binding("down", "nav_down", "下移", show=False),
        Binding("q", "close", "返回", key_display="Q"),
        Binding("escape", "close", "返回"),
    ]

    def __init__(self, config: dict, department: str, plot: str) -> None:
        super().__init__()
        self._config = config
        self._department = department
        self._plot = plot
        self._dept_cfg = config.get(department, {})
        self._persons: list[dict] = []
        self._row_keys: list = []
        self._editing_index: int | None = None  # None = 新增, int = 编辑索引
        self._copy_data: dict | None = None

    # ── 人员收集 ─────────────────────────────────
    def _collect_persons(self) -> None:
        """收集该部门所有人员（去重），填入 self._persons"""
        raw = {}
        assignees = self._dept_cfg.get("assignees", {})

        def _ensure(name: str) -> dict:
            if name not in raw:
                raw[name] = {"name": name, "mobile": "", "userId": "", "plots": [], "roles": {}}
            return raw[name]

        for plot, person in assignees.items():
            entry = _ensure(person["name"])
            entry["mobile"] = person.get("mobile", "")
            entry["userId"] = person.get("userId", "")
            if plot not in entry["plots"]:
                entry["plots"].append(plot)
            entry["roles"][plot] = "current"

            for b in person.get("backups", []):
                bentry = _ensure(b["name"])
                bentry["mobile"] = b.get("mobile", "")
                bentry["userId"] = b.get("userId", "")
                if plot not in bentry["plots"]:
                    bentry["plots"].append(plot)
                bentry["roles"].setdefault(plot, "backup")

        # 部门级备份人员（不绑定具体地块）
        for b in self._dept_cfg.get("backups", []):
            if isinstance(b, dict) and b.get("name"):
                bentry = _ensure(b["name"])
                bentry["mobile"] = b.get("mobile", "")
                bentry["userId"] = b.get("userId", "")

        self._persons = list(raw.values())

    # ── 界面 ─────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="pe-header")
        yield DataTable(id="pe-table")
        with Horizontal(id="pe-form"):
            with Vertical():
                yield Input(placeholder="姓名", id="pe-input-name")
            with Vertical():
                yield Input(placeholder="电话", id="pe-input-mobile")
            with Vertical():
                yield Input(placeholder="userId", id="pe-input-userid")
            with Vertical(id="pe-form-buttons"):
                yield Static("[bold]Enter 保存  Esc 取消[/bold]")
        yield Footer()

    def on_mount(self) -> None:
        self._collect_persons()
        header_text = f"═ {self._department} · {self._plot}  — 人员选择 ═"
        self.query_one("#pe-header", Static).update(header_text)
        table = self.query_one("#pe-table", DataTable)
        table.add_column("姓名", key="name", width=10)
        table.add_column("电话", key="mobile", width=13)
        table.add_column("当前所属地块", key="plots", width=20)
        table.cursor_type = "row"
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one("#pe-table", DataTable)
        table.clear()
        self._row_keys.clear()
        for p in self._persons:
            if p["roles"].get(self._plot) == "current":
                plots_cell = Text(f"◀ {self._plot}", style="bold green")
            elif "current" in p["roles"].values():
                current_plots = [pl for pl, r in p["roles"].items() if r == "current"]
                plots_cell = Text("，".join(current_plots), style="green")
            else:
                plots_cell = Text("无", style="dim")
            row = table.add_row(
                Text(p["name"], style="bold" if p["roles"].get(self._plot) == "current" else ""),
                p["mobile"],
                plots_cell,
            )
            self._row_keys.append(row)

    def _update_actions(self) -> None:
        pass  # 已移除屏幕内置提示，统一由 Footer 显示快捷键

    # ── 替换 ─────────────────────────────────────
    def _replace_assignee(self, person: dict) -> None:
        """将 person 设为 self._plot 的当前接单人"""
        assignees = self._dept_cfg.setdefault("assignees", {})
        current = assignees.get(self._plot)
        if current and current["name"] == person["name"]:
            self.notify(f"{person['name']} 已是当前接单人", severity="information")
            return

        # 旧接单人 → 备份
        old_name = current["name"] if current else None
        if current:
            assignees[self._plot] = {
                "name": person["name"],
                "mobile": person.get("mobile", ""),
                "userId": person.get("userId", ""),
                "enabled": current.get("enabled", True),
                "backups": current.get("backups", []),
            }
            # 旧人加入备份（如果不在备份中）
            backups = assignees[self._plot].setdefault("backups", [])
            if not any(b["name"] == old_name for b in backups):
                backups.append({
                    "name": current["name"],
                    "mobile": current.get("mobile", ""),
                    "userId": current.get("userId", ""),
                })
        else:
            assignees[self._plot] = {
                "name": person["name"],
                "mobile": person.get("mobile", ""),
                "userId": person.get("userId", ""),
                "backups": [],
            }

        write_assign_config(self._config)
        self._collect_persons()
        self._rebuild_table()
        self.notify(f"{person['name']} 已替换为 {self._plot} 的当前接单人", severity="information")

    # ── CRUD ─────────────────────────────────────
    def _enter_form(self, index: int | None, copy_data: dict | None = None) -> None:
        """进入编辑/新增表单"""
        self._editing_index = index
        self._copy_data = copy_data
        form = self.query_one("#pe-form")
        form.styles.display = "block"

        name_input = self.query_one("#pe-input-name", Input)
        mobile_input = self.query_one("#pe-input-mobile", Input)
        userid_input = self.query_one("#pe-input-userid", Input)

        if index is not None and copy_data is None:
            p = self._persons[index]
            name_input.value = p["name"]
            mobile_input.value = p["mobile"]
            userid_input.value = p["userId"]
        else:
            data = copy_data or {}
            name_input.value = data.get("name", "")
            mobile_input.value = data.get("mobile", "")
            userid_input.value = data.get("userId", "")

        # 新增或复制时姓名可编辑；修改时只改手机和 userId
        if index is not None and copy_data is None:
            name_input.read_only = True
        else:
            name_input.read_only = False

        self.set_focus(name_input)

    def _hide_form(self) -> None:
        form = self.query_one("#pe-form")
        form.styles.display = "none"
        self._editing_index = None
        self._copy_data = None
        self.set_focus(self.query_one("#pe-table"))

    def _save_form(self) -> None:
        name = self.query_one("#pe-input-name", Input).value.strip()
        mobile = self.query_one("#pe-input-mobile", Input).value.strip()
        userid = self.query_one("#pe-input-userid", Input).value.strip()
        if not name:
            self.notify("姓名不能为空", severity="warning")
            return

        if self._editing_index is not None and self._copy_data is None:
            # 修改：更新该人在各处的信息
            old_name = self._persons[self._editing_index]["name"]
            assignees = self._dept_cfg.setdefault("assignees", {})
            for plot, person in assignees.items():
                if person["name"] == old_name:
                    person["mobile"] = mobile
                    person["userId"] = userid
                for b in person.get("backups", []):
                    if b["name"] == old_name:
                        b["mobile"] = mobile
                        b["userId"] = userid
        else:
            # 新增/复制 → 加入当前岗位的备份列表
            assignees = self._dept_cfg.setdefault("assignees", {})
            current = assignees.get(self._plot, {})
            backups = current.get("backups", [])
            if any(b["name"] == name for b in backups):
                self.notify(f"备用人员中已存在 {name}", severity="warning")
                return
            if current and current.get("name") == name:
                self.notify(f"{name} 已是当前接单人", severity="warning")
                return
            backups.append({"name": name, "mobile": mobile, "userId": userid})
            if current:
                current["backups"] = backups
            else:
                assignees[self._plot] = {"name": "", "mobile": "", "userId": "",
                                          "backups": backups}

        write_assign_config(self._config)
        self._hide_form()
        self._collect_persons()
        self._rebuild_table()
        self.notify("已保存", severity="information")

    # ── 动作 ─────────────────────────────────────
    def action_close(self) -> None:
        self.dismiss()

    def action_add_person(self) -> None:
        self._enter_form(index=None)

    def action_copy_person(self) -> None:
        coord = self.query_one("#pe-table", DataTable).cursor_coordinate
        if coord is None or coord[0] >= len(self._persons):
            self.notify("请先选择一个人员", severity="warning")
            return
        p = self._persons[coord[0]]
        self._enter_form(index=None, copy_data=p)

    def action_edit_person(self) -> None:
        coord = self.query_one("#pe-table", DataTable).cursor_coordinate
        if coord is None or coord[0] >= len(self._persons):
            self.notify("请先选择一个人员", severity="warning")
            return
        self._enter_form(index=coord[0])

    def action_delete_person(self) -> None:
        coord = self.query_one("#pe-table", DataTable).cursor_coordinate
        if coord is None or coord[0] >= len(self._persons):
            self.notify("请先选择一个人员", severity="warning")
            return
        p = self._persons[coord[0]]
        name = p["name"]

        # 检查是否是当前岗位的接单人
        assignees = self._dept_cfg.setdefault("assignees", {})
        current = assignees.get(self._plot, {})
        if current and current.get("name") == name:
            self.notify(f"{name} 是当前接单人，无法直接删除，请先替换", severity="error")
            return

        # 删除：从所有备份中移除
        removed = False
        for plot, person in assignees.items():
            backups = person.get("backups", [])
            before = len(backups)
            person["backups"] = [b for b in backups if b["name"] != name]
            if len(person["backups"]) < before:
                removed = True

        if not removed:
            self.notify(f"未找到 {name}", severity="warning")
            return

        write_assign_config(self._config)
        self._collect_persons()
        self._rebuild_table()
        self.notify(f"已删除 {name}", severity="information")

    # ── 键盘事件（表单输入处理） ──────────────────
    def on_key(self, event) -> None:
        form = self.query_one("#pe-form")
        if form.styles.display == "block":
            if event.key == "escape":
                event.stop()
                self._hide_form()
            elif event.key in ("enter",):
                event.stop()
                self._save_form()

    # ── 循环滚动（Binding 拦截） ─────────────────
    def _wrap_cursor(self, direction: str) -> None:
        focused = self.focused
        if not isinstance(focused, DataTable) or focused.id != "pe-table":
            return
        coord = focused.cursor_coordinate
        if coord is None or focused.row_count <= 1:
            return
        r = coord[0]
        if direction == "up":
            target = focused.row_count - 1 if r == 0 else r - 1
        else:
            target = 0 if r == focused.row_count - 1 else r + 1
        focused.move_cursor(row=target, column=0)

    def action_nav_up(self) -> None:
        self._wrap_cursor("up")

    def action_nav_down(self) -> None:
        self._wrap_cursor("down")

    # ── Enter 替换 ───────────────────────────────
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id != "pe-table":
            return
        coord = event.control.cursor_coordinate
        if coord is None or coord[0] >= len(self._persons):
            return
        self._replace_assignee(self._persons[coord[0]])
