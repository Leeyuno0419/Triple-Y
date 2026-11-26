/**
 * 단계별 대응 가이드. 순서는 DENSITY_LEVELS 와 같다 (정상·주의·경계·심각).
 * 근거: docs/proposal.md 위험 등급 표의 '상황실' 열, docs/proposal-detail.md 3.3절·UC-03·UC-06.
 * 현장 대응 절차는 운영 기관이 정해야 하며, 문구를 바꾸려면 여기만 고친다.
 */
export const RESPONSE_GUIDE: Array<{ action: string; steps: string[] }> = [
  { action: '표시만', steps: ['화면 모니터링 유지'] },
  { action: '강조 표시', steps: ['해당 셀과 60초 뒤 예측 확인'] },
  { action: '알림', steps: ['영상과 추이 그래프 확인', '현장 요원에게 상황 전달'] },
  { action: '비상 알림', steps: ['대피 경로 안내 검토', '유입 차단 지점 지정 검토', '현장 요원에게 즉시 지시'] },
];
