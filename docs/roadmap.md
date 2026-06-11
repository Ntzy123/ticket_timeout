# 开发路线图

### 1. 指派功能

-    指派页面选择人员后弹出提示，确认是否将该工单指派给 XXX（手机号），按下回车或Y确认，ESC或Q取消返回

-   后续提供真正的指派 API URL 和 body 格式后，可以直接用 `_selected_ticket` 和 `_selected_assignee` 来发起指派请求。
    -   1. 指派API
        
        -   指派URL：`https://heimdallr.onewo.com/api/task/courier/admin/task/work-order/assignmentMember`
        -   请求方法：POST
        -   请求头，使用TicketMonitorApp里的self._api_headers
        -   指派请求体：{
              "bodyForm": {
                "dealUserId": "1702071",
                "dealUserMobile": "18085009482",
                "dealUserName": "李海波",
                "projectCode": "52010017",
                "workOrderNo": "815460635530309",
                "woType": "PM",
                "deleted": false,
                "optMobile": "13639000773",
                "optUserName": "胡廷胤"
              },
              "source": "02"
            }
        -   以上请求体所需要的参数都可以在之前获取指派人员的API，和工单详情的API中获得，并填入
        -   指派响应体：{
              "isOk": true,
              "msg": null,
              "cause": null,
              "code": "200",
              "data": "指派成功！！！"
            }
        
    -   2. 指派成功提示
    
        -   指派成功提示：`指派成功`
    
        -   指派失败提示：`指派失败，请稍后重试`