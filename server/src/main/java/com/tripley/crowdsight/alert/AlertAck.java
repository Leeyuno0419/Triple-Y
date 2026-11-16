package com.tripley.crowdsight.alert;

/**
 * 확인 요청 결과 (api-spec 4.5).
 *
 * @param alert    확인한 알림
 * @param ackedAt  처음 확인한 시각. 이미 확인한 알림이면 그때 시각
 * @param firstAck 이번 요청이 처음 확인이면 true. 이때만 확인 기록을 쓴다
 */
public record AlertAck(Alert alert, String ackedAt, boolean firstAck) {
}
