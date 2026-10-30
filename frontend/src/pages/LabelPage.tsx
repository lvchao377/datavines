import { Button, Form, Input, Modal, Select, Space, Table, message } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function LabelPage() {
  const [categories, setCategories] = useState<Record<string, any>[]>([]);
  const [tags, setTags] = useState<Record<string, any>[]>([]);
  const [category, setCategory] = useState<string>();
  const [open, setOpen] = useState<"category" | "tag" | null>(null);
  const [form] = Form.useForm();

  const loadCats = () => http.get("/catalog/tag/category/list/1").then(setCategories);
  useEffect(() => { loadCats(); }, []);
  useEffect(() => { if (category) http.get(`/catalog/tag/list-in-category/${category}`).then(setTags); }, [category]);

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button onClick={() => setOpen("category")}>新建分类</Button>
        <Button type="primary" onClick={() => setOpen("tag")}>新建标签</Button>
        <Select style={{ width: 220 }} placeholder="选择分类" value={category} onChange={setCategory} options={categories.map((item) => ({ value: item.uuid, label: item.name }))} />
      </Space>
      <Table rowKey="uuid" dataSource={tags} columns={[{ title: "标签", dataIndex: "name" }, { title: "UUID", dataIndex: "uuid" }]} />
      <Modal title={open === "category" ? "分类" : "标签"} open={!!open} onCancel={() => setOpen(null)} onOk={async () => {
        const values = await form.validateFields();
        if (open === "category") await http.post("/catalog/tag/category", { name: values.name, workspaceId: 1 });
        else await http.post("/catalog/tag", { name: values.name, categoryUuid: values.categoryUuid || category });
        message.success("已保存");
        setOpen(null);
        form.resetFields();
        loadCats();
        if (category) http.get(`/catalog/tag/list-in-category/${category}`).then(setTags);
      }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          {open === "tag" && <Form.Item name="categoryUuid" label="分类"><Select options={categories.map((item) => ({ value: item.uuid, label: item.name }))} /></Form.Item>}
        </Form>
      </Modal>
    </div>
  );
}
