package com.tripley.crowdsight.replay;

import static com.tripley.crowdsight.timeline.TimelineFixtures.timelineOf;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import com.tripley.crowdsight.timeline.ZoneTimeline;

class ZonePlayerTest {

    private static List<Tick> tickN(ZonePlayer player, int n) {
        List<Tick> ticks = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            ticks.add(player.tick().orElseThrow());
        }
        return ticks;
    }

    @Test
    @DisplayName("시작 전 상태는 재생 중 t=0이다")
    void snapshotBeforeFirstTick() {
        ZonePlayer player = new ZonePlayer(timelineOf(3), true);

        assertThat(player.snapshot()).isEqualTo(new PlaybackSnapshot(PlaybackState.PLAYING, 0, true, 3));
        assertThat(player.pollStateChange()).isEmpty();
    }

    @Test
    @DisplayName("첫 tick은 t=0이고 불연속이다")
    void firstTickIsDiscontinuity() {
        ZoneTimeline timeline = timelineOf(5);
        ZonePlayer player = new ZonePlayer(timeline, true);

        Tick tick = player.tick().orElseThrow();

        assertThat(tick.frame().t()).isZero();
        assertThat(tick.discontinuity()).isTrue();
        assertThat(tick.wrapped()).isFalse();
        assertThat(tick.frame()).isSameAs(timeline.frames().get(0));
    }

    @Test
    @DisplayName("끝에서 처음으로 돌아가며 불연속·반복을 표시한다")
    void loops() {
        List<Tick> ticks = tickN(new ZonePlayer(timelineOf(3), true), 7);

        assertThat(ticks).extracting(k -> k.frame().t()).containsExactly(0, 1, 2, 0, 1, 2, 0);
        assertThat(ticks).extracting(Tick::discontinuity).containsExactly(true, false, false, true, false, false, true);
        assertThat(ticks).extracting(Tick::wrapped).containsExactly(false, false, false, true, false, false, true);
    }

    @Test
    @DisplayName("반복 상태 변화는 한 번만 준다")
    void wrapReportsPlaybackOnce() {
        ZonePlayer player = new ZonePlayer(timelineOf(3), true);

        for (int i = 0; i < 3; i++) {
            player.tick();
            assertThat(player.pollStateChange()).isEmpty();
        }
        player.tick();

        assertThat(player.pollStateChange()).contains(new PlaybackSnapshot(PlaybackState.PLAYING, 0, true, 3));
        assertThat(player.pollStateChange()).isEmpty();
    }

    @Test
    @DisplayName("프레임 1개도 반복한다")
    void loopsSingleFrame() {
        List<Tick> ticks = tickN(new ZonePlayer(timelineOf(1), true), 3);

        assertThat(ticks).extracting(k -> k.frame().t()).containsExactly(0, 0, 0);
        assertThat(ticks).extracting(Tick::wrapped).containsExactly(false, true, true);
    }

    @Test
    @DisplayName("반복이 꺼져 있으면 마지막 프레임 다음 tick에 끝난다")
    void endsWithoutLoop() {
        ZonePlayer player = new ZonePlayer(timelineOf(3), false);
        List<Boolean> present = new ArrayList<>();

        for (int i = 1; i <= 5; i++) {
            Optional<Tick> tick = player.tick();
            present.add(tick.isPresent());
            if (i == 3) {
                assertThat(player.snapshot()).isEqualTo(new PlaybackSnapshot(PlaybackState.PLAYING, 2, false, 3));
            }
            if (i == 4) {
                PlaybackSnapshot ended = new PlaybackSnapshot(PlaybackState.ENDED, 2, false, 3);
                assertThat(player.snapshot()).isEqualTo(ended);
                assertThat(player.pollStateChange()).contains(ended);
            }
            if (i == 5) {
                assertThat(player.pollStateChange()).isEmpty();
            }
        }

        assertThat(present).containsExactly(true, true, true, false, false);
    }

    @Test
    @DisplayName("프레임이 없는 타임라인은 만들 수 없다")
    void rejectsEmptyTimeline() {
        ZoneTimeline empty = timelineOf(0);

        assertThatThrownBy(() -> new ZonePlayer(empty, true))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("프레임이 없는");
    }
}
