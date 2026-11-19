# 흐름 추정 개선 계획: 반해상도 Farneback + 프레임 간격 0.2초

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-18 |
| 근거 | `docs/research/flow_model_upgrade_research.md` (E05_035 읽기 전용 벤치마크) |
| 대상 | `src/flow/estimators.py`, `src/flow/run_flow.py`, 새 파일 `src/flow/flow_proxy.py`·`src/flow/compare_flow.py`, `tests/flow/` |
| 제안만 | `src/counting/analyze.py` 한 줄 (이유노 님 파일, 편집하지 않음) |
| 브랜치 | `feat/flow-half-res-gap` (`main`에서 분기, `fix/flow-sparse-cell-noise`와 별개) |
| 일정 | 코드 동결 11-19. **동결 전 병합은 팀 합의(예외 승인)가 있어야 한다.** 합의가 없으면 11-19 이후 발표 뒤 작업으로 미룬다 |
| 상태 | 계획 v1. **사용자 검토 전** (모든 결정은 `제안`) |

## 0. 목표와 원칙
- 목표: 흐름 단계를 **더 빠르게(3배 이상)** 하고 **속도 잡음을 줄인다(정지 배경 p95 절반 이하)**.
- 기본 동작은 바꾸지 않는다. `FarnebackEstimator()`와 `analyze_video(gap_frames=1)` 기본값은 그대로 두고, 새 설정은 인자로만 켠다. 그래서 되돌리기는 `analyze.py` 한 줄을 원래대로 두는 것이다.
- timeline 규격(키·단위·자릿수)은 바꾸지 않는다. 바뀌는 것은 `meta.models.flow` 문자열뿐이다.
- 머리 점·흐름장은 지금처럼 메모리로만 쓰고 저장하지 않는다.

## 1. 권장안 (제안)
**Farneback 반해상도(0.5배) + `gap_frames = 6`(30 fps에서 0.2초)**.

| 설정 | 시간/쌍 | 정지 p95 (px/프레임) | 신호/잡음 | 사진 오차 / 흐름 0 |
|---|---|---|---|---|
| 현재: Farneback 원본, gap 1 | 0.991초 | 0.181 | 6.6 | 0.50 |
| **권장: Farneback 0.5배, gap 6** | **0.289초 (3.4배 빠름)** | **0.075 (0.41배)** | **13.0 (2.0배)** | 0.56 |
| 대안 A: Farneback 원본, gap 6 (정확도만) | 1.143초 | 0.043 | 22.3 | 0.48 |
| 대안 B: Farneback 0.5배, gap 3 | 0.258초 | 0.135 | 7.5 | 0.52 |

(E05_035 10쌍, 연구 문서 5.2절)

- 이유: 정지 잡음은 쌍당 약 0.2 px로 거의 일정해서 간격이 길수록 속도 잡음이 준다. 설계 문서의 Δt도 0.2초다(`docs/proposal-detail.md:297`). 반해상도는 잡음을 2배로 키우지만 간격 6이 이를 덮고 남는다.
- DIS·RAFT는 권장하지 않는다. DIS는 잡음이 크고(MEDIUM p95 0.72 px), RAFT small은 CPU 3.3초/쌍에 프록시도 가장 나쁘다.
- 전체 분석 시간은 인원 추정이 83~97%라서 크게 줄지 않는다. 흐름 단계 E04_039 106.8초 → 약 35초(추정, 가정)다.

## 2. 받아들이는 기준 (제안)
세 영상 E04_039·E05_035·E05_038에서 현재 설정(기준)과 권장 설정을 같은 머리 점으로 비교한다(5장 절차).

