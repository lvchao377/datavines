import { Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import http from "../api";
import { workspaceId } from "../session";

type UserRow = {
  id: number;
  username: string;
  email?: string;
  admin?: boolean;
  workspaces?: { id: number; name: string }[];
};

export default function UsersPage() {
  const [rows, setRows] = useState<UserRow[]>([]);

  const load = () => {
    const current = workspaceId();
    http.get("/user/list", { params: current ? { workspaceId: current } : {} }).then(setRows);
  };

  useEffect(() => {
    load();
    const onSwitch = () => load();
    window.addEventListener("dv-workspace", onSwitch);
    return () => window.removeEventListener("dv-workspace", onSwitch);
  }, []);

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>用户</Typography.Title>
      <Typography.Paragraph type="secondary">这里只列出当前工作空间的成员。注册用户会得到自己的默认工作空间，看不到别人的数据源。</Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={rows}
        pagination={false}
        columns={[
          { title: "用户名", dataIndex: "username" },
          { title: "邮箱", dataIndex: "email" },
          { title: "角色", dataIndex: "admin", render: (admin: boolean) => admin ? <Tag color="blue">管理员</Tag> : <Tag>成员</Tag> },
          { title: "工作空间", render: (_, row) => (row.workspaces || []).map((item) => item.name).join("、") },
        ]}
      />
    </div>
  );
}
