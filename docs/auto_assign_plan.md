# 临时工单自动指派功能 — 开发计划

## 一、功能概述

对每个**首次出现**的临时性工单（OD），后台自动查询详情，解析 `workorderTypeName` 和 `createName` 字段，根据预设规则自动指派给对应部门的接单人。提供全屏管理界面，供用户查看已自动指派的工单历史、配置指派规则。

---

## 二、核心数据流

```
OD查询 → 发现新工单（首次） → 开线程查工单详情
    ├─ workorderTypeName: "公共清洁/楼内公区清洁问题/电梯内部清洁(含沟槽清理)"
    │   └─ 按 "/" 分割 → 取第一段 → "公共清洁" → 映射部门 → "保洁"
    ├─ createName: "张三"
    │   └─ 管家配置查地块 → "11号地" / "6号地"
    └─ 结果: 部门+地块 → 指派给对应接单人
         ├─ 调用现有指派 API
         └─ 记录到自动指派历史
```

### 2.1 workorderTypeName → 部门映射

| workorderTypeName 第一段 | 对应部门 | 启用自动指派 |
|---|---|---|
| 公共清洁 | 保洁 | true |
| 环境绿化 | 绿化 | true |
| 公共秩序 | 安防 | false |
| 其他 | — | false |

### 2.2 createName → 地块映射（管家配置）

通过预设的"管家配置"表，确定每个工单创建人（`createName`）属于哪个地块：

| 创建人（createName） | 所属地块 |
|---|---|
| 赵中婧 | 11号地 |
| 叶小玲 | 11号地 |
| 李如玉 | 11号地 |
| 杨维强 | 6号地 |
| 纪雪婷 | 6号地 |
| 王智勇 | 6号地 |

如果 `createName` 在管家配置中查不到，则**不进行自动指派**，仅记录到日志。

---

## 三、配置文件结构

配置文件目录：`config/`（与 `.config.json`、`ignored.toml` 同级）

### 3.1 `config/assign_config.toml`

```toml
# =====================
# 部门接单人配置
# =====================
[departments]

[departments.保洁]
enabled = true

[departments.保洁.assignees]
[departments.保洁.assignees."11号地"]
name = "张明金"
mobile = "15685306313"
userId = "2076797"

[departments.保洁.assignees."6号地"]
name = "柏万碧"
mobile = "18985106736"
userId = "2078412"

[departments.绿化]
enabled = true

[departments.绿化.assignees]
[departments.绿化.assignees."11号地"]
name = "肖钰琴"
mobile = "15186950839"
userId = "2452500"

[departments.绿化.assignees."6号地"]
name = "肖钰琴"
mobile = "15186950839"
userId = "2452500"

[departments.安防]
enabled = false

[departments.安防.assignees]
[departments.安防.assignees."11号地"]
name = "倪昌飞"
mobile = "15120193103"
userId = "1698342"

[departments.安防.assignees."6号地"]
name = "曾洪熙"
mobile = "18585028903"
userId = "1784302"

# =====================
# 管家配置
# =====================
[[butlers]]
name = "赵中婧"
plot = "11号地"

[[butlers]]
name = "叶小玲"
plot = "11号地"

[[butlers]]
name = "李如玉"
plot = "11号地"

[[butlers]]
name = "杨维强"
plot = "6号地"

[[butlers]]
name = "纪雪婷"
plot = "6号地"

[[butlers]]
name = "王智勇"
plot = "6号地"
```

### 3.2 指派策略

同一部门+地块下仅能有1个接单人

### 3.3 自动指派历史

存储在 `config/auto_assign_history.json`，记录格式：

```json
[
  {
    "workorderNo": "OD20260617001",
    "workorderDescription": "楼道地面清洁",
    "workorderStatusName": "待处理",
    "department": "保洁",
    "plot": "11号地",
    "assigneeName": "赵六",
    "assigneeMobile": "13800138001",
    "acceptTime": "2026-06-17 12:15:30",
    "createName": "张三",
    "workorderTypeName": "公共清洁/楼内公区清洁问题"
  }
]
```

