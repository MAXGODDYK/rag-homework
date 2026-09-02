import Editor from "@monaco-editor/react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import { open } from "@tauri-apps/plugin-dialog";
import { Archive, ArchiveRestore, Bot, ChevronRight, CircleDot, Code2, Database, File, FilePlus2, FolderGit2, GitBranch, Network, PanelBottom, Plus, Send, Settings, SlidersHorizontal, Sparkles, Upload, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { ChunkingCategory, ChunkingCategoryMode, ChunkingMode, Citation, DocumentFile, LocalSettingsDraft, LocalSettingsStatus, Message, Project, RagAnswer, Session } from "./types";

type Policy = { provider_profile: "local" | "extractive"; source_selector: string };
const defaultPolicy: Policy = { provider_profile: "local", source_selector: "auto" };

type UiLanguage = "en" | "ru";

const UI = {
  en: {
    newConversation: "New conversation", projects: "PROJECTS", conversations: "CONVERSATIONS", settings: "Settings", importFolder: "Import a folder", noProjects: "No projects yet", noProject: "No project", localFiles: "local files",
    providerLocal: "Local Qwen3", evidenceOnly: "Evidence only", corpusProject: "Corpus: current project", corpusAll: "Corpus: all projects", file: "File", askFiles: "Ask about imported files", welcome: "JARVIS searches the selected corpus with FTS5, multilingual FAISS and BGE reranking, then shows exact source citations.",
    summarize: "Summarize selected files", searchDocuments: "Search my documents", you: "You", grounded: "Grounded", insufficient: "Insufficient context", retrieving: "Retrieving", searching: "Searching the selected corpus", checkingChanges: "Checking project changes and Google Sheets…", noChanges: "No changes", updatedFiles: "Uploaded / updated {count} files", reindexedFiles: "Reindexed {count} files for chunking policy", removedFiles: "Archived / removed {count} files", rejectedFiles: "{count} files could not be indexed", placeholder: "Ask a question about your imported files…", upload: "Upload files", untrusted: "Imported files are untrusted context. Answers include citations.",
    corpus: "CORPUS", drop: "Drop documents, code or a project archive here", preview: "Preview", useProject: "Use project corpus", graph: "Dependency graph", selectFile: "Select an imported file to inspect its extracted text.",
    settingsTitle: "JARVIS settings", settingsSubtitle: "Local settings are kept only on this PC.", language: "Interface language", provider: "Answer mode", localModel: "Local Ollama model", googleJson: "Google service-account JSON path", googleOwner: "Google account e-mail for table access", googleConnect: "Create / connect JARVIS DB", googleConnected: "Google Sheets connected", available: "available", notConfigured: "not available", saved: "Saved locally. Local-model availability was refreshed.", desktopOnly: "JARVIS is desktop-only. Imported files and answers stay on this PC.", close: "Close", save: "Save locally", saving: "Saving…", page: "page", generalTab: "General", databaseTab: "Database", chunkingTab: "Developer chunking", archivesTab: "Archived chats", archivedEmpty: "No archived chats.", archiveConversation: "Archive conversation", restoreConversation: "Restore", globalMode: "Global mode", defaultMode: "Default", classicMode: "Classic — cleaned text", developerMode: "Developer — source structure", mixedMode: "Mixed — choose by question", chunkingHint: "Saving changes reindexes each project when it is next queried.",
  },
  ru: {
    newConversation: "Новый диалог", projects: "ПРОЕКТЫ", conversations: "ДИАЛОГИ", settings: "Настройки", importFolder: "Импортировать папку", noProjects: "Проектов пока нет", noProject: "Нет проекта", localFiles: "локальные файлы",
    providerLocal: "Локальная Qwen3", evidenceOnly: "Только источники", corpusProject: "Корпус: текущий проект", corpusAll: "Корпус: все проекты", file: "Файл", askFiles: "Задайте вопрос по импортированным файлам", welcome: "JARVIS ищет в выбранном корпусе через FTS5, многоязычный FAISS и BGE reranking, затем показывает точные ссылки на источники.",
    summarize: "Кратко изложить выбранные файлы", searchDocuments: "Поиск по документам", you: "Вы", grounded: "Ответ по источникам", insufficient: "Недостаточно контекста", retrieving: "Поиск", searching: "Поиск по выбранному корпусу", checkingChanges: "Проверка проекта и Google Sheets…", noChanges: "Изменений нет", updatedFiles: "Отправлено / обновлено файлов: {count}", reindexedFiles: "Переиндексировано файлов по политике chunks: {count}", removedFiles: "Архивировано / удалено файлов: {count}", rejectedFiles: "Не удалось проиндексировать файлов: {count}", placeholder: "Задайте вопрос по импортированным файлам…", upload: "Загрузить файлы", untrusted: "Импортированные файлы — недоверенный контекст. Ответы содержат источники.",
    corpus: "КОРПУС", drop: "Перетащите сюда документы, код или архив проекта", preview: "Предпросмотр", useProject: "Использовать весь проект", graph: "Граф зависимостей", selectFile: "Выберите импортированный файл, чтобы увидеть извлечённый текст.",
    settingsTitle: "Настройки JARVIS", settingsSubtitle: "Локальные настройки хранятся только на этом ПК.", language: "Язык интерфейса", provider: "Режим ответа", localModel: "Локальная модель Ollama", googleJson: "Путь к JSON service account Google", googleOwner: "Google e-mail для доступа к таблице", googleConnect: "Создать / подключить JARVIS DB", googleConnected: "Google Sheets подключены", available: "доступна", notConfigured: "недоступна", saved: "Сохранено локально. Доступность локальной модели обновлена.", desktopOnly: "JARVIS работает только на этом ПК. Импортированные файлы и ответы остаются локально.", close: "Закрыть", save: "Сохранить локально", saving: "Сохранение…", page: "стр.", generalTab: "Общие", databaseTab: "База данных", chunkingTab: "Нарезка chunks для разработчиков", archivesTab: "Архивированные чаты", archivedEmpty: "Архивированных чатов нет.", archiveConversation: "Архивировать чат", restoreConversation: "Восстановить", globalMode: "Глобальный режим", defaultMode: "По умолчанию", classicMode: "Classic — очищенный текст", developerMode: "Developer — исходная структура", mixedMode: "Mixed — выбор по вопросу", chunkingHint: "После сохранения каждый проект будет переиндексирован при следующем вопросе.",
  },
} as const;

export function App() {
  const [language, setLanguage] = useState<UiLanguage>(() => (localStorage.getItem("jarvis-ui-language") === "ru" ? "ru" : "en"));
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [archivedSessions, setArchivedSessions] = useState<Session[]>([]);
  const [files, setFiles] = useState<DocumentFile[]>([]);
  const [repositoryGraph, setRepositoryGraph] = useState<{ nodes: Array<{ id: string; relative_path: string }>; edges: Array<{ id: string; source_document_id: string; target_ref: string; edge_type: string }> }>({ nodes: [], edges: [] });
  const [activeProject, setActiveProject] = useState<string>();
  const [activeSession, setActiveSession] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [answer, setAnswer] = useState<RagAnswer>();
  const [selectedFile, setSelectedFile] = useState<DocumentFile>();
  const [fileContent, setFileContent] = useState<string>(UI[language].selectFile);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [syncStatus, setSyncStatus] = useState("");
  const [error, setError] = useState("");
  const [policy, setPolicy] = useState<Policy>(defaultPolicy);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState<LocalSettingsStatus>();
  const [settingsDraft, setSettingsDraft] = useState<LocalSettingsDraft>({});
  const [settingsNotice, setSettingsNotice] = useState("");
  const uploadRef = useRef<HTMLInputElement>(null);
  const text = UI[language];

  useEffect(() => { localStorage.setItem("jarvis-ui-language", language); }, [language]);
  useEffect(() => { if (!selectedFile) setFileContent(text.selectFile); }, [selectedFile, text.selectFile]);

  const refresh = useCallback(async () => {
    await api.health();
    const [nextProjects, nextSessions, nextArchived] = await Promise.all([api.projects(), api.sessions(), api.sessions(true)]);
    setProjects(nextProjects); setSessions(nextSessions); setArchivedSessions(nextArchived);
    if (!activeProject && nextProjects[0]) setActiveProject(nextProjects[0].id);
    if (!activeSession && nextSessions[0]) setActiveSession(nextSessions[0].id);
  }, [activeProject, activeSession]);

  useEffect(() => { refresh().catch((event) => setError(String(event))); }, [refresh]);
  useEffect(() => {
    let close: (() => void) | undefined;
    api.events((event) => {
      if (event.session_id && event.session_id !== activeSession) return;
      if (event.type === "chat.started") setStreaming("");
      if (event.type === "project.syncing") setSyncStatus(text.checkingChanges);
      if (event.type === "project.synced") {
        const updated = Number(event.payload.added || 0) + Number(event.payload.updated || 0);
        const reindexed = Number(event.payload.reindexed || 0);
        const removed = Number(event.payload.removed || 0);
        const rejected = Number(event.payload.rejected || 0);
        const lines = [
          updated ? text.updatedFiles.replace("{count}", String(updated)) : "",
          reindexed ? text.reindexedFiles.replace("{count}", String(reindexed)) : "",
          removed ? text.removedFiles.replace("{count}", String(removed)) : "",
          rejected ? text.rejectedFiles.replace("{count}", String(rejected)) : "",
        ].filter(Boolean);
        setSyncStatus(lines.join(" · ") || text.noChanges);
      }
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
      setProjects((items) => [project, ...items.filter((item) => item.id !== project.id)]); setActiveProject(project.id);
      await api.importProject(project.id); setFiles(await api.files(project.id)); setRepositoryGraph(await api.graph(project.id));
    } catch (event) { setError(String(event)); }
  }
  async function openSettings() { setSettingsOpen(true); setSettingsNotice(""); try { const [nextStatus, nextArchived] = await Promise.all([api.settings(), api.sessions(true)]); setSettingsStatus(nextStatus); setArchivedSessions(nextArchived); } catch (event) { setError(String(event)); } }
  async function archiveConversation(sessionId: string) {
    try {
      const archived = await api.archiveSession(sessionId);
      setSessions((items) => items.filter((item) => item.id !== sessionId));
      setArchivedSessions((items) => [archived, ...items.filter((item) => item.id !== sessionId)]);
      if (activeSession === sessionId) { const next = sessions.find((item) => item.id !== sessionId); setActiveSession(next?.id); setMessages([]); setAnswer(undefined); }
    } catch (event) { setError(String(event)); }
  }
  async function restoreConversation(sessionId: string) {
    try {
      const restored = await api.restoreSession(sessionId);
      setArchivedSessions((items) => items.filter((item) => item.id !== sessionId));
      setSessions((items) => [restored, ...items.filter((item) => item.id !== sessionId)]);
    } catch (event) { setError(String(event)); }
  }
  async function saveSettings() {
    setBusy(true); setSettingsNotice("");
    try { const next = await api.updateSettings(settingsDraft); setSettingsStatus(next); setSettingsDraft({}); setSettingsNotice(text.saved); }
    catch (event) { setSettingsNotice(String(event)); } finally { setBusy(false); }
  }
  async function connectGoogleSheets() {
    setBusy(true); setSettingsNotice("");
    try { await api.updateSettings(settingsDraft); const cloud = await api.connectGoogleSheets(); setSettingsStatus(await api.settings()); setSettingsDraft({}); setSettingsNotice(cloud?.spreadsheet_url || text.googleConnected); }
    catch (event) { setSettingsNotice(String(event)); } finally { setBusy(false); }
  }
  async function changePolicy(next: Partial<Policy>) { const value = { ...policy, ...next }; setPolicy(value); if (activeSession) await api.setPolicy(activeSession, value); }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || !activeSession || busy) return;
    const content = query.trim(); setQuery(""); setBusy(true); setStreaming(""); setSyncStatus(text.checkingChanges); setError("");
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", content, grounded: 0, metadata_json: "{}", created_at: new Date().toISOString() }]);
    try {
      const next = await api.send(activeSession, content); setAnswer(next);
      setMessages((items) => [...items, { id: next.message_id, role: "assistant", content: next.answer, grounded: Number(next.grounded), metadata_json: JSON.stringify(next), created_at: new Date().toISOString() }]);
      if (activeProject) {
        const [nextFiles, nextGraph] = await Promise.all([api.files(activeProject), api.graph(activeProject)]);
        setFiles(nextFiles); setRepositoryGraph(nextGraph);
      }
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
      <button className="primary" onClick={() => void createConversation()}><Plus size={16}/> {text.newConversation}</button>
      <Section title={text.projects} action={<button className="section-action" onClick={() => void addProject()} title={text.importFolder}><FolderGit2 size={14}/><Plus size={10}/></button>}>{projects.map((project) => <button key={project.id} className={activeProject === project.id ? "nav active" : "nav"} onClick={() => setActiveProject(project.id)}><ChevronRight size={13}/><span>{project.name}</span></button>)}{!projects.length && <p className="empty">{text.noProjects}</p>}</Section>
      <Section title={text.conversations}>{sessions.map((session) => <div className={activeSession === session.id ? "nav-row active" : "nav-row"} key={session.id}><button className="nav" onClick={() => setActiveSession(session.id)}><CircleDot size={12}/><span>{session.title}</span></button><button className="archive-button" title={text.archiveConversation} onClick={() => void archiveConversation(session.id)}><Archive size={13}/></button></div>)}</Section>
      <button className="settings" onClick={() => void openSettings()}><Settings size={16}/> {text.settings}</button>
    </aside>
    <section className="workspace">
      <header className="toolbar"><div className="crumb"><Bot size={17}/><span>{projects.find((project) => project.id === activeProject)?.name || text.noProject}</span><span className="branch"><GitBranch size={13}/> {text.localFiles}</span></div><div className="controls"><select aria-label={text.language} value={language} onChange={(event) => setLanguage(event.target.value as UiLanguage)}><option value="en">English</option><option value="ru">Русский</option></select><select value={policy.provider_profile} onChange={(event) => void changePolicy({ provider_profile: event.target.value as Policy["provider_profile"] })}><option value="local">{text.providerLocal}</option><option value="extractive">{text.evidenceOnly}</option></select><select value={policy.source_selector} onChange={(event) => void changePolicy({ source_selector: event.target.value })}><option value="auto">{text.corpusProject}</option><option value="all">{text.corpusAll}</option>{files.map((file) => <option value={file.relative_path} key={file.id}>{text.file}: {file.relative_path}</option>)}</select></div></header>
      <div className="content-grid">
        <section className="chat-panel"><div className="timeline">
          {!messages.length && <div className="welcome"><div className="hero-icon"><Sparkles/></div><h1>{text.askFiles}</h1><p>{text.welcome}</p><div className="suggestions"><button onClick={() => setQuery(language === "ru" ? "Кратко изложи главную информацию в выбранных файлах и укажи источники." : "Summarize the most important information in the selected files and cite it.")}>{text.summarize}</button><button onClick={() => setQuery(language === "ru" ? "Что сказано в этих файлах о главной теме? Укажи источник." : "What do these files say about the main topic? Cite the source.")}>{text.searchDocuments}</button></div></div>}
          {messages.map((message) => <article key={message.id} className={`message ${message.role}`}><div className="avatar">{message.role === "user" ? "YOU" : "JR"}</div><div><div className="message-meta">{message.role === "user" ? text.you : "JARVIS"}{message.role === "assistant" && <span className={message.grounded ? "grounded" : "general"}>{message.grounded ? text.grounded : text.insufficient}</span>}</div><div className="message-body">{message.content}</div>{message.role === "assistant" && answer?.message_id === message.id && <Citations items={answer.citations} language={language}/>}</div></article>)}
          {busy && streaming && <article className="message assistant"><div className="avatar">JR</div><div><div className="message-meta">JARVIS <span className="grounded">{text.retrieving}</span></div><div className="message-body">{streaming}</div></div></article>}
          {busy && !streaming && <div className="thinking"><span/><span/><span/> {syncStatus || text.searching}</div>}
        </div>{error && <div className="error"><span>{error}</span><button onClick={() => setError("")}><X size={14}/></button></div>}<form className="composer" onSubmit={send}><textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder={text.placeholder} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}/><div className="composer-actions"><button type="button" className="icon" onClick={() => uploadRef.current?.click()} title={text.upload}><FilePlus2 size={17}/></button><span>{text.untrusted}</span><button className="send" disabled={busy || !activeSession}><Send size={16}/></button></div></form><input ref={uploadRef} hidden type="file" multiple onChange={(event) => event.target.files && void handleFiles(event.target.files)}/></section>
        <aside className="project-panel"><div className="panel-title"><span><Code2 size={15}/> {text.corpus}</span><button onClick={() => uploadRef.current?.click()}><Upload size={14}/></button></div><div className="file-tree">{files.map((file) => <button key={file.id} className={selectedFile?.id === file.id ? "file-row selected" : "file-row"} onClick={() => void openFile(file)}><File size={14}/><span>{file.relative_path}</span><small>{Math.ceil(file.size_bytes / 1024)} KB</small></button>)}{!files.length && <div className="drop-zone"><Upload size={22}/><span>{text.drop}</span></div>}</div><div className="editor-title"><span>{selectedFile?.relative_path || text.preview}</span>{selectedFile && <button onClick={() => void changePolicy({ source_selector: "auto" })}>{text.useProject}</button>}</div><div className="editor"><Editor height="100%" theme="vs-dark" value={fileContent} language={selectedFile?.language || "plaintext"} options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, wordWrap: "on", scrollBeyondLastLine: false }}/></div></aside>
      </div>
      <section className="bottom-panel"><div className="bottom-tabs"><button className="active"><Network size={14}/> {text.graph}</button><button className="collapse"><PanelBottom size={14}/></button></div><div className="graph"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView><Background color="#292e3a"/><Controls/></ReactFlow></div></section>
    </section>
    {settingsOpen && <SettingsModal language={language} policy={policy} status={settingsStatus} draft={settingsDraft} notice={settingsNotice} busy={busy} archivedSessions={archivedSessions} onPolicy={changePolicy} onDraft={setSettingsDraft} onSave={saveSettings} onConnectGoogle={connectGoogleSheets} onRestore={restoreConversation} onClose={() => setSettingsOpen(false)}/>}
  </main>;
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="side-section"><div className="section-label"><span>{title}</span>{action}</div><div className="section-items">{children}</div></section>; }
function Citations({ items, language }: { items: Citation[]; language: UiLanguage }) { if (!items.length) return null; return <div className="citations">{items.map((item) => <button key={item.chunk_id}><File size={12}/><span>{item.source_path}{item.page ? ` · ${UI[language].page} ${item.page}` : ""}{item.line_start ? ` · L${item.line_start}${item.line_end ? `–${item.line_end}` : ""}` : ""}{item.sheet ? ` · ${item.sheet} ${item.cell_range || ""}` : ""}</span></button>)}</div>; }

