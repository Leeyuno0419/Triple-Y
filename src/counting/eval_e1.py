"""E1: P2PNet 공식 가중치로 ShanghaiTech 인원 추정 MAE를 잰다.

사용 예:
    python -m src.counting.eval_e1 --part A            # 전체 test
    python -m src.counting.eval_e1 --part A --limit 5  # 빠른 확인

전처리·판정은 공식 run_test.py와 같다(128 배수 리사이즈, ImageNet 정규화, 점수 > 0.5).
머리 좌표는 저장하지 않고 개수만 기록한다.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import scipy.io
import torch
import torchvision
from PIL import Image
from torch import nn
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[2]
P2P_DIR = ROOT / "third_party" / "CrowdCounting-P2PNet"
DATA_DIR = ROOT / "data" / "raw" / "archive" / "ShanghaiTech"
WEIGHTS = ROOT / "data" / "raw" / "weights" / "SHTechA.pth"
OUT_DIR = ROOT / "outputs" / "e1"

_TF = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def load_p2pnet(weights: Path) -> nn.Module:
    """공식 코드로 P2PNet(vgg16_bn, 2×2 앵커)을 만들고 가중치를 불러온다.

    공식 코드를 고치지 않고 두 가지만 우회한다.
    - util/misc.py의 버전 비교가 torchvision 0.1x를 0.1로 읽어 없는 함수를 import하므로,
      import 동안만 버전 문자열을 바꾼다.
    - 백본이 ImageNet 가중치를 내려받지 않게 한다. 어차피 weights로 덮어쓴다.
    """
    sys.path.insert(0, str(P2P_DIR))
    real_version = torchvision.__version__
    torchvision.__version__ = "0.99"
    try:
        from models import backbone, build_model
    finally:
        torchvision.__version__ = real_version
    real_vgg = backbone.models.vgg16_bn  # 저장소 안의 models/vgg_.py
    backbone.models.vgg16_bn = lambda **kw: real_vgg(**{**kw, "pretrained": False})
    try:
        model = build_model(SimpleNamespace(backbone="vgg16_bn", row=2, line=2))
    finally:
        backbone.models.vgg16_bn = real_vgg
    ckpt = torch.load(weights, map_location="cpu")
    model.load_state_dict(ckpt["model"])
    return model.eval()


@torch.no_grad()
def count_image(model: nn.Module, img_path: Path) -> int:
    """이미지 1장의 예측 인원수(점수 > 0.5인 점 개수)를 돌려준다."""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    img = img.resize((w // 128 * 128, h // 128 * 128), Image.LANCZOS)
    out = model(_TF(img).unsqueeze(0))
    scores = torch.softmax(out["pred_logits"], -1)[0, :, 1]
    return int((scores > 0.5).sum())


def gt_count(mat_path: Path) -> int:
    """ShanghaiTech .mat 라벨의 정답 인원수(머리 점 개수)를 돌려준다."""
    return len(scipy.io.loadmat(mat_path)["image_info"][0][0][0][0][0])


def main() -> None:
    """test 이미지 전체를 추론해 이미지별 CSV와 MAE·MSE 요약을 저장한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["A", "B"], default="A")
    ap.add_argument("--limit", type=int, default=0, help="0이면 전체")
    args = ap.parse_args()

    torch.manual_seed(0)
    test_dir = DATA_DIR / f"part_{args.part}" / "test_data"
    images = sorted((test_dir / "images").glob("*.jpg"), key=lambda p: int(p.stem.split("_")[1]))
    if args.limit:
        images = images[: args.limit]

    model = load_p2pnet(WEIGHTS)
    rows, start = [], time.time()
    for i, img_path in enumerate(images, 1):
        gt = gt_count(test_dir / "ground-truth" / f"GT_{img_path.stem}.mat")
        pred = count_image(model, img_path)
        rows.append((img_path.stem, gt, pred, abs(pred - gt)))
        print(f"[{i}/{len(images)}] {img_path.stem} gt={gt} pred={pred}", flush=True)
    elapsed = time.time() - start

    err = np.array([r[2] - r[1] for r in rows], dtype=float)
    mae, mse = float(np.abs(err).mean()), float(np.sqrt((err ** 2).mean()))
    tag = f"SH{args.part}" + (f"_limit{args.limit}" if args.limit else "")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / f"{tag}.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("image", "gt", "pred", "abs_err"), *rows])
    summary = (
        f"# E1 {tag}\n\n"
        f"| 항목 | 값 |\n|---|---|\n"
        f"| 이미지 수 | {len(rows)} |\n| MAE | {mae:.2f} |\n| MSE(RMSE) | {mse:.2f} |\n"
        f"| 가중치 | {WEIGHTS.name} |\n| 소요 시간 | {elapsed:.0f}초 ({elapsed / len(rows):.2f}초/장) |\n"
        f"| 환경 | torch {torch.__version__}, torchvision {torchvision.__version__}, CPU |\n"
    )
    (OUT_DIR / f"{tag}.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
