import axios from "axios";
import { message } from "antd";

const http = axios.create({ baseURL: "/api/v1", timeout: 120000 });

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("dv_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (response) => {
    const body = response.data;
    if (body && typeof body.code === "number" && body.code !== 200) {
      message.error(body.msg || "请求失败");
      return Promise.reject(new Error(body.msg || "请求失败"));
    }
    return body?.data;
  },
  (error) => {
    const status = error?.response?.status;
    const msg = error?.response?.data?.msg || error.message || "网络错误";
    if (status === 401 && !window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/register")) {
      localStorage.removeItem("dv_token");
      window.location.assign("/login");
    }
    message.error(msg);
    return Promise.reject(error);
  },
);

type Api = {
  get: (url: string, config?: object) => Promise<any>;
  post: (url: string, data?: unknown, config?: object) => Promise<any>;
  put: (url: string, data?: unknown, config?: object) => Promise<any>;
  delete: (url: string, config?: object) => Promise<any>;
};

const api: Api = {
  get: (url, config) => http.get(url, config) as Promise<any>,
  post: (url, data, config) => http.post(url, data, config) as Promise<any>,
  put: (url, data, config) => http.put(url, data, config) as Promise<any>,
  delete: (url, config) => http.delete(url, config) as Promise<any>,
};

export default api;

export const STATUS: Record<number, { text: string; color: string }> = {
  0: { text: "已提交", color: "default" },
  1: { text: "运行中", color: "processing" },
  6: { text: "失败", color: "error" },
  7: { text: "成功", color: "success" },
  9: { text: "已终止", color: "warning" },
};
