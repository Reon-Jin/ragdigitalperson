import { useState } from "react";

import type { DocumentDetail } from "../../types";

interface StructurePanelProps {
  document: DocumentDetail | null;
}

export function StructurePanel(props: StructurePanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (!props.document) {
    return <div className="rounded-2xl border border-dashed border-white/12 bg-[#101720]/70 p-6 text-sm text-slate-400">暂无结构提取结果。</div>;
  }

  return (
    <section className="space-y-3">
      {props.document.sections.map((section) => {
        const open = expanded[section.section_id] ?? section.order <= 2;
        return (
          <article key={section.section_id} className="rounded-2xl border border-white/8 bg-[#101720]/88">
            <button
              type="button"
              onClick={() => setExpanded((current) => ({ ...current, [section.section_id]: !open }))}
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
            >
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Theme {section.order}</p>
                <h3 className="mt-1 text-sm font-semibold text-slate-100">{section.title}</h3>
              </div>
              <div className="text-right">
                <p className="text-sm text-slate-300">{section.chunk_count} 个分析块</p>
                <p className="text-xs text-slate-500">{open ? "收起" : "展开"}</p>
              </div>
            </button>

            {open ? (
              <div className="border-t border-white/6 px-5 py-4">
                <p className="text-sm leading-7 text-slate-400">{section.summary || "暂无摘要句。"}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {section.previews.slice(0, 4).map((item) => (
                    <span key={item.chunk_id} className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300">
                      {item.chunk_title}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
