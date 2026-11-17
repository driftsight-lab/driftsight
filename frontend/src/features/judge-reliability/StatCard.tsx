interface StatCardProps {
  title: string;
  value: string;
  note: string;
  tone?: 'good' | 'warn' | 'neutral';
  aside?: string;
}

const TONE_CLASS = {
  good: 'text-emerald-700',
  warn: 'text-amber-700',
  neutral: 'text-slate-600',
} as const;

export function StatCard({ title, value, note, tone = 'neutral', aside }: StatCardProps) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-sm text-slate-500">{title}</h2>
      <div className="mt-2 flex items-baseline gap-3">
        <p className="text-4xl font-bold text-slate-900">{value}</p>
        {aside && <p className="text-sm text-slate-600">{aside}</p>}
      </div>
      <p className={`mt-1 text-sm font-semibold ${TONE_CLASS[tone]}`}>{note}</p>
    </section>
  );
}
