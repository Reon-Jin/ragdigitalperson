interface DocumentMetaBarProps {
  metrics: Array<{ label: string; value: string; note: string }>;
}

export function DocumentMetaBar(props: DocumentMetaBarProps) {
  return (
    <section className="grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
      {props.metrics.map((item) => (
        <article
          key={item.label}
          className="rounded-2xl border border-white/8 bg-[#121a24]/86 px-4 py-4 shadow-[0_12px_32px_rgba(0,0,0,0.18)]"
        >
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
          <div className="mt-3 flex items-end justify-between gap-4">
            <strong className="text-2xl font-semibold tracking-[0.02em] text-slate-50">{item.value}</strong>
            <span className="text-xs text-slate-500">{item.note}</span>
          </div>
        </article>
      ))}
    </section>
  );
}
