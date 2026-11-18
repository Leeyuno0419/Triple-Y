package com.tripley.crowdsight.e5;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

import com.tripley.crowdsight.alert.AlertEvent;
import com.tripley.crowdsight.config.CrowdsightProperties;
import com.tripley.crowdsight.config.TestProperties;
import com.tripley.crowdsight.grade.CellEvaluation;
import com.tripley.crowdsight.grade.GradeSettings;
import com.tripley.crowdsight.grade.InflowSettings;
import com.tripley.crowdsight.grade.InstabilitySettings;
import com.tripley.crowdsight.grade.ZoneEvaluation;
import com.tripley.crowdsight.replay.ZoneRegistry;
import com.tripley.crowdsight.replay.ZoneRuntime;
import com.tripley.crowdsight.replay.ZoneStep;
import com.tripley.crowdsight.timeline.TimelineFixtures;
import com.tripley.crowdsight.timeline.TimelineLoader;

import lombok.extern.slf4j.Slf4j;

/**
 * E5 기준값 민감도 실행기. test 소스셋에 있어 bootJar에 들어가지 않고, @Test가 없어 ./gradlew test에서 돌지 않는다.
 * Gradle 작업 e5Sweep으로 실행한다: 인자 = 타임라인 파일, 출력 폴더 (상대 경로는 작업 폴더 server/ 기준).
 * 타임라인 하나를 서버와 같은 경로(TimelineLoader 검증 → ZoneRegistry 배선 → ZoneRuntime.tick)로 기준값 조합마다
 * 끝까지(반복 없음) 재생해 CSV 4개를 쓴다. Spring 컨텍스트 없이 설정 record를 직접 만든다. 판정 객체를 직접
 * 조립하지 않으므로 서버 배선과 어긋날 수 없다. 기본 조합은 TestProperties(= application.yml 기본값) 상수다.
 * 스레드 규칙: main 스레드 하나에서만 돈다. 상태 없음.
 */
@Slf4j
public final class E5Sweep {

    static final List<Double> PRESSURES = List.of(0.005, 0.01, 0.02, 0.04, 0.08);
    static final List<Integer> SECONDS = List.of(1, 2, 3, 5);
    static final List<Double> RATIOS = List.of(0.5, 0.55, 0.6, 0.65, 0.7);
    static final List<Window> WINDOWS = List.of(new Window(3, 2), new Window(5, 3), new Window(10, 6));
    static final List<Double> MIN_COUNTS = List.of(0.0, 3.0, 5.0);
    static final int OFF_SECONDS = 10;

    static final String TICKS_HEADER =
            "t,zone_grade,max_density,inflow_avg,inflow_alert,n_unstable,unstable_cells,events";
    static final String ALERTS_HEADER = "t,reason,level,value,cell_ids";
    static final String INSTABILITY_HEADER = "pressure,seconds,is_default," + SweepSummary.HEADER;
    static final String INFLOW_HEADER =
            "ratio,window_seconds,min_samples,min_count,off_seconds,is_default," + SweepSummary.HEADER;

    /** 유입 평균 창과 그 창의 최소 non-null 수 (제안 P5). */
    record Window(int seconds, int minSamples) {
    }

    private E5Sweep() {
    }

