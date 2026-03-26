interface TopHeaderProps {
  title: string;
  filename: string;
  suffix: string;
  uploadedAt: string;
  statusLabel: string;
  statusTone: "success" | "processing" | "error" | "neutral";
  onRefresh: () => void;
  onDelete: () => void;
  onExportSummary: () => void;
  disableDelete?: boolean;
  demo?: boolean;
}

const STEP_ITEMS = ["上传资料", "解析入库", "查看摘要", "深入分块", "问答分析"];

function statusClass(tone: TopHeaderProps["statusTone"]) {
  if (tone === "success") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  if (tone === "processing") return "border-sky-400/20 bg-sky-400/10 text-sky-200";
  if (tone === "error") return "border-rose-400/20 bg-rose-400/10 text-rose-200";
  return "border-white/10 bg-white/5 text-slate-300";
}

export function TopHeader(props: TopHeaderProps) {
  return (
    <header className="rounded-[24px] border border-white/8 bg-[#101720]/88 p-6 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
      <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/8 bg-white/4 px-3 py-1 text-[11px] uppercase tracking-[0.22em] text-slate-500">
              Knowledge Base / Document Desk
            </span>
            {props.demo ? (
              <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-amber-200">
                Demo Data
              </span>
            ) : null}
          </div>
          <div>
            <h2 className="text-[28px] font-semibold tracking-[0.02em] text-slate-50">{props.title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-slate-400">
              <span>{props.filename}</span>
              <span className="text-slate-600">/</span>
              <span>{props.suffix.replace(".", "").toUpperCase()}</span>
              <span className="text-slate-600">/</span>
              <span>上传于 {props.uploadedAt}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col items-start gap-3 xl:items-end">
          <span className={`rounded-full border px-3 py-1.5 text-xs ${statusClass(props.statusTone)}`}>{props.statusLabel}</span>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={props.onRefresh}
              className="rounded-xl border border-white/10 bg-white/4 px-4 py-2 text-sm text-slate-200 hover:bg-white/8"
            >
              重新解析
            </button>
            <button
              type="button"
              onClick={props.onExportSummary}
              className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200 hover:bg-emerald-400/14"
            >
              导出摘要
            </button>
            <button
              type="button"
              onClick={props.onDelete}
              disabled={props.disableDelete}
              className="rounded-xl border border-rose-400/18 bg-rose-400/8 px-4 py-2 text-sm text-rose-200 hover:bg-rose-400/12 disabled:cursor-not-allowed disabled:opacity-50"
            >
              删除资料
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-3 rounded-2xl border border-white/6 bg-black/10 px-4 py-4 lg:grid-cols-5">
        {STEP_ITEMS.map((item, index) => {
          const active = index <= 2;
          return (
            <div
              key={item}
              className={`rounded-2xl border px-4 py-3 ${
                active ? "border-emerald-400/18 bg-emerald-400/[0.07]" : "border-white/6 bg-white/[0.02]"
              }`}
            >
              <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Step {index + 1}</p>
              <p className={`mt-2 text-sm font-medium ${active ? "text-slate-100" : "text-slate-400"}`}>{item}</p>
            </div>
          );
        })}
      </div>
    </header>
  );
}
