import { open } from "@tauri-apps/plugin-dialog";
import { Archive, ArchiveRestore, ArrowLeft, Bot, ChevronDown, ChevronRight, CircleDot, Database, File, FilePlus2, Folder, FolderGit2, GitBranch, MoreHorizontal, Pencil, Plus, Search, Send, Settings, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { ChunkingCategory, ChunkingCategoryMode, ChunkingMode, Citation, DocumentFile, LocalSettingsDraft, LocalSettingsStatus, Message, Project, RagAnswer, Session } from "./types";

type Policy = { provider_profile: "local" | "extractive"; source_selector: string };
const defaultPolicy: Policy = { provider_profile: "local", source_selector: "auto" };

type UiLanguage = "en" | "ru";

const UI = {
  en: {
    newConversation: "New conversation", projects: "PROJECTS", conversations: "CONVERSATIONS", settings: "Settings", importFolder: "Import a folder", noProjects: "No projects yet", noProject: "No project", localFiles: "local files", backToApp: "Back to JARVIS", searchSettings: "Search settings…", modelRagTab: "Model & RAG", renameConversation: "Rename", renamePrompt: "Conversation name", projectHasNoChats: "No conversations yet", settingsNoResults: "No settings found",
    providerLocal: "Local Qwen3", evidenceOnly: "Evidence only", corpusProject: "Corpus: current project", corpusAll: "Corpus: all projects", file: "File", askFiles: "Ask about imported files", welcome: "JARVIS searches the selected corpus with FTS5, multilingual FAISS and BGE reranking, then shows exact source citations.",
    summarize: "Summarize selected files", searchDocuments: "Search my documents", you: "You", grounded: "Grounded", insufficient: "Insufficient context", retrieving: "Retrieving", searching: "Searching the selected corpus", checkingChanges: "Checking project changes and Google Sheets…", noChanges: "No changes", updatedFiles: "Uploaded / updated {count} files", reindexedFiles: "Reindexed {count} files for chunking policy", removedFiles: "Archived / removed {count} files", rejectedFiles: "{count} files could not be indexed", placeholder: "Ask a question about your imported files…", upload: "Upload files", untrusted: "Imported files are untrusted context. Answers include citations.",
    loadingConversation: "Loading conversation…",
    settingsTitle: "JARVIS settings", settingsSubtitle: "Local settings are kept only on this PC.", language: "Interface language", provider: "Answer mode", localModel: "Local Ollama model", googleJson: "Google service-account JSON path", googleOwner: "Google account e-mail for table access", googleConnect: "Create / connect JARVIS DB", googleConnected: "Google Sheets connected", available: "available", notConfigured: "not available", saved: "Saved locally. Local-model availability was refreshed.", desktopOnly: "JARVIS is desktop-only. Imported files and answers stay on this PC.", close: "Close", save: "Save locally", saving: "Saving…", page: "page", generalTab: "General", databaseTab: "Database", chunkingTab: "Developer chunking", archivesTab: "Archived chats", archivedEmpty: "No archived chats.", archiveConversation: "Archive conversation", restoreConversation: "Restore", globalMode: "Global mode", defaultMode: "Default", classicMode: "Classic — cleaned text", developerMode: "Developer — source structure", mixedMode: "Mixed — choose by question", chunkingHint: "Saving changes reindexes each project when it is next queried.",
  },
  ru: {
    newConversation: "Новый диалог", projects: "ПРОЕКТЫ", conversations: "ДИАЛОГИ", settings: "Настройки", importFolder: "Импортировать папку", noProjects: "Проектов пока нет", noProject: "Нет проекта", localFiles: "локальные файлы", backToApp: "Вернуться в JARVIS", searchSettings: "Поиск настроек…", modelRagTab: "Модель и RAG", renameConversation: "Переименовать", renamePrompt: "Название чата", projectHasNoChats: "Диалогов пока нет", settingsNoResults: "Настройки не найдены",
    providerLocal: "Локальная Qwen3", evidenceOnly: "Только источники", corpusProject: "Корпус: текущий проект", corpusAll: "Корпус: все проекты", file: "Файл", askFiles: "Задайте вопрос по импортированным файлам", welcome: "JARVIS ищет в выбранном корпусе через FTS5, многоязычный FAISS и BGE reranking, затем показывает точные ссылки на источники.",
    summarize: "Кратко изложить выбранные файлы", searchDocuments: "Поиск по документам", you: "Вы", grounded: "Ответ по источникам", insufficient: "Недостаточно контекста", retrieving: "Поиск", searching: "Поиск по выбранному корпусу", checkingChanges: "Проверка проекта и Google Sheets…", noChanges: "Изменений нет", updatedFiles: "Отправлено / обновлено файлов: {count}", reindexedFiles: "Переиндексировано файлов по политике chunks: {count}", removedFiles: "Архивировано / удалено файлов: {count}", rejectedFiles: "Не удалось проиндексировать файлов: {count}", placeholder: "Задайте вопрос по импортированным файлам…", upload: "Загрузить файлы", untrusted: "Импортированные файлы — недоверенный контекст. Ответы содержат источники.",
    loadingConversation: "Загрузка диалога…",
    settingsTitle: "Настройки JARVIS", settingsSubtitle: "Локальные настройки хранятся только на этом ПК.", language: "Язык интерфейса", provider: "Режим ответа", localModel: "Локальная модель Ollama", googleJson: "Путь к JSON service account Google", googleOwner: "Google e-mail для доступа к таблице", googleConnect: "Создать / подключить JARVIS DB", googleConnected: "Google Sheets подключены", available: "доступна", notConfigured: "недоступна", saved: "Сохранено локально. Доступность локальной модели обновлена.", desktopOnly: "JARVIS работает только на этом ПК. Импортированные файлы и ответы остаются локально.", close: "Закрыть", save: "Сохранить локально", saving: "Сохранение…", page: "стр.", generalTab: "Общие", databaseTab: "База данных", chunkingTab: "Нарезка chunks для разработчиков", archivesTab: "Архивированные чаты", archivedEmpty: "Архивированных чатов нет.", archiveConversation: "Архивировать чат", restoreConversation: "Восстановить", globalMode: "Глобальный режим", defaultMode: "По умолчанию", classicMode: "Classic — очищенный текст", developerMode: "Developer — исходная структура", mixedMode: "Mixed — выбор по вопросу", chunkingHint: "После сохранения каждый проект будет переиндексирован при следующем вопросе.",
  },
} as const;

function sessionBelongsToProject(session: Session, project: Project): boolean {
  return (project.alias_ids?.length ? project.alias_ids : [project.id]).includes(session.project_id || "");
}

export function App() {
  const [language, setLanguage] = useState<UiLanguage>(() => (localStorage.getItem("jarvis-ui-language") === "ru" ? "ru" : "en"));
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [archivedSessions, setArchivedSessions] = useState<Session[]>([]);
  const [files, setFiles] = useState<DocumentFile[]>([]);
  const [activeProject, setActiveProject] = useState<string>();
  const [activeSession, setActiveSession] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [answer, setAnswer] = useState<RagAnswer>();
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
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem("jarvis-expanded-projects") || "[]") as string[]); }
    catch { return new Set(); }
  });
  const [sessionMenu, setSessionMenu] = useState<string>();
  const uploadRef = useRef<HTMLInputElement>(null);
  const activeSessionRef = useRef<string | undefined>(undefined);
  const text = UI[language];

  useEffect(() => { localStorage.setItem("jarvis-ui-language", language); }, [language]);
  useEffect(() => { localStorage.setItem("jarvis-expanded-projects", JSON.stringify([...expandedProjects])); }, [expandedProjects]);
  useEffect(() => { activeSessionRef.current = activeSession; }, [activeSession]);
  useEffect(() => {
    if (!activeProject) return;
    setExpandedProjects((current) => current.has(activeProject) ? current : new Set(current).add(activeProject));
  }, [activeProject]);
  const refresh = useCallback(async () => {
    await api.health();
    const [nextProjects, nextSessions, nextArchived] = await Promise.all([api.projects(), api.sessions(), api.sessions(true)]);
    setProjects(nextProjects); setSessions(nextSessions); setArchivedSessions(nextArchived);
    setActiveProject((current) => current || nextProjects[0]?.id);
    setActiveSession((current) => current || nextSessions[0]?.id);
  }, []);

  useEffect(() => { refresh().catch((event) => setError(String(event))); }, [refresh]);
  useEffect(() => {
    let close: (() => void) | undefined;
    let cancelled = false;
    api.events((event) => {
      if (event.session_id && event.session_id !== activeSessionRef.current) return;
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
    }).then((value) => { if (cancelled) value(); else close = value; }).catch(() => undefined);
    return () => { cancelled = true; close?.(); };
  }, [text.checkingChanges, text.noChanges, text.reindexedFiles, text.rejectedFiles, text.removedFiles, text.updatedFiles]);
  useEffect(() => {
    if (!activeProject) { setFiles([]); return; }
    api.files(activeProject)
      .then(setFiles)
      .catch((event) => setError(String(event)));
  }, [activeProject]);
  useEffect(() => {
    let cancelled = false;
    setMessages([]);
    setAnswer(undefined);
    setStreaming("");
    setSyncStatus("");
    setError("");
    setLoadingMessages(Boolean(activeSession));
    if (!activeSession) return () => { cancelled = true; };
    api.messages(activeSession)
      .then((nextMessages) => {
        if (!cancelled) { setMessages(nextMessages); setLoadingMessages(false); }
      })
      .catch((event) => {
        if (!cancelled) { setError(String(event)); setLoadingMessages(false); }
      });
    return () => { cancelled = true; };
  }, [activeSession]);

  async function createConversation() {
    if (!activeProject) { setError("Create or select a project first."); return; }
    try {
      const session = await api.createSession(activeProject);
      setSessions((items) => [session, ...items]); setActiveSession(session.id); setMessages([]); setAnswer(undefined); setPolicy(defaultPolicy);
    } catch (event) { setError(String(event)); }
  }
  async function addProject() {
    try {
      const selected = await open({ directory: true, multiple: false, title: "Select a document folder or repository" });
      if (!selected || Array.isArray(selected)) return;
      const name = selected.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "Imported project";
      const project = await api.createProject(name, selected);
      setActiveProject(project.id);
      await api.importProject(project.id);
      const [nextProjects, nextFiles] = await Promise.all([api.projects(), api.files(project.id)]);
      setProjects(nextProjects); setFiles(nextFiles);
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
  async function renameConversation(session: Session) {
    setSessionMenu(undefined);
    const requested = window.prompt(text.renamePrompt, session.title);
    if (requested === null) return;
    try {
      const renamed = await api.renameSession(session.id, requested);
      setSessions((items) => items.map((item) => item.id === renamed.id ? renamed : item));
      setArchivedSessions((items) => items.map((item) => item.id === renamed.id ? renamed : item));
    } catch (event) { setError(String(event)); }
  }
  function toggleProject(projectId: string) {
    setActiveProject(projectId);
    setExpandedProjects((current) => {
      const next = new Set(current);
      if (next.has(projectId)) next.delete(projectId); else next.add(projectId);
      return next;
    });
  }
  function selectConversation(projectId: string, sessionId: string) {
    setSessionMenu(undefined);
    setActiveProject(projectId);
    activeSessionRef.current = sessionId;
    setActiveSession(sessionId);
    setPolicy(defaultPolicy);
    void api.setPolicy(sessionId, defaultPolicy).catch((event) => setError(String(event)));
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
      if (activeProject) setFiles(await api.files(activeProject));
    } catch (event) { setError(String(event)); } finally { setBusy(false); setStreaming(""); }
  }
  async function handleFiles(list: FileList | File[]) {
    if (!activeProject) { setError("Create or select a project first."); return; }
    setBusy(true);
    try { for (const file of Array.from(list)) await api.upload(activeProject, file); setFiles(await api.files(activeProject)); }
    catch (event) { setError(String(event)); } finally { setBusy(false); }
  }
  if (settingsOpen) {
    return <SettingsPage language={language} onLanguage={setLanguage} policy={policy} projects={projects} status={settingsStatus} draft={settingsDraft} notice={settingsNotice} busy={busy} archivedSessions={archivedSessions} onPolicy={changePolicy} onDraft={setSettingsDraft} onSave={saveSettings} onConnectGoogle={connectGoogleSheets} onRestore={restoreConversation} onClose={() => setSettingsOpen(false)}/>;
  }

  return <main className="app" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void handleFiles(event.dataTransfer.files); }}>
    <aside className="sidebar">
      <div className="brand"><div className="mark"><Sparkles size={16}/></div><div><strong>JARVIS</strong><span>DESKTOP RAG</span></div></div>
      <button className="primary" onClick={() => void createConversation()}><Plus size={16}/> {text.newConversation}</button>
      <Section title={text.projects} action={<button className="section-action" onClick={() => void addProject()} title={text.importFolder}><FolderGit2 size={14}/><Plus size={10}/></button>}>{projects.map((project) => { const expanded = expandedProjects.has(project.id); const projectSessions = sessions.filter((session) => sessionBelongsToProject(session, project)); return <div className="project-group" key={project.id}><button className={activeProject === project.id ? "project-nav active" : "project-nav"} onClick={() => toggleProject(project.id)}>{expanded ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}<Folder size={13}/><span>{project.name}</span></button>{expanded && <div className="project-chats">{projectSessions.map((session) => <div className={activeSession === session.id ? "chat-row active" : "chat-row"} key={session.id}><button className="chat-nav" onClick={() => selectConversation(project.id, session.id)}><CircleDot size={10}/><span>{session.title}</span></button><button className="more-button" aria-label={`${session.title} menu`} onClick={() => setSessionMenu((current) => current === session.id ? undefined : session.id)}><MoreHorizontal size={13}/></button>{sessionMenu === session.id && <div className="session-menu"><button onClick={() => void renameConversation(session)}><Pencil size={13}/>{text.renameConversation}</button><button onClick={() => { setSessionMenu(undefined); void archiveConversation(session.id); }}><Archive size={13}/>{text.archiveConversation}</button></div>}</div>)}{!projectSessions.length && <p className="project-empty">{text.projectHasNoChats}</p>}</div>}</div>; })}{!projects.length && <p className="empty">{text.noProjects}</p>}</Section>
      <button className="settings" onClick={() => void openSettings()}><Settings size={16}/> {text.settings}</button>
    </aside>
    <section className="workspace">
      <header className="toolbar"><div className="crumb"><Bot size={17}/><span>{projects.find((project) => project.id === activeProject)?.name || text.noProject}</span><span className="branch"><GitBranch size={13}/> {text.localFiles}</span></div><div className="controls"><select aria-label={text.language} value={language} onChange={(event) => setLanguage(event.target.value as UiLanguage)}><option value="en">English</option><option value="ru">Русский</option></select><select value={policy.provider_profile} onChange={(event) => void changePolicy({ provider_profile: event.target.value as Policy["provider_profile"] })}><option value="local">{text.providerLocal}</option><option value="extractive">{text.evidenceOnly}</option></select><select value={policy.source_selector} onChange={(event) => void changePolicy({ source_selector: event.target.value })}><option value="auto">{text.corpusProject}</option><option value="all">{text.corpusAll}</option>{files.map((file) => <option value={file.relative_path} key={file.id}>{text.file}: {file.relative_path}</option>)}</select></div></header>
      <div className="content-grid">
        <section className="chat-panel"><div className="timeline">
          {loadingMessages && <div className="thinking"><span/><span/><span/> {text.loadingConversation}</div>}
          {!loadingMessages && !messages.length && <div className="welcome"><div className="hero-icon"><Sparkles/></div><h1>{text.askFiles}</h1><p>{text.welcome}</p><div className="suggestions"><button onClick={() => setQuery(language === "ru" ? "Кратко изложи главную информацию в выбранных файлах и укажи источники." : "Summarize the most important information in the selected files and cite it.")}>{text.summarize}</button><button onClick={() => setQuery(language === "ru" ? "Что сказано в этих файлах о главной теме? Укажи источник." : "What do these files say about the main topic? Cite the source.")}>{text.searchDocuments}</button></div></div>}
          {messages.map((message) => <article key={message.id} className={`message ${message.role}`}><div className="avatar">{message.role === "user" ? "YOU" : "JR"}</div><div><div className="message-meta">{message.role === "user" ? text.you : "JARVIS"}{message.role === "assistant" && <span className={message.grounded ? "grounded" : "general"}>{message.grounded ? text.grounded : text.insufficient}</span>}</div><div className="message-body">{message.content}</div>{message.role === "assistant" && answer?.message_id === message.id && <Citations items={answer.citations} language={language}/>}</div></article>)}
          {busy && streaming && <article className="message assistant"><div className="avatar">JR</div><div><div className="message-meta">JARVIS <span className="grounded">{text.retrieving}</span></div><div className="message-body">{streaming}</div></div></article>}
          {busy && !streaming && <div className="thinking"><span/><span/><span/> {syncStatus || text.searching}</div>}
        </div>{error && <div className="error"><span>{error}</span><button onClick={() => setError("")}><X size={14}/></button></div>}<form className="composer" onSubmit={send}><textarea value={query} onChange={(event) => setQuery(event.target.value)} placeholder={text.placeholder} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}/><div className="composer-actions"><button type="button" className="icon" onClick={() => uploadRef.current?.click()} title={text.upload}><FilePlus2 size={17}/></button><span>{text.untrusted}</span><button className="send" disabled={busy || !activeSession}><Send size={16}/></button></div></form><input ref={uploadRef} hidden type="file" multiple onChange={(event) => event.target.files && void handleFiles(event.target.files)}/></section>
      </div>
    </section>
  </main>;
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="side-section"><div className="section-label"><span>{title}</span>{action}</div><div className="section-items">{children}</div></section>; }
function Citations({ items, language }: { items: Citation[]; language: UiLanguage }) { if (!items.length) return null; return <div className="citations">{items.map((item) => <button key={item.chunk_id}><File size={12}/><span>{item.source_path}{item.page ? ` · ${UI[language].page} ${item.page}` : ""}{item.line_start ? ` · L${item.line_start}${item.line_end ? `–${item.line_end}` : ""}` : ""}{item.sheet ? ` · ${item.sheet} ${item.cell_range || ""}` : ""}</span></button>)}</div>; }

