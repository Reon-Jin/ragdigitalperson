import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AvatarPanel } from "./components/AvatarPanel";
import { LibraryWorkspace } from "./components/LibraryWorkspace";
import { createApi } from "./lib/api";
import { formatTimeLabel, joinTags, num, pct, splitTags, toneClass, turnover } from "./lib/format";
import { renderMarkdown } from "./lib/markdown";
import { ACTIVE_CONV_KEY, AVATAR_VOICE_KEY, TOKEN_KEY } from "./lib/storage";
import type {
  AgentMemory,
  AnalysisCard,
  AnalysisMode,
  AuthUser,
  CitationItem,
  ConversationMessage,
  ConversationSession,
  ConversationSummary,
  DashboardOverview,
  DocumentDetail,
  LibraryFileItem,
  LocalAvatarProfile,
  HealthPayload,
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

const MAX_HISTORY = 8;
const TASK_LABELS: Record<TaskType, string> = {
  dashboard: "市场总览",
  auto: "智能问答",
  library: "资料管理",
};
const QUICK_PROMPTS = [
  "结合我最近关注的方向，今天哪些 A 股值得继续跟踪？",
  "请帮我总结市场总览里最值得继续追问的 3 个方向。",
  "如果我偏中长期持有，当前市场更适合防御还是成长？",
];

const EMPTY_PROFILE: UserProfile = {
  profile_id: "default",
  risk_level: "medium",
  investment_horizon: "medium",
  markets: ["A-share"],
  sector_preferences: [],
  style_preference: "advisor",
};

const EMPTY_MEMORY: AgentMemory = {
  summary: "Agent 会在这里显示你的长期偏好、近期操作和最近关注标的。",
  recent_symbols: [],
  recent_sectors: [],
  preference_tags: [],
  recent_tasks: [],
  recent_actions: [],
  updated_at: "",
};

function createLocalMessage(role: "user" | "assistant", content: string): ConversationMessage {
  return {
    message_id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    created_at: new Date().toISOString(),
  };
}

function chartPath(history: Array<{ close?: number; open?: number }> = []): string[] {
  const points = history.map((item) => Number(item.close ?? item.open)).filter((item) => Number.isFinite(item));
  if (!points.length) return [];
  const width = 640;
  const height = 220;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  return points.map((value, index) => {
    const x = ((index / Math.max(points.length - 1, 1)) * width).toFixed(2);
    const y = (height - ((value - min) / range) * (height - 24) - 12).toFixed(2);
    return `${index ? "L" : "M"} ${x} ${y}`;
  });
}

function MarkdownBlock({ text }: { text: string }) {
  return <div dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }} />;
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
  const [displayName, setDisplayName] = useState("");
  const [registerUsername, setRegisterUsername] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");

  const submitLogin = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    await props.onLogin(loginUsername.trim(), loginPassword);
  };

  const submitRegister = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    await props.onRegister(registerUsername.trim(), registerPassword, displayName.trim());
  };

  return (
    <main className="auth-layout">
      <section className="auth-story panel hero-surface">
        <div className="hero-orbit hero-orbit-a" />
        <div className="hero-orbit hero-orbit-b" />
        <p className="section-kicker">FinAvatar</p>
        <h1>把金融 Copilot 升级成企业工作台与真人数字人分析席位。</h1>
        <p className="hero-copy">
          实时市场数据、私有知识库、结构化分析卡片、证据引用和会话记忆被整合在同一套界面里，杜绝工具堆砌式前端。
        </p>
        <div className="hero-grid">
          <article className="hero-stat">
            <span>实时总览</span>
            <strong>Dashboard + 个股查询</strong>
          </article>
          <article className="hero-stat">
            <span>数字人</span>
            <strong>ww自建数字人</strong>
          </article>
          <article className="hero-stat">
            <span>知识链路</span>
            <strong>私有资料上传与证据引用</strong>
          </article>
        </div>
      </section>

      <section className="auth-card panel">
        <div className="tab-row">
          <button className={`tab-button ${props.mode === "login" ? "active" : ""}`} type="button" onClick={() => props.onSwitch("login")}>
            登录
          </button>
          <button className={`tab-button ${props.mode === "register" ? "active" : ""}`} type="button" onClick={() => props.onSwitch("register")}>
            注册
          </button>
        </div>

        {props.mode === "login" ? (
          <form className="form-grid" onSubmit={(event) => void submitLogin(event)}>
            <label className="field">
              <span>用户名</span>
              <input value={loginUsername} onChange={(event) => setLoginUsername(event.target.value)} required />
            </label>
            <label className="field">
              <span>密码</span>
              <input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} required />
            </label>
            <button className="button primary" type="submit" disabled={props.busy}>
              {props.busy ? "登录中..." : "登录并进入工作台"}
            </button>
          </form>
        ) : (
          <form className="form-grid" onSubmit={(event) => void submitRegister(event)}>
            <label className="field">
              <span>显示名称</span>
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            </label>
            <label className="field">
              <span>用户名</span>
              <input value={registerUsername} onChange={(event) => setRegisterUsername(event.target.value)} required />
            </label>
            <label className="field">
              <span>密码</span>
              <input type="password" value={registerPassword} onChange={(event) => setRegisterPassword(event.target.value)} required />
            </label>
            <button className="button primary" type="submit" disabled={props.busy}>
              {props.busy ? "注册中..." : "注册并创建专属席位"}
            </button>
          </form>
        )}

        <p className={`auth-note ${props.error ? "is-error" : ""}`}>{props.error || "每个用户拥有独立对话、画像、长期记忆和私有知识库。"}</p>
      </section>
    </main>
  );
}

