# 前端页面

界面用 React、TypeScript 和 Ant Design，结构对齐 datavines-ui 的主框架：左侧深色菜单、右侧白顶栏、内容区。不提供登录、注册、忘记密码页面；访问 `/`、`/login`、`/register` 都会进 `/main/home`。顶栏固定显示工作空间 `admin's default` 和用户 `admin`，并用健康检查给服务状态打标签。

开发服务器端口 5680。生产镜像里 Nginx 监听 80，Compose 映射到宿主机 5680。

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
| `/main/warning` | 告警管理 | SLA、飞书发送器、发送记录、测试 |
| `/main/errorDataManage` | 错误数据存储 | MySQL 存储的测试与保存 |
| `/main/label` | 标签管理 | 分类和标签 |
| `/main/config` | 参数配置 | `dv_config` 键值 |
| `/main/env` | 运行环境 | 记录 Spark 等环境变量，不用于真正提交 Spark |
| `/main/tokenManager` | 令牌 | 说明鉴权已关闭 |

数据源详情顶上还有一条横向菜单，对应上游 detail 路由里的 dashboard、editor、jobs、jobExecutionLogs，并补上目录、概览和 Schema，避免从概览去看表时 404。

## 交互约定

- 所有请求走 `/api/v1`。axios 看到 `code !== 200` 会弹出 `msg`。
- 列表空数据用 Ant Design 的 Empty 或表格自带空态，不写占位拉丁文。
- 作业表单按检查类型切换字段：枚举、正则、长度、值域、及时性、自定义 SQL、第二张表只在对应指标下出现。
- 引擎下拉明确写出 spark「仅接口，运行会失败」。
- 窄屏下侧栏仍占 216 像素，内容区可以滚动。这不是独立的移动端应用，但页面不依赖固定的超宽表格才能完成「进入数据源、运行作业」。

## 和上游 UI 的差异

- 没有工作空间切换、用户管理、注册。
- 血缘没有单独的图画布，接口可用，见目录文档。
- 自定义 SQL 用多行输入框，没有内嵌 Monaco。
- 质量概览把饼图和趋势放在同一页，而不是再套一层仅有 ECharts 的子路由。