function SettingsPage({ language, onLanguage, policy, projects, status, draft, notice, busy, archivedSessions, onPolicy, onDraft, onSave, onConnectGoogle, onRestore, onClose }: { language: UiLanguage; onLanguage: (language: UiLanguage) => void; policy: Policy; projects: Project[]; status?: LocalSettingsStatus; draft: LocalSettingsDraft; notice: string; busy: boolean; archivedSessions: Session[]; onPolicy: (next: Partial<Policy>) => Promise<void>; onDraft: (next: LocalSettingsDraft) => void; onSave: () => Promise<void>; onConnectGoogle: () => Promise<void>; onRestore: (sessionId: string) => Promise<void>; onClose: () => void }) {
  type SettingsTab = "general" | "model" | "database" | "chunking" | "archives";
  const [tab, setTab] = useState<SettingsTab>("general");
  const [search, setSearch] = useState("");
  const update = (name: keyof LocalSettingsDraft, value: string) => onDraft({ ...draft, [name]: value });
  const text = UI[language];
  const categories: Array<[ChunkingCategory, string]> = [
    ["code", "Code"], ["web_markup", "Web markup (HTML/XML)"], ["config_data", "Config / data"],
    ["documents", "Documents (PDF/DOCX/PPTX)"], ["tables", "Tables (XLSX/CSV)"], ["notebooks", "Notebooks"], ["plain_text", "Plain text"],
  ];
  const modeOptions = (includeDefault: boolean) => <>{includeDefault && <option value="default">{text.defaultMode}</option>}<option value="classic">{text.classicMode}</option><option value="developer">{text.developerMode}</option><option value="mixed">{text.mixedMode}</option></>;
  const categoryValue = (category: ChunkingCategory) => draft[`chunking_${category}`] ?? status?.chunking?.[category] ?? "default";
  const navItems: Array<{ id: SettingsTab; label: string; icon: React.ReactNode }> = [
    { id: "general", label: text.generalTab, icon: <Settings size={14}/> },
    { id: "model", label: text.modelRagTab, icon: <Bot size={14}/> },
    { id: "database", label: text.databaseTab, icon: <Database size={14}/> },
    { id: "chunking", label: text.chunkingTab, icon: <SlidersHorizontal size={14}/> },
    { id: "archives", label: text.archivesTab, icon: <Archive size={14}/> },
  ];
  const visibleNav = navItems.filter((item) => item.label.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const activeLabel = navItems.find((item) => item.id === tab)?.label || text.settingsTitle;
  const archiveGroups = projects.map((project) => ({ project, sessions: archivedSessions.filter((session) => sessionBelongsToProject(session, project)) })).filter((group) => group.sessions.length);
  const knownArchiveIds = new Set(archiveGroups.flatMap((group) => group.sessions.map((session) => session.id)));
  const orphanArchives = archivedSessions.filter((session) => !knownArchiveIds.has(session.id));
  return <main className="settings-page">
    <aside className="settings-sidebar">
      <button className="settings-back" onClick={onClose}><ArrowLeft size={14}/>{text.backToApp}</button>
      <div className="settings-search"><Search size={14}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={text.searchSettings}/></div>
      <small>JARVIS</small>
      <nav>{visibleNav.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>{item.icon}{item.label}</button>)}</nav>
      {!visibleNav.length && <p className="settings-empty">{text.settingsNoResults}</p>}
    </aside>
    <section className="settings-main"><div className="settings-main-inner"><header><h1>{activeLabel}</h1><p>{text.settingsSubtitle}</p></header>
      {tab === "general" && <div className="settings-card"><label>{text.language}<select value={language} onChange={(event) => onLanguage(event.target.value as UiLanguage)}><option value="en">English</option><option value="ru">Русский</option></select></label><p>{text.desktopOnly}</p></div>}
      {tab === "model" && <div className="settings-card"><div className="provider-status">{Object.entries(status?.providers || {}).map(([name, value]) => <span key={name} className={value.available ? "available" : "unavailable"}><i/>{name}: {value.available ? text.available : text.notConfigured}</span>)}</div><div className="settings-grid"><label>{text.provider}<select value={policy.provider_profile} onChange={(event) => void onPolicy({ provider_profile: event.target.value as Policy["provider_profile"] })}><option value="local">{text.providerLocal}</option><option value="extractive">{text.evidenceOnly}</option></select></label><label>{text.localModel}<input value={draft.ollama_model ?? status?.models.local ?? "qwen3:14b"} onChange={(event) => update("ollama_model", event.target.value)}/></label></div></div>}
      {tab === "database" && <div className="settings-card"><div className="settings-grid"><label>{text.googleJson}<input value={draft.google_service_account_path ?? ""} placeholder="C:\\private\\jarvis-service-account.json" onChange={(event) => update("google_service_account_path", event.target.value)}/></label><label>{text.googleOwner}<input value={draft.google_owner_email ?? ""} placeholder="name@gmail.com" onChange={(event) => update("google_owner_email", event.target.value)}/></label></div>{status?.google_sheets?.connected && <p className="settings-notice">{text.googleConnected}</p>}<button className="ghost settings-connect" disabled={busy} onClick={() => void onConnectGoogle()}>{text.googleConnect}</button></div>}
      {tab === "chunking" && <div className="settings-card"><div className="settings-grid"><label>{text.globalMode}<select value={draft.chunking_global_mode ?? status?.chunking?.global_mode ?? "classic"} onChange={(event) => update("chunking_global_mode", event.target.value as ChunkingMode)}>{modeOptions(false)}</select></label>{categories.map(([category, label]) => <label key={category}>{label}<select value={categoryValue(category)} onChange={(event) => update(`chunking_${category}` as keyof LocalSettingsDraft, event.target.value as ChunkingCategoryMode)}>{modeOptions(true)}</select></label>)}</div><p className="settings-notice">{text.chunkingHint}</p></div>}
      {tab === "archives" && <div className="archive-groups">{archiveGroups.map(({ project, sessions }) => <section key={project.id}><h2><Folder size={14}/>{project.name}</h2><div className="archive-list">{sessions.map((session) => <ArchiveRow key={session.id} session={session} language={language} label={text.restoreConversation} onRestore={onRestore}/>)}</div></section>)}{orphanArchives.length > 0 && <section><h2>{text.noProject}</h2><div className="archive-list">{orphanArchives.map((session) => <ArchiveRow key={session.id} session={session} language={language} label={text.restoreConversation} onRestore={onRestore}/>)}</div></section>}{!archivedSessions.length && <p className="empty">{text.archivedEmpty}</p>}</div>}
      {notice && <p className="settings-notice">{notice}</p>}
      {tab !== "general" && tab !== "archives" && <div className="settings-actions"><button className="primary" disabled={busy} onClick={() => void onSave()}>{busy ? text.saving : text.save}</button></div>}
    </div></section>
  </main>;
}

function ArchiveRow({ session, language, label, onRestore }: { session: Session; language: UiLanguage; label: string; onRestore: (sessionId: string) => Promise<void> }) {
  return <div className="archive-item"><div><strong>{session.title}</strong><small>{new Date(session.archived_at || session.updated_at).toLocaleString(language === "ru" ? "ru-RU" : "en-US")}</small></div><button className="ghost" onClick={() => void onRestore(session.id)}><ArchiveRestore size={14}/>{label}</button></div>;
}
