# run.py

import typer

from tui.app import TicketMonitorApp


def main(
    wait_time: int = typer.Option(120, "--time", "-t", help="临时性工单查询间隔（秒）"),
    end_time: str = typer.Option(
        None, "--end", "-e",
        help="程序结束时间（24小时制，例如 8:30 或 20:30），不指定则不自动关闭"
    ),
):
    """工单超时监控终端 - TUI 界面"""
    # 解析 end_time
    end_time_tuple = None
    if end_time is not None:
        try:
            parts = end_time.strip().replace("：", ":").split(":")
            end_hour = int(parts[0])
            end_minute = int(parts[1]) if len(parts) > 1 else 0
            end_time_tuple = (end_hour, end_minute)
        except (ValueError, IndexError):
            print("[ERROR] 结束时间格式错误，请使用 HH:MM 格式（例如 8:30 或 20:30）")
            return

    app = TicketMonitorApp(
        wait_time=wait_time,
        end_time=end_time_tuple,
    )
    app.run()


if __name__ == "__main__":
    typer.run(main)