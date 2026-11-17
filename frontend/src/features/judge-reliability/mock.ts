import type { JudgeReliability } from './types';

// Console API 8.2가 생기기 전까지 쓰는 예시 데이터 (frontend/CLAUDE.md > 6. Data and API).
// 값은 과제 B-1 1차 실행 결과(PR #34 댓글, claude-sonnet-4-5, MT-Bench 보고용 181쌍)이다.
export const judgeReliabilityMock: JudgeReliability = {
  judgeKey: 'claude-sonnet-4-5-judge-pairwise-v1',
  sampleCount: 181,
  agreementRate: 0.7766,
  agreementRateWithTies: 0.6113,
  cohensKappa: 0.3909,
  humanAgreementRate: 0.6718,
  positionBias: { swapConsistency: 0.7624 },
  lengthBias: { longerWinRate: 0.6768 },
  confusionMatrix: {
    labels: ['A', 'B', 'tie'],
    rows: 'human',
    cols: 'judge',
    matrix: [
      [74, 20, 7],
      [13, 79, 4],
      [19, 40, 9],
    ],
  },
  disagreements: [
    {
      questionId: 83,
      modelA: 'gpt-3.5-turbo',
      modelB: 'claude-v1',
      turn: 2,
      human: 'A',
      judge: 'B',
      judgeSwapped: 'B',
      reason: "For Turn 1, both responses provide blog post outlines, but Assistant B delivers a more comprehensive and practical outline that includes specific comparative points with examples within the outline structure, while staying within the 200-word limit at 160 words. Assistant A provides a solid structural outline but lacks the substantive comparative content. For Turn 2, Assistant B creates a more accurate and complete limerick that better captures the essence of the comparison, while Assistant A's limerick is too short (only one verse instead of the typical five-line structure) and doesn't adequately represent the content of the blog outline. Assistant B maintains both quality and completeness across both turns.",
    },
    {
      questionId: 83,
      modelA: 'gpt-4',
      modelB: 'claude-v1',
      turn: 2,
      human: 'A',
      judge: 'tie',
      judgeSwapped: 'A',
      reason: "Both assistants correctly completed the two-part challenge. For Turn 1, Assistant A provided a traditional, well-structured outline while Assistant B gave a more narrative outline with specific examples. Both stayed under 200 words. For Turn 2, Assistant B created a proper limerick with the AABBA rhyme scheme (fancy/stability/heavenly technically breaks this pattern, though it attempts it), while Assistant A's response is not technically a limerick but rather a single five-line poem that doesn't follow the form. However, the challenge is somewhat ambiguous - rephrasing a detailed outline as a limerick is inherently difficult to do literally. Neither perfectly captures all the information in limerick form, making this effectively a tie.",
    },
    {
      questionId: 86,
      modelA: 'gpt-4',
      modelB: 'claude-v1',
      turn: 1,
      human: 'A',
      judge: 'tie',
      judgeSwapped: 'A',
      reason: "Both responses effectively create an immersive marketplace scene with vivid sensory details covering smells, sounds, and visuals. Assistant A's response is slightly more polished with metaphors like 'vibrant tapestry' and 'living, breathing entity,' while Assistant B provides a more straightforward description. However, both adequately fulfill the prompt with appropriate depth and detail.",
    },
    {
      questionId: 87,
      modelA: 'gpt-3.5-turbo',
      modelB: 'gpt-4',
      turn: 2,
      human: 'tie',
      judge: 'B',
      judgeSwapped: 'B',
      reason: "For Turn 2, Assistant B follows the instruction to use only four-word sentences throughout the entire story, while Assistant A primarily uses fragments and incomplete sentences that don't consistently meet the four-word requirement. Assistant B's version maintains narrative coherence while adhering strictly to the constraint, making it the better response to the user's specific instruction.",
    },
    {
      questionId: 88,
      modelA: 'gpt-3.5-turbo',
      modelB: 'claude-v1',
      turn: 2,
      human: 'A',
      judge: 'B',
      judgeSwapped: 'B',
      reason: "Assistant B better fulfills the Turn 2 instruction to use only nouns and adjectives without verbs. While both provided three bullet points, Assistant A's items like 'Unleashing of powers' contains the gerund 'unleashing' which is a verb form, whereas Assistant B strictly adhered to using only nouns and adjectives (e.g., 'shocked protagonist,' 'unexpected temporal shift,' 'familiar yet unfamiliar world'). Both opening paragraphs were engaging and appropriate.",
    },
  ],
};

export const judgeReliabilityEmpty: JudgeReliability = {
  ...judgeReliabilityMock,
  sampleCount: 0,
  confusionMatrix: { ...judgeReliabilityMock.confusionMatrix, matrix: [] },
  disagreements: [],
};
