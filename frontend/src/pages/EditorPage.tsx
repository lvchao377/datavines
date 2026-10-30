import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import http from "../api";

const CHECKS = [
  { value: "column", label: "单表列检查", jobType: 0 },
  { value: "custom", label: "单表自定义 SQL", jobType: 0 },
  { value: "accuracy", label: "跨表准确性", jobType: 2 },
  { value: "comparison", label: "两表值比对", jobType: 2 },
];

export default function EditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [open, setOpen] = useState(false);
  const [metrics, setMetrics] = useState<{ label: string; value: string }[]>([]);
  const [expected, setExpected] = useState<{ label: string; value: string }[]>([]);
  const [formulas, setFormulas] = useState<{ label: string; value: string }[]>([]);
  const [operators, setOperators] = useState<{ label: string; value: string }[]>([]);
  const [databases, setDatabases] = useState<string[]>([]);
  const [tables, setTables] = useState<{ name: string }[]>([]);
  const [columns, setColumns] = useState<{ name: string }[]>([]);
  const [tables2, setTables2] = useState<{ name: string }[]>([]);
  const [form] = Form.useForm();
  const [scheduleForm] = Form.useForm();
  const [scheduleJob, setScheduleJob] = useState<number | null>(null);
  const checkType = Form.useWatch("checkType", form);
  const engineType = Form.useWatch("engineType", form);
  const database = Form.useWatch("database", form);
  const table = Form.useWatch("table", form);

  const load = () => http.get("/job/page", { params: { datasourceId: id, pageNumber: 1, pageSize: 100 } }).then((page) => setRows(page.records || []));

  useEffect(() => {
    load();
    http.get("/metric/resultFormula/list").then(setFormulas);
    http.get("/metric/operator/list").then(setOperators);
    http.get(`/datasource/${id}/databases`).then(setDatabases).catch(() => setDatabases([]));
  }, [id]);

  useEffect(() => {
    if (!database) return;
    http.get(`/datasource/${id}/${database}/tables`).then(setTables).catch(() => setTables([]));
    http.get(`/datasource/${id}/${database}/tables`).then(setTables2).catch(() => setTables2([]));
  }, [database, id]);

  useEffect(() => {
    if (!database || !table) return;
    http.get(`/datasource/${id}/${database}/${table}/columns`).then(setColumns).catch(() => setColumns([]));
  }, [database, table, id]);

  const onCheck = async (value: string) => {
    if (value === "custom") {
      setMetrics([
        { label: "自定义聚合SQL", value: "custom_aggregate_sql" },
        { label: "自定义统计SQL", value: "custom_count_sql" },
      ]);
      const list = await http.get("/metric/expectedValue/list/DATA_QUALITY");
      setExpected(list);
    } else if (value === "accuracy") {
      setMetrics([{ label: "跨表准确性检查", value: "multi_table_accuracy" }]);
      form.setFieldValue("metricType", "multi_table_accuracy");
      setExpected(await http.get("/metric/expectedValue/list/DATA_RECONCILIATION"));
    } else if (value === "comparison") {
      setMetrics([{ label: "两表值比对", value: "multi_table_value_comparison" }]);
      form.setFieldValue("metricType", "multi_table_value_comparison");
      setExpected(await http.get("/metric/expectedValue/list/DATA_RECONCILIATION"));
    } else {
      const column = await http.get("/metric/quality/list/column");
      const tableLevel = await http.get("/metric/quality/list/table");
      setMetrics([...column, ...tableLevel]);
      setExpected(await http.get("/metric/expectedValue/list/DATA_QUALITY"));
    }
  };

  const save = async () => {
    const values = await form.validateFields();
    const check = CHECKS.find((item) => item.value === values.checkType);
    const parameter = {
      metricType: values.metricType,
      metricParameter: {
        database: values.database,
        table: values.table,
        column: values.column,
        filter: values.filter,
        enum_list: values.enum_list,
        regexp: values.regexp,
        comparator: values.comparator,
        length: values.length,
        min: values.min,
        max: values.max,
        begin_time: values.begin_time,
        deadline_time: values.deadline_time,
        datetime_format: values.datetime_format || "yyyy-MM-dd HH:mm:ss",
        actual_aggregate_sql: values.actual_aggregate_sql,
        actual_execute_sql: values.actual_execute_sql,
        table2: values.table2,
        column2: values.column2,
        filter2: values.filter2,
        join_column: values.join_column,
        compare_column: values.compare_column,
        compare_metric: values.compare_metric,
      },
      expectedType: values.expectedType,
      expectedParameter: { expected_value: values.expected_value },
      resultFormula: values.resultFormula,
      operator: values.operator,
      threshold: values.threshold,
    };
    await http.post("/job", {
      name: values.name,
      type: check?.jobType ?? 0,
      datasourceId: Number(id),
      schemaName: values.database,
      tableName: values.table,
      columnName: values.column,
      metricType: values.metricType,
      engineType: values.engineType || "local",
      parameter,
      retryTimes: values.retryTimes || 0,
      retryInterval: values.retryInterval || 1,
      timeout: values.timeout || 600,
      preSql: values.preSql,
      postSql: values.postSql,
      cronExpression: values.cronExpression,
      isErrorDataOutputToDatasource: Boolean(values.errorOutput),
      errorDataOutputToDatasourceDatabase: values.database,
    });
    message.success("作业已保存");
    setOpen(false);
    form.resetFields();
    load();
  };

  const run = async (jobId: number) => {
    const executionId = await http.post(`/job/execute/${jobId}`);
    message.success(`已提交执行 #${executionId}`);
    navigate(`/main/detail/${id}/jobExecutionLogs?executionId=${executionId}`);
  };

  const metric = Form.useWatch("metricType", form);

  return (
    <div>
      <div style={{ marginBottom: 12, display: "flex", justifyContent: "space-between" }}>
        <span>在这张数据源上配置质量作业。引擎请选 local，spark 只保留接口。</span>
        <Button type="primary" onClick={() => { form.setFieldsValue({ checkType: "column", engineType: "local", expectedType: "fix_value", resultFormula: "count", operator: "eq", threshold: 0, retryTimes: 0, timeout: 600 }); onCheck("column"); setOpen(true); }}>新建作业</Button>
      </div>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "指标", dataIndex: "metricType" },
          { title: "库表列", render: (_, row) => [row.schemaName, row.tableName, row.columnName].filter(Boolean).join(".") },
          { title: "引擎", dataIndex: "engineType", render: (value) => <Tag color={value === "spark" ? "orange" : "blue"}>{value || "local"}</Tag> },
          {
            title: "操作",
            render: (_, row) => (
              <Space>
                <a onClick={() => run(row.id)}>运行</a>
                <a onClick={async () => {
                  const current = await http.get(`/job/schedule/${row.id}`);
                  scheduleForm.setFieldsValue({
                    cronExpression: current?.cronExpression || "0 2 * * *",
                    status: current ? current.status === 1 : true,
                  });
                  setScheduleJob(row.id);
                }}>调度</a>
                <a onClick={async () => { await http.delete(`/job/${row.id}`); load(); }}>删除</a>
              </Space>
            ),
          },
        ]}
      />
      <Modal title="质量作业" open={open} onCancel={() => setOpen(false)} onOk={save} width={760} okText="保存">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="作业名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="checkType" label="检查类型" rules={[{ required: true }]}>
            <Select options={CHECKS} onChange={onCheck} />
          </Form.Item>
          <Form.Item name="metricType" label="规则" rules={[{ required: true }]}><Select options={metrics} showSearch optionFilterProp="label" /></Form.Item>
          <Form.Item name="engineType" label="执行引擎">
            <Select options={[{ value: "local", label: "local（已实现）" }, { value: "spark", label: "spark（仅接口，运行会失败）" }]} />
          </Form.Item>
          {engineType === "spark" && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="Spark 只保留接口。保存后一旦运行，执行会失败，日志会要求改回 local。不会提交 Spark 或 Livy。" />}
          <Space style={{ display: "flex" }} align="start">
            <Form.Item name="database" label="数据库" rules={[{ required: checkType !== "custom" }]}><Select style={{ width: 180 }} options={databases.map((item) => ({ value: item, label: item }))} /></Form.Item>
            <Form.Item name="table" label="表" rules={[{ required: checkType !== "custom" }]}><Select style={{ width: 200 }} options={tables.map((item) => ({ value: item.name, label: item.name }))} /></Form.Item>
            <Form.Item name="column" label="列"><Select allowClear style={{ width: 180 }} options={columns.map((item) => ({ value: item.name, label: item.name }))} /></Form.Item>
          </Space>
          {["column_in_enums", "column_not_in_enums"].includes(metric) && <Form.Item name="enum_list" label="枚举值，逗号分隔" rules={[{ required: true }]}><Input placeholder="PAID,SHIPPED" /></Form.Item>}
          {["column_match_regex", "column_match_not_regex"].includes(metric) && <Form.Item name="regexp" label="正则" rules={[{ required: true }]}><Input /></Form.Item>}
          {metric === "column_length" && (
            <Space>
              <Form.Item name="comparator" label="比较符"><Select style={{ width: 120 }} options={[{ value: "gt", label: ">" }, { value: "gte", label: ">=" }, { value: "eq", label: "=" }, { value: "lt", label: "<" }, { value: "lte", label: "<=" }]} /></Form.Item>
              <Form.Item name="length" label="长度"><InputNumber /></Form.Item>
            </Space>
          )}
          {metric === "column_value_between" && (
            <Space>
              <Form.Item name="min" label="最小值"><InputNumber /></Form.Item>
              <Form.Item name="max" label="最大值"><InputNumber /></Form.Item>
            </Space>
          )}
          {metric === "freshness" && (
            <>
              <Form.Item name="begin_time" label="开始时间"><Input placeholder="2026-01-01 00:00:00" /></Form.Item>
              <Form.Item name="deadline_time" label="结束时间"><Input placeholder="2026-12-31 23:59:59" /></Form.Item>
              <Form.Item name="datetime_format" label="时间格式"><Input placeholder="yyyy-MM-dd HH:mm:ss" /></Form.Item>
            </>
          )}
          {metric === "custom_aggregate_sql" && <Form.Item name="actual_aggregate_sql" label="聚合 SQL" rules={[{ required: true }]}><Input.TextArea rows={3} placeholder="select sum(amount) from demo.orders" /></Form.Item>}
          {metric === "custom_count_sql" && <Form.Item name="actual_execute_sql" label="统计 SQL（返回待计数的行）" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>}
          {(metric === "multi_table_accuracy" || metric === "multi_table_value_comparison") && (
            <>
              <Form.Item name="table2" label="目标表" rules={[{ required: true }]}><Select options={tables2.map((item) => ({ value: item.name, label: item.name }))} /></Form.Item>
              {metric === "multi_table_accuracy" && (
                <Space>
                  <Form.Item name="join_column" label="关联列" rules={[{ required: true }]}><Input placeholder="id" /></Form.Item>
                  <Form.Item name="compare_column" label="比对列"><Input placeholder="amount，可空" /></Form.Item>
                </Space>
              )}
              {metric === "multi_table_value_comparison" && (
                <Space>
                  <Form.Item name="column2" label="目标列"><Input /></Form.Item>
                  <Form.Item name="compare_metric" label="聚合" initialValue="count"><Select style={{ width: 140 }} options={["count", "sum", "avg", "min", "max"].map((item) => ({ value: item, label: item }))} /></Form.Item>
                </Space>
              )}
              <Form.Item name="filter2" label="目标表过滤"><Input /></Form.Item>
            </>
          )}
          <Form.Item name="filter" label="过滤条件"><Input placeholder="status = 'PAID'" /></Form.Item>
          <Space align="start">
            <Form.Item name="expectedType" label="期望值" rules={[{ required: true }]}><Select style={{ width: 180 }} options={expected} /></Form.Item>
            <Form.Item name="expected_value" label="固定值"><Input placeholder="期望类型为固定值时填写" /></Form.Item>
            <Form.Item name="resultFormula" label="结果公式" rules={[{ required: true }]}><Select style={{ width: 220 }} options={formulas} /></Form.Item>
          </Space>
          <Space>
            <Form.Item name="operator" label="比较符" rules={[{ required: true }]}><Select style={{ width: 120 }} options={operators} /></Form.Item>
            <Form.Item name="threshold" label="阈值" rules={[{ required: true }]}><Input /></Form.Item>
          </Space>
          <Space>
            <Form.Item name="retryTimes" label="重试次数"><InputNumber min={0} /></Form.Item>
            <Form.Item name="retryInterval" label="重试间隔(秒)"><InputNumber min={0} /></Form.Item>
            <Form.Item name="timeout" label="超时(秒)"><InputNumber min={0} /></Form.Item>
          </Space>
          <Form.Item name="preSql" label="前置 SQL"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="postSql" label="后置 SQL"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="cronExpression" label="Cron（可空，5 位或 Quartz 6 位）"><Input placeholder="0 0 * * *" /></Form.Item>
          <Form.Item name="errorOutput" label="失败时把错误样本写回被检库" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
      <Modal title="作业调度" open={scheduleJob != null} onCancel={() => setScheduleJob(null)} onOk={async () => {
        const values = await scheduleForm.validateFields();
        await http.post("/job/schedule/createOrUpdate", {
          jobId: scheduleJob,
          type: "cycle",
          cronExpression: values.cronExpression,
          status: values.status ? 1 : 0,
        });
        message.success("调度已保存");
        setScheduleJob(null);
      }}>
        <Form form={scheduleForm} layout="vertical">
          <Form.Item name="cronExpression" label="Cron（5 位，或 Quartz 6 位秒在前）" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="status" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
