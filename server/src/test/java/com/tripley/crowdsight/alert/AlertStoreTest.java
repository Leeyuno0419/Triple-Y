package com.tripley.crowdsight.alert;

import static com.tripley.crowdsight.grade.Grade.ALERT;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.Grade;

class AlertStoreTest {

    private static final Clock FIXED = Clock.fixed(Instant.parse("2026-11-18T05:02:31.512Z"),
            ZoneId.of("Asia/Seoul"));
    private static final String FIXED_TS = "2026-11-18T14:02:31.512+09:00";

    private final AlertStore store = new AlertStore(TestProperties.replay(1000, true), FIXED);

    private static AlertEvent event(Grade level, AlertReason reason) {
        return new AlertEvent(level, reason, "시험", 4.5, List.of("c-0000"));
    }

    private void issueTimes(String zoneId, int n) {
        for (int i = 0; i < n; i++) {
            store.issue(zoneId, i, FIXED_TS, event(ALERT, AlertReason.GRADE_UP));
        }
    }

    private static List<String> ids(List<Alert> alerts) {
        return alerts.stream().map(Alert::alertId).toList();
    }

    @Test
    @DisplayName("발급하면 ID·구역·t·frame_ts를 붙이고 사건 값을 옮긴다")
    void issueAssignsIdAndCopiesFields() {
        Alert alert = store.issue("zone-test", 3, FIXED_TS, event(ALERT, AlertReason.GRADE_UP));

        assertThat(alert).isEqualTo(new Alert("a-20261118-0001", "zone-test", 3, FIXED_TS, ALERT,
                AlertReason.GRADE_UP, "시험", 4.5, List.of("c-0000")));
    }

    @Test
    @DisplayName("미확인 알림은 오래된 것부터 준다")
    void unackedOldestFirst() {
        issueTimes("zone-test", 3);

        assertThat(ids(store.unacked("zone-test")))
                .containsExactly("a-20261118-0001", "a-20261118-0002", "a-20261118-0003");
    }

    @Test
    @DisplayName("구역마다 따로 모은다")
    void unackedPerZone() {
        issueTimes("zone-a", 2);
        issueTimes("zone-b", 1);

        assertThat(store.unacked("zone-a")).hasSize(2);
        assertThat(ids(store.unacked("zone-b"))).containsExactly("a-20261118-0003");
        assertThat(store.unacked("zone-c")).isEmpty();
    }

    @Test
    @DisplayName("구역당 100개를 넘으면 가장 오래된 것부터 버린다")
    void capDropsOldest() {
        issueTimes("zone-test", 101);
        issueTimes("zone-other", 1);

        List<Alert> alerts = store.unacked("zone-test");
        assertThat(alerts).hasSize(100);
        assertThat(alerts.get(0).alertId()).isEqualTo("a-20261118-0002");
        assertThat(alerts.get(99).alertId()).isEqualTo("a-20261118-0101");
        assertThat(ids(store.unacked("zone-other"))).containsExactly("a-20261118-0102");
    }

    @Test
    @DisplayName("받은 목록은 나중 발급에 바뀌지 않고 고칠 수 없다")
    void unackedIsSnapshot() {
        issueTimes("zone-test", 1);
        List<Alert> before = store.unacked("zone-test");
        issueTimes("zone-test", 1);

        assertThat(before).hasSize(1);
        assertThatThrownBy(() -> before.add(before.get(0))).isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    @DisplayName("발급과 조회를 동시에 해도 예외 없이 상한·순서를 지킨다")
    void concurrentIssueAndRead() throws Exception {
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> writer = pool.submit(() -> {
                start.await();
                issueTimes("zone-test", 1000);
                return null;
            });
            Future<List<List<Alert>>> reader = pool.submit(() -> {
                start.await();
                List<List<Alert>> seen = new ArrayList<>();
                for (int i = 0; i < 1000; i++) {
                    seen.add(store.unacked("zone-test"));
                }
                return seen;
            });
            start.countDown();
            writer.get(10, TimeUnit.SECONDS);
            List<List<Alert>> seen = reader.get(10, TimeUnit.SECONDS);

            assertThat(seen).allSatisfy(list -> {
                assertThat(list.size()).isLessThanOrEqualTo(100);
                assertThat(ids(list)).isSorted();
            });
        } finally {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        }
        List<Alert> alerts = store.unacked("zone-test");
        assertThat(alerts).hasSize(100);
        assertThat(alerts.get(99).alertId()).isEqualTo("a-20261118-1000");
    }
}
