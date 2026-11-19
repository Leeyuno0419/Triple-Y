# E8 알림 화면 표시 지연 (브라우저)

- 측정: 2026-11-19 12:37~12:44 (KST), 같은 PC의 localhost (서버와 브라우저 시계가 같다)
- 구성: 서버 `main` `46421ac` (`--crowdsight.timeline-files=E04_039.json,E05_035.json,E05_038.json`), 화면 `web/` Vite 개발 서버, Chrome
- 측정 코드: #65 `web/src/lib/renderLatency.ts`가 브라우저 콘솔에 남긴 `[G2-latency]` 로그
- 판정 (G2, 알림 5초 이내 화면 표시): **통과**. 화면 쪽 지연이 대부분 수십 ms라, 서버 측정 p95 4.0초에 더해도 5초 안이다.

## 결과: 서버가 보낸 시각 → 화면에 그려진 시각
| 구역 | 알림 | 화면 표시까지 (ms) | 수신까지 (ms) | 그리기 (ms) | 비고 |
|---|---|---|---|---|---|
| zone-e04-039 | INFLOW/CAUTION t=56 | 16 | 5 | 11 | |
| zone-e04-039 | INFLOW/CAUTION t=78 | 20 | 7 | 13 | |
| zone-e05-038 | INFLOW/CAUTION t=4 | 75 | 24 | 51 | |
| zone-e05-038 | INFLOW/CAUTION t=29 | 299 | 6 | 293 | |
| zone-e05-038 | INFLOW/CAUTION t=4 | 2,291 | 7 | 2,284 | 창이 6.5초 가려짐 (아래 참고) |
| zone-e05-038 | INFLOW/CAUTION t=29 | 37 | 8 | 29 | |
| zone-e05-038 | INFLOW/CAUTION t=4 | 36 | 9 | 27 | |

- 7건 모두 5초 이내. 창이 가려진 1건을 빼면 최대 299 ms, 중앙값 37 ms.
- 수신까지 = WebSocket으로 받은 시각 − `frame_ts`. 그리기 = 알림 행이 DOM에 들어가고 브라우저가 한 번 그린 시각 − 받은 시각.

## 조건 충족부터 화면 표시까지 (합산)
| 구역 | 조건 충족 → 서버 전송, INFLOW p95 (11-17 E8) | 서버 전송 → 화면 (이번 최대) | 합 |
|---|---|---|---|
| zone-e04-039 | 4,001 ms | 20 ms | 약 4.0초 |
| zone-e05-038 | 4,002 ms | 299 ms | 약 4.3초 |

- 앞부분은 판정 규칙이 기다리는 시간이다(유입은 5초 평균 창). 시작점 정의는 `docs/api-spec.md` 7절(#64).
- 서로 다른 날 잰 두 값을 더한 것이다. 같은 알림을 처음부터 화면까지 한 번에 잰 값은 아니다.

## 한계
- **E05_035는 재지 못했다.** 화면용 타임라인 파일이 `web/public/data/`에 없다.
- 표본이 7건(모두 유입 경보)이다. 서버 측정(30분, 289건)보다 훨씬 적다. 서버→화면 전달과 그리기는 알림 종류와 관계없이 같은 경로다.
- **Chrome 창이 다른 창에 가려지거나 최소화되면** 탭이 숨김(`document.hidden`)이 되고 그리기가 멈춘다. 그동안 온 알림은 창이 다시 보일 때 그려져 지연이 수 초~수십 초로 찍힌다. 첫 시도에서 이 때문에 5.7~100.7초가 나왔고, 위 표에서는 뺐다. 다시 잴 때는 창을 맨 앞에 두고, 백업 녹화도 창을 가리지 않고 한다.
- 접속할 때 `hello`로 받은 이전 알림은 재지 않는다(수신 시각이 없어서).

## 다시 재는 법
```bash
# 서버 (server/)
./gradlew bootRun --args='--crowdsight.timeline-files=E04_039.json,E05_035.json,E05_038.json'
# 화면 (web/), .env.local을 고치지 않고 환경변수로 구역을 고른다
VITE_WS_URL=ws://localhost:8080/ws/zones VITE_ZONE_ID=zone-e04-039 \
VITE_TIMELINE_URL=/data/E04_039.json VITE_USE_MOCK=false npx vite --port 5173
```
- 브라우저에서 `http://localhost:5173`을 열고 창을 가리지 않은 채 한 바퀴(E04_039 180초, E05 60초) 이상 둔다.
- 개발자 도구 콘솔 필터에 `G2-latency`를 넣어 로그를 본다.
