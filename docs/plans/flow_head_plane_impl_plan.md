# 흐름 속도를 머리 높이 평면으로 계산하기: 구현 계획

| 항목 | 내용 |
|---|---|
| 브랜치 | `feat/flow-head-plane` (PR #32 `feat/flow-timeline-v01` 위에 쌓음) |
| 근거 | `docs/decisions-2026-11-11.md` 결정 3, `docs/timeline-spec.md` v0.2 8절·9절 4번 |
| 기한 | 11-13 |
| 범위 밖 (다음 PR) | `counterflow` 필드 쓰기, `inflow_ratio` 소수 4자리, RAFT 미세조정 |
| 테스트 명령 | `conda run -n crowdsight python -m pytest tests/flow -q` |

## 0. 코드를 읽고 확인한 것

### 0.1 그대로 쓰는 것
- **시간 맞춤.** `run_density.main`은 초 t마다 `round((t + off)·fps)` 프레임을 센다. `off = linspace(-0.4, 0.4, 5)`의 가운데 값이 0.0이라 가운데 프레임 = 흐름 시작 프레임 `int(round(t·fps))`. (가정) `counter.avg_frames`는 홀수. 짝수면 통합 스크립트가 `round(t·fps)` 프레임에서 P2PNet을 한 번 더 돌린다.
- **`reduce_to_cells(cell_ids, vel, n_cells)`**: `(N,)`·`(N, 2)` 입력, −1과 NaN은 버림. 머리 하나를 표본 하나로 넣으면 그대로 쓴다 (`count` = 유효 머리 수, `mean_v` = 머리 속도 평균).
- **`inflow_ratio(cell_ids, vel, is_boundary, inward, ...)`**: 표본 입력이라 그대로 맞는다. 이름만 `min_pixels` → `min_samples` (5단계).
- **`boundary_inward`, `TemporalInstability`, `fill_flow_fields`**: 바꾸지 않는다. `quality`·`min_quality` 의미만 "머리 수" (docstring).

### 0.2 고칠 것
**H 부호.** `infra/homography/E04_039.json` 두 행렬은 보행 영역에서 동차 w가 음수다.

| 화면 점 (px) | w |
|---|---|
| (0, 0) | +1.0 (지평선 너머) |
| (1919, 0) | +2.07 |
| (960, 540) | −9.16 (보행 영역) |
| (0, 1079) | −20.4 |
| (1919, 1079) | −19.3 |

- H와 −H는 같은 사상이라 부호는 임의다. `ground._dehomog`의 `w > _MIN_W` 규칙을 그대로 쓰면 보행 영역 전부 NaN.
- 기존 셀 호모그래피는 `cv2.getPerspectiveTransform`이 h33 = 1로 맞춰 문제가 없었다.
- 해결: `orient_homography`(T1)로 셀 중심에서 w > 0이 되게 부호를 맞춘 뒤 `_MIN_W` 규칙을 쓴다.

**화면 가장자리 머리.** 패치가 화면 밖에 걸친다고 머리를 버리지 않는다 (경계 셀 표본이 줄어 유입 비율에 불리).
- 패치 중심 `rint(p)`가 화면 밖이면 버린다.
- 안이면 화면 밖 패치 픽셀만 빼고 중앙값.

**셀 배정은 지면 좌표.** `image_polygon`은 바닥 평면 셀이라 머리(유효 높이 0.95 m)가 들어 있는 다각형은 그 사람이 선 셀이 아니다 (약 2.4 m 밀림).
- 인원 세기 `count_cells`와 같은 식: `(col, row) = floor((H_head(p) − cell_origin_m) / cell_m)`. 셀에서 센 머리 = 그 셀 속도에 들어간 머리.
- 그래서 픽셀 → 셀 번호표가 흐름에서 필요 없다. `build_cell_index`는 지운다. `cell_index_map`(counting)도 흐름에서 안 쓴다.
- [토론] 결정 2의 "`cell_index_map` 사용"이 결정 3으로 바뀐다. 이유노 님께 알리고 문서 수정을 부탁한다.
- 셀 크기는 `meta.cell_size_m` (`count_cells`는 2.0 고정, 지금 같음).

### 0.3 `cell_origin_m`은 입력으로 받는다
- timeline `meta`에 없고 구역 설정 파일에만 있다. `h_head`와 함께 배열로 받고, 설정 파일 로더 `load_head_plane`(T5)을 따로 둔다.
- `E04_022.json`에는 `head_plane`·`cell_origin_m`이 없다 → `ValueError`.

## 1. 데이터 흐름

```text
heads[t] (N,2) px    (통합 스크립트가 메모리로 넘김, 저장 안 함)
  ├─ flow = estimator.estimate(frame[round(t·fps)], frame[+gap])
  ├─ d   = sample_head_flow(flow, heads[t], r)       # T2, (N,2) px
  │   del flow
  ├─ g, v = head_ground_velocity(heads[t], d, H, dt) # T3, m, m/s
  ├─ ids = head_cell_ids(g, cells, origin, cell_m)   # T4, (N,)
  ├─ cf  = reduce_to_cells(ids, v, n_cells)          # 그대로
  ├─ TemporalInstability.update(...)                 # 그대로
  ├─ fill_flow_fields(..., cf.count, min_heads)      # 그대로
  └─ inflow_ratio(ids, v, ..., min_samples=...)      # 이름만 바꿈
```
`H`는 영상당 한 번: `orient_homography(h_head, 셀 중심 px)`.

## 2. 테스트 경계

T1~T4는 `src/flow/ground.py`에 둔다. 모듈 docstring은 "머리 점 변위를 머리 높이 평면으로 지면 속도로 바꾼다". `_MIN_W`, `_dehomog`은 남긴다.

### T1. `orient_homography`
```python
def orient_homography(
    h: np.ndarray, ref_px: np.ndarray,
) -> np.ndarray:
    """ref_px 점들에서 동차 w가 양수가 되도록 부호를 맞춘 H 사본을 준다.

    H와 −H는 같은 사상이라 부호는 임의다. E04_039 행렬은 보행
    영역에서 w < 0이다. 그래서 w ≤ 1e-9 버림 규칙을 쓰기 전에
    부호를 맞춘다. ref_px는 (M, 2) px이며 보통 셀 다각형 중심이다.
    h가 (3, 3) 유한 행렬이 아니거나 ref_px가 (M ≥ 1, 2)가 아니면
    ValueError다. ref_px의 w가 0 근처(|w| ≤ 1e-9)이거나 부호가
    섞이면(지평선이 셀을 지남) 설정 오류라 ValueError다.
    """
```
| 사례 | 입력 | 기대 |
|---|---|---|
| 이미 양수 | `h = I`, `ref = [[1, 1]]` | `I` (사본, 입력 불변) |
| 뒤집기 | `h = −I` | `I` |
| E04_039 실제 | `ref` = `build_cells` 셀 중심 | 모든 ref에서 w > 0 |
| 부호 섞임 | `h = [[1,0,0],[0,1,0],[0,−0.1,1]]`, `ref = [[0,5],[0,15]]` | `ValueError` |
| 모양 오류 | `(2, 3)`, NaN 행렬, 빈 `ref` | `ValueError` |

### T2. `sample_head_flow`
```python
def sample_head_flow(
    flow: np.ndarray, heads_px: np.ndarray, radius_px: int,
) -> np.ndarray:
    """머리 점마다 주변 패치 흐름의 성분별 중앙값 (N, 2) px를 준다.

    패치 중심은 np.rint(heads_px) (x, y)이고 크기는 (2r+1)²다.
    화면 밖 패치 픽셀과 NaN 픽셀은 빼고 중앙값을 낸다. 중심이 화면
    밖이거나 남는 픽셀이 없으면 그 머리는 NaN이다. 머리가 0개면
    (0, 2)를 준다. flow가 (H, W, 2)가 아니거나, heads_px가 유한한
    (N, 2)가 아니거나, radius_px가 0 이상 정수(bool 제외)가 아니면
    ValueError다.
    """
```
반복문 없는 구현:
```python
    h, w = flow.shape[:2]
    c = np.rint(heads_px).astype(np.int64)          # (N, 2) x, y
    off = np.arange(-radius_px, radius_px + 1)
    ox, oy = np.meshgrid(off, off)
    xs = c[:, :1] + ox.ravel()                       # (N, K)
    ys = c[:, 1:] + oy.ravel()
    inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    patch = flow[ys.clip(0, h - 1), xs.clip(0, w - 1)]
    patch = patch.astype(np.float64)                 # (N, K, 2)
    patch[~inside] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # 빈 패치
        disp = np.nanmedian(patch, axis=1)
    disp[~inside[:, off.size ** 2 // 2]] = np.nan    # 중심이 화면 밖
    return disp
```
| 사례 | 입력 | 기대 |
|---|---|---|
| 균일 흐름 | 20×20 흐름 (2, −1), 머리 (10, 10), r = 2 | (2, −1) |
| 중앙값 | r = 1, 3×3 중 4칸 dx = 10, 나머지 0 | dx = 0 |
| 같은 패치, 5칸 | 5칸 dx = 10 | dx = 10 |
| 모서리 | 머리 (0, 0), r = 2, 균일 (2, 0) | (2, 0) (화면 안 9칸) |
| 반올림 경계 | x = −0.4 | 살아남음 |
| 반올림 경계 | x = −0.6, 또는 x = W − 0.4 | NaN |
| NaN 섞임 / 전부 | 일부 / 전부 NaN | 나머지 중앙값 / NaN, 경고 없음 |
| 빈 입력 | 머리 0개 | `(0, 2)` |
| 입력 오류 | heads NaN, `(N, 3)`, r = −1, r = True, flow `(H, W)` | `ValueError` |

### T3. `head_ground_velocity`
```python
def head_ground_velocity(
    heads_px: np.ndarray,
    disp_px: np.ndarray,
    h_head: np.ndarray,
    dt_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """머리 점의 지면 위치 g (N, 2) m와 지면 속도 v (N, 2) m/s를 준다.

    g = H(p), g' = H(p + d), v = (g' − g) / dt (규격 v0.2 8절).
    두 끝점 모두 투영 변환을 그대로 쓴다 (p에서의 선형 근사 아님).
    h_head는 orient_homography를 거친 머리 높이 평면 행렬이다.
    시작점 w ≤ 1e-9면 g·v가 모두 NaN이고, 끝점만 그러면 v만 NaN이다.
    d가 NaN인 머리는 v가 NaN이다. 모양이 맞지 않거나 dt_s ≤ 0이면
    ValueError다.
    """
```
| 사례 | 입력 | 기대 |
|---|---|---|
| 배율 | `H = diag(0.05, 0.05, 1)`, p (10, 20), d (2, 0), dt 0.1 | g = (0.5, 1.0), v = (1.0, 0.0) |
| 투영 | `H = [[1,0,0],[0,1,0],[0,0.01,1]]`, p (0, 0), d (0, 10), dt 1 | v = (0, 9.0909) (1e-6) |
| 끝점 지평선 | `H = [[1,0,0],[0,1,0],[0,−0.1,1]]`, p (5, 5), d (0, 10) | g 유한, v NaN |
| 시작점 지평선 | 같은 H, p (5, 12) | g·v NaN |
| d NaN | | g 유한, v NaN |
| 오류 | dt = 0, 모양 불일치 | `ValueError` |

### T4. `head_cell_ids`
```python
def head_cell_ids(
    ground_m: np.ndarray,
    cells: list[dict],
    origin_m: tuple[float, float],
    cell_m: float,
) -> np.ndarray:
    """지면 점 (N, 2) m마다 meta.cells 순서의 셀 번호 (N,) int64를 준다.

    인원 세기(src/counting/run_density.py count_cells)와 같은 규칙:
    (col, row) = floor((g − origin_m) / cell_m). 그 (row, col)이
    cells에 없거나 g가 유한하지 않으면 −1이다. 같은 (row, col)이
    두 번 나오면 ValueError다.
    """
```
공통: cells (0,0), (0,1), (1,0), `origin = (−0.5, −1.34)`, `cell_m = 2`.

| g (m) | 기대 |
|---|---|
| (−0.5, −1.34) | 0 |
| (1.5, −1.34) | 1 |
| (1.49, 0.65) | 0 |
| (1.6, 0.7) | −1 (row 1, col 1 없음) |
| (−0.6, 0) | −1 |
| NaN | −1 |

- 빈 입력 `(0, 2)` → `(0,)`.
- 무작위 200점(시드 0)으로 `np.bincount(ids[ids >= 0], minlength=n)` == `count_cells(...)`.

### T5. `load_head_plane` (`src/flow/run_flow.py`)
```python
def load_head_plane(
    config_path: Path,
) -> tuple[np.ndarray, tuple[float, float]]:
    """구역 설정 파일에서 머리 높이 평면 행렬과 셀 원점을 읽는다.

    head_plane.H_head_img_to_ground (3, 3)와 cell_origin_m (x, y) m를
    돌려준다. 키가 없거나(E04_022처럼 머리 평면이 없는 설정) 모양이
    맞지 않으면 ValueError다.
    """
```
| 사례 | 기대 |
|---|---|
| `E04_039.json` | (3, 3), `(−0.5, −1.34)` |
| `E04_022.json` | `ValueError` |
| tmp JSON 2×3 행렬 | `ValueError` |

### T6. `analyze_video` (통합)
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
    min_heads: int = 1,
    patch_radius_px: int = 6,
    inflow_min_heads: int = 0,
) -> dict:
    """인원 추정 타임라인의 각 프레임 t에 흐름 필드를 채워 쓰고 돌려준다.

    heads[t]는 round(t·fps) 프레임의 머리 점 (N, 2) 원본 px다.
    통합 분석 스크립트가 같은 프로세스 안에서 메모리로만 넘기며,
    이 함수도 파일·반환값 어디에도 남기지 않는다 (규격 9절 4번).
    머리마다 반경 patch_radius_px 패치 흐름의 중앙값을 h_head로
    지면 속도(m/s)로 바꾸고, count_cells와 같은 규칙으로 셀에 넣어
    셀 평균을 낸다. 유효 머리가 min_heads보다 적은 셀은
    vx·vy·speed_var·pressure가 null이고 불안정 창에도 넣지 않는다.
    (이하 기존 규칙 유지.)
    len(heads)가 프레임 수와 다르거나, heads[t]가 유한한 (N, 2)가
    아니거나, h_head가 (3, 3)이 아니면 ValueError다.
    """
