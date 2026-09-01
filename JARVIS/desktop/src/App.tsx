import Editor from "@monaco-editor/react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import { open } from "@tauri-apps/plugin-dialog";
import { Bot, ChevronRight, CircleDot, Code2, File, FilePlus2, FolderGit2, GitBranch, Network, PanelBottom, Plus, Send, Settings, Sparkles, Upload, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { Citation, DocumentFile, LocalSettingsDraft, LocalSettingsStatus, Message, Project, RagAnswer, Session } from "./types";

type Policy = { provider_profile: "auto" | "freemodel" | "openai" | "extractive"; source_selector: string };
const defaultPolicy: Policy = { provider_profile: "auto", source_selector: "auto" };

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [files, setFiles] = useState<DocumentFile[]>([]);
  const [repositoryGraph, setRepositoryGraph] = useState<{ nodes: Array<{ id: string; relative_path: string }>; edges: Array<{ id: string; source_document_id: string; target_ref: string; edge_type: string }> }>({ nodes: [], edges: [] });
  const [activeProject, setActiveProject] = useState<string>();
  const [activeSession, setActiveSession] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [answer, setAnswer] = useState<RagAnswer>();
  const [selectedFile, setSelectedFile] = useState<DocumentFile>();
  const [fileContent, setFileContent] = useState("Select an imported file to inspect its extracted text.");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [error, setError] = useState("");
  const [policy, setPolicy] = useState<Policy>(defaultPolicy);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState<LocalSettingsStatus>();
  const [settingsDraft, setSettingsDraft] = useState<LocalSettingsDraft>({});
  const [settingsNotice, setSettingsNotice] = useState("");
  const uploadRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    await api.health();
    const [nextProjects, nextSessions] = await Promise.all([api.projects(), api.sessions()]);
    setProjects(nextProjects); setSessions(nextSessions);
    if (!activeProject && nextProjects[0]) setActiveProject(nextProjects[0].id);
    if (!activeSession && nextSessions[0]) setActiveSession(nextSessions[0].id);
  }, [activeProject, activeSession]);

  useEffect(() => { refresh().catch((event) => setError(String(event))); }, [refresh]);
  useEffect(() => {
    let close: (() => void) | undefined;
    api.events((event) => {
      if (event.session_id && event.session_id !== activeSession) return;
      if (event.type === "chat.started") setStreaming("");
      if (event.type === "chat.delta") setStreaming((value) => value + String(event.payload.delta || ""));
      if (event.type === "chat.failed") setError(String(event.payload.error || "RAG request failed"));
    }).then((value) => { close = value; }).catch(() => undefined);
    return () => close?.();
  }, [activeSession]);
  useEffect(() => {
    if (!activeProject) { setFiles([]); setRepositoryGraph({ nodes: [], edges: [] }); return; }
    Promise.all([api.files(activeProject), api.graph(activeProject)])
      .then(([nextFiles, nextGraph]) => { setFiles(nextFiles); setRepositoryGraph(nextGraph); })
      .catch((event) => setError(String(event)));
  }, [activeProject]);
  useEffect(() => { if (activeSession) api.messages(activeSession).then(setMessages).catch((event) => setError(String(event))); }, [activeSession]);

  async function createConversation() {
    if (!activeProject) { setError("Create or select a project first."); return; }
    const session = await api.createSession(activeProject);
    setSessions((items) => [session, ...items]); setActiveSession(session.id); setMessages([]); setAnswer(undefined); setPolicy(defaultPolicy);
  }
  async function addProject() {
    try {
      const selected = await open({ directory: true, multiple: false, title: "Select a document folder or repository" });
      if (!selected || Array.isArray(selected)) return;
      const name = selected.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "Imported project";
      const project = await api.createProject(name, selected);
      setProjects((items) => [project, ...items]); setActiveProject(project.id);
      await api.importProject(project.id); setFiles(await api.files(project.id)); setRepositoryGraph(await api.graph(project.id));
    } catch (event) { setError(String(event)); }
  }
  async function openSettings() { setSettingsOpen(true); setSettingsNotice(""); try { setSettingsStatus(await api.settings()); } catch (event) { setError(String(event)); } }
  async function saveSettings() {
    setBusy(true); setSettingsNotice("");
    try { const next = await api.updateSettings(settingsDraft); setSettingsStatus(next); setSettingsDraft({}); setSettingsNotice("Saved locally. Provider availability was refreshed."); }
    catch (event) { setSettingsNotice(String(event)); } finally { setBusy(false); }
  }
  async function changePolicy(next: Partial<Policy>) { const value = { ...policy, ...next }; setPolicy(value); if (activeSession) await api.setPolicy(activeSession, value); }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || !activeSession || busy) return;
    const content = query.trim(); setQuery(""); setBusy(true); setStreaming(""); setError("");
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", content, grounded: 0, metadata_json: "{}", created_at: new Date().toISOString() }]);
    try {
      const next = await api.send(activeSession, content); setAnswer(next);
      setMessages((items) => [...items, { id: next.message_id, role: "assistant", content: next.answer, grounded: Number(next.grounded), metadata_json: JSON.stringify(next), created_at: new Date().toISOString() }]);
    } catch (event) { setError(String(event)); } finally { setBusy(false); setStreaming(""); }
  }
  async function handleFiles(list: FileList | File[]) {
    if (!activeProject) { setError("Create or select a project first."); return; }
    setBusy(true);
    try { for (const file of Array.from(list)) await api.upload(activeProject, file); setFiles(await api.files(activeProject)); }
    catch (event) { setError(String(event)); } finally { setBusy(false); }
  }
  async function openFile(item: DocumentFile) {
    try { setSelectedFile(item); const content = await api.fileContent(item.id); setFileContent(content.content); await changePolicy({ source_selector: item.relative_path }); }
    catch (event) { setError(String(event)); }
  }
  const graph = useMemo(() => {
    const nodes = repositoryGraph.nodes.slice(0, 100).map((item, index) => ({ id: item.id, position: { x: (index % 5) * 210, y: Math.floor(index / 5) * 100 }, data: { label: item.relative_path }, style: { background: "#171b24", border: "1px solid #343b4c", color: "#d7dcea", fontSize: 11, width: 180 } }));
    const byName = new Map(repositoryGraph.nodes.flatMap((item) => [[item.relative_path.toLowerCase(), item.id], [item.relative_path.split(/[\\/]/).pop()!.replace(/\.[^.]+$/, "").toLowerCase(), item.id]]));
    const edges = repositoryGraph.edges.flatMap((edge) => { const target = byName.get(edge.target_ref.toLowerCase()); return target ? [{ id: edge.id, source: edge.source_document_id, target, label: edge.edge_type, style: { stroke: "#697386" } }] : []; });
    return { nodes, edges };
  }, [repositoryGraph]);

  return <main className="app" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void handleFiles(event.dataTransfer.files); }}>
    <aside className="sidebar">
      <div className="brand"><div className="mark"><Sparkles size={16}/></div><div><strong>JARVIS</strong><span>DESKTOP RAG</span></div></div>
      <button className="primary" onClick={() => void createConversation()}><Plus size={16}/> New conversation</button>
      <Section title="PROJECTS" action={<button className="section-action" onClick={() => void addProject()} title="Import a folder"><FolderGit2 size={14}/><Plus size={10}/></button>}>{projects.map((project) => <button key={project.id} className={activeProject === project.id ? "nav active" : "nav"} onClick={() => setActiveProject(project.id)}><ChevronRight size={13}/><span>{project.name}</span></button>)}{!projects.length && <p className="empty">No projects yet</p>}</Section>
      <Section title="CONVERSATIONS">{sessions.map((session) => <button key={session.id} className={activeSession === session.id ? "nav active" : "nav"} onClick={() => setActiveSession(session.id)}><CircleDot size={12}/><span>{session.title}</span></button>)}</Section>
      <button className="settings" onClick={() => void openSettings()}><Settings size={16}/> Settings</button>
    </aside>
    <section className="workspace">
      <header className="toolbar"><div className="crumb"><Bot size={17}/><span>{projects.find((project) => project.id === activeProject)?.name || "No project"}</span><span className="branch"><GitBranch size={13}/> local files</span></div><div className="controls"><select value={policy.provider_profile} onChange={(event) => void changePolicy({ provider_profile: event.target.value as Policy["provider_profile"] })}><option value="auto">Provider: Auto</option><option value="freemodel">FreeModel</option><option value="openai">OpenAI</option><option value="extractive">Evidence only</option></select><select value={policy.source_selector} onChange={(event) => void changePolicy({ source_selector: event.target.value })}><option value="auto">Corpus: current project</option><option value="all">Corpus: all projects</option>{files.map((file) => <option value={file.relative_path} key={file.id}>File: {file.relative_path}</option>)}</select></div></header>
      <div className="content-grid">
        <section className="chat-panel"><div className="timeline">
          {!messages.length && <div className="welcome"><div className="hero-icon"><Sparkles/></div><h1>Ask about imported files</h1><p>JARVIS searches the selected corpus with FTS5, multilingual FAISS and BGE reranking, then shows exact source citations.</p><div className="suggestions"><button onClick={() => setQuery("Summarize the most important information in the selected files and cite it.")}>Summarize selected files</button><button onClick={() => setQuery("What do these files say about the main topic? Cite the source.")}>Search my documents</button></div></div>}
          {messages.map((message) => <article key={message.id} className={`message ${message.role}`}><div className="avatar">{message.role === "user" ? "YOU" : "JR"}</div><div><div className="message-meta">{message.role === "user" ? "You" : "JARVIS"}{message.role === "assistant" && <span className={message.grounded ? "grounded" : "general"}>{message.grounded ? "Grounded" : "Insufficient context"}</span>}</div><div className="message-body">{message.content}</div>{message.role === "assistant" && answer?.message_id === message.id && <Citations items={answer.citations}/>}</div></article>)}
          {busy && streaming && <article className="message assistant"><div className="avatar">JR</div><div><div className="message-meta">JARVIS <span className="grounded">Retrieving</span></div><div className="message-body">{streaming}</div></div></article>}
          {busy && !streaming && <div className="thinking"><span/><span/><span/> Searching the selected corpus</div>}
        </div>{error && <div className="error"><span>{error}</span><button onClick={() => setError("")}><X size={14}/></button></div>}<form className="composer" onSubmit={send}><textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask a question about your imported files…" onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}/><div className="composer-actions"><button type="button" className="icon" onClick={() => uploadRef.current?.click()} title="Upload files"><FilePlus2 size={17}/></button><span>Imported files are untrusted context. Answers include citations.</span><button className="send" disabled={busy || !activeSession}><Send size={16}/></button></div></form><input ref={uploadRef} hidden type="file" multiple onChange={(event) => event.target.files && void handleFiles(event.target.files)}/></section>
        <aside className="project-panel"><div className="panel-title"><span><Code2 size={15}/> CORPUS</span><button onClick={() => uploadRef.current?.click()}><Upload size={14}/></button></div><div className="file-tree">{files.map((file) => <button key={file.id} className={selectedFile?.id === file.id ? "file-row selected" : "file-row"} onClick={() => void openFile(file)}><File size={14}/><span>{file.relative_path}</span><small>{Math.ceil(file.size_bytes / 1024)} KB</small></button>)}{!files.length && <div className="drop-zone"><Upload size={22}/><span>Drop documents, code or a project archive here</span></div>}</div><div className="editor-title"><span>{selectedFile?.relative_path || "Preview"}</span>{selectedFile && <button onClick={() => void changePolicy({ source_selector: "auto" })}>Use project corpus</button>}</div><div className="editor"><Editor height="100%" theme="vs-dark" value={fileContent} language={selectedFile?.language || "plaintext"} options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, wordWrap: "on", scrollBeyondLastLine: false }}/></div></aside>
      </div>
      <section className="bottom-panel"><div className="bottom-tabs"><button className="active"><Network size={14}/> Dependency graph</button><button className="collapse"><PanelBottom size={14}/></button></div><div className="graph"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView><Background color="#292e3a"/><Controls/></ReactFlow></div></section>
    </section>
    {settingsOpen && <SettingsModal policy={policy} status={settingsStatus} draft={settingsDraft} notice={settingsNotice} busy={busy} onPolicy={changePolicy} onDraft={setSettingsDraft} onSave={saveSettings} onClose={() => setSettingsOpen(false)}/>}
  </main>;
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="side-section"><div className="section-label"><span>{title}</span>{action}</div><div className="section-items">{children}</div></section>; }
function Citations({ items }: { items: Citation[] }) { if (!items.length) return null; return <div className="citations">{items.map((item) => <button key={item.chunk_id}><File size={12}/><span>{item.source_path}{item.page ? ` · page ${item.page}` : ""}{item.line_start ? ` · L${item.line_start}${item.line_end ? `–${item.line_end}` : ""}` : ""}{item.sheet ? ` · ${item.sheet} ${item.cell_range || ""}` : ""}</span></button>)}</div>; }

