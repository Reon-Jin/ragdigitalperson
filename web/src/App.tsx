import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { DashboardWorkspace } from "./components/DashboardWorkspace";
import { LibraryWorkspace } from "./components/LibraryWorkspace";
import { createApi } from "./lib/api";
import { formatTimeLabel, joinTags, num, pct, splitTags, toneClass, turnover } from "./lib/format";
import { renderMarkdown } from "./lib/markdown";
import { ACTIVE_CONV_KEY, AVATAR_VOICE_KEY, TOKEN_KEY } from "./lib/storage";
import type {
  AgentMemory,
  AnalysisCard,
  AnalysisMode,
  DeskSource,
  AuthUser,
  CitationItem,
  ConversationMessage,
  ConversationSession,
  ConversationSummary,
  DashboardOverview,
  DocumentDetail,
  HealthPayload,
  IngestionJob,
  LibraryFileItem,
  LocalAvatarProfile,
  ModelItem,
  SecurityPayload,
  StreamBaseEvent,
  StreamCardsEvent,
  StreamCitationsEvent,
  StreamConversationEvent,
  StreamDeltaEvent,
  StreamEvent,
  StreamFinalEvent,
  StreamRouteEvent,
  TaskType,
  UserProfile,
} from "./types";

type ThemeMode = "dark" | "light";

const MAX_HISTORY = 8;
const STATUS_LIMIT = 6;
const DEFAULT_SUMMARY_TITLE = "等待分析";
const DEFAULT_SUMMARY_TEXT = "输入问题或证券代码，系统会生成结构化投资分析。";
const DEFAULT_RISK_ITEM = "等待系统生成风险提示";
const DEFAULT_STATUS_ITEM = "Desk ready";
const QUICK_PROMPTS = [
  "结合当前市场情绪，今天最值得继续跟踪的方向是什么？",
  "围绕我最近关注的股票，给我一个更偏专业风格的投资判断。",
  "如果我偏中长期持有，当前更适合防御还是进攻？",
];
const SOURCE_LABELS: Record<DeskSource, string> = {
  hybrid: "Hybrid Intelligence",
  market: "Market Tape",
  knowledge: "Research Vault",
};
const MODE_LABELS: Record<AnalysisMode, string> = {
  professional: "Professional",
  summary: "Summary",
  teaching: "Teaching",
};
const EMPTY_PROFILE: UserProfile = {
  profile_id: "default",
  risk_level: "medium",
  investment_horizon: "medium",
  markets: ["A-share"],
  sector_preferences: [],
  style_preference: "advisor",
};
const EMPTY_MEMORY: AgentMemory = {
  summary: "系统会在这里维护你的长期偏好、最近关注标的和近期操作线索。",
  recent_symbols: [],
  recent_sectors: [],
  preference_tags: [],
  recent_tasks: [],
  recent_actions: [],
  updated_at: "",
};

function clamp(value: number, min = 0, max = 100): number {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function unique(items: Array<string | undefined | null>): string[] {
  return Array.from(
    new Set(
      items
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  );
}

function createLocalMessage(role: "user" | "assistant", content: string): ConversationMessage {
  return {
    message_id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    created_at: new Date().toISOString(),
  };
}

function pushStatusLine(current: string[], incoming: string): string[] {
  const next = [...current, incoming].filter(Boolean);
  return next.slice(-STATUS_LIMIT);
}

function markdownBlock(text: string) {
  return { __html: renderMarkdown(text) };
}

function computeFallbackBullets(
  security: SecurityPayload | null,
  dashboard: DashboardOverview | null,
  memory: AgentMemory,
): string[] {
  const bullets: string[] = [];

  if (security?.quote?.symbol) {
    bullets.push(`${security.quote.symbol} 当前价格 ${num(security.quote.last_price)}，涨跌 ${pct(security.quote.change_percent)}。`);
  }
  if (security?.technical?.momentum_label || security?.technical?.rsi14 != null) {
    bullets.push(`技术面 ${security.technical?.momentum_label || "待确认"}，RSI14 ${num(security.technical?.rsi14)}。`);
  }
  if (security?.capital_flow?.summary) {
    bullets.push(security.capital_flow.summary);
  }
  if (dashboard?.market_sentiment?.summary) {
    bullets.push(dashboard.market_sentiment.summary);
  }
  if (memory.recent_symbols.length) {
    bullets.push(`最近关注标的：${memory.recent_symbols.slice(0, 3).join(" / ")}。`);
  }

  return bullets.slice(0, 4);
}

function computeRiskScore(security: SecurityPayload | null): number {
  if (!security) return 42;
  const moveRisk = Math.abs(Number(security.quote?.change_percent || 0)) * 8;
  const amplitudeRisk = Math.abs(Number(security.quote?.amplitude || 0)) * 4;
  const leverageRisk = Number(security.profile?.debt_ratio || 0) * 0.35;
  return clamp(moveRisk + amplitudeRisk + leverageRisk);
}

function computeLiquidityScore(security: SecurityPayload | null): number {
  if (!security) return 48;
  const turnoverRate = Number(security.quote?.turnover_rate || 0) * 8;
  const turnoverWeight = Number(security.quote?.turnover || 0) >= 1e9 ? 30 : Number(security.quote?.turnover || 0) >= 1e8 ? 18 : 10;
  return clamp(turnoverRate + turnoverWeight);
}

function computeConfidenceScore(cards: AnalysisCard[], citations: CitationItem[], security: SecurityPayload | null): number {
  return clamp(cards.length * 18 + citations.length * 10 + (security?.quote?.symbol ? 28 : 12));
}

function initialsOf(value: string): string {
  const clean = String(value || "").trim();
  if (!clean) return "FA";
  const compact = clean.replace(/\s+/g, "");
  return compact.slice(0, 2).toUpperCase();
}

function MarkdownBlock({ text }: { text: string }) {
  return <div className="markdown-block" dangerouslySetInnerHTML={markdownBlock(text)} />;
}

function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`skeleton-block ${className}`.trim()} aria-hidden="true" />;
}

