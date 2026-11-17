import { VERDICT_LABEL } from './format';
import type { ConfusionMatrix as Matrix } from './types';

function cellClass(isDiagonal: boolean, share: number): string {
  if (isDiagonal) return 'bg-blue-600 text-white';
  if (share >= 0.2) return 'bg-rose-200 text-rose-950';
  if (share >= 0.1) return 'bg-rose-100 text-rose-950';
  return 'bg-rose-50 text-slate-800';
}

export function ConfusionMatrix({ data }: { data: Matrix }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-base font-semibold text-slate-900">혼동 행렬 (사람 vs LLM 채점자)</h2>
      <table className="mt-4 w-full border-separate border-spacing-2 text-center">
        <caption className="sr-only">행은 사람 판정, 열은 LLM 채점자 판정, 칸은 건수</caption>
        <thead>
          <tr>
            <th scope="col" className="text-left text-xs font-normal text-slate-500">
              사람 ↓ / LLM →
            </th>
            {data.labels.map((label) => (
              <th key={label} scope="col" className="text-sm font-semibold text-slate-600">
                {VERDICT_LABEL[label]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.matrix.map((row, i) => {
            const rowTotal = row.reduce((sum, n) => sum + n, 0) || 1;
            return (
              <tr key={data.labels[i]}>
                <th scope="row" className="text-left text-sm font-semibold text-slate-600">
                  {VERDICT_LABEL[data.labels[i]]}
                </th>
                {row.map((count, j) => (
                  <td
                    key={data.labels[j]}
                    className={`rounded-lg py-5 text-2xl font-bold ${cellClass(i === j, count / rowTotal)}`}
                  >
                    {count}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">파란 칸은 사람과 같은 판정, 붉은 칸은 다른 판정입니다.</p>
    </section>
  );
}
