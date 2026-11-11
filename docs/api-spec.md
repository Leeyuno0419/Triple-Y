# 서버 API 명세 (초안 v0.1)

## 문서 상태

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 |
| 작성자 | 조영준 (Claude 작성 보조) |
| 상태 | 초안. 나예린(화면)·이유노(타임라인) 검토 전 |
| 기준 문서 | `docs/timeline-spec.md` v0.1 (파일 규격), `docs/proposal.md` 3.2·4.3·5.1, `docs/server-alignment.md` Q2~Q6 |
| 범위 | Spring Boot ↔ React 상황실 화면. `timeline-spec.md` 8절 6·7번 안건의 답 |

- 표기는 `docs/proposal-guide.md`를 따른다. 팀이 정하지 않은 값은 `(가정)`, 합의가 필요한 것은 `[토론]`이다.

---

## 1. 원칙

- 서버는 `data/processed/timeline/{video_id}.json`을 읽어 1초마다 재생한다. 분석은 하지 않는다.
- 등급과 알림은 서버만 판정한다. 화면은 받은 등급을 그대로 표시한다.
- 서버 → 화면은 **순수 WebSocket + JSON** 하나다. 화면 → 서버 요청은 **REST**로 한다.
    - STOMP 대신 순수 WebSocket을 고른 이유: 구역 1개·1Hz 방송·알림뿐이라 STOMP 라우팅의 이점이 작고, 대시보드가 이미 순수 WebSocket을 쓴다. 구역 동시 구독이나 사용자별 알림이 필요해지면 STOMP로 옮긴다.
- 모든 메시지는 `type` 필드로 구분한다. 모르는 `type`은 화면이 무시한다 (뒤 호환).
- 시각은 두 가지다.
    - `t`: 영상 시작 뒤 경과 초(정수). 타임라인의 `frames[].t`와 같다.
    - `frame_ts`: 서버가 그 초를 보낸 시각. ISO 8601, 밀리초, `+09:00`. 지연(E8) 측정용이다.
- 개인정보: 메시지에는 타임라인에 있는 셀·구역 집계값만 싣는다.

## 2. 엔드포인트 요약

| 방식 | 경로 | 하는 일 |
|---|---|---|
| WebSocket | `/ws/zones/{zone_id}` | 접속 시 `hello`, 이후 1초마다 `zone_state`, 사건 때 `alert`·`playback` |
| GET | `/api/zones` | 재생 가능한 구역 목록 |
| GET | `/api/zones/{zone_id}/meta` | 타임라인 `meta` 그대로 (셀 목록·`image_polygon`) |
| POST | `/api/zones/{zone_id}/playback` | 재생 제어: 재생·일시정지·이동·반복 |
| GET | `/api/zones/{zone_id}/alerts?unacked=true` | 알림 목록 (미확인만 선택 가능) |
| POST | `/api/alerts/{alert_id}/ack` | 알림 확인. 확인 기록을 로그 파일에 남긴다 |
| GET | `/api/health` | 서버 상태 (재생 중 구역, 현재 `t`) |

- 경로 앞에는 `/api`, WebSocket은 `/ws`를 쓴다.
- 개발 CORS 허용: `http://localhost:5173` (Vite). 운영은 같은 출처로 배포한다 (가정).

## 3. WebSocket 메시지 (서버 → 화면)

### 3.1 `hello` (접속 직후 1번, 재접속 때마다)

```json
{
  "type": "hello",
  "schema_version": "0.1",
  "zone_id": "zone-e04-039",
  "meta": { "...": "timeline-spec.md 3절의 meta 그대로" },
  "playback": { "state": "playing", "t": 57, "loop": true, "duration_s": 180 },
  "thresholds": {
    "density": { "caution": 3.0, "alert": 4.0, "critical": 5.0 },
    "pressure": 0.02,
    "inflow_ratio": 0.6
  },
  "unacked_alerts": [ { "...": "3.3 alert 형식" } ]
}
```

