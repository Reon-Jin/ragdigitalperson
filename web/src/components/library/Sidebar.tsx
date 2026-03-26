import type { UserProfile } from "../../types";
import { UploadPanel } from "./UploadPanel";

const NAV_ITEMS = [
  { key: "overview", label: "总览 / 工作台" },
  { key: "library", label: "知识库" },
  { key: "analysis", label: "对话分析" },
  { key: "market", label: "市场观察" },
  { key: "history", label: "会话历史" },
  { key: "settings", label: "设置" },
];

interface SidebarProps {
  profile: UserProfile;
  activeKey: string;
  onSaveProfile: () => void;
  onBackToDesk: () => void;
  onOpenSessions: () => void;
  onLogout: () => void;
  onProfileChange: (patch: Partial<UserProfile>) => void;
  onUploadFiles: (files: FileList | File[]) => void;
  uploading: boolean;
  queuedCount: number;
}

export function Sidebar(props: SidebarProps) {
  return (
    <aside className="flex h-full flex-col border-r border-white/8 bg-[#0b1016]/95 px-4 py-5 backdrop-blur">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-400/20 bg-emerald-400/10 text-sm font-semibold text-slate-100">
          FA
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Financial Research OS</p>
          <h1 className="text-base font-semibold tracking-[0.04em] text-slate-100">FinAvatar Insight</h1>
        </div>
      </div>

      <nav className="space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = props.activeKey === item.key;
          const handler = item.key === "overview" ? props.onBackToDesk : item.key === "history" ? props.onOpenSessions : undefined;
          return (
            <button
              key={item.key}
              type="button"
              onClick={handler}
              className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition ${
                active
                  ? "bg-slate-800 text-slate-50 ring-1 ring-emerald-400/25"
                  : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
              }`}
            >
              <span>{item.label}</span>
              {active ? <span className="h-2 w-2 rounded-full bg-emerald-400" /> : null}
            </button>
          );
        })}
      </nav>

      <div className="mt-6 rounded-2xl border border-white/6 bg-slate-950/50 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Investor Lens</p>
            <h2 className="text-sm font-semibold text-slate-100">投资偏好</h2>
          </div>
          <button
            type="button"
            onClick={props.onSaveProfile}
            className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 hover:border-emerald-400/30 hover:bg-emerald-400/10"
          >
            保存
          </button>
        </div>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1.5 block text-[11px] uppercase tracking-[0.18em] text-slate-500">风险偏好</span>
            <select
              value={props.profile.risk_level}
              onChange={(event) => props.onProfileChange({ risk_level: event.target.value as UserProfile["risk_level"] })}
              className="w-full rounded-xl border border-white/8 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none"
            >
              <option value="low">低风险</option>
              <option value="medium">中风险</option>
              <option value="high">高风险</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[11px] uppercase tracking-[0.18em] text-slate-500">投资期限</span>
            <select
              value={props.profile.investment_horizon}
              onChange={(event) =>
                props.onProfileChange({ investment_horizon: event.target.value as UserProfile["investment_horizon"] })
              }
              className="w-full rounded-xl border border-white/8 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none"
            >
              <option value="short">短期</option>
              <option value="medium">中期</option>
              <option value="long">长期</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[11px] uppercase tracking-[0.18em] text-slate-500">关注市场</span>
            <input
              value={props.profile.markets.join(" / ")}
              onChange={(event) =>
                props.onProfileChange({ markets: event.target.value.split(/[、,/]/).map((item) => item.trim()).filter(Boolean) })
              }
              className="w-full rounded-xl border border-white/8 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600"
              placeholder="A-share / HK / US"
            />
          </label>
        </div>
      </div>

      <div className="mt-6">
        <UploadPanel uploading={props.uploading} queuedCount={props.queuedCount} onUploadFiles={props.onUploadFiles} />
      </div>

      <div className="mt-auto flex gap-2 pt-6">
        <button
          type="button"
          onClick={props.onBackToDesk}
          className="flex-1 rounded-xl border border-white/10 bg-white/4 px-3 py-2.5 text-sm text-slate-200 hover:bg-white/8"
        >
          返回工作台
        </button>
        <button
          type="button"
          onClick={props.onLogout}
          className="rounded-xl border border-rose-400/20 bg-rose-400/8 px-3 py-2.5 text-sm text-rose-200 hover:bg-rose-400/12"
        >
          退出
        </button>
      </div>
    </aside>
  );
}
