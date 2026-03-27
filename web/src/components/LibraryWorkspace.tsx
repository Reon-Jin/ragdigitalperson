import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";

import { formatTimeLabel } from "../lib/format";
import type { ConversationSummary, DocumentDetail, IngestionJob, LibraryFileItem, SearchResultItem, UserProfile } from "../types";
import { DocumentMetaBar } from "./library/DocumentMetaBar";
import { DocumentTabs, type LibraryTabKey } from "./library/DocumentTabs";
import { mockDocument, mockFiles, mockHits, mockJobs, mockSessions } from "./library/mockData";
import { RightInsightPanel } from "./library/RightInsightPanel";
import { SessionDrawer } from "./library/SessionDrawer";
import { Sidebar } from "./library/Sidebar";
import { TopHeader } from "./library/TopHeader";

function resolveJob(jobs: IngestionJob[], docId: string): IngestionJob | null {
  const matches = jobs.filter((item) => item.doc_id === docId);
  if (!matches.length) return null;
  return matches.sort((a, b) => (b.updated_at || b.created_at).localeCompare(a.updated_at || a.created_at))[0];
}

function resolveStatusLabel(item: LibraryFileItem, job: IngestionJob | null): string {
  if (job) return job.stage;
  if (item.status === "completed") return "Completed";
  if (item.status === "failed") return "Failed";
  if (item.status === "processing") return "Processing";
  return item.status || "Queued";
}