| ID | 지표 | 기준 |
|---|---|---|
| A1 | 흐름 단계 시간 (`compare_flow` 출력 `flow_s`) | 기준의 **0.5배 이하** (E04_039 ≤ 53초) |
| A2 | 프레임 프록시 정지 p95 (px/프레임, `flow_proxy`) | 기준의 **0.6배 이하** |
| A3 | 프레임 프록시 사진 오차 비율 | 기준 **+0.10 이하** |
| A4 | 셀 평균 속력 > 3 m/s 셀-초 수 | 기준 **이하** |
| A5 | 움직이는 셀(추정 머리 ≥ 2, 속력 ≥ 0.3 m/s) 속력 중앙값 | 기준 대비 **±20% 안** (간격이 길어 과소 추정하는지 확인) |
| A6 | 판정 셀 `pressure > 0.02` 셀-초 수 | 기준 **이하** |
| A7 | `pytest tests/flow` | 모두 통과 |

- A5만 실패하면 대안 B(gap 3)로 다시 잰다. A1이 실패하면(반해상도가 느리면) 대안 A로 정확도만 챙긴다.
- E04_039·E05_038 영상은 이 PC에 없다. A2·A3는 영상이 있는 PC에서 잰다.

## 3. 코드 변경

### 3.1 `src/flow/estimators.py` — `FarnebackEstimator(scale)`
```python
class FarnebackEstimator:
    """OpenCV Farneback 흐름. 학습하지 않는 기준선이다."""

    def __init__(self, scale: float = 1.0) -> None:
        """기본 파라미터(proposal-detail 3.4 시작값, 가정)로 만든다.

        scale은 흐름을 구할 해상도 배율이다(0 < scale ≤ 1). 1이 아니면
        줄인 회색조로 흐름을 구하고 원본 크기로 선형 확대한 뒤 값을
        1/scale배 해 원본 px로 돌려준다. 범위 밖이면 ValueError다.
        """
        if isinstance(scale, bool) or not 0 < scale <= 1:
            raise ValueError(f"scale은 0보다 크고 1 이하여야 한다: {scale!r}")
        self._scale = float(scale)
        self.name = (
            "farneback-cv2" if scale == 1 else f"farneback-cv2-x{scale:g}"
        )

    def estimate(
        self, prev_bgr: np.ndarray, next_bgr: np.ndarray
    ) -> np.ndarray:
        """Farneback 흐름을 원본 해상도 px 단위로 돌려준다."""
        a, b = _to_gray(prev_bgr), _to_gray(next_bgr)
        s = self._scale
        if s != 1:
            a = cv2.resize(a, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            b = cv2.resize(b, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        # 인자 순서: prev, next, flow, pyr_scale, levels, winsize,
        # iterations, poly_n, poly_sigma, flags. 값은 시작값 (가정)
        flow = cv2.calcOpticalFlowFarneback(
            a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0,
        )
        if s != 1:
            h, w = prev_bgr.shape[:2]
            flow = cv2.resize(flow, (w, h), interpolation=cv2.INTER_LINEAR)
            flow /= s
        return flow.astype(np.float32)
```
- `scale=1`이면 지금과 같은 계산·같은 이름이다(기존 테스트와 timeline 문자열 유지).

### 3.2 `src/flow/run_flow.py` — `meta.models.flow`에 간격 표시
```python
    meta.setdefault("models", {})["flow"] = (
        f"{estimator.name} head-r{patch_radius_px} gap{gap_frames}"
    )
```
- 어떤 간격으로 돌렸는지 timeline만 보고 알 수 있게 한다. 문자열을 해석하는 코드는 없다.
- `fix_flow_sparse_cell_noise_plan.md` 3.3(D3)의 `mh{min_heads}`와 함께 들어가면 순서는 `"{name} head-r6 gap6 mh2"`로 맞춘다(뒤에 병합하는 쪽이 맞춘다).
- docstring 86행 `meta.models.flow는 "{estimator.name} head-r{patch_radius_px}"다.`를 `... head-r{patch_radius_px} gap{gap_frames}"다.`로 바꾼다.

