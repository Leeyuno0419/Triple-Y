# 서버 API 명세 (초안 v0.2)

## 문서 상태

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 (v0.1·v0.2) |
| 작성자 | 조영준 (Claude 작성 보조) |
| 상태 | 초안 v0.2 (11-11). 팀 결정 4·6·7·9와 타임라인 v0.2(`count`, `counterflow`), 조영준 결정(느린 화면·허용 출처·null 관측·v0.2 검증·유입 평균) 반영. 나예린(화면)·이유노(타임라인) 검토 전 |
| 기준 문서 | `docs/timeline-spec.md` v0.2 (파일 규격), `docs/decisions-2026-11-11.md` (팀 결정 4·6·7·9), `docs/plans/server_impl_plan.md` 결정 기록 1·2·4·7·8 (조영준 결정: 느린 화면, 허용 출처, null 관측, v0.2 검증, 유입 평균), `docs/proposal.md` v3.1 3.2·4.3·5.1, `docs/server-alignment.md` Q2~Q6 |
| 범위 | Spring Boot ↔ React 상황실 화면. `timeline-spec.md` 9절 6·7번(결정됨)의 세부 |

- 표기는 `docs/proposal-guide.md`를 따른다. 팀이 정하지 않은 값은 `(가정)`, 합의가 필요한 것은 `[토론]`이다.
- v0.1 → v0.2 변경: `zone_state`에 `zone.count`·`cells[].counterflow` 추가, 판정 대상 셀 2㎡ 이상(결정 4), 유입 경보 `count` 3명 미만 제외(결정 6), 유입 5초 평균은 non-null 3개 이상일 때(결정 기록 8), E8 기준(결정 9), `GRADE_UP` 재전송 규칙, `INFLOW`의 `value`는 5초 평균, `INSTABILITY`는 구역 단위, 없는 구역은 닫기 코드 `4404`, `hello.schema_version`은 API 메시지 버전, 반복 재생 신호, 느린 화면 처리, 허용 출처 패턴, 설정 파일 갱신.

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
- 개발 허용 출처(CORS): `http://localhost:*`, `http://127.0.0.1:*` 패턴 (Vite 5173 포함). WebSocket과 REST(`/api/**`) 모두 같은 값을 쓴다. 값은 설정 `crowdsight.cors-origin-patterns`에 둔다. 운영은 같은 출처로 배포한다 (가정).

## 3. WebSocket 메시지 (서버 → 화면)

### 3.1 `hello` (접속 직후 1번, 재접속 때마다)

```json
{
  "type": "hello",
  "schema_version": "0.2",
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

- `schema_version`은 이 API 메시지의 버전이다. 타임라인 파일의 `schema_version`과 별개다.
- 화면은 `meta`로 히트맵 셀을 그린다. `GET /meta`를 따로 부르지 않아도 된다.
- `thresholds`는 표시용(범례·그래프 기준선)이다. 판정은 서버가 한다.
- 재접속하면 미확인 알림을 `unacked_alerts`로 다시 받는다.
- 없는 구역으로 접속하면 서버는 닫기 코드 `4404` (`unknown zone`)로 연결을 닫는다. 닫기 코드는 WebSocket을 닫을 때 이유를 알리는 숫자다. 4000~4999는 응용이 정해 쓴다.

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
    "inflow_alert": false,
    "count": 13.8
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
      "counterflow": 0.12,
      "density_pred_60s": 4.6,
      "grade_pred_60s": "ALERT"
    }
  ]
}
```