function SettingsModal({ policy, status, draft, notice, busy, onPolicy, onDraft, onSave, onClose }: { policy: Policy; status?: LocalSettingsStatus; draft: LocalSettingsDraft; notice: string; busy: boolean; onPolicy: (next: Partial<Policy>) => Promise<void>; onDraft: (next: LocalSettingsDraft) => void; onSave: () => Promise<void>; onClose: () => void }) {
  const update = (name: keyof LocalSettingsDraft, value: string) => onDraft({ ...draft, [name]: value });
  const secretFields: Array<[keyof LocalSettingsDraft, string]> = [["freemodel_api_key", "FreeModel API key"], ["openai_api_key", "OpenAI API key"], ["hf_token", "Hugging Face token (optional)"]];
  return <div className="modal-backdrop" onClick={onClose}><section className="modal settings-modal" onClick={(event) => event.stopPropagation()}><header><div><h2>JARVIS RAG settings</h2><small>Keys stay only in the local Windows application profile.</small></div><button onClick={onClose}><X/></button></header><div className="provider-status">{Object.entries(status?.providers || {}).map(([name, value]) => <span key={name} className={value.available ? "available" : "unavailable"}><i/>{name}: {value.available ? "available" : "not configured"}</span>)}</div><div className="settings-grid"><label>Provider<select value={policy.provider_profile} onChange={(event) => void onPolicy({ provider_profile: event.target.value as Policy["provider_profile"] })}><option value="auto">Auto</option><option value="freemodel">FreeModel</option><option value="openai">OpenAI</option><option value="extractive">Evidence only</option></select></label><label>FreeModel model<input value={draft.freemodel_model ?? status?.models.freemodel ?? "auto"} onChange={(event) => update("freemodel_model", event.target.value)}/></label>{secretFields.map(([name, label]) => <label key={name}>{label}<input type="password" autoComplete="off" value={draft[name] || ""} placeholder={status?.configured[name] ? "Configured — leave blank unchanged" : "Not configured"} onChange={(event) => update(name, event.target.value)}/></label>)}</div>{notice && <p className="settings-notice">{notice}</p>}<p>JARVIS is desktop-only and uses these keys only for grounded answers over your selected local corpus.</p><footer><button className="ghost" onClick={onClose}>Close</button><button className="primary" disabled={busy} onClick={() => void onSave()}>{busy ? "Saving…" : "Save locally"}</button></footer></section></div>;
}