```
새 인자는 키워드 전용.

**합성 시험 고정값.**
- `H = diag(0.05, 0.05, 1)`, `origin = (0.1, 1.2)` → col = ⌊(x − 2) / 40⌋, row = ⌊(y − 24) / 40⌋.
- 멈춘 셀을 col 1에서 col 3(x 122~162)으로 옮긴다 (`c-0003`, `c-0103`).
- 셀 중심 (1,1), (7,1), (1,3), (7,3) m, 구역 중심 (4, 2) m. +x 움직임이면 경계 셀 내적 양수 → 기존 유입 기대값 1.0 유지.
- `_heads(n, per_cell)`: 셀마다 4점, 셀 중심 ± 8 px.

| 사례 | 기대 |
|---|---|
| 기존 속도 시험 (Farneback, 2 px/프레임) | vx ≈ 1.0 ± 0.1 |
| 기존 gap = 2, fps 7.5 쌍 시험 | 그대로 |
| `h_head = −diag(0.05, 0.05, 1)` | 결과 같음 (부호 둘 다 parametrize) |
| density > 0, 그 초 머리 0개 | vx·vy·speed_var·pressure null |
| density 0 셀에 머리 있음 | vx null, pressure 0 |
| 셀 밖·화면 밖 머리 | 영향 없음, 오류 없음 |
| 모든 초 `np.empty((0, 2))` | 모든 vx null, inflow null, 파일 정상 |
| `len(heads) != len(frames)` | `ValueError`, 출력 파일 없음 |
| `heads[1]` NaN 또는 `(N, 3)` | `ValueError` |
| `h_head` `(2, 3)` | `ValueError` |
| 머리 점이 파일에 남지 않음 | 출력 frame·cell 키 집합 = 입력, 폴더에 파일 1개 |

**기존 스텁 시험 바꾸기.**
- `test_low_quality_cell_sample_is_kept_out_of_window`: `min_heads = 2`, t = 1에만 `c-0000` 머리 1개, 그 위치 흐름 10 px → t = 1 vx null, t = 4 `speed_var` 0.0.
- `test_inflow_min_pixels_forces_null` → `inflow_min_heads`: 경계 셀 `c-0000` 움직이는 머리 4개, `(4, 1.0)`·`(5, None)`.
- `test_inflow_ratio_is_rounded_to_two_decimals`: `c-0000` 머리 3개 (+x 1, −x 2) → 0.33.
- `test_rejects_bad_cell_polygon`: 삭제.
- 나머지는 `_run`·`_run_stub`이 기본 `heads`·`h_head`·`cell_origin_m`을 넘기게 고치고 기대값 유지.

## 3. 기존 규칙과의 관계
| 항목 | 처리 |
|---|---|
| 필드별 null | `fill_flow_fields` 그대로. 머리 0개 → `mean_v` NaN → null. density 0 규칙 우선 |
| density 5장 평균 vs 머리 1장 | density > 0인데 그 초 머리 0개 → 속도 null (측정 못 함 ≠ 0) |
| `TemporalInstability` | 그대로. 듬성한 셀은 `speed_var` null이 잦음. [토론] `min_valid_ratio` 0.8 조정 |
| 불안정 값 의미 | 셀 평균 속도 시간 분산에 사람 교체에 따른 속도 차도 들어감. [토론] 기획 정의와 맞는지 |
| `noise_var` | 의미가 "머리 평균 속도 잡음 분산"으로 바뀜. 다시 재야 함 |
| 원자적 쓰기 등 | 그대로 |
| `meta.models.flow` | (가정) `f"{estimator.name} head-r{patch_radius_px}"` → 시험 기대 `"farneback-cv2 head-r6"` |
| 유입 사람 있는 셀 필터 | 남김 |
| `count`, `counterflow` | 건드리지 않음 |

## 4. 성능
| 항목 | 지금 | 바꾼 뒤 |
|---|---|---|
| 프레임당 속도 계산 | `cell_velocity` 약 0.2 s | 머리 약 100 × 169칸 gather + nanmedian, 1 ms 안팎 (가정, `timeit` 확인) |
| 영상당 준비 | 약 190 MB | 3×3 행렬 |

## 5. 지우는 코드
- `src/flow/ground.py`: `build_cell_index`, `_polygon_points`, `cell_homographies`, `CellVelocityPlan`, `prepare_cell_velocity`, `cell_velocity`, `_COORD_TOL`, 안 쓰는 import. `_MIN_W`, `_dehomog`은 남김.
- `tests/flow/test_ground.py`: 기존 시험 전부 지우고 T1~T4로 다시 씀 (지평선 NaN → T3, 중복 (row, col) → T4로 의미 유지).
- `tests/flow/test_run_flow.py`: `test_rejects_bad_cell_polygon` 삭제.
- 남김: `src/counting/cells.py` `cell_index_map` (이유노 파일), `src/flow/cells.py` (docstring "픽셀" → "표본(머리)").

## 6. 통합 스크립트 연결 [토론] (이유노 님과)
```python
h_head, origin = load_head_plane(cfg_path)
heads: list[np.ndarray] = [np.empty((0, 2))] * duration
# 세는 반복문 안: 가운데 장(off == 0)이면 heads[t] = pts
analyze_video(
    video, timeline, timeline, estimator,
    heads=heads, h_head=h_head, cell_origin_m=origin,
)
del heads  # 저장하지 않는다
```
- [토론] 초별 목록 대신 초마다 부르는 방식이 필요한지.
- [토론] timeline dict를 바로 받는 메모리용 함수가 필요한지.
- [토론] CLAUDE.md "AI 모듈끼리는 timeline.json으로만"에 규격 9절 4번 예외 한 줄 (팀 합의 뒤).

## 7. 가정과 토론 항목
| 표시 | 항목 | 초기값 |
|---|---|---|
| (가정) [토론] | 패치 반경 r | 6 px (13×13). 1080p 머리 지름 약 15~40 px |
| (가정) | 패치 대표값 | 성분별 중앙값 |
| (가정) [토론] | `min_heads` | 1 |
| (가정) [토론] | `inflow_min_heads` | 0 (서버가 `count` < 3이면 유입 경보 끔, 결정 6) |
| (가정) | 시작점 지평선 너머 머리 | 버림 |
| (가정) | `counter.avg_frames` 홀수 | 가운데 장 = 흐름 시작 프레임 |
| [토론] | `min_valid_ratio` 0.8 | 듬성한 셀 `speed_var` null 증가 |

## 8. TDD 순서
단계마다 빨강 → 초록 → 정리. 단계 끝마다 `conda run -n crowdsight python -m pytest tests/flow -q` 전부 통과. 줄 79자 이하, 한국어 docstring.

1. T1 `orient_homography` — 사례 5개, E04_039 셀 중심 w > 0.
2. T2 `sample_head_flow` — 반복문 없음, `-W error::RuntimeWarning` 통과.
3. T3 `head_ground_velocity` — 손 계산과 1e-9.
4. T4 `head_cell_ids` — 표 + `count_cells` 일치.
5. `inflow_ratio` `min_pixels` → `min_samples`.
6. T5 `load_head_plane`, T6 `analyze_video` 전환 (고정값·오류 시험 먼저, `_fill_frames` 교체, 인자 이름·`meta.models.flow`·docstring).
7. 5절 코드 지우기 — `grep -rn "build_cell_index\|cell_homographies\|cell_velocity\|CellVelocityPlan" src tests` 결과 없음.
8. 실제 영상 확인 (수동, 저장 없음): E04_039 앞 30초, `head_points`로 머리를 구해 넘김. 사람 있는 셀 속력 중앙값 약 0.5~1.5 m/s, 프레임당 속도 계산 ≤ 10 ms. 결과는 PR 설명에 (머리 좌표 출력 금지).
