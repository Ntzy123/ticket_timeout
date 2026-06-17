"""TUI 共享工具函数和常量"""

import json
import os
import sys
import tomllib
from datetime import datetime

from lib.init_app import BASE_DIR

# ── TOML 忽略工单管理 ───────────────────────────────────
IGNORE_FILE = os.path.join(BASE_DIR, "config", "ignored.toml")


def load_ignored() -> list[dict]:
    """加载 ignored.toml，返回 [{workorder_no, description, reason}, ...]"""
    try:
        with open(IGNORE_FILE, "rb") as f:
            data = tomllib.load(f)
        return data.get("ignore", [])
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return []


def load_ignored_set() -> set[str]:
    """仅返回已忽略工单号的集合（用于过滤）"""
    return {r["workorder_no"] for r in load_ignored()}


def add_ignored(wo_no: str, description: str = "", reason: str = ""):
    """追加一条忽略记录"""
    records = load_ignored()
    if any(r["workorder_no"] == wo_no for r in records):
        return
    records.append({
        "workorder_no": wo_no,
        "description": description,
        "reason": reason,
    })
    _write_ignored(records)


def remove_ignored(wo_no: str):
    """从 TOML 中移除指定工单号"""
    records = [r for r in load_ignored() if r["workorder_no"] != wo_no]
    _write_ignored(records)


def _escape_toml(s: str) -> str:
    """转义 TOML 双引号字符串中的特殊字符"""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _write_ignored(records: list[dict]):
    """回写 TOML 文件（安全转义特殊字符）"""
    lines = ["# 已忽略工单列表\n"]
    for r in records:
        lines.append("[[ignore]]\n")
        lines.append(f'workorder_no = "{_escape_toml(r["workorder_no"])}"\n')
        if r.get("description"):
            lines.append(f'description = "{_escape_toml(r["description"])}"\n')
        if r.get("reason"):
            lines.append(f'reason = "{_escape_toml(r["reason"])}"\n')
        lines.append("\n")
    with open(IGNORE_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ── 时间格式化 ──────────────────────────────────────────
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
    else:
        if total_minutes < 10:
            return "red"
        elif total_minutes < 30:
            return "yellow"
        return "green"


def now_str() -> str:
    """返回当前时间的格式化字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def truncate(text: str, max_len: int = 60) -> str:
    """过长文本截断，末尾加..."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def ralign(text: str, width: int = 10) -> str:
    """右对齐填充"""
    text = str(text)
    return text.rjust(width) if len(text) < width else text


# ── API 配置 ────────────────────────────────────────────
def load_api_config() -> dict:
    """从配置文件加载 API 请求头（过滤掉固定字段）"""
    config_path = os.path.join("config", ".config.json")
    if not os.path.isfile(config_path):
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        config_path = os.path.join(base, "config", ".config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    headers = cfg.get("headers", {})
    for k in ("Content-Length", "Accept-Encoding"):
        headers.pop(k, None)
    return headers
