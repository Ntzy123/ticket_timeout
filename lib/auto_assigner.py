"""自动指派核心逻辑：查询工单详情、分类、派单"""

import json
import logging
import os
import sys
import requests
from datetime import datetime
from typing import Callable

from lib import api as lib_api
from lib.config_manager import (
    load_assign_config,
    resolve_department,
    build_butler_map,
    append_history,
)

logger = logging.getLogger("ticket_timeout")


def _get_headers() -> dict:
    """加载请求头（复用 app.py 中 load_api_config 相同的逻辑）"""
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


def _fetch_detail(workorder_no: str, etl_code: str) -> dict | None:
    """查询工单详情，返回详情 data 或 None"""
    url = lib_api.DETAIL_URL_TPL.format(etl_code=etl_code)
    headers = _get_headers()
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"[自动指派] 详情查询 HTTP {resp.status_code} - 工单 {workorder_no}")
            return None
        data = resp.json()
        if data.get("code") == 200 or data.get("msg") == "success":
            return data.get("data", {})
        else:
            logger.warning(f"[自动指派] 详情查询失败: {data.get('msg')} - 工单 {workorder_no}")
            return None
    except Exception as e:
        logger.error(f"[自动指派] 详情查询异常 {workorder_no}: {e}", exc_info=True)
        return None


def _do_assign(
    workorder_no: str,
    user_id: str,
    mobile: str,
    name: str,
    project_id: str,
    wo_type: str,
    source: str,
) -> bool:
    """执行指派 API 调用"""
    body = lib_api.build_assign_body(
        deal_user_id=user_id,
        deal_user_mobile=mobile,
        deal_user_name=name,
        project_code=project_id,
        workorder_no=workorder_no,
        wo_type=wo_type,
        source=source,
    )
    headers = _get_headers()
    try:
        resp = requests.post(
            lib_api.ASSIGN_URL, json=body, headers=headers, verify=False, timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("isOk") or str(data.get("code", "")) in ("200",):
                logger.info(f"[自动指派] 指派成功 {workorder_no} → {name}({mobile})")
                return True
            else:
                logger.warning(f"[自动指派] 指派失败 {workorder_no}: {data.get('msg', '未知')}")
                return False
        else:
            logger.warning(f"[自动指派] 指派 HTTP {resp.status_code} - 工单 {workorder_no}")
            return False
    except Exception as e:
        logger.error(f"[自动指派] 指派异常 {workorder_no}: {e}", exc_info=True)
        return False


def auto_assign_single(
    workorder_no: str,
    etl_code: str,
    project_id: str = "52010017",
    source: str = "02",
    callback: Callable | None = None,
) -> None:
    """自动指派单个工单（在后台线程中调用）

    参数:
        workorder_no: 工单号
        etl_code: 工单 ETL 编码
        project_id: 项目 ID
        source: 来源
        callback: 可选的回调函数，指派完成后调用 (success: bool, info: dict)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[自动指派] 开始处理工单 {workorder_no}")

    # 1. 查询工单详情
    detail = _fetch_detail(workorder_no, etl_code)
    if not detail:
        logger.warning(f"[自动指派] 无法获取工单详情，跳过 {workorder_no}")
        return

    workorder_type_name = detail.get("workorderTypeName", "")
    create_name = detail.get("createName", "")

    # 2. 解析 workorderTypeName → 部门
    department = resolve_department(workorder_type_name)
    if not department:
        logger.info(f"[自动指派] 工单 {workorder_no} 类型 '{workorder_type_name}' 不在自动指派范围，跳过")
        return

    # 3. 查管家配置 → 地块
    butler_map = build_butler_map()
    plot = butler_map.get(create_name)
    if not plot:
        logger.info(f"[自动指派] 工单 {workorder_no} 创建人 '{create_name}' 未配置地块，跳过")
        return

    # 4. 检查部门是否启用
    assign_config = load_assign_config()
    dept_config = assign_config.get(department)
    if not dept_config or not dept_config.get("enabled"):
        logger.info(f"[自动指派] 部门 '{department}' 未启用自动指派，跳过工单 {workorder_no}")
        return

    # 5. 获取该部门+地块的接单人（唯一指定）
    assignees = dept_config.get("assignees", {})
    assignee = assignees.get(plot)
    if not assignee:
        logger.info(f"[自动指派] 部门 '{department}' 地块 '{plot}' 未配置接单人，跳过工单 {workorder_no}")
        return

    assignee_name = assignee["name"]
    assignee_mobile = assignee["mobile"]
    assignee_user_id = assignee["userId"]

    # 6. 调用指派 API
    success = _do_assign(
        workorder_no=workorder_no,
        user_id=assignee_user_id,
        mobile=assignee_mobile,
        name=assignee_name,
        project_id=project_id,
        wo_type="OD",
        source=source,
    )

    # 7. 记录结果
    if success:
        record = {
            "workorderNo": workorder_no,
            "workorderDescription": detail.get("workorderDescription") or detail.get("workorderTitle", ""),
            "workorderStatusName": detail.get("workorderStatusName", ""),
            "department": department,
            "plot": plot,
            "assigneeName": assignee_name,
            "assigneeMobile": assignee_mobile,
            "acceptTime": now_str,
            "createName": create_name,
            "workorderTypeName": workorder_type_name,
        }
        append_history(record)

    if callback:
        try:
            callback(success, {
                "workorderNo": workorder_no,
                "department": department,
                "plot": plot,
                "assigneeName": assignee_name,
                "success": success,
            })
        except Exception:
            pass