- 화면은 `meta`로 히트맵 셀을 그린다. `GET /meta`를 따로 부르지 않아도 된다.
- `thresholds`는 표시용(범례·그래프 기준선)이다. 판정은 서버가 한다.
- 재접속하면 미확인 알림을 `unacked_alerts`로 다시 받는다.

### 3.2 `zone_state` (1초마다)

```json
{
  "type": "zone_state",
  "zone_id": "zone-e04-039",
  "t": 120,
  "frame_ts": "2026-11-18T14:02:31.512+09:00",
  "zone": {
    "grade": "ALERT",
    "max_density": 4.3,
    "inflow_ratio": 0.42,
    "inflow_alert": false
  },
  "cells": [
    {
      "cell_id": "c-0412",
      "grade": "ALERT",
      "density": 4.3,
      "vx": 0.21,
      "vy": -0.05,
      "speed_var": 0.006,
      "pressure": 0.0258,
      "density_pred_60s": 4.6,
      "grade_pred_60s": "ALERT"
    }
  ]
}
```

- `cells[]`의 측정·예측 필드는 타임라인 `frames[].cells[]`를 그대로 옮긴다. 서버는 `grade`와 `grade_pred_60s`만 더한다.
- 값이 `null`이면 그대로 `null`로 보낸다 (`timeline-spec.md` 5절). 화면은 "관측 불가"로 표시한다.
- `max_density`는 판정 대상 셀 중 최대 밀도다 (4.2절).

### 3.3 `alert` (사건이 생길 때)

```json
{
  "type": "alert",
  "alert_id": "a-20261118-0007",
  "zone_id": "zone-e04-039",
  "t": 121,
  "frame_ts": "2026-11-18T14:02:32.508+09:00",
  "level": "ALERT",
  "reason": "GRADE_UP",
  "message": "구역 등급이 주의 → 경계로 올랐다",
  "value": 4.3,
  "cell_ids": ["c-0412", "c-0413"]
}
```

| `reason` | 언제 | `level` | `value` |
|---|---|---|---|
| `GRADE_UP` | 구역 등급이 경계·심각으로 오를 때 | 오른 등급 | 최대 밀도 |
| `INFLOW` | 유입 경보가 켜질 때 (4.4절) | `CAUTION` | `inflow_ratio` |
| `INSTABILITY` | 불안정 지표가 기준을 넘을 때 (4.3절) | `CRITICAL` | 최대 `pressure` |

- 같은 `reason`의 알림은 조건이 해제되기 전에는 다시 보내지 않는다.
- 주의로 오르는 것은 알림 없이 `zone_state`의 등급만 바꾼다 (기획서 3.2: 주의 = 히트맵 표시).

### 3.4 `playback` (재생 상태가 바뀔 때)

```json
{ "type": "playback", "zone_id": "zone-e04-039", "state": "paused", "t": 130, "loop": true }
```

- `state`: `playing`, `paused`, `ended`.
- 이동(seek)하면 이 메시지 다음에 새 `t`의 `zone_state`가 온다.

### 3.5 연결 유지와 재접속

- 서버는 30초마다 WebSocket ping 프레임을 보낸다 (브라우저가 자동 응답).
- 화면은 끊기면 1초, 2초, 5초, 이후 5초 간격으로 다시 접속한다. 다시 접속하면 `hello`부터 다시 받는다.

## 4. 등급·알림 판정 (서버)

### 4.1 등급

| 코드 | 화면 표기 | 셀 조건 (명/㎡) | 상황실 (기획서 3.2) |
|---|---|---|---|
| `NORMAL` | 정상 | ρ < 3 | 표시만 |
| `CAUTION` | 주의 | 3 ≤ ρ < 4 | 히트맵 강조 |
| `ALERT` | 경계 | 4 ≤ ρ < 5 | 알림 |
| `CRITICAL` | 심각 | ρ ≥ 5, 또는 불안정 조건(4.3) | 비상 알림 |

