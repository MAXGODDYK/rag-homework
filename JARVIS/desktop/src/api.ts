import { invoke } from "@tauri-apps/api/core";
import type { BackendInfo, DocumentFile, LocalSettingsDraft, LocalSettingsStatus, Message, Project, RagAnswer, Session } from "./types";

class JarvisApi {
  private info?: BackendInfo;

  async connect(): Promise<BackendInfo> {
    if (this.info) return this.info;
    try {
      this.info = await invoke<BackendInfo>("ensure_backend");
    } catch {
      const saved = localStorage.getItem("jarvis-dev-backend");
      if (!saved) throw new Error("JARVIS backend is not running");
      this.info = JSON.parse(saved) as BackendInfo;
    }
    return this.info;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const info = await this.connect();
      if (attempt > 0) {
        // The Python bootstrap contract is printed just before Uvicorn starts
        // accepting connections. Give the recovered process a brief grace period.
        await new Promise((resolve) => window.setTimeout(resolve, attempt * 250));
      }
      let response: Response;
      try {
        response = await fetch(`http://${info.host}:${info.port}${path}`, {
          ...init,
          headers: {
            "X-Jarvis-Token": info.ipc_token,
            ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...init.headers,
          },
        });
      } catch (error) {
        if (attempt < 2) {
          // The Python process may have restarted. Drop the stale port/token
          // and let Tauri's ensure_backend command recover it once.
          this.info = undefined;
          continue;
        }
        throw new Error(`JARVIS backend connection was lost: ${String(error)}`);
      }
      if (response.status === 401 && attempt < 2) {
        this.info = undefined;
        continue;
      }
      if (!response.ok) {
        const detail = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(detail.detail || `HTTP ${response.status}`);
      }
      return response.json() as Promise<T>;
    }
    throw new Error("JARVIS backend connection could not be restored");
  }

  health() { return this.request<{ status: string; version: string; mode: string }>("/v1/health"); }
  settings() { return this.request<LocalSettingsStatus>("/v1/settings"); }
  updateSettings(settings: LocalSettingsDraft) {
    return this.request<LocalSettingsStatus>("/v1/settings", { method: "POST", body: JSON.stringify(settings) });
  }
  connectGoogleSheets() { return this.request<LocalSettingsStatus["google_sheets"]>("/v1/google-sheets/connect", { method: "POST" }); }
  projects() { return this.request<Project[]>("/v1/projects"); }
  sessions(archived = false) { return this.request<Session[]>(`/v1/sessions?archived=${archived}`); }
  createProject(name: string, rootPath?: string) {
    return this.request<Project>("/v1/projects", { method: "POST", body: JSON.stringify({ name, root_path: rootPath || null }) });
  }
  createSession(projectId?: string) {
    return this.request<Session>("/v1/sessions", { method: "POST", body: JSON.stringify({ user_id: "desktop-owner", project_id: projectId || null, title: "New conversation" }) });
  }
  archiveSession(sessionId: string) { return this.request<Session>(`/v1/sessions/${sessionId}/archive`, { method: "POST" }); }
  restoreSession(sessionId: string) { return this.request<Session>(`/v1/sessions/${sessionId}/restore`, { method: "POST" }); }
  renameSession(sessionId: string, title: string) { return this.request<Session>(`/v1/sessions/${sessionId}`, { method: "PATCH", body: JSON.stringify({ title }) }); }
  messages(sessionId: string) { return this.request<Message[]>(`/v1/sessions/${sessionId}/messages`); }
  send(sessionId: string, content: string) {
    return this.request<RagAnswer>(`/v1/messages?session_id=${encodeURIComponent(sessionId)}`, { method: "POST", body: JSON.stringify({ content }) });
  }
  setPolicy(sessionId: string, policy: Record<string, string>) {
    return this.request(`/v1/sessions/${sessionId}/policy`, { method: "POST", body: JSON.stringify(policy) });
  }
  files(projectId: string) { return this.request<DocumentFile[]>(`/v1/projects/${projectId}/files`); }
  async upload(projectId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.request<{ records: unknown[] }>(`/v1/uploads?project_id=${encodeURIComponent(projectId)}`, { method: "POST", body: form });
  }
  importProject(projectId: string) { return this.request(`/v1/projects/${projectId}/import`, { method: "POST" }); }
  async events(onEvent: (event: { type: string; session_id?: string; payload: Record<string, unknown> }) => void) {
    let stopped = false;
    let socket: WebSocket | undefined;
    let reconnectTimer: number | undefined;
    const openSocket = async () => {
      if (stopped) return;
      const info = await this.connect();
      socket = new WebSocket(`ws://${info.host}:${info.port}/v1/events?token=${encodeURIComponent(info.ipc_token)}`);
      socket.addEventListener("message", (message) => {
        try { onEvent(JSON.parse(message.data as string)); } catch { /* ignore malformed local events */ }
      });
      socket.addEventListener("close", () => {
        if (stopped) return;
        this.info = undefined;
        reconnectTimer = window.setTimeout(() => void openSocket().catch(() => undefined), 500);
      });
    };
    await openSocket();
    return () => {
      stopped = true;
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }
}

export const api = new JarvisApi();
