"""S8 seam: unsup_losses.backward_warp·sequence_unsup_loss 시험.

흐름은 (B, 2, H, W) px 단위이고 채널 0이 x(오른쪽 +), 채널 1이 y(아래 +)다.
기대값은 손으로 정한 영상과 이동량에서 숫자로 적는다.
광도·평활 손실, 앞뒤 일치 마스크 같은 내부 도우미는 직접 시험하지 않는다.
"""
from __future__ import annotations

import torch

from src.flow.unsup_losses import backward_warp, sequence_unsup_loss


def _ramp(h: int, w: int) -> torch.Tensor:
    """값이 10·y + x인 (1, 1, h, w) 영상을 만든다."""
    ys, xs = torch.meshgrid(
        torch.arange(h, dtype=torch.float32),
        torch.arange(w, dtype=torch.float32),
        indexing="ij",
    )
    return (10.0 * ys + xs).view(1, 1, h, w)


def test_zero_flow_warp_is_identity() -> None:
    """흐름 0이면 비틀린 영상은 원본과 같고, 모든 픽셀이 화면 안(1)이다."""
    img = _ramp(4, 5)
    flow = torch.zeros(1, 2, 4, 5)
    warped, inside = backward_warp(img, flow)
    torch.testing.assert_close(warped, img)
    torch.testing.assert_close(inside, torch.ones(1, 1, 4, 5))


def test_integer_shift_warp_samples_exact_pixels() -> None:
    """흐름 (x +2, y +1)이면 (y, x)는 원본 (y + 1, x + 2) 값이 된다.

    5×6 영상(값 10·y + x)에서 표본 위치가 화면 안인 곳은 y 0~3, x 0~3이다.
    그 밖은 화면 밖 마스크 0이다.
    """
    img = _ramp(5, 6)
    flow = torch.zeros(1, 2, 5, 6)
    flow[:, 0] = 2.0
    flow[:, 1] = 1.0
    warped, inside = backward_warp(img, flow)
    expected = torch.tensor([
        [12.0, 13.0, 14.0, 15.0],
        [22.0, 23.0, 24.0, 25.0],
        [32.0, 33.0, 34.0, 35.0],
        [42.0, 43.0, 44.0, 45.0],
    ])
    torch.testing.assert_close(warped[0, 0, :4, :4], expected)
    expected_inside = torch.zeros(5, 6)
    expected_inside[:4, :4] = 1.0
    torch.testing.assert_close(inside[0, 0], expected_inside)


def _texture(h: int, w: int, seed: int = 0) -> torch.Tensor:
    """시드 고정 무작위 무늬 (1, 3, h, w) 영상을 [0, 1] 범위로 만든다."""
    gen = torch.Generator().manual_seed(seed)
    return torch.rand(1, 3, h, w, generator=gen)


def _const_flow(h: int, w: int, dx: float, dy: float) -> torch.Tensor:
    """모든 픽셀이 (dx, dy)인 (1, 2, h, w) 흐름을 만든다."""
    flow = torch.zeros(1, 2, h, w)
    flow[:, 0] = dx
    flow[:, 1] = dy
    return flow


def test_identical_images_zero_flow_loss_is_near_zero() -> None:
    """같은 영상 두 장, 앞뒤 흐름 0이면 손실은 0에 가깝다 (1e-6 이하)."""
    img = _texture(16, 16)
    zero = torch.zeros(1, 2, 16, 16)
    region = torch.ones(1, 1, 16, 16)
    loss, _ = sequence_unsup_loss([zero], [zero], img, img.clone(), region)
    assert float(loss) <= 1e-6


def _shifted_pair(
    dx: int, dy: int, size: int = 32, seed: int = 0
) -> tuple[torch.Tensor, torch.Tensor]:
    """img2(x, y) = img1(x - dx, y - dy)인 무늬 영상 쌍을 만든다.

    큰 무늬에서 두 창을 잘라내므로 두 영상 모두 테두리까지 무늬가 있다.
    img1의 (x, y)는 img2의 (x + dx, y + dy)로 옮겨 가므로 정답 앞 흐름은
    (dx, dy), 뒤 흐름은 (-dx, -dy)다.
    """
    pad = 4
    base = _texture(size + 2 * pad, size + 2 * pad, seed)
    img1 = base[:, :, pad:pad + size, pad:pad + size]
    img2 = base[:, :, pad - dy:pad - dy + size, pad - dx:pad - dx + size]
    return img1.clone(), img2.clone()


