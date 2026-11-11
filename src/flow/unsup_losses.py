"""비지도 광학 흐름 손실. 영상은 [0, 1] 범위 (B, 3, H, W) 텐서를 받는다."""
from __future__ import annotations

import torch
import torch.nn.functional as F


def backward_warp(
    img: torch.Tensor, flow: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor]:
    """img를 x + flow 위치에서 표본해 (비틀린 영상, 화면 안 마스크)를 돌려준다.

    flow는 (B, 2, H, W) px 단위, 채널 0이 x(오른쪽 +), 채널 1이 y(아래 +)다.
    align_corners=True로 -1·+1을 첫·끝 픽셀 중심에 맞춘다. 화면 밖 표본은
    0으로 채우고(padding_mode="zeros"), 마스크 0으로 표시한다.
    """
    _, _, h, w = img.shape
    ys, xs = torch.meshgrid(
        torch.arange(h, device=img.device, dtype=img.dtype),
        torch.arange(w, device=img.device, dtype=img.dtype),
        indexing="ij",
    )
    x = xs + flow[:, 0]
    y = ys + flow[:, 1]
    grid = torch.stack(
        [2.0 * x / (w - 1) - 1.0, 2.0 * y / (h - 1) - 1.0], dim=-1
    )
    warped = F.grid_sample(
        img, grid, mode="bilinear", padding_mode="zeros",
        align_corners=True,
    )
    inside = (x >= 0) & (x <= w - 1) & (y >= 0) & (y <= h - 1)
    return warped, inside.unsqueeze(1).to(img.dtype)


def fb_consistency_mask(
    f12: torch.Tensor,
    f21: torch.Tensor,
    alpha1: float = 0.01,
    alpha2: float = 0.5,
) -> torch.Tensor:
    """앞뒤 흐름 일치 검사로 가려지지 않은 픽셀 마스크 (B, 1, H, W)를 만든다.

    |f12 + f21(x + f12)|² < alpha1·(|f12|² + |f21(x + f12)|²) + alpha2
    이면 1. 상수는 UnFlow(Meister et al. 2018) 관례값이다 (원문 확인 필요).
    기울기는 흐르지 않는다.
    """
    f21_w, _ = backward_warp(f21, f12)
    diff = (f12 + f21_w).pow(2).sum(1, keepdim=True)
    mag = f12.pow(2).sum(1, keepdim=True) + f21_w.pow(2).sum(1, keepdim=True)
    bound = alpha1 * mag + alpha2
    return (diff < bound).to(f12.dtype).detach()


def charbonnier(
    x: torch.Tensor, eps: float = 1e-3, alpha: float = 0.45
) -> torch.Tensor:
    """일반화 Charbonnier (x² + eps²)^alpha. 상수는 (가정)."""
    return (x.pow(2) + eps ** 2).pow(alpha)


def _gray(img: torch.Tensor) -> torch.Tensor:
    """RGB [0, 1] 영상을 0~255 밝기 회색조 (B, 1, H, W)로 바꾼다.

    census 상수 0.81은 0~255 밝기 기준이다 (UFlow census_transform).
    """
    r, g, b = img[:, 0:1], img[:, 1:2], img[:, 2:3]
    return (0.299 * r + 0.587 * g + 0.114 * b) * 255.0


