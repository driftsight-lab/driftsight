import { judgeReliabilityMock } from './mock';
import type { JudgeReliability } from './types';

/**
 * 채점자 신뢰도 데이터를 가져온다.
 * Console API(`GET /api/v1/experiments/judge-reliability`, api.md 8.2)가 아직 없어 예시 데이터를 돌려준다.
 * API가 생기면 이 함수만 `api.get`으로 바꾼다.
 */
export async function getJudgeReliability(): Promise<{
  data: JudgeReliability;
  isMock: boolean;
}> {
  return { data: judgeReliabilityMock, isMock: true };
}
