package com.tripley.crowdsight.api;

/**
 * /api/health의 구역 하나.
 *
 * @param zoneId 구역 ID
 * @param state  playing·ended
 * @param t      마지막으로 재생한 초 (시작 전 0)
 * @param loop   끝에서 처음으로 돌아가는지
 */
public record ZoneHealth(String zoneId, String state, int t, boolean loop) {
}
