package com.tripley.crowdsight.alert;

import java.util.Objects;

/**
 * 저장소가 보관하는 알림 하나와 확인 시각. 불변이다. 확인하면 저장소가 새 값으로 바꿔 넣는다.
 *
 * @param alert   발급한 알림
 * @param ackedAt 처음 확인한 시각 (frame_ts 형식). 미확인이면 null
 */
public record StoredAlert(Alert alert, String ackedAt) {

    public StoredAlert {
        Objects.requireNonNull(alert, "alert");
    }

    /** 확인했는지. */
    public boolean acked() {
        return ackedAt != null;
    }
}
