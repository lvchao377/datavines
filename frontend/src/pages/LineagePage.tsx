import { Button, Card, Form, Input, Select, Space, Table, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import http from "../api";

/** Skeleton for table lineage. Parsing is best-effort; the graph is one hop. */
export default function LineagePage() {
  const { id } = useParams();
  const [tables, setTables] = useState<Record<string, any>[]>([]);
  const [focus, setFocus] = useState<string>();
  const [graph, setGraph] = useState<{ nodes: Record<string, any>[]; edges: Record<string, any>[] }>({ nodes: [], edges: [] });
  const [form] = Form.useForm();

  useEffect(() => {
    (async () => {
      const databases = await http.get(`/catalog/databases/${id}`);
      const all: Record<string, any>[] = [];
      for (const db of databases || []) {
        const rows = await http.get(`/catalog/list/table/${db.uuid}`);
        all.push(...(rows || []));
      }
      setTables(all);
      if (all[0]) setFocus(all[0].uuid);
    })();
  }, [id]);

  const load = async (uuid: string) => {
    setGraph(await http.get(`/catalog/lineage/getByUUID/${uuid}`));
  };

  useEffect(() => { if (focus) load(focus); }, [focus]);

  return (
    <div>
      <Typography.Paragraph type="secondary">
        血缘是简化实现：手工指定上游表到下游表，或从 INSERT/SELECT 语句里抽出表名。只展示一跳，不解析复杂子查询。
      </Typography.Paragraph>
      <Space style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 280 }}
          value={focus}
          onChange={setFocus}
          options={tables.map((item) => ({ value: item.uuid, label: item.fullyQualifiedName }))}
          placeholder="选择表"
        />
        <Button onClick={() => focus && load(focus)}>刷新</Button>
      </Space>
      <Card title="一跳关系" size="small">
        <Table
          rowKey={(row) => `${row.from}-${row.to}-${row.type}`}
          dataSource={graph.edges || []}
          locale={{ emptyText: "还没有血缘边" }}
          columns={[
            { title: "从", dataIndex: "from", render: (value: string) => graph.nodes.find((node) => node.uuid === value)?.fqn || value },
            { title: "到", dataIndex: "to", render: (value: string) => graph.nodes.find((node) => node.uuid === value)?.fqn || value },
            { title: "类型", dataIndex: "type" },
            { title: "来源", dataIndex: "sourceType" },
          ]}
        />
      </Card>
      <Card title="添加边" size="small" style={{ marginTop: 12 }}>
        <Form form={form} layout="inline" onFinish={async (values) => {
          await http.post("/catalog/lineage/add", { fromUUID: values.from, toUUID: values.to, sourceType: "manual" });
          message.success("已添加");
          if (focus) load(focus);
        }}>
          <Form.Item name="from" rules={[{ required: true }]}><Select style={{ width: 220 }} placeholder="上游" options={tables.map((item) => ({ value: item.uuid, label: item.fullyQualifiedName }))} /></Form.Item>
          <Form.Item name="to" rules={[{ required: true }]}><Select style={{ width: 220 }} placeholder="下游" options={tables.map((item) => ({ value: item.uuid, label: item.fullyQualifiedName }))} /></Form.Item>
          <Button htmlType="submit" type="primary">保存</Button>
        </Form>
      </Card>
      <Card title="从 SQL 解析" size="small" style={{ marginTop: 12 }}>
        <Form layout="vertical" onFinish={async (values) => {
          const result = await http.post("/catalog/lineage/addByParseSql", { datasourceId: Number(id), sql: values.sql });
          message.success(`写入 ${result.edges} 条边`);
          if (focus) load(focus);
        }}>
          <Form.Item name="sql" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="insert into orders_mirror select * from orders" />
          </Form.Item>
          <Button htmlType="submit">解析并保存</Button>
        </Form>
      </Card>
    </div>
  );
}