### 3.3 새 파일 `src/flow/flow_proxy.py` — 머리 점 없이 재는 프레임 프록시
연구 문서 부록 A·B 스크립트를 함수로 옮긴다. 정답 흐름 없이 잰다.
```python
def static_noise_p95(flow: np.ndarray, mask: np.ndarray, gap: int) -> float:
    """정지 마스크 화소의 |흐름|/gap 95백분위 [px/프레임]. 마스크가 비면 NaN."""

def photometric_ratio(
    prev_gray: np.ndarray, next_gray: np.ndarray, flow: np.ndarray,
    mask: np.ndarray,
) -> float:
    """next를 흐름으로 당겨 prev와 비교한 평균 절대 차를 흐름 0일 때 값으로 나눈다.

    마스크가 비거나 흐름 0 오차가 0이면 NaN이다. 낮을수록 좋다.
    """

def frame_masks(
    prev_gray: np.ndarray, next_gray: np.ndarray, walkable: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """(정지 배경, 움직인 곳) 마스크. 흐린 절대 차 < 1은 정지(걷는 곳 밖), ≥ 4는 움직임(걷는 곳 안)."""

def main() -> None:
    """--video, --homography, --configs "fb:1:1,fb:0.5:6"(추정기:배율:gap),
    --pairs 10. 설정별 시간/쌍·정지 p95·사진 오차 비율을 표로 찍고
    outputs/flow_upgrade/{video}_proxy.json에 집계값만 쓴다."""
```

### 3.4 새 파일 `src/flow/compare_flow.py` — 같은 머리 점으로 설정 비교
```python
def timeline_proxies(timeline: dict, min_area_m2: float = 2.0) -> dict:
    """timeline 하나의 셀 단위 지표를 낸다.

    판정 셀(walkable_area_m2 ≥ min_area_m2)만 쓴다.
    over3_ms: 셀 평균 속력 > 3 m/s 셀-초 수,
    moving_speed_median: 추정 머리(density × walkable_area_m2) ≥ 2이고
    속력 ≥ 0.3 m/s인 셀-초 속력 중앙값 (없으면 None),
    p_over_002: pressure > 0.02 셀-초 수.
    """

def main() -> None:
    """--homography, --video, --configs. count_video를 한 번 돌리고,
    머리 점을 메모리에 둔 채 설정마다 analyze_video를 돌린다.
    설정별 timeline은 data/processed/flow_upgrade/{video}_{설정}.json
    (git 제외), 지표·flow_s는 outputs/flow_upgrade/{video}_compare.json에 쓴다.
    머리 점은 어디에도 쓰지 않는다."""
```
- `count_video`는 `src/counting/run_density.py:59`의 공개 함수를 import만 한다(수정 없음). P2PNet 가중치가 있는 PC(이유노 님)에서만 돈다.
- `min_area_m2 = 2.0`은 서버 `min-walkable-area-m2`와 같은 값(가정)이다. 규칙을 옮기는 것이 아니라 비교용 필터다.

### 3.5 `src/counting/analyze.py` 제안 (이유노 님께, 편집하지 않음, A1~A7 통과 뒤)
```python
    analyze_video(Path(args.video), out, out, FarnebackEstimator(scale=0.5), heads=heads,
                  h_head=np.array(cfg["head_plane"]["H_head_img_to_ground"]),
                  cell_origin_m=tuple(cfg["cell_origin_m"]), gap_frames=6)
```
- 제안 문구: "흐름 단계를 반해상도·0.2초 간격으로 바꾸면 흐름이 3배 이상 빠르고 속도 잡음이 절반 아래로 줍니다(연구 문서 5.2절). `analyze.py` 56행 호출에 `scale=0.5`와 `gap_frames=6` 두 인자만 더해 주세요. 되돌릴 때는 두 인자를 빼면 됩니다."
- 영상 fps가 7 미만이면 `gap_frames=6`은 기존 검사(`run_flow.py:140~144`)에서 ValueError다. 지금 영상은 모두 30 fps(가정, E05_035는 확인)다.