def _census(gray: torch.Tensor, patch: int = 7) -> torch.Tensor:
    """부드러운 census 변환.

    주변 patch×patch 픽셀과의 밝기 차이 부호를 연속값으로 낸다.
    d / sqrt(0.81 + d²)는 UFlow census_transform과 같다 (DDFlow 상수,
    google-research/uflow uflow_utils.py, 2026-11-09 확인).
    """
    b, _, h, w = gray.shape
    p = F.unfold(gray, patch, padding=patch // 2)
    d = p.view(b, patch * patch, h, w) - gray
    return d / torch.sqrt(0.81 + d * d)


def _abs_robust(
    x: torch.Tensor, eps: float = 0.01, q: float = 0.4
) -> torch.Tensor:
    """(|x| + eps)^q − eps^q. UFlow abs_robust_loss에서 상수만 뺐다.

    eps^q를 빼서 오차 0일 때 손실 0이 되게 한다. 기울기는 UFlow와 같다.
    """
    return (x.abs() + eps).pow(q) - eps ** q


def _erode(mask: torch.Tensor, radius: int) -> torch.Tensor:
    """마스크를 radius px만큼 깎는다. 화면 밖은 0으로 본다.

    (2·radius + 1)² 창 안이 모두 1인 픽셀만 1로 남긴다.
    """
    padded = F.pad(mask, (radius,) * 4, value=0.0)
    return -F.max_pool2d(-padded, 2 * radius + 1, stride=1)


def photometric_loss(
    img1: torch.Tensor,
    img2_warped: torch.Tensor,
    mask: torch.Tensor,
    kind: str = "census",
    patch: int = 7,
) -> torch.Tensor:
    """마스크 안 광도 손실의 평균.

    kind: "census"(밝기 변화에 강함) 또는 "charbonnier"(단순).
    기본값 선택은 (가정). census는 UFlow census_loss를 따른다
    (uflow_utils.py, 2026-11-09 확인): soft hamming 문턱 0.1, 픽셀별
    (|h| + 0.01)^0.4, 마스크 평균. 다른 점 두 가지:
    - 오차 0일 때 손실 0이 되도록 상수 0.01^0.4를 뺀다 (기울기 같음).
    - UFlow는 화면 테두리만 patch // 2만큼 깎는다. 여기서는 영역·가림·
      화면 안을 곱한 마스크 전체를 깎아 화면 밖 표본 경계도 뺀다.
    """
    if kind == "census":
        mask = _erode(mask, patch // 2)
        t1 = _census(_gray(img1), patch)
        t2 = _census(_gray(img2_warped), patch)
        dist = (t1 - t2).pow(2)
        hamming = (dist / (0.1 + dist)).sum(1, keepdim=True)
        per_px = _abs_robust(hamming)
    elif kind == "charbonnier":
        per_px = charbonnier(img1 - img2_warped).mean(1, keepdim=True)
    else:
        raise ValueError(f"알 수 없는 kind: {kind}")
    return (per_px * mask).sum() / (mask.sum() + 1e-6)


def smoothness_loss(
    flow: torch.Tensor,
    img: torch.Tensor,
    mask: torch.Tensor,
    edge_weight: float = 150.0,
) -> torch.Tensor:
    """경계 인식 1차 평활 손실. 영상 경계에서는 흐름이 바뀌어도 벌점을 줄인다.

    edge_weight 150은 [0, 1] 영상 기준 UFlow 값이다 (원문 확인 필요).
    mask는 군중·보행 영역이다.
    """
    dfx = (flow[..., :, 1:] - flow[..., :, :-1]).abs()
    dfy = (flow[..., 1:, :] - flow[..., :-1, :]).abs()
    gx = (img[..., :, 1:] - img[..., :, :-1]).abs().mean(1, keepdim=True)
    gy = (img[..., 1:, :] - img[..., :-1, :]).abs().mean(1, keepdim=True)
    wx = torch.exp(-edge_weight * gx)
    wy = torch.exp(-edge_weight * gy)
    mx = mask[..., :, 1:] * mask[..., :, :-1]
    my = mask[..., 1:, :] * mask[..., :-1, :]
    lx = (wx * dfx * mx).sum() / (2 * mx.sum() + 1e-6)
    ly = (wy * dfy * my).sum() / (2 * my.sum() + 1e-6)
    return lx + ly


def sequence_unsup_loss(
    f12s: list[torch.Tensor],
    f21s: list[torch.Tensor],
    img1: torch.Tensor,
    img2: torch.Tensor,
    region: torch.Tensor,
    w_smooth: float = 0.1,
    gamma: float = 0.8,
    kind: str = "census",
) -> tuple[torch.Tensor, dict[str, float]]:
    """RAFT 반복별 양방향 흐름의 비지도 손실 (전체 손실, 기록용 항).

    반복 i에 감쇠 가중치 gamma^(N−1−i)를 둔다 (가정).
    region은 보행 가능·군중 영역 마스크 (B, 1, H, W)다 (기획 4.3).
    가림 마스크는 마지막 반복의 앞뒤 흐름으로 한 번 만들어 모든 반복에
    쓴다 (가정). 기록용 항은 마지막 반복의 광도·평활 손실과 앞 방향 유효
    픽셀 비율(영역·가림·화면 안을 곱한 마스크의 평균, census 깎기 전)이다.
    가림 마스크와 평활 손실이 결과에 주는 효과는 시험하지 않았다.
    """
    with torch.no_grad():
        occ12 = fb_consistency_mask(f12s[-1], f21s[-1])
        occ21 = fb_consistency_mask(f21s[-1], f12s[-1])
    n = len(f12s)
    total = img1.new_zeros(())
    log = {"photo": 0.0, "smooth": 0.0, "valid_frac": 0.0}
    for i, (f12, f21) in enumerate(zip(f12s, f21s)):
        wgt = gamma ** (n - 1 - i)
        w2, in2 = backward_warp(img2, f12)
        w1, in1 = backward_warp(img1, f21)
        m12, m21 = region * occ12 * in2, region * occ21 * in1
        photo = photometric_loss(img1, w2, m12, kind)
        photo = photo + photometric_loss(img2, w1, m21, kind)
        smooth = smoothness_loss(f12, img1, region)
        smooth = smooth + smoothness_loss(f21, img2, region)
        total = total + wgt * (photo + w_smooth * smooth)
        if i == n - 1:
            log = {
                "photo": float(photo.detach()),
                "smooth": float(smooth.detach()),
                "valid_frac": float(m12.detach().mean()),
            }
    return total, log
