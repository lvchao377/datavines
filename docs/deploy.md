# 部署和启动

## 业务背景

平台要在一台机器上跑起来：元数据库、API、页面。不依赖 Hadoop、ZooKeeper 或登录服务。Docker Compose 把这三件事按固定端口拉起，并在后端启动时自动建表、灌入上游那批系统配置，再创建 Demo 库和两条能跑的质量作业。

## 用 Docker Compose

需要 Docker Engine 与 Compose v2。在仓库根目录：

```bash
docker compose up --build
```

| 服务 | 容器端口 | 宿主机 | 说明 |
| --- | --- | --- | --- |
| frontend | 80 | **5680** | 页面。浏览器打开 `http://127.0.0.1:5680` |
| backend | 5600 | **5600** | API。健康检查 `http://127.0.0.1:5600/api/v1/health` |
| mysql | 3306 | **33306** | 元数据库 `datavines`，root 密码 `datavines` |

后端环境变量：

- `DATABASE_URL=mysql+pymysql://root:datavines@mysql:3306/datavines?charset=utf8mb4`
- `AUTO_BOOTSTRAP_DEMO=true`：启动后创建 `demo` 库、`orders` / `orders_mirror`、数据源 `demo-mysql`、作业 `demo_email_null_check` 与 `demo_orders_row_count`、飞书 mock SLA。
- `ENABLE_WORKER=true`：启动命令工人和 Cron 扫描。

MySQL 健康之后后端才启动。后端会重试最多约一分钟执行 Alembic。前端 Nginx 把 `/api/` 反代到 `backend:5600`，所以页面和接口同源，没有跨域问题。

停掉并保留数据卷：`docker compose down`。连数据一起删：`docker compose down -v`。

## 不用 Docker 的本地运行

适合已经有 MySQL 或 MariaDB 的开发机。创建库和账号：

```sql
CREATE DATABASE datavines CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'datavines'@'127.0.0.1' IDENTIFIED BY 'datavines';
GRANT ALL PRIVILEGES ON *.* TO 'datavines'@'127.0.0.1';
```

后端：

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL='mysql+pymysql://datavines:datavines@127.0.0.1:3306/datavines?charset=utf8mb4'
uvicorn app.main:app --host 0.0.0.0 --port 5600
```

首次启动执行 Alembic 版本 `0001_initial`（按 SQLAlchemy 模型建 `dv_*` 表），再执行 `scripts/sql/datavines-mysql.sql` 里的 `dv_config`、`dv_user`、`dv_workspace` 插入。默认用户 `admin`，工作空间名是 `admin's default`。

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 监听 **5680**，把 `/api` 代理到 `127.0.0.1:5600`。

测试：

```bash
cd backend
pytest -q
```

没有元数据库时，依赖 MySQL 的 `test_flow.py` 会跳过；指标 SQL、公式、SQLite 执行和表结构对比仍然会跑。

## Demo 路径（不需要第二台数据库）

1. 打开 `http://127.0.0.1:5680`。没有登录页。
2. 若卡片里还没有 `demo-mysql`，点「初始化 Demo」。Compose 已设置自动引导时，这个按钮是幂等的。
3. 进入数据源 →「规则作业」。
4. 运行 `demo_email_null_check`：执行成功，结果未通过，实际值 1，错误样本里有空邮箱，告警页能看到飞书 mock 记录。
5. 运行 `demo_orders_row_count`：实际值 8，结果通过，分数 100。
6. 「数据目录」点同步；「数据概览」对 `demo.orders` 跑探查；「Schema 变更」可点「模拟 Demo 变更」给 `orders` 加 `note` 列。

从宿主机用客户端连元数据库看 Demo 表：主机 `127.0.0.1`，端口 **33306**（Compose）或 **3306**（本机安装），库 `demo`，账号与元数据库相同。

## 配置项

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+pymysql://datavines:datavines@127.0.0.1:3306/datavines?charset=utf8mb4` | 元数据库 |
| `AUTO_BOOTSTRAP_DEMO` | false | 启动时创建 Demo |
| `ENABLE_WORKER` | true | 命令队列与 Cron |
| `DATAVINES_SQL_PATH` | 自动查找 `scripts/sql/datavines-mysql.sql` | 种子 SQL |

日志目录固定为 `/tmp/datavines/logs`。接口文档由 FastAPI 生成：`http://127.0.0.1:5600/docs`。
