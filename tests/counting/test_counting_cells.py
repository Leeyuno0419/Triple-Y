"""src/counting/cells.py, fake_timeline.py 테스트."""
import numpy as np
import pytest

from src.counting.cells import build_cells, cell_index_map
from src.counting.fake_timeline import make_fake_timeline

# 100px = 1m 인 위에서 내려다본 카메라 (영상 1000×800 → 지면 10m×8m)
H_TOP = np.diag([0.01, 0.01, 1.0])
SIZE = (1000, 800)
FULL = [[0, 0], [1000, 0], [1000, 800], [0, 800]]


def test_full_floor_gives_regular_grid() -> None:
    """바닥 전체가 보행 가능하면 2m 셀 5×4개, 면적은 모두 4㎡."""
    cells = build_cells(H_TOP, FULL, SIZE)
    assert len(cells) == 20
    assert all(c["walkable_area_m2"] == 4.0 for c in cells)
    assert cells[0]["cell_id"] == "c-0000"
    assert cells[0]["image_polygon"] == [[0.0, 0.0], [0.2, 0.0], [0.2, 0.25], [0.0, 0.25]]


def test_partial_floor_area_and_small_cells_dropped() -> None:
    """왼쪽 5m만 바닥이면 3번째 열은 절반(2㎡), 4번째 열부터는 빠진다."""
    cells = build_cells(H_TOP, [[0, 0], [500, 0], [500, 800], [0, 800]], SIZE)
    by_col = {c["col"]: c["walkable_area_m2"] for c in cells}
    assert by_col == {0: 4.0, 1: 4.0, 2: 2.0}


def test_cells_outside_image_are_dropped() -> None:
    """꼭짓점이 영상 밖으로 나가는 셀은 image_polygon 규격(0~1) 때문에 뺀다."""
    cells = build_cells(H_TOP, [[0, 0], [1000, 0], [1000, 700], [0, 700]], (1000, 700))
    assert max(c["row"] for c in cells) == 2  # 7m 중 6m까지만 셀 3줄
    for c in cells:
        assert all(0 <= v <= 1 for p in c["image_polygon"] for v in p)


def test_fake_timeline_passes_spec_and_null_rules() -> None:
    """가짜 timeline은 규격 검사를 통과하고, 빈 셀은 vx·vy·speed_var가 null이다."""
    tl = make_fake_timeline(H_TOP, FULL, SIZE, "TEST_001", duration_s=40)
    assert tl["meta"]["zone_id"] == "zone-test-001"
    assert len(tl["frames"]) == 40
    for fr in tl["frames"]:
        for c in fr["cells"]:
            assert c["density_pred_60s"] is None
            if c["density"] == 0:
                assert c["vx"] is None and c["speed_var"] is None and c["pressure"] == 0.0


def test_fake_timeline_is_reproducible() -> None:
    """시드가 같으면 결과가 같다."""
    a = make_fake_timeline(H_TOP, FULL, SIZE, "T", duration_s=5, seed=1)
    b = make_fake_timeline(H_TOP, FULL, SIZE, "T", duration_s=5, seed=1)
    assert a == b


def test_cell_index_map_marks_cells_and_outside() -> None:
    """번호표는 셀 안 픽셀에 셀 번호를, 셀 밖에 -1을 적는다."""
    cells = build_cells(H_TOP, [[0, 0], [500, 0], [500, 800], [0, 800]], SIZE)
    idx = cell_index_map(cells, SIZE)
    assert idx.shape == (800, 1000)
    first = next(i for i, c in enumerate(cells) if c["cell_id"] == "c-0000")
    assert idx[50, 50] == first                       # 0~2m 셀 안
    assert idx[400, 900] == -1                         # 셀이 없는 오른쪽 (5m 밖)
    assert set(np.unique(idx)) == set(range(len(cells))) | {-1}


def test_fake_timeline_has_v02_fields() -> None:
    """v0.2 필드: 프레임에 구역 인원 count, 셀에 counterflow."""
    tl = make_fake_timeline(H_TOP, FULL, SIZE, "T", duration_s=3)
    fr = tl["frames"][0]
    assert isinstance(fr["count"], float)
    assert all("counterflow" in c for c in fr["cells"])


def test_too_large_grid_raises() -> None:
    """cell_id는 행·열 2자리라 100칸을 넘으면 오류."""
    with pytest.raises(ValueError):
        build_cells(np.diag([1.0, 1.0, 1.0]), FULL, SIZE)