- `cells[]`의 측정·예측 필드는 타임라인 `frames[].cells[]`를 그대로 옮긴다. 서버는 `grade`와 `grade_pred_60s`만 더한다.
- `zone.count`는 타임라인 `frames[].count`(구역 인원) 그대로다.
- v0.1 타임라인 파일에는 `count`와 `cells[].counterflow`가 둘 다 없다. 서버는 둘 다 `null`로 읽어 보낸다.
- v0.2 타임라인 파일은 두 키가 반드시 있어야 한다(값은 `null` 가능). 없으면 서버가 파일을 거부한다 (`src/predict/schema.py`와 같은 규칙, 결정 기록 7).
- `zone.inflow_ratio`는 타임라인 값 그대로다. `inflow_alert`는 최근 5초 평균으로 판정한다 (4.4절).
- 값이 `null`이면 그대로 `null`로 보낸다 (`timeline-spec.md` 5절). 키는 빼지 않는다. 화면은 "관측 불가"로 표시한다.
- `max_density`는 판정 대상 셀 중 최대 밀도다 (4.2절). 대상 셀이 없으면 `null`이다.
- 판정 대상이 아닌 작은 셀도 자기 `grade`를 계산해 `cells[]`로 보낸다.

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
| `INFLOW` | 유입 경보가 켜질 때 (4.4절) | `CAUTION` | `inflow_ratio` 최근 5초 평균 |
| `INSTABILITY` | 판정 대상 셀 중 하나라도 불안정이 될 때 (4.3절, 구역 단위) | `CRITICAL` | 불안정 셀의 최대 `pressure` |

- `t`·`frame_ts`는 같은 초에 보낸 `zone_state`와 같다. 한 초 안에서는 `zone_state` 다음에 `alert`가 온다.
- `GRADE_UP` 재전송: 구역 등급이 경계 이상이고 이번 사건에서 보낸 가장 높은 단계보다 높을 때만 보낸다. 구역 등급이 경계 아래로 내려가면 사건이 끝나고, 다시 경계로 오르면 새로 보낸다.
    - 예: 구역 등급 정상, 주의, 경계, 심각, 경계, 심각, 주의, 경계 → 3번째(경계)·4번째(심각)·8번째(경계)에 보낸다.
- `cell_ids` (`meta.cells` 순서):
    - `GRADE_UP`: 판정 대상 셀 중 등급이 `level` 이상인 셀.
    - `INSTABILITY`: 불안정이 된 판정 대상 셀 (가정).
    - `INFLOW`: 빈 목록 `[]` (가정). 구역 단위 경보다.
- `INFLOW`·`INSTABILITY`는 조건이 해제되기 전에는 다시 보내지 않는다.
- 불안정은 알림을 둘 다 만든다. 불안정이 된 초(예: t2)에 `INSTABILITY`, 등급 올림 2초 확인 뒤(예: t3)에 `GRADE_UP`(심각)이 온다. 하나로 줄일지는 `[토론]`이다 (10절 9번).
- 주의로 오르는 것은 알림 없이 `zone_state`의 등급만 바꾼다 (기획서 3.2: 주의 = 히트맵 표시).

### 3.4 `playback` (재생 상태가 바뀔 때)

```json
{ "type": "playback", "zone_id": "zone-e04-039", "state": "paused", "t": 130, "loop": true }
```

- `state`: `playing`, `paused`, `ended`.
- 이동(seek)하면 이 메시지 다음에 새 `t`의 `zone_state`가 온다.
- 반복 재생으로 처음(0)으로 돌아가면 `{ "state": "playing", "t": 0 }`인 `playback`을 먼저 보내고, 그다음 `t: 0`의 `zone_state`를 보낸다. 화면은 이 메시지를 받으면 쌓아 둔 프레임(그래프·이력)을 비운다.

### 3.5 연결 유지와 재접속

