import { useState } from "react";

import { formatTimeLabel } from "../lib/format";
import { renderMarkdown } from "../lib/markdown";
import type {
  AnalysisMode,
  ConversationMessage,
  ConversationSummary,
  DeskSource,
  HealthPayload,
  ModelItem,
  UserProfile,
} from "../types";
import { SessionDrawer } from "./library/SessionDrawer";
import { Sidebar } from "./library/Sidebar";

interface AnalysisWorkspaceProps {
  profile: UserProfile;
  models: ModelItem[];
  modelProvider: string;
  analysisMode: AnalysisMode;
  deskSource: DeskSource;
  controlHint: string;
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
  onGoAnalysis: () => void;
  onGoDesk: () => void;
  onOpenSession: (conversationId: string) => void;
  onRefreshCoreData: () => void;
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

export function AnalysisWorkspace(props: AnalysisWorkspaceProps) {
  const [sessionOpen, setSessionOpen] = useState(false);

  return (
    <>
      <div className="min-h-screen bg-[#071017] text-slate-100">
        <div className="grid min-h-screen grid-cols-[248px_minmax(0,1fr)_320px]">
          <Sidebar
            profile={props.profile}
            activeKey="analysis"
            onSaveProfile={props.onSaveProfile}
            onBackToDesk={props.onGoDesk}
            onGoLibrary={props.onGoLibrary}
            onGoAnalysis={props.onGoAnalysis}
            onOpenSessions={() => setSessionOpen(true)}
            onLogout={props.onLogout}
            onProfileChange={props.onProfileChange}
            onUploadFiles={props.onUploadFiles}
            uploading={props.streaming}
            queuedCount={props.uploadQueuedCount}
          />

          <main className="min-w-0 bg-[radial-gradient(circle_at_top,_rgba(33,55,75,0.24),_transparent_42%)] px-6 py-6 2xl:px-8">
            <div className="mx-auto flex max-w-[1380px] flex-col gap-5">
              <header className="rounded-[24px] border border-white/8 bg-[#101720]/88 p-6 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Dialogue Analysis</p>
                    <h2 className="mt-3 text-[28px] font-semibold tracking-[0.02em] text-slate-50">{props.conversationTitle}</h2>
                    <p className="mt-3 text-sm leading-6 text-slate-400">使用当前模型、分析模式和数据源进行连续对话分析。这里承接所有会话、流式回答和上下文记忆。</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={props.onCreateConversation} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">新会话</button>
                    <button type="button" onClick={props.onRemoveConversation} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">删除</button>
                  </div>
                </div>
              </header>

              <section className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
                <div className="space-y-5">
                  <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
                    <div className="flex flex-wrap gap-2">
                      {props.quickPrompts.map((prompt) => (
                        <button key={prompt} type="button" onClick={() => props.onSubmitMessage(prompt)} className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-slate-300 hover:border-emerald-400/30 hover:bg-emerald-400/[0.06]">
                          {prompt}
                        </button>
                      ))}
                    </div>
                    <div className="mt-4 max-h-[560px] space-y-3 overflow-auto pr-1">
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
                        className="min-h-[140px] w-full rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
                        placeholder="例如：围绕我当前关注的标的，给我一份更偏专业风格的买卖观察和风险提示。"
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
                    <p className="mt-2 text-sm leading-6 text-slate-500">{props.controlHint}</p>
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
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Session History</p>
                        <h3 className="mt-2 text-lg font-semibold text-slate-50">相关会话</h3>
                      </div>
                      <button type="button" onClick={() => setSessionOpen(true)} className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8">查看全部</button>
                    </div>
                    <div className="mt-4 space-y-2">
                      {props.conversations.slice(0, 6).map((item) => (
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