export default function App() {
  const [token, setToken] = useState<string>(() => window.localStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [task, setTask] = useState<TaskType>("dashboard");
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
  const [securityQuery, setSecurityQuery] = useState("");
  const [security, setSecurity] = useState<SecurityPayload | null>(null);
  const [securityBusy, setSecurityBusy] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>(() => window.localStorage.getItem(ACTIVE_CONV_KEY) || "");
  const [conversationTitle, setConversationTitle] = useState("新对话");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [cards, setCards] = useState<AnalysisCard[]>([]);
  const [citations, setCitations] = useState<CitationItem[]>([]);
  const [summaryTitle, setSummaryTitle] = useState("等待分析");
  const [summaryText, setSummaryText] = useState("你可以直接给出选股需求，Agent 会结合记忆、行情、新闻和知识库继续分析。");
  const [summaryBullets, setSummaryBullets] = useState<string[]>([]);
  const [riskItems, setRiskItems] = useState<string[]>(["尚未生成风险提示。"]);
  const [statusItems, setStatusItems] = useState<string[]>(["系统待命。"]);
  const [streaming, setStreaming] = useState(false);
  const [routeBadge, setRouteBadge] = useState("待识别");
  const [agentTitle, setAgentTitle] = useState("待命中");
  const [agentCaption, setAgentCaption] = useState("市场总览与长期记忆同步后，可以直接开始问答或查询个股。");
  const [agentState, setAgentState] = useState<"idle" | "loading" | "warn">("idle");
  const [avatarVoiceEnabled, setAvatarVoiceEnabled] = useState<boolean>(() => window.localStorage.getItem(AVATAR_VOICE_KEY) === "1");
  const [avatarProfile, setAvatarProfile] = useState<LocalAvatarProfile | null>(null);
  const [lastAssistantMessage, setLastAssistantMessage] = useState("");

  const controllerRef = useRef<AbortController | null>(null);
  const answerRef = useRef("");
  const assistantMessageIdRef = useRef("");

  const handleUnauthorized = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(ACTIVE_CONV_KEY);
    setToken("");
    setUser(null);
    setMessages([]);
    setConversations([]);
    setActiveConversationId("");
    setConversationTitle("新对话");
    setCards([]);
    setCitations([]);
    setSecurity(null);
    setLibraryFiles([]);
    setLibrarySearch("");
    setSelectedLibraryDocId("");
    setSelectedLibraryDoc(null);
  }, []);

  const api = useMemo(() => createApi(() => token, handleUnauthorized), [handleUnauthorized, token]);

  const setAgent = useCallback((stateName: "idle" | "loading" | "warn", title: string, caption: string) => {
    setAgentState(stateName);
    setAgentTitle(title);
    setAgentCaption(caption);
  }, []);

  const applyCards = useCallback((nextCards: AnalysisCard[]) => {
    setCards(nextCards);
    if (!nextCards.length) {
      setSummaryTitle("等待分析");
      setSummaryText("你可以直接给出选股需求，Agent 会结合记忆、行情、新闻和知识库继续分析。");
      setSummaryBullets([]);
      setRiskItems(["尚未生成风险提示。"]);
      return;
    }
    const conclusion = nextCards.find((card) => card.card_type === "conclusion") || nextCards[0];
    const riskCard = nextCards.find((card) => card.card_type === "risk");
    setSummaryTitle(conclusion?.title || "分析完成");
    setSummaryText(conclusion?.summary || "已生成本轮结构化分析。");
    setSummaryBullets((conclusion?.items || []).slice(0, 4));
    setRiskItems(riskCard?.items?.length ? riskCard.items : ["暂无额外风险提示。"]);
  }, []);

  const resetInsightPanels = useCallback(() => {
    applyCards([]);
    setCitations([]);
    setStatusItems(["系统待命。"]);
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
      setAgent("warn", "资料加载失败", error instanceof Error ? error.message : "无法读取资料详情。");
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
    if (!nextId) {
      setSelectedLibraryDocId("");
      setSelectedLibraryDoc(null);
      return files;
    }
    await loadLibraryDocument(nextId);
    return files;
  }, [api, loadLibraryDocument, selectedLibraryDocId]);

  const refreshCoreData = useCallback(async () => {
    const results = await Promise.allSettled([api.dashboard(), api.health(), api.memory(), api.files(), api.models(), api.profile(), api.avatarProfile()]);
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
    setConversationTitle(session.title || "新对话");
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
    setAgent("loading", "查询个股", "正在拉取实时行情、K 线、资金流和重点事件。");
    try {
      const result = await api.queryStock(normalized);
      setSecurity(result);
      setSecurityQuery(result.quote?.symbol || normalized);
      setAgent("idle", "个股详情已更新", "你可以继续围绕这只股票追问，系统会把它写入近期上下文。");
      const memorySnapshot = await api.memory();
      setMemory(memorySnapshot);
    } catch (error) {
      setAgent("warn", "查询失败", error instanceof Error ? error.message : "未能识别该标的。");
    } finally {
      setSecurityBusy(false);
    }
  }, [api, securityQuery, setAgent]);

  const uploadFiles = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.querySelector('input[type="file"]') as HTMLInputElement | null;
    if (!input?.files?.length) return;
    const body = new FormData();
    Array.from(input.files).forEach((file) => body.append("files", file));
    body.append("model_provider", modelProvider || "deepseek");
    setAgent("loading", "上传资料中", "正在写入你的私有知识库。");
    try {
      const result = await api.upload(body);
      input.value = "";
      const preferredDocId = result.added[0]?.doc_id;
      const [, memorySnapshot] = await Promise.all([refreshLibrary(preferredDocId), api.memory()]);
      setMemory(memorySnapshot);
      if (preferredDocId) setTask("library");
      setAgent("idle", "资料已入库", preferredDocId ? "已切换到资料管理，可继续预览和核对分块。" : "后续问答会优先引用你的私有资料。");
    } catch (error) {
      setAgent("warn", "上传失败", error instanceof Error ? error.message : "上传失败。");
    }
  }, [api, modelProvider, refreshLibrary, setAgent]);

  const saveProfile = useCallback(async () => {
    try {
      const payload: UserProfile = {
        ...profile,
        profile_id: user?.user_id || profile.profile_id,
      };
      const saved = await api.saveProfile(payload);
      setProfile(saved);
      setMemory(await api.memory());
      setAgent("idle", "画像已保存", "风险偏好、投资期限与关注方向已写入长期记忆。");
    } catch (error) {
      setAgent("warn", "画像保存失败", error instanceof Error ? error.message : "保存失败。");
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
        setConversationTitle(payload.conversation.title || "当前对话");
        window.localStorage.setItem(ACTIVE_CONV_KEY, payload.conversation.conversation_id);
      }
      return;
    }
    if (event.type === "ack" || event.type === "market_fetch_started" || event.type === "rag_fetch_started") {
      const payload = event as StreamBaseEvent;
      if (payload.message) {
        setStatusItems((current) => [...current, payload.message || "处理中。"]);
      }
      return;
    }
    if (event.type === "route") {
      const payload = event as StreamRouteEvent;
      setRouteBadge(`${payload.route.task_type} / ${payload.route.reason}`);
      setStatusItems((current) => [...current, `已路由到 ${payload.route.task_type}`]);
      return;
    }
    if (event.type === "market_fetch_done") {
      const payload = event as StreamBaseEvent;
      setStatusItems((current) => [...current, payload.degraded ? "实时数据阶段已降级。" : "实时数据已返回。"]);
      return;
    }
    if (event.type === "rag_fetch_done") {
      const payload = event as StreamBaseEvent & { citations?: CitationItem[] };
      setStatusItems((current) => [...current, payload.degraded ? "知识证据阶段已降级。" : `已匹配 ${payload.citations?.length || 0} 条证据。`]);
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
      setRouteBadge(`${payload.route?.task_type || "analysis"} / 完成`);
      setAgent("idle", "分析完成", `已完成对“${source.slice(0, 18)}”的分析。`);
      setLastAssistantMessage(answer);
      return;
    }
    if (event.type === "error") {
      const payload = event as StreamBaseEvent & { detail?: string };
      updateAssistantMessage(assistantMessageIdRef.current, `分析失败：${payload.detail || "unknown error"}`);
      setRouteBadge("异常");
      setAgent("warn", "分析异常", "本次回答未完整返回。");
    }
  }, [applyCards, setAgent, updateAssistantMessage]);


  const submitMessage = useCallback(async (rawText?: string) => {
    const message = String(rawText || draft).trim();
    if (!message) return;
    if (controllerRef.current) controllerRef.current.abort();
    setTask("auto");
    setDraft("");
    resetInsightPanels();
    setRouteBadge("路由中");
    setStatusItems([
      "请求已发送。",
      security?.quote?.symbol ? `沿用 ${security.quote.symbol} 的已选标的上下文。` : "未做前置证券解析，直接进入流式分析。",
      "正在连接分析引擎与证据链路。",
    ]);
    setAgent("loading", "正在分析", "已跳过前置阻塞解析，直接开始流式检索与生成。");
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
            task_type: null,
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
      setRouteBadge("异常");
      setAgent("warn", "分析异常", detail);
    } finally {
      controllerRef.current = null;
      setStreaming(false);
      const [conversationList, memorySnapshot] = await Promise.allSettled([refreshConversations(), api.memory()]);
      if (conversationList.status === "fulfilled") {
        const currentConversation = conversationList.value.find((item) => item.conversation_id === conversationId);
        if (currentConversation) setConversationTitle(currentConversation.title || "新对话");
      }
      if (memorySnapshot.status === "fulfilled") setMemory(memorySnapshot.value);
    }
  }, [activeConversationId, analysisMode, api, createConversation, draft, messages, modelProvider, processStreamEvent, refreshConversations, resetInsightPanels, security?.profile?.company_name, security?.profile?.sector, security?.quote?.symbol, setAgent, updateAssistantMessage]);

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
    const confirmed = window.confirm(`确认删除资料「${current?.title || current?.filename || docId}」？这会同时删除原文件和知识库索引。`);
    if (!confirmed) return;
    setLibraryDeletingDocId(docId);
    try {
      await api.deleteLibraryDocument(docId);
      await refreshLibrary(selectedLibraryDocId === docId ? "" : selectedLibraryDocId);
      setAgent("idle", "资料已删除", "原始文件与知识库索引已同步移除。");
    } catch (error) {
      setAgent("warn", "删除失败", error instanceof Error ? error.message : "资料删除失败。");
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
        // ignore logout failures
      }
    }
    handleUnauthorized();
    resetInsightPanels();
  }, [api, handleUnauthorized, resetInsightPanels, token]);

  useEffect(() => {
    window.localStorage.setItem(AVATAR_VOICE_KEY, avatarVoiceEnabled ? "1" : "0");
  }, [avatarVoiceEnabled]);

  useEffect(() => {
    if (task !== "library" || libraryDetailBusy) return;
    if (!libraryFiles.length) {
      setSelectedLibraryDocId("");
      setSelectedLibraryDoc(null);
      return;
    }
    const hasSelected = selectedLibraryDocId && libraryFiles.some((item) => item.doc_id === selectedLibraryDocId);
    if (selectedLibraryDoc && selectedLibraryDoc.doc_id === selectedLibraryDocId && hasSelected) {
      return;
    }
    const nextId = hasSelected ? selectedLibraryDocId : libraryFiles[0].doc_id;
    if (!nextId) return;
    void loadLibraryDocument(nextId);
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
        setAgent("loading", "初始化中", "正在同步你的画像、记忆、总览与对话历史。");
        await refreshCoreData();
        await initConversations();
        setAgent("idle", "待命中", "市场总览与长期记忆已同步，可以开始工作。");
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
      if (security?.quote?.symbol) {
        void queryStock(security.quote.symbol);
      }
    }, 60000);
    return () => window.clearInterval(timer);
  }, [queryStock, refreshCoreData, security?.quote?.symbol, streaming, token, user]);

  const handleLogin = async (username: string, password: string): Promise<void> => {
    setAuthBusy(true);
    setAuthError("");
    try {
      const payload = await api.login(username, password);
      setToken(payload.token);
      setUser(payload.user);
      window.localStorage.setItem(TOKEN_KEY, payload.token);
      setAgent("loading", "初始化中", "正在同步你的画像、记忆、总览与对话历史。");
      await refreshCoreData();
      await initConversations();
      setAgent("idle", "待命中", "工作台已准备就绪。");
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
      setToken(payload.token);
      setUser(payload.user);
      window.localStorage.setItem(TOKEN_KEY, payload.token);
      setAgent("loading", "初始化中", "正在创建你的工作台和长期记忆。");
      await refreshCoreData();
      await initConversations();
      setAgent("idle", "待命中", "专属席位已经创建完成。");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "注册失败");
    } finally {
      setAuthBusy(false);
    }
  };

  if (!token || !user) {
    return <AuthScreen mode={authMode} busy={authBusy} error={authError} onSwitch={setAuthMode} onLogin={handleLogin} onRegister={handleRegister} />;
  }

  const securityPath = chartPath(security?.history || []);
  const securitySvgPath = securityPath.join(" ");

  return (
    <div className="app-shell">
      <header className="topbar panel">
        <div>
          <p className="section-kicker">FinAvatar Enterprise Desk</p>
          <h1>金融数字人分析工作台</h1>
        </div>
        <div className="topbar-meta">
          <button className={`nav-chip ${task === "dashboard" ? "active" : ""}`} type="button" onClick={() => setTask("dashboard")}>
            市场总览
          </button>
          <button className={`nav-chip ${task === "auto" ? "active" : ""}`} type="button" onClick={() => setTask("auto")}>
            智能问答
          </button>
          <button className={`nav-chip ${task === "library" ? "active" : ""}`} type="button" onClick={() => setTask("library")}>
            资料管理
          </button>
          <span className={`status-pill ${agentState === "warn" ? "status-warn" : agentState === "loading" ? "status-loading" : "status-good"}`}>{agentTitle}</span>
          <span className="status-pill status-neutral">{analysisMode}</span>
          <button className="button ghost" type="button" onClick={() => void logout()}>
            退出
          </button>
        </div>
      </header>

      <div className="workspace-grid">
        <aside className="sidebar-column">
          <AvatarPanel
            profile={avatarProfile}
            voiceEnabled={avatarVoiceEnabled}
            agentTitle={agentTitle}
            agentCaption={agentCaption}
            routeBadge={routeBadge}
            runtimeState={agentState}
            lastAssistantMessage={lastAssistantMessage}
            onTranscript={(text) => void submitMessage(text)}
            onToggleVoice={() => setAvatarVoiceEnabled((current) => !current)}
            onSaveProfile={async (nextProfile) => {
              const saved = await api.saveAvatarProfile(nextProfile);
              setAvatarProfile(saved);
            }}
          />

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Copilot Control</p>
                <h2>分析参数</h2>
              </div>
            </div>
            <div className="form-grid two-col">
              <label className="field">
                <span>分析风格</span>
                <select value={analysisMode} onChange={(event) => setAnalysisMode(event.target.value as AnalysisMode)}>
                  <option value="professional">专业分析</option>
                  <option value="summary">简洁摘要</option>
                  <option value="teaching">教学解释</option>
                </select>
              </label>
              <label className="field">
                <span>模型</span>
                <select value={modelProvider} onChange={(event) => setModelProvider(event.target.value)}>
                  {(models.length ? models : [{ id: "deepseek", label: "DeepSeek" }]).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="toolbar-row">
              <button className="button secondary" type="button" onClick={() => void refreshCoreData()}>
                刷新总览
              </button>
              <button className="button ghost" type="button" onClick={() => void api.recordEvent("switch_module", `切换到 ${TASK_LABELS[task]}`, { task_type: task })}>
                记录动作
              </button>
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Investor Profile</p>
                <h2>用户画像</h2>
              </div>
              <button className="button ghost" type="button" onClick={() => void saveProfile()}>
                保存画像
              </button>
            </div>
            <div className="form-grid two-col">
              <label className="field">
                <span>风险偏好</span>
                <select value={profile.risk_level} onChange={(event) => setProfile((current) => ({ ...current, risk_level: event.target.value as UserProfile["risk_level"] }))}>
                  <option value="low">稳健</option>
                  <option value="medium">均衡</option>
                  <option value="high">积极</option>
                </select>
              </label>
              <label className="field">
                <span>投资期限</span>
                <select value={profile.investment_horizon} onChange={(event) => setProfile((current) => ({ ...current, investment_horizon: event.target.value as UserProfile["investment_horizon"] }))}>
                  <option value="short">短期</option>
                  <option value="medium">中期</option>
                  <option value="long">长期</option>
                </select>
              </label>
              <label className="field full-span">
                <span>关注市场</span>
                <input value={joinTags(profile.markets)} onChange={(event) => setProfile((current) => ({ ...current, markets: splitTags(event.target.value) }))} />
              </label>
              <label className="field full-span">
                <span>偏好方向</span>
                <input value={joinTags(profile.sector_preferences)} onChange={(event) => setProfile((current) => ({ ...current, sector_preferences: splitTags(event.target.value) }))} />
              </label>
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Private Vault</p>
                <h2>知识库资料</h2>
              </div>
              <span className="status-pill status-neutral">已上传 {libraryCount} 份</span>
            </div>
            <form className="form-grid" onSubmit={(event) => void uploadFiles(event)}>
              <label className="field">
                <span>上传文档</span>
                <input type="file" name="files" multiple accept=".txt,.md,.pdf,.docx,.csv,.json,.html,.htm,.xlsx" />
              </label>
              <div className="toolbar-row">
                <button className="button primary" type="submit">写入私有知识库</button>
                <button className="button ghost" type="button" onClick={() => setTask("library")}>进入资料管理</button>
              </div>
            </form>
          </section>
        </aside>

        <main className="main-column">
          <section className="panel briefing-panel">
            <div>
              <p className="section-kicker">Desk Status</p>
              <h2>{agentTitle}</h2>
              <p className="muted-copy">{agentCaption}</p>
            </div>
            <div className="pill-row">
              <span className="status-pill status-neutral">用户 {user.display_name || user.username}</span>
              <span className="status-pill status-neutral">路由 {routeBadge}</span>
              <span className="status-pill status-neutral">模式 {analysisMode}</span>
            </div>
          </section>

          {task === "dashboard" ? (
            <>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <p className="section-kicker">Security Focus</p>
                    <h2>个股深挖</h2>
                  </div>
                </div>
                <div className="toolbar-row">
                  <input className="hero-search" value={securityQuery} onChange={(event) => setSecurityQuery(event.target.value)} placeholder="输入股票代码或名称，例如 600519 / 贵州茅台" />
                  <button className="button primary" type="button" onClick={() => void queryStock(securityQuery)} disabled={securityBusy}>
                    {securityBusy ? "查询中..." : "查询个股"}
                  </button>
                </div>
                {security ? (
                  <div className="security-shell">
                    <div className="security-summary-card">
                      <div>
                        <h3>{security.quote?.name || security.profile?.company_name || security.quote?.symbol || "个股详情"}</h3>
                        <div className="pill-row compact">
                          <span className="status-pill status-neutral">{security.quote?.symbol || "--"}</span>
                          <span className="status-pill status-neutral">{security.profile?.sector || "待补充行业"}</span>
                          <span className="status-pill status-neutral">{security.profile?.industry || "待补充分组"}</span>
                        </div>
                      </div>
                      <div className="security-price-block">
                        <strong className={toneClass(security.quote?.change_percent)}>{num(security.quote?.last_price)}</strong>
                        <span className={toneClass(security.quote?.change_percent)}>{pct(security.quote?.change_percent)}</span>
                      </div>
                    </div>
                    <div className="security-grid">
                      <article className="subpanel">
                        <div className="subpanel-head">
                          <h3>走势概览</h3>
                          <span className="muted-copy">近 {security.history?.length || 0} 个交易日</span>
                        </div>
                        {securitySvgPath ? (
                          <svg className="line-chart" viewBox="0 0 640 220" preserveAspectRatio="none">
                            <defs>
                              <linearGradient id="securityGradient" x1="0" x2="0" y1="0" y2="1">
                                <stop offset="0%" stopColor="rgba(77, 211, 194, 0.38)" />
                                <stop offset="100%" stopColor="rgba(77, 211, 194, 0.04)" />
                              </linearGradient>
                            </defs>
                            <path d={`${securitySvgPath} L 640 220 L 0 220 Z`} fill="url(#securityGradient)" />
                            <path d={securitySvgPath} fill="none" stroke="#4dd3c2" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        ) : (
                          <div className="empty-state">暂无 K 线历史数据。</div>
                        )}
                      </article>

                      <article className="subpanel">
                        <div className="subpanel-head">
                          <h3>关键数据</h3>
                        </div>
                        <div className="metrics-grid compact-grid">
                          <Metric label="成交额" value={turnover(security.quote?.turnover)} />
                          <Metric label="换手率" value={pct(security.quote?.turnover_rate)} />
                          <Metric label="振幅" value={pct(security.quote?.amplitude)} />
                          <Metric label="PE / PB" value={`${num(security.profile?.pe)} / ${num(security.profile?.pb)}`} />
                          <Metric label="ROE / 负债率" value={`${pct(security.profile?.roe)} / ${pct(security.profile?.debt_ratio)}`} />
                          <Metric label="主力资金" value={turnover(security.capital_flow?.main_net_inflow)} />
                        </div>
                        <p className="muted-copy">{security.capital_flow?.summary || "暂无资金流摘要。"}</p>
                        <div className="pill-row compact">
                          <span className="status-pill status-neutral">RSI14 {num(security.technical?.rsi14)}</span>
                          <span className="status-pill status-neutral">MA5 {num(security.technical?.ma5)}</span>
                          <span className="status-pill status-neutral">MA20 {num(security.technical?.ma20)}</span>
                          <span className="status-pill status-neutral">趋势 {security.technical?.momentum_label || "--"}</span>
                        </div>
                      </article>
                    </div>
                    <article className="subpanel">
                      <div className="subpanel-head">
                        <h3>重点事件</h3>
                      </div>
                      <div className="list-stack">
                        {(security.news || []).length ? (
                          security.news?.map((item, index) => (
                            <div className="list-card" key={`${item.title || "news"}-${index}`}>
                              <div className="card-topline">
                                <strong>{item.title || "未命名事件"}</strong>
                                <span className="status-pill status-neutral">{item.theme || item.event_type || "事件"}</span>
                              </div>
                              <p>{item.summary || "--"}</p>
                              <div className="pill-row compact">
                                <span className="status-pill status-neutral">{item.source || "--"}</span>
                                <span className="status-pill status-neutral">{formatTimeLabel(item.publish_time)}</span>
                              </div>
                              {item.agent_reason ? <p className="muted-copy">{item.agent_reason}</p> : null}
                            </div>
                          ))
                        ) : (
                          <div className="empty-state">暂无可用热点事件。</div>
                        )}
                      </div>
                    </article>
                  </div>
                ) : (
                  <div className="empty-state">输入一只 A 股，系统会返回详细数据、资金流、热点事件和 K 线概览。</div>
                )}
              </section>

              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <p className="section-kicker">Market Overview</p>
                    <h2>实时市场总览</h2>
                  </div>
                </div>
                <div className="metrics-grid">
                  {(dashboard?.indices || []).length ? (
                    dashboard?.indices.map((item) => (
                      <article className="metric-tile" key={item.name}>
                        <span>{item.name}</span>
                        <strong>{num(item.last_price)}</strong>
                        <em className={toneClass(item.change_percent)}>{pct(item.change_percent)}</em>
                        <small>成交额 {turnover(item.turnover)}</small>
                      </article>
                    ))
                  ) : (
                    <div className="empty-state">暂无指数数据。</div>
                  )}
                </div>
                <div className="insight-grid three-up">
                  <article className="subpanel">
                    <div className="subpanel-head"><h3>市场风格</h3></div>
                    <strong>{dashboard?.market_sentiment?.regime || "--"}</strong>
                    <p>{dashboard?.market_sentiment?.summary || "暂无情绪摘要。"}</p>
                  </article>
                  <ListPanel title="热门板块" items={dashboard?.hot_sectors || []} onSelect={(value) => void queryStock(String(value.symbol || value.name || ""))} />
                  <ListPanel title="热门 ETF" items={dashboard?.hot_etfs || []} onSelect={() => undefined} />
                  <ListPanel title="涨幅居前" items={dashboard?.top_gainers || []} onSelect={(value) => void queryStock(String(value.symbol || ""))} />
                  <ListPanel title="成交额领先" items={dashboard?.top_turnover || []} onSelect={(value) => void queryStock(String(value.symbol || ""))} />
                  <article className="subpanel events-panel">
                    <div className="subpanel-head"><h3>重点事件</h3></div>
                    <div className="list-stack">
                      {(dashboard?.latest_events || []).length ? (
                        dashboard?.latest_events.map((item, index) => (
                          <div className="list-card" key={`${item.title}-${index}`}>
                            <div className="card-topline">
                              <strong>{item.title}</strong>
                              <span className="status-pill status-neutral">{item.theme || item.event_type || "事件"}</span>
                            </div>
                            <p>{item.summary || "--"}</p>
                            <div className="pill-row compact">
                              <span className="status-pill status-neutral">{item.source || "--"}</span>
                              <span className="status-pill status-neutral">{formatTimeLabel(item.publish_time)}</span>
                              <span className="status-pill status-neutral">评分 {num(item.importance_score, 1)}</span>
                            </div>
                            {item.agent_reason ? <p className="muted-copy">Agent 筛选理由：{item.agent_reason}</p> : null}
                          </div>
                        ))
                      ) : (
                        <div className="empty-state">暂无热点事件。</div>
                      )}
                    </div>
                  </article>
                </div>
              </section>
            </>
          ) : task === "auto" ? (
            <>
              <section className="panel composer-panel">
                <div className="panel-heading">
                  <div>
                    <p className="section-kicker">Conversation</p>
                    <h2>{conversationTitle}</h2>
                  </div>
                  <div className="toolbar-row">
                    <button className="button secondary" type="button" onClick={() => void createConversation(true)}>
                      新对话
                    </button>
                    <button className="button ghost" type="button" onClick={() => void removeConversation()}>
                      删除对话
                    </button>
                  </div>
                </div>
                <div className="quick-prompt-row">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button className="prompt-chip" key={prompt} type="button" onClick={() => void submitMessage(prompt)}>
                      {prompt}
                    </button>
                  ))}
                </div>
                <div className="message-stream">
                  {messages.length ? (
                    messages.map((message) => (
                      <article key={message.message_id} className={`message-card ${message.role}`}>
                        <div className="message-head">{message.role === "user" ? "USER" : "FINAVATAR"}</div>
                        <MarkdownBlock text={message.content || (message.role === "assistant" ? "正在生成..." : "")} />
                      </article>
                    ))
                  ) : (
                    <div className="empty-state">这是一个新对话，可以直接开始提问。</div>
                  )}
                </div>
                <form className="composer-row" onSubmit={(event) => { event.preventDefault(); void submitMessage(); }}>
                  <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="例如：结合我最近的偏好，今天还有哪些 A 股值得继续跟踪？" rows={4} />
                  <div className="toolbar-row align-end">
                    <button className="button ghost" type="button" onClick={() => controllerRef.current?.abort()} disabled={!streaming}>
                      停止生成
                    </button>
                    <button className="button primary" type="submit" disabled={streaming}>
                      {streaming ? "分析中..." : "发起分析"}
                    </button>
                  </div>
                </form>
              </section>

              <section className="analysis-layout">
                <article className="panel">
                  <div className="panel-heading">
                    <div>
                      <p className="section-kicker">Structured Output</p>
                      <h2>{summaryTitle}</h2>
                    </div>
                  </div>
                  <p className="muted-copy">{summaryText}</p>
                  <ul className="bullet-list">
                    {summaryBullets.length ? summaryBullets.map((item) => <li key={item}>{item}</li>) : <li>等待结构化摘要。</li>}
                  </ul>
                  <div className="analysis-card-grid">
                    {cards.length ? (
                      cards.map((card, index) => (
                        <article className="analysis-card" key={`${card.title || card.card_type || "card"}-${index}`}>
                          <p className="section-kicker">{card.card_type || "分析卡"}</p>
                          <h3>{card.title || "分析"}</h3>
                          <p>{card.summary || "--"}</p>
                          {card.items?.length ? (
                            <ul className="bullet-list">
                              {card.items.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          ) : null}
                        </article>
                      ))
                    ) : (
                      <div className="empty-state">暂无结构化分析卡片。</div>
                    )}
                  </div>
                </article>

                <article className="panel">
                  <div className="panel-heading">
                    <div>
                      <p className="section-kicker">Evidence & Risk</p>
                      <h2>引用与风险</h2>
                    </div>
                  </div>
                  <div className="risk-strip">
                    <strong>风险提示</strong>
                    <ul className="bullet-list">
                      {riskItems.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="list-stack">
                    {citations.length ? (
                      citations.map((item, index) => (
                        <div className="list-card" key={`${item.title || "citation"}-${index}`}>
                          <strong>{item.title || "证据"}</strong>
                          <p className="muted-copy">{item.section_title || "未分节"}{item.time_label ? ` · ${formatTimeLabel(item.time_label)}` : ""}</p>
                          <p>{item.preview || "--"}</p>
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">本次回答没有引用到私有知识库证据。</div>
                    )}
                  </div>
                </article>
              </section>            </>
          ) : (
            <LibraryWorkspace
              files={libraryFiles}
              search={librarySearch}
              selectedDocumentId={selectedLibraryDocId}
              selectedDocument={selectedLibraryDoc}
              detailBusy={libraryDetailBusy}
              deletingDocId={libraryDeletingDocId}
              onSearchChange={setLibrarySearch}
              onSelectDocument={(docId) => { void loadLibraryDocument(docId); }}
              onRefresh={() => { void refreshLibrary(); }}
              onDeleteDocument={(docId) => { void deleteLibraryDocument(docId); }}
            />
          )}
        </main>

        <aside className="right-column">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Conversation Navigator</p>
                <h2>会话历史</h2>
              </div>
            </div>
            <div className="list-stack">
              {conversations.length ? (
                conversations.map((item) => (
                  <button className={`conversation-item ${item.conversation_id === activeConversationId ? "active" : ""}`} key={item.conversation_id} type="button" onClick={() => void loadConversation(item.conversation_id)}>
                    <strong>{item.title || "新对话"}</strong>
                    <p>{item.last_message_preview || "暂无消息"}</p>
                    <span>{item.message_count || 0} 条消息</span>
                  </button>
                ))
              ) : (
                <div className="empty-state">还没有历史对话。</div>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Agent Memory</p>
                <h2>长期记忆</h2>
              </div>
            </div>
            <p className="muted-copy">{memory.summary}</p>
            <TagRow label="偏好标签" items={memory.preference_tags} />
            <TagRow label="最近关注股票" items={memory.recent_symbols} />
            <TagRow label="最近关注板块" items={memory.recent_sectors} />
            <div className="subpanel mini-panel">
              <strong>最近动作</strong>
              <ul className="bullet-list">
                {memory.recent_actions.length ? memory.recent_actions.map((item) => <li key={item}>{item}</li>) : <li>暂无记录</li>}
              </ul>
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Runtime Health</p>
                <h2>链路状态</h2>
              </div>
            </div>
            <div className="list-stack">
              {(health?.providers || []).length ? (
                health?.providers.map((item) => (
                  <div className={`provider-card ${item.ok ? "ok" : "fail"}`} key={item.provider}>
                    <div className="card-topline">
                      <strong>{item.provider}</strong>
                      <span>{item.ok ? "可用" : "降级"}</span>
                    </div>
                    <p className="muted-copy">延迟 {item.latency_ms ?? "--"} ms</p>
                    {item.error ? <p className="muted-copy">{item.error}</p> : null}
                  </div>
                ))
              ) : (
                <div className="empty-state">尚未检测。</div>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">Execution Trace</p>
                <h2>运行状态</h2>
              </div>
            </div>
            <ul className="bullet-list status-list">
              {statusItems.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-tile mini">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TagRow({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="tag-row-block">
      <strong>{label}</strong>
      <div className="pill-row compact">
        {items.length ? items.map((item) => <span className="status-pill status-neutral" key={item}>{item}</span>) : <span className="status-pill status-neutral">暂无</span>}
      </div>
    </div>
  );
}

function ListPanel(props: {
  title: string;
  items: Array<Record<string, unknown>>;
  onSelect: (item: Record<string, unknown>) => void;
}) {
  return (
    <article className="subpanel">
      <div className="subpanel-head"><h3>{props.title}</h3></div>
      <div className="list-stack">
        {props.items.length ? (
          props.items.map((item, index) => (
            <button className="list-card selectable" key={`${props.title}-${String(item.name || item.symbol || index)}`} type="button" onClick={() => props.onSelect(item)}>
              <div className="card-topline">
                <strong>{String(item.name || item.sector || item.fund_name || item.symbol || "--")}</strong>
                <span className={toneClass(Number(item.change_percent ?? item.daily_change ?? 0))}>{pct(Number(item.change_percent ?? item.daily_change ?? 0))}</span>
              </div>
              <div className="pill-row compact">
                {item.symbol ? <span className="status-pill status-neutral">{String(item.symbol)}</span> : null}
                {item.turnover ? <span className="status-pill status-neutral">成交额 {turnover(Number(item.turnover))}</span> : null}
                {item.leader_name ? <span className="status-pill status-neutral">龙头 {String(item.leader_name)}</span> : null}
              </div>
            </button>
          ))
        ) : (
          <div className="empty-state">暂无数据。</div>
        )}
      </div>
    </article>
  );
}

