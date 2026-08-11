import Editor, { DiffEditor } from "@monaco-editor/react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  Bot, ChevronRight, CircleDot, Code2, File, FilePlus2, FolderGit2,
  GitBranch, Network, PanelBottom, Plus, Send, Settings, ShieldCheck,
  Sparkles, SquareTerminal, Upload, X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { AgentAnswer, Citation, DocumentFile, LocalSettingsDraft, LocalSettingsStatus, Message, Project, Session } from "./types";

type Policy = { mode: "safe" | "autonomous"; scope: "workspace" | "roots" | "computer"; provider_profile: "auto" | "local-agent" | "local-grounded" | "remote-strong"; source_selector: string };
const defaultPolicy: Policy = { mode: "safe", scope: "workspace", provider_profile: "auto", source_selector: "auto" };

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [files, setFiles] = useState<DocumentFile[]>([]);
  const [repositoryGraph, setRepositoryGraph] = useState<{ nodes: Array<{ id: string; relative_path: string }>; edges: Array<{ id: string; source_document_id: string; target_ref: string; edge_type: string }> }>({ nodes: [], edges: [] });
  const [activeProject, setActiveProject] = useState<string>();
  const [activeSession, setActiveSession] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [answer, setAnswer] = useState<AgentAnswer>();
  const [selectedFile, setSelectedFile] = useState<DocumentFile>();
  const [fileContent, setFileContent] = useState("Select a project file to inspect its extracted content.");
  const [originalFileContent, setOriginalFileContent] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [error, setError] = useState("");
  const [policy, setPolicy] = useState<Policy>(defaultPolicy);
  const [bottomPanel, setBottomPanel] = useState<"terminal" | "graph">("terminal");
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

  useEffect(() => { refresh().catch((e) => setError(String(e))); }, []);
  useEffect(() => {
    let close: (() => void) | undefined;
    api.events((event) => {
      if (event.session_id && event.session_id !== activeSession) return;
      if (event.type === "chat.started") setStreaming("");
      if (event.type === "chat.delta") setStreaming((value) => value + String(event.payload.delta || ""));
      if (event.type === "chat.failed") setError(String(event.payload.error || "Agent failed"));
    }).then((value) => { close = value; }).catch(() => undefined);
    return () => close?.();
  }, [activeSession]);
  useEffect(() => { if (activeProject) Promise.all([api.files(activeProject), api.graph(activeProject)]).then(([nextFiles, nextGraph]) => { setFiles(nextFiles); setRepositoryGraph(nextGraph); }).catch((e) => setError(String(e))); else { setFiles([]); setRepositoryGraph({ nodes: [], edges: [] }); } }, [activeProject]);
  useEffect(() => { if (activeSession) api.messages(activeSession).then(setMessages).catch((e) => setError(String(e))); }, [activeSession]);

  async function createConversation() {
    const session = await api.createSession(activeProject);
    setSessions((items) => [session, ...items]); setActiveSession(session.id); setMessages([]); setAnswer(undefined);
  }

  async function addProject() {
    try {
      const selected = await open({ directory: true, multiple: false, title: "Select a repository or project folder" });
      if (!selected || Array.isArray(selected)) return;
      const name = selected.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "Imported project";
      const project = await api.createProject(name, selected);
      setProjects((items) => [project, ...items]); setActiveProject(project.id);
      await api.importProject(project.id);
      setFiles(await api.files(project.id)); setRepositoryGraph(await api.graph(project.id));
    } catch (e) { setError(String(e)); }
  }

  async function openSettings() {
    setSettingsOpen(true); setSettingsNotice("");
    try { setSettingsStatus(await api.settings()); }
    catch (e) { setError(String(e)); }
  }

  async function saveSettings() {
    setBusy(true); setSettingsNotice("");
    try {
      const next = await api.updateSettings(settingsDraft);
      setSettingsStatus(next); setSettingsDraft({});
      setSettingsNotice("Saved locally. Provider keys are active now; restart JARVIS to apply Telegram and integration changes.");
    } catch (e) { setSettingsNotice(String(e)); }
    finally { setBusy(false); }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || !activeSession || busy) return;
    const content = query.trim(); setQuery(""); setBusy(true); setStreaming(""); setError("");
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", content, grounded: 0, metadata_json: "{}", created_at: new Date().toISOString() }]);
    try {
      const next = await api.send(activeSession, content); setAnswer(next);
      setMessages((items) => [...items, { id: next.message_id, role: "assistant", content: next.answer, grounded: Number(next.grounded), metadata_json: JSON.stringify(next), created_at: new Date().toISOString() }]);
    } catch (e) { setError(String(e)); } finally { setBusy(false); setStreaming(""); }
  }

  async function changePolicy(next: Partial<Policy>) {
    const value = { ...policy, ...next }; setPolicy(value);
    if (activeSession) await api.setPolicy(activeSession, value);
  }

  async function handleFiles(list: FileList | File[]) {
    if (!activeProject) { setError("Create or select a project first."); return; }
    setBusy(true);
    try { for (const file of Array.from(list)) await api.upload(activeProject, file); setFiles(await api.files(activeProject)); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  async function confirmApproval() {
    if (!answer?.pending_approval_id) return;
    try {
      let result = await api.confirm(answer.pending_approval_id) as { requires_local_code?: boolean; answer?: AgentAnswer };
      if (result.requires_local_code) {
        const local = await api.localCode(answer.pending_approval_id);
        const entered = window.prompt(`High-risk action. Re-enter this one-time local code to continue: ${local.local_code}`);
        if (!entered) return;
        result = await api.confirm(answer.pending_approval_id, entered) as { answer?: AgentAnswer };
      }
      if (result.answer) {
        setAnswer(result.answer);
        setMessages((items) => [...items, { id: result.answer!.message_id, role: "assistant", content: result.answer!.answer, grounded: Number(result.answer!.grounded), metadata_json: JSON.stringify(result.answer), created_at: new Date().toISOString() }]);
      }
    } catch (e) { setError(String(e)); }
  }

  async function openFile(item: DocumentFile) {
    setSelectedFile(item); const content = await api.fileContent(item.id); setFileContent(content.content); setOriginalFileContent(content.content); setEditMode(false);
  }

  function preparePatch() {
    if (!selectedFile || fileContent === originalFileContent) { setEditMode(false); return; }
    if (fileContent.length + originalFileContent.length > 80_000) { setError("This draft is too large for one agent patch. Split it into a smaller exact replacement."); return; }
    setQuery(`Use the patch_file tool for ${selectedFile.relative_path}. Replace exactly this old_text:\n\n${originalFileContent}\n\nWith this new_text:\n\n${fileContent}\n\nDo not modify any other file.`);
    setEditMode(false);
  }

  const graph = useMemo(() => {
    const nodes = repositoryGraph.nodes.slice(0, 100).map((item, index) => ({ id: item.id, position: { x: (index % 5) * 210, y: Math.floor(index / 5) * 100 }, data: { label: item.relative_path }, style: { background: "#171b24", border: "1px solid #343b4c", color: "#d7dcea", fontSize: 11, width: 180 } }));
    const byName = new Map(repositoryGraph.nodes.flatMap((item) => [[item.relative_path.toLowerCase(), item.id], [item.relative_path.split(/[\\/]/).pop()!.replace(/\.[^.]+$/, "").toLowerCase(), item.id]]));
    const edges = repositoryGraph.edges.flatMap((edge) => { const target = byName.get(edge.target_ref.toLowerCase()); return target ? [{ id: edge.id, source: edge.source_document_id, target, label: edge.edge_type, style: { stroke: "#697386" } }] : []; });
    return { nodes, edges };
  }, [repositoryGraph]);

  return <main className="app" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void handleFiles(e.dataTransfer.files); }}>
    <aside className="sidebar">
      <div className="brand"><div className="mark"><Sparkles size={16}/></div><div><strong>JARVIS</strong><span>LOCAL AGENT</span></div></div>
      <button className="primary" onClick={() => void createConversation()}><Plus size={16}/> New task</button>
      <Section title="PROJECTS" action={<button className="section-action" onClick={() => void addProject()} title="Import project"><FolderGit2 size={14}/><Plus size={10}/></button>}>{projects.map((project) => <button key={project.id} className={activeProject === project.id ? "nav active" : "nav"} onClick={() => setActiveProject(project.id)}><ChevronRight size={13}/><span>{project.name}</span></button>)}{!projects.length && <p className="empty">No projects yet</p>}</Section>
      <Section title="TASKS">{sessions.map((session) => <button key={session.id} className={activeSession === session.id ? "nav active" : "nav"} onClick={() => setActiveSession(session.id)}><CircleDot size={12}/><span>{session.title}</span></button>)}</Section>
      <button className="settings" onClick={() => void openSettings()}><Settings size={16}/> Settings</button>
    </aside>

    <section className="workspace">
      <header className="toolbar">
        <div className="crumb"><Bot size={17}/><span>{projects.find((p) => p.id === activeProject)?.name || "No project"}</span><span className="branch"><GitBranch size={13}/> local</span></div>
        <div className="controls">
          <select value={policy.provider_profile} onChange={(e) => void changePolicy({ provider_profile: e.target.value as Policy["provider_profile"] })}><option value="auto">Provider: Auto</option><option value="local-agent">Local agent</option><option value="local-grounded">Local grounded</option><option value="remote-strong">Remote strong</option></select>
          <select value={policy.mode} onChange={(e) => void changePolicy({ mode: e.target.value as Policy["mode"] })}><option value="safe">Safe mode</option><option value="autonomous">Autonomous</option></select>
          <select value={policy.scope} onChange={(e) => void changePolicy({ scope: e.target.value as Policy["scope"] })}><option value="workspace">Workspace</option><option value="roots">Allowed roots</option><option value="computer">Computer</option></select>
        </div>
      </header>

      <div className="content-grid">
        <section className="chat-panel">
          <div className="timeline">
            {!messages.length && <div className="welcome"><div className="hero-icon"><Sparkles/></div><h1>What are we building?</h1><p>Ask about your files, upload documents, inspect a repository, or let JARVIS compose safe tools.</p><div className="suggestions"><button onClick={() => setQuery("Analyze this project architecture and cite the important files.")}>Analyze project architecture</button><button onClick={() => setQuery("Find the relevant document sections and summarize them with citations.")}>Search my documents</button></div></div>}
            {messages.map((message) => <article key={message.id} className={`message ${message.role}`}><div className="avatar">{message.role === "user" ? "YOU" : "JR"}</div><div><div className="message-meta">{message.role === "user" ? "You" : "JARVIS"}{message.role === "assistant" && <span className={message.grounded ? "grounded" : "general"}>{message.grounded ? "Grounded" : "General knowledge"}</span>}</div><div className="message-body">{message.content}</div>{message.role === "assistant" && answer?.message_id === message.id && <Citations items={answer.citations}/>}</div></article>)}
            {busy && streaming && <article className="message assistant"><div className="avatar">JR</div><div><div className="message-meta">JARVIS <span className="general">Streaming</span></div><div className="message-body">{streaming}</div></div></article>}
            {busy && !streaming && <div className="thinking"><span/><span/><span/> JARVIS is working</div>}
          </div>
          {answer?.pending_approval_id && <div className="approval"><ShieldCheck size={18}/><div><strong>Approval required</strong><small>{answer.answer}</small></div><button onClick={() => void confirmApproval()}>Confirm</button><button className="ghost" onClick={() => void api.cancel(answer.pending_approval_id!)}>Cancel</button></div>}
          {error && <div className="error"><span>{error}</span><button onClick={() => setError("")}><X size={14}/></button></div>}
          <form className="composer" onSubmit={send}><textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask JARVIS or describe a task…" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }}/><div className="composer-actions"><button type="button" className="icon" onClick={() => uploadRef.current?.click()} title="Upload files"><FilePlus2 size={17}/></button><span>Files are treated as untrusted context</span><button className="send" disabled={busy || !activeSession}><Send size={16}/></button></div></form>
          <input ref={uploadRef} hidden type="file" multiple onChange={(e) => e.target.files && void handleFiles(e.target.files)}/>
        </section>

        <aside className="project-panel">
          <div className="panel-title"><span><Code2 size={15}/> PROJECT</span><button onClick={() => uploadRef.current?.click()}><Upload size={14}/></button></div>
          <div className="file-tree">{files.map((item) => <button key={item.id} className={selectedFile?.id === item.id ? "file-row selected" : "file-row"} onClick={() => void openFile(item)}><File size={14}/><span>{item.relative_path}</span><small>{Math.ceil(item.size_bytes / 1024)} KB</small></button>)}{!files.length && <div className="drop-zone"><Upload size={22}/><span>Drop documents or a project archive here</span></div>}</div>
          <div className="editor-title"><span>{selectedFile?.relative_path || "Preview"}</span>{selectedFile && <div className="editor-actions">{editMode ? <><button onClick={() => { setFileContent(originalFileContent); setEditMode(false); }}>Cancel</button><button onClick={preparePatch}>Prepare patch</button></> : <button onClick={() => setEditMode(true)}>Edit with diff</button>}</div>}</div>
          <div className="editor">{editMode ? <DiffEditor height="100%" theme="vs-dark" original={originalFileContent} modified={fileContent} language={selectedFile?.language || "plaintext"} onMount={(editor) => editor.getModifiedEditor().onDidChangeModelContent(() => setFileContent(editor.getModifiedEditor().getValue()))} options={{ originalEditable: false, minimap: { enabled: false }, fontSize: 12, wordWrap: "on", scrollBeyondLastLine: false }}/> : <Editor height="100%" theme="vs-dark" value={fileContent} language={selectedFile?.language || "plaintext"} options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, wordWrap: "on", scrollBeyondLastLine: false }}/>}</div>
        </aside>
      </div>

      <section className="bottom-panel"><div className="bottom-tabs"><button className={bottomPanel === "terminal" ? "active" : ""} onClick={() => setBottomPanel("terminal")}><SquareTerminal size={14}/> Terminal</button><button className={bottomPanel === "graph" ? "active" : ""} onClick={() => setBottomPanel("graph")}><Network size={14}/> Dependency graph</button><button className="collapse"><PanelBottom size={14}/></button></div>{bottomPanel === "terminal" ? <div className="terminal"><span className="prompt">PS JARVIS&gt;</span> Backend connected. Commands are executed only through typed, approval-aware tools.</div> : <div className="graph"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView><Background color="#292e3a"/><Controls/></ReactFlow></div>}</section>
    </section>

    {settingsOpen && <SettingsModal policy={policy} status={settingsStatus} draft={settingsDraft} notice={settingsNotice} busy={busy} onPolicy={changePolicy} onDraft={setSettingsDraft} onSave={saveSettings} onClose={() => setSettingsOpen(false)}/>}
  </main>;
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="side-section"><div className="section-label"><span>{title}</span>{action}</div><div className="section-items">{children}</div></section>; }
function Citations({ items }: { items: Citation[] }) { if (!items.length) return null; return <div className="citations">{items.map((item) => <button key={item.chunk_id}><File size={12}/><span>{item.source_path}{item.page ? ` · page ${item.page}` : ""}{item.line_start ? ` · L${item.line_start}${item.line_end ? `–${item.line_end}` : ""}` : ""}{item.sheet ? ` · ${item.sheet} ${item.cell_range || ""}` : ""}</span></button>)}</div>; }

