import type { ChunkDetail } from "../../types";

interface ChunkListProps {
  chunks: ChunkDetail[];
  selectedChunkId: string;
  onSelectChunk: (chunkId: string) => void;
  onAsk: (prompt: string) => void;
}

export function ChunkList(props: ChunkListProps) {
  if (!props.chunks.length) {
    return <div className="rounded-2xl border border-dashed border-white/12 bg-[#101720]/70 p-6 text-sm text-slate-400">暂无可检索分块。</div>;
  }

  return (
    <div className="space-y-3">
      {props.chunks.map((chunk) => {
        const active = chunk.chunk_id === props.selectedChunkId;
        return (
          <article
            key={chunk.chunk_id}
            className={`rounded-2xl border p-4 transition ${
              active ? "border-emerald-400/24 bg-emerald-400/[0.06]" : "border-white/8 bg-[#101720]/88"
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{chunk.section_title || "未分类章节"}</p>
                <h3 className="mt-1 text-sm font-semibold text-slate-100">{chunk.chunk_title}</h3>
              </div>
              <div className="flex gap-2">
                <span className="rounded-full border border-white/8 px-3 py-1 text-xs text-slate-400">
                  P.{chunk.page_start ?? "-"}{chunk.page_end && chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""}
                </span>
                <span className="rounded-full border border-white/8 px-3 py-1 text-xs text-slate-400">{chunk.word_count} tokens</span>
              </div>
            </div>

            <p className="mt-3 text-sm leading-7 text-slate-400">{chunk.preview || "暂无摘要。"}</p>
            {active ? <pre className="mt-4 max-h-72 overflow-auto rounded-2xl bg-black/20 p-4 text-sm leading-7 text-slate-300">{chunk.text}</pre> : null}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => props.onSelectChunk(chunk.chunk_id)}
                className="rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-xs text-slate-200 hover:bg-white/8"
              >
                {active ? "已展开" : "展开原文"}
              </button>
              <button
                type="button"
                onClick={() => props.onAsk(`基于分块“${chunk.chunk_title}”，提炼可执行结论与主要风险。`)}
                className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-200 hover:bg-emerald-400/14"
              >
                用于问答
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