function InsightMetric(props: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <article className="insight-metric">
      <span>{props.label}</span>
      <strong className={props.tone || ""}>{props.value}</strong>
      <small>{props.note || " "}</small>
    </article>
  );
}

function ProgressMeter(props: { label: string; value: number; note: string; tone?: "risk" | "positive" | "neutral" }) {
  const width = `${clamp(props.value)}%`;
  return (
    <div className="progress-meter">
      <div className="progress-meter-head">
        <span>{props.label}</span>
        <strong>{Math.round(clamp(props.value))}</strong>
      </div>
      <div className="progress-track">
        <div className={`progress-fill ${props.tone || "neutral"}`} style={{ width }} />
      </div>
      <small>{props.note}</small>
    </div>
  );
}

function TagCluster(props: { title: string; items: string[]; emptyLabel?: string }) {
  return (
    <div className="tag-cluster">
      <div className="cluster-head">
        <span>{props.title}</span>
      </div>
      <div className="tag-grid">
        {props.items.length ? (
          props.items.map((item) => (
            <span className="tv-tag" key={`${props.title}-${item}`}>
              {item}
            </span>
          ))
        ) : (
          <span className="tv-tag muted">{props.emptyLabel || "暂无"}</span>
        )}
      </div>
    </div>
  );
}

function StatusBadge(props: { state: "idle" | "loading" | "warn" }) {
  const label = props.state === "loading" ? "Analyzing" : props.state === "warn" ? "Attention" : "Online";
  return (
    <span className={`status-badge ${props.state}`}>
      <i />
      {label}
    </span>
  );
}

function AuthScreen(props: {
  mode: "login" | "register";
  busy: boolean;
  error: string;
  onSwitch: (mode: "login" | "register") => void;
  onLogin: (username: string, password: string) => Promise<void>;
  onRegister: (username: string, password: string, displayName: string) => Promise<void>;
}) {
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [registerUsername, setRegisterUsername] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  return (
    <main className="auth-shell">
      <section className="auth-hero panel">
        <div className="brand-lockup">
          <div className="brand-mark">FA</div>
          <div>
            <p className="eyebrow">FinAvatar Terminal</p>
            <h1>专业金融终端级数字人工作台</h1>
          </div>
        </div>
        <p className="hero-copy">实时行情、结构化分析、风险提示和会话记忆被整合到同一套深色终端界面中，聚焦“数据分析 + 决策辅助”。</p>
        <div className="hero-matrix">
          <article className="hero-stat"><span>Desk</span><strong>Market + AI Analysis</strong></article>
          <article className="hero-stat"><span>Risk</span><strong>Structured Warning System</strong></article>
          <article className="hero-stat"><span>Memory</span><strong>Persistent Research Context</strong></article>
        </div>
      </section>

      <section className="auth-panel panel">
        <div className="auth-switch">
          <button className={`switch-pill ${props.mode === "login" ? "active" : ""}`} type="button" onClick={() => props.onSwitch("login")}>登录</button>
          <button className={`switch-pill ${props.mode === "register" ? "active" : ""}`} type="button" onClick={() => props.onSwitch("register")}>注册</button>
        </div>

        {props.mode === "login" ? (
          <form className="form-grid" onSubmit={(event) => { event.preventDefault(); void props.onLogin(loginUsername.trim(), loginPassword); }}>
            <label className="field"><span>账户</span><input value={loginUsername} onChange={(event) => setLoginUsername(event.target.value)} required /></label>
            <label className="field"><span>密码</span><input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} required /></label>
            <button className="button primary" type="submit" disabled={props.busy}>{props.busy ? "登录中..." : "进入终端"}</button>
          </form>
        ) : (
          <form className="form-grid" onSubmit={(event) => { event.preventDefault(); void props.onRegister(registerUsername.trim(), registerPassword, displayName.trim()); }}>
            <label className="field"><span>显示名称</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
            <label className="field"><span>账户</span><input value={registerUsername} onChange={(event) => setRegisterUsername(event.target.value)} required /></label>
            <label className="field"><span>密码</span><input type="password" value={registerPassword} onChange={(event) => setRegisterPassword(event.target.value)} required /></label>
            <button className="button primary" type="submit" disabled={props.busy}>{props.busy ? "创建中..." : "创建工作台"}</button>
          </form>
        )}

        <p className={`auth-note ${props.error ? "error" : ""}`}>{props.error || "每个账户拥有独立会话、长期记忆、私有资料库和金融分析偏好。"}</p>
      </section>
    </main>
  );
}

