# lib/api.py — 所有工单 API 配置和请求体构建函数

# ── 查询工单列表 API ──────────────────────────────────
QUERY_URL = (
    "https://heimdallr.onewo.com/api/task/courier/admin/task"
    "/work-order/queryCourierTaskWorkOrderEtlPage"
)

QUERY_BODY_TEMPLATE = {
    "workorderNo": "",
    "createMobile": "",
    "projectId": "52010017",
    "workorderStatus": (
        '["1","1001","1002","1003","1004","1005","1013","1014",'
        '"4040","6","3","4","5","1006","1007","1008","1015",'
        '"4041","10","1017","1091"]'
    ),
    "sourceKeyList": [],
    "date1": ["2025-01-28", "2025-04-28"],
    "fmWoType": "PM",
    "current": 1,
    "limit": 100,
    "startTime": "2025-01-28 00:00:00",
    "endTime": "2025-04-28 23:59:59",
    "workOrderTypeNoList": ["5"],
    "type": "1",
}

# ── 工单详情 API ───────────────────────────────────────
DETAIL_URL_TPL = (
    "https://heimdallr.onewo.com/api/datacenter/workOrder-etl/api"
    "/workOrder-etl/feign/getFmWorkOrderDetail/{etl_code}"
)

# ── 指派人员列表 API ────────────────────────────────────
ASSIGNEE_LIST_URL = (
    "https://heimdallr.onewo.com/api/task/courier/admin/task"
    "/work-order/assignmentList"
)


def build_assignee_list_body(
    project_code: str,
    workorder_no: str,
    source: str = "02",
) -> dict:
    return {
        "bodyForm": {
            "projectCode": project_code,
            "queryParam": "",
            "workOrderNo": workorder_no,
        },
        "source": source,
    }


# ── 指派 API ───────────────────────────────────────────
ASSIGN_URL = (
    "https://heimdallr.onewo.com/api/task/courier/admin/task"
    "/work-order/assignmentMember"
)


def build_assign_body(
    deal_user_id: str,
    deal_user_mobile: str,
    deal_user_name: str,
    project_code: str,
    workorder_no: str,
    wo_type: str,
    source: str = "02",
) -> dict:
    return {
        "bodyForm": {
            "dealUserId": deal_user_id,
            "dealUserMobile": deal_user_mobile,
            "dealUserName": deal_user_name,
            "projectCode": project_code,
            "workOrderNo": workorder_no,
            "woType": wo_type,
            "deleted": False,
            "optMobile": ASSIGN_OPT_MOBILE,
            "optUserName": ASSIGN_OPT_USER_NAME,
        },
        "source": source,
    }


# ── 项目默认配置 ───────────────────────────────────────
DEFAULT_PROJECT_ID = "52010017"
DEFAULT_SOURCE = "02"

# ── 指派操作人信息（固定值） ────────────────────────────
ASSIGN_OPT_MOBILE = "13639000773"
ASSIGN_OPT_USER_NAME = "胡廷胤"
