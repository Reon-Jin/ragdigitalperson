export type TaskType = "dashboard" | "auto" | "library";
export type AnalysisMode = "summary" | "professional" | "teaching";
export type ModelProvider = "deepseek" | "qwen" | "mimo" | "ollama";
export type MessageRole = "user" | "assistant";

export interface AuthUser {
  user_id: string;
  username: string;
  display_name: string;
  created_at: string;
  last_login_at: string;
}

export interface SessionResponse {
  authenticated: boolean;
  user: AuthUser | null;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface ModelItem {
  id: string;
  label: string;
  configured?: boolean;
}

export interface UserProfile {
  profile_id: string;
  risk_level: "low" | "medium" | "high";
  investment_horizon: "short" | "medium" | "long";
  markets: string[];
  sector_preferences: string[];
  style_preference: "summary" | "advisor" | "teaching";
}

export interface LocalAvatarProfile {
  avatar_id: string;
  display_name: string;
  greeting: string;
  persona: string;
  default_language: string;
  voice_name: string;
  portrait_data_url?: string | null;
  motion_mode: "portrait_motion" | "studio_card";
  tts_backend: "browser" | "local_server";
  asr_backend: "browser" | "manual";
  note?: string | null;
  updated_at: string;
}

export interface DashboardIndex {
  name: string;
  last_price: number;
  change_percent: number;
  turnover?: number;
}

export interface DashboardEvent {
  title: string;
  summary?: string;
  theme?: string;
  event_type?: string;
  source?: string;
  publish_time?: string;
  importance_score?: number;
  agent_reason?: string;
  action_hint?: string;
}

export interface MarketSentiment {
  regime?: string;
  avg_index_move?: number;
  summary?: string;
}

export interface DashboardOverview {
  indices: DashboardIndex[];
  market_sentiment?: MarketSentiment;
  hot_sectors: Array<Record<string, unknown>>;
  hot_etfs: Array<Record<string, unknown>>;
  top_gainers: Array<Record<string, unknown>>;
  top_turnover: Array<Record<string, unknown>>;
  latest_events: DashboardEvent[];
}

export interface ProviderHealthItem {
  provider: string;
  ok: boolean;
  latency_ms?: number | null;
  error?: string | null;
}

export interface HealthPayload {
  status: string;
  providers: ProviderHealthItem[];
}

export interface AgentMemory {
  summary: string;
  recent_symbols: string[];
  recent_sectors: string[];
  preference_tags: string[];
  recent_tasks: string[];
  recent_actions: string[];
  updated_at: string;
}

export interface QuotePayload {
  symbol?: string;
  name?: string;
  last_price?: number;
  change_percent?: number;
  turnover?: number;
  turnover_rate?: number;
  amplitude?: number;
}

export interface StockProfilePayload {
  company_name?: string;
  sector?: string;
  industry?: string;
  pe?: number;
  pb?: number;
  roe?: number;
  debt_ratio?: number;
  dividend_yield?: number;
}

export interface TechnicalPayload {
  rsi14?: number;
  ma5?: number;
  ma20?: number;
  momentum_label?: string;
}

export interface CapitalFlowPayload {
  main_net_inflow?: number;
  summary?: string;
  trend_label?: string;
}

export interface HistoryPoint {
  close?: number;
  open?: number;
}

export interface NewsItem {
  title?: string;
  summary?: string;
  theme?: string;
  event_type?: string;
  source?: string;
  publish_time?: string;
  agent_reason?: string;
}

export interface SecurityPayload {
  quote?: QuotePayload;
  profile?: StockProfilePayload;
  technical?: TechnicalPayload;
  capital_flow?: CapitalFlowPayload;
  history?: HistoryPoint[];
  news?: NewsItem[];
}

export interface LibraryFileItem {
  doc_id: string;
  filename: string;
  category: string;
  title: string;
  suffix: string;
  uploaded_at: string;
  chunk_count: number;
  section_count: number;
  summary: string;
  keywords: string[];
}

export interface UploadResponse {
  added: LibraryFileItem[];
  skipped: string[];
}

export interface ChunkPreview {
  chunk_id: string;
  chunk_index: number;
  chunk_title: string;
  chunk_kind: string;
  section_id: string;
  section_title: string;
  preview: string;
  word_count: number;
  page_start?: number | null;
  page_end?: number | null;
}

export interface SectionSummary {
  section_id: string;
  doc_id: string;
  title: string;
  order: number;
  summary: string;
  chunk_count: number;
  previews: ChunkPreview[];
}

export interface ChunkDetail extends ChunkPreview {
  text: string;
  char_start: number;
  char_end: number;
}

export interface PageDetail {
  doc_id: string;
  page_number: number;
  char_start: number;
  char_end: number;
  preview: string;
  text: string;
  chunks: ChunkPreview[];
}

export interface DocumentDetail extends LibraryFileItem {
  headings: string[];
  sections: SectionSummary[];
  chunks: ChunkDetail[];
  pages: PageDetail[];
}

export interface ConversationMessage {
  message_id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  task_type?: string | null;
  route?: Record<string, unknown> | null;
}

export interface ConversationSession {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface AnalysisCard {
  card_type?: string;
  title?: string;
  summary?: string;
  items?: string[];
  payload?: SecurityPayload;
}

export interface CitationItem {
  title?: string;
  section_title?: string;
  preview?: string;
  time_label?: string;
}

export interface RouteDecision {
  task_type: string;
  reason: string;
}

export interface StreamBaseEvent {
  type: string;
  message?: string;
  degraded?: boolean;
}

export interface StreamRouteEvent extends StreamBaseEvent {
  route: RouteDecision;
}

export interface StreamConversationEvent extends StreamBaseEvent {
  conversation?: {
    conversation_id?: string;
    title?: string;
  };
}

export interface StreamCardsEvent extends StreamBaseEvent {
  cards: AnalysisCard[];
}

export interface StreamCitationsEvent extends StreamBaseEvent {
  items: CitationItem[];
}

export interface StreamDeltaEvent extends StreamBaseEvent {
  delta?: string;
}

export interface StreamFinalEvent extends StreamBaseEvent {
  answer?: string;
  cards?: AnalysisCard[];
  citations?: CitationItem[];
  route?: RouteDecision;
  metadata?: {
    warnings?: string[];
  };
}

export type StreamEvent =
  | StreamBaseEvent
  | StreamRouteEvent
  | StreamConversationEvent
  | StreamCardsEvent
  | StreamCitationsEvent
  | StreamDeltaEvent
  | StreamFinalEvent;