def _centre_region(size: int = 32, lo: int = 8, hi: int = 24) -> torch.Tensor:
    """가운데 [lo, hi) 정사각형만 1인 군중 영역 마스크를 만든다."""
    region = torch.zeros(1, 1, size, size)
    region[..., lo:hi, lo:hi] = 1.0
    return region


def test_wrong_flow_gives_larger_loss_than_correct_flow() -> None:
    """(x +3, y +2) 이동 쌍에서 흐름 0(오답)의 손실이 정답 흐름보다 크다."""
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    right12, right21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2)
    zero = torch.zeros(1, 2, 32, 32)
    loss_right, _ = sequence_unsup_loss(
        [right12], [right21], img1, img2, region
    )
    loss_wrong, _ = sequence_unsup_loss([zero], [zero], img1, img2, region)
    assert float(loss_wrong) > float(loss_right)


def test_constant_flow_on_shifted_images_loss_is_near_zero() -> None:
    """(x +3, y +2) 이동 쌍에 일정한 정답 흐름을 주면 손실은 0에 가깝다.

    영역은 가운데 16×16이라 비틀기 표본과 census 창이 모두 화면 안이다.
    일정한 흐름이므로 평활 손실도 0이다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2)
    loss, _ = sequence_unsup_loss([f12], [f21], img1, img2, region)
    assert float(loss) <= 1e-6


def test_pixels_outside_region_do_not_change_loss() -> None:
    """영역 밖 바깥 2px 테두리의 영상·흐름을 바꿔도 손실은 그대로다.

    영역 가운데 16×16(8~23)에서 흐름 ±1px, census 반경 3px이므로 손실이
    읽는 픽셀은 4~27 안이다. 테두리 0~1, 30~31은 그 밖이다.
    오답 흐름 (x +1)을 써서 손실이 0이 아닌 상태에서 비교한다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 1, 0), _const_flow(32, 32, -1, 0)
    before, _ = sequence_unsup_loss([f12], [f21], img1, img2, region)

    ring = torch.ones(32, 32, dtype=torch.bool)
    ring[2:30, 2:30] = False
    img1_c, img2_c = img1.clone(), img2.clone()
    img1_c[..., ring] = 1.0 - img1_c[..., ring]
    img2_c[..., ring] = 0.0
    f12_c, f21_c = f12.clone(), f21.clone()
    f12_c[..., ring] = 7.0
    f21_c[..., ring] = -5.0
    after, _ = sequence_unsup_loss([f12_c], [f21_c], img1_c, img2_c, region)

    assert float(before) > 0.1
    torch.testing.assert_close(after, before)


def test_brightness_change_barely_changes_loss_at_correct_flow() -> None:
    """img2 밝기를 0.8배 + 0.1로 바꿔도 정답 흐름의 손실은 거의 그대로다.

    census는 0~255 밝기 차이에 상수 0.81을 쓴다 (UFlow). 밝기 변화로 늘어난
    손실이 오답(흐름 0)과 정답의 손실 차이의 10% 미만이어야 한다.
    현재 약 4%다. [0, 1] 밝기로 census를 계산하면 약 28%가 되어 실패한다.
    """
    img1, img2 = _shifted_pair(3, 2)
    bright = img2 * 0.8 + 0.1
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2)
    zero = torch.zeros(1, 2, 32, 32)
    plain, _ = sequence_unsup_loss([f12], [f21], img1, img2, region)
    lit, _ = sequence_unsup_loss([f12], [f21], img1, bright, region)
    wrong, _ = sequence_unsup_loss([zero], [zero], img1, bright, region)
    ratio = (float(lit) - float(plain)) / (float(wrong) - float(plain))
    assert ratio < 0.1