- 서버는 30초마다 WebSocket ping 프레임을 보낸다 (브라우저가 자동 응답). ping 프레임은 연결이 살아 있는지 확인하는 제어 신호다. 화면 코드에는 보이지 않는다.
- 화면은 끊기면 1초, 2초, 5초, 이후 5초 간격으로 다시 접속한다. 다시 접속하면 `hello`부터 다시 받는다.
- 느린 화면: 한 세션에 보내기가 2초 넘게 막히면 서버는 그 세션만 닫는다 (Tomcat 차단 전송 제한 2초). 차단 전송 제한은 메시지 한 개를 보내며 기다리는 최대 시간이다. 다른 접속자와 재생은 계속된다. 화면은 재접속해 `hello`로 상태를 복구한다.
- 한 세션에 보내지 못하고 쌓인 메시지가 512KB(`ws.buffer-size-limit-bytes`)를 넘어도 그 세션을 닫는다.
- 닫기 코드 `4404`를 받으면 재접속해도 같은 결과다. 재접속을 멈출지는 10절에서 정한다 `[토론]`.

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

- 셀마다 "현재 등급"을 기억한다. 시작 등급은 정상이다.
- **올림**: 최근 **2초** 관측 등급이 모두 현재보다 높으면, 그 2초 중 낮은 쪽 등급으로 바로 올린다 (기획서 3.2, 가정).
    - 예: 4.1, 3.9, 4.1, 4.1 → 정상, 주의, 주의, 경계. 5.5, 5.5 → 정상, 심각 (단계를 건너뛸 수 있다).
- **내림**: 관측 등급이 현재보다 낮은 상태가 **10초 연속**이면 **한 단계만** 내린다. 다시 10초가 지나야 또 내린다.
- 서버는 `density`가 `null`인 타임라인 파일을 거부한다. 그래도 `null` 관측이 들어오면 그 초는 건너뛴다 (방어용). 현재 등급을 유지하고, 연속 횟수도 끊지 않는다. `density` `null` 셀을 허용할지는 `[토론]`이다.
- 구역 등급 = 판정 대상 셀 등급 중 최댓값이다 (결정 4). 대상 셀이 없으면 정상이다.
    - 판정 대상: `walkable_area_m2 ≥ 2.0`인 셀 (결정 4). 면적이 작은 셀은 오탐 1개로도 밀도가 튄다 (E04_039 오른쪽 위 1.17㎡ 셀이 사람 없이 0.3~0.6).
- 예측 등급 `grade_pred_60s`는 `density_pred_60s`에 4.1절 기준만 적용한다. 히스테리시스는 쓰지 않는다. `density_pred_60s`가 `null`이면 `null`이다.
- 이동(seek)이나 반복 재생으로 `t`가 불연속이 되면 모든 셀의 상태를 초기화한다.
- 반복·이동 때 불안정 연속 횟수, 유입 5초 평균·경보, 알림 사건 상태도 초기화한다. 그래서 반복할 때마다 같은 알림이 다시 온다 (가정).

### 4.3 불안정 → 심각

- 셀 `pressure`가 `thresholds.pressure`(0.02/s², 가정)를 **3초 연속** 넘으면 그 셀을 심각 조건으로 본다.
- 셀 관측 등급 = 밀도 등급과 (불안정이면 심각) 중 높은 쪽. 여기에 4.2절 히스테리시스를 적용한다.
- 조사 결과 0.02/s²는 측정 방법에 따라 달라 그대로 쓰기 어렵다 (`docs/research/crowd_turbulence_research.md`). 기준값은 E5 결과로 바꾼다 `[토론]`.
- `pressure`가 `null`이거나 기준 이하이면 연속 횟수를 0으로 되돌린다.
- `counterflow`는 화면에 전달만 하고 판정에는 쓰지 않는다. 불안정 판정에 넣을지는 `[토론]`이다.
- `timeline-spec.md` v0.2 4절은 `counterflow`를 불안정 판정(이 문서 4.3)에 쓴다고 적었다. MVP에서는 쓰지 않으므로, 이유노 님께 규격 문구를 맞춰 달라고 요청한다 `[토론]`.

### 4.4 유입 경보

