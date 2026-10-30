import { Navigate, Route, Routes } from "react-router-dom";
import MainLayout from "./layout/MainLayout";
import HomePage from "./pages/HomePage";
import DetailLayout from "./pages/DetailLayout";
import DashboardPage from "./pages/DashboardPage";
import EditorPage from "./pages/EditorPage";
import ExecutionPage from "./pages/ExecutionPage";
import CatalogPage from "./pages/CatalogPage";
import ProfilePage from "./pages/ProfilePage";
import SchemaPage from "./pages/SchemaPage";
import LineagePage from "./pages/LineagePage";
import WarningPage from "./pages/WarningPage";
import StoragePage from "./pages/StoragePage";
import LabelPage from "./pages/LabelPage";
import ConfigPage from "./pages/ConfigPage";
import EnvPage from "./pages/EnvPage";
import TokenPage from "./pages/TokenPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import UsersPage from "./pages/UsersPage";
import { readToken } from "./session";

function RequireAuth() {
  if (!readToken()) return <Navigate to="/login" replace />;
  return <MainLayout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/main/home" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/main" element={<RequireAuth />}>
        <Route path="home" element={<HomePage />} />
        <Route path="detail/:id" element={<DetailLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="editor" element={<EditorPage />} />
          <Route path="jobs" element={<ExecutionPage mode="list" />} />
          <Route path="jobExecutionLogs" element={<ExecutionPage mode="log" />} />
          <Route path="catalog" element={<CatalogPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="schema" element={<SchemaPage />} />
          <Route path="lineage" element={<LineagePage />} />
        </Route>
        <Route path="warning" element={<WarningPage />} />
        <Route path="errorDataManage" element={<StoragePage />} />
        <Route path="label" element={<LabelPage />} />
        <Route path="config" element={<ConfigPage />} />
        <Route path="env" element={<EnvPage />} />
        <Route path="tokenManager" element={<TokenPage />} />
        <Route path="users" element={<UsersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/main/home" replace />} />
    </Routes>
  );
}
