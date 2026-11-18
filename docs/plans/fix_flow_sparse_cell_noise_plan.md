# 흐름 단계 저밀도 셀 잡음 수정 계획 (`fix/flow-sparse-cell-noise`)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-18 |
| 기준 | `data/processed/timeline/{E04_039,E05_035,E05_038}.json`(11-18 실제 분석 결과), `src/flow/run_flow.py`·`cells.py`·`timeline_flow.py`·`noise_floor.py`·`ground.py`, `src/counting/analyze.py`·`run_density.py`, `tests/flow/test_run_flow.py`, PR #63(`fix/instability-false-alarm`), PR #62(`feat/flow-e5`) |
| 대상 | `src/flow/run_flow.py`, `tests/flow/test_run_flow.py` (`main` `24537bb`에서 분기). `src/counting/analyze.py`는 **제안만** (이유노 님 파일) |
| 범위 | 흐름 단계에서 머리 1개 셀의 속도·압력을 내지 않게 한다. timeline 규격(키·단위·자릿수)은 그대로다 |
| 일정 | 코드 동결(11-19) **뒤**에 진행. 지금은 이유노 님과 상의할 계획만 쓴다 |
| 상태 | 계획 v1. **사용자·이유노 님 검토 전** (모든 결정은 `제안`) |

## 0. 확인한 사실

### 0.1 코드 (읽어서 확인)
- `src/flow/run_flow.py:67` `analyze_video(..., noise_var=None, window_s=30.0, min_heads: int = 1, patch_radius_px=6, inflow_min_heads=0)`. `min_heads`는 검사가 없다(0·음수·실수도 받는다).
- `run_flow._fill_frames` 228~233행: `low = cf.count < min_heads`인 셀은 불안정 창에 NaN으로 넣고, `fill_flow_fields(..., cf.count, min_heads)`가 `vx`·`vy`·`speed_var`·`pressure`를 null로 쓴다. 그래서 **같은 `min_heads` 하나가 표시 속도와 압력을 함께 막는다.**
- `src/counting/analyze.py:56~58` `analyze_video(...)` 호출은 `min_heads`·`noise_var`를 넘기지 않는다. 기본값(1, None)이 쓰인다. 따라서 **`run_flow.py` 기본값만 바꿔도 통합 분석에 반영된다.**
- `src/flow/cells.py` `TemporalInstability`: 30초 창 셀 평균 속도의 분산. 창 안 유효 표본이 `ceil(0.8 × 30) = 24`개 미만인 셀은 NaN. `noise_var=None`이면 0을 뺀다.
- `src/flow/noise_floor.py` `measure_noise_floor(mean_v_series, static_mask, min_samples=30)`: **정지 표시(static_mask)가 붙은 구간**의 셀 평균 속도 분산. 파이프라인 어디에서도 부르지 않는다.
- `src/flow/ground.py`: `sample_head_flow`는 머리마다 반경 6 px 패치 흐름의 중앙값, `head_ground_velocity`는 머리 높이 평면으로 m/s 변환. 속력 상한은 없다.
- `src/flow/timeline_flow.py` `fill_flow_fields`: density(소수 2자리) 0이면 `vx`·`vy`·`speed_var` null, `pressure` 0. 유효 표본 < `min_quality`면 네 필드 null. `pressure = round(ρ × 저장 speed_var, 4)`.
- `src/counting/run_density.py` `count_video`: density는 **5프레임(±0.4초) 평균** 인원 / `walkable_area_m2`이고, 흐름에 넘기는 머리 점은 **정각 프레임 1장**의 것이다. 그래서 timeline의 density로 그 초 흐름 머리 수를 정확히 알 수는 없다.
- 기존 테스트(`tests/flow/test_run_flow.py`)는 셀마다 머리 4개(한 곳은 3개)를 둔다. `min_heads`를 명시한 테스트는 `test_low_quality_cell_sample_is_kept_out_of_window`(min_heads=2) 하나다. 기본값을 2로 올려도 기존 결과는 바뀌지 않는다(4.3절).
- `meta.models.flow` 문자열을 해석하는 코드는 없다(`src/predict/schema.py`는 그대로 옮기기만 함). 테스트 `test_keeps_counting_fields_and_sets_flow_model`이 `"farneback-cv2 head-r6"`를 단언한다.
- `vx`·`vy` 사용처: 웹 `RegionPanel.tsx`·`AnalysisView.tsx`(속력 표시), 예측 `flow` 예측기(`src/predict/model.py`, 현재 설정은 `persistence`라 안 씀), 서버 `MessageFactory`(전달만).

