# run.py

import sys

import requests
import typer

from tui.app import TicketMonitorApp

AUTH_URL = "https://kyrian.asia/api/get_auth"


def check_auth() -> bool:
    """静默鉴权：仅后台请求，不输出任何信息"""
    try:
        return requests.get(AUTH_URL, timeout=5).text.strip() == "OK"
    except Exception:
        return False


def main(
    wait_time: int = typer.Option(120, "--time", "-t", help="临时性工单查询间隔（秒）"),
    end_time: str = typer.Option(
        None, "--end", "-e",
        help="程序结束时间（24小时制，支持格式：8:30、20:30、830、2030），不指定则不自动关闭"
    ),
):
    """工单超时监控终端 - TUI 界面"""
    # 启动时静默鉴权，失败则直接退出
    if not check_auth():
        sys.exit(1)

    # 解析 end_time
    end_time_tuple = None
    if end_time is not None:
        raw = end_time.strip()
        try:
            if ":" in raw or "：" in raw:
                # 格式1: HH:MM（含中文冒号）
                parts = raw.replace("：", ":").split(":")
                end_hour = int(parts[0])
                end_minute = int(parts[1]) if len(parts) > 1 else 0
            elif raw.isdigit() and 3 <= len(raw) <= 4:
                # 格式2: HHMM / HMM（如 2030、807）
                if len(raw) == 3:
                    end_hour = int(raw[0])
                    end_minute = int(raw[1:])
                else:
                    end_hour = int(raw[:2])
                    end_minute = int(raw[2:])
            else:
                raise ValueError("无法识别的格式")

            if not (0 <= end_hour <= 23 and 0 <= end_minute <= 59):
                raise ValueError("时间数值超出范围")

            end_time_tuple = (end_hour, end_minute)
        except ValueError:
            print(f"[WARNING] 结束时间参数 '-e {end_time}' 格式无法识别，程序将正常启动但不会启用自动关闭功能。")
            print(f"          支持格式示例：-e 8:30、-e 20:30、-e 830、-e 2030")

    app = TicketMonitorApp(
        wait_time=wait_time,
        end_time=end_time_tuple,
    )
    app.run()


if __name__ == "__main__":
    typer.run(main)