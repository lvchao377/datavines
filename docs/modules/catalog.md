# 数据目录（Catalog）

## 业务背景

目录把「库、表、列」收成可以检索、打标签、看变更、挂质量作业的实体，而不是每次都去业务库现查。上游用 `dv_catalog_entity_instance` 存实体，用 `dv_catalog_entity_rel` 存父子和血缘，用 `dv_catalog_schema_change` 记结构变化，用标签分类和标签两张表做标注。本实现覆盖这些能力。血缘解析是简化版：用正则找 FROM / JOIN / INSERT INTO，不保证覆盖所有 SQL 方言。

## 核心功能点

- 全量或单库同步。首次同步会为每个新库、新表、新列写一条 `*_ADDED` 变更，这样目录从空到有的过程本身可追溯。
- 再次同步时比较列的 `columnType`。类型变了记 `COLUMN_TYPE_CHANGED`，列或表消失记 `*_DELETED`，并把实体 `status` 改成 `deleted-` 加随机后缀。上游用这个后缀而不是物理删除，是为了躲开 `(datasource_id, fully_qualified_name, status)` 的唯一约束，本实现保持同样做法。
- 表、列上可以挂标签。标签属于某个分类，分类属于工作空间。
- 质量作业保存时，若对应库/表/列实体已存在，写入 `dv_catalog_entity_metric_job_rel`。
- 血缘：手工添加 `downstream` 边，或解析 SQL 后添加。查询某个实体的一跳邻居。
- Demo 可以执行 `ALTER TABLE demo.orders ADD COLUMN note`，再同步，用于演示 `COLUMN_ADDED`。

## 关键业务规则

- 全名：库是 `demo`，表是 `demo.orders`，列是 `demo.orders.email`。展示名是最后一段。
- 父子关系的 `type` 为 `child`：`entity1` 是父，`entity2` 是子。查询某库下的表就是找这种边。
- 血缘边的 `type` 为 `downstream`：`entity1` 是上游，`entity2` 是下游。不写反向的 upstream 行，查询时把两端都算进图。
- 只同步 `BASE TABLE`，跳过系统库。
- 列属性 JSON 含 `dataType`、`columnType`、`nullable`、`comment`、`position`、`columnKey`。概览用 `dataType` 选指标。
- 解析 SQL 时，`INSERT INTO 目标 SELECT ... FROM 源` 会把源指向目标。没有 INSERT 时，按 FROM/JOIN 出现顺序把前一张表指到后一张。匹配不到目录实体的表名会被丢掉，所以要先同步。
- 通用任务 `CATALOG_METADATA` 失败时，错误文本写进任务 `parameter`，状态为 3。成功为 2，运行为 1，等待为 0。

## 数据流转过程

1. 目录页点「同步元数据」，`POST /catalog/refresh` 入队。需要立刻看结果时用 `POST /catalog/refresh/sync`，它在请求线程里跑完并返回 `{added, deleted, changed}`。Demo 引导走的是同步版本。
2. 采集器打开业务库，拉库、表、列。内存里先对已有 active 实体的 properties 做快照，再更新行，最后用快照和最新 `columnType` 比较。这样不会把「刚写进去的新类型」和自己比。
3. 前端用 `GET /catalog/databases/{datasourceId}` 列库，再用父实体 uuid 拉子表、子列。
4. 点预览时不读目录里的样本，而是回业务库 `SELECT * LIMIT n`。目录不保存业务数据。
5. Schema 页按数据源过滤变更：先找出该源全部实体 uuid，再查变更表。

## 前后端对应的接口和页面

| 页面 | 路由 | 接口 |
| --- | --- | --- |
| 数据目录 | `/main/detail/:id/catalog` | `GET /catalog/databases/{id}`、`GET /catalog/list/table/{uuid}`、`GET /catalog/list/column/{uuid}`、`POST /catalog/refresh`、`GET /common-task/page`、预览走数据源接口 |
| Schema 变更 | `/main/detail/:id/schema` | `GET /catalog/page/schema-change`、`POST /demo/schema-change` |
| 标签 | `/main/label` | `POST /catalog/tag/category`、`GET /catalog/tag/category/list/{workspaceId}`、`POST /catalog/tag`、`GET /catalog/tag/list-in-category/{uuid}`、`POST /catalog/tag/entity-tag` |
| 血缘 | 当前 UI 未单独做图，接口可用 | `GET /catalog/lineage/getByUUID/{uuid}`、`POST /catalog/lineage/add`、`POST /catalog/lineage/addByParseSql`、`DELETE /catalog/lineage/{from}/{to}` |

实体详情：`GET /catalog/detail/{uuid}`，附带标签。某实体相关变更：`GET /catalog/list/schema-change/{uuid}`。

## 使用示例

同步并阅读变更：

```http
POST /api/v1/catalog/refresh/sync
{"datasourceId":1,"database":"demo"}
```

```http
GET /api/v1/catalog/page/schema-change?datasourceId=1&pageNumber=1&pageSize=20
```

给列打标签。先建分类和标签，再绑定实体 uuid：

```http
POST /api/v1/catalog/tag/category
{"name":"敏感级别","workspaceId":1}

POST /api/v1/catalog/tag
{"name":"邮箱","categoryUuid":"<分类 uuid>"}

POST /api/v1/catalog/tag/entity-tag
{"entityUuid":"<列 uuid>","tagUuid":"<标签 uuid>"}
```

从 SQL 补一条血缘（表必须已经在目录里）：

```http
POST /api/v1/catalog/lineage/addByParseSql
{"datasourceId":1,"sql":"insert into orders_mirror select * from orders"}
```

成功时 `data.edges` 大于 0。`GET /catalog/lineage/getByUUID/{orders的uuid}` 返回 `nodes` 和 `edges`。
