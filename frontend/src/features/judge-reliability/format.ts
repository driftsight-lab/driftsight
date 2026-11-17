import type { Verdict } from './types';

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

// Landis & Koch(1977)의 kappa 해석 구간
export function kappaLabel(kappa: number): string {
  if (kappa < 0) return '우연보다 낮음';
  if (kappa <= 0.2) return '매우 약한 일치';
  if (kappa <= 0.4) return '약한 일치';
  if (kappa <= 0.6) return '보통 일치';
  if (kappa <= 0.8) return '상당한 일치';
  return '거의 완전한 일치';
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  A: 'A 승',
  B: 'B 승',
  tie: '무승부',
};
