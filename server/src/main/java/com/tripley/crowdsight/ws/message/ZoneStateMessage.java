package com.tripley.crowdsight.ws.message;

import java.util.List;

/**
 * 1초마다 보내는 구역 상태 (api-spec 3.2).
 *
 * @param type    "zone_state"
 * @param zoneId  구역 ID
 * @param t       프레임 t
 * @param frameTs 보낸 시각 (FrameTimestamps 형식)
 * @param zone    구역 값
 * @param cells   셀 값 (meta 순서)
 */
public record ZoneStateMessage(String type, String zoneId, int t, String frameTs, ZoneView zone,
                               List<CellView> cells) {

    public static final String TYPE = "zone_state";

    public ZoneStateMessage {
        cells = List.copyOf(cells);
    }

    /** type을 "zone_state"로 채운다. */
    public ZoneStateMessage(String zoneId, int t, String frameTs, ZoneView zone, List<CellView> cells) {
        this(TYPE, zoneId, t, frameTs, zone, cells);
    }
}
