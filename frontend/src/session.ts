export const TOKEN_KEY = "dv_token";
export const USER_KEY = "dv_user";
export const WORKSPACE_KEY = "dv_workspace";

export type SessionUser = {
  id: number;
  username: string;
  email?: string;
  admin?: boolean;
  token?: string;
  workspaceId?: number | null;
  workspaces?: { id: number; name: string }[];
};

export function readToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function readUser(): SessionUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionUser;
  } catch {
    return null;
  }
}

export function workspaceId(): string | null {
  return localStorage.getItem(WORKSPACE_KEY);
}

export function saveSession(data: SessionUser) {
  if (data.token) localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, JSON.stringify(data));
  const current = localStorage.getItem(WORKSPACE_KEY);
  const known = (data.workspaces || []).some((item) => String(item.id) === current);
  const next = known ? current : data.workspaceId ? String(data.workspaceId) : "";
  if (next) localStorage.setItem(WORKSPACE_KEY, next);
}

export function selectWorkspace(id: number | string) {
  localStorage.setItem(WORKSPACE_KEY, String(id));
  window.dispatchEvent(new Event("dv-workspace"));
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(WORKSPACE_KEY);
}
