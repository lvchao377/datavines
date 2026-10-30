# 数据源管理

## 业务背景

质量检查、目录采集和数据概览都要先知道「去哪张库上跑 SQL」。数据源是平台里的连接定义，不是业务表本身。上游 DataVines 把连接器做成插件，本实现只把 MySQL 和 Doris 做成能真正连上的插件，其它类型留在列表里告诉使用者尚未实现，避免配了一个永远连不上的源还以为是网络问题。

Doris 在这里按 MySQL 协议访问 FE 的查询端口（常见是 9030）。元数据查询用 `information_schema`，因此同一套浏览库表列的代码可以服务两种类型。

## 核心功能点

- 登记、修改、删除数据源，名称在 `dv_datasource.name` 上唯一。
- 保存前可单独测试连接（`SELECT 1`）。
- 浏览库、表、列，并预览前 N 行。
- 在数据源上执行一条只读 SQL（SELECT / WITH / SHOW / DESC），自动补 `LIMIT`。
- 页面提供「初始化 Demo」：在元数据库同一台 MySQL 上创建 `demo` 库、样例表、名为 `demo-mysql` 的数据源、两条质量作业和一条飞书 SLA。

连接参数存在 `dv_datasource.param` 文本列，内容是 JSON。列表接口把密码打成 `******`，按 id 查询时返回原文，方便编辑。本系统没有鉴权，这个取舍写在令牌页上。

## 关键业务规则

- `type` 只能是 `mysql` 或 `doris`。其它值在 `validate_param` 里直接拒绝。
- `host` 只允许字母、数字、点、下划线和连字符。`database` 若填写，只能是普通标识符。
- 未填端口时 MySQL 用 3306，Doris 用 9030。
- 浏览库时跳过 `information_schema`、`mysql`、`performance_schema`、`sys`。
- 预览和 `/datasource/execute` 拒绝多语句，也拒绝 INSERT/UPDATE/DELETE。作业里的前置、后置 SQL 不走这个接口，由执行器按分号拆开执行。
- 工作空间固定为 1。请求里的 `workspaceId` 会写入行，但不会做权限过滤之外的隔离。

## 数据流转过程

1. 前端把表单收成 `{name, type, param}`，`POST /api/v1/datasource`。
2. 后端校验类型和参数，计算并不落库密码的 MD5（上游有 `param_code` 列，本实现允许为空），插入 `dv_datasource`。
3. 用户点「进入」后，前端用数据源 id 拉库表。后端用参数拼出 `mysql+pymysql://...`，查 `information_schema`，用完即 `dispose` 连接池。
4. 目录同步和作业执行复用同一套参数解析，所以数据源改密码后，下一次采集和检查会用新密码，不必改作业。
5. Demo 引导另外做一件事：用元数据库账号 `CREATE DATABASE demo`，灌入 `orders` 与 `orders_mirror`，再插入数据源行并同步目录。Docker 里元数据库主机名是 `mysql`，因此 Demo 数据源的 host 也是 `mysql`，后端容器能连上，浏览器不用直连数据库。

## 前后端对应的接口和页面

| 页面 | 路由 | 接口 |
| --- | --- | --- |
| 数据源卡片 | `/main/home` | `GET /datasource/page`、`POST /datasource`、`POST /datasource/test`、`DELETE /datasource/{id}`、`POST /demo/bootstrap` |
| 类型与表单字段 | 新建弹窗 | `GET /datasource/type/list`、`GET /datasource/config/{type}` |
| 数据源详情各页 | `/main/detail/:id/*` | `GET /datasource/{id}` |
| 目录里的预览 | `/main/detail/:id/catalog` | `GET /datasource/{id}/{database}/tables`、`.../columns`、`.../preview` |
| 只读 SQL | 供脚本或调试 | `POST /datasource/execute` |

## 使用示例

在 Compose 网络里登记那台元数据库上的 demo 库（若还没点「初始化 Demo」）：

```http
POST /api/v1/datasource
Content-Type: application/json

{
  "name": "demo-mysql",
  "type": "mysql",
  "workspaceId": 1,
  "param": {
    "host": "mysql",
    "port": 3306,
    "database": "demo",
    "user": "root",
    "password": "datavines"
  }
}
```

本机不用 Docker、元数据库在 `127.0.0.1:3306` 时，把 `host` 改成 `127.0.0.1`，用户改成实际账号。测试连接：

```http
POST /api/v1/datasource/test
{"type":"mysql","param":{"host":"127.0.0.1","port":3306,"user":"datavines","password":"datavines","database":"demo"}}
```

成功时 `data` 为 `true`。Doris 把 `type` 改成 `doris`、`port` 改成 FE 查询端口即可，参数字段相同。

预览：

```http
GET /api/v1/datasource/1/demo/orders/preview?limit=20
```