---

## 四、TUI 界面设计

### 4.1 主界面新增入口

在 `TicketMonitorApp` 中增加快捷键 `O`（Assign）：

```python
BINDINGS = [
    # ... 原有绑定
    Binding("o", "open_auto_assign", "自动指派", key_display="O"),
]
```

### 4.2 自动指派全屏界面 `AutoAssignScreen`

**布局**：全屏 Screen，标题 "自动指派管理终端"

- **数据表格**（占大部分空间）：显示已自动指派的工单
  - 列：指派时间 | 工单编号 | 任务描述 | 处理人 | 状态
  - 按指派时间降序排列（最新的在最上面）
  - 支持光标行选择
- **底部提示栏**：快捷键提示

**快捷键**：
| 键 | 功能 |
|---|---|
| Enter | 查看选中工单的详情（复用 DetailScreen） |
| P | 打开配置页（半屏配置模式） |
| Q / Esc | 返回主界面 |
| R | 刷新历史列表 |

### 4.3 配置页面（P 键进入）

**布局**：左半屏是配置面板，右半屏保留工单列表（挤压缩小）

**默认进入"接单人配置"页面**：

左半区：
```
┌─ 接单人配置 ──────────────────────┐
│                                     │
│  [保洁]                             │
│    11号地: 赵六(13800138001)        │
│    6号地:  孙八(13800138003)        │
│                                     │
│  [绿化]  ● 已启用                   │
│    11号地: 吴十(13800138005)        │
│    6号地:  郑一(13800138006)        │
│                                     │
│  [安防]  ○ 已停用                   │
│    11号地: 冯二(13800138007)        │
│                                     │
│  [Tab] 切换管家配置  [Q] 返回       │
└─────────────────────────────────────┘
```

**Tab 键切换到"管家配置"**（左半区内容替换）：

```
┌─ 管家配置 ──────────────────────────┐
│                                      │
│  创建人          所属地块            │
│  ─────────────────────────           │
│  张三             11号地             │
│  李四             6号地              │
│  王五             11号地             │
│  赵大             6号地              │
│                                      │
│  [Tab] 切换接单人配置  [Q] 返回       │
└──────────────────────────────────────┘
```

**等待后续开发**：配置的增删改编辑功能（当前版本仅展示配置内容，支持通过 Tab 切换查看）

---

## 五、自动触发逻辑

### 5.1 触发时机

在 `_run_od_query()` 中，当发现**新工单**（`new_ids`）时，对每个新工单启动一个后台线程执行自动指派流程：

```python
def _run_od_query(self, ...):
    # ... 现有查询逻辑 ...
    new_ids = {...}  # 新出现的工单
    for wo_no in new_ids:
        threading.Thread(
            target=self._auto_assign_single,
            args=(wo_no,),
            daemon=True,
        ).start()
```

### 5.2 自动指派单线程流程

```
_auto_assign_single(wo_no)
  ├─ 1. 查询工单详情 (复用 _fetch_detail 的 API 逻辑)
  │   └─ 获取 workorderTypeName, createName, etlCode 等
  ├─ 2. 解析 workorderTypeName → 部门
  │   ├─ 按 "/" 分割取第一段
  │   └─ 查部门映射表，不在列表中则跳过（仅记录日志）
  ├─ 3. 查管家配置 → 地块
  │   ├─ createName 在 butlers 列表中 → 取 plot
  │   └─ 不在列表中则跳过（仅记录日志）
  ├─ 4. 检查该部门是否启用自动指派
  │   └─ enabled == false → 跳过
  ├─ 5. 调用指派 API (复用 _execute_assign 逻辑)
  │   ├─ build_assign_body(...)
  │   └─ POST ASSIGN_URL
  └─ 6. 记录结果
      ├─ 成功 → 写入 auto_assign_history.json
      └─ 失败 → 记录日志
```

### 5.3 防止重复指派

- `_notified_od_ids` 已经记录首次出现的工单号
- 自动指派成功后，该工单不再触发第二次指派
- 即使指派 API 失败，也**不再重试**（仅记录日志，用户可手动在详情页指派）

