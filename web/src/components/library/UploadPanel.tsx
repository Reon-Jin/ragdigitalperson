import { useId } from "react";

interface UploadPanelProps {
  uploading: boolean;
  queuedCount: number;
  onUploadFiles: (files: FileList | File[]) => void;
}

export function UploadPanel(props: UploadPanelProps) {
  const inputId = useId();

  return (
    <section className="rounded-2xl border border-white/6 bg-slate-950/50 p-4">
      <div className="mb-3">
        <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Knowledge Intake</p>
        <h2 className="mt-1 text-sm font-semibold text-slate-100">资料注入</h2>
        <p className="mt-1 text-sm leading-6 text-slate-400">上传后将后台解析，不阻塞当前浏览与问答。</p>
      </div>

      <label
        htmlFor={inputId}
        className="flex cursor-pointer flex-col gap-2 rounded-2xl border border-dashed border-white/12 bg-white/[0.02] px-4 py-4 hover:border-emerald-400/35 hover:bg-emerald-400/[0.05]"
      >
        <span className="text-sm font-medium text-slate-100">{props.uploading ? "后台处理中" : "上传资料或研报"}</span>
        <span className="text-xs leading-5 text-slate-500">支持 PDF / DOCX / TXT / CSV / HTML / XLSX</span>
        <span className="text-xs text-emerald-300">{props.queuedCount > 0 ? `队列中 ${props.queuedCount} 份资料` : "点击选择文件"}</span>
      </label>
      <input
        id={inputId}
        type="file"
        multiple
        accept=".txt,.md,.pdf,.docx,.csv,.json,.html,.htm,.xlsx"
        className="hidden"
        onChange={(event) => {
          if (event.target.files?.length) props.onUploadFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </section>
  );
}