## 4. TDD 단계 (합성 픽스처만, 실제 영상·가중치 없음)

### 4.1 단계 1 — 반해상도 Farneback이 알려진 이동을 원본 px로 복원 (RED → GREEN)
`tests/flow/test_estimators.py`에 추가. 기존 `_shifted_pair`·`_interior_median` 재사용.
```python
# 반해상도 허용 오차 0.5 px. 배율 복원을 빠뜨리면 x가 2 px(4→2),
# x·y를 거꾸로 나누면 이동 (+4, -2)에서 두 축 모두 크게 어긋난다.
# 질감 σ 2는 0.5배로 줄이면 σ 1이 되므로 더 큰 영상에서 시험한다.
def test_farneback_half_scale_recovers_shift_in_original_px() -> None:
    """scale=0.5: (H, W, 2) float32, 원본 px 단위로 (+4, -2)가 나온다."""
    prev, nxt = _shifted_pair(256, 320, 4, -2)
    flow = FarnebackEstimator(scale=0.5).estimate(prev, nxt)
    assert flow.shape == (256, 320, 2)
    assert flow.dtype == np.float32
    mx, my = _interior_median(flow, border=32)
    assert abs(mx - 4) < TOL_CV_PX
    assert abs(my - (-2)) < TOL_CV_PX


def test_farneback_name_marks_scale_only_when_not_one() -> None:
    """이름: 기본은 그대로, 0.5배는 -x0.5가 붙는다."""
    assert FarnebackEstimator().name == "farneback-cv2"
    assert FarnebackEstimator(scale=0.5).name == "farneback-cv2-x0.5"


@pytest.mark.parametrize("scale", [0, -0.5, 1.5, True])
def test_farneback_rejects_bad_scale(scale: object) -> None:
    """scale이 (0, 1] 밖이거나 bool이면 ValueError다."""
    with pytest.raises(ValueError):
        FarnebackEstimator(scale=scale)
```
- 변이 검사: `flow /= s`를 빼면 첫 테스트가 실패하는지 확인하고 차이를 주석에 적는다(기존 테스트 형식).

### 4.2 단계 2 — `meta.models.flow`에 gap 표시
`tests/flow/test_run_flow.py:281` 기대값을 `"farneback-cv2 head-r6 gap1"`로 바꾸고(RED), 새 테스트를 더한다.
```python
def test_flow_model_records_gap_frames(tmp_path: Path) -> None:
    """gap_frames=2로 돌리면 models.flow 끝에 gap2가 붙는다."""
    result, _, _ = _run(tmp_path, [2, 2], gap_frames=2)
    assert result["meta"]["models"]["flow"] == "farneback-cv2 head-r6 gap2"
```
- 그다음 3.2절 한 줄로 GREEN.
- 반해상도와 `_run`의 조합 회귀: `analyze_video`에 `FarnebackEstimator(scale=0.5)`를 넣어 `EXPECTED_VX` 1.0 m/s가 `TOL_V` 안인지 보는 테스트 하나를 더한다. 합성 영상 크기가 작아 반해상도에서 실패하면 영상 크기를 키우는 대신 이 테스트를 빼고 4.1로 갈음한다(결정 D6).

### 4.3 단계 3 — `flow_proxy` 지표 함수
`tests/flow/test_flow_proxy.py` (새 파일):
- `photometric_ratio`: 질감을 (+3, −2) 옮긴 쌍에 정확한 흐름(모든 화소 (3, −2))을 넣으면 내부 마스크에서 < 0.05, 흐름 0을 넣으면 1.0(±1e-6).
- `static_noise_p95`: 흐름이 모두 0.4 px이면 gap 2에서 0.2, 마스크가 비면 NaN.
- `frame_masks`: 오른쪽 절반만 바뀐 두 영상과 걷는 곳 = 오른쪽 절반이면, 움직인 곳은 오른쪽 안에만, 정지는 왼쪽에만 있다.
- `main`은 테스트하지 않는다(실제 영상 필요). 대신 E05_035로 손으로 돌려 연구 문서 5.2절 값과 소수 2자리 안에서 같은지 본다.

