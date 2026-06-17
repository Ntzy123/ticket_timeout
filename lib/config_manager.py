"""配置管理模块：读写部门配置、管家配置、自动指派历史"""

import json
import os
import tomllib
from typing import Any

from lib.init_app import BASE_DIR

CONFIG_DIR = os.path.join(BASE_DIR, "config")
ASSIGN_CONFIG_FILE = os.path.join(CONFIG_DIR, "assign_config.toml")
BUTLER_CONFIG_FILE = os.path.join(CONFIG_DIR, "butler_config.toml")
HISTORY_FILE = os.path.join(CONFIG_DIR, "auto_assign_history.json")

# ── 工单类型 → 部门映射 ────────────────────────────────
WORKORDER_TYPE_MAP: dict[str, str] = {
    "公共清洁": "保洁",
    "环境绿化": "绿化",
    "公共秩序": "安防",
}


# ── 部门配置 ────────────────────────────────────────────
def load_assign_config() -> dict[str, Any]:
    """加载 assign_config.toml，返回结构：
    {
        "保洁": {
            "enabled": True,
            "assignees": {
                "11号地": {"name": "张明金", "mobile": "15685306313", "userId": "2076797"},
                "6号地":  {"name": "柏万碧", "mobile": "18985106736", "userId": "2078412"},
            },
        },
        ...
    }
    """
    try:
        with open(ASSIGN_CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}

    # TOML 中所有表头即为部门名（["保洁"] → 保洁）
    result: dict[str, Any] = {}
    departments = data
    for dept_name, dept_cfg in departments.items():
        enabled = dept_cfg.get("enabled", False)
        assignees_raw = dept_cfg.get("assignees", {})
        assignees: dict[str, dict[str, str]] = {}
        for plot, person in assignees_raw.items():
            if isinstance(person, dict) and person.get("name"):
                assignees[plot] = {
                    "name": person["name"],
                    "mobile": person.get("mobile", ""),
                    "userId": person.get("userId", ""),
                }
        result[dept_name] = {
            "enabled": enabled,
            "assignees": assignees,
        }
    return result


# ── 管家配置 ────────────────────────────────────────────
def load_butler_config() -> list[dict[str, str]]:
    """加载 butler_config.toml，返回：
    [{"name": "赵中婧", "plot": "11号地"}, ...]
    """
    try:
        with open(BUTLER_CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return []
    return data.get("butlers", [])


def build_butler_map() -> dict[str, str]:
    """返回 {创建人姓名: 地块} 的字典，用于快速查找"""
    butlers = load_butler_config()
    return {b["name"]: b["plot"] for b in butlers if b.get("name") and b.get("plot")}


# ── 工单类型 → 部门 解析 ────────────────────────────────
def resolve_department(workorder_type_name: str) -> str | None:
    """根据 workorderTypeName 的第一段返回部门名称，不在映射表内返回 None"""
    if not workorder_type_name:
        return None
    first_segment = workorder_type_name.split("/")[0].strip()
    return WORKORDER_TYPE_MAP.get(first_segment)


# ── 自动指派历史 ────────────────────────────────────────
def load_history() -> list[dict]:
    """加载自动指派历史"""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def append_history(record: dict) -> None:
    """追加一条指派历史记录"""
    history = load_history()
    history.append(record)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def cleanup_history(max_hours: int = 48) -> None:
    """删除超过指定小时数的指派历史记录，并在文件上持久化"""
    from datetime import datetime, timedelta
    history = load_history()
    cutoff = datetime.now() - timedelta(hours=max_hours)
    kept = []
    for h in history:
        try:
            t = datetime.strptime(h.get("acceptTime", ""), "%Y-%m-%d %H:%M:%S")
            if t >= cutoff:
                kept.append(h)
        except (ValueError, TypeError):
            continue
    if len(kept) < len(history):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
