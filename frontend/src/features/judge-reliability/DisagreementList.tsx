import { VERDICT_LABEL } from './format';
import type { Disagreement } from './types';

export function DisagreementList({ items }: { items: Disagreement[] }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-base font-semibold text-slate-900">불일치 사례</h2>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">표시할 불일치 사례가 없습니다.</p>
      ) : (
        <table className="mt-3 w-full text-left text-sm">
          <thead className="text-slate-500">
            <tr className="border-b border-slate-200">
              <th scope="col" className="py-2 font-normal">MT-Bench 질문</th>
              <th scope="col" className="py-2 font-normal">비교 모델 (A vs B)</th>
              <th scope="col" className="py-2 font-normal">사람</th>
              <th scope="col" className="py-2 font-normal">LLM</th>
              <th scope="col" className="py-2 font-normal">LLM (순서 바꿈)</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr
                key={`${d.questionId}-${d.modelA}-${d.modelB}-${d.turn}-${d.human}`}
                className="border-b border-slate-100 align-top"
              >
                <td className="py-3 pr-4">
                  <p className="font-semibold text-slate-900">
                    #{d.questionId} · {d.turn}턴
                  </p>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500" lang="en">
                    {d.reason}
                  </p>
                </td>
                <td className="py-3 pr-4 text-slate-700">
                  {d.modelA} vs {d.modelB}
                </td>
                <td className="py-3 pr-4 text-slate-900">{VERDICT_LABEL[d.human]}</td>
                <td className="py-3 pr-4 font-semibold text-rose-700">{VERDICT_LABEL[d.judge]}</td>
                <td className="py-3 text-slate-700">{VERDICT_LABEL[d.judgeSwapped]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
