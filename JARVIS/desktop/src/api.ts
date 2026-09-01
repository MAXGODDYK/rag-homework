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
    const info = await this.connect();
    const response = await fetch(`http://${info.host}:${info.port}${path}`, {
      ...init,
      headers: {
        "X-Jarvis-Token": info.ipc_token,
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
      },
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  }

  health() { return this.request<{ status: string; version: string; mode: string }>("/v1/health"); }
  settings() { return this.request<LocalSettingsStatus>("/v1/settings"); }
  updateSettings(settings: LocalSettingsDraft) {
    return this.request<LocalSettingsStatus>("/v1/settings", { method: "POST", body: JSON.stringify(settings) });
  }
  projects() { return this.request<Project[]>("/v1/projects"); }
  sessions() { return this.request<Session[]>("/v1/sessions"); }
  createProject(name: string, rootPath?: string) {
    return this.request<Project>("/v1/projects", { method: "POST", body: JSON.stringify({ name, root_path: rootPath || null }) });
  }
  createSession(projectId?: string) {
    return this.request<Session>("/v1/sessions", { method: "POST", body: JSON.stringify({ user_id: "desktop-owner", project_id: projectId || null, title: "New conversation" }) });
  }
  messages(sessionId: string) { return this.request<Message[]>(`/v1/sessions/${sessionId}/messages`); }
  send(sessionId: string, content: string) {
    return this.request<RagAnswer>(`/v1/messages?session_id=${encodeURIComponent(sessionId)}`, { method: "POST", body: JSON.stringify({ content }) });
  }
  setPolicy(sessionId: string, policy: Record<string, string>) {
    return this.request(`/v1/sessions/${sessionId}/policy`, { method: "POST", body: JSON.stringify(policy) });
  }
  files(projectId: string) { return this.request<DocumentFile[]>(`/v1/projects/${projectId}/files`); }
  graph(projectId: string) { return this.request<{ nodes: Array<{ id: string; relative_path: string }>; edges: Array<{ id: string; source_document_id: string; target_ref: string; edge_type: string }> }>(`/v1/projects/${projectId}/graph`); }
  fileContent(documentId: string) { return this.request<{ content: string }>(`/v1/files/${documentId}/content`); }
  async upload(projectId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.request<{ records: unknown[] }>(`/v1/uploads?project_id=${encodeURIComponent(projectId)}`, { method: "POST", body: form });
  }
  importProject(projectId: string) { return this.request(`/v1/projects/${projectId}/import`, { method: "POST" }); }
  async events(onEvent: (event: { type: string; session_id?: string; payload: Record<string, unknown> }) => void) {
    const info = await this.connect();
    const socket = new WebSocket(`ws://${info.host}:${info.port}/v1/events?token=${encodeURIComponent(info.ipc_token)}`);
    socket.addEventListener("message", (message) => {
      try { onEvent(JSON.parse(message.data as string)); } catch { /* ignore malformed local events */ }
    });
    return () => socket.close();
  }
}

export const api = new JarvisApi();
