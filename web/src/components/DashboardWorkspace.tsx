import { useState } from "react";

import { formatTimeLabel, num, pct, splitTags, toneClass, turnover } from "../lib/format";
import { renderMarkdown } from "../lib/markdown";
import type {
  AnalysisMode,
  ConversationMessage,
  ConversationSummary,
  DashboardOverview,
  DeskSource,
  HealthPayload,
  ModelItem,
  SecurityPayload,
  UserProfile,
} from "../types";
import { TrendMiniChart } from "./TrendMiniChart";
import { SessionDrawer } from "./library/SessionDrawer";
import { Sidebar } from "./library/Sidebar";

interface ReferenceItem {
  title: string;
  summary: string;
  meta: string;
}

interface DashboardWorkspaceProps {
  profile: UserProfile;
  models: ModelItem[];
  modelProvider: string;
  analysisMode: AnalysisMode;
  deskSource: DeskSource;
  controlHint: string;
  securityQuery: string;
  securityBusy: boolean;
  dashboard: DashboardOverview | null;
  security: SecurityPayload | null;
  displayedSecurityName: string;
  displayedTicker: string;
  displayedPrice: number | null | undefined;
  displayedChange: number | null | undefined;
  routeBadge: string;
  sparkValues: number[];
  displayedSummaryTitle: string;
  displayedSummaryText: string;
  displayedBullets: string[];
  displayedRisks: string[];
  keyTags: string[];
  referenceItems: ReferenceItem[];
  rsiScore: number;
  riskScore: number;
  liquidityScore: number;
  confidenceScore: number;
  citationsCount: number;
  conversationTitle: string;
  messages: ConversationMessage[];
  draft: string;
  streaming: boolean;
  quickPrompts: string[];
  conversations: ConversationSummary[];
  activeConversationId: string;
  memorySummary: string;
  memoryTags: string[];
  health: HealthPayload | null;
  okProviders: number;
  statusItems: string[];
  userDisplayName: string;
  avatarVoiceEnabled: boolean;
  uploadQueuedCount: number;
  onProfileChange: (patch: Partial<UserProfile>) => void;
  onSaveProfile: () => void;
  onUploadFiles: (files: FileList | File[]) => void;
  onLogout: () => void;
  onGoLibrary: () => void;
  onGoDesk: () => void;
  onOpenSession: (conversationId: string) => void;
  onRefreshCoreData: () => void;
  onSecurityQueryChange: (value: string) => void;
  onQueryStock: (value?: string) => void;
  onDraftChange: (value: string) => void;
  onSubmitMessage: (prompt?: string) => void;
  onCreateConversation: () => void;
  onRemoveConversation: () => void;
  onAbortStream: () => void;
  onToggleVoice: () => void;
  onModelProviderChange: (value: string) => void;
  onAnalysisModeChange: (value: AnalysisMode) => void;
  onDeskSourceChange: (value: DeskSource) => void;
}

function markdownBlock(text: string) {
  return { __html: renderMarkdown(text) };
}

function metricTone(value?: number | null) {
  return toneClass(Number(value || 0));
}

