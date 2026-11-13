package com.tripley.crowdsight.ws;

import java.time.Clock;
import java.util.List;
import java.util.Locale;

import org.springframework.stereotype.Component;

import com.tripley.crowdsight.alert.Alert;
import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.grade.CellEvaluation;
import com.tripley.crowdsight.grade.ZoneEvaluation;
import com.tripley.crowdsight.replay.PlaybackSnapshot;
import com.tripley.crowdsight.replay.PlaybackState;
import com.tripley.crowdsight.replay.ZonePlayer;
import com.tripley.crowdsight.replay.ZoneRuntime;
import com.tripley.crowdsight.replay.ZoneStep;
import com.tripley.crowdsight.timeline.CellState;
import com.tripley.crowdsight.timeline.Frame;
import com.tripley.crowdsight.ws.message.AlertMessage;
import com.tripley.crowdsight.ws.message.CellView;
import com.tripley.crowdsight.ws.message.HelloMessage;
import com.tripley.crowdsight.ws.message.PlaybackMessage;
import com.tripley.crowdsight.ws.message.PlaybackView;
import com.tripley.crowdsight.ws.message.ThresholdsView;
import com.tripley.crowdsight.ws.message.ZoneStateMessage;
import com.tripley.crowdsight.ws.message.ZoneView;

import lombok.RequiredArgsConstructor;

/**
 * 재생·판정 결과를 API 메시지 record로 바꾼다 (api-spec 3.1~3.4). JSON 변환은 하지 않는다.
 * 상태가 없어 재생 스레드와 Tomcat 접속 스레드에서 같이 불러도 된다.
 */
@Component
@RequiredArgsConstructor
public class MessageFactory {

    /** hello.schema_version. API 메시지 버전 (api-spec v0.2). 메시지 형식을 바꾸는 PR이 올린다. */
    public static final String API_SCHEMA_VERSION = "0.2";

    private final Clock clock;
    private final CrowdsightProperties props;

    /** 접속한 화면에 보낼 hello. 재생 상태는 지금 snapshot, unacked는 AlertStore.unacked(zoneId)다. */
    public HelloMessage hello(ZoneRuntime zone, List<Alert> unacked) {
        ZonePlayer player = zone.player();
        ThresholdsView thresholds = new ThresholdsView(props.grade().density(), props.instability().pressure(),
                props.inflow().ratio());
        return new HelloMessage(API_SCHEMA_VERSION, zone.zoneId(), player.timeline().metaJson(),
                playbackView(player.snapshot()), thresholds, unacked.stream().map(this::alert).toList());
    }

    /** 발급한 알림 (api-spec 3.3). */
    public AlertMessage alert(Alert a) {
        return new AlertMessage(a.alertId(), a.zoneId(), a.t(), a.frameTs(), a.level(), a.reason(), a.message(),
                a.value(), a.cellIds());
    }

    /** 재생 상태 변화 (반복으로 0, 끝). */
    public PlaybackMessage playback(String zoneId, PlaybackSnapshot snapshot) {
        return new PlaybackMessage(zoneId, stateName(snapshot.state()), snapshot.t(), snapshot.loop());
    }

    /** 한 초 판정 결과. frameTs는 frameTs()로 tick마다 한 번 만든다. */
    public ZoneStateMessage zoneState(String zoneId, ZoneStep step, String frameTs) {
        Frame frame = step.tick().frame();
        ZoneEvaluation eval = step.evaluation();
        ZoneView zone = new ZoneView(eval.zoneGrade(), eval.maxDensity(), frame.inflowRatio(), eval.inflowAlert(),
                frame.count());
        List<CellView> cells = eval.cells().stream().map(MessageFactory::cellView).toList();
        return new ZoneStateMessage(zoneId, eval.t(), frameTs, zone, cells);
    }

    /** 지금 시각의 frame_ts. 한 tick의 zone_state와 alert(S5)는 같은 값을 쓴다. */
    public String frameTs() {
        return FrameTimestamps.now(clock);
    }

    static String stateName(PlaybackState state) {
        return state.name().toLowerCase(Locale.ROOT);
    }

    private static PlaybackView playbackView(PlaybackSnapshot s) {
        return new PlaybackView(stateName(s.state()), s.t(), s.loop(), s.durationS());
    }

    private static CellView cellView(CellEvaluation c) {
        CellState s = c.state();
        return new CellView(c.cellId(), c.grade(), s.density(), s.vx(), s.vy(), s.speedVar(), s.pressure(),
                s.counterflow(), s.densityPred60s(), c.gradePred60s());
    }
}
