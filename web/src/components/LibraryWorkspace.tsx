import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { formatTimeLabel } from "../lib/format";
import type { DocumentDetail, LibraryFileItem, PageDetail } from "../types";

type LibraryTab = "preview" | "chunks" | "pages";

function formatPageRange(start?: number | null, end?: number | null): string {
  if (start == null && end == null) return "未定位页码";
  if ((start ?? null) === (end ?? null)) return `P.${start}`;
  return `P.${start ?? "?"}-${end ?? "?"}`;
}

function suffixLabel(suffix: string): string {
  const cleaned = String(suffix || "").replace(/^\./, "").trim();
  return cleaned ? cleaned.toUpperCase() : "FILE";
}

function excerpt(text: string, limit = 1600): string {
  const cleaned = String(text || "").trim();
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, limit).trimEnd()}...`;
}

function previewExcerpt(document: DocumentDetail): string {
  const pageText = document.pages.find((item) => item.text.trim())?.text || "";
  if (pageText.trim()) return excerpt(pageText);
  const chunkText = document.chunks.find((item) => item.text.trim())?.text || "";
  if (chunkText.trim()) return excerpt(chunkText);
  return document.summary || "暂无可预览文本。";
}

function PageViewer({ page }: { page: PageDetail | null }) {
  if (!page) {
    return <div className="empty-state">当前资料没有可分页预览的内容。</div>;
  }
  return (
    <div className="library-active-view">
      <div className="card-topline">
        <strong>第 {page.page_number} 页</strong>
        <span className="status-pill status-neutral">{page.chunks.length} 个分块命中</span>
      </div>
      <p className="muted-copy">{page.preview || "暂无页摘要。"}</p>
      <pre className="library-text-preview">{page.text || "当前页暂无可提取文本。"}</pre>
      <div className="library-chip-stack">
        {page.chunks.length ? (
          page.chunks.map((chunk) => (
            <span className="status-pill status-neutral" key={chunk.chunk_id}>
              {chunk.chunk_title} · {formatPageRange(chunk.page_start, chunk.page_end)}
            </span>
          ))
        ) : (
          <span className="status-pill status-neutral">这一页未匹配到分块。</span>
        )}
      </div>
    </div>
  );
}

export function LibraryWorkspace(props: {
  files: LibraryFileItem[];
  search: string;
  selectedDocumentId: string;
  selectedDocument: DocumentDetail | null;
  detailBusy: boolean;
  deletingDocId: string;
  onSearchChange: (value: string) => void;
  onSelectDocument: (docId: string) => void;
  onRefresh: () => void;
  onDeleteDocument: (docId: string) => void;
}) {
  const deferredSearch = useDeferredValue(props.search);
  const [activeTab, setActiveTab] = useState<LibraryTab>("preview");
  const [activeChunkId, setActiveChunkId] = useState("");
  const [activePageNumber, setActivePageNumber] = useState(1);

  const filteredFiles = useMemo(() => {
    const keyword = deferredSearch.trim().toLowerCase();
    if (!keyword) return props.files;
    return props.files.filter((item) => {
      const haystack = [item.title, item.filename, item.summary, item.category, ...(item.keywords || [])].join("\n").toLowerCase();
      return haystack.includes(keyword);
    });
  }, [deferredSearch, props.files]);

  useEffect(() => {
    const document = props.selectedDocument;
    if (!document) {
      setActiveChunkId("");
      setActivePageNumber(1);
      return;
    }
    setActiveChunkId((current) => {
      if (current && document.chunks.some((item) => item.chunk_id === current)) return current;
      return document.chunks[0]?.chunk_id || "";
    });
    setActivePageNumber((current) => {
      if (document.pages.some((item) => item.page_number === current)) return current;
      return document.pages[0]?.page_number || 1;
    });
  }, [props.selectedDocument]);

  const activeChunk = useMemo(() => {
    if (!props.selectedDocument) return null;
    return props.selectedDocument.chunks.find((item) => item.chunk_id === activeChunkId) || props.selectedDocument.chunks[0] || null;
  }, [activeChunkId, props.selectedDocument]);

  const activePage = useMemo(() => {
    if (!props.selectedDocument) return null;
    return props.selectedDocument.pages.find((item) => item.page_number === activePageNumber) || props.selectedDocument.pages[0] || null;
  }, [activePageNumber, props.selectedDocument]);

  return (
    <section className="panel library-panel">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Knowledge Base Manager</p>
          <h2>资料管理</h2>
          <p className="muted-copy">集中查看你的私有资料、预览正文、核对分块与清理无效文档。</p>
        </div>
        <div className="toolbar-row library-toolbar">
          <label className="field library-search-wrap">
            <span>搜索资料</span>
            <input value={props.search} onChange={(event) => props.onSearchChange(event.target.value)} placeholder="按标题、文件名、关键词搜索" />
          </label>
          <button className="button secondary" type="button" onClick={props.onRefresh}>
            刷新资料
          </button>
        </div>
      </div>

      <div className="library-layout">
        <div className="library-list-column">
          <div className="library-list-stack">
            {filteredFiles.length ? (
              filteredFiles.map((item) => {
                const active = item.doc_id === props.selectedDocumentId;
                return (
                  <button
                    className={`list-card selectable library-doc-card ${active ? "active" : ""}`}
                    key={item.doc_id}
                    type="button"
                    onClick={() => props.onSelectDocument(item.doc_id)}
                  >
                    <div className="card-topline">
                      <strong>{item.title || item.filename}</strong>
                      <span className="status-pill status-neutral">{suffixLabel(item.suffix)}</span>
                    </div>
                    <p className="muted-copy">{item.filename}</p>
                    <p>{item.summary || "暂无摘要。"}</p>
                    <div className="pill-row compact">
                      <span className="status-pill status-neutral">{item.section_count} 节</span>
                      <span className="status-pill status-neutral">{item.chunk_count} 块</span>
                      <span className="status-pill status-neutral">{formatTimeLabel(item.uploaded_at)}</span>
                    </div>
                    <div className="pill-row compact">
                      {(item.keywords || []).length ? (
                        item.keywords.slice(0, 3).map((keyword) => (
                          <span className="status-pill status-neutral" key={`${item.doc_id}-${keyword}`}>
                            {keyword}
                          </span>
                        ))
                      ) : (
                        <span className="status-pill status-neutral">{item.category}</span>
                      )}
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="empty-state">{props.files.length ? "没有匹配到资料。" : "还没有上传任何资料。"}</div>
            )}
          </div>
        </div>

        <div className="library-detail-column">
          {props.detailBusy ? (
            <div className="empty-state">正在加载资料详情...</div>
          ) : props.selectedDocument ? (
            <>
              <div className="subpanel library-detail-hero">
                <div className="panel-heading">
                  <div>
                    <p className="section-kicker">Document Detail</p>
                    <h3>{props.selectedDocument.title || props.selectedDocument.filename}</h3>
                    <p className="muted-copy">{props.selectedDocument.filename}</p>
                  </div>
                  <button
                    className="button ghost library-danger-button"
                    type="button"
                    onClick={() => props.onDeleteDocument(props.selectedDocument!.doc_id)}
                    disabled={props.deletingDocId === props.selectedDocument.doc_id}
                  >
                    {props.deletingDocId === props.selectedDocument.doc_id ? "删除中..." : "删除资料"}
                  </button>
                </div>
                <div className="library-stat-grid">
                  <div className="metric-tile mini">
                    <span>分类</span>
                    <strong>{props.selectedDocument.category}</strong>
                  </div>
                  <div className="metric-tile mini">
                    <span>分节</span>
                    <strong>{props.selectedDocument.section_count}</strong>
                  </div>
                  <div className="metric-tile mini">
                    <span>分块</span>
                    <strong>{props.selectedDocument.chunk_count}</strong>
                  </div>
                  <div className="metric-tile mini">
                    <span>分页</span>
                    <strong>{props.selectedDocument.pages.length}</strong>
                  </div>
                </div>
                <div className="pill-row compact">
                  <span className="status-pill status-neutral">{suffixLabel(props.selectedDocument.suffix)}</span>
                  <span className="status-pill status-neutral">上传于 {formatTimeLabel(props.selectedDocument.uploaded_at)}</span>
                </div>
              </div>

              <div className="tab-row library-tab-bar">
                <button className={`tab-button ${activeTab === "preview" ? "active" : ""}`} type="button" onClick={() => setActiveTab("preview")}>
                  正文预览
                </button>
                <button className={`tab-button ${activeTab === "chunks" ? "active" : ""}`} type="button" onClick={() => setActiveTab("chunks")}>
                  分块查看
                </button>
                <button className={`tab-button ${activeTab === "pages" ? "active" : ""}`} type="button" onClick={() => setActiveTab("pages")}>
                  页面预览
                </button>
              </div>

              {activeTab === "preview" ? (
                <div className="library-preview-grid">
                  <article className="subpanel library-active-view">
                    <div className="subpanel-head">
                      <h3>资料摘要</h3>
                      <span className="status-pill status-neutral">{props.selectedDocument.chunks.length} 个分块已建索引</span>
                    </div>
                    <p>{props.selectedDocument.summary || "暂无摘要。"}</p>
                    <pre className="library-text-preview">{previewExcerpt(props.selectedDocument)}</pre>
                  </article>

                  <article className="subpanel library-meta-panel">
                    <div className="subpanel-head">
                      <h3>结构概览</h3>
                    </div>
                    <div className="tag-row-block">
                      <strong>标题提取</strong>
                      <div className="library-chip-stack">
                        {props.selectedDocument.headings.length ? (
                          props.selectedDocument.headings.map((heading) => (
                            <span className="status-pill status-neutral" key={heading}>
                              {heading}
                            </span>
                          ))
                        ) : (
                          <span className="status-pill status-neutral">未提取到标题结构</span>
                        )}
                      </div>
                    </div>
                    <div className="tag-row-block">
                      <strong>关键词</strong>
                      <div className="library-chip-stack">
                        {props.selectedDocument.keywords.length ? (
                          props.selectedDocument.keywords.map((keyword) => (
                            <span className="status-pill status-neutral" key={keyword}>
                              {keyword}
                            </span>
                          ))
                        ) : (
                          <span className="status-pill status-neutral">暂无关键词</span>
                        )}
                      </div>
                    </div>
                  </article>

                  <article className="subpanel full-span">
                    <div className="subpanel-head">
                      <h3>分节摘要</h3>
                    </div>
                    <div className="library-section-list">
                      {props.selectedDocument.sections.length ? (
                        props.selectedDocument.sections.map((section) => (
                          <div className="list-card library-section-card" key={section.section_id}>
                            <div className="card-topline">
                              <strong>{section.title}</strong>
                              <span className="status-pill status-neutral">{section.chunk_count} 块</span>
                            </div>
                            <p>{section.summary || "暂无摘要。"}</p>
                            <div className="library-mini-list">
                              {section.previews.slice(0, 3).map((chunk) => (
                                <button className="prompt-chip" key={chunk.chunk_id} type="button" onClick={() => { setActiveTab("chunks"); setActiveChunkId(chunk.chunk_id); }}>
                                  {chunk.chunk_title}
                                </button>
                              ))}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="empty-state">还没有生成章节结构。</div>
                      )}
                    </div>
                  </article>
                </div>
              ) : null}

              {activeTab === "chunks" ? (
                <div className="library-explorer-grid">
                  <div className="subpanel library-nav-panel">
                    <div className="subpanel-head">
                      <h3>分块列表</h3>
                      <span className="status-pill status-neutral">{props.selectedDocument.chunks.length} 块</span>
                    </div>
                    <div className="library-nav-list">
                      {props.selectedDocument.chunks.map((chunk) => (
                        <button
                          className={`list-card selectable library-nav-card ${chunk.chunk_id === activeChunk?.chunk_id ? "active" : ""}`}
                          key={chunk.chunk_id}
                          type="button"
                          onClick={() => setActiveChunkId(chunk.chunk_id)}
                        >
                          <div className="card-topline">
                            <strong>{chunk.chunk_title}</strong>
                            <span className="status-pill status-neutral">{formatPageRange(chunk.page_start, chunk.page_end)}</span>
                          </div>
                          <p className="muted-copy">{chunk.section_title}</p>
                          <p>{chunk.preview || "暂无预览。"}</p>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="subpanel">
                    {activeChunk ? (
                      <div className="library-active-view">
                        <div className="card-topline">
                          <strong>{activeChunk.chunk_title}</strong>
                          <span className="status-pill status-neutral">{activeChunk.word_count} 词</span>
                        </div>
                        <div className="pill-row compact">
                          <span className="status-pill status-neutral">{activeChunk.section_title}</span>
                          <span className="status-pill status-neutral">{activeChunk.chunk_kind}</span>
                          <span className="status-pill status-neutral">{formatPageRange(activeChunk.page_start, activeChunk.page_end)}</span>
                        </div>
                        <p className="muted-copy">{activeChunk.preview || "暂无摘要。"}</p>
                        <pre className="library-text-preview">{activeChunk.text}</pre>
                      </div>
                    ) : (
                      <div className="empty-state">当前资料没有可查看的分块。</div>
                    )}
                  </div>
                </div>
              ) : null}

              {activeTab === "pages" ? (
                <div className="library-explorer-grid">
                  <div className="subpanel library-nav-panel">
                    <div className="subpanel-head">
                      <h3>页面列表</h3>
                      <span className="status-pill status-neutral">{props.selectedDocument.pages.length} 页</span>
                    </div>
                    <div className="library-nav-list">
                      {props.selectedDocument.pages.length ? (
                        props.selectedDocument.pages.map((page) => (
                          <button
                            className={`list-card selectable library-nav-card ${page.page_number === activePage?.page_number ? "active" : ""}`}
                            key={`${props.selectedDocument!.doc_id}-page-${page.page_number}`}
                            type="button"
                            onClick={() => setActivePageNumber(page.page_number)}
                          >
                            <div className="card-topline">
                              <strong>第 {page.page_number} 页</strong>
                              <span className="status-pill status-neutral">{page.chunks.length} 块</span>
                            </div>
                            <p>{page.preview || "暂无页摘要。"}</p>
                          </button>
                        ))
                      ) : (
                        <div className="empty-state">当前资料没有分页结果。</div>
                      )}
                    </div>
                  </div>

                  <div className="subpanel">
                    <PageViewer page={activePage} />
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="empty-state">从左侧选择一份资料后，可以预览正文并查看它是如何被切分成章节与分块的。</div>
          )}
        </div>
      </div>
    </section>
  );
}
