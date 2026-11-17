/**
 * 알림 확인(ack) 요청: POST /api/alerts/{alert_id}/ack (docs/api-spec.md 4.5절).
 *
 * 응답: 200 {alert_id, acked_at} (이미 확인한 알림이어도 200), 없는 ID 면 404.
 * 404 는 서버가 재시작돼 알림 번호가 1부터 다시 시작했거나 이미 정리된 알림이다. 화면 목록에서 지우면 되므로 성공으로 본다.
 * 그 밖의 오류(네트워크 끊김, 5xx)는 Error 를 던져 목록에 남기고 다시 누를 수 있게 한다.
 */
export async function ackAlert(apiBase: string, alertId: string, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${apiBase}/api/alerts/${encodeURIComponent(alertId)}/ack`, { method: 'POST', signal });
  if (res.ok || res.status === 404) return;
  throw new Error(`알림 확인 실패: HTTP ${res.status}`);
}