export function DashboardWorkspace(props: DashboardWorkspaceProps) {
  const [sessionOpen, setSessionOpen] = useState(false);

  return (
    <>
      <div className="min-h-screen bg-[#071017] text-slate-100">
        <div className="grid min-h-screen grid-cols-[248px_minmax(0,1fr)_320px]">
          <Sidebar
            profile={props.profile}
            activeKey="overview"
            onSaveProfile={props.onSaveProfile}
            onBackToDesk={props.onGoDesk}
            onOpenSessions={() => setSessionOpen(true)}
            onLogout={props.onLogout}
            onProfileChange={props.onProfileChange}
            onUploadFiles={props.onUploadFiles}
            uploading={props.securityBusy}
            queuedCount={props.uploadQueuedCount}
          />

          <main className="min-w-0 bg-[radial-gradient(circle_at_top,_rgba(33,55,75,0.24),_transparent_42%)] px-6 py-6 2xl:px-8">
            <div className="mx-auto flex max-w-[1380px] flex-col gap-5">
              <header className="rounded-[24px] border border-white/8 bg-[#101720]/88 p-6 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
                <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-white/8 bg-white/4 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-slate-500">
                        Research Overview / Analysis Desk
                      </span>
                      <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-emerald-200">
                        {props.routeBadge}
                      </span>
                    </div>
                    <h2 className="mt-4 text-[28px] font-semibold tracking-[0.02em] text-slate-50">{props.displayedSecurityName}</h2>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-400">
                      <span>{props.displayedTicker}</span>
                      <span className="text-slate-600">/</span>
                      <span>{props.analysisMode}</span>
                      <span className="text-slate-600">/</span>
                      <span>{props.deskSource}</span>
                    </div>
                  </div>

                  <div className="w-full max-w-[420px]">
                    <label className="block text-[11px] uppercase tracking-[0.2em] text-slate-500">搜索标的</label>
                    <div className="mt-2 flex gap-2">
                      <input
                        className="min-w-0 flex-1 rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
                        value={props.securityQuery}
                        onChange={(event) => props.onSecurityQueryChange(event.target.value)}
                        placeholder="输入股票名称或代码，例如：600519 / 贵州茅台"
                      />
                      <button
                        type="button"
                        onClick={() => props.onQueryStock(props.securityQuery)}
                        disabled={props.securityBusy}
                        className="rounded-2xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200 hover:bg-emerald-400/14 disabled:opacity-50"
                      >
                        {props.securityBusy ? "加载中" : "查询"}
                      </button>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-500">{props.controlHint}</p>
                  </div>
                </div>

                <div className="mt-6 grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
                  {[
                    { label: "当前价格", value: num(props.displayedPrice), note: pct(props.displayedChange) },
                    { label: "PE / PB", value: `${num(props.security?.profile?.pe)} / ${num(props.security?.profile?.pb)}`, note: props.security?.profile?.sector || "Valuation" },
                    { label: "ROE", value: pct(props.security?.profile?.roe), note: props.security?.profile?.industry || "Profitability" },
                    { label: "主力资金", value: turnover(props.security?.capital_flow?.main_net_inflow), note: props.security?.capital_flow?.trend_label || "Capital Flow" },
                    { label: "证据覆盖", value: String(props.citationsCount), note: "Citations" },
                  ].map((item) => (
                    <article key={item.label} className="rounded-2xl border border-white/8 bg-[#121a24]/86 px-4 py-4">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
                      <div className="mt-3 flex items-end justify-between gap-4">
                        <strong className={`text-2xl font-semibold ${item.label === "当前价格" ? metricTone(props.displayedChange) : "text-slate-50"}`}>
                          {item.value}
                        </strong>
                        <span className="text-xs text-slate-500">{item.note}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </header>

              <section className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
                <div className="space-y-5">
                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
                      <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">价格快照</p>
                        <strong className={`mt-3 block text-[34px] font-semibold ${metricTone(props.displayedChange)}`}>{num(props.displayedPrice)}</strong>
                        <span className={`mt-2 block text-sm ${metricTone(props.displayedChange)}`}>{pct(props.displayedChange)}</span>
                        <p className="mt-4 text-xs uppercase tracking-[0.16em] text-slate-600">Route {props.routeBadge}</p>
                      </div>
                      <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">市场轨迹</p>
                        <div className="mt-3 h-[152px] overflow-hidden rounded-2xl bg-black/10">
                          {props.securityBusy && !props.sparkValues.length ? (
                            <div className="flex h-full items-center justify-center text-sm text-slate-500">加载中</div>
                          ) : (
                            <TrendMiniChart values={props.sparkValues} tone={Number(props.displayedChange) >= 0 ? "rise" : "fall"} />
                          )}
                        </div>
                      </div>
                    </div>
                  </section>

                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Primary Analysis</p>
                        <h3 className="mt-2 text-lg font-semibold text-slate-50">{props.displayedSummaryTitle}</h3>
                      </div>
                      <button
                        type="button"
                        onClick={props.onGoLibrary}
                        className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8"
                      >
                        进入知识库
                      </button>
                    </div>
                    <div className="mt-4 rounded-2xl border border-emerald-400/18 bg-emerald-400/[0.06] p-5">
                      <p className="text-sm leading-7 text-slate-200">{props.displayedSummaryText}</p>
                    </div>
                    <div className="mt-4 space-y-2">
                      {props.displayedBullets.length ? props.displayedBullets.map((item) => (
                        <div key={item} className="flex items-start gap-3 rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3 text-sm text-slate-300">
                          <span className="mt-2 h-1.5 w-1.5 rounded-full bg-emerald-400" />
                          <span>{item}</span>
                        </div>
                      )) : <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-4 text-sm text-slate-500">等待新的结构化结论。</div>}
                    </div>
                  </section>

                  <section className="grid gap-5 xl:grid-cols-2">
                    <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Risk</p>
                      <h3 className="mt-2 text-lg font-semibold text-slate-50">风险提示</h3>
                      <div className="mt-4 space-y-2">
                        {props.displayedRisks.length ? props.displayedRisks.map((item) => (
                          <div key={item} className="flex items-start gap-3 rounded-2xl border border-rose-400/16 bg-rose-400/[0.06] px-4 py-3 text-sm text-slate-200">
                            <span className="mt-2 h-1.5 w-1.5 rounded-full bg-rose-300" />
                            <span>{item}</span>
                          </div>
                        )) : <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-4 text-sm text-slate-500">暂无风险提示。</div>}
                      </div>
                    </section>

                    <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Context</p>
                      <h3 className="mt-2 text-lg font-semibold text-slate-50">辅助线索</h3>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {props.keyTags.length ? props.keyTags.map((tag) => (
                          <span key={tag} className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">{tag}</span>
                        )) : <span className="text-sm text-slate-500">暂无标签</span>}
                      </div>
                      <div className="mt-4 space-y-3">
                        {props.referenceItems.length ? props.referenceItems.map((item) => (
                          <article key={`${item.title}-${item.meta}`} className="rounded-2xl border border-white/6 bg-white/[0.02] p-4">
                            <p className="text-sm font-medium text-slate-100">{item.title}</p>
                            <p className="mt-2 text-sm leading-6 text-slate-400">{item.summary}</p>
                            <p className="mt-2 text-[11px] uppercase tracking-[0.16em] text-slate-600">{item.meta}</p>
                          </article>
                        )) : <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-4 text-sm text-slate-500">暂无辅助引用。</div>}
                      </div>
                    </section>
                  </section>

                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Conversation</p>
                        <h3 className="mt-2 text-lg font-semibold text-slate-50">{props.conversationTitle}</h3>
                      </div>
                      <div className="flex gap-2">
                        <button type="button" onClick={props.onCreateConversation} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">新会话</button>
                        <button type="button" onClick={props.onRemoveConversation} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">删除</button>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {props.quickPrompts.map((prompt) => (
                        <button key={prompt} type="button" onClick={() => props.onSubmitMessage(prompt)} className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-slate-300 hover:border-emerald-400/30 hover:bg-emerald-400/[0.06]">
                          {prompt}
                        </button>
                      ))}
                    </div>
                    <div className="mt-4 max-h-[420px] space-y-3 overflow-auto pr-1">
                      {props.messages.length ? props.messages.map((message) => (
                        <article key={message.message_id} className={`rounded-2xl border p-4 ${message.role === "assistant" ? "border-emerald-400/12 bg-emerald-400/[0.04]" : "border-white/8 bg-white/[0.03]"}`}>
                          <div className="mb-2 flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.16em] text-slate-500">
                            <span>{message.role === "user" ? "User" : "FinAvatar"}</span>
                            <span>{formatTimeLabel(message.created_at)}</span>
                          </div>
                          <div className="prose prose-invert max-w-none text-sm leading-7 text-slate-300" dangerouslySetInnerHTML={markdownBlock(message.content || (message.role === "assistant" ? "正在生成..." : ""))} />
                        </article>
                      )) : <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-4 text-sm text-slate-500">从这里开始新的投研对话，系统会保留上下文并实时流式输出。</div>}
                    </div>
                    <div className="mt-4 grid gap-3">
                      <textarea
                        value={props.draft}
                        onChange={(event) => props.onDraftChange(event.target.value)}
                        className="min-h-[120px] w-full rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
                        placeholder="例如：围绕当前关注标的，给我一份偏专业风格的买卖观察和风险提示。"
                      />
                      <div className="flex justify-end gap-2">
                        <button type="button" onClick={props.onAbortStream} disabled={!props.streaming} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-sm text-slate-200 hover:bg-white/8 disabled:opacity-50">停止</button>
                        <button type="button" onClick={() => props.onSubmitMessage()} disabled={props.streaming} className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200 hover:bg-emerald-400/14 disabled:opacity-50">{props.streaming ? "分析中..." : "发送分析"}</button>
                      </div>
                    </div>
                  </section>
                </div>

                <aside className="space-y-5">
                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Control Center</p>
                    <h3 className="mt-2 text-lg font-semibold text-slate-50">分析设置</h3>
                    <div className="mt-4 space-y-3">
                      <label className="block">
                        <span className="mb-1.5 block text-[11px] uppercase tracking-[0.18em] text-slate-500">模型选择</span>
                        <select value={props.modelProvider} onChange={(event) => props.onModelProviderChange(event.target.value)} className="w-full rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 outline-none">
                          {(props.models.length ? props.models : [{ id: "deepseek", label: "DeepSeek" }]).map((item) => (
                            <option key={item.id} value={item.id}>{item.label}</option>
                          ))}
                        </select>
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-[11px] uppercase tracking-[0.18em] text-slate-500">分析模式</span>
                        <select value={props.analysisMode} onChange={(event) => props.onAnalysisModeChange(event.target.value as AnalysisMode)} className="w-full rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 outline-none">
                          <option value="professional">Professional</option>
                          <option value="summary">Summary</option>
                          <option value="teaching">Teaching</option>
                        </select>
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-[11px] uppercase tracking-[0.18em] text-slate-500">数据源</span>
                        <select value={props.deskSource} onChange={(event) => props.onDeskSourceChange(event.target.value as DeskSource)} className="w-full rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 outline-none">
                          <option value="hybrid">Hybrid</option>
                          <option value="market">Market</option>
                          <option value="knowledge">Knowledge</option>
                        </select>
                      </label>
                    </div>
                  </section>

                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Breadth</p>
                    <h3 className="mt-2 text-lg font-semibold text-slate-50">市场宽度</h3>
                    <div className="mt-4 grid gap-2">
                      {(props.dashboard?.top_gainers || []).slice(0, 5).map((item, index) => (
                        <button key={`${String(item.symbol || item.name || index)}`} type="button" onClick={() => props.onQueryStock(String(item.symbol || item.name || ""))} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-left hover:bg-white/[0.05]">
                          <span className="text-sm text-slate-200">{String(item.name || item.symbol || "--")}</span>
                          <strong className={`text-sm ${toneClass(Number(item.change_percent ?? item.daily_change ?? 0))}`}>{pct(Number(item.change_percent ?? item.daily_change ?? 0))}</strong>
                        </button>
                      ))}
                    </div>
                  </section>

                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Session History</p>
                        <h3 className="mt-2 text-lg font-semibold text-slate-50">相关会话</h3>
                      </div>
                      <button type="button" onClick={() => setSessionOpen(true)} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">查看全部</button>
                    </div>
                    <div className="mt-4 space-y-2">
                      {props.conversations.slice(0, 4).map((item) => (
                        <button key={item.conversation_id} type="button" onClick={() => props.onOpenSession(item.conversation_id)} className={`w-full rounded-2xl border px-4 py-3 text-left ${item.conversation_id === props.activeConversationId ? "border-emerald-400/24 bg-emerald-400/[0.06]" : "border-white/8 bg-white/[0.02]"}`}>
                          <p className="text-sm font-medium text-slate-100">{item.title || "未命名会话"}</p>
                          <p className="mt-1 text-xs leading-6 text-slate-500">{item.last_message_preview || "暂无消息"}</p>
                        </button>
                      ))}
                    </div>
                  </section>
                </aside>
              </section>
            </div>
          </main>

          <aside className="border-l border-white/8 bg-[#0c1118]/95 px-4 py-5">
            <div className="space-y-5">
              <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">User</p>
                    <h3 className="mt-2 text-lg font-semibold text-slate-50">{props.userDisplayName}</h3>
                  </div>
                  <button type="button" onClick={props.onToggleVoice} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">{props.avatarVoiceEnabled ? "Voice On" : "Voice Off"}</button>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-400">{props.memorySummary}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {props.memoryTags.length ? props.memoryTags.map((tag) => (
                    <span key={tag} className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">{tag}</span>
                  )) : <span className="text-sm text-slate-500">暂无记忆标签</span>}
                </div>
              </section>

              <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">System Status</p>
                    <h3 className="mt-2 text-lg font-semibold text-slate-50">系统健康</h3>
                  </div>
                  <span className="rounded-full border border-white/8 px-3 py-1 text-xs text-slate-300">{props.okProviders}/{props.health?.providers?.length || 0}</span>
                </div>
                <div className="mt-4 grid gap-3">
                  {(props.health?.providers || []).length ? props.health?.providers.map((item) => (
                    <div key={item.provider} className={`rounded-2xl border px-4 py-3 ${item.ok ? "border-emerald-400/18 bg-emerald-400/[0.05]" : "border-rose-400/18 bg-rose-400/[0.05]"}`}>
                      <div className="flex items-center justify-between gap-3">
                        <strong className="text-sm text-slate-100">{item.provider}</strong>
                        <span className="text-xs text-slate-400">{item.ok ? "OK" : "WARN"}</span>
                      </div>
                      <p className="mt-2 text-xs text-slate-500">Latency {item.latency_ms ?? "--"} ms</p>
                      {item.error ? <p className="mt-2 text-xs text-rose-200">{item.error}</p> : null}
                    </div>
                  )) : <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-4 text-sm text-slate-500">暂无 provider 健康数据。</div>}
                </div>
                <button type="button" onClick={props.onRefreshCoreData} className="mt-4 w-full rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-sm text-slate-200 hover:bg-white/8">刷新系统</button>
              </section>

              <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Execution Trace</p>
                <h3 className="mt-2 text-lg font-semibold text-slate-50">执行轨迹</h3>
                <div className="mt-4 space-y-2">
                  {props.statusItems.map((item, index) => (
                    <div key={`${item}-${index}`} className="flex items-start gap-3 rounded-2xl border border-white/6 bg-white/[0.02] px-4 py-3 text-sm text-slate-300">
                      <span className="mt-2 h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </aside>
        </div>
      </div>

      <SessionDrawer
        open={sessionOpen}
        sessions={props.conversations}
        activeConversationId={props.activeConversationId}
        onClose={() => setSessionOpen(false)}
        onOpenSession={(conversationId) => {
          setSessionOpen(false);
          props.onOpenSession(conversationId);
        }}
      />
    </>
  );
}
