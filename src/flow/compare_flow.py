"""같은 머리 점으로 흐름 설정(배율·gap)을 비교한다.

    python -m src.flow.compare_flow \
        --homography infra/homography/E05_035.json \
        --video data/raw/aihub_71850/halloween_fri/E05_035.mp4 \
        --configs fb:1:1,fb:0.5:6

인원 추정(count_video)은 한 번만 돌리고, 머리 점을 메모리에 둔 채 설정마다
analyze_video를 돌린다. 머리 점은 어디에도 쓰지 않는다 (규격 9절 4번).
P2PNet 가중치가 있는 PC에서만 돈다.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np

from src.flow.estimators import FarnebackEstimator
from src.flow.flow_proxy import parse_configs
from src.flow.run_flow import analyze_video

ROOT = Path(__file__).resolve().parents[2]
TIMELINE_DIR = ROOT / "data" / "processed" / "flow_upgrade"
OUT_DIR = ROOT / "outputs" / "flow_upgrade"


def timeline_proxies(timeline: dict, min_area_m2: float = 2.0) -> dict:
    """timeline 하나의 셀 단위 지표를 낸다.

    판정 셀(walkable_area_m2 ≥ min_area_m2)만 쓰고, vx·vy가 null인 셀-초는
    모든 지표에서 뺀다.
    over3_ms: 셀 평균 속력 > 3 m/s 셀-초 수,
    moving_speed_median: 추정 머리(density × walkable_area_m2) ≥ 2이고
    속력 ≥ 0.3 m/s인 셀-초 속력 중앙값 (없으면 None),
    p_over_002: pressure > 0.02 셀-초 수.
    min_area_m2 2.0은 서버 min-walkable-area-m2와 같은 값(가정)이며
    비교용 필터일 뿐 판정 규칙이 아니다.
    """
    area = {c["cell_id"]: c["walkable_area_m2"]
            for c in timeline["meta"]["cells"]}
    over3, p_over, moving = 0, 0, []
    for frame in timeline["frames"]:
        for cell in frame["cells"]:
            a = area[cell["cell_id"]]
            if a < min_area_m2 or cell["vx"] is None or cell["vy"] is None:
                continue
            speed = float(np.hypot(cell["vx"], cell["vy"]))
            over3 += speed > 3.0
            if cell["pressure"] is not None and cell["pressure"] > 0.02:
                p_over += 1
            if cell["density"] * a >= 2 and speed >= 0.3:
                moving.append(speed)
    return {
        "over3_ms": int(over3),
        "moving_speed_median": (
            statistics.median(moving) if moving else None
        ),
        "p_over_002": p_over,
    }


def main() -> None:
    """설정별 timeline과 지표·흐름 시간(flow_s)을 쓴다.

    timeline은 data/processed/flow_upgrade/{video}_{설정}.json(git 제외),
    지표는 outputs/flow_upgrade/{video}_compare.json(--out으로 바꿈)이다.
    """
    from src.counting.run_density import count_video

    ap = argparse.ArgumentParser()
    ap.add_argument("--homography", required=True, help="구역 설정 파일")
    ap.add_argument("--video", required=True)
    ap.add_argument("--configs", default="fb:1:1,fb:0.5:6")
    ap.add_argument("--out", default=None,
                    help="기본: outputs/flow_upgrade/{video}_compare.json")
    args = ap.parse_args()

    configs = parse_configs(args.configs)
    cfg = json.loads(Path(args.homography).read_text(encoding="utf-8"))
    base, heads, _ = count_video(cfg, args.video)
    stem = Path(args.video).stem
    TIMELINE_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, scale, gap in configs:
        path = TIMELINE_DIR / f"{stem}_{name.replace(':', '-')}.json"
        path.write_text(json.dumps(base, ensure_ascii=False),
                        encoding="utf-8")
        start = time.perf_counter()
        result = analyze_video(
            Path(args.video), path, path, FarnebackEstimator(scale=scale),
            heads=heads,
            h_head=np.array(cfg["head_plane"]["H_head_img_to_ground"]),
            cell_origin_m=tuple(cfg["cell_origin_m"]), gap_frames=gap,
        )
        flow_s = time.perf_counter() - start
        rows.append({"config": name,
                     "flow_model": result["meta"]["models"]["flow"],
                     "flow_s": round(flow_s, 1),
                     **timeline_proxies(result)})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    del heads  # 머리 점은 여기까지만 쓴다

    out = Path(args.out) if args.out else OUT_DIR / f"{stem}_compare.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"video": stem, "rows": rows}, ensure_ascii=False,
                   indent=2),
        encoding="utf-8",
    )
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
