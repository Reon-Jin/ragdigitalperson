import type { DocumentDetail, IngestionJob } from "../../types";

interface SummaryPanelProps {
  document: DocumentDetail | null;
  job: IngestionJob | null;
  onJumpToChunks: () => void;
  onAsk: (prompt: string) => void;
  loading?: boolean;
}

export function SummaryPanel(props: SummaryPanelProps) {
  if (props.loading) {
    return <div className="rounded-2xl border border-white/8 bg-[#101720]/88 p-6 text-sm text-slate-400">正在加载资料工作台...</div>;
  }

  if (!props.document) {
    return (
      <div className="rounded-2xl border border-dashed border-white/12 bg-[#101720]/70 p-8">
        <p className="text-sm font-medium text-slate-200">尚未选择资料</p>
        <p className="mt-2 max-w-xl text-sm leading-7 text-slate-400">从左侧列表选择一份资料后，这里会展示主摘要、关键判断与下一步分析入口。</p>
      </div>
    );
  }

  if (props.job && ["queued", "running"].includes(props.job.status)) {
    return (
      <div className="rounded-2xl border border-sky-400/16 bg-sky-400/[0.06] p-6">
        <p className="text-sm font-medium text-sky-100">{props.job.stage}</p>
        <p className="mt-2 text-sm leading-7 text-slate-300">{props.job.message || "后台处理中，完成后将局部刷新摘要与结构视图。"}</p>
        <div className="mt-4 h-2 rounded-full bg-white/6">
          <div className="h-2 rounded-full bg-sky-300" style={{ width: `${Math.max(8, Math.round(props.job.progress * 100))}%` }} />
        </div>
      </div>
    );
  }

  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
      <article className="rounded-2xl border border-white/8 bg-[#101720]/88 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Executive Summary</p>
            <h3 className="mt-2 text-lg font-semibold text-slate-50">文档摘要</h3>
          </div>
          <button
            type="button"
            onClick={props.onJumpToChunks}
            className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8"
          >
            深入分块
          </button>
        </div>
        <p className="mt-4 text-sm leading-7 text-slate-300">{props.document.summary || "尚未生成摘要。"}</p>

        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {props.document.sections.slice(0, 4).map((section) => (
            <div key={section.section_id} className="rounded-2xl border border-white/6 bg-white/[0.02] p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Section</p>
              <h4 className="mt-2 text-sm font-medium text-slate-100">{section.title}</h4>
              <p className="mt-2 text-sm leading-6 text-slate-400">{section.summary || "暂无节摘要。"}</p>
            </div>
          ))}
        </div>
      </article>

      <article className="rounded-2xl border border-white/8 bg-[#101720]/88 p-6">
        <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Guided Actions</p>
        <h3 className="mt-2 text-lg font-semibold text-slate-50">下一步分析</h3>
        <div className="mt-4 space-y-3">
          {[
            "总结本报告最适合跟踪的配置主线",
            "提炼红利资产的筛选标准与排除项",
            "从科技链章节中列出三项关键验证指标",
          ].map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => props.onAsk(prompt)}
              className="flex w-full items-start rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-left text-sm text-slate-300 hover:border-emerald-400/30 hover:bg-emerald-400/[0.06]"
            >
              {prompt}
            </button>
          ))}
        </div>
      </article>
    </section>
  );
}
