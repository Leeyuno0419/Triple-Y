"""S9 테스트 경계: finetune.train 시험 (VideoPairs 포함).

기본 시험은 학습을 돌리지 않는다: 설정·체크포인트 경로 검사, 합성
FFV1 영상으로 VideoPairs의 쌍 간격·개수·시드·증강 정렬을 본다.
slow 시험은 CPU에서 raft_small을 작은 해상도로 몇십 step 돌린다.
기대값은 손실 함수를 다시 계산하지 않고, 영상에 새긴 프레임 번호와
손실 감소 여부·두 실행의 일치 여부라는 동작 자체에서 가져온다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("torch")

from src.flow.finetune import (  # noqa: E402
    FinetuneConfig, VideoPairs, checkpoint_dir, train,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cfg(**kw: object) -> FinetuneConfig:
    """시험용 작은 설정을 만든다."""
    base = dict(run_id="t", device="cpu")
    base.update(kw)
    return FinetuneConfig(**base)


def test_checkpoint_dir_inside_repo_is_refused(tmp_path: Path) -> None:
    """설정의 체크포인트 폴더가 저장소 안이면 학습 전에 ValueError를 낸다."""
    inside = REPO_ROOT / "outputs" / "ckpt_should_not_exist"
    with pytest.raises(ValueError):
        train(_cfg(ckpt_dir=str(inside)), run_dir=tmp_path / "run")
    assert not inside.exists()
    assert not (tmp_path / "run").exists()


def test_env_checkpoint_dir_inside_repo_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """설정에 없으면 CROWDSIGHT_CKPT_DIR을 쓰고, 저장소 안이면 거부한다."""
    monkeypatch.setenv("CROWDSIGHT_CKPT_DIR", str(REPO_ROOT))
    with pytest.raises(ValueError):
        train(_cfg(), run_dir=tmp_path / "run")


@pytest.mark.parametrize("ckpt", [
    str(REPO_ROOT / "a" / ".." / "ckpt"),           # .. 로 저장소 안
    "\\\\?\\" + str(REPO_ROOT / "ckpt"),     # 긴 경로 접두사 \\?\
    str(REPO_ROOT / "ckpt").upper(),                # 대소문자만 다름
])
def test_checkpoint_dir_variants_inside_repo_are_refused(ckpt: str) -> None:
    """경로 표기만 다른 저장소 안 경로도 거부한다 (Windows)."""
    with pytest.raises(ValueError):
        checkpoint_dir(_cfg(ckpt_dir=ckpt))


def test_cfg_checkpoint_dir_takes_precedence_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cfg.ckpt_dir가 있으면 환경 변수(저장소 안)를 보지 않는다."""
    monkeypatch.setenv("CROWDSIGHT_CKPT_DIR", str(REPO_ROOT))
    got = checkpoint_dir(_cfg(ckpt_dir=str(tmp_path)))
    assert got == (tmp_path / "t").resolve()
    assert not got.exists()


@pytest.mark.parametrize("bad", [
    dict(run_id="../x"),
    dict(run_id="a b"),
    dict(run_id=""),
    dict(frame_gap=0),
    dict(pair_prob=0.0),
    dict(pair_prob=1.5),
    dict(batch_size=0),
    dict(work_hw=(130, 160)),
    dict(work_hw=(120, 160)),
    dict(crop_hw=(100, 128)),
    dict(crop_hw=(136, 160)),   # work_hw(128, 160)보다 크다
    dict(max_steps=0),
    dict(train_videos=["v.avi"], eval_videos=["v.avi"]),  # 학습·평가 겹침
])
def test_invalid_config_is_refused_before_anything_is_made(
    tmp_path: Path, bad: dict
) -> None:
    """잘못된 설정은 체크포인트·실행 폴더를 만들기 전에 ValueError를 낸다."""
    base = dict(work_hw=(128, 160), ckpt_dir=str(tmp_path / "ckpt"))
    base.update(bad)
    with pytest.raises(ValueError):
        train(_cfg(**base), run_dir=tmp_path / "run")
    assert not (tmp_path / "run").exists()
    assert not (tmp_path / "ckpt").exists()


def _quick_cfg(tmp_path: Path, **kw: object) -> FinetuneConfig:
    """검사 시험용 설정. 체크포인트는 tmp_path/ckpt(저장소 밖)다."""
    base = dict(work_hw=(128, 160), ckpt_dir=str(tmp_path / "ckpt"))
    base.update(kw)
    return _cfg(**base)


