# 前端页面

界面用 React、TypeScript 和 Ant Design，结构对齐 datavines-ui 的主框架：左侧深色菜单、右侧白顶栏、内容区。`/login` 与 `/register` 是独立页面。进入 `/main` 前要有本地 JWT。顶栏是工作空间下拉、当前用户和退出，并用健康检查给服务状态打标签。

开发服务器端口 5680。生产镜像里 Nginx 同样监听 5680，Compose 使用 host 网络，页面直接开在这个端口。

## 路由

| 路由 | 菜单或入口 | 做什么 |
| --- | --- | --- |
| `/main/home` | 数据源 | 卡片列表、测试连接、删除、新建 MySQL/Doris、初始化 Demo |
| `/main/detail/:id/dashboard` | 质量概览 | 质量分、通过占比、分数趋势、最近问题 |
| `/main/detail/:id/editor` | 规则作业 | 作业表、新建四类规则、运行 |
| `/main/detail/:id/jobs` | 执行记录 | 实例列表，运行中可终止 |
| `/main/detail/:id/jobExecutionLogs` | 执行日志 | 日志、判定结果、错误样本，2 秒刷新 |
| `/main/detail/:id/catalog` | 数据目录 | 库表列、预览、提交同步、看通用任务 |
| `/main/detail/:id/profile` | 数据概览 | 提交探查、行数柱状图、列指标和直方图 |
| `/main/detail/:id/schema` | Schema 变更 | 变更表、Demo 加列 |
| `/main/detail/:id/lineage` | 血缘 | 一跳上下游、手工加边、从 SQL 解析。不是完整血缘图画布 |
| `/main/warning` | 告警管理 | SLA、飞书发送器、发送记录、测试 |
| `/main/errorDataManage` | 错误数据存储 | MySQL 存储的测试与保存 |
| `/main/label` | 标签管理 | 分类和标签 |
| `/main/config` | 参数配置 | `dv_config` 键值 |
| `/main/env` | 运行环境 | 记录 Spark 等环境变量，不用于真正提交 Spark |
| `/login` | 登录 | 用户名和密码。预置 admin / 123456、user / 123456 |
| `/register` | 注册 | 用户名、邮箱、密码，成功后去登录 |
| `/main/users` | 用户 | 当前工作空间的成员 |
| `/main/tokenManager` | 令牌 | 说明登录 JWT 与指标目录公开 |

数据源详情顶上还有一条横向菜单，对应上游 detail 路由里的 dashboard、editor、jobs、jobExecutionLogs，并补上目录、概览和 Schema，避免从概览去看表时 404。

## 交互约定

- 所有请求走 `/api/v1`。axios 看到 `code !== 200` 会弹出 `msg`。
- 列表空数据用 Ant Design 的 Empty 或表格自带空态，不写占位拉丁文。
- 作业表单按检查类型切换字段：枚举、正则、长度、值域、及时性、自定义 SQL、第二张表只在对应指标下出现。
- 引擎下拉明确写出 spark「仅接口，运行会失败」。
- 窄屏下侧栏仍占 216 像素，内容区可以滚动。这不是独立的移动端应用，但页面不依赖固定的超宽表格才能完成「进入数据源、运行作业」。

## 和上游 UI 的差异

- 顶栏可以切换工作空间并退出。用户页只显示当前空间的成员。
- 血缘没有单独的图画布，接口可用，见目录文档。
- 自定义 SQL 用多行输入框，没有内嵌 Monaco。
- 质量概览把饼图和趋势放在同一页，而不是再套一层仅有 ECharts 的子路由。