- **켬**: 구역 `inflow_ratio`의 최근 5초 평균이 `thresholds.inflow_ratio`(0.6, 가정)를 넘고, 구역 인원 `count`가 3명 이상일 때 (결정 6).
- 5초 평균은 최근 5초 값 중 `null`이 아닌 값이 3개(`inflow.min-samples`) 이상이면 그 값들의 평균이다. 3개 미만이면 평균은 `null`이고 조건은 거짓이다 (결정 기록 8, 가정). 흐름 모듈은 경계에 움직이는 사람이 적으면 `inflow_ratio`를 `null`로 쓰므로, 5개를 모두 요구하면 경보가 거의 켜지지 않는다.
    - 예: 0.7, `null`, 0.8, 0.7, 0.9 → 평균 (0.7 + 0.8 + 0.7 + 0.9) / 4 = 0.775.
    - 평균은 창이 다 찬 뒤에만 낸다. 재생 시작이나 초기화(반복·이동, 4.2절) 뒤 5초 관측이 쌓이기 전에는 평균이 `null`이다. 초기화 뒤 첫 평균은 `t` 4다 (결정 기록 8).
- `count`가 `null`이거나 키가 없으면 켜지 않는다.
- **끔**: 위 조건이 10초 연속 거짓이면 끈다. 평균이 `null`인 초, `count` 3명 미만인 초, `count`가 `null`인 초도 거짓으로 센다 (가정).
- 보완 배경: 경계에 사람이 적으면 몇 명만 들어와도 비율이 튄다 (`timeline-spec.md` 9절 2번).

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

- E8 기준 (결정 9): 기획서 "1초 분량 처리 ≤ 1초"를 둘로 나눈다.
    - (가) 사전 분석 처리 시간: 기록·공개만 한다 (현재 3분 영상에 약 8분 반). 판정 기준이 아니다.
    - (나) 판정 기준: 재생 중 판정 → 알림 **p95 ≤ 5초**, **30분 반복 재생 무중단**.
- 화면은 메시지를 받은 시각과 `frame_ts`의 차이를 기록한다.
- 시연은 서버와 화면이 같은 PC에서 돌아 시계가 같다 (가정). 다른 PC면 두 PC를 같은 NTP 서버에 맞춘다.
- 기록 위치는 화면의 개발자 도구 또는 화면이 내보내는 CSV다 `[토론]`.
- `frame_ts`는 서버가 보낸 시각이다. 이것만 쓰면 히스테리시스 확인 지연(밀도 +1초, 불안정 +2~3초)이 빠져 거의 0초가 나온다.
- 측정 시작점을 `alert`의 `onset_t`·`onset_ts`로 할지 `[토론]`이다. `onset_t`는 조건이 처음 충족된 초, `onset_ts`는 그 초를 재생한 시각이다 (`docs/research/server_research.md` 1.5절).
- 정하기 전에는 이 필드를 넣지 않는다.

## 8. 서버 설정 (`application.yml`, 가정 값)