- 화면 표기는 기획서 기준 **경계**로 통일한다. 대시보드의 "경고"는 "경계"로 바꾼다.
- 기준값은 서버 설정(`application.yml`)에 둔다. 바꿔도 분석을 다시 돌리지 않는다 (`timeline-spec.md` 7절).

### 4.2 히스테리시스 (등급이 깜빡이지 않게)

- 셀마다 "현재 등급"을 기억한다.
- **올림**: 조건 등급이 현재보다 높은 상태가 **2초 연속**이면 그 등급으로 바로 올린다 (기획서 3.2, 가정).
- **내림**: 조건 등급이 현재보다 낮은 상태가 **10초 연속**이면 **한 단계만** 내린다. 다시 10초가 지나야 또 내린다.
- `density`가 `null`인 초는 연속 횟수를 세지 않고 현재 등급을 유지한다.
- 구역 등급 = 판정 대상 셀 등급 중 최댓값이다 `[토론]`.
    - 판정 대상: `walkable_area_m2 ≥ 1.0`인 셀 (가정). 면적이 아주 작은 셀은 한 사람만 있어도 밀도가 튄다.
- 예측 등급 `grade_pred_60s`는 `density_pred_60s`에 4.1절 기준만 적용한다. 히스테리시스는 쓰지 않는다.
- 이동(seek)이나 반복 재생으로 `t`가 불연속이 되면 모든 셀의 상태를 초기화한다.

### 4.3 불안정 → 심각

- 셀 `pressure`가 `thresholds.pressure`(0.02/s², 가정)를 **3초 연속** 넘으면 그 셀을 심각 조건으로 본다.
- 조사 결과 0.02/s²는 측정 방법에 따라 달라 그대로 쓰기 어렵다 (`docs/research/crowd_turbulence_research.md`). 기준값은 E5 결과로 바꾼다 `[토론]`.
- `pressure`가 `null`이면 불안정 조건을 판정하지 않는다.

### 4.4 유입 경보

- 구역 `inflow_ratio`의 최근 5초 평균이 `thresholds.inflow_ratio`(0.6, 가정)를 넘으면 켠다. 10초 연속 기준 미만이면 끈다.
- 약점: 경계에 사람이 적으면 몇 명만 들어와도 비율이 튄다 (`timeline-spec.md` 8절 2번). 판정 대상 셀의 밀도 합이 일정 이상일 때만 켜는 보완을 검토한다 `[토론]`.

### 4.5 알림 확인 기록

- `POST /api/alerts/{alert_id}/ack`를 받으면 `logs/alerts.jsonl`에 한 줄을 추가한다. `logs/`는 git에 올리지 않는다 (가정).

```json
{"alert_id":"a-20261118-0007","zone_id":"zone-e04-039","t":121,"level":"ALERT","reason":"GRADE_UP","sent_at":"2026-11-18T14:02:32.508+09:00","acked_at":"2026-11-18T14:02:36.910+09:00"}
```

- 응답: `200 {"alert_id": "...", "acked_at": "..."}`. 이미 확인한 알림이면 `200`과 처음 확인 시각을 돌려준다. 없는 ID면 `404`.
- DB는 쓰지 않는다 (기획서 5.1: 로그 파일). 서버를 재시작하면 미확인 알림 목록은 비워진다 (가정).

## 5. 재생 제어 (REST)

`POST /api/zones/{zone_id}/playback`

```json
{ "action": "seek", "t": 90 }
```

| `action` | 추가 필드 | 동작 |
|---|---|---|
| `play` | | 현재 `t`부터 1초마다 재생 |
| `pause` | | 멈춘다. 연결은 유지된다 |
| `seek` | `t` (0 ≤ t < `duration_s`) | 그 초로 이동하고 판정 상태를 초기화한다 |
| `loop` | `enabled` (bool) | 끝에 닿으면 처음부터 다시 재생 (E8 30분 무중단 시험) |