### 0.2 실제 timeline에서 잰 값 (11-18, 읽기 전용 스크립트, 부록 A)
- 판정 셀 = `walkable_area_m2 ≥ 2.0`(서버 `min-walkable-area-m2`). "값 있음" = 판정 셀 중 ρ > 0이고 `pressure`가 숫자인 셀-초. (요청서의 500·1113·1355는 분모 정의가 다르다. ρ = 0 셀의 pressure 0이나 null 포함 여부 차이로 보인다. 넘는 개수 268·130·6과 최댓값은 같다.)

  | 영상 | 판정 셀 | 최대 ρ | 값 있음 | > 0.02 | 최대 P | ρ ≥ 3이면서 > 0.02 |
  |---|---|---|---|---|---|---|
  | E04_039 | 8 | 3.05 | 227 | 6 | 0.026 | 0 |
  | E05_035 | 44 | 1.35 | 172 | 130 | 0.202 | 0 |
  | E05_038 | 23 | 1.60 | 270 | 268 | 0.804 | 0 |

- **재현 검증**: 저장된 `vx`·`vy`로 `TemporalInstability`와 같은 규칙(창 30, 유효 24)을 다시 계산하면 저장된 `speed_var`와 세 영상 모두 100% 일치한다(|차| ≤ 0.002, 331·205·286개). 그래서 아래 (a)·(b) 시뮬레이션은 "저장된 셀 평균 속도에서 표본을 빼거나 자른 결과"로 믿을 만하다. 단 원래 머리별 속도는 없으므로 머리 단위 처리는 근사다.
- 추정 머리 수 n̂ = density × `walkable_area_m2` (5프레임 평균이라 그 초 정각 프레임 머리 수와 ±1 정도 다를 수 있다. 소수다).
- 판정 셀의 셀 평균 속력 분포:

  | 영상 | n̂ 구간 | 셀-초 | p50 | p95 | 최대 | > 3 m/s |
  |---|---|---|---|---|---|---|
  | E04_039 | [0,1) | 15 | 0.34 | 2.16 | 3.56 | 1 |
  | E04_039 | [1,2) | 51 | 0.01 | 0.20 | 0.74 | 0 |
  | E04_039 | ≥ 5 | 104 | 0.02 | 0.13 | 0.29 | 0 |
  | E05_035 | [0,1) | 403 | 0.45 | 1.78 | 2.13 | 0 |
  | E05_035 | [1,2) | 583 | 0.41 | 1.53 | 3.24 | 1 |
  | E05_035 | [2,3) | 194 | 0.39 | 1.41 | 1.76 | 0 |
  | E05_035 | [3,5) | 89 | 0.28 | 1.29 | 2.12 | 0 |
  | E05_038 | [0,1) | 186 | 0.36 | 2.17 | 4.53 | 6 |
  | E05_038 | [1,2) | 328 | 0.38 | 1.51 | 6.37 | 3 |
  | E05_038 | [2,3) | 208 | 0.34 | 1.17 | 1.66 | 0 |
  | E05_038 | [3,5) | 112 | 0.32 | 1.08 | 1.61 | 0 |

  - 3 m/s 넘는 셀-초는 모두(판정 외 셀 포함 1·1·9개) n̂ < 2 셀이다(n̂ 0.4~1.39).
  - 30초 창 분산과 창 평균 1/n̂의 1차 회귀: E05_035 `0.012 + 0.128·(1/n̂)`(r 0.51), E05_038 `−0.028 + 0.456·(1/n̂)`(r 0.32), E04_039 `0.002 + 0.007·(1/n̂)`(r 0.38). 머리가 적을수록 분산이 커진다.

