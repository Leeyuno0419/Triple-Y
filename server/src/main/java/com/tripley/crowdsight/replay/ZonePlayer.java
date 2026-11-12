package com.tripley.crowdsight.replay;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

import com.tripley.crowdsight.timeline.Frame;
import com.tripley.crowdsight.timeline.ZoneTimeline;

/**
 * 구역 1개의 재생 위치와 상태. tick마다 다음 프레임을 준다. Spring에 의존하지 않는다.
 * 스레드 규칙: tick()은 재생 스레드만 부른다. snapshot()·pollStateChange()와 S7의 제어 메서드는
 * 다른 스레드(WS·REST)에서도 부르므로 모든 공개 메서드를 synchronized로 둔다. 잠그는 시간은 짧다.
 */
public final class ZonePlayer {

    private final ZoneTimeline timeline;
    private final boolean loop;                 // S7 setLoop가 생기면 final을 뗀다
    private PlaybackState state = PlaybackState.PLAYING;
    private int nextT;
    private int currentT;
    private boolean pendingDiscontinuity = true;
    private PlaybackSnapshot pendingChange;     // 아직 가져가지 않은 상태 변화 (없으면 null)

    public ZonePlayer(ZoneTimeline timeline, boolean loop) {
        this.timeline = Objects.requireNonNull(timeline, "timeline");
        if (timeline.frames().isEmpty()) {
            throw new IllegalArgumentException("프레임이 없는 타임라인은 재생할 수 없습니다: zone=" + timeline.zoneId());
        }
        this.loop = loop;
    }

    /** 구역 ID. */
    public String zoneId() {
        return timeline.zoneId();
    }

    /** 재생 중인 타임라인. */
    public ZoneTimeline timeline() {
        return timeline;
    }

    /**
     * PLAYING이면 다음 프레임을 주고 한 칸 나아간다. 끝을 지나면 loop일 때 0으로 돌아가고(wrapped),
     * 아니면 ENDED가 되며 빈 값을 준다. PAUSED·ENDED이면 빈 값.
     */
    public synchronized Optional<Tick> tick() {
        if (state != PlaybackState.PLAYING) {
            return Optional.empty();
        }
        List<Frame> frames = timeline.frames();
        boolean wrapped = false;
        if (nextT >= frames.size()) {
            if (!loop) {
                state = PlaybackState.ENDED;
                pendingChange = snapshotLocked();
                return Optional.empty();
            }
            nextT = 0;
            wrapped = true;
            pendingDiscontinuity = true;
        }
        currentT = nextT;
        nextT++;
        boolean discontinuity = pendingDiscontinuity;
        pendingDiscontinuity = false;
        if (wrapped) {
            pendingChange = snapshotLocked();
        }
        return Optional.of(new Tick(frames.get(currentT), discontinuity, wrapped));
    }

    /** 지금 재생 상태. */
    public synchronized PlaybackSnapshot snapshot() {
        return snapshotLocked();
    }

    /** 마지막 tick에서 상태가 바뀌었으면(반복, 끝) 그 상태를 한 번만 준다. playback 메시지용. */
    public synchronized Optional<PlaybackSnapshot> pollStateChange() {
        PlaybackSnapshot change = pendingChange;
        pendingChange = null;
        return Optional.ofNullable(change);
    }

    private PlaybackSnapshot snapshotLocked() {
        return new PlaybackSnapshot(state, currentT, loop, timeline.durationS());
    }
}
