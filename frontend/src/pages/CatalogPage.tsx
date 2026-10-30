import { Button, Card, Descriptions, Drawer, Select, Space, Table, Tag, message } from "antd";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import http from "../api";

export default function CatalogPage() {
  const { id } = useParams();
  const [databases, setDatabases] = useState<Record<string, any>[]>([]);
  const [database, setDatabase] = useState<string>();
  const [tables, setTables] = useState<Record<string, any>[]>([]);
  const [table, setTable] = useState<Record<string, any> | null>(null);
  const [columns, setColumns] = useState<Record<string, any>[]>([]);
  const [preview, setPreview] = useState<Record<string, any> | null>(null);
  const [tasks, setTasks] = useState<Record<string, any>[]>([]);

  const loadDatabases = async () => {
    const rows = await http.get(`/catalog/databases/${id}`);
    setDatabases(rows || []);
    if (rows?.[0]) setDatabase(rows[0].fullyQualifiedName);
  };

  useEffect(() => { loadDatabases(); loadTasks(); }, [id]);

  useEffect(() => {
    const entity = databases.find((item) => item.fullyQualifiedName === database);
    if (!entity) return;
    http.get(`/catalog/list/table/${entity.uuid}`).then(setTables);
  }, [database, databases]);

  const openTable = async (row: Record<string, any>) => {
    setTable(row);
    setColumns(await http.get(`/catalog/list/column/${row.uuid}`));
  };

  const sync = async () => {
    const body = await http.post("/catalog/refresh", { datasourceId: Number(id), database });
    message.success(`已提交元数据采集 #${body.taskId}`);
    setTimeout(loadTasks, 1500);
    setTimeout(loadDatabases, 2000);
  };

  const loadTasks = () => http.get("/common-task/page", { params: { datasourceId: id, pageNumber: 1, pageSize: 8 } }).then((page) => setTasks(page.records || []));

  const showPreview = async () => {
    if (!table) return;
    const [dbName, tableName] = String(table.fullyQualifiedName).split(".");
    setPreview(await http.get(`/datasource/${id}/${dbName}/${tableName}/preview`, { params: { limit: 20 } }));
  };

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Select style={{ width: 220 }} value={database} onChange={setDatabase} options={databases.map((item) => ({ value: item.fullyQualifiedName, label: item.displayName }))} placeholder="选择库" />
        <Button type="primary" onClick={sync}>同步元数据</Button>
        <Button onClick={loadTasks}>刷新任务</Button>
      </Space>
      <Table
        rowKey="uuid"
        dataSource={tables}
        columns={[
          { title: "表", dataIndex: "displayName" },
          { title: "全名", dataIndex: "fullyQualifiedName" },
          { title: "说明", dataIndex: "description" },
          { title: "操作", render: (_, row) => <a onClick={() => openTable(row)}>列</a> },
        ]}
      />
      <Card title="最近采集任务" style={{ marginTop: 16 }} size="small">
        <Table size="small" rowKey="id" pagination={false} dataSource={tasks} columns={[
          { title: "ID", dataIndex: "id" },
          { title: "类型", dataIndex: "taskType" },
          { title: "状态", dataIndex: "status", render: (value: number) => <Tag>{["等待", "运行", "成功", "失败"][value] || value}</Tag> },
          { title: "提交", dataIndex: "submitTime" },
        ]} />
      </Card>
      <Drawer width={720} title={table?.displayName} open={!!table} onClose={() => setTable(null)} extra={<Button onClick={showPreview}>预览数据</Button>}>
        <Table
          rowKey="uuid"
          size="small"
          dataSource={columns}
          pagination={false}
          columns={[
            { title: "列", dataIndex: "displayName" },
            { title: "类型", render: (_, row) => row.properties?.columnType },
            { title: "可空", render: (_, row) => (row.properties?.nullable ? "是" : "否") },
            { title: "注释", dataIndex: "description" },
          ]}
        />
        {preview && (
          <Table
            style={{ marginTop: 16 }}
            size="small"
            rowKey={(_, index) => String(index)}
            dataSource={preview.records}
            columns={(preview.columns || []).map((col: string) => ({ title: col, dataIndex: col }))}
            scroll={{ x: true }}
          />
        )}
        {table && <Descriptions style={{ marginTop: 12 }}><Descriptions.Item label="UUID">{table.uuid}</Descriptions.Item></Descriptions>}
      </Drawer>
    </div>
  );
}