### 0.3 해석 (원인)
1. **머리 1개 셀의 이상 속도**: 패치 중앙값 흐름이 사람 하나의 오검출·가림·경계 패치에 그대로 실린다. 평균할 다른 머리가 없어 6.37 m/s 같은 값이 셀 속도가 된다. 3 m/s 넘는 값은 모두 n̂ < 2에서 나온다.
2. **저밀도 셀의 분산 자체가 큼 (잡음이 아닌 부분 포함)**: 2 m 셀에 머리 2~5개여도 E05의 셀 평균 속력 p95는 1.1~1.4 m/s다. 셀 평균은 오일러 방식이라 매초 다른 사람이 지나가면 평균이 그 사람 속도로 바뀐다. 자유 보행(0.3~1.5 m/s)끼리의 차이만으로 분산 0.02~0.1 m²/s²가 생긴다. 이는 측정 잡음이 아니라 저밀도에서 P = ρ·Var가 뜻이 없다는 문헌 설명(조사 문서 1.2)과 같다.
3. 그래서 **흐름 쪽 수정만으로는 E05의 0.02 초과가 0이 되지 않는다** (2장 표). 흐름 쪽은 1번(머리 1개 잡음)을 막고, 2번은 PR #63의 서버 밀도 하한이 막는다.

## 1. 원인 확인 측정 (구현 전 사용자가 돌릴 것)
- 이미 부록 A 스크립트로 0.2절 표를 냈다. 구현자(TDD)는 다시 돌려 숫자가 같은지 확인만 한다(읽기 전용, 저장소 밖 `%TEMP%`에 둔다).
- 실행: `PYTHONIOENCODING=utf-8 <crowdsight env>/python.exe %TEMP%/flowsim/sim.py E04_039 E05_035 E05_038`
  - 이 PC에서 `conda run -n crowdsight`는 conda 4.9 오류로 실패했다. 환경의 `python.exe`를 직접 쓴다.
- 확인할 것: (1) 재현 검증 일치율 1.000, (2) 3 m/s 초과가 모두 n̂ < 2, (3) 2장 표의 옵션별 숫자.
- 한계: n̂는 5프레임 평균이라 정각 프레임 머리 수가 아니다. 실제 머리 수 분포는 재분석(5장) 때만 알 수 있다. 머리 점은 저장하지 않는다(CLAUDE.md). 대신 재분석 뒤 새 timeline에서 `vx` null 비율과 3 m/s 초과 개수를 다시 잰다.

## 2. 선택지와 권장

### 2.1 시뮬레이션 결과 (판정 셀, 값 있음 / > 0.02 / 최대 P)
- (a)는 n̂ < k인 초의 셀 속도를 창에서 빼고 그 초 pressure를 null로 한다. (b)는 셀 평균 속력에만 적용한 근사다(실제 구현은 머리별이라 결과가 조금 다르다).

  | 옵션 | E04_039 | E05_035 | E05_038 |
  |---|---|---|---|
  | 현재 (min_heads=1) | 227 / 6 / 0.026 | 172 / 130 / 0.202 | 270 / 268 / 0.804 |
  | (a) min_heads=2 | 149 / **0** / 0.017 | 11 / 10 / 0.052 | 30 / 30 / 0.149 |
  | (a) min_heads=3 | 93 / 0 / 0.016 | 3 / 3 / 0.039 | 0 / 0 / – |
  | (b1) 3 m/s로 자르기 | 227 / 6 / 0.026 | 172 / 130 / 0.202 | 270 / 268 / 0.788 |
  | (b2) 3 m/s 넘는 표본 버리기 | 227 / 6 / 0.026 | 172 / 130 / 0.202 | 266 / 264 / 0.606 |
  | (d) min_heads=2 + 3 m/s 자르기 | 149 / 0 / 0.017 | 11 / 10 / 0.052 | 30 / 30 / 0.149 |

- 판정 셀 속도(`vx`) 값이 남는 셀-초:

  | k | E04_039 | E05_035 | E05_038 |
  |---|---|---|---|
  | 1 (현재) | 287 | 1274 | 847 |
  | 2 | 221 (77%) | 288 (23%) | 333 (39%) |
  | 3 | 154 (54%) | 94 (7%) | 125 (15%) |

- ρ ≥ 3 셀-초는 E04_039에 1개뿐이고, k = 1·2·3 모두 압력 값이 남는다. 고밀도 탐지를 잃는 경우는 없다.