---

## 六、需要新建的文件

| 文件 | 说明 |
|---|---|
| `lib/auto_assigner.py` | 自动指派核心逻辑：详情查询、分类、派单、轮询 |
| `lib/config_manager.py` | 配置文件读写：部门配置、管家配置、指派历史 |
| `tui/auto_assign_screen.py` | TUI 全屏自动指派管理界面 + 配置页面 |
| `config/assign_config.toml` | 默认部门接单人配置（首次运行自动创建） |
| `config/butler_config.toml` | 默认管家配置（首次运行自动创建） |
| `config/auto_assign_history.json` | 自动指派历史记录（首次运行自动创建） |

---

## 七、需要修改的文件

| 文件 | 改动 |
|---|---|
| `lib/init_app.py` | 增加 `config/` 目录及默认配置文件的自动初始化 |
| `tui/app.py` | 新增 `O` 键绑定 → `action_open_auto_assign` |
| `tui/app.py` | 在 `_run_od_query` 中增加对新工单的自动指派触发 |

---

## 八、默认初始配置

### 8.1 `config/assign_config.toml`

```toml
# =====================
# 部门接单人配置
# =====================
[departments]

[departments.保洁]
enabled = true

[departments.保洁.assignees]
[departments.保洁.assignees."11号地"]
name = "张明金"
mobile = "15685306313"
userId = "2076797"

[departments.保洁.assignees."6号地"]
name = "柏万碧"
mobile = "18985106736"
userId = "2078412"

[departments.绿化]
enabled = true

[departments.绿化.assignees]
[departments.绿化.assignees."11号地"]
name = "肖钰琴"
mobile = "15186950839"
userId = "2452500"

[departments.绿化.assignees."6号地"]
name = "肖钰琴"
mobile = "15186950839"
userId = "2452500"

[departments.安防]
enabled = false

[departments.安防.assignees]
[departments.安防.assignees."11号地"]
name = "倪昌飞"
mobile = "15120193103"
userId = "1698342"

[departments.安防.assignees."6号地"]
name = "曾洪熙"
mobile = "18585028903"
userId = "1784302"
```

### 8.2 `config/butler_config.toml`

```toml
# =====================
# 管家配置
# =====================
[[butlers]]
name = "赵中婧"
plot = "11号地"

[[butlers]]
name = "叶小玲"
plot = "11号地"

[[butlers]]
name = "李如玉"
plot = "11号地"

[[butlers]]
name = "杨维强"
plot = "6号地"

[[butlers]]
name = "纪雪婷"
plot = "6号地"

[[butlers]]
name = "王智勇"
plot = "6号地"
```

---

## 九、实施步骤

| 步骤 | 内容 | 涉及文件 |
|---|---|---|
| 1 | 实现 `lib/config_manager.py`：读写部门配置、管家配置、指派历史 | 新建 |
| 2 | 实现 `lib/auto_assigner.py`：自动指派核心逻辑 | 新建 |
| 3 | 修改 `lib/init_app.py`：初始化 config 目录和默认配置文件 | `init_app.py` |
| 4 | 实现 `tui/auto_assign_screen.py`：全屏管理界面 + 配置页面 | 新建 |
| 5 | 修改 `tui/app.py`：添加 `O` 键入口、触发自动指派逻辑 | `app.py` |

---

## 十、注意事项

1. **指派 API 的 optMobile / optUserName**：复用现有 `lib.api.ASSIGN_OPT_MOBILE` 和 `ASSIGN_OPT_USER_NAME`（当前为"胡廷胤"）
2. **配置懒加载**：每次进入配置页面时重新读取文件，确保配置实时生效
3. **线程安全**：自动指派线程和轮询索引使用 `threading.Lock` 保护
4. **静默运行**：自动指派过程不在用户日志区域输出过多信息，仅在成功/失败时输出简要日志
5. **配置编辑**：当前版本仅展示配置，编辑功能等待后续迭代实现