    /** 인자: 타임라인 파일, 출력 폴더. 파일 이름 앞부분은 타임라인 파일 이름(확장자 뺌)이다. */
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException("사용법: e5Sweep --args=\"<타임라인 파일> <출력 폴더>\"");
        }
        Path timeline = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        String stem = stem(timeline);
        List<ZoneStep> base = replay(timeline, TestProperties.GRADE, TestProperties.INSTABILITY,
                TestProperties.INFLOW);
        write(outDir.resolve(stem + "_ticks.csv"), TICKS_HEADER, tickRows(base));
        write(outDir.resolve(stem + "_alerts.csv"), ALERTS_HEADER, alertRows(base));
        write(outDir.resolve(stem + "_sweep_instability.csv"), INSTABILITY_HEADER, instabilityRows(timeline));
        write(outDir.resolve(stem + "_sweep_inflow.csv"), INFLOW_HEADER, inflowRows(timeline));
    }

    /** 서버 경로로 끝까지 재생한 초별 결과. 시작 tick에서 판정·알림이 초기화된다 (ZoneRuntime.java:41-45). */
    static List<ZoneStep> replay(Path timeline, GradeSettings grade, InstabilitySettings instability,
                                 InflowSettings inflow) {
        CrowdsightProperties props = props(timeline, grade, instability, inflow);
        ZoneRuntime zone = new ZoneRegistry(new TimelineLoader(TimelineFixtures.MAPPER, props), props)
                .all().getFirst();
        List<ZoneStep> steps = new ArrayList<>();
        for (Optional<ZoneStep> step = zone.tick(); step.isPresent(); step = zone.tick()) {
            steps.add(step.get());
        }
        return steps;
    }

    /** 파일 하나를 읽는 서버 설정. 판정 외 성분은 TestProperties 기본값, 반복은 끈다. */
    static CrowdsightProperties props(Path timeline, GradeSettings grade, InstabilitySettings instability,
                                      InflowSettings inflow) {
        Path abs = timeline.toAbsolutePath().normalize();
        return new CrowdsightProperties(abs.getParent().toString(), List.of(abs.getFileName().toString()),
                TestProperties.TIME_ZONE, new CrowdsightProperties.Replay(1000, false, TestProperties.SLOW_TICK_MS),
                grade, instability, inflow, TestProperties.UNACKED_ALERT_LIMIT, TestProperties.WS,
                TestProperties.ALERT_LOG, TestProperties.CORS);
    }

    /** 불안정 격자 20행 (제안 P4). 유입·등급은 기본값. */
    static List<String> instabilityRows(Path timeline) {
        List<String> rows = new ArrayList<>();
        for (double pressure : PRESSURES) {
            for (int seconds : SECONDS) {
                InstabilitySettings settings = new InstabilitySettings(pressure, seconds);
                SweepSummary summary = SweepSummary.of(replay(timeline, TestProperties.GRADE, settings,
                        TestProperties.INFLOW));
                rows.add(pressure + "," + seconds + "," + settings.equals(TestProperties.INSTABILITY) + ","
                        + summary.toCsv());
            }
        }
        return rows;
    }

    /** 유입 격자 45행 (제안 P5). 불안정·등급은 기본값. */
    static List<String> inflowRows(Path timeline) {
        List<String> rows = new ArrayList<>();
        for (double ratio : RATIOS) {
            for (Window window : WINDOWS) {
                for (double minCount : MIN_COUNTS) {
                    InflowSettings settings = new InflowSettings(ratio, window.seconds(), window.minSamples(),
                            OFF_SECONDS, minCount);
                    SweepSummary summary = SweepSummary.of(replay(timeline, TestProperties.GRADE,
                            TestProperties.INSTABILITY, settings));
                    rows.add(ratio + "," + window.seconds() + "," + window.minSamples() + "," + minCount + ","
                            + OFF_SECONDS + "," + settings.equals(TestProperties.INFLOW) + "," + summary.toCsv());
                }
            }
        }
        return rows;
    }

    /** 초별 판정 행. n_unstable·unstable_cells는 판정 대상(eligible) 셀만, events는 "REASON:LEVEL"을 ;로 잇는다. */
    static List<String> tickRows(List<ZoneStep> steps) {
        List<String> rows = new ArrayList<>(steps.size());
        for (ZoneStep step : steps) {
            ZoneEvaluation eval = step.evaluation();
            List<String> unstable = eval.cells().stream()
                    .filter(c -> c.eligible() && c.unstable())
                    .map(CellEvaluation::cellId)
                    .toList();
            String events = step.alerts().stream()
                    .map(a -> a.reason() + ":" + a.level())
                    .collect(Collectors.joining(";"));
            rows.add(eval.t() + "," + eval.zoneGrade() + "," + text(eval.maxDensity()) + ","
                    + text(eval.inflowAvg()) + "," + eval.inflowAlert() + "," + unstable.size() + ","
                    + String.join(";", unstable) + "," + events);
        }
        return rows;
    }

    /** 알림 행 (서버가 같은 초에 AlertStore.issue에 넘기는 순서). cell_ids는 ;로 잇는다. */
    static List<String> alertRows(List<ZoneStep> steps) {
        List<String> rows = new ArrayList<>();
        for (ZoneStep step : steps) {
            for (AlertEvent alert : step.alerts()) {
                rows.add(step.evaluation().t() + "," + alert.reason() + "," + alert.level() + ","
                        + text(alert.value()) + "," + String.join(";", alert.cellIds()));
            }
        }
        return rows;
    }

    /** 머리줄 + 행을 UTF-8·LF로 쓴다. 폴더가 없으면 만든다. 실패하면 UncheckedIOException(한국어 메시지). */
    static void write(Path file, String header, List<String> rows) {
        StringBuilder text = new StringBuilder(header).append('\n');
        rows.forEach(row -> text.append(row).append('\n'));
        try {
            Path parent = file.toAbsolutePath().getParent();
            Files.createDirectories(parent);
            Files.writeString(file, text, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException("CSV를 쓸 수 없습니다: " + file.toAbsolutePath(), e);
        }
        log.info("저장 {} ({}행)", file, rows.size());
    }

    /** 숫자 칸. null은 빈칸, 아니면 Double.toString. */
    private static String text(Double value) {
        return value == null ? "" : value.toString();
    }

    /** 파일 이름에서 마지막 확장자를 뺀 것. */
    private static String stem(Path timeline) {
        String name = timeline.getFileName().toString();
        int dot = name.lastIndexOf('.');
        return dot > 0 ? name.substring(0, dot) : name;
    }
}
