# 서버 계획 재점검 (main 병합분 반영, 11-11)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-11 |
| 작성 | Researcher 서브에이전트 (조영준 요청) |
| 비교 구간 | `1b519f0`(계획·조사 작성 기준) → `main` `99d5320` (#32~#40) |
| 점검 대상 | `docs/plans/server_impl_plan.md`(이하 "계획"), `docs/research/server_research.md`(이하 "조사"), `docs/api-spec.md` D1 초안(작업 트리), `docs/plans/server_s0_skeleton_plan.md`(이하 "S0") |

- 표기는 `docs/proposal-guide.md`를 따른다. `(가정)` 설계값, `[토론]` 팀 합의 필요, `[결정 필요]` 조영준이 정할 것.
- 확인 방법: `git log --oneline 1b519f0..main`, `git diff 1b519f0 main -- <경로>`, `git show main:<경로>`. 코드는 읽기만 했다.

---

## 0. 요약

1. **서버 규칙을 정하는 문서는 바뀌지 않았다.** `docs/timeline-spec.md`(v0.2), `docs/decisions-2026-11-11.md`, `docs/api-spec.md`(v0.1)는 `1b519f0` 뒤로 커밋이 없다. 계획은 이미 이 셋을 기준으로 썼다.
2. **기획서 v3.1(#33)은 계획과 같은 값이다.** 등급 3·4·5명/㎡, 표기 "경계", 올림 2초·내림 10초 한 단계, 구역 등급 2㎡ 이상 셀 최댓값, 유입 5초 평균 + `count` 3명 미만 제외, E8(알림 p95 ≤ 5초 + 30분 무중단, 처리 시간은 기록만). 새 `[토론]`은 없다.
3. **타임라인 v0.2가 코드에 들어왔다(#35).** `schema.py`·`validate.ts`가 `count`·`counterflow`를 읽고 쓴다. `schema_version`이 `"0.2"` 이상이면 두 키가 **반드시 있어야** 한다(값은 null 가능). `counterflow`는 0~1, `count`는 0 이상이다. 계획의 서버 검증 규칙(키 생략 항상 허용, `counterflow` 범위 검사 없음)이 이보다 느슨하다 → S1 부분 수정.
4. **예측 모듈이 `count`를 버리던 문제가 풀렸다(#35).** `fill_predictions`가 `count`를 넘기고, 생산자(`run_density.py`, `fake_timeline.py`)는 `SCHEMA_VERSION` `"0.2"`로 쓴다.
5. **화면은 v0.2를 받지만 서버 메시지는 아직 모른다.** `liveFeed.ts`·`alerts.ts`·`useLiveFeed.ts`·`mock-ws-server.mjs`는 바뀌지 않았다. 여전히 `timeline`·`frames`·`frame`만 받는다. 새로 영상 오버레이와 api-spec 6절 시간 맞춤(1.0초)이 들어왔다(#34).
6. **흐름 출력(#36·#37)은 null이 잦다.** 경계에 움직이는 머리가 적으면 `inflow_ratio`가 null, 셀 머리 수가 적으면 `pressure`가 null이다. 계획의 "5초 값이 모두 있어야 평균", "null이면 불안정 연속 0" 규칙은 실제 데이터에서 경보를 거의 못 켤 수 있다 `[토론]`. `counterflow`는 흐름 모듈이 쓰지 않아 늘 null이다.
7. **결론: 재작성은 필요 없다.** 계획·조사·D1은 부분 수정, S0은 그대로다 (5절).

---

## 1. 변경 목록 (서버에 관계있는 것만)

| PR | 파일 | 바뀐 것 | 서버 관련 |
|---|---|---|---|
| #33 | `docs/proposal.md` v3.1 | 3.2에 구역 등급 규칙(2㎡ 이상 셀 최댓값), 3.3에 유입 보완(5초 평균, `count` < 3 제외)·머리 높이 평면·5장 평균, 3.4 `timeline.json` 항목에 구역 인원·역방향 비율, E8을 "알림 p95 ≤ 5초 + 30분 무중단, 처리 시간은 기록만"으로, 6절 문서 표에 `timeline-spec.md`·`api-spec.md`·`decisions-2026-11-11.md` 추가 | 결정 4·6·9가 기획서에 들어감. 계획과 같은 값 |
| #33 | `docs/proposal-detail.md` | 평활 식을 EMA(0.3/0.7)에서 "앞뒤 0.4초 5장 평균"으로 교체, 실시간 예상 질문을 E8 결정에 맞춤 | 조사 1.4 "EMA는 옛 설계" 주석이 이제 불필요 |
| #35 | `src/predict/schema.py` | `SCHEMA_VERSION` `"0.2"`. `Frame.count`, `CellState.counterflow` 추가. 검증: v0.2 이상이면 두 키 필수, `count` ≥ 0 또는 null, `counterflow` 0~1 또는 null. 읽을 때 v0.1이면 두 필드를 None으로 채우고 버전을 `"0.2"`로 올림 | 서버 검증 규칙의 기준 (2절 #1~#3) |
| #35 | `src/predict/model.py`, `sample.py`, `io.py` | `fill_predictions`가 `count`를 넘김. 샘플도 `count` 생성 | 예측을 거쳐도 `count`가 남음 → 유입 경보 가능 |
| #35 | `web/src/types/timeline.ts` | v0.2 타입. `SCHEMA_VERSION` `'0.2'`, `SCHEMA_V02_MINOR` 2, `Frame.count`, `CellState.counterflow` | 계획 8장 #6 해결 |
| #35 | `web/src/lib/validate.ts` | `validateFrame(fr, meta, requireV02 = false)`. 파일은 버전으로 필수 여부를 정하고, **실시간 프레임은 기본값(false)으로 검사**. 반환에 `count` 포함, 빠진 `counterflow`는 null로 채움 | 서버가 `frames`형으로 보내면 `count`가 남는다. 단 화면은 아직 `zone_state`를 모른다 |
| #35 | `web/src/lib/region.ts`, `mock.ts` | 구역 인원은 프레임 `count`를 우선, 없으면 셀 합. mock도 v0.2 | `zone.count`를 화면이 쓸 곳이 생김 |
| #34 | `web/src/lib/video.ts`, `config/app.ts`, `.env.example`, `App.tsx`, `MonitorView.tsx`, `CellHeatmap.tsx` | 영상 `${VITE_VIDEO_BASE_URL}/${meta.video_id}.mp4`. 재생 중에는 영상 시각이 기준이고, `t`와 1.0초 넘게 벌어지면 영상을 `t`로 옮김(api-spec 6절 인용). 실시간에서 최신 프레임을 따라갈 때 영상 재생 | `hello.meta.video_id`가 필수로 쓰인다(계획은 meta를 그대로 보내므로 충족). `playback`(일시정지·이동)은 화면이 아직 처리하지 않음 |
| #36·#37 | `src/flow/run_flow.py`, `timeline_flow.py`, `inflow.py`, `ground.py`, `cells.py` | 흐름 필드를 규격 이름(`vx`·`vy`·`speed_var`·`pressure`, 프레임 `inflow_ratio`)으로 채움. 머리 높이 평면으로 m/s. `inflow_ratio` = 경계 셀의 움직이는 머리 중 안쪽으로 가는 비율, **소수 2자리**, 움직이는 경계 머리가 `inflow_min_heads`보다 적으면 null. 셀 머리가 `min_heads`보다 적으면 `vx`·`vy`·`speed_var`·`pressure` null(사람 없는 셀은 `pressure` 0). **`counterflow`는 쓰지 않음**(입력값 그대로). `interval_s`가 1이 아니면 거부. `allow_nan=False` | 2절 #6~#8 |
| #38~#40 | `web/src/styles.css`, `CellHeatmap.tsx`, `DebugGrid.tsx`, `AnalysisView.tsx`, `config/density.ts`, `lib/density.ts` | 격자 가시성, 제목 색, 분석 화면 지표 띠(인원·최대 밀도·등급 배지·유입 %) | 화면 표시만. 등급 배지는 여전히 화면 `levelOf`로 즉시 판정, 표기 "경고" |

바뀌지 않은 것 (서버 기준):

| 파일 | 상태 |
|---|---|
| `docs/timeline-spec.md` | v0.2 그대로 (마지막 커밋 `0404906`, `1b519f0`의 조상) |
| `docs/decisions-2026-11-11.md` | 그대로 |
| `docs/api-spec.md` | main은 v0.1 그대로. D1 초안이 main 위에서 바로 적용된다 (충돌 없음) |
| `web/src/lib/liveFeed.ts`, `alerts.ts`, `useLiveFeed.ts`, `web/scripts/mock-ws-server.mjs` | 그대로. `timeline`·`frames`·`frame`만 받음, 모르는 type throw, 닫힘 코드 무시, 재접속 1→15초, mock은 v0.1 `timeline`/`frame` |
| `src/counting/fake_timeline.py`, `run_density.py` | 코드는 그대로. 단 `schema.py`의 `SCHEMA_VERSION`을 import하므로 **출력이 이제 `"0.2"`** 이고 `count`·`counterflow` 키를 모두 쓴다 |
| 루트 `.gitignore`, `CLAUDE.md`, `README.md`, `infra/` | 그대로 |

---

## 2. 영향 표

| # | 대상 | 지금 내용 | 바뀌어야 할 것 | 심각도 |
|---|---|---|---|---|
| 1 | 계획 S1 검증 규칙 (148~154행) | `counterflow`·`count` 키 생략을 항상 허용 | `schema.py`·`validate.ts`와 같게: `schema_version` 둘째 자리 ≥ 2이면 `frames[].count`와 `cells[].counterflow` 키 필수(값 null 가능), 그 아래(v0.1)는 생략 허용. 생산자가 모두 `"0.2"`로 쓰므로 엄격하게 해도 실제 파일은 통과한다 `[결정 필요]` (엄격 권장) | 중간 |
| 2 | 계획 S1 검증 규칙 | `counterflow` 범위 검사 없음 | `counterflow`는 0~1 또는 null. `count`는 0 이상 또는 null(이미 있음) | 중간 |
| 3 | 계획 S1 테스트 표 | `loadsV01WithoutCountAndCounterflow`만 있음 | 추가: `rejectsMissingCountInV02`, `rejectsMissingCounterflowInV02`, `rejectsCounterflowOutOfRange`(1.2), `rejectsNegativeCount`(−1). 버전 둘째 자리 해석은 `schema.py` `_schema_minor`와 같게(숫자 아니면 0) | 중간 |
| 4 | 계획 "조사 반영" 28행, 8장 #6 | "#35로 v0.2 반영, 8장은 S3 전 재확인" / #6 "web이 v0.1" | #6은 **해결**로 바꾼다. 남은 불일치는 #1·#2·#3·#4·#5·#7~#13 (3절 표) | 낮음 |
| 5 | 계획 기준 문서 (6행), D1 기준 문서 | `docs/proposal.md` (버전 없음) | `docs/proposal.md` v3.1로 표기. 값은 같으므로 본문 수정 없음 | 낮음 |
| 6 | 계획 6장 `inflow_ratio`, S4 `InflowMonitor`, D1 4.4 | 최근 5초 값이 **모두** 있어야 평균, 하나라도 null이면 경보 조건 거짓 | 실제 흐름 출력은 경계에 움직이는 머리가 적으면 null이다. 5개 연속 non-null을 요구하면 경보가 거의 안 켜질 수 있다. 선택지: (가) 지금대로, (나) 최근 5초 중 non-null이 k개(예: 3) 이상이면 그 평균 `(가정)`. 실제 E04_039 흐름 결과의 null 비율을 보고 정한다 `[토론]` (조영준이 흐름·서버 모두 담당이라 혼자 정할 수 있음) | 중간 |
| 7 | 계획 6장 `pressure`, S4 `InstabilityTracker`, D1 4.3 | null이면 불안정 연속 0 | 흐름 출력은 셀 머리 수가 `min_heads`보다 적거나 불안정 창이 덜 찬 첫 구간에서 `pressure` null이다. 밀집 셀에서 머리가 가려져 null이 끼면 3초 연속이 끊긴다. 규칙은 유지하되, 실제 데이터에서 끊김 빈도를 E5 때 확인한다 `[토론]` | 낮음 |
| 8 | 계획 6장·S4 `counterflow`, D1 4.3 | 판정 안 씀, 그대로 전달 | 흐름 모듈이 `counterflow`를 쓰지 않으므로 실제 파일에서 늘 null(가짜 타임라인만 값 있음). 계획대로 둔다. `timeline-spec.md` 4절 "불안정 판정에 쓴다" 문구 정리 요청(D1에 이미 있음)은 유지 | 낮음 |
| 9 | 조사 3절 #6 `[토론]` 6, 계획 6장 | 흐름 `inflow_ratio` 소수 2자리 → 규격 4자리 | 여전히 2자리(`run_flow.py` "가정 [토론]"). 서버는 자리수와 무관하게 0~1만 검사하므로 서버 영향 없음. 안건은 그대로 열어 둔다 | 낮음 |
| 10 | 계획 S1 fixture `valid_v02.json` | `schema_version` "0.2", `count` 6.5 | 그대로. 1~3번 규칙에 맞게 모든 프레임·셀에 두 키를 넣는다(값 null 가능) | 낮음 |
| 11 | 계획 0장 39행, 조사 1.3 | 가짜 `inflow_ratio` 최대 0.6 / 예측을 거치면 `count`·`counterflow`가 빠진다 | 앞부분은 그대로(`fake_timeline.py` 안 바뀜). **뒷부분은 해결**: 예측을 거쳐도 두 키가 남는다. 조사 1.3 주석 삭제 | 낮음 |
| 12 | 조사 0절 #8, 1.2 예측 행, 5절 위험 "예측 모듈 `count` 사라짐" | 문제로 기록 | **해결**(#35)로 표시 | 낮음 |
| 13 | 조사 1.1 `validate.ts`·`types/timeline.ts` 행, 3절 #21 | `count`를 버림, v0.1 | v0.2. `count` 유지, `counterflow` null 채움. 실시간 프레임은 `requireV02=false`로 검사 | 낮음 |
| 14 | 조사 1.2 `run_density.py` 행 | `schema_version`은 `"0.1"` | 이제 `"0.2"`(같은 상수 import) | 낮음 |
| 15 | 조사 1.2 `run_flow.py` 행 | "작업 중", `counterflow` 안 씀, `inflow_ratio` 2자리 | 병합됨. 위 내용에 더해 `inflow_ratio`·`pressure` null 조건(6·7번), `interval_s` 1 강제, 머리 높이 평면 m/s | 낮음 |
| 16 | 조사 1.4 E8 행 | 기획서 1.2·7.2가 "1초 분량 처리 ≤ 1초"를 기준처럼 적음(이유노 반영 예정) | **반영됨**(v3.1). 행 상태를 "확정"으로 | 낮음 |
| 17 | 조사 1.4 밀도 평활 행 | `proposal-detail.md`의 EMA는 옛 설계 | 상세 문서도 5장 평균으로 고쳐짐. 주석 삭제 | 낮음 |
| 18 | 계획 8장 / 조사 4절 (새 행) | 없음 | 화면이 영상 시각을 기준으로 프레임을 고르고, `t`와 1.0초 넘게 벌어지면 영상을 옮긴다(api-spec 6절 구현됨). 서버 반복 재생으로 `t`가 0이 되면 화면 프레임 목록에 옛 `t`가 섞인다(8장 #5와 같은 문제). 일시정지·이동은 화면이 `playback`을 처리하지 않아 영상이 멈추지 않는다 → 8장 #11에 포함 | 낮음 |
| 19 | D1 3.2 | v0.1 파일이면 두 필드를 null로 읽어 보냄 | 그대로 맞다(`schema.py`도 같은 방식). 1번을 엄격하게 정하면 "v0.2 파일은 두 키 필수" 한 줄 추가 | 낮음 |
| 20 | D1 6절 (main 6절 그대로) | 영상 시간 맞춤 1.0초 (가정) | 화면이 이 값으로 구현했다. 고칠 것 없음. "(가정)" 유지 | 없음 |
| 21 | S0 계획 | 뼈대·`application.yml`·`.editorconfig`·CLAUDE.md 규칙 | main 병합분 중 `server/`·루트 `.gitignore`·`CLAUDE.md`를 건드린 것이 없다. 그대로 | 없음 |

---

## 3. 세부 확인

### 3.1 기획서 v3.1과 계획의 등급·알림 규칙

| 규칙 | 기획서 v3.1 | 계획 (4장 yml, S2·S4·S5) | 일치 |
|---|---|---|---|
| 등급 경계 | 정상 < 3, 주의 ≥ 3, 경계 ≥ 4, 심각 ≥ 5 또는 불안정 (3.2) | `caution 3.0, alert 4.0, critical 5.0`, `≥` 판정 | 예 |
| 등급 이름 | 정상·주의·경계·심각 | `NORMAL("정상")`, `CAUTION("주의")`, `ALERT("경계")`, `CRITICAL("심각")` | 예 (화면만 "경고") |
| 히스테리시스 | 2초 연속 충족 시 올림, 10초 연속 해제 시 한 단계 내림 (3.2, 가정) | `up-seconds 2`, `down-seconds 10`, 한 단계 | 예 |
| 구역 등급 | 보행 면적 2㎡ 이상 셀 등급의 최댓값 (3.2, 가정) | `min-walkable-area-m2: 2.0`, 대상 셀 최댓값 | 예 |
| 불안정 | P = ρ × Var(v), 초기 기준 0.02/s² (3.3) | `pressure 0.02`, `seconds 3` | 예. 3초 지속은 기획서 5.4 지연 예산(≤ 3.7초)과 같음 |
| 유입 경보 | 서버가 최근 5초 평균, 구역 인원 3명 미만이면 켜지 않음 (3.3, 가정) | `ratio 0.6`, `window-seconds 5`, `min-count 3`, `off-seconds 10` | 예. 0.6·10초는 api-spec 값 |
| 알림 | 경계 = 알림, 심각 = 비상 알림, 주의 = 강조 표시 (3.2) | `GRADE_UP`은 경계 이상, 주의는 등급만 | 예 |
| E8 | 알림 p95 ≤ 5초, 30분 반복 재생 무중단, 처리 시간은 기록·공개만 (1.2, 7.2) | 결정 9, 5장, D1 7절 | 예 |
| 지연 예산 | 확인 1.0 + 판정 0.2 + 표시 0.5 = ≤ 1.7초, 불안정 ≤ 3.7초 (5.4) | 위험 표 "밀도 +1초, 불안정 +3초" | 예 |
| E6 | 셀별과 구역별 예측을 모두 비교 (v3.1 추가) | 셀 `density_pred_60s`만 | 규격에 구역 예측 필드가 없다. 나중에 생기면 모르는 키 무시·`hello.meta` 그대로라 서버는 깨지지 않는다 |

새 `[토론]`: 기획서에는 없다. 흐름 코드(`inflow.py`, `run_flow.py`)에 경계 셀 정의·`min_samples`·소수 2자리·사람 없는 셀 머리 제외가 `(가정) [토론]`으로 있다. 서버에는 2절 6번 null 빈도 문제로만 닿는다.

해결된 것: 기획서 E8 문구(조사 1.4), 예측 모듈의 `count` 누락(조사 0절 #8), 화면 v0.2 타입·검증(계획 8장 #6).

### 3.2 화면 메시지 형태와 검증 (main 기준)

| 질문 | 답 | 근거 |
|---|---|---|
| 화면이 `count`·`counterflow`를 받나 | 예. 파일과 실시간 프레임 모두. 실시간은 `requireV02=false`라 키가 없어도 통과하고, 있으면 범위 검사 | `validate.ts` `validateFrame` |
| 화면이 아직 옛 메시지를 기대하나 | 예. `timeline`·`frames`·`frame`·type 없음만 받고 나머지는 throw | `liveFeed.ts` (안 바뀜) |
| `hello`·`zone_state`·`alert`·`playback`을 아나 | 아니오 | 같은 파일 |
| 서버 `grade`를 쓰나 | 아니오. 등급 배지·알림은 `levelOf(density)`로 화면에서 즉시 판정, 작은 셀 제외 없음, 표기 "경고" | `config/density.ts`, `alerts.ts`, `AnalysisView.tsx` |
| 닫힘 코드 4404, 재접속 | 무시, 1초부터 2배 최대 15초 | `useLiveFeed.ts`, `config/app.ts` (안 바뀜) |
| mock 서버 | 포트 8787, v0.1 `timeline`/`frame` | `mock-ws-server.mjs` (안 바뀜) |
| 영상 | `meta.video_id`로 `/videos/{id}.mp4`. 재생 중 영상 시각이 기준, 1.0초 넘게 벌어지면 영상을 `t`로 | `video.ts` (#34) |

→ 서버가 api-spec대로 `zone_state`를 보내면 지금 화면은 여전히 아무것도 표시하지 못한다. 11-13 1차 연결 전에 화면 쪽 `liveFeed.ts` 어댑터가 필요하다는 계획 8장 결론은 그대로다.

### 3.3 계획 8장 불일치 표 갱신

| # | 상태 |
|---|---|
| 1 mock·화면 메시지 type | 남음 |
| 2 모르는 type throw | 남음 |
| 3 `zone_state` 어댑터 | 남음 |
| 4 `ws://localhost:8787` → `/ws/zones/{zone_id}` | 남음 |
| 5 반복 시 초기화 신호 | 남음. 영상 기준 프레임 선택(#34)이 생겨 옛 `t`가 섞이면 영상과 히트맵이 어긋난다 |
| 6 타입·검증 v0.1 | **해결** (#35) |
| 7 화면 즉시 판정, "경고" | 남음 (분석 화면 등급 배지 추가로 노출이 늘었다) |
| 8 화면 자체 알림 | 남음 |
| 9 재접속 최대 15초 | 남음 |
| 10 `frame_ts` 지연 기록 | 남음 |
| 11 `thresholds`·`playback`·`unacked_alerts` | 남음. `playback` 일시정지·이동을 영상에도 반영해야 함 (api-spec 6절) |
| 12 mock 옛 형식 | 남음 |
| 13 CORS 5173 | 남음 (영상은 화면 자체 `/videos`에서 열어 서버 CORS와 무관) |

---

## 4. 할 일 (문서별)

| 문서 | 고칠 곳 |
|---|---|
| `server_impl_plan.md` | 기준 문서에 v3.1. S1 검증 규칙에 2절 #1·#2, 테스트 표에 #3. 6장·S4에 #6 `[토론]`(유입 평균 null 처리), #7 메모. 8장 #6 해결 표시, #5·#11에 영상 메모. 9장 `[토론]`에 #6 추가 |
| `server_research.md` | 0절 #8, 1.1 `validate.ts`·타입 행, 1.2 생산자 표(`run_density` 버전, 예측 행, `run_flow` 행), 1.3 주석, 1.4 E8·평활 행, 3절 #21, 4절 #4, 5절 위험 1행을 "해결/갱신"으로. 덧붙여 이 문서 링크 |
| D1 `api-spec.md` 초안 | 기준 문서에 `proposal.md` v3.1. 2절 #1을 엄격하게 정하면 3.2에 "v0.2 파일은 두 키 필수" 한 줄. 2절 #6을 바꾸면 4.4 "5초 값 모두" 문장과 10절 안건 추가 |
| `server_s0_skeleton_plan.md` | 없음 |

---

## 5. 결론

| 문서 | 판정 | 이유 |
|---|---|---|
| (a) `server_impl_plan.md` | **부분 수정** | 기준 문서(타임라인 규격·결정 기록·API 명세)가 그대로이고 기획서 v3.1 값도 계획과 같다. 구조·PR 순서·yml·판정 규칙은 유지. S1 검증을 `schema.py` v0.2(버전별 필수 키, `counterflow` 0~1)에 맞추고 테스트 4개 추가(중간). 실제 흐름 출력의 잦은 null 때문에 유입 5초 평균 규칙을 `[토론]`으로 올림(중간). 나머지는 표시 갱신(낮음) |
| (b) `server_research.md` | **부분 수정** | 외부 API 분석(2절)과 검증표 대부분은 그대로 유효. 내부 분석(1절)의 웹·예측·생산자 행 몇 개가 #35·#36·#37로 낡았다. 해결 표시와 흐름 null 조건 추가면 충분 |
| (c) D1 `api-spec.md` 초안 | **부분 수정 (작음)** | main의 `api-spec.md`가 안 바뀌어 충돌 없이 그대로 올릴 수 있다. 내용도 기획서 v3.1·`schema.py` v0.2와 맞다. 기준 문서 표기와, 2절 #1·#6을 정한 결과만 반영 |
| (d) `server_s0_skeleton_plan.md` | **그대로** | 병합분 중 `server/`, 루트 `.gitignore`, `CLAUDE.md`를 건드린 것이 없다. S0은 D1·규격 변경에 의존하지 않는다 |

### `[결정 필요]` (조영준)
1. 서버 검증에서 v0.2 파일의 `count`·`counterflow` 키를 필수로 할지 (권장: 필수, `schema.py`·`validate.ts`와 같게).

### `[토론]`
| # | 안건 | 누구와 |
|---|---|---|
| 1 | 유입 5초 평균: 5개 모두 non-null 요구 vs 일부 null 허용(k개 이상) | 조영준 (흐름·서버), 실제 E04_039 흐름 결과로 |
| 2 | `pressure` null이 불안정 3초 연속을 끊는 빈도 확인 | 조영준, E5 때 |
| 3 | 화면 `liveFeed.ts` 어댑터와 `playback`의 영상 반영 (11-13 연결 범위) | 나예린 |