def test_full_frame_region_correct_flow_loss_is_near_zero() -> None:
    """영역이 화면 전체여도 정답 흐름의 손실은 0에 가깝다.

    화면 테두리와 화면 밖 표본 경계에서는 census 창(7×7)이 0으로 채운
    픽셀을 읽는다. 손실이 마스크를 창 반경 3px만큼 깎아 이 픽셀을 뺀다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = torch.ones(1, 1, 32, 32)
    f12, f21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2)
    loss, _ = sequence_unsup_loss([f12], [f21], img1, img2, region)
    assert float(loss) <= 1e-6


def test_census_loss_per_pixel_is_bounded_by_robust_penalty() -> None:
    """census 손실은 픽셀마다 (|h| + 0.01)^0.4로 눌러 평균한다 (UFlow).

    soft hamming h는 49채널 각각 1 미만이므로 h < 49다. 한 방향 최대값은
    49.01^0.4 − 0.01^0.4 ≈ 4.585, 양방향 합은 9.171 미만이다.
    흐름 0(오답)으로 무늬 쌍을 맞춰도 이 상한을 넘지 않는다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    zero = torch.zeros(1, 2, 32, 32)
    loss, _ = sequence_unsup_loss([zero], [zero], img1, img2, region)
    assert 1.0 < float(loss) < 9.171


def test_earlier_iterations_are_weighted_by_gamma() -> None:
    """반복 [흐름 0, 정답]이면 손실 = 0.8 × 흐름 0만의 손실이다.

    가중치는 gamma^(N−1−i)이므로 앞 반복이 0.8, 마지막 반복이 1이다.
    정답 반복의 손실은 0이다. 가운데 영역에서는 두 경우의 가림 마스크가
    모두 1이라 같다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2)
    zero = torch.zeros(1, 2, 32, 32)
    only_zero, _ = sequence_unsup_loss([zero], [zero], img1, img2, region)
    seq, _ = sequence_unsup_loss(
        [zero, f12], [zero, f21], img1, img2, region, gamma=0.8
    )
    assert float(only_zero) > 1.0
    torch.testing.assert_close(seq, 0.8 * only_zero)


def test_wrong_backward_flow_alone_raises_loss() -> None:
    """앞 흐름은 정답, 뒤 흐름만 y 0.5px 틀리면 손실이 0보다 확실히 크다.

    차이 (0, −0.5)는 앞뒤 일치 검사 범위(0.5 + 1%) 안이라 가림으로
    빠지지 않는다. 뒤 방향 광도 항이 없다면 손실은 0이 된다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2.5)
    loss, _ = sequence_unsup_loss([f12], [f21], img1, img2, region)
    assert float(loss) > 1.0


def test_batch_of_duplicates_equals_single_loss() -> None:
    """같은 표본 2개를 묶은 B = 2 손실은 B = 1 손실과 같다 (평균 정규화)."""
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 1, 0), _const_flow(32, 32, -1, 0)
    single, _ = sequence_unsup_loss([f12], [f21], img1, img2, region)

    def two(x: torch.Tensor) -> torch.Tensor:
        """배치 축으로 두 번 잇는다."""
        return torch.cat([x, x], dim=0)

    double, _ = sequence_unsup_loss(
        [two(f12)], [two(f21)], two(img1), two(img2), two(region)
    )
    assert float(single) > 1.0
    torch.testing.assert_close(double, single)


def test_log_reports_terms_and_valid_fraction() -> None:
    """기록에는 광도·평활 항과 앞 방향 유효 픽셀 비율이 따로 들어간다.

    가운데 16×16 영역, 정답 흐름이면 가림·화면 밖이 없으므로 유효 비율은
    256 / 1024 = 0.25다. 광도·평활 항은 0이다.
    """
    img1, img2 = _shifted_pair(3, 2)
    region = _centre_region()
    f12, f21 = _const_flow(32, 32, 3, 2), _const_flow(32, 32, -3, -2)
    _, log = sequence_unsup_loss([f12], [f21], img1, img2, region)
    assert log["photo"] <= 1e-6
    assert log["smooth"] <= 1e-6
    assert abs(log["valid_frac"] - 0.25) <= 1e-6