export function LibraryWorkspace(props: {
  files: LibraryFileItem[];
  search: string;
  selectedDocumentId: string;
  selectedDocument: DocumentDetail | null;
  detailBusy: boolean;
  deletingDocId: string;
  jobs: IngestionJob[];
  profile: UserProfile;
  sessions: ConversationSummary[];
  activeConversationId: string;
  onSearchChange: (value: string) => void;
  onSelectDocument: (docId: string) => void;
  onRefresh: () => void;
  onUpdateDocument: (docId: string, patch: { title?: string; is_active?: boolean }) => Promise<DocumentDetail>;
  onDeleteDocument: (docId: string) => void;
  onUploadFiles: (files: FileList | File[]) => void;
  onSaveProfile: () => void;
  onProfileChange: (patch: Partial<UserProfile>) => void;
  onOpenSession: (conversationId: string) => void;
  onAskQuestion: (prompt: string) => void;
  onGoAnalysis: () => void;
  onBackToDesk: () => void;
  onLogout: () => void;
}) {
  const [activeTab, setActiveTab] = useState<LibraryTabKey>("summary");
  const [selectedChunkId, setSelectedChunkId] = useState("");
  const [selectedPageNumber, setSelectedPageNumber] = useState(1);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [editingDocId, setEditingDocId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [savingDocId, setSavingDocId] = useState("");

  const deferredSearch = useDeferredValue(props.search);
  const usingMockData = !props.files.length;
  const displayFiles = usingMockData ? mockFiles : props.files;
  const displayJobs = usingMockData ? mockJobs : props.jobs;
  const displaySessions = props.sessions.length ? props.sessions : mockSessions;

  const filteredFiles = useMemo(() => {
    const keyword = deferredSearch.trim().toLowerCase();
    if (!keyword) return displayFiles;
    return displayFiles.filter((item) => [item.title, item.filename, item.summary, item.category, ...(item.keywords || [])].join("\n").toLowerCase().includes(keyword));
  }, [deferredSearch, displayFiles]);

  const displayDocument = useMemo(() => {
    if (usingMockData) return mockDocument;
    if (props.selectedDocument) return props.selectedDocument;
    return null;
  }, [props.selectedDocument, usingMockData]);

  const activeJob = displayDocument ? resolveJob(displayJobs, displayDocument.doc_id) : null;
  const displayHits: SearchResultItem[] = usingMockData ? mockHits : mockHits;

  useEffect(() => {
    if (!displayDocument) {
      setSelectedChunkId("");
      setSelectedPageNumber(1);
      return;
    }
    setSelectedChunkId((current) => current || displayDocument.chunks[0]?.chunk_id || "");
    setSelectedPageNumber((current) => current || displayDocument.pages[0]?.page_number || 1);
  }, [displayDocument]);

  useEffect(() => {
    if (!editingDocId) return;
    const exists = displayFiles.some((item) => item.doc_id === editingDocId);
    if (!exists) {
      setEditingDocId("");
      setRenameDraft("");
    }
  }, [displayFiles, editingDocId]);

  const statusTone = displayDocument?.status === "failed" ? "error" : activeJob ? "processing" : "success";
  const statusLabel = displayDocument?.status === "failed" ? "Parse Failed" : activeJob ? `${activeJob.stage} ${Math.round((activeJob.progress || 0) * 100)}%` : "Indexed";

  const metrics = useMemo(
    () => [
      { label: "Pages", value: `${displayDocument?.pages.length || 0}`, note: "source pages" },
      { label: "Sections", value: `${displayDocument?.section_count || 0}`, note: "structured headings" },
      { label: "Chunks", value: `${displayDocument?.chunk_count || 0}`, note: "retrieval units" },
      { label: "Updated", value: displayDocument ? formatTimeLabel(displayDocument.uploaded_at) : "--", note: "latest sync" },
      {
        label: "Retrieval",
        value: activeJob ? "Processing" : displayDocument ? (displayDocument.is_active ? "Active" : "Inactive") : "Pending",
        note: activeJob ? activeJob.message || "background job" : displayDocument?.is_active ? "included in RAG" : "excluded from RAG",
      },
    ],
    [activeJob, displayDocument],
  );

  const startRename = (item: LibraryFileItem) => {
    if (usingMockData) return;
    setEditingDocId(item.doc_id);
    setRenameDraft(item.title || item.filename);
  };

  const submitRename = async (docId: string) => {
    if (usingMockData) return;
    const nextTitle = renameDraft.trim();
    if (!nextTitle) return;
    setSavingDocId(docId);
    try {
      await props.onUpdateDocument(docId, { title: nextTitle });
      setEditingDocId("");
      setRenameDraft("");
    } catch {
      // handled by parent workspace state
    } finally {
      setSavingDocId("");
    }
  };

  const toggleDocument = async (item: LibraryFileItem) => {
    if (usingMockData) return;
    setSavingDocId(item.doc_id);
    try {
      await props.onUpdateDocument(item.doc_id, { is_active: !item.is_active });
    } catch {
      // handled by parent workspace state
    } finally {
      setSavingDocId("");
    }
  };

  return (
    <>
      <div className="min-h-screen bg-[#071017] text-slate-100">
        <div className="grid min-h-screen grid-cols-[248px_minmax(0,1fr)_320px]">
          <Sidebar
            profile={props.profile}
            activeKey="library"
            onSaveProfile={props.onSaveProfile}
            onBackToDesk={props.onBackToDesk}
            onGoLibrary={() => {}}
            onGoAnalysis={props.onGoAnalysis}
            onOpenSessions={() => setSessionOpen(true)}
            onLogout={props.onLogout}
            onProfileChange={props.onProfileChange}
            onUploadFiles={props.onUploadFiles}
            uploading={Boolean(activeJob)}
            queuedCount={displayJobs.filter((item) => !["completed", "failed"].includes(item.status)).length}
          />

          <main className="min-w-0 bg-[radial-gradient(circle_at_top,_rgba(33,55,75,0.24),_transparent_42%)] px-6 py-6 2xl:px-8">
            <div className="mx-auto flex max-w-[1380px] flex-col gap-5">
              <TopHeader
                title={displayDocument?.title || "Knowledge Workspace"}
                filename={displayDocument?.filename || "No document selected"}
                suffix={displayDocument?.suffix || ".pdf"}
                uploadedAt={displayDocument ? formatTimeLabel(displayDocument.uploaded_at) : "--"}
                statusLabel={statusLabel}
                statusTone={statusTone}
                onRefresh={props.onRefresh}
                onDelete={() => displayDocument && !usingMockData && props.onDeleteDocument(displayDocument.doc_id)}
                onExportSummary={() => props.onAskQuestion(`Summarize document \"${displayDocument?.title || "current document"}\" and prioritize evidence from it.`)}
                disableDelete={!displayDocument || usingMockData || props.deletingDocId === displayDocument.doc_id}
                demo={usingMockData}
              />

              <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
                <aside className="rounded-[24px] border border-white/8 bg-[#0f1620]/88 p-4">
                  <div className="mb-4 flex items-end justify-between gap-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Knowledge List</p>
                      <h2 className="mt-1 text-sm font-semibold text-slate-100">Documents</h2>
                    </div>
                    <span className="rounded-full border border-white/8 px-3 py-1 text-xs text-slate-400">{filteredFiles.length}</span>
                  </div>
                  <input
                    value={props.search}
                    onChange={(event) => props.onSearchChange(event.target.value)}
                    className="mb-4 w-full rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600"
                    placeholder="Search title, filename, keywords"
                  />
                  <div className="max-h-[calc(100vh-19rem)] space-y-3 overflow-auto pr-1">
                    {filteredFiles.length ? (
                      filteredFiles.map((item) => {
                        const active = item.doc_id === (displayDocument?.doc_id || props.selectedDocumentId);
                        const itemJob = resolveJob(displayJobs, item.doc_id);
                        const editing = editingDocId === item.doc_id;
                        const busy = savingDocId === item.doc_id;
                        return (
                          <div key={item.doc_id} className={`rounded-2xl border px-4 py-4 transition ${active ? "border-emerald-400/24 bg-emerald-400/[0.06]" : "border-white/8 bg-white/[0.02]"}`}>
                            <button
                              type="button"
                              onClick={() => {
                                if (usingMockData) return;
                                props.onSelectDocument(item.doc_id);
                              }}
                              className="w-full text-left"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  {editing ? (
                                    <input
                                      autoFocus
                                      value={renameDraft}
                                      onChange={(event) => setRenameDraft(event.target.value)}
                                      onClick={(event) => event.stopPropagation()}
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter") {
                                          event.preventDefault();
                                          void submitRename(item.doc_id);
                                        }
                                        if (event.key === "Escape") {
                                          setEditingDocId("");
                                          setRenameDraft("");
                                        }
                                      }}
                                      className="w-full rounded-xl border border-emerald-400/20 bg-black/20 px-3 py-2 text-sm text-slate-100 outline-none"
                                      placeholder="Document title"
                                    />
                                  ) : (
                                    <p className="truncate text-sm font-medium text-slate-100">{item.title || item.filename}</p>
                                  )}
                                  <p className="mt-1 text-xs text-slate-500">{item.filename}</p>
                                  <p className={`mt-2 text-[11px] uppercase tracking-[0.16em] ${item.is_active ? "text-emerald-300/80" : "text-amber-300/80"}`}>
                                    {item.is_active ? "RAG ACTIVE" : "RAG OFF"}
                                  </p>
                                </div>
                                <span className="rounded-full border border-white/8 px-2.5 py-1 text-[11px] text-slate-400">{resolveStatusLabel(item, itemJob)}</span>
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-slate-600">
                                <span>{item.suffix.replace(".", "").toUpperCase()}</span>
                                <span>{item.section_count} sections</span>
                                <span>{item.chunk_count} chunks</span>
                              </div>
                              <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-400">{item.summary || "No summary yet."}</p>
                            </button>

                            <div className="mt-4 flex flex-wrap gap-2">
                              {editing ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => void submitRename(item.doc_id)}
                                    disabled={busy || !renameDraft.trim()}
                                    className="rounded-full border border-emerald-400/24 bg-emerald-400/[0.08] px-3 py-1.5 text-xs text-emerald-200 disabled:opacity-50"
                                  >
                                    Save Name
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setEditingDocId("");
                                      setRenameDraft("");
                                    }}
                                    disabled={busy}
                                    className="rounded-full border border-white/8 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-50"
                                  >
                                    Cancel
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => startRename(item)}
                                  disabled={busy || usingMockData}
                                  className="rounded-full border border-white/8 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-50"
                                >
                                  Rename
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => void toggleDocument(item)}
                                disabled={busy || usingMockData}
                                className={`rounded-full border px-3 py-1.5 text-xs disabled:opacity-50 ${item.is_active ? "border-emerald-400/24 bg-emerald-400/[0.08] text-emerald-200" : "border-amber-400/24 bg-amber-400/[0.08] text-amber-200"}`}
                              >
                                {item.is_active ? "Disable Retrieval" : "Enable Retrieval"}
                              </button>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.02] p-5 text-sm text-slate-400">No matching documents.</div>
                    )}
                  </div>
                </aside>

                <div className="min-w-0 space-y-5">
                  <DocumentMetaBar metrics={metrics} />
                  <DocumentTabs
                    activeTab={activeTab}
                    document={displayDocument}
                    loading={props.detailBusy}
                    selectedChunkId={selectedChunkId}
                    selectedPageNumber={selectedPageNumber}
                    onChangeTab={(tab) => startTransition(() => setActiveTab(tab))}
                    onSelectChunk={setSelectedChunkId}
                    onSelectPage={setSelectedPageNumber}
                    onAsk={(prompt) => {
                      props.onAskQuestion(prompt);
                      setSessionOpen(false);
                    }}
                  />
                </div>
              </section>
            </div>
          </main>

          <RightInsightPanel
            collapsed={rightCollapsed}
            onToggleCollapsed={() => setRightCollapsed((current) => !current)}
            document={displayDocument}
            sessions={displaySessions}
            hits={displayHits}
            onOpenSessions={() => setSessionOpen(true)}
            onAsk={props.onAskQuestion}
          />
        </div>
      </div>

      <SessionDrawer
        open={sessionOpen}
        sessions={displaySessions}
        activeConversationId={props.activeConversationId}
        onClose={() => setSessionOpen(false)}
        onOpenSession={(conversationId) => {
          setSessionOpen(false);
          if (!usingMockData) props.onOpenSession(conversationId);
        }}
      />
    </>
  );
}