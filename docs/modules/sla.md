# SLA 告警

## 业务背景

质量未通过如果只躺在报告里，值班的人不会知道。上游的 SLA 把「哪些作业」和「用哪个发送器通知」分开配置：SLA 是一张告警策略，`dv_sla_job` 把它挂到作业，`dv_sla_sender` 保存渠道账号，`dv_sla_notification` 把策略和发送器连起来。本实现保留这四张表，渠道只做飞书机器人 Webhook。

没有外网、也没有真实飞书群时，可以把 Webhook 指到本服务的 mock 地址。执行器发现地址里包含 `/api/v1/sla/mock/receive`，或是 `mock://` 开头，就在进程内记一条成功发送，不发起 HTTP。这样 Demo 和自动化测试不依赖飞书开放平台。

## 核心功能点

- 维护 SLA、飞书发送器、通知绑定、作业绑定。
- 对单个发送器或整条 SLA 发测试消息。
- 作业质量未通过或执行失败时，找出该作业的全部 SLA，逐个通知其发送器。
- 每次尝试写入 `dv_alert_send_log`（扩展表）：渠道、Webhook、标题、正文、是否成功、响应摘录。告警页读取最近 50 条。

## 关键业务规则

- 发送器 `type` 必须是飞书。其它类型在创建接口返回「仅支持飞书」，执行时若历史数据不是飞书，日志写「未实现」并跳过。
- 配置 JSON 认 `webhook` 或 `url`。空地址记失败，原因为「webhook 为空」。
- 真正的 HTTP 使用飞书 `msg_type=post` 的中文富文本。HTTP 状态码小于 300 且响应 JSON 里的 `code` 不是非零，才算成功。网络异常记在 `response_body`，不让整个质量作业回滚。告警发送发生在结果已写入之后。
- 作业没有 SLA 绑定时，只打日志「跳过飞书通知」，仍然会写 Issue。
- 一个作业可以挂多个 SLA，一个 SLA 可以有多条通知。都会发。
- 测试发送同样落审计日志，`job_id` 为空。

## 数据流转过程

1. 在告警页创建发送器，Webhook 填真实地址或 `http://127.0.0.1:5600/api/v1/sla/mock/receive`。Docker 网络里如果后端要回调自己，用 `http://127.0.0.1:5600/...` 即可，因为 mock 并不真的打回环，执行器在进程内直接记账。
2. 创建 SLA，选择发送器和作业。后端写 `dv_sla`、`dv_sla_notification`、`dv_sla_job`。
3. 作业跑完且未通过时，`runner._notify` 加载这些行，调用 `send_feishu`，写 `dv_alert_send_log`。
4. 告警页 `GET /sla/mock/messages` 同时返回内存收件箱和数据库日志。重启后内存清空，数据库还在。

## 前后端对应的接口和页面

页面路由是 `/main/warning`，菜单名「告警管理」。

| 动作 | 接口 |
| --- | --- |
| SLA 列表 / 创建 | `GET /sla/page`、`POST /sla`、`PUT /sla`、`GET /sla/{id}`、`DELETE /sla/{id}` |
| 发送器 | `POST /sla/sender`、`PUT /sla/sender`、`GET /sla/sender/list`、`GET /sla/sender/page`、`DELETE /sla/sender/{id}`、`POST /sla/sender/test` |
| 支持的渠道与表单 | `GET /sla/plugin/support`、`GET /sla/sender/config/feishu` |
| 通知 | `POST /sla/notification`、`PUT /sla/notification`、`DELETE /sla/notification/{id}`、`GET /sla/notification/page` |
| 挂作业 | `POST /sla/job/createOrUpdate`、`GET /sla/job/list?slaId=`、`GET /sla/job/{jobId}`、`DELETE /sla/job/{id}` |
| 测试整条 SLA | `GET /sla/test/{slaId}` |
| mock 与审计 | `POST /sla/mock/receive`、`GET /sla/mock/messages` |

## 使用示例

```http
POST /api/v1/sla/sender
{
  "name": "demo-feishu-mock",
  "type": "feishu",
  "workspaceId": 1,
  "config": {"webhook": "http://127.0.0.1:5600/api/v1/sla/mock/receive"}
}
```

```http
POST /api/v1/sla
{"name":"demo-null-sla","description":"邮箱空值失败时通知","workspaceId":1}
```

假设返回的 SLA id 是 1、发送器 id 是 1、作业 id 是 1：

```http
POST /api/v1/sla/notification
{"slaId":1,"senderId":1,"type":"feishu","config":{"atAll":false}}

POST /api/v1/sla/job/createOrUpdate
{"slaId":1,"jobId":1,"workspaceId":1}
```

然后跑作业 1。未通过后 `GET /api/v1/sla/mock/messages` 能看到 `success=1`、`responseBody` 为 `mock webhook accepted`。Demo 引导会自动建好这一套，挂在 `demo_email_null_check` 上。
