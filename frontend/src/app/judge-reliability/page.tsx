import { getJudgeReliability } from '@/features/judge-reliability/data';
import { JudgeReliabilityView } from '@/features/judge-reliability/JudgeReliabilityView';

export const metadata = { title: '채점자 신뢰도 | AISV 관측 플랫폼' };

export default async function JudgeReliabilityPage() {
  const { data, isMock } = await getJudgeReliability();
  return <JudgeReliabilityView data={data} isMock={isMock} />;
}