### 4.4 단계 4 — `compare_flow.timeline_proxies`
`tests/flow/test_compare_flow.py` (새 파일), 손으로 만든 timeline dict:
- 판정 셀 2개(면적 4 m²)와 작은 셀 1개(1 m²). 속력 3.5 m/s 셀-초 1개(판정 셀) → `over3_ms == 1`, 작은 셀의 4 m/s는 세지 않는다.
- density 0.6(추정 머리 2.4), 속력 1.0·1.4 → `moving_speed_median == 1.2`. density 0.2(머리 0.8)는 빠진다.
- pressure 0.03·0.01·null → `p_over_002 == 1`.
- `vx`가 null인 셀은 모든 지표에서 빠진다.
- `main`은 P2PNet 가중치가 필요해 테스트하지 않는다.

### 4.5 기존 테스트 영향
- `test_keeps_counting_fields_and_sets_flow_model`(281행) 기대 문자열만 바뀐다. 나머지는 `FarnebackEstimator()` 기본(scale 1)을 쓰므로 그대로다.
- 실행: `C:\Users\Woori\anaconda3\envs\crowdsight\python.exe -m pytest tests/flow -q`

## 5. 평가·재분석 절차 (이유노 님과 조율)
1. (조영준, 이 PC) 프레임 프록시: 
   `python -m src.flow.flow_proxy --video data/raw/aihub_71850/halloween_fri/E05_035.mp4 --homography infra/homography/E05_035.json --configs fb:1:1,fb:0.5:6,fb:1:6,fb:0.5:3`
2. (이유노 님, P2PNet 가중치 PC) 세 영상 비교. 인원 추정은 영상마다 한 번만 돈다(E05 약 18분, E04_039 약 9분):
   ```
   python -m src.flow.compare_flow --homography infra/homography/E04_039.json --video <E04_039 영상> --configs fb:1:1,fb:0.5:6
   python -m src.flow.compare_flow --homography infra/homography/E05_035.json --video data/raw/aihub_71850/halloween_fri/E05_035.mp4 --configs fb:1:1,fb:0.5:6
   python -m src.flow.compare_flow --homography infra/homography/E05_038.json --video <E05_038 영상> --configs fb:1:1,fb:0.5:6
   ```
   같은 PC에서 1번도 세 영상으로 돌린다(A2·A3).
3. `outputs/flow_upgrade/*_compare.json`, `*_proxy.json`으로 2장 A1~A6을 판정해 이 문서 변경 이력에 적는다.
4. 통과하면 3.5절 한 줄 변경을 이유노 님께 요청하고, `analyze.py`로 세 영상을 다시 분석해 `data/processed/timeline/*.json`과 `outputs/e8/*_analysis_time.json`을 새로 만든다. 서버·화면은 timeline만 바뀌므로 그대로다.
5. 실패하면 3.5절을 적용하지 않는다. 1~4단계 코드는 기본값을 바꾸지 않으므로 그대로 둬도 동작이 같다.
- 동결(11-19) 뒤 3.5·4번은 **팀 합의로 예외를 받아야 한다.** 발표 수치(흐름 시간, E5 결과)가 바뀌므로 기획서·발표 자료 담당과 함께 정한다.
- `fix/flow-sparse-cell-noise`(min_heads 2)와 함께 재분석하면 인원 추정을 한 번만 돌릴 수 있다. 두 변경을 같은 재분석에 묶는 것을 제안한다(D5).

## 6. 결정 표

