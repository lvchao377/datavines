# 作业调度

## 业务背景

质量检查和元数据采集都需要按钟点重复，而不只靠人去点「运行」。上游用 Quartz，表脚本里也有 `QRTZ_*`。本实现是单机，不再嵌入 Quartz：Cron 存在 `dv_job_schedule` 和 `dv_common_task_schedule`，由进程内线程用 croniter 判断是否到点，到点后写入命令表，由同一进程的工作线程抢走执行。这样仍然满足「先入命令队列、再执行」的原版链路，只是没有多节点选主。

## 核心功能点

- 为质量作业创建或更新一条调度：类型、Cron、起止时间、启用状态。
- 校验 Cron，并列出接下来若干次触发时间。
- 支持 5 位标准 Cron（分 时 日 月 周）和 6 位 Quartz Cron（秒在前）。7 位表达式会丢掉末尾的年。`?` 会换成 `*`。
- 通用任务调度：`CATALOG_METADATA`（目录同步）和 `DATA_PROFILE`（探查），挂在数据源上。
- 手动运行也会写 `dv_command`，和到点触发走同一条工人线程。

## 关键业务规则

- `dv_job_schedule.status = 1` 才参与扫描，0 为停用。接口把 `true` / `"online"` 也当成启用。
- 若当前时间早于 `start_time` 或晚于 `end_time`，本次跳过。
- 判定「到点」的窗口大约是调度扫描间隔再加 5 秒（默认扫描 20 秒）。同一作业如果 70 秒内已经有提交记录，不再重复入队，避免扫描重叠打出两份实例。
- 通用任务用同样的 70 秒去重，键是数据源加任务类型。
- 进程重启时，状态仍为「运行中」的作业实例和通用任务会被标成失败。单机没有别的节点会把它们跑完，留着运行中只会让界面一直转圈。
- 调度线程和执行线程都是 daemon。`ENABLE_WORKER=false` 时不启动它们，便于测试自己调用 `run_execution`。

## 数据流转过程

1. 用户在作业表单里填写 Cron，或稍后 `POST /api/v1/job/schedule/createOrUpdate`。
2. 每 20 秒 `scheduler._tick_schedules` 读取 `status=1` 的行，用 croniter 取上一次触发点。
3. 到点且没有近期实例时，`submit_execution` 插入 `dv_job_execution`（状态 0 已提交），再插入 `dv_command`（type=0 启动，priority=2），然后唤醒工人。
4. 工人 `SELECT ... FOR UPDATE SKIP LOCKED` 取一条命令，删除命令，调用 `run_execution`。停止命令 type=1、priority=0，会先于启动命令被拿走，并关闭正在用的连接。
5. 通用任务同理：插入 `dv_common_task` 和 `dv_common_task_command`，工人调用目录同步或探查。

## 前后端对应的接口和页面

调度没有单独的顶级菜单。质量作业的 Cron 在 `/main/detail/:id/editor` 的新建表单里。通用任务的提交按钮在目录页和概览页，任务历史在目录页底部。

| 动作 | 接口 |
| --- | --- |
| 保存作业调度 | `POST /job/schedule/createOrUpdate` |
| 查看作业调度 | `GET /job/schedule/{jobId}` |
| 校验 Cron | `POST /job/schedule/cron` |
| 未来触发点 | `POST /job/schedule/cron/future/list` |
| 保存通用任务调度 | `POST /common-task/schedule` |
| 通用任务历史 | `GET /common-task/page` |
| 通用调度列表 | `GET /common-task/schedule/page` |

## 使用示例

每天 02:10 跑作业 1，Quartz 风格把秒写在最前：

```http
POST /api/v1/job/schedule/createOrUpdate
{"jobId":1,"type":"cycle","cronExpression":"0 10 2 * * ?","status":1}
```

等价的 5 位表达式是 `10 2 * * *`。查看下一次：

```http
POST /api/v1/job/schedule/cron/future/list
{"cronExpression":"10 2 * * *","count":3}
```

每小时同步数据源 1 的目录：

```http
POST /api/v1/common-task/schedule
{
  "taskType": "CATALOG_METADATA",
  "type": "cycle",
  "datasourceId": 1,
  "cronExpression": "0 * * * *",
  "status": 1,
  "param": {"database": "demo"}
}
```

手动触发不等 Cron：`POST /api/v1/catalog/refresh`，体为 `{"datasourceId":1,"database":"demo"}`，返回 `taskId`。
