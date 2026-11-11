"""torchvision RAFT 비지도 추가 학습. GPU 서버에서 백그라운드로 실행한다.

실행 예: python -m src.flow.finetune <설정 JSON 경로>
가중치(*.pth)는 저장소 밖 체크포인트 폴더에만 저장한다.
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import cv2
import numpy as np
import torch

from src.flow.unsup_losses import sequence_unsup_loss

REPO_ROOT = Path(__file__).resolve().parents[2]

# (img1 uint8 (B, 3, H, W), img2 uint8 (B, 3, H, W), 영역 float (B, 1, H, W))
Batch = tuple[torch.Tensor, torch.Tensor, torch.Tensor]


@dataclass
class FinetuneConfig:
    """학습 설정. 값은 모두 시작값이다 (가정)."""

    run_id: str
    train_videos: list[str] = field(default_factory=list)  # 저장소 밖 경로
    eval_videos: list[str] = field(default_factory=list)   # 학습에 안 씀
    region_masks: dict[str, str] = field(default_factory=dict)  # 영상→PNG
    allow_full_mask: bool = False  # True면 마스크 없는 영상은 화면 전체
    ckpt_dir: str | None = None  # 없으면 CROWDSIGHT_CKPT_DIR
    size: str = "small"
    work_hw: tuple[int, int] = (544, 960)  # 8의 배수, 128 이상
    crop_hw: tuple[int, int] | None = None  # 무작위 자르기. 8의 배수, 128 이상
    frame_gap: int = 6       # 30fps면 0.2초 (proposal-detail 3.4)
    pair_prob: float = 0.05  # 프레임마다 쌍으로 뽑을 확률
    batch_size: int = 2
    iters: int = 12          # num_flow_updates
    photo_loss: str = "census"
    w_smooth: float = 0.1
    gamma: float = 0.8
    lr: float = 1e-5         # 망각을 줄이려 작게 둔다 (기획 4.3)
    weight_decay: float = 1e-5
    max_steps: int = 5000
    save_every: int = 500
    clip_grad: float = 1.0
    seed: int = 42
    device: str = "cuda"


def load_config(path: str | Path) -> FinetuneConfig:
    """JSON 설정 파일을 읽어 FinetuneConfig로 만든다."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("work_hw", "crop_hw"):
        if data.get(key) is not None:
            data[key] = tuple(data[key])
    return FinetuneConfig(**data)


def _check_hw(name: str, hw: tuple[int, int]) -> None:
    """해상도가 8의 배수이고 128 이상인지 본다 (RAFT 조건)."""
    if hw[0] % 8 or hw[1] % 8 or min(hw) < 128:
        raise ValueError(f"{name}는 8의 배수이고 128 이상이어야 한다: {hw}")


def validate_config(cfg: FinetuneConfig) -> None:
    """학습 전에 설정 값을 검사한다. 잘못되면 ValueError를 낸다.

    학습·평가 영상이 겹치면 거부한다 (기획 3.1).
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cfg.run_id):
        raise ValueError(f"run_id는 영문·숫자·_·-만 쓴다: {cfg.run_id!r}")
    overlap = set(cfg.train_videos) & set(cfg.eval_videos)
    if overlap:
        raise ValueError(f"학습·평가 영상이 겹친다 (기획 3.1): {overlap}")
    if cfg.frame_gap < 1:
        raise ValueError("frame_gap은 1 이상이어야 한다")
    if not 0.0 < cfg.pair_prob <= 1.0:
        raise ValueError("pair_prob는 0 초과 1 이하여야 한다")
    if cfg.batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 한다")
    if cfg.max_steps < 1:
        raise ValueError("max_steps는 1 이상이어야 한다")
    _check_hw("work_hw", cfg.work_hw)
    if cfg.crop_hw is not None:
        _check_hw("crop_hw", cfg.crop_hw)
        if (cfg.crop_hw[0] > cfg.work_hw[0]
                or cfg.crop_hw[1] > cfg.work_hw[1]):
            raise ValueError("crop_hw가 work_hw보다 크다")


def checkpoint_dir(cfg: FinetuneConfig) -> Path:
    """체크포인트 폴더 경로를 정한다. 만들지는 않는다.

    cfg.ckpt_dir이 없으면 환경 변수 CROWDSIGHT_CKPT_DIR, 그것도 없으면
    ~/crowdsight_ckpt를 쓴다. 그 아래 run_id 폴더다. 저장소 안이면
    ValueError를 낸다 (가중치는 git에 넣지 않는다). Windows 긴 경로
    접두사와 대소문자 차이는 지우고 비교한다.
    """
    root = cfg.ckpt_dir or os.environ.get(
        "CROWDSIGHT_CKPT_DIR", str(Path.home() / "crowdsight_ckpt")
    )
    if root.startswith("\\\\?\\"):  # 긴 경로 접두사 \\?\
        root = root[4:]
    path = (Path(root) / cfg.run_id).resolve()
    repo = os.path.normcase(str(REPO_ROOT))
    here = os.path.normcase(str(path))
    if here == repo or here.startswith(repo.rstrip(os.sep) + os.sep):
        raise ValueError(f"체크포인트를 저장소 안에 둘 수 없다: {path}")
    return path


def set_seed(seed: int) -> None:
    """random·numpy·torch 시드를 고정한다.

    CUDA의 grid_sample 역전파는 결정적이지 않을 수 있어 GPU에서 완전
    재현은 보장하지 않는다 (확인 필요).
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