| ID | 결정 | 제안 | 근거 | 상태 |
|---|---|---|---|---|
| D1 | 바꿀 설정 | Farneback 0.5배 + gap 6 | 연구 5.2절: 3.4배 빠르고 신호/잡음 2배 | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D2 | 추정기 교체(DIS·RAFT) | 하지 않음 | DIS 잡음 큼, RAFT CPU 느리고 프록시 나쁨 (연구 5.1절) | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D3 | `meta.models.flow` 형식 | `"{name} head-r{r} gap{g}"`, min_heads와 합치면 `... gap{g} mh{m}` | 간격을 timeline에서 알 수 있게 | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D4 | 기본값 변경 | `estimators`·`run_flow` 기본값은 그대로, `analyze.py` 호출 인자로만 켬 | 되돌리기 쉽고 테스트 영향 최소 | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D5 | 재분석 묶기 | min_heads 2 계획과 같은 재분석 | 인원 추정 시간(세 영상 약 45분) 한 번 | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D6 | 반해상도 `analyze_video` 통합 테스트 | 합성 영상이 작으면 빼고 4.1로 갈음 | 합성 영상 크기 확인 필요 | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D7 | 동결 예외 | 팀 합의 뒤에만 3.5절 적용. 합의 없으면 발표 뒤 | `CLAUDE.md` 진행 원칙 (11-19 동결) | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |
| D8 | 기준 A1~A6 수치 | 2장 표 | 벤치마크 여유를 두고 정함 (가정) | **확정** (11-19 사용자 \"다음 작업 진행\", 추천안) |

## 7. 위험
| 위험 | 영향 | 대응 |
|---|---|---|
| 간격 6에서 밀집 장면 가림·큰 이동으로 속도 과소 추정 | 속력·분산이 낮게 나와 경보를 놓침 | A5(±20%)로 확인, 실패하면 gap 3 |
| 측정이 영상 1개·10쌍·프록시뿐 | 다른 영상에서 결론이 다를 수 있음 | 5장에서 세 영상 확인 뒤에만 적용 |
| 반해상도에서 작은(먼) 머리의 움직임이 뭉개짐 | 먼 셀 속도 오차 | 머리 패치 r6은 원본 px 기준이라 그대로. A4·A5로 확인 |
| 동결 직전 변경 | 발표 수치(E5, 처리 시간) 다시 써야 함 | D7. 기본값을 안 바꾸므로 코드 병합 자체는 동작에 영향 없음 |
| `outputs/e8` 흐름 시간과 벤치마크 시간 차이(0.56 vs 0.98초/쌍) | A1 판정 기준 혼동 | A1은 같은 실행 안의 `compare_flow` `flow_s`로만 비교 |
| 재분석에 이유노 님 시간 필요 | 일정 | D5로 한 번에 묶음 |

## 8. 설치
- **필요 없음.** `opencv-python` 5.0.0, `numpy` 2.4.6만 쓴다.
- 참고(채택하지 않음): RAFT large 비교에는 가중치 내려받기(torchvision 자동, 약 20 MB, 가정), OpenCV contrib 알고리즘에는 `pip install opencv-contrib-python==5.0.0.93`(현재 `opencv-python`과 바꿔 설치, 승인 필요)이 든다.

## 9. 커밋 제안
1. `feat: Farneback 반해상도 배율 인자 추가` (4.1)
2. `feat: 흐름 모델 문자열에 프레임 간격 표시` (4.2)
3. `feat: 머리 점 없는 흐름 프록시 지표 추가` (4.3)
4. `feat: 같은 머리 점으로 흐름 설정 비교 스크립트 추가` (4.4)

## 변경 이력
| 날짜 | 내용 |
|---|---|
| 2026-11-18 | 계획 v1 작성 (사용자 검토 전) |
| v1.1 | 11-19 | 사용자 "다음작업 진행해": 추천안 D1~D8 확정. `feat/flow-upgrade` 브랜치에서 min_heads 2 계획(`fix_flow_sparse_cell_noise_plan.md`)과 함께 구현한다 |