### 2.2 선택지 평가
- **(a) `min_heads` 기본값 상향** — 권장 (k = 2)
  - 원인 1번(머리 1개 셀)을 직접 막는다. 코드 변경 1줄 + 검사. `analyze.py`를 고치지 않아도 반영된다.
  - E04_039의 0.02 초과 6개가 0개가 된다(최대 0.017). E05의 초과는 크게 줄지만(268 → 30, 130 → 10) 0이 되지 않는다. 남는 이유는 0.3절 2번이다.
  - 대가: 저밀도 셀의 표시 속도(`vx`)가 null이 많아진다(E05_035 23%만 남음). 머리 1개 속도는 6.37 m/s 같은 값이라 표시에도 믿기 어렵다고 본다.
  - k = 3은 E05_038 압력이 모두 사라지고 속도도 7~15%만 남아 과하다.
- **(b) 속력 상한** — 권장하지 않음 (보류)
  - 3 m/s 초과 셀-초가 영상당 1~9개라 압력 초과 수에 거의 영향이 없다(268 → 264). 초과는 이상치가 아니라 0.3~1.5 m/s 사이 분산에서 나온다.
  - 3 m/s 초과는 모두 n̂ < 2라 (a) k = 2가 대부분 함께 걸러낸다. (d)가 (a)와 같은 숫자인 이유다.
  - 자르기는 달리는 사람(3~5 m/s, 실제 위험 신호일 수 있음)을 숨긴다. 버리기는 유효 표본을 줄인다. 정할 근거가 부족하다.
- **(c) `noise_var` 전달** — 권장하지 않음 (지금)
  - `measure_noise_floor`는 정지 표시 구간이 필요하다. 실시간 CCTV 입력에는 "사람이 서 있는 구간" 표시가 없고, 만들려면 별도 측정·설정(구역 설정 파일에 셀별 값)이 필요하다.
  - 셀마다 상수 하나를 빼는 방식이라, 시간마다 바뀌는 머리 수(1/n̂ 항, 0.2절 회귀)를 따라가지 못한다. 머리 1개 초와 10개 초에 같은 값을 뺀다.
  - 후속 안건으로 남긴다(7장 D5).
