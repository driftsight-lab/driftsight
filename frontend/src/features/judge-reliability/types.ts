// docs/specs/api.md > 8.2 채점자 신뢰도 조회 응답(data)
// confusionMatrix·disagreements[] 원소의 필드는 api.md에 아직 정의되지 않아,
// model/src/evaluate/judge_reliability.py가 만드는 구조를 그대로 따른다.

export type Verdict = 'A' | 'B' | 'tie';

export interface ConfusionMatrix {
  labels: Verdict[];
  rows: 'human';
  cols: 'judge';
  /** matrix[사람 판정][채점자 판정] 건수 */
  matrix: number[][];
}

export interface Disagreement {
  questionId: number;
  modelA: string;
  modelB: string;
  turn: number;
  human: Verdict;
  judge: Verdict;
  judgeSwapped: Verdict;
  reason: string;
}

export interface JudgeReliability {
  judgeKey: string;
  sampleCount: number;
  agreementRate: number;
  agreementRateWithTies: number;
  cohensKappa: number;
  humanAgreementRate: number;
  positionBias: { swapConsistency: number };
  lengthBias: { longerWinRate: number };
  confusionMatrix: ConfusionMatrix;
  disagreements: Disagreement[];
}