export default function App() {
  const [theme] = useState<ThemeMode>("dark");
  const [token, setToken] = useState<string>(() => window.localStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [task, setTask] = useState<TaskType>("dashboard");
  const [deskSource, setDeskSource] = useState<DeskSource>("hybrid");
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("professional");
  const [models, setModels] = useState<ModelItem[]>([]);
  const [modelProvider, setModelProvider] = useState("deepseek");
  const [profile, setProfile] = useState<UserProfile>(EMPTY_PROFILE);
  const [dashboard, setDashboard] = useState<DashboardOverview | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [memory, setMemory] = useState<AgentMemory>(EMPTY_MEMORY);
  const [libraryCount, setLibraryCount] = useState(0);
  const [libraryFiles, setLibraryFiles] = useState<LibraryFileItem[]>([]);
  const [librarySearch, setLibrarySearch] = useState("");
  const [selectedLibraryDocId, setSelectedLibraryDocId] = useState("");
  const [selectedLibraryDoc, setSelectedLibraryDoc] = useState<DocumentDetail | null>(null);
  const [libraryDetailBusy, setLibraryDetailBusy] = useState(false);
  const [libraryDeletingDocId, setLibraryDeletingDocId] = useState("");
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [securityQuery, setSecurityQuery] = useState("");
  const [security, setSecurity] = useState<SecurityPayload | null>(null);
  const [securityBusy, setSecurityBusy] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>(() => window.localStorage.getItem(ACTIVE_CONV_KEY) || "");
  const [conversationTitle, setConversationTitle] = useState("新会话");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [cards, setCards] = useState<AnalysisCard[]>([]);
  const [citations, setCitations] = useState<CitationItem[]>([]);
  const [summaryTitle, setSummaryTitle] = useState(DEFAULT_SUMMARY_TITLE);
  const [summaryText, setSummaryText] = useState(DEFAULT_SUMMARY_TEXT);
  const [summaryBullets, setSummaryBullets] = useState<string[]>([]);
  const [riskItems, setRiskItems] = useState<string[]>([DEFAULT_RISK_ITEM]);
  const [statusItems, setStatusItems] = useState<string[]>([DEFAULT_STATUS_ITEM]);
  const [streaming, setStreaming] = useState(false);
  const [routeBadge, setRouteBadge] = useState("Waiting");
  const [agentTitle, setAgentTitle] = useState("Desk Ready");
  const [agentCaption, setAgentCaption] = useState("等待新的证券查询或分析问题。");
  const [agentState, setAgentState] = useState<"idle" | "loading" | "warn">("idle");
  const [avatarVoiceEnabled, setAvatarVoiceEnabled] = useState<boolean>(() => window.localStorage.getItem(AVATAR_VOICE_KEY) === "1");
  const [avatarProfile, setAvatarProfile] = useState<LocalAvatarProfile | null>(null);
  const [lastAssistantMessage, setLastAssistantMessage] = useState("");
  const [historyCollapsed, setHistoryCollapsed] = useState(false);

  const controllerRef = useRef<AbortController | null>(null);
  const tokenRef = useRef(token);
  const answerRef = useRef("");
  const assistantMessageIdRef = useRef("");
  const messageStreamRef = useRef<HTMLDivElement | null>(null);
  const lastSpokenRef = useRef("");

  const appendStatus = useCallback((text: string) => {
    setStatusItems((current) => pushStatusLine(current, text));
  }, []);

  const handleUnauthorized = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(ACTIVE_CONV_KEY);
    setToken("");
    setUser(null);
    setMessages([]);
    setConversations([]);
    setActiveConversationId("");
    setConversationTitle("新会话");
    setCards([]);
    setCitations([]);
    setSecurity(null);
    setLibraryFiles([]);
    setLibrarySearch("");
    setSelectedLibraryDocId("");
    setSelectedLibraryDoc(null);
  }, []);

  const api = useMemo(() => createApi(() => tokenRef.current || window.localStorage.getItem(TOKEN_KEY) || "", handleUnauthorized), [handleUnauthorized]);

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const setAgent = useCallback((stateName: "idle" | "loading" | "warn", title: string, caption: string) => {
    setAgentState(stateName);
    setAgentTitle(title);
    setAgentCaption(caption);
  }, []);

  const applyCards = useCallback((nextCards: AnalysisCard[]) => {
    setCards(nextCards);
    if (!nextCards.length) {
      setSummaryTitle(DEFAULT_SUMMARY_TITLE);
      setSummaryText(DEFAULT_SUMMARY_TEXT);
      setSummaryBullets([]);
      setRiskItems([DEFAULT_RISK_ITEM]);
      return;
    }

    const conclusion = nextCards.find((card) => card.card_type === "conclusion") || nextCards[0];
    const riskCard = nextCards.find((card) => card.card_type === "risk");

    setSummaryTitle(conclusion?.title || "分析完成");
    setSummaryText(conclusion?.summary || DEFAULT_SUMMARY_TEXT);
    setSummaryBullets((conclusion?.items || []).slice(0, 4));
    setRiskItems(riskCard?.items?.length ? riskCard.items : [DEFAULT_RISK_ITEM]);
  }, []);

  const resetInsightPanels = useCallback(() => {
    applyCards([]);
    setCitations([]);
    setStatusItems([DEFAULT_STATUS_ITEM]);
  }, [applyCards]);

  const loadLibraryDocument = useCallback(async (docId: string) => {
    if (!docId) {
      setSelectedLibraryDocId("");
      setSelectedLibraryDoc(null);
      return;
    }
    setSelectedLibraryDocId(docId);
    setLibraryDetailBusy(true);
    try {
      const detail = await api.getLibraryDocument(docId);
      setSelectedLibraryDoc(detail);
    } catch (error) {
      setSelectedLibraryDoc(null);
      setAgent("warn", "Document Load Failed", error instanceof Error ? error.message : "无法读取资料详情。");
    } finally {
      setLibraryDetailBusy(false);
    }
  }, [api, setAgent]);

  const refreshLibrary = useCallback(async (preferredDocId?: string | null): Promise<LibraryFileItem[]> => {
    const files = await api.files();
    setLibraryFiles(files);
    setLibraryCount(files.length);
    if (!files.length) {
      setSelectedLibraryDocId("");
      setSelectedLibraryDoc(null);
      return files;
    }

    const requestedId = preferredDocId === undefined ? selectedLibraryDocId : preferredDocId || "";
    const nextId = requestedId && files.some((item) => item.doc_id === requestedId) ? requestedId : files[0].doc_id;
    if (nextId) await loadLibraryDocument(nextId);
    return files;
  }, [api, loadLibraryDocument, selectedLibraryDocId]);

  const pollIngestionJobs = useCallback(async (jobIds: string[]) => {
    if (!jobIds.length) return;
    let active = [...jobIds];
    while (active.length) {
      const snapshots = await Promise.all(active.map((jobId) => api.getJob(jobId)));
      setIngestionJobs((current) => {
        const merged = new Map(current.map((item) => [item.job_id, item]));
        snapshots.forEach((item) => merged.set(item.job_id, item));
        return Array.from(merged.values()).sort((a, b) => b.created_at.localeCompare(a.created_at));
      });
      const pending = snapshots.filter((item) => !['completed', 'failed'].includes(item.status));
      if (!pending.length) {
        await refreshLibrary();
        const failed = snapshots.filter((item) => item.status === 'failed');
        if (failed.length) {
          setAgent('warn', 'Ingestion Finished With Errors', failed[0].error_message || 'Some documents failed to ingest.');
        } else {
          setAgent('idle', 'Vault Updated', 'Documents are ready for semantic retrieval.');
        }
        break;
      }
      active = pending.map((item) => item.job_id);
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
  }, [api, refreshLibrary, setAgent]);

  const refreshCoreData = useCallback(async () => {
    const results = await Promise.allSettled([
      api.dashboard(),
      api.health(),
      api.memory(),
      api.files(),
      api.models(),
      api.profile(),
      api.avatarProfile(),
    ]);

    if (results[0].status === "fulfilled") setDashboard(results[0].value);
    if (results[1].status === "fulfilled") setHealth(results[1].value);
    if (results[2].status === "fulfilled") setMemory(results[2].value);
    if (results[3].status === "fulfilled") {
      setLibraryFiles(results[3].value);
      setLibraryCount(results[3].value.length);
    }
    if (results[4].status === "fulfilled") {
      const configuredModels = results[4].value.filter((item) => item.configured !== false);
      setModels(configuredModels);
      if (configuredModels.length && !configuredModels.some((item) => item.id === modelProvider)) {
        setModelProvider(configuredModels[0].id);
      }
    }
    if (results[5].status === "fulfilled") setProfile(results[5].value);
    if (results[6].status === "fulfilled") setAvatarProfile(results[6].value);
  }, [api, modelProvider]);

  const refreshConversations = useCallback(async (): Promise<ConversationSummary[]> => {
    const nextConversations = await api.conversations();
    setConversations(nextConversations);
    return nextConversations;
  }, [api]);

  const applyConversation = useCallback((session: ConversationSession) => {
    setActiveConversationId(session.conversation_id);
    setConversationTitle(session.title || "新会话");
    setMessages(session.messages || []);
    window.localStorage.setItem(ACTIVE_CONV_KEY, session.conversation_id);
  }, []);

  const loadConversation = useCallback(async (conversationId: string) => {
    const session = await api.getConversation(conversationId);
    applyConversation(session);
  }, [api, applyConversation]);

  const createConversation = useCallback(async (select = true): Promise<ConversationSession> => {
    const session = await api.createConversation();
    await refreshConversations();
    if (select) applyConversation(session);
    return session;
  }, [api, applyConversation, refreshConversations]);

  const initConversations = useCallback(async () => {
    const list = await refreshConversations();
    const savedId = window.localStorage.getItem(ACTIVE_CONV_KEY) || activeConversationId;
    if (savedId && list.some((item) => item.conversation_id === savedId)) {
      await loadConversation(savedId);
      return;
    }
    if (list.length) {
      await loadConversation(list[0].conversation_id);
      return;
    }
    await createConversation(true);
  }, [activeConversationId, createConversation, loadConversation, refreshConversations]);

  const queryStock = useCallback(async (query: string) => {
    const normalized = String(query || securityQuery).trim();
    if (!normalized) return;
    setSecurityBusy(true);
    setTask("dashboard");
    setAgent("loading", "Fetching Security", "正在拉取实时行情、技术面和事件流。");
    try {
      const result = await api.queryStock(normalized);
      setSecurity(result);
      setSecurityQuery(result.quote?.symbol || normalized);
      setAgent("idle", "Security Updated", "中区已经同步刷新为最新证券分析视图。");
      const memorySnapshot = await api.memory();
      setMemory(memorySnapshot);
    } catch (error) {
      setAgent("warn", "Security Query Failed", error instanceof Error ? error.message : "未能识别该证券。");
    } finally {
      setSecurityBusy(false);
    }
  }, [api, securityQuery, setAgent]);

  const uploadLibraryFiles = useCallback(async (files: FileList | File[]) => {
    const uploadList = Array.from(files || []);
    if (!uploadList.length) return;

    const body = new FormData();
    uploadList.forEach((file) => body.append("files", file));
    body.append("model_provider", modelProvider || "deepseek");

    setAgent("loading", "Queueing Research", "Upload accepted and queued for background ingestion.");
    try {
      const result = await api.upload(body);
      const jobIds = result.items.map((item) => item.job_id);
      if (result.items.length) {
        setTask("library");
        await refreshLibrary();
        void pollIngestionJobs(jobIds);
      }
      const memorySnapshot = await api.memory();
      setMemory(memorySnapshot);
      if (!result.items.length && result.skipped.length) {
        setAgent("warn", "Upload Skipped", `Skipped: ${result.skipped.join(" / ")}`);
      } else {
        setAgent("loading", "Ingestion Running", `Queued ${result.items.length} file(s) for background ingestion.`);
      }
    } catch (error) {
      setAgent("warn", "Upload Failed", error instanceof Error ? error.message : "Upload failed.");
    }
  }, [api, modelProvider, pollIngestionJobs, refreshLibrary, setAgent]);

  const uploadFiles = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.querySelector('input[type="file"]') as HTMLInputElement | null;
    if (!input?.files?.length) return;

    const body = new FormData();
    Array.from(input.files).forEach((file) => body.append("files", file));
    body.append("model_provider", modelProvider || "deepseek");

    setAgent("loading", "Queueing Research", "Upload accepted and queued for background ingestion.");
    try {
      const result = await api.upload(body);
      input.value = "";
      const jobIds = result.items.map((item) => item.job_id);
      if (result.items.length) {
        setTask("library");
        await refreshLibrary();
        void pollIngestionJobs(jobIds);
      }
      const memorySnapshot = await api.memory();
      setMemory(memorySnapshot);
      if (!result.items.length && result.skipped.length) {
        setAgent("warn", "Upload Skipped", `Skipped: ${result.skipped.join(" / ")}`);
      } else {
        setAgent("loading", "Ingestion Running", `Queued ${result.items.length} file(s) for background ingestion.`);
      }
    } catch (error) {
      setAgent("warn", "Upload Failed", error instanceof Error ? error.message : "Upload failed.");
    }
  }, [uploadLibraryFiles]);

  const saveProfile = useCallback(async () => {
    try {
      const payload: UserProfile = {
        ...profile,
        profile_id: user?.user_id || profile.profile_id,
      };
      const saved = await api.saveProfile(payload);
      setProfile(saved);
      setMemory(await api.memory());
      setAgent("idle", "Profile Saved", "投资偏好已写入长期记忆。");
    } catch (error) {
      setAgent("warn", "Profile Save Failed", error instanceof Error ? error.message : "保存失败。");
    }
  }, [api, profile, setAgent, user?.user_id]);

  const updateAssistantMessage = useCallback((messageId: string, content: string) => {
    setMessages((current) => current.map((item) => (item.message_id === messageId ? { ...item, content } : item)));
  }, []);

  const processStreamEvent = useCallback((event: StreamEvent, source: string) => {
    if (event.type === "conversation") {
      const payload = event as StreamConversationEvent;
      if (payload.conversation?.conversation_id) {
        setActiveConversationId(payload.conversation.conversation_id);
        setConversationTitle(payload.conversation.title || "当前会话");
        window.localStorage.setItem(ACTIVE_CONV_KEY, payload.conversation.conversation_id);
      }
      return;
    }

    if (event.type === "ack" || event.type === "market_fetch_started" || event.type === "rag_fetch_started") {
      const payload = event as StreamBaseEvent;
      if (payload.message) appendStatus(payload.message);
      return;
    }

    if (event.type === "route") {
      const payload = event as StreamRouteEvent;
      setRouteBadge(`${payload.route.task_type} / ${payload.route.reason}`);
      appendStatus(`Route: ${payload.route.task_type}`);
      return;
    }

    if (event.type === "market_fetch_done") {
      const payload = event as StreamBaseEvent;
      appendStatus(payload.degraded ? "实时行情已降级" : "实时行情拉取完成");
      return;
    }

    if (event.type === "rag_fetch_done") {
      const payload = event as StreamBaseEvent & { citations?: CitationItem[] };
      appendStatus(payload.degraded ? "知识证据已降级" : `知识证据就绪 (${payload.citations?.length || 0})`);
      return;
    }

    if (event.type === "analysis_cards") {
      applyCards((event as StreamCardsEvent).cards || []);
      return;
    }

    if (event.type === "citations") {
      setCitations((event as StreamCitationsEvent).items || []);
      return;
    }

    if (event.type === "delta") {
      const payload = event as StreamDeltaEvent;
      answerRef.current += payload.delta || "";
      updateAssistantMessage(assistantMessageIdRef.current, answerRef.current || "正在生成...");
      return;
    }

    if (event.type === "final") {
      const payload = event as StreamFinalEvent;
      const answer = payload.answer || answerRef.current;
      answerRef.current = answer;
      updateAssistantMessage(assistantMessageIdRef.current, answer);
      applyCards(payload.cards || []);
      setCitations(payload.citations || []);
      setRouteBadge(`${payload.route?.task_type || "analysis"} / complete`);
      setAgent("idle", "Analysis Complete", `已完成“${source.slice(0, 18)}”的分析。`);
      setLastAssistantMessage(answer);
      return;
    }

    if (event.type === "error") {
      const payload = event as StreamBaseEvent & { detail?: string };
      updateAssistantMessage(assistantMessageIdRef.current, `分析失败：${payload.detail || "unknown error"}`);
      setRouteBadge("Error");
      setAgent("warn", "Analysis Error", "本次回答未完整返回。");
    }
  }, [appendStatus, applyCards, setAgent, updateAssistantMessage]);

  const submitMessage = useCallback(async (rawText?: string) => {
    const message = String(rawText || draft).trim();
    if (!message) return;
    if (controllerRef.current) controllerRef.current.abort();

    setDraft("");
    resetInsightPanels();
    setRouteBadge("Routing");
    setStatusItems([
      "请求已发送",
      security?.quote?.symbol ? `沿用证券上下文：${security.quote.symbol}` : "无预选证券上下文",
      `Source focus: ${SOURCE_LABELS[deskSource]}`,
    ]);
    setAgent("loading", "Streaming Analysis", "正在执行实时检索与结构化生成。");
    answerRef.current = "";

    let conversationId = activeConversationId;
    if (!conversationId) {
      const session = await createConversation(true);
      conversationId = session.conversation_id;
    }

    const userMessage = createLocalMessage("user", message);
    const assistantMessage = createLocalMessage("assistant", "正在连接分析引擎...");
    assistantMessageIdRef.current = assistantMessage.message_id;
    setMessages((current) => [...current, userMessage, assistantMessage]);

    try {
      const controller = new AbortController();
      controllerRef.current = controller;
      setStreaming(true);
      await api.streamCopilot(
        {
          message,
          task_type: "auto",
          analysis_mode: analysisMode,
          model_provider: modelProvider,
          conversation_id: conversationId,
          history: messages.slice(-MAX_HISTORY).map((item) => ({ role: item.role, content: item.content })),
          context_hint: {
            source_focus: deskSource,
            symbol: security?.quote?.symbol || null,
            company: security?.profile?.company_name || null,
            sector: security?.profile?.sector || null,
          },
        },
        controller.signal,
        (event) => processStreamEvent(event, message),
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : "请求异常";
      updateAssistantMessage(assistantMessageIdRef.current, detail);
      setRouteBadge("Error");
      setAgent("warn", "Analysis Error", detail);
    } finally {
      controllerRef.current = null;
      setStreaming(false);
      const [conversationList, memorySnapshot] = await Promise.allSettled([refreshConversations(), api.memory()]);
      if (conversationList.status === "fulfilled") {
        const currentConversation = conversationList.value.find((item) => item.conversation_id === conversationId);
        if (currentConversation) setConversationTitle(currentConversation.title || "新会话");
      }
      if (memorySnapshot.status === "fulfilled") setMemory(memorySnapshot.value);
    }
  }, [activeConversationId, analysisMode, api, createConversation, deskSource, draft, messages, modelProvider, processStreamEvent, refreshConversations, resetInsightPanels, security?.profile?.company_name, security?.profile?.sector, security?.quote?.symbol, setAgent, updateAssistantMessage]);

  const removeConversation = useCallback(async () => {
    if (!activeConversationId) return;
    await api.deleteConversation(activeConversationId);
    setMessages([]);
    setActiveConversationId("");
    window.localStorage.removeItem(ACTIVE_CONV_KEY);
    await initConversations();
  }, [activeConversationId, api, initConversations]);

  const deleteLibraryDocument = useCallback(async (docId: string) => {
    if (!docId) return;
    const current = libraryFiles.find((item) => item.doc_id === docId);
    const confirmed = window.confirm(`确认删除资料「${current?.title || current?.filename || docId}」？这会同时移除原文件与索引。`);
    if (!confirmed) return;
    setLibraryDeletingDocId(docId);
    try {
      await api.deleteLibraryDocument(docId);
      await refreshLibrary(selectedLibraryDocId === docId ? "" : selectedLibraryDocId);
      setAgent("idle", "Document Removed", "资料与索引已同步删除。");
    } catch (error) {
      setAgent("warn", "Delete Failed", error instanceof Error ? error.message : "资料删除失败。");
    } finally {
      setLibraryDeletingDocId("");
    }
  }, [api, libraryFiles, refreshLibrary, selectedLibraryDocId, setAgent]);

  const logout = useCallback(async () => {
    if (controllerRef.current) controllerRef.current.abort();
    if (token) {
      try {
        await api.logout();
      } catch {
        // ignore logout errors
      }
    }
    handleUnauthorized();
    resetInsightPanels();
  }, [api, handleUnauthorized, resetInsightPanels, token]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem(AVATAR_VOICE_KEY, avatarVoiceEnabled ? "1" : "0");
  }, [avatarVoiceEnabled]);

  useEffect(() => {
    if (!avatarVoiceEnabled || !lastAssistantMessage.trim()) return;
    if (lastAssistantMessage === lastSpokenRef.current) return;
    lastSpokenRef.current = lastAssistantMessage;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(lastAssistantMessage);
    utterance.lang = avatarProfile?.default_language || "zh-CN";
    if (avatarProfile?.voice_name && avatarProfile.voice_name !== "default") {
      const matched = window.speechSynthesis.getVoices().find((voice) => voice.name === avatarProfile.voice_name);
      if (matched) utterance.voice = matched;
    }
    window.speechSynthesis.speak(utterance);
    return () => {
      window.speechSynthesis.cancel();
    };
  }, [avatarProfile?.default_language, avatarProfile?.voice_name, avatarVoiceEnabled, lastAssistantMessage]);

  useEffect(() => {
    const viewport = messageStreamRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  useEffect(() => {
    if (task !== "library" || libraryDetailBusy) return;
    if (!libraryFiles.length) {
      setSelectedLibraryDocId("");
      setSelectedLibraryDoc(null);
      return;
    }
    const hasSelected = selectedLibraryDocId && libraryFiles.some((item) => item.doc_id === selectedLibraryDocId);
    if (selectedLibraryDoc && selectedLibraryDoc.doc_id === selectedLibraryDocId && hasSelected) return;
    const nextId = hasSelected ? selectedLibraryDocId : libraryFiles[0].doc_id;
    if (nextId) void loadLibraryDocument(nextId);
  }, [libraryDetailBusy, libraryFiles, loadLibraryDocument, selectedLibraryDoc, selectedLibraryDocId, task]);

  useEffect(() => {
    let active = true;

    const restore = async (): Promise<void> => {
      if (!token) return;
      try {
        const session = await api.session();
        if (!active) return;
        if (!session.authenticated || !session.user) {
          handleUnauthorized();
          return;
        }
        setUser(session.user);
        setAgent("loading", "Initializing", "正在同步用户画像、行情和会话历史。");
        await refreshCoreData();
        await initConversations();
        setAgent("idle", "Desk Ready", "市场与研究上下文已同步。");
      } catch {
        if (!active) return;
        handleUnauthorized();
      }
    };

    void restore();
    return () => {
      active = false;
    };
  }, [api, handleUnauthorized, initConversations, refreshCoreData, setAgent, token]);

  useEffect(() => {
    if (!token || !user) return;
    const timer = window.setInterval(() => {
      if (streaming || document.hidden) return;
      void refreshCoreData();
      if (security?.quote?.symbol) void queryStock(security.quote.symbol);
    }, 60000);
    return () => window.clearInterval(timer);
  }, [queryStock, refreshCoreData, security?.quote?.symbol, streaming, token, user]);

  const handleLogin = async (username: string, password: string): Promise<void> => {
    setAuthBusy(true);
    setAuthError("");
    try {
      const payload = await api.login(username, password);
      tokenRef.current = payload.token;
      window.localStorage.setItem(TOKEN_KEY, payload.token);
      setToken(payload.token);
      setUser(payload.user);
      setAgent("loading", "Initializing", "正在同步用户工作台。");
      await refreshCoreData();
      await initConversations();
      setAgent("idle", "Desk Ready", "工作台已就绪。");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "登录失败");
    } finally {
      setAuthBusy(false);
    }
  };

  const handleRegister = async (username: string, password: string, displayName: string): Promise<void> => {
    setAuthBusy(true);
    setAuthError("");
    try {
      const payload = await api.register(username, password, displayName);
      tokenRef.current = payload.token;
      window.localStorage.setItem(TOKEN_KEY, payload.token);
      setToken(payload.token);
      setUser(payload.user);
      setAgent("loading", "Bootstrapping", "正在创建专属金融工作台。");
      await refreshCoreData();
      await initConversations();
      setAgent("idle", "Desk Ready", "专属工作台已创建完成。");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "注册失败");
    } finally {
      setAuthBusy(false);
    }
  };

  const displayedSecurityName = security?.quote?.name || security?.profile?.company_name || security?.quote?.symbol || "Market Focus";
  const displayedTicker = security?.quote?.symbol || "CN-MKT";
  const displayedPrice = security?.quote?.last_price ?? dashboard?.indices?.[0]?.last_price;
  const displayedChange = security?.quote?.change_percent ?? dashboard?.indices?.[0]?.change_percent;
  const sparkValues = useMemo(() => (security?.history || []).map((item) => Number(item.close ?? item.open)).filter((item) => Number.isFinite(item)), [security?.history]);
  const marketBullets = useMemo(() => computeFallbackBullets(security, dashboard, memory), [dashboard, memory, security]);
  const displayedBullets = summaryBullets.length ? summaryBullets : marketBullets;
  const displayedSummaryTitle = summaryTitle === DEFAULT_SUMMARY_TITLE ? (security?.quote?.symbol ? "AI Investment Analysis" : "Market Strategy Snapshot") : summaryTitle;
  const displayedSummaryText = summaryText === DEFAULT_SUMMARY_TEXT
    ? security?.quote?.symbol
      ? `${displayedSecurityName} 当前处于 ${security?.technical?.momentum_label || "待确认"} 节奏，结合 ${SOURCE_LABELS[deskSource]} 进行研判。`
      : dashboard?.market_sentiment?.summary || "等待新的证券查询或对话输入。"
    : summaryText;

  const displayedRisks = riskItems.length && riskItems[0] !== DEFAULT_RISK_ITEM
    ? riskItems
    : unique([
        security?.quote?.amplitude != null ? `波动率 ${pct(security.quote.amplitude)}，短线风险需控制仓位。` : "",
        security?.profile?.debt_ratio != null ? `资产负债率 ${pct(security.profile.debt_ratio)}，注意杠杆约束。` : "",
        dashboard?.market_sentiment?.regime ? `当前市场风格为 ${dashboard.market_sentiment.regime}，避免与主导风格逆向重仓。` : "",
      ]).slice(0, 3);

  const riskScore = computeRiskScore(security);
  const liquidityScore = computeLiquidityScore(security);
  const confidenceScore = computeConfidenceScore(cards, citations, security);
  const rsiScore = clamp(Number(security?.technical?.rsi14 ?? 50));
  const keyTags = unique([
    security?.profile?.sector,
    security?.profile?.industry,
    security?.technical?.momentum_label,
    ...memory.preference_tags.slice(0, 3),
  ]);

  const referenceItems = useMemo(() => {
    if (deskSource === "market") {
      return (security?.news || dashboard?.latest_events || []).slice(0, 4).map((item) => ({
        title: item.title || item.theme || "市场事件",
        summary: item.summary || item.agent_reason || "暂无摘要",
        meta: [item.source || "Market", formatTimeLabel(item.publish_time)].filter(Boolean).join("  "),
      }));
    }

    if (deskSource === "knowledge") {
      return citations.slice(0, 4).map((item) => ({
        title: item.title || "知识证据",
        summary: item.preview || "暂无摘要",
        meta: [item.section_title || "Research", item.time_label ? formatTimeLabel(item.time_label) : ""].filter(Boolean).join("  "),
      }));
    }

    const hybrid = [
      ...citations.slice(0, 2).map((item) => ({
        title: item.title || "知识证据",
        summary: item.preview || "暂无摘要",
        meta: [item.section_title || "Research", item.time_label ? formatTimeLabel(item.time_label) : ""].filter(Boolean).join("  "),
      })),
      ...(security?.news || dashboard?.latest_events || []).slice(0, 2).map((item) => ({
        title: item.title || item.theme || "市场事件",
        summary: item.summary || item.agent_reason || "暂无摘要",
        meta: [item.source || "Market", formatTimeLabel(item.publish_time)].filter(Boolean).join("  "),
      })),
    ];
    return hybrid.slice(0, 4);
  }, [citations, dashboard?.latest_events, deskSource, security?.news]);

  const historyTags = unique([...memory.recent_symbols, ...memory.recent_sectors, ...memory.preference_tags]).slice(0, 8);
  const okProviders = (health?.providers || []).filter((item) => item.ok).length;
  const controlHint = useMemo(() => {
    if (deskSource === "market") return "优先使用实时行情、事件流和技术指标。";
    if (deskSource === "knowledge") return "优先使用私有资料、引用证据和历史记忆。";
    return "混合模式会同时调取行情与知识库证据。";
  }, [deskSource]);

  if (!token || !user) {
    return <AuthScreen mode={authMode} busy={authBusy} error={authError} onSwitch={setAuthMode} onLogin={handleLogin} onRegister={handleRegister} />;
  }

  if (task === "library") {
    return (
      <LibraryWorkspace
        files={libraryFiles}
        search={librarySearch}
        selectedDocumentId={selectedLibraryDocId}
        selectedDocument={selectedLibraryDoc}
        detailBusy={libraryDetailBusy}
        deletingDocId={libraryDeletingDocId}
        jobs={ingestionJobs}
        profile={profile}
        sessions={conversations}
        activeConversationId={activeConversationId}
        onSearchChange={setLibrarySearch}
        onSelectDocument={(docId) => { void loadLibraryDocument(docId); }}
        onRefresh={() => { void refreshLibrary(); }}
        onDeleteDocument={(docId) => { void deleteLibraryDocument(docId); }}
        onUploadFiles={(files) => { void uploadLibraryFiles(files); }}
        onSaveProfile={() => { void saveProfile(); }}
        onProfileChange={(patch) => setProfile((current) => ({ ...current, ...patch }))}
        onOpenSession={(conversationId) => { void loadConversation(conversationId); }}
        onAskQuestion={(prompt) => { setTask("dashboard"); void submitMessage(prompt); }}
        onBackToDesk={() => setTask("dashboard")}
        onLogout={() => { void logout(); }}
      />
    );
  }

  return (
    <DashboardWorkspace
      profile={profile}
      models={models}
      modelProvider={modelProvider}
      analysisMode={analysisMode}
      deskSource={deskSource}
      controlHint={controlHint}
      securityQuery={securityQuery}
      securityBusy={securityBusy}
      dashboard={dashboard}
      security={security}
      displayedSecurityName={displayedSecurityName}
      displayedTicker={displayedTicker}
      displayedPrice={displayedPrice}
      displayedChange={displayedChange}
      routeBadge={routeBadge}
      sparkValues={sparkValues}
      displayedSummaryTitle={displayedSummaryTitle}
      displayedSummaryText={displayedSummaryText}
      displayedBullets={displayedBullets}
      displayedRisks={displayedRisks}
      keyTags={keyTags}
      referenceItems={referenceItems}
      rsiScore={Number(security?.technical?.rsi14 || 0)}
      riskScore={computeRiskScore(security)}
      liquidityScore={computeLiquidityScore(security)}
      confidenceScore={computeConfidenceScore(cards, citations, security)}
      citationsCount={citations.length}
      conversationTitle={conversationTitle}
      messages={messages}
      draft={draft}
      streaming={streaming}
      quickPrompts={QUICK_PROMPTS}
      conversations={conversations}
      activeConversationId={activeConversationId}
      memorySummary={memory.summary}
      memoryTags={historyTags}
      health={health}
      okProviders={okProviders}
      statusItems={statusItems}
      userDisplayName={avatarProfile?.display_name || user.display_name || user.username}
      avatarVoiceEnabled={avatarVoiceEnabled}
      uploadQueuedCount={ingestionJobs.filter((item) => !["completed", "failed"].includes(item.status)).length}
      onProfileChange={(patch) => setProfile((current) => ({ ...current, ...patch }))}
      onSaveProfile={() => { void saveProfile(); }}
      onUploadFiles={(files) => { void uploadLibraryFiles(files); }}
      onLogout={() => { void logout(); }}
      onGoLibrary={() => setTask("library")}
      onGoDesk={() => setTask("dashboard")}
      onOpenSession={(conversationId) => { void loadConversation(conversationId); }}
      onRefreshCoreData={() => { void refreshCoreData(); }}
      onSecurityQueryChange={setSecurityQuery}
      onQueryStock={(value) => { void queryStock(value || securityQuery); }}
      onDraftChange={setDraft}
      onSubmitMessage={(prompt) => { void submitMessage(prompt); }}
      onCreateConversation={() => { void createConversation(); }}
      onRemoveConversation={() => { void removeConversation(); }}
      onAbortStream={() => controllerRef.current?.abort()}
      onToggleVoice={() => setAvatarVoiceEnabled((current) => !current)}
      onModelProviderChange={setModelProvider}
      onAnalysisModeChange={setAnalysisMode}
      onDeskSourceChange={setDeskSource}
    />
  );
}