function SettingsModal({ policy, status, draft, notice, busy, onPolicy, onDraft, onSave, onClose }: { policy: Policy; status?: LocalSettingsStatus; draft: LocalSettingsDraft; notice: string; busy: boolean; onPolicy: (next: Partial<Policy>) => Promise<void>; onDraft: (next: LocalSettingsDraft) => void; onSave: () => Promise<void>; onClose: () => void }) {
  const update = (name: keyof LocalSettingsDraft, value: string) => onDraft({ ...draft, [name]: value });
  const secretFields: Array<[keyof LocalSettingsDraft, string]> = [
    ["freemodel_api_key", "FreeModel API key"], ["openai_api_key", "OpenAI API key"],
    ["telegram_bot_token", "Telegram bot token"], ["hf_token", "Hugging Face token"],
    ["web_search_api_key", "Web search API key"], ["google_access_token", "Google access token"],
    ["microsoft_access_token", "Microsoft access token"],
  ];
  return <div className="modal-backdrop" onClick={onClose}><section className="modal settings-modal" onClick={(e) => e.stopPropagation()}>
    <header><div><h2>JARVIS settings</h2><small>Stored only in the local Windows application profile.</small></div><button onClick={onClose}><X/></button></header>
    <div className="provider-status">{Object.entries(status?.providers || {}).map(([name, value]) => <span key={name} className={value.available ? "available" : "unavailable"}><i/>{name}: {value.available ? "available" : "not configured"}</span>)}</div>
    <div className="settings-grid">
      <label>Provider profile<select value={policy.provider_profile} onChange={(e) => void onPolicy({ provider_profile: e.target.value as Policy["provider_profile"] })}><option value="auto">Auto</option><option value="local-agent">Local agent</option><option value="local-grounded">Local grounded</option><option value="remote-strong">Remote strong</option></select></label>
      <label>Corpus selector<input value={policy.source_selector} onChange={(e) => void onPolicy({ source_selector: e.target.value })}/></label>
      <label>FreeModel model<input value={draft.freemodel_model ?? status?.models.freemodel ?? "auto"} onChange={(e) => update("freemodel_model", e.target.value)}/></label>
      <label>LoRA adapter path<input value={draft.local_adapter_path || ""} placeholder={status?.configured.local_adapter_path ? "Configured — leave blank unchanged" : "C:\\path\\to\\adapter"} onChange={(e) => update("local_adapter_path", e.target.value)}/></label>
      {secretFields.map(([name, label]) => <label key={name}>{label}<input type="password" autoComplete="off" value={draft[name] || ""} placeholder={status?.configured[name] ? "Configured — leave blank unchanged" : "Not configured"} onChange={(e) => update(name, e.target.value)}/></label>)}
    </div>
    {notice && <p className="settings-notice">{notice}</p>}
    <p>Secret values are write-only: the backend returns only configured/available flags. Session mode resets to safe + workspace after restart.</p>
    <footer><button className="ghost" onClick={onClose}>Close</button><button className="primary" disabled={busy} onClick={() => void onSave()}>{busy ? "Saving…" : "Save locally"}</button></footer>
  </section></div>;
}