function SettingsModal({ language, policy, status, draft, notice, busy, archivedSessions, onPolicy, onDraft, onSave, onConnectGoogle, onRestore, onClose }: { language: UiLanguage; policy: Policy; status?: LocalSettingsStatus; draft: LocalSettingsDraft; notice: string; busy: boolean; archivedSessions: Session[]; onPolicy: (next: Partial<Policy>) => Promise<void>; onDraft: (next: LocalSettingsDraft) => void; onSave: () => Promise<void>; onConnectGoogle: () => Promise<void>; onRestore: (sessionId: string) => Promise<void>; onClose: () => void }) {
  const [tab, setTab] = useState<"general" | "database" | "chunking" | "archives">("general");
  const update = (name: keyof LocalSettingsDraft, value: string) => onDraft({ ...draft, [name]: value });
  const text = UI[language];
  const categories: Array<[ChunkingCategory, string]> = [
    ["code", "Code"], ["web_markup", "Web markup (HTML/XML)"], ["config_data", "Config / data"],
    ["documents", "Documents (PDF/DOCX/PPTX)"], ["tables", "Tables (XLSX/CSV)"], ["notebooks", "Notebooks"], ["plain_text", "Plain text"],
  ];
  const modeOptions = (includeDefault: boolean) => <>{includeDefault && <option value="default">{text.defaultMode}</option>}<option value="classic">{text.classicMode}</option><option value="developer">{text.developerMode}</option><option value="mixed">{text.mixedMode}</option></>;
  const categoryValue = (category: ChunkingCategory) => draft[`chunking_${category}`] ?? status?.chunking?.[category] ?? "default";
  return <div className="modal-backdrop" onClick={onClose}><section className="modal settings-modal" onClick={(event) => event.stopPropagation()}>
    <header><div><h2>{text.settingsTitle}</h2><small>{text.settingsSubtitle}</small></div><button onClick={onClose}><X/></button></header>
    <div className="settings-layout"><nav className="settings-tabs"><button className={tab === "general" ? "active" : ""} onClick={() => setTab("general")}><Settings size={14}/>{text.generalTab}</button><button className={tab === "database" ? "active" : ""} onClick={() => setTab("database")}><Database size={14}/>{text.databaseTab}</button><button className={tab === "chunking" ? "active" : ""} onClick={() => setTab("chunking")}><SlidersHorizontal size={14}/>{text.chunkingTab}</button><button className={tab === "archives" ? "active" : ""} onClick={() => setTab("archives")}><Archive size={14}/>{text.archivesTab}</button></nav><div className="settings-content">
      {tab === "general" && <><div className="provider-status">{Object.entries(status?.providers || {}).map(([name, value]) => <span key={name} className={value.available ? "available" : "unavailable"}><i/>{name}: {value.available ? text.available : text.notConfigured}</span>)}</div><div className="settings-grid"><label>{text.provider}<select value={policy.provider_profile} onChange={(event) => void onPolicy({ provider_profile: event.target.value as Policy["provider_profile"] })}><option value="local">{text.providerLocal}</option><option value="extractive">{text.evidenceOnly}</option></select></label><label>{text.localModel}<input value={draft.ollama_model ?? status?.models.local ?? "qwen3:14b"} onChange={(event) => update("ollama_model", event.target.value)}/></label></div></>}
      {tab === "database" && <><div className="settings-grid"><label>{text.googleJson}<input value={draft.google_service_account_path ?? ""} placeholder="C:\\private\\jarvis-service-account.json" onChange={(event) => update("google_service_account_path", event.target.value)}/></label><label>{text.googleOwner}<input value={draft.google_owner_email ?? ""} placeholder="name@gmail.com" onChange={(event) => update("google_owner_email", event.target.value)}/></label></div>{status?.google_sheets?.connected && <p className="settings-notice">{text.googleConnected}</p>}<button className="ghost settings-connect" disabled={busy} onClick={() => void onConnectGoogle()}>{text.googleConnect}</button></>}
      {tab === "chunking" && <div className="settings-grid"><label>{text.globalMode}<select value={draft.chunking_global_mode ?? status?.chunking?.global_mode ?? "classic"} onChange={(event) => update("chunking_global_mode", event.target.value as ChunkingMode)}>{modeOptions(false)}</select></label>{categories.map(([category, label]) => <label key={category}>{label}<select value={categoryValue(category)} onChange={(event) => update(`chunking_${category}` as keyof LocalSettingsDraft, event.target.value as ChunkingCategoryMode)}>{modeOptions(true)}</select></label>)}<p className="settings-notice">{text.chunkingHint}</p></div>}
      {tab === "archives" && <div className="archive-list">{archivedSessions.length ? archivedSessions.map((session) => <div className="archive-item" key={session.id}><div><strong>{session.title}</strong><small>{new Date(session.archived_at || session.updated_at).toLocaleString(language === "ru" ? "ru-RU" : "en-US")}</small></div><button className="ghost" onClick={() => void onRestore(session.id)}><ArchiveRestore size={14}/>{text.restoreConversation}</button></div>) : <p className="empty">{text.archivedEmpty}</p>}</div>}
      {notice && <p className="settings-notice">{notice}</p>}<p>{text.desktopOnly}</p>
    </div></div><footer><button className="ghost" onClick={onClose}>{text.close}</button>{tab !== "archives" && <button className="primary" disabled={busy} onClick={() => void onSave()}>{busy ? text.saving : text.save}</button>}</footer>
  </section></div>;
}
