import type { DocumentDetail } from "../../types";
import { ChunkList } from "./ChunkList";
import { StructurePanel } from "./StructurePanel";
import { SummaryPanel } from "./SummaryPanel";

export type LibraryTabKey = "summary" | "structure" | "chunks" | "pages" | "qa";

interface DocumentTabsProps {
  activeTab: LibraryTabKey;
  document: DocumentDetail | null;
  loading: boolean;
  selectedChunkId: string;
  selectedPageNumber: number;
  onChangeTab: (tab: LibraryTabKey) => void;
  onSelectChunk: (chunkId: string) => void;
  onSelectPage: (pageNumber: number) => void;
  onAsk: (prompt: string) => void;
}

const TAB_ITEMS: Array<{ key: LibraryTabKey; label: string }> = [
  { key: "summary", label: "文档摘要" },
  { key: "structure", label: "章节结构" },
  { key: "chunks", label: "分块内容" },
  { key: "pages", label: "页面预览" },
  { key: "qa", label: "知识问答" },
];

export function DocumentTabs(props: DocumentTabsProps) {
  const activePage = props.document?.pages.find((item) => item.page_number === props.selectedPageNumber) || props.document?.pages[0] || null;

  return (
    <section className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-5">
      <div className="flex flex-wrap gap-2 border-b border-white/8 pb-4">
        {TAB_ITEMS.map((item) => {
          const active = item.key === props.activeTab;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => props.onChangeTab(item.key)}
              className={`rounded-xl px-4 py-2.5 text-sm transition ${
                active
                  ? "bg-slate-100 text-slate-950"
                  : "border border-white/8 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="mt-5">
        {props.activeTab === "summary" ? (
          <SummaryPanel document={props.document} job={null} loading={props.loading} onJumpToChunks={() => props.onChangeTab("chunks")} onAsk={props.onAsk} />
        ) : null}

        {props.activeTab === "structure" ? <StructurePanel document={props.document} /> : null}

        {props.activeTab === "chunks" ? (
          <ChunkList
            chunks={props.document?.chunks || []}
            selectedChunkId={props.selectedChunkId}
            onSelectChunk={props.onSelectChunk}
            onAsk={props.onAsk}
          />
        ) : null}

        {props.activeTab === "pages" ? (
          <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
            <div className="space-y-2">
              {(props.document?.pages || []).map((page) => {
                const active = page.page_number === activePage?.page_number;
                return (
                  <button
                    key={page.page_number}
                    type="button"
                    onClick={() => props.onSelectPage(page.page_number)}
                    className={`w-full rounded-2xl border px-4 py-3 text-left ${
                      active ? "border-emerald-400/20 bg-emerald-400/[0.06]" : "border-white/8 bg-white/[0.02]"
                    }`}
                  >
                    <p className="text-sm font-medium text-slate-100">第 {page.page_number} 页</p>
                    <p className="mt-1 text-xs leading-6 text-slate-500">{page.preview || "暂无页面摘要"}</p>
                  </button>
                );
              })}
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
              {activePage ? (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-slate-100">页面预览</h3>
                    <span className="rounded-full border border-white/8 px-3 py-1 text-xs text-slate-400">
                      命中 {activePage.chunks.length} 个分块
                    </span>
                  </div>
                  <pre className="mt-4 max-h-[30rem] overflow-auto whitespace-pre-wrap rounded-2xl bg-black/20 p-4 text-sm leading-7 text-slate-300">
                    {activePage.text}
                  </pre>
                </>
              ) : (
                <div className="text-sm text-slate-400">当前资料没有分页结果。</div>
              )}
            </div>
          </div>
        ) : null}

        {props.activeTab === "qa" ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
              <h3 className="text-base font-semibold text-slate-100">基于知识库发起问答</h3>
              <p className="mt-2 text-sm leading-7 text-slate-400">当前问答将优先围绕所选资料的摘要、章节和分块内容组织回答。</p>
              <div className="mt-5 flex flex-wrap gap-2">
                {[
                  "总结核心投资结论",
                  "列出最重要的风险提示",
                  "生成适合投研晨会的三点提纲",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => props.onAsk(prompt)}
                    className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm text-slate-300 hover:border-emerald-400/30 hover:bg-emerald-400/[0.06]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
              <h3 className="text-base font-semibold text-slate-100">当前上下文</h3>
              <div className="mt-4 space-y-3 text-sm text-slate-400">
                <p>已选资料：{props.document?.title || "未选择"}</p>
                <p>已提取章节：{props.document?.section_count || 0}</p>
                <p>已建索引分块：{props.document?.chunk_count || 0}</p>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