- **(d) 조합** — (a) k = 2 + (b)는 (a)와 결과가 같아 이득이 없다. (a) + 서버 밀도 하한(PR #63)을 권장한다.

### 2.3 권장 (제안)
- `min_heads` 기본값 1 → **2**, 값 검사 추가. 속력 상한·`noise_var`는 하지 않는다.
- `meta.models.flow`에 `mh{min_heads}`를 붙여 어떤 설정으로 만든 timeline인지 남긴다(재현성 규칙). 규격 키는 그대로이고 문자열 값만 바뀐다. (D3)
- PR #63 밀도 하한은 **유지**한다(6장).

## 3. 코드 변경 (`src/flow/run_flow.py`만)

### 3.1 기본값과 검사
```python
def analyze_video(
    video_path: Path,
    timeline_in: Path,
    timeline_out: Path,
    estimator: FlowEstimator,
    *,
    heads: Sequence[np.ndarray],
    h_head: np.ndarray,
    cell_origin_m: tuple[float, float],
    gap_frames: int = 1,
    noise_var: np.ndarray | None = None,
    window_s: float = 30.0,
    min_heads: int = 2,
    patch_radius_px: int = 6,
    inflow_min_heads: int = 0,
) -> dict:
```
- 함수 맨 앞 `gap_frames` 검사 바로 뒤에 추가:
```python
    if isinstance(min_heads, bool) or not isinstance(min_heads, int) \
            or min_heads < 1:
        raise ValueError(f"min_heads는 1 이상 정수여야 한다: {min_heads!r}")
```
  - 기존 `gap_frames` 검사 스타일(`isinstance(..., bool)` 먼저)과 맞춘다. 영상·파일을 열기 전에 거부하므로 출력 파일이 생기지 않는다.

### 3.2 docstring (83~85행 단락 교체)
```text
    유효 머리가 min_heads(기본 2, 가정)보다 적은 셀은 vx·vy·speed_var·
    pressure가 null이고 불안정 창에도 넣지 않는다. 머리 1개 셀의 속도는
    패치 잡음이 그대로 실려 3 m/s를 넘기도 한다 (11-18 실제 timeline:
    3 m/s 초과는 모두 추정 머리 2개 미만 셀). density > 0인데 그 초
    머리가 없으면 측정 못 함이라 null이다 (0 아님). min_heads가 1 이상
    정수(bool 제외)가 아니면 ValueError다.
    meta.models.flow는 "{estimator.name} head-r{patch_radius_px}
    mh{min_heads}"다.
```

### 3.3 `meta.models.flow` (D3 확정 시만)
```python
    meta.setdefault("models", {})["flow"] = (
        f"{estimator.name} head-r{patch_radius_px} mh{min_heads}"
    )
```

### 3.4 바꾸지 않는 것
- `_fill_frames`·`fill_flow_fields`·`TemporalInstability`·`noise_floor.py`·`ground.py`: 그대로. 기존 null 규칙이 이미 `min_heads`를 따른다.
- timeline 규격(`docs/timeline-spec.md`): 키·단위·자릿수 변경 없음. `vx` null이 늘어날 뿐이며 null은 규격 안의 값이다.

### 3.5 `analyze.py` 호출부 제안 (이유노 님께, 편집하지 않음)
- 기본값이 바뀌므로 **필수 변경은 없다.** 다만 어떤 값으로 돌렸는지 코드에서 보이도록 명시를 제안한다:
```python
    analyze_video(Path(args.video), out, out, FarnebackEstimator(), heads=heads,
                  h_head=np.array(cfg["head_plane"]["H_head_img_to_ground"]),
                  cell_origin_m=tuple(cfg["cell_origin_m"]), min_heads=2)
```
- 제안 문구: "흐름 단계에서 머리 1개 셀의 속도·압력을 null로 바꿨습니다(`min_heads` 기본 1 → 2). `analyze.py`는 안 고쳐도 반영되지만, 값을 드러내려면 호출에 `min_heads=2` 한 인자만 더해 주세요. 그리고 세 영상 재분석을 부탁드립니다(5장)."

## 4. TDD 단계 (`tests/flow/test_run_flow.py`, 합성 픽스처만)
- 실행: `python -m pytest tests/flow -q` (crowdsight 환경). 실제 영상·timeline·가중치를 쓰지 않는다.

### 4.1 단계 1 — 기본값으로 머리 1개 셀은 null (RED → GREEN)
```python
def test_single_head_cell_is_null_by_default(tmp_path: Path) -> None:
    """min_heads 기본값(2)에서 머리 1개 셀은 vx·vy·speed_var·pressure null.

    t=1에 c-0000(ρ 4.0) 머리를 1개만 둔다. 다른 셀은 4개라 vx 1.0.
    """
    heads = _heads(2)
    heads[1] = np.vstack(
        [_cell_heads(0, 1)] + [_cell_heads(i) for i in (1, 2, 3)]
    )
    result = _run_stub(tmp_path, 2, lambda call: _uniform(2.0), heads=heads)
    cell = result["frames"][1]["cells"][0]
    assert cell["vx"] is None and cell["vy"] is None
    assert cell["speed_var"] is None and cell["pressure"] is None
    assert result["frames"][1]["cells"][1]["vx"] == 1.0
```
- 현재 기본값 1에서는 `vx == 1.0`이라 실패한다. 기본값을 2로 바꾸면 통과한다.

### 4.2 단계 2 — `min_heads=1`을 넘기면 예전 동작 (회귀 보호)
```python
def test_min_heads_one_keeps_single_head_cell(tmp_path: Path) -> None:
    """min_heads=1을 명시하면 머리 1개 셀도 속도를 낸다 (예전 기본 동작)."""
    heads = _heads(2)
    heads[1] = np.vstack(
        [_cell_heads(0, 1)] + [_cell_heads(i) for i in (1, 2, 3)]
    )
    result = _run_stub(
        tmp_path, 2, lambda call: _uniform(2.0), heads=heads, min_heads=1,
    )
    assert result["frames"][1]["cells"][0]["vx"] == 1.0
```
- 단계 1 이후 바로 GREEN이어야 한다(동작 확인용). 이 테스트는 RED를 거치지 않는다고 PR에 적는다.

### 4.3 단계 3 — 값 검사
```python
@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_rejects_bad_min_heads(tmp_path: Path, bad: object) -> None:
    """min_heads가 1 이상 정수(bool 제외)가 아니면 ValueError, 출력 없음."""
    video, timeline_in, _ = _prepare(tmp_path, [2])
    out = tmp_path / "out" / "o.json"
    with pytest.raises(ValueError, match="min_heads"):
        analyze_video(
            video, timeline_in, out,
            _StubEstimator(lambda call: _uniform(2.0)),
            **_head_kw(1, {"min_heads": bad}),
        )
    assert not out.exists()
```

### 4.4 단계 4 — `models.flow` 문자열 (D3 확정 시만)
- `test_keeps_counting_fields_and_sets_flow_model` 기대값을 `"farneback-cv2 head-r6 mh2"`로 바꾼다(RED) → 3.3 변경(GREEN).

### 4.5 기존 테스트 영향
- `grep -n "min_heads\|noise_var" tests/flow/` 결과: `test_low_quality_cell_sample_is_kept_out_of_window`(min_heads=2 명시, 그대로 통과), `test_noise_var_is_subtracted_from_speed_var`(머리 4개, 영향 없음), `test_inflow_min_heads_forces_null`(`inflow_min_heads`라 별개), `tests/flow/test_cells.py`의 `noise_var`(`TemporalInstability` 단위, 영향 없음).
- 셀마다 머리 4개(혼합 테스트는 3개)라 기본값 2에서도 기존 기대값이 같다. 단계 4를 하면 `models.flow` 단언 1개만 바뀐다.
- 마지막에 `python -m pytest tests -q` 전체를 돌려 `tests/predict`·`tests/counting`도 통과하는지 본다.

## 5. 병합 뒤 재분석 절차
1. **재분석 (이유노 님 PC)**: 영상과 P2PNet 가중치가 이유노 님 PC에만 있다. 영상당 약 8.5분.
   ```
   python -m src.counting.analyze --homography infra/homography/E04_039.json --video data/processed/g1/E04_039.mp4 --out data/processed/timeline/E04_039.json
   python -m src.counting.analyze --homography infra/homography/E05_035.json --video <E05_035 영상> --out data/processed/timeline/E05_035.json
   python -m src.counting.analyze --homography infra/homography/E05_038.json --video <E05_038 영상> --out data/processed/timeline/E05_038.json
   ```
   - 주의: 실행하면 git에 올라간 `outputs/g1/{영상}_counts.csv`·`outputs/e8/{영상}_analysis_time.json`이 덮어써진다. 인원 추정은 바뀌지 않으므로 counts CSV가 같아야 한다. 다르면 원인을 먼저 본다. 기록할 생각이 없으면 `git restore outputs/g1 outputs/e8`로 되돌린다.
   - 새 timeline을 조영준에게 전달한다(`data/`는 git 제외).
2. **확인 (조영준)**: 부록 A 스크립트를 새 timeline에 돌린다. 기대: 판정 셀 3 m/s 초과 0개(머리 2개 이상 셀에서는 0.2절 기준 최대 2.12 m/s), E04_039 0.02 초과 0개, `meta.models.flow`에 `mh2`(D3 시).
   - 시뮬레이션(2.1절)과 다를 수 있다: 실제 머리 수는 n̂와 다르다. 차이가 크면 결과 문서에 적는다.
3. **E5 다시 돌리기 (PR #62 병합 뒤)**: `cd server; ./gradlew e5Sweep` → `python -m src.flow.e5.report`. `outputs/e5/*_e5.md`의 압력 기준 민감도 표를 새 값으로 갱신한다.
4. **서버 재생 확인**: 서버를 새 timeline으로 띄워 E05 두 영상에서 INSTABILITY·GRADE_UP(심각)가 0건인지 본다(밀도 하한 켬). 하한을 0으로 끈 실행도 한 번 해서 흐름 수정만의 효과(E04_039 0건, E05 감소)를 기록한다.

## 6. PR #63(서버 밀도 하한)과의 관계
- 두 수정은 독립이고 함께 둘 수 있다. #63은 판정 단계, 이 수정은 측정 단계다.
- **하한은 유지한다 (제안).** 2.1절에서 k = 2여도 E05_038 30개·E05_035 10개가 0.02를 넘는다. 이는 저밀도 자유 보행의 실제 분산이라 흐름 쪽에서 없앨 수 없다. 문헌도 난류를 고밀도 현상으로 본다.
- 이 수정의 몫: 머리 1개 셀의 엉뚱한 속도(표시·예측 입력)와 E04_039의 작은 초과를 없앤다. 압력 값 자체가 덜 시끄러워져 E5 민감도 분석이 깨끗해진다.

## 7. 결정 표

| # | 항목 | 제안 | 상태 | 누구 |
|---|---|---|---|---|
| D1 | `min_heads` 기본값 | 2 | **확정** (11-18 사용자) | 사용자 |
| D2 | 속력 상한 | 하지 않음(보류). 3 m/s 초과는 k = 2가 거의 걸러냄 | **확정** (11-18 사용자) | 사용자 |
| D3 | `meta.models.flow`에 `mh{min_heads}` 붙임 | 붙임 | **확정** (11-18 사용자) | 사용자·이유노 |
| D4 | `analyze.py`에 `min_heads=2` 명시 | 명시(선택) | 제안 (이유노 님 판단) | 이유노 |
| D5 | `noise_var`(잡음 바닥) | 후속. 정지 구간 정의가 필요 | **확정** (11-18 사용자) | 사용자 |
| D6 | PR #63 밀도 하한 3.0 | 유지 | **확정** (11-18 사용자) | 사용자 |
| D7 | 재분석·E5 재실행 시점 | 동결(11-19) 뒤, 발표 자료 숫자 갱신 여부와 함께 | **확정** (11-18 사용자) | 사용자·이유노 |

## 8. 위험
- **동결 뒤 timeline 숫자 변경**: 발표 자료·E5 결과(`outputs/e5`)·기획서의 압력 숫자가 바뀐다. 재분석 전 숫자로 발표할지 먼저 정한다(D7).
- **표시 속도 공백 증가**: E05_035 판정 셀 속도가 23%만 남는다(n̂ 근사). 웹 속력 칸이 "-"로 자주 보인다. 저밀도라 운영상 손실은 작다고 본다.
- **예측 `flow` 예측기**: `vx` null이 늘면 이류할 속도가 줄어든다. 현재 설정은 `persistence`라 영향 없음. `flow`로 바꿀 경우 E6를 다시 본다.
- **근사 한계**: n̂는 5프레임 평균이고 (b) 시뮬레이션은 셀 평균에만 적용했다. 실제 효과는 재분석으로만 확정된다.
- **실제 고밀도에서 머리 1개 셀**: 고밀도에서는 머리 수가 많아 해당 없음. 단 P2PNet 미검출(가림)로 머리 수가 적게 나오면 null이 될 수 있다. E04_039 ρ ≥ 3 셀-초 1개는 k = 2에서도 값이 남았다.

## 9. 커밋 제안
- `fix: 흐름 머리 1개 셀은 속도·압력을 비운다 (min_heads 기본 2)`
- 범위: `src/flow/run_flow.py`, `tests/flow/test_run_flow.py`, 이 계획 문서.

## 부록 A. 측정 스크립트 (저장소 밖 `%TEMP%/flowsim/sim.py`)
- 핵심 계산만 적는다(전체는 같은 폴더). 저장된 `vx`·`vy`에 마스크를 씌워 30초 창 분산(유효 24개 이상)을 다시 내고, `P = round(round(ρ,2) × round(S,4), 4)`, 마스크된 초는 null로 센다.
```python
def window_var(vx, vy, mask):
    v = np.stack([vx, vy], -1); v[~mask] = np.nan
    S = np.full(vx.shape, np.nan)
    for t in range(29, len(vx)):
        b = v[t - 29:t + 1]
        u = np.nanmean(b, 0); raw = np.nanmean(((b - u) ** 2).sum(-1), 0)
        raw[np.isfinite(b).all(-1).sum(0) < 24] = np.nan
        S[t] = raw
    return S

nhat = rho * area                       # 추정 머리 수 (5프레임 평균)
ok_k = np.isfinite(vx) & np.isfinite(vy) & (nhat >= k)   # (a)
```

## 변경 이력
| 버전 | 날짜 | 내용 |
|---|---|---|
| v1 | 2026-11-18 | 최초 작성. 실제 timeline 3개로 원인 측정·옵션 시뮬레이션, 권장 (a) min_heads=2 + #63 하한 유지 |
| v1.1 | 11-18 | 사용자 "추천안대로 진행": D1~D3·D5~D7 확정, D4는 이유노 님 판단. 구현은 코드 동결(11-19) 뒤 |
