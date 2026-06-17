"""已忽略工单管理弹窗"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Static, DataTable
from textual.containers import Vertical
from textual.binding import Binding

from tui.common import load_ignored, remove_ignored


class IgnoreListScreen(ModalScreen):
    """查看和管理已忽略工单"""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #ignore-container {
        layout: vertical;
        height: 1fr;
    }

    #ignore-header {
        background: $primary-background;
        color: $text;
        padding: 0 1;
        border-bottom: tall $border;
        text-style: bold;
        width: 100%;
        text-align: center;
    }

    #ignore-table {
        height: 1fr;
    }

    #ignore-footer {
        padding: 0 1;
        border-top: tall $border;
        background: $primary-background;
    }

    Header {
        background: $primary-background;
    }

    Footer {
        background: $primary-background;
    }
    """

    BINDINGS = [
        Binding("q", "close", "返回", key_display="Q"),
        Binding("escape", "close", "返回"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="ignore-container"):
            yield Static("═══ 已忽略工单 ═══", id="ignore-header")
            yield DataTable(id="ignore-table")
            yield Static("[dim]Enter 取消忽略  Esc 返回[/dim]", id="ignore-footer")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#ignore-table", DataTable)
        table.add_column("工单编号", key="id", width=20)
        table.add_column("工单描述", key="desc")
        table.cursor_type = "row"
        self._refresh_list()

    def _refresh_list(self) -> None:
        records = load_ignored()
        table = self.query_one("#ignore-table", DataTable)
        table.clear()
        for r in records:
            table.add_row(
                r.get("workorder_no", ""),
                r.get("description", ""),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id != "ignore-table":
            return
        table = event.control
        try:
            coord = table.cursor_coordinate
            if coord is None:
                return
            row = table.get_row_at(coord[0])
        except Exception:
            return
        if not row or not row[0]:
            return
        wo_no = str(row[0]).strip()
        if len(wo_no) < 5:
            return
        remove_ignored(wo_no)
        self._refresh_list()
        self.notify(f"已取消忽略工单 {wo_no}", severity="information")

    def action_close(self) -> None:
        self.dismiss()