```yaml
spring:
  application:
    name: crowdsight-server
  jackson:
    property-naming-strategy: SNAKE_CASE
server:
  port: 8080

crowdsight:
  timeline-dir: ../data/processed/timeline   # bootRun 작업 폴더가 server/. 환경변수 CROWDSIGHT_TIMELINE_DIR로 바꿈
  timeline-files: [E04_039.json]
  time-zone: Asia/Seoul
  replay:
    interval-ms: 1000
    loop: true
  grade:
    density: { caution: 3.0, alert: 4.0, critical: 5.0 }
    up-seconds: 2
    down-seconds: 10
    min-walkable-area-m2: 2.0                # 결정 4
  instability:
    pressure: 0.02                           # 가정, E5 결과로 조정
    seconds: 3
  inflow:
    ratio: 0.6
    window-seconds: 5
    min-samples: 3                           # 결정 기록 8, 5초 중 non-null 값 개수 하한
    off-seconds: 10
    min-count: 3                             # 결정 6
  ws:
    ping-interval-ms: 30000
    send-time-limit-ms: 2000
    buffer-size-limit-bytes: 524288
  alert-log: logs/alerts.jsonl               # server/logs/, git 제외
  cors-origin-patterns: ["http://localhost:*", "http://127.0.0.1:*"]
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

- 상세는 `docs/research/server_research.md` 4절 (`liveFeed.ts` 확인 결과, 4404 무시·재접속 최대 15초 등).

## 10. 미결 안건 `[토론]`

| 번호 | 안건 | 초안 | 함께 정할 사람 |
|---|---|---|---|
| 1 | 구역 등급을 셀 최댓값으로 할지, 경계 이상 셀이 N개 이상일 때로 할지 | **닫힘 (결정 4)**: 보행 면적 2㎡ 이상 셀 등급의 최댓값 (4.2절) | 이유노 |
| 2 | 0.02/s² 불안정 기준과 3초 지속 | E5 결과로 조정 | 이유노 |
| 3 | 유입 경보 기준 0.6과 사람 수 보완 | **닫힘 (결정 6)**: 5초 평균, `count` 3명 미만이면 끔 (4.4절) | 조영준 |
| 4 | 재생 상태를 접속자마다 따로 둘지 | 구역마다 하나 (공용 화면) | 나예린 |
| 5 | 지연 기록 방식 (콘솔·CSV) | CSV 내보내기 | 나예린, 이유노 |
| 6 | `inflow_ratio` 산출 방식 (흐름 모듈) | **닫힘 (`timeline-spec.md` 9절 1번)**: 구역 전체 비율 하나로 저장 | 조영준 (흐름) |
| 7 | `density` `null` 셀을 허용할지 | 지금은 파일 거부, 히스테리시스는 `null` 관측 건너뜀 (4.2절) | 이유노 |
| 8 | 불안정 판정에 `counterflow`를 넣을지 | 넣지 않고 전달만 (4.3절) | 이유노 |
| 9 | 불안정이 `INSTABILITY`와 `GRADE_UP`(심각) 알림을 둘 다 만드는 것 | 명세대로 둘 다 보냄 | 이유노, 나예린 |
| 10 | E8 측정 시작점 (`onset_t`·`onset_ts` 추가), 히스테리시스 지연 포함 여부, 30분 실행 시점 | `frame_ts` 기준 유지, 추가는 합의 뒤 (7절) | 이유노 |
| 11 | mock 서버를 새 형식으로 갱신할 담당 | 갱신하거나 11-13부터 실제 서버에 연결 | 나예린 |
| 12 | 반복 재생 신호로 `playback`(`playing`, `t: 0`)을 쓰고 화면이 프레임을 비우는 것 | 3.4절 방식 | 나예린 |
| 13 | 화면이 만드는 예측(forecast) 알림을 유지할지 | 서버 `alert`만 쓰는 쪽 검토 | 나예린 |
| 14 | 재접속 최대 간격 (지금 화면 15초, 명세 5초) | 5초 (3.5절) | 나예린 |
| 15 | 닫기 코드 `4404`를 받으면 재접속을 멈출지 | 멈추고 오류 표시 | 나예린 |
| 16 | 서버 CORS(허용 출처 패턴)와 Vite `server.proxy`(`/api`, `/ws`) 중 무엇을 쓸지 | 서버 CORS (2절) | 나예린 |
| 17 | 2㎡ 기준이 가짜 E04_039에서 가장 붐비는 왼쪽 열(1.0~1.2㎡)을 판정에서 뺀다 | 실제 셀 면적을 확인한 뒤 기준 유지 여부 결정 | 이유노 |
| 18 | 화면 변경(9절)과 11-13 1차 연결 범위 | `hello`·`zone_state`부터 | 나예린 |
| 19 | 유입 5초 평균에 `null`이 섞일 때 (5개 모두 요구 vs 일부 허용) | **닫힘 (결정 8, 구현 계획 결정 기록 8)**: 창(5초)이 다 찬 뒤 non-null 3개 이상이면 평균 (4.4절) | 조영준 |
