# Screen Memory Plugin - 使用说明

## 概述

Screen Memory 是 OpenClaw 的屏幕记忆插件，提供屏幕捕获、OCR 识别、URI Graph 记忆管理、实体追踪和跨设备同步能力。

**支持平台：** Windows、Android

---

## 记忆管理工具

### memory_write - 写入记忆

向 URI Graph 写入一条记忆。如果 URI 节点不存在会自动创建。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| uri | string | 是 | Nocturne URI，如 `core://my/topic` |
| content | string | 是 | 记忆内容 |

**示例：**
```
写入一条关于项目计划的记忆到 core://project/plan 路径下
```

**返回：**
```json
{"ok": true, "uri": "core://project/plan", "version": 1}
```

---

### memory_read - 读取记忆

读取指定 URI 的最新一条记忆。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| uri | string | 是 | Nocturne URI |
| scope | string | 否 | 查询范围，默认 `local` |

**scope 取值：**
- `local` — 仅查询本机数据
- `remote` — 仅查询其他设备的数据
- `all` — 本机 + 其他设备，优先返回本机

**示例：**
```
读取 core://project/plan 的记忆，scope 设为 all 可以同时看到其他设备的同路径记忆
```

---

### memory_search - 搜索记忆

全文搜索所有记忆内容（基于 FTS5）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 搜索关键词 |
| scope | string | 否 | 查询范围，默认 `local` |

**示例：**
```
搜索包含"项目进度"的所有记忆，设置 scope 为 remote 可以搜索其他设备上的记忆
```

**scope 取值同 memory_read。**

---

### memory_delete - 删除记忆

删除指定 URI 的节点及其所有记忆。此操作仅影响本机数据，不可撤销。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| uri | string | 是 | 要删除的 Nocturne URI |

**示例：**
```
删除 core://project/old-plan 这个节点
```

---

### graph_query_subtree - 查询子树

查询指定 URI 前缀下的所有子节点，返回树形结构。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| uri_prefix | string | 是 | URI 前缀，如 `core://project` |
| max_depth | integer | 否 | 最大遍历深度，默认 10 |
| scope | string | 否 | 查询范围，默认 `local` |

**示例：**
```
查询 core://project 下的所有子节点，最大深度 3，scope 设为 all 查看所有设备的
```

---

## 实体追踪工具

### signal_ingest - 记录信号

为实体追踪系统记录一次信号。系统会根据信号频率和权重自动判断实体是否值得关注。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| entity_type | string | 是 | 实体类型：`person`、`topic`、`location`、`event` |
| entity_name | string | 是 | 实体名称 |
| source | string | 是 | 信号来源：`screenshot`、`ocr`、`manual` 等 |
| evidence | string[] | 否 | 证据文本列表 |

**示例：**
```
记录一个信号：entity_type=person，entity_name=张三，source=screenshot，evidence=["在会议截图中出现"]
```

---

### signal_activate - 激活实体

将候选实体提升为活跃状态，同时将其物化到 URI Graph 中。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| entity_name | string | 是 | 要激活的实体名称 |

**示例：**
```
激活实体"张三"，使其从候选变为活跃状态
```

---

## 截图搜索

### screenshot_search - 搜索截图

根据 OCR 文本内容搜索截图记录。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 搜索关键词 |
| limit | integer | 否 | 最大返回条数，默认 20 |
| scope | string | 否 | 查询范围，默认 `local` |

**示例：**
```
搜索包含"合同"的截图，scope 设为 remote 可以搜索其他设备上的截图
```

---

## Android 专属工具

以下工具仅在 Android 端可用，需要手机上运行 Screen Memory APK 服务。

### screen_capture - 截屏

截取当前手机屏幕，返回图片元信息（不含完整图片数据）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| quality | integer | 否 | JPEG 质量 1-100，默认 80 |

**示例：**
```
截取当前屏幕，质量设为 90
```

---

### screen_ocr - 截屏识别

截取屏幕并执行 OCR，返回识别到的文字和文本块信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| quality | integer | 否 | JPEG 质量，默认 80 |

**示例：**
```
截屏并识别当前屏幕上的文字
```

**返回包含：** `full_text`（完整文字）、`text_blocks`（分块文字+置信度+位置）、`app_package`（当前应用包名）

---

### screen_status - 服务状态

检查手机端 Screen Memory APK 服务是否正在运行。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 无 | | | |

**示例：**
```
检查手机端截屏服务是否就绪
```

---

### screen_index - 一键索引

截屏 + OCR + 存储 + 索引，一步完成完整的屏幕记忆流程。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| uri | string | 否 | 存储到哪个 URI 下，默认 `auto://screenshot` |

**示例：**
```
截屏并自动索引到记忆图中
```

---

## 跨设备同步

### sync_status - 同步状态

查看当前设备的同步状态和服务器上所有已连接设备的信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 无 | | | |

**示例：**
```
查看同步状态，确认服务器连接正常以及哪些设备在线
```

**返回示例：**
```json
{
  "device_id": "windows-my-pc-a3f1",
  "last_sync_time": "2026-05-28 10:30:00",
  "pending_changes": 0,
  "server_reachable": true,
  "devices": [
    {"device_id": "android-localhost-ff07", "last_sync": "2026-05-28 10:29:00", "tables": {"screenshots": 152}},
    {"device_id": "windows-zhengtianying-2e26", "last_sync": "2026-05-28 10:30:00", "tables": {"screenshots": 89}}
  ]
}
```

---

## scope 参数详解

以下工具支持 `scope` 参数，用于跨设备查询：

| 工具 | 支持 scope |
|------|-----------|
| memory_read | local / remote / all |
| memory_search | local / remote / all |
| graph_query_subtree | local / remote / all |
| screenshot_search | local / remote / all |

**scope 工作方式：**

- `local`（默认）— 只查本机 SQLite 数据库，不访问服务器。向后兼容，无网络也能用。
- `remote` — 通过服务器 API 查询其他设备的数据，自动排除本机数据。
- `all` — 先查本机，再查服务器上的其他设备数据，合并去重后返回。

**注意：** 使用 `remote` 或 `all` 需要配置同步服务器（见下方配置说明）。

---

## 跨设备同步配置

### 前提条件

- 已部署同步服务器（FastAPI + SQLite）
- 服务器地址和认证 token 已知

### Windows 配置

设置环境变量：

```bash
export SCREEN_MEMORY_SYNC_URL=http://47.118.19.85:8200
export SCREEN_MEMORY_SYNC_TOKEN=screen-memory-sync-token-2026
export SCREEN_MEMORY_SYNC_INTERVAL=30
```

或在系统环境变量中添加。

### Android 配置

**方式一：** 创建配置文件 `~/.screenmemory/sync.yaml`：

```yaml
url: http://47.118.19.85:8200
token: screen-memory-sync-token-2026
interval: 30
```

**方式二：** 在 `~/.bashrc` 中设置环境变量：

```bash
export SCREEN_MEMORY_SYNC_URL=http://47.118.19.85:8200
export SCREEN_MEMORY_SYNC_TOKEN=screen-memory-sync-token-2026
export SCREEN_MEMORY_SYNC_INTERVAL=30
```

**方式三：** 在 `~/.openclaw/openclaw.json` 的 MCP server 配置中添加 `env` 字段。

### 同步机制

- **后台推送：** 每 30 秒（可配置）自动检测本地数据库变更并推送到服务器
- **退出推送：** 插件退出时自动推送未同步的数据
- **单向推送：** 只推送本机数据到服务器，不下载其他设备数据到本地
- **远程查询：** 需要查看其他设备数据时，通过 scope 参数实时从服务器查询