def test_train_video_without_region_mask_is_refused(tmp_path: Path) -> None:
    """보행 영역 마스크가 없는 학습 영상은 allow_full_mask 없이 거부한다."""
    video = str(tmp_path / "v.avi")
    with pytest.raises(ValueError, match="v.avi"):
        train(_quick_cfg(tmp_path, train_videos=[video]),
              run_dir=tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_missing_region_mask_file_is_named(tmp_path: Path) -> None:
    """마스크 파일이 없으면 그 경로를 담은 ValueError를 낸다."""
    video = str(tmp_path / "v.avi")
    mask = str(tmp_path / "no_such_mask.png")
    cfg = _quick_cfg(tmp_path, train_videos=[video],
                     region_masks={video: mask})
    with pytest.raises(ValueError, match="no_such_mask.png"):
        train(cfg, run_dir=tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_existing_train_log_is_not_overwritten(tmp_path: Path) -> None:
    """run_dir에 train_log.csv가 이미 있으면 덮어쓰지 않고 거부한다."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "train_log.csv").write_text("old", encoding="utf-8")
    with pytest.raises(ValueError):
        train(_quick_cfg(tmp_path), run_dir=run_dir)
    assert (run_dir / "train_log.csv").read_text(encoding="utf-8") == "old"


def test_existing_checkpoint_is_not_overwritten(tmp_path: Path) -> None:
    """체크포인트 폴더에 *.pth가 이미 있으면 거부한다."""
    old = tmp_path / "ckpt" / "t" / "step000010.pth"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    with pytest.raises(ValueError):
        train(_quick_cfg(tmp_path), run_dir=tmp_path / "run")
    assert old.read_bytes() == b"old"
    assert not (tmp_path / "run").exists()


def test_unreadable_video_is_named(tmp_path: Path) -> None:
    """열 수 없는 영상은 반복할 때 그 경로를 담은 ValueError를 낸다."""
    video = tmp_path / "broken.avi"
    video.write_bytes(b"not a video")
    cfg = _quick_cfg(tmp_path, train_videos=[str(video)],
                     allow_full_mask=True)
    with pytest.raises(ValueError, match="broken.avi"):
        list(VideoPairs(cfg))


# ---- VideoPairs: 합성 FFV1(무손실) 영상 ----
# 프레임 i의 밝기는 8·i, 영역 패턴 안 픽셀만 +4다. 무손실이라 밝기 // 8로
# 프레임 번호를, 밝기 % 8 == 4로 패턴을 정확히 되읽는다.

VH, VW = 136, 176  # 영상 크기 = work_hw (크기 바꾸기로 값이 섞이지 않게)


def _pattern() -> "np.ndarray":
    """좌우 비대칭 영역 패턴 (VH, VW) bool: 왼쪽 40열."""
    import numpy as np

    pat = np.zeros((VH, VW), bool)
    pat[:, :40] = True
    return pat


def _write_video(tmp_path: Path, n: int) -> tuple[str, str]:
    """프레임 n개 FFV1 영상과 같은 패턴의 마스크 PNG를 쓴다."""
    import cv2
    import numpy as np

    path, mask = str(tmp_path / "v.avi"), str(tmp_path / "v_mask.png")
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"FFV1"), 30,
                          (VW, VH))
    assert out.isOpened()
    pat = _pattern()
    for i in range(n):
        gray = (8 * i + 4 * pat).astype(np.uint8)
        out.write(np.dstack([gray] * 3))
    out.release()
    cv2.imwrite(mask, pat.astype(np.uint8) * 255)
    return path, mask


def _video_cfg(tmp_path: Path, n: int = 20, **kw: object) -> FinetuneConfig:
    """합성 영상 하나로 학습하는 설정."""
    path, mask = _write_video(tmp_path, n)
    base = dict(train_videos=[path], region_masks={path: mask},
                work_hw=(VH, VW), frame_gap=3, pair_prob=1.0,
                batch_size=1, seed=7)
    base.update(kw)
    return _cfg(**base)


def _frame_ids(batch: tuple) -> list[tuple[int, int]]:
    """배치 안 쌍마다 (img1 프레임 번호, img2 프레임 번호)를 되읽는다."""
    img1, img2, _ = batch
    ids = []
    for a, b in zip(img1, img2):
        ia, ib = (a.int() // 8).unique(), (b.int() // 8).unique()
        assert len(ia) == 1 and len(ib) == 1  # 한 쌍은 한 프레임씩
        ids.append((int(ia), int(ib)))
    return ids


def test_video_pairs_are_frame_gap_apart(tmp_path: Path) -> None:
    """pair_prob=1이면 (t, t + frame_gap) 쌍이 t = 0..N−gap−1 순서로 나온다."""
    ids = [i for b in VideoPairs(_video_cfg(tmp_path)) for i in _frame_ids(b)]
    assert ids == [(t, t + 3) for t in range(20 - 3)]


def test_video_pairs_batch_count(tmp_path: Path) -> None:
    """쌍 20 − 3 = 17개, 배치 2개씩이면 배치 8개(남는 1쌍은 버림)."""
    batches = list(VideoPairs(_video_cfg(tmp_path, batch_size=2)))
    assert len(batches) == 8
    assert batches[0][0].shape == (2, 3, VH, VW)
    assert batches[0][2].shape == (2, 1, VH, VW)


def test_video_pairs_picks_follow_seed_and_epoch(tmp_path: Path) -> None:
    """같은 시드는 같은 쌍을, 다음 epoch·다른 시드는 다른 쌍을 뽑는다."""
    cfg = _video_cfg(tmp_path, n=30, pair_prob=0.3)

    def picks(vp: VideoPairs) -> list:
        return [i for b in vp for i in _frame_ids(b)]

    vp = VideoPairs(cfg)
    first, second = picks(vp), picks(vp)
    assert first == picks(VideoPairs(cfg))
    assert first != second
    cfg.seed = 8
    assert first != picks(VideoPairs(cfg))


def test_full_mask_when_allowed(tmp_path: Path) -> None:
    """allow_full_mask=True이고 마스크가 없으면 영역은 전부 1이다."""
    cfg = _video_cfg(tmp_path, region_masks={}, allow_full_mask=True)
    region = next(iter(VideoPairs(cfg)))[2]
    assert bool((region == 1).all())


def test_zero_frame_video_is_named(tmp_path: Path) -> None:
    """열리지만 프레임이 0개인 영상은 그 경로를 담은 ValueError를 낸다."""
    cfg = _video_cfg(tmp_path, n=0)
    with pytest.raises(ValueError, match="v.avi"):
        list(VideoPairs(cfg))


def test_flip_and_crop_are_seeded_and_keep_pair_aligned(
    tmp_path: Path
) -> None:
    """뒤집기·자르기가 img1·img2·영역에 같게 걸리고 시드로 재현된다.

    영역 패턴은 왼쪽 40열이다. 뒤집지 않으면 영역이 왼쪽 끝 열에,
    뒤집으면 오른쪽 끝 열에 닿는다. 자르기 x0는 0~48 px라 영역 열 수가
    배치마다 달라진다. 17쌍 모두 같은 쪽일 확률은 2^-16 정도다.
    """
    cfg = _video_cfg(tmp_path, crop_hw=(128, 128))
    batches = list(VideoPairs(cfg))
    again = list(VideoPairs(cfg))
    left = right = 0
    widths = set()
    for (img1, img2, region), (b1, b2, br) in zip(batches, again):
        assert img1.shape == (1, 3, 128, 128)
        assert region.shape == (1, 1, 128, 128)
        assert _torch_equal(img1, b1) and _torch_equal(img2, b2)
        assert _torch_equal(region, br)
        reg = region[0, 0] > 0
        assert _torch_equal(img1[0, 0] % 8 == 4, reg)
        assert _torch_equal(img2[0, 0] % 8 == 4, reg)
        left += bool(reg[:, 0].any())
        right += bool(reg[:, -1].any())
        widths.add(int(reg[0].sum()))
    assert len(batches) == 17
    assert left > 0 and right > 0
    assert len(widths) > 1


def _torch_equal(a: object, b: object) -> bool:
    """두 텐서가 모양·값 모두 같은지 본다."""
    import torch

    return bool(torch.equal(a, b))


# ---- slow: CPU에서 raft_small 짧은 학습 ----

H, W = 128, 160  # 8의 배수, 128 이상 (estimators.RaftEstimator 조건)
SHIFT_X, SHIFT_Y = 3, -2
N_PAIRS = 4
STEPS = 30  # N_PAIRS의 배수가 아니어도 마지막 N_PAIRS step은 모든 쌍을 돈다


def _shifted_batches(n: int = N_PAIRS) -> list:
    """고정 시드 질감을 (SHIFT_X, SHIFT_Y) px 옮긴 쌍 n개를 만든다.

    각 원소는 (img1 uint8 (1, 3, H, W), img2 uint8, 영역 float (1, 1, H, W))다.
    """
    import torch
    import torch.nn.functional as F

    gen = torch.Generator().manual_seed(0)
    out = []
    for _ in range(n):
        noise = torch.rand(1, 3, H // 4, W // 4, generator=gen)
        img = F.interpolate(noise, size=(H, W), mode="bilinear")
        img1 = (img * 255).to(torch.uint8)
        img2 = torch.roll(img1, shifts=(SHIFT_Y, SHIFT_X), dims=(2, 3))
        out.append((img1, img2, torch.ones(1, 1, H, W)))
    return out


def _read_losses(run_dir: Path) -> list[float]:
    """train_log.csv의 loss 열을 읽는다."""
    import csv

    with open(run_dir / "train_log.csv", encoding="utf-8") as f:
        return [float(r["loss"]) for r in csv.DictReader(f)]


def _slow_cfg(tmp_path: Path, run_id: str) -> FinetuneConfig:
    """CPU 짧은 학습 설정. 체크포인트는 tmp_path 아래(저장소 밖)다."""
    return _cfg(
        run_id=run_id, size="small", iters=4, max_steps=STEPS,
        save_every=STEPS, ckpt_dir=str(tmp_path / "ckpt"), seed=7,
    )


@pytest.mark.slow
def test_loss_decreases_on_shifted_pairs(tmp_path: Path) -> None:
    """합성 이동 쌍에서 STEPS step 학습하면 손실이 처음보다 5% 넘게 준다.

    쌍마다 손실 크기가 달라서, 같은 쌍 N_PAIRS개를 한 바퀴씩 도는
    처음·마지막 N_PAIRS step 평균을 비교한다. 2026-11-09 CPU 측정:
    7.10 → 6.12 (−13.8%). 5% 문턱은 이보다 작고 잡음보다 크다 (가정).
    """
    run_dir = tmp_path / "run"
    try:
        ckpt = train(
            _slow_cfg(tmp_path, "a"), run_dir=run_dir,
            pairs=_shifted_batches(),
        )
    except (OSError, RuntimeError) as exc:  # 가중치 내려받기 실패
        if "download" in str(exc).lower() or "url" in str(exc).lower():
            pytest.skip(f"RAFT 가중치를 내려받지 못함: {exc}")
        raise
    losses = _read_losses(run_dir)
    assert len(losses) == STEPS
    first = sum(losses[:N_PAIRS]) / N_PAIRS
    last = sum(losses[-N_PAIRS:]) / N_PAIRS
    assert last < 0.95 * first
    assert ckpt.exists() and REPO_ROOT not in ckpt.resolve().parents
    _check_run_outputs(run_dir, ckpt, STEPS)


def _check_run_outputs(run_dir: Path, ckpt: Path, steps: int) -> None:
    """실행 기록 파일과 체크포인트 형식을 확인한다."""
    import json

    import torch

    saved = torch.load(ckpt, map_location="cpu")
    assert saved["step"] == steps
    assert saved["size"] == "small" and saved["run_id"] == ckpt.parent.name
    assert "model" in saved
    assert not list(ckpt.parent.glob("*.tmp"))
    config = json.loads((run_dir / "config.json").read_text("utf-8"))
    assert config["allow_full_mask"] is False
    env = (run_dir / "env.txt").read_text("utf-8")
    assert "git_dirty=" in env and "pip_freeze:" in env


REPRO_STEPS = 2
REPRO_TOL = 1e-6


@pytest.mark.slow
def test_same_pairs_give_same_losses_on_cpu(tmp_path: Path) -> None:
    """같은 설정·같은 쌍으로 두 번 돌리면 CPU에서 step별 손실이 같다.

    주입한 쌍에는 난수가 없으므로 시드가 아니라 학습 루프의 CPU 결정성을
    본다. 시드 재현은 VideoPairs 시험이 본다.
    """
    runs = []
    for name in ("r1", "r2"):
        cfg = _slow_cfg(tmp_path, name)
        cfg.max_steps = cfg.save_every = REPRO_STEPS
        train(cfg, run_dir=tmp_path / name, pairs=_shifted_batches())
        runs.append(_read_losses(tmp_path / name))
    assert len(runs[0]) == REPRO_STEPS
    assert runs[0] == pytest.approx(runs[1], abs=REPRO_TOL)


@pytest.mark.slow
def test_empty_pairs_is_refused_without_saving(tmp_path: Path) -> None:
    """쌍을 하나도 내지 않는 입력이면 ValueError, 체크포인트는 없다."""
    with pytest.raises(ValueError):
        train(_slow_cfg(tmp_path, "e"), run_dir=tmp_path / "e", pairs=[])
    assert not list((tmp_path / "ckpt").rglob("*.pth"))


@pytest.mark.slow
def test_non_finite_loss_stops_without_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """손실이 NaN이면 step 번호를 담은 ValueError로 멈추고 저장하지 않는다.

    NaN 손실은 실제 입력으로 만들기 어려워 손실 함수를 바꿔 끼운다.
    """
    import src.flow.finetune as ft

    def nan_loss(
        f12s: list, f21s: list, *args: object, **kwargs: object
    ) -> tuple:
        """기울기가 이어진 NaN 손실을 돌려준다."""
        return f12s[-1].sum() * float("nan"), {
            "photo": 0.0, "smooth": 0.0, "valid_frac": 0.0}

    monkeypatch.setattr(ft, "sequence_unsup_loss", nan_loss)
    cfg = _slow_cfg(tmp_path, "n")
    cfg.save_every = 1
    with pytest.raises(ValueError, match="step 1"):
        train(cfg, run_dir=tmp_path / "n", pairs=_shifted_batches())
    assert not list((tmp_path / "ckpt").rglob("*.pth"))
