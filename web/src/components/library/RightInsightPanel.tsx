import { useState } from "react";

import { formatTimeLabel } from "../../lib/format";
import type { ConversationSummary, DocumentDetail, SearchResultItem } from "../../types";

type InsightTab = "tags" | "questions" | "related" | "hits";

interface RightInsightPanelProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  document: DocumentDetail | null;
  sessions: ConversationSummary[];
  hits: SearchResultItem[];
  onOpenSessions: () => void;
  onAsk: (prompt: string) => void;
}

export function RightInsightPanel(props: RightInsightPanelProps) {
  const [tab, setTab] = useState<InsightTab>("tags");

  if (props.collapsed) {
    return (
      <aside className="flex h-full flex-col items-center gap-4 border-l border-white/8 bg-[#0c1118]/95 px-3 py-5">
        <button
          type="button"
          onClick={props.onToggleCollapsed}
          className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8"
        >
          展开辅助区
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex h-full flex-col border-l border-white/8 bg-[#0c1118]/95 px-4 py-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Insight Panel</p>
          <h2 className="mt-1 text-sm font-semibold text-slate-100">辅助信息</h2>
        </div>
        <button
          type="button"
          onClick={props.onToggleCollapsed}
          className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8"
        >
          折叠
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {[
          ["tags", "主题标签"],
          ["questions", "问答建议"],
          ["related", "相关会话"],
          ["hits", "检索命中"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key as InsightTab)}
            className={`rounded-xl px-3 py-2 text-xs ${
              tab === key ? "bg-slate-100 text-slate-950" : "border border-white/8 bg-white/[0.03] text-slate-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-4 flex-1 overflow-auto pr-1">
        {tab === "tags" ? (
          <div className="space-y-4">
            <section className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">关键词</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {(props.document?.keywords || []).length ? (
                  props.document?.keywords.map((keyword) => (
                    <span key={keyword} className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">
                      {keyword}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-slate-500">暂无结构提取结果</span>
                )}
              </div>
            </section>
            <section className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">提取主题</p>
              <div className="mt-3 space-y-2">
                {(props.document?.sections || []).slice(0, 4).map((section) => (
                  <div key={section.section_id} className="rounded-xl border border-white/6 bg-black/10 px-3 py-3">
                    <p className="text-sm font-medium text-slate-100">{section.title}</p>
                    <p className="mt-1 text-xs leading-6 text-slate-500">{section.summary}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        ) : null}

        {tab === "questions" ? (
          <div className="space-y-2">
            {[
              "本资料支持什么配置判断？",
              "如果风险偏好下降，哪些结论需要下调？",
              "从全文抽出适合路演复述的三句话。",
            ].map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => props.onAsk(prompt)}
                className="w-full rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-left text-sm text-slate-300 hover:border-emerald-400/30 hover:bg-emerald-400/[0.06]"
              >
                {prompt}
              </button>
            ))}
          </div>
        ) : null}

        {tab === "related" ? (
          <div className="space-y-3">
            {props.sessions.slice(0, 6).map((item) => (
              <button
                key={item.conversation_id}
                type="button"
                onClick={props.onOpenSessions}
                className="w-full rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-left hover:bg-white/[0.05]"
              >
                <p className="text-sm font-medium text-slate-100">{item.title}</p>
                <p className="mt-1 text-xs leading-6 text-slate-500">{item.last_message_preview}</p>
                <p className="mt-2 text-[11px] uppercase tracking-[0.16em] text-slate-600">{formatTimeLabel(item.updated_at)}</p>
              </button>
            ))}
          </div>
        ) : null}

        {tab === "hits" ? (
          <div className="space-y-3">
            {props.hits.map((item) => (
              <article key={item.chunk_id} className="rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-medium text-slate-100">{item.chunk_title}</h3>
                  <span className="text-xs text-emerald-300">{Math.round(item.score * 100)} 分</span>
                </div>
                <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-500">{item.section_title}</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">{item.text}</p>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </aside>
  );
}