class VideoPairs:
    """영상을 순서대로 읽어 (t, t + frame_gap) 프레임 쌍 배치를 낸다.

    프레임마다 시드 고정 난수로 pair_prob 확률로 쌍을 뽑는다. 탐색 없이
    순차로 읽으므로 코덱별 탐색 오차가 없다. 프레임을 디스크에 저장하지
    않는다. 반복할 때마다 처음부터 다시 읽는다 (한 바퀴 = 한 epoch).
    """

    def __init__(self, cfg: FinetuneConfig) -> None:
        """설정과 epoch 번호를 두고 영상별 영역 마스크를 미리 읽는다.

        마스크가 없는 영상은 cfg.allow_full_mask가 아니면 ValueError,
        마스크 파일을 읽지 못하면 그 경로를 담은 ValueError를 낸다.
        """
        self._cfg = cfg
        self._epoch = 0
        self._regions = {p: self._region(p) for p in cfg.train_videos}

    def _to_tensor(self, bgr: np.ndarray) -> torch.Tensor:
        """BGR 프레임을 작업 해상도 (3, h, w) uint8 RGB 텐서로 바꾼다."""
        h, w = self._cfg.work_hw
        rgb = cv2.cvtColor(cv2.resize(bgr, (w, h)), cv2.COLOR_BGR2RGB)
        return torch.from_numpy(rgb).permute(2, 0, 1).contiguous()

    def _region(self, path: str) -> torch.Tensor:
        """영상의 보행 영역 마스크 (1, h, w). 허용 시 없으면 전체 1."""
        h, w = self._cfg.work_hw
        mask_path = self._cfg.region_masks.get(path)
        if mask_path is None:
            if not self._cfg.allow_full_mask:
                raise ValueError(
                    f"보행 영역 마스크가 없다 (allow_full_mask 아님): {path}"
                )
            return torch.ones(1, h, w)
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise ValueError(f"마스크 파일을 읽을 수 없다: {mask_path}")
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        return torch.from_numpy(mask > 0).float().unsqueeze(0)

    def __iter__(self) -> Iterator[Batch]:
        """배치 크기만큼 쌍이 모이면 배치를 낸다. 남는 쌍은 버린다.

        프레임 t에서 쌍 시작 여부를 정한다. 쓰지 않을 프레임은 grab만
        하고 풀지(retrieve) 않는다. 영상을 열 수 없거나 프레임이 0개면
        그 경로를 담은 ValueError를 낸다.
        """
        cfg = self._cfg
        rng = np.random.default_rng([cfg.seed, self._epoch])
        self._epoch += 1
        buf: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = []
        for path in cfg.train_videos:
            cap = cv2.VideoCapture(path)
            try:
                if not cap.isOpened():
                    raise ValueError(f"영상을 열 수 없다: {path}")
                # 최근 frame_gap개 (쌍 시작 여부, 프레임 또는 None).
                # 꽉 차면 맨 앞이 t − frame_gap 프레임이다.
                window: deque = deque(maxlen=cfg.frame_gap)
                n_read = 0
                while cap.grab():
                    n_read += 1
                    pick = bool(rng.random() < cfg.pair_prob)
                    head = (window[0] if len(window) == cfg.frame_gap
                            else (False, None))
                    frame = None
                    if pick or head[0]:
                        ok, frame = cap.retrieve()
                        if not ok:
                            break
                    if head[0]:
                        buf.append(self._pair(head[1], frame, path, rng))
                    window.append((pick, frame))
                    if len(buf) == cfg.batch_size:
                        a, b, m = zip(*buf)
                        yield torch.stack(a), torch.stack(b), torch.stack(m)
                        buf = []
                if n_read == 0:
                    raise ValueError(f"영상에 프레임이 없다: {path}")
            finally:
                cap.release()

    def _pair(
        self,
        first: np.ndarray,
        second: np.ndarray,
        path: str,
        rng: np.random.Generator,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """프레임 두 장과 영역 마스크를 텐서 쌍으로 만든다.

        세 장에 같은 무작위 자르기(cfg.crop_hw)와 좌우 뒤집기(확률 0.5)를
        건다. 난수는 rng에서만 뽑아 시드로 재현된다. 뒤집은 쌍에서 손실을
        계산하므로 흐름 부호는 따로 고치지 않는다. 밝기 증강은 census
        손실이 밝기 변화에 강해서 넣지 않았다 (가정).
        """
        imgs = [self._to_tensor(first), self._to_tensor(second),
                self._regions[path]]
        if self._cfg.crop_hw is not None:
            h, w = self._cfg.work_hw
            ch, cw = self._cfg.crop_hw
            y0 = int(rng.integers(0, h - ch + 1))
            x0 = int(rng.integers(0, w - cw + 1))
            imgs = [t[:, y0:y0 + ch, x0:x0 + cw] for t in imgs]
        if rng.random() < 0.5:
            imgs = [t.flip(-1) for t in imgs]
        a, b, m = (t.contiguous() for t in imgs)
        return a, b, m


def _freeze_batchnorm(model: torch.nn.Module) -> None:
    """배치 크기가 작으므로 BatchNorm 통계를 고정한다 (가정).

    torchvision raft_small에는 BatchNorm이 없다 (InstanceNorm2d만 21개,
    2026-11-09 확인). raft_large에만 해당할 수 있다 (확인 필요).
    """
    for mod in model.modules():
        if isinstance(mod, torch.nn.BatchNorm2d):
            mod.eval()


def _write_env(run_dir: Path, device: str) -> None:
    """git 커밋 해시·수정 여부, 패키지 버전, 장치 이름을 env.txt에 남긴다.

    git·pip이 없거나 실패하면 "unknown"으로 적고 멈추지 않는다.
    커밋하지 않은 수정이 있어도 기록만 하고 거부하지 않는다.
    """
    def run(cmd: list[str]) -> str:
        """명령 출력을 돌려준다. 실패하면 "unknown"."""
        try:
            out = subprocess.run(
                cmd, cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError):
            return "unknown"
        return out.stdout.strip() if out.returncode == 0 else "unknown"

    commit = run(["git", "rev-parse", "HEAD"]) or "unknown"
    status = run(["git", "status", "--porcelain"])
    dirty = "unknown" if status == "unknown" else str(bool(status))
    freeze = run([sys.executable, "-m", "pip", "freeze"])
    gpu = (torch.cuda.get_device_name(0)
           if device.startswith("cuda") and torch.cuda.is_available()
           else "none")
    import torchvision

    lines = [
        f"git_commit={commit}",
        f"git_dirty={dirty}",
        f"python={sys.version.split()[0]}",
        f"torch={torch.__version__}",
        f"torchvision={torchvision.__version__}",
        f"device={device}",
        f"gpu={gpu}",
        "pip_freeze:",
        freeze,
    ]
    (run_dir / "env.txt").write_text("\n".join(lines) + "\n",
                                     encoding="utf-8")


def train(
    cfg: FinetuneConfig,
    run_dir: Path,
    pairs: Iterable[Batch] | None = None,
) -> Path:
    """비지도 추가 학습을 돌리고 마지막 체크포인트 경로를 돌려준다.

    pairs는 (img1, img2, 영역) 배치를 내는 다시 반복 가능한 객체다
    (리스트, VideoPairs. 한 번만 도는 생성기는 안 된다). 없으면
    cfg.train_videos로 VideoPairs를 만든다. max_steps까지 처음부터 다시
    반복한다. 설정이 잘못됐거나, 체크포인트 폴더가 저장소 안이거나,
    이전 기록·체크포인트가 있으면 아무것도 만들기 전에 ValueError를
    낸다. run_dir에 config.json, env.txt, train_log.csv를 쓴다.
    손실이 유한하지 않으면 그 step에서 멈추고 저장하지 않는다.
    체크포인트는 {"model", "step", "size", "run_id"} 사전이며, 평가는
    ["model"]을 load_state_dict로 읽는다.
    """
    from torchvision.models.optical_flow import (
        Raft_Large_Weights, Raft_Small_Weights, raft_large, raft_small,
    )

    validate_config(cfg)
    ckpt_dir = checkpoint_dir(cfg)
    if (run_dir / "train_log.csv").exists():
        raise ValueError(f"이미 학습 기록이 있다: {run_dir}")
    if ckpt_dir.is_dir() and any(ckpt_dir.glob("*.pth")):
        raise ValueError(f"이미 체크포인트가 있다: {ckpt_dir}")
    if pairs is None:
        pairs = VideoPairs(cfg)
    set_seed(cfg.seed)
    if cfg.size == "large":
        weights, builder = Raft_Large_Weights.DEFAULT, raft_large
    else:
        weights, builder = Raft_Small_Weights.DEFAULT, raft_small
    model = builder(weights=weights).to(cfg.device)
    model.train()
    _freeze_batchnorm(model)
    preprocess = weights.transforms()
    opt = torch.optim.AdamW(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )

    run_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_env(run_dir, cfg.device)

    step, n_batches, t0 = 0, 0, time.time()
    last = ckpt_dir / "step000000.pth"
    with open(run_dir / "train_log.csv", "w", newline="",
              encoding="utf-8") as log_f:
        log = csv.writer(log_f)
        log.writerow(["step", "loss", "photo", "smooth", "valid_frac",
                      "lr", "elapsed_s"])
        while step < cfg.max_steps:
            before = n_batches
            for img1, img2, region in pairs:
                n_batches += 1
                a, b = preprocess(img1, img2)  # [-1, 1]
                a, b = a.to(cfg.device), b.to(cfg.device)
                region = region.to(cfg.device)
                f12s = model(a, b, num_flow_updates=cfg.iters)
                f21s = model(b, a, num_flow_updates=cfg.iters)
                loss, terms = sequence_unsup_loss(
                    f12s, f21s, (a + 1) / 2, (b + 1) / 2, region,
                    w_smooth=cfg.w_smooth, gamma=cfg.gamma,
                    kind=cfg.photo_loss,
                )
                if not torch.isfinite(loss):
                    raise ValueError(
                        f"손실이 유한하지 않다 (step {step + 1}): "
                        f"{float(loss.detach())}"
                    )
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), cfg.clip_grad
                )
                opt.step()
                step += 1
                log.writerow([
                    step, float(loss.detach()), terms["photo"],
                    terms["smooth"], terms["valid_frac"], cfg.lr,
                    round(time.time() - t0, 1),
                ])
                if step % 10 == 0:
                    log_f.flush()
                if step % cfg.save_every == 0 or step == cfg.max_steps:
                    last = ckpt_dir / f"step{step:06d}.pth"
                    _save_checkpoint(model, cfg, step, last)
                    log_f.flush()
                if step >= cfg.max_steps:
                    break
            if n_batches == before:
                raise ValueError("학습 프레임 쌍이 하나도 없다")
    return last


def _save_checkpoint(
    model: torch.nn.Module, cfg: FinetuneConfig, step: int, path: Path
) -> None:
    """가중치와 step·크기·run_id를 저장소 밖 path에 원자적으로 저장한다.

    .tmp에 먼저 쓰고 os.replace로 바꿔, 중간에 끊겨도 반쯤 쓴 .pth가
    남지 않게 한다.
    """
    tmp = path.with_suffix(".tmp")
    torch.save({"model": model.state_dict(), "step": step,
                "size": cfg.size, "run_id": cfg.run_id}, tmp)
    os.replace(tmp, path)


if __name__ == "__main__":
    _cfg = load_config(sys.argv[1])
    print(train(_cfg, REPO_ROOT / "outputs" / "flow" / "runs" / _cfg.run_id))
