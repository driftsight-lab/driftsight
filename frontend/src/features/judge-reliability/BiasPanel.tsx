import { percent } from './format';

// 순서 교환 일관성이 이 값보다 낮으면 순서 교환 2회 평가를 권한다.
// 문서에 정해진 값이 아니라 화면 표시용 기준이다 (protocol.md B-1: 편향이 보이면 보정 적용).
const SWAP_CONSISTENCY_WARN = 0.9;

function Bar({ value, className }: { value: number; className: string }) {
  const width = Math.max(0, Math.min(1, value)) * 100;
  return (
    <svg viewBox="0 0 100 6" preserveAspectRatio="none" className="h-6 w-full" aria-hidden="true">
      <rect width="100" height="6" className="fill-slate-100" />
      <rect width={width} height="6" className={className} />
      <line x1="50" y1="0" x2="50" y2="6" className="stroke-slate-400" strokeWidth="0.3" />
    </svg>
  );
}

export function BiasPanel({
  swapConsistency,
  longerWinRate,
}: {
  swapConsistency: number;
  longerWinRate: number;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-base font-semibold text-slate-900">편향 점검</h2>

      <div className="mt-4">
        <h3 className="text-sm font-semibold text-slate-800">답변 순서를 바꿨을 때 판정이 유지되는 비율</h3>
        <p className="mt-1 text-2xl font-bold text-blue-700">{percent(swapConsistency)}</p>
        <Bar value={swapConsistency} className="fill-blue-600" />
        <p className="text-sm text-slate-600">순서를 바꾸면 판정이 뒤집힌 비율 {percent(1 - swapConsistency)}</p>
      </div>

      <div className="mt-6">
        <h3 className="text-sm font-semibold text-slate-800">승부가 난 판정 중 더 긴 답변이 이긴 비율</h3>
        <p className="mt-1 text-2xl font-bold text-amber-700">{percent(longerWinRate)}</p>
        <Bar value={longerWinRate} className="fill-amber-500" />
        <p className="text-sm text-slate-600">가운데 선(50%)에 가까울수록 길이 편향이 작습니다.</p>
      </div>

      {swapConsistency < SWAP_CONSISTENCY_WARN && (
        <p className="mt-6 inline-block rounded-full bg-amber-100 px-3 py-1 text-sm font-semibold text-amber-900">
          권장: 답변 순서를 바꿔 2번 평가하고, 판정이 다르면 무승부로 처리
        </p>
      )}
    </section>
  );
}
