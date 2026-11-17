import { BiasPanel } from './BiasPanel';
import { ConfusionMatrix } from './ConfusionMatrix';
import { DisagreementList } from './DisagreementList';
import { kappaLabel, percent } from './format';
import { StatCard } from './StatCard';
import type { JudgeReliability } from './types';

export function JudgeReliabilityView({ data, isMock }: { data: JudgeReliability; isMock: boolean }) {
  return (
    <main className="min-h-screen bg-slate-50 px-8 py-8">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">채점자 신뢰도</h1>
        <p className="mt-1 text-sm text-slate-600">
          LLM 채점자(2단계)가 사람 평가와 얼마나 일치하는지 검증 · 기준: MT-Bench 사람 평가
        </p>
        <p className="mt-2 text-xs text-slate-500">
          채점자 {data.judgeKey} · 표본 {data.sampleCount}쌍
          {isMock && (
            <span className="ml-2 rounded bg-slate-200 px-2 py-0.5 text-slate-700">
              예시 데이터 (B-1 1차 실행 결과, API 연결 전)
            </span>
          )}
        </p>
      </header>

      {data.sampleCount === 0 ? (
        <section className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="text-lg font-semibold text-slate-800">실험 전</h2>
          <p className="mt-2 text-sm text-slate-600">아직 채점자 신뢰도 실험 결과가 없습니다.</p>
        </section>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard
              title="사람과의 일치율 (무승부 포함)"
              value={percent(data.agreementRateWithTies)}
              aside={`사람끼리 ${percent(data.humanAgreementRate)}`}
              note={`무승부 제외 시 ${percent(data.agreementRate)}`}
              tone={data.agreementRateWithTies >= data.humanAgreementRate ? 'good' : 'neutral'}
            />
            <StatCard
              title="Cohen's kappa"
              value={data.cohensKappa.toFixed(2)}
              note={kappaLabel(data.cohensKappa)}
              tone={data.cohensKappa > 0.6 ? 'good' : 'warn'}
            />
            <StatCard
              title="순서 편향"
              value={percent(1 - data.positionBias.swapConsistency)}
              note="순서를 바꾸면 판정이 뒤집힘"
              tone="warn"
            />
            <StatCard
              title="길이 편향"
              value={percent(data.lengthBias.longerWinRate)}
              note="더 긴 답변이 이긴 비율 (50%면 편향 없음)"
              tone={Math.abs(data.lengthBias.longerWinRate - 0.5) > 0.1 ? 'warn' : 'neutral'}
            />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ConfusionMatrix data={data.confusionMatrix} />
            <BiasPanel
              swapConsistency={data.positionBias.swapConsistency}
              longerWinRate={data.lengthBias.longerWinRate}
            />
          </div>

          <div className="mt-4">
            <DisagreementList items={data.disagreements} />
          </div>
        </>
      )}
    </main>
  );
}
