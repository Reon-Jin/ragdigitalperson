import { formatTimeLabel } from "../../lib/format";
import type { ConversationSummary } from "../../types";

interface SessionDrawerProps {
  open: boolean;
  sessions: ConversationSummary[];
  activeConversationId: string;
  onClose: () => void;
  onOpenSession: (conversationId: string) => void;
}

export function SessionDrawer(props: SessionDrawerProps) {
  if (!props.open) return null;

  return (
    <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm">
      <div className="absolute inset-y-0 right-0 w-full max-w-md border-l border-white/10 bg-[#0b1016] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Session History</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-50">历史会话</h2>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8"
          >
            关闭
          </button>
        </div>

        <div className="mt-5 space-y-3 overflow-auto pr-1">
          {props.sessions.length ? (
            props.sessions.map((item) => {
              const active = item.conversation_id === props.activeConversationId;
              return (
                <button
                  key={item.conversation_id}
                  type="button"
                  onClick={() => props.onOpenSession(item.conversation_id)}
                  className={`w-full rounded-2xl border px-4 py-3 text-left ${
                    active ? "border-emerald-400/24 bg-emerald-400/[0.06]" : "border-white/8 bg-white/[0.02]"
                  }`}
                >
                  <p className="text-sm font-medium text-slate-100">{item.title || "未命名会话"}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{item.last_message_preview || "暂无消息"}</p>
                  <div className="mt-3 flex items-center justify-between text-[11px] uppercase tracking-[0.16em] text-slate-600">
                    <span>{item.message_count} 条消息</span>
                    <span>{formatTimeLabel(item.updated_at)}</span>
                  </div>
                </button>
              );
            })
          ) : (
            <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-5 text-sm text-slate-400">暂无历史问答。</div>
          )}
        </div>
      </div>
    </div>
  );
}
