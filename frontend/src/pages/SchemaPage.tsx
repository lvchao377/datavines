import { Button, Space, Table, Tag, message } from "antd";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import http from "../api";

export default function SchemaPage() {
  const { id } = useParams();
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const load = () => http.get("/catalog/page/schema-change", { params: { datasourceId: id, pageNumber: 1, pageSize: 100 } }).then((page) => setRows(page.records || []));
  useEffect(() => { load(); }, [id]);
  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button onClick={load}>刷新</Button>
        <Button onClick={async () => { await http.post("/demo/schema-change"); message.success("已尝试给 demo.orders 增加 note 列并重新采集"); load(); }}>模拟 Demo 变更</Button>
      </Space>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "类型", dataIndex: "changeType", render: (value: string) => <Tag>{value}</Tag> },
          { title: "库", dataIndex: "databaseName" },
          { title: "表", dataIndex: "tableName" },
          { title: "列", dataIndex: "columnName" },
          { title: "变更前", dataIndex: "changeBefore" },
          { title: "变更后", dataIndex: "changeAfter" },
          { title: "时间", dataIndex: "updateTime" },
        ]}
      />
    </div>
  );
}