- 응답: `200` + 현재 재생 상태(`playback` 메시지와 같은 내용). 잘못된 `t`는 `400`.
- 재생 상태는 구역마다 하나이고 모든 접속자가 같은 화면을 본다 (상황실 공용 화면, 가정).

## 6. 영상과 히트맵 시간 맞춤

- 영상 파일은 서버가 아니라 화면이 시연 PC에서 직접 연다 (`timeline-spec.md` 7절). `meta.video_id`로 파일을 찾는다.
- 화면은 `zone_state`를 받을 때마다 `|video.currentTime − t| > 1.0초`이면 `video.currentTime = t`로 맞춘다 (가정).
- 일시정지·이동은 `playback` 메시지를 따라 영상도 같이 멈추거나 옮긴다.

## 7. 지연 측정 (E8, 판정→알림 p95 ≤ 5초)

- 화면은 메시지를 받은 시각과 `frame_ts`의 차이를 기록한다.
- 시연은 서버와 화면이 같은 PC에서 돌아 시계가 같다 (가정). 다른 PC면 두 PC를 같은 NTP 서버에 맞춘다.
- 기록 위치는 화면의 개발자 도구 또는 화면이 내보내는 CSV다 `[토론]`.

## 8. 서버 설정 (`application.yml`, 가정 값)

```yaml
crowdsight:
  timeline-dir: data/processed/timeline
  replay:
    interval-ms: 1000
    loop: true
  grade:
    density: { caution: 3.0, alert: 4.0, critical: 5.0 }
    up-seconds: 2
    down-seconds: 10
    min-walkable-area-m2: 1.0
  instability:
    pressure: 0.02
    seconds: 3
  inflow:
    ratio: 0.6
    window-seconds: 5
    off-seconds: 10
  alert-log: logs/alerts.jsonl
  cors-origins: [http://localhost:5173]
```

## 9. 화면(대시보드)에 미치는 영향

| 지금 (`web/src/lib/liveFeed.ts` 가정) | 이 명세 | 바꿀 곳 |
|---|---|---|
| `{type: "timeline"}`로 전체 상태 | `hello` (`meta`, 재생 상태, 기준값, 미확인 알림) | `parseLiveMessage` |
| `{type: "frames"}`에 관측 + 예측 프레임 | `zone_state` 1개에 관측값과 `density_pred_60s`가 같이 | 예측은 어댑터가 `t+60`으로 펼친다 (`server-alignment.md` 5장) |
| 화면이 임계값으로 등급 판정 | 서버 `grade` 사용 | `density.ts` |
| 화면이 알림을 만든다 | 서버 `alert` 수신, 확인은 REST | `alerts.ts` |
| 격자 `rows × cols` | `cell_id` 목록 + `row`·`col` + `image_polygon` | 어댑터 |
| 3단계 "경고" | "경계" | 표기 |

## 10. 미결 안건 `[토론]`

| 번호 | 안건 | 초안 | 함께 정할 사람 |
|---|---|---|---|
| 1 | 구역 등급을 셀 최댓값으로 할지, 경계 이상 셀이 N개 이상일 때로 할지 | 최댓값 + 작은 셀 제외 | 이유노 |
| 2 | 0.02/s² 불안정 기준과 3초 지속 | E5 결과로 조정 | 이유노 |
| 3 | 유입 경보 기준 0.6과 사람 수 보완 | 5초 평균, 밀도 합 보완 검토 | 나예린 |
| 4 | 재생 상태를 접속자마다 따로 둘지 | 구역마다 하나 (공용 화면) | 나예린 |
| 5 | 지연 기록 방식 (콘솔·CSV) | CSV 내보내기 | 나예린, 이유노 |
| 6 | `inflow_ratio` 산출 방식 (흐름 모듈) | 화각 경계 셀에서 안쪽 방향 속도 성분이 양수인 비율 | 조영준 (흐름) |
