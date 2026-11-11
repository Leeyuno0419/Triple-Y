# 흐름·군중 불안정 모듈용 사전학습 모델 조사

## 문서 상태

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-09 |
| 작성자 | 조영준 (Claude 작성 보조) |
| 범위 | `src/flow/`에 쓸 수 있는 공개 가중치 모델(광학 흐름, 군중 이상 행동, 점 추적)과 코드 공개 현황 |
| 범위 밖 | 군중 난류 이론·지표·판정 방법은 `docs/research/crowd_turbulence_research.md`에서 다룬다 |
| 관련 절 | `docs/proposal-detail.md` 7.2.3 흐름 추정 모델, 7.2.4 군중난류 감지 방법 |

- 이 문서는 조사 자료다. 모델 채택은 팀이 정한다. Claude의 제안은 7장에 `[토론]`으로 둔다.
- 수치는 논문·공식 저장소에서 확인한 것만 적는다. 확인하지 못한 것은 `(확인 필요)`로 표시한다.
- 용어:
    - 광학 흐름(optical flow): 두 프레임 사이에서 픽셀마다 움직인 방향과 거리(변위 벡터)를 구한 값이다.
    - 밀집 흐름(dense flow): 모든 픽셀에 대해 흐름을 구한 것이다. Farneback·DIS·RAFT가 여기에 속한다.
    - EPE(end-point error, 끝점 오차): 추정 흐름 벡터와 정답 벡터 끝점 사이의 평균 거리다. 단위는 픽셀이고 낮을수록 좋다.
    - Fl-all: KITTI 벤치마크 지표다. 오차가 3픽셀 이상이면서 정답 크기의 5% 이상인 픽셀의 비율이다.
    - Sintel·KITTI·Spring: 광학 흐름 표준 벤치마크다. Sintel은 애니메이션 영화, KITTI는 자동차 주행, Spring은 고해상도 합성 영상이다. 셋 다 군중 영상이 아니다.
    - clean/final: Sintel의 두 버전이다. final에는 모션 블러·안개 같은 효과가 들어가 더 어렵다.

## 요약

- 군중 난류·압사 위험을 직접 판정하는 공개 가중치 모델은 찾지 못했다. 그래서 규칙 기반 군중 압력(P = ρ × Var(v)) [1]을 유지하는 근거가 그대로 선다.
- 흐름 추정기는 세 단계로 정리한다.
    - 1단계 Farneback [18]: 현재 기본값이다.
    - 2단계 DIS [19]: 이미 E4 비교가 계획돼 있다. 군중 합성 벤치마크(TUB CrowdFlow)에서 시험한 고전 방법 중 가장 정확했다 [21].
    - 3단계 딥 흐름: torchvision RAFT [20]가 설치 부담이 가장 작다. 실제 군중 영상(출입구 밀치기 탐지)에서 Farneback보다 하위 분류 정확도가 8%p 높았다는 보고가 있다 [M12].
- 2025~2026년 최신 모델(WAFT, DPFlow, FlowSeek, MEMFOF, ReCoVEr, UFM, MegaFlow)은 가중치가 공개돼 있다. 다만 군중 영상 평가가 없다. 일부 가중치는 학술용만 허용된다.
- 저사양에 가장 유리한 최신 후보는 ReCoVEr(ICCV 2025)다. 저자는 가장 빠른 모델이 Full HD를 약 20 FPS, GPU 메모리 약 500MB로 처리한다고 보고한다 [M10]. 가중치 라이선스는 명시되지 않았다.
- 점 추적(CoTracker3, TAPIR, AllTracker)은 개인 궤적을 만든다. 프라이버시 규칙과 맞지 않아 쓰지 않는 쪽이 맞다.
- 주의: `references.md` [66]의 TUB CrowdFlow 저장소 주소(`github.com/tsenst/CrowdFlow`)는 2026-11-09 접속 시 404다. 소유자 계정도 조회되지 않는다.

---

## 1. 광학 흐름 모델

### 1.1 비교표: 정확도·라이선스

| 모델 | 연도·학회 | Sintel test clean / final EPE | KITTI test Fl-all | 코드 라이선스 | 가중치 라이선스 | 출처 |
|---|---|---|---|---|---|---|
| Farneback | 2003, SCIA | 공식 수치 없음 | 공식 수치 없음 | OpenCV(Apache-2.0) | 해당 없음 | [18] |
| DIS | 2016, ECCV | 공식 수치 없음 (확인 필요) | (확인 필요) | OpenCV(Apache-2.0) | 해당 없음 | [19] |
| RAFT (원 논문) | 2020, ECCV | 1.61 / 2.86 (warm-start) | 5.10% | BSD-3 | 저장소와 동일 | [20], [M1] |
| RAFT (torchvision `C_T_SKHT_V2`) | 2020 구조, torchvision 재학습 | 1.819 / 3.067 | 5.19% (`C_T_SKHT_K_V2`) | BSD-3 | BSD-3 | [M2] |
| GMFlow+ (UniMatch) | 2023, TPAMI | 1.03 / 2.37 | 4.49 (표의 "All pixels") | MIT | MIT | [M3] |
| FlowFormer++ | 2023, CVPR | (확인 필요) | (확인 필요) | Apache (README 문구, LICENSE 파일 없음) | 저장소와 동일 (확인 필요) | [M4] |
| VideoFlow | 2023, ICCV | (확인 필요) | (확인 필요) | Apache (README 문구, LICENSE 파일 없음) | 저장소와 동일 (확인 필요) | [M5] |
| MemFlow | 2024, CVPR | (확인 필요) | (확인 필요) | Apache-2.0 | 저장소와 동일 | [M6] |
| SEA-RAFT (M) | 2024, ECCV Oral | 1.44 / 2.86 | 4.64% | BSD-3 | BSD-3 | [M7] |
| SEA-RAFT (L) | 2024, ECCV Oral | 1.31 / 2.60 | 4.30% | BSD-3 | BSD-3 | [M7] |
| NeuFlow v2 | 2024, arXiv (학회 미표기) | test 수치 없음 (1.3절 참고) | test 수치 없음 | Apache-2.0 | 저장소와 동일 | [M8] |
| DPFlow | 2025, CVPR | (확인 필요) | (확인 필요) | Apache-2.0 | **학술·연구용만** | [M9] |
| ReCoVEr | 2025, ICCV | (확인 필요) | (확인 필요) | BSD-3 | 명시 없음 (확인 필요) | [M10] |
| MEMFOF | 2025, ICCV Highlight | (확인 필요) | (확인 필요) | BSD-3 | 저장소와 동일 (확인 필요) | [M11] |
| FlowSeek | 2025, ICCV | (확인 필요) | (확인 필요) | Apache-2.0 | 의존 모델 Depth Anything v2 Base/Large가 **CC-BY-NC-4.0**. Small만 Apache-2.0 | [M13], [M14] |
| UFM | 2025, NeurIPS | (확인 필요) | (확인 필요) | BSD-3 | **CC BY-NC-SA 4.0 (상업 이용 불가)** | [M15] |
| WAFT | 2026, ICLR Oral | 저자 주장: Spring·Sintel·KITTI 1위 (수치 확인 필요) | 같음 | BSD-3 | 저장소와 동일 (확인 필요) | [M16] |
| MegaFlow | 2026, ECCV (arXiv 표기) | 저자 주장: 여러 벤치마크 zero-shot 최고 (수치 확인 필요) | 같음 | Apache-2.0 | (확인 필요) | [M17] |
| Flow-Anything | 2025, arXiv | (확인 필요) | (확인 필요) | arXiv에 코드 링크 없음 | ptlflow에 모델 폴더 있음 (확인 필요) | [M18] |

- 학습 데이터 구성이 모델마다 다르다. 같은 표 안의 수치도 엄밀한 동일 조건 비교가 아니다.
- torchvision RAFT의 Sintel 수치가 원 논문보다 나쁜 것은 warm-start(이전 프레임 흐름으로 초기화)를 쓰지 않았기 때문으로 보인다 (확인 필요).
- `proposal-detail.md` 7.2.3의 RAFT 수치(Sintel final 2.855, KITTI 5.10%)는 원 논문 초록 값이다. 위 표의 [M1]과 같은 출처다.

### 1.2 비교표: 속도·자원·설치

| 모델 | 파라미터 | 속도 (측정 조건) | GPU 메모리 | 설치 경로 | 비고 |
|---|---|---|---|---|---|
| Farneback | 없음 | CPU 동작. 공식 수치 없음 (E4에서 측정) | 불필요 | `cv2.calcOpticalFlowFarneback` | 현재 기본값 |
| DIS | 없음 | TUB CrowdFlow 1280×720 기준 DIS4 1.70초, DIS2 0.28초 (i9-7980XE CPU 멀티스레드) [21] | 불필요 | `cv2.DISOpticalFlow_create` | 7.2.3 표의 값 |
| RAFT large (torchvision) | 5,257,536개, 211.01 GFLOPS, 20.1MB | 140.7ms (540×960, RTX 3090) [M7] | (확인 필요) | `torchvision.models.optical_flow.raft_large` | 입력 H·W가 8의 배수여야 한다 [M2] |
| RAFT small (torchvision) | 990,162개, 3.8MB | (확인 필요) | (확인 필요) | `raft_small` | `C_T_V2` Sintel train final EPE 3.279 (large는 2.716) [M2] |
| SEA-RAFT (M) | (확인 필요) | 70.96ms, 486.9G MACs (540×960, RTX 3090) [M7] | (확인 필요) | 저장소 클론, PyTorch 2.2·CUDA 12.2, HuggingFace 가중치 | RAFT 대비 약 2배 빠름 |
| SEA-RAFT (L) | (확인 필요) | 108.0ms, 655.1G MACs (같은 조건) [M7] | (확인 필요) | 같음 | |
| NeuFlow v2 | (확인 필요) | 0.015초 (1024×436, RTX 2080, 반정밀도). 저자 주장 Jetson Orin Nano 512×384에서 20 FPS 이상 [M8] | 8GB 장치에서 배치 26 [M8] | 저장소 클론, 가중치 3종 저장소 포함 | 가장 가벼운 축 |
| GMFlow (UniMatch) | 4.7M~7.4M | 26~122ms (448×1024, A100) [M3] | (확인 필요) | 저장소 클론, MODEL_ZOO | |
| ReCoVEr | (확인 필요) | 가장 빠른 모델 Full HD 약 20 FPS (GPU 확인 필요) [M10] | 약 500MB (같은 모델) [M10] | 저장소 클론 + release `ckpt.tar.gz` | 변형 `recover_cx`·`recover_rn`·`recover_mn` |
| MEMFOF | (확인 필요) | (확인 필요) | 저자 주장 "Full HD에서 낮은 VRAM" (수치 확인 필요) [M11] | HuggingFace 가중치 6종 | 다중 프레임. 실제 영상용으로 `Tartan-T-TSKH` 권장 |
| UFM | 0.3B~1B | 28~96ms (RTX 5090) [M15] | (확인 필요) | `pip install -e .` (서브모듈 포함) | 흐름 + 공시성 마스크 출력 |
| WAFT | (확인 필요) | 저자 주장 FlowFormer++ 대비 1.3배, CCMR+ 대비 4.1배 빠름 [M16] | (확인 필요) | PyTorch 2.7·CUDA 12.8·Python 3.12, xformers 별도 | 환경 요구가 가장 최신이다 |
| FlowFormer++ / VideoFlow / MemFlow | (확인 필요) | FlowFormer는 1024×436 RTX 2080에서 1.007초 [M8] | VideoFlow는 PyTorch 1.6·CUDA 10.1 기준 [M5] | 저장소 클론, Google Drive 가중치 | 무겁다 |

- 통합 라이브러리 **ptlflow** [M19]
    - 위 표의 모델 대부분(RAFT, SEA-RAFT, NeuFlow v2, DPFlow, ReCoVEr, MEMFOF, UFM, WAFT, MegaFlow, FlowSeek, Flow-Anything 등)을 한 API로 부른다. 2026-10-31까지 갱신됐다.
    - 설치: `pip install ptlflow`. Python 3.10~3.13, PyTorch 2.3~2.9를 지원한다 [M19].
    - 코드는 Apache-2.0이다. ptlflow가 자체 학습한 가중치는 CC BY-NC-SA 4.0이다. 모델마다 폴더에 라이선스가 따로 있다.
    - 장점: 모델 교체 비용이 작다. 단점: 의존성이 늘어난다. 가중치 라이선스를 모델마다 따로 확인해야 한다.

### 1.3 NeuFlow v2 논문의 동일 조건 비교 (참고)

- NeuFlow v2 논문 표 I은 모든 모델을 FlyingThings(합성 데이터)로만 학습한 뒤 Sintel·KITTI train에서 잰 값이다 [M8]. 학습하지 않은 장면에 대한 일반화를 보는 데 쓸 수 있다.

| 모델 | Sintel clean | Sintel final | KITTI-15 EPE | KITTI-15 Fl | 1024×436 시간 (RTX 2080) |
|---|---|---|---|---|---|
| RAFT (32회 반복) | 1.43 | 2.71 | 5.04 | 17.4 | 0.125초 |
| SEA-RAFT (M, 4회) | 1.21 | 4.04 | 4.29 | 14.2 | 0.061초 |
| SEA-RAFT (L, 12회) | 1.19 | 4.11 | 3.62 | 12.9 | 0.096초 |
| GMFlow (1회) | 1.50 | 2.96 | 10.3 | 33.6 | 0.046초 |
| FlowFormer | 1.01 | 2.40 | 4.09 | 14.7 | 1.007초 |
| NeuFlow v2 (9회) | 1.24 | 2.67 | 4.33 | 15.3 | 0.015초 |

- 이 표에서 SEA-RAFT의 Sintel final 값이 RAFT보다 나쁘다. SEA-RAFT 원 논문의 기본 학습 구성(TartanAir 포함)과 다르기 때문으로 보인다 (확인 필요).
- 논문 본문에 RTX 2080과 RTX 3080 표기가 섞여 있다. GPU 이름은 (확인 필요)다.

### 1.4 군중 영상에서의 근거

- **TUB CrowdFlow** [21] (= `references.md` [21], 저장소 [66])
    - 군중 전용 합성 광학 흐름 벤치마크다. 5개 장면, 10개 시퀀스, 1280×720, 25fps, 3,200 프레임이다. 시퀀스마다 371~1,451명이 움직인다.
    - 결론: 기존 벤치마크의 순위가 군중 영상으로 옮겨가지 않는다.
    - 7.2.3 표의 결과: 고전 방법 중 DIS4가 평균 EPE 0.784로 가장 정확했다. Sintel 상위권이던 FlowFields는 0.915였다.
    - RAFT 이후의 딥 모델로 이 벤치마크를 다시 잰 공개 결과는 찾지 못했다 (확인 필요).
    - 데이터는 학술 용도로만 쓸 수 있다. 상업 이용은 저자에게 문의해야 한다 [M20].
    - 저장소 라이선스: 메타데이터는 GPL-3.0, README는 "평가 프레임워크는 MIT"로 서로 다르다 [M20].
    - 저장소 상태: 2026-11-09 기준 `github.com/tsenst/CrowdFlow`가 404다. 보관 사이트(ecosyste.ms)에 남은 README에 데이터 다운로드 링크(HiDrive)가 있다. 링크가 지금도 살아 있는지는 (확인 필요)다.
- **DL4PuDe** (출입구 밀치기 탐지) [M12]
    - 실제 군중 실험 영상(Forschungszentrum Jülich 보행자 동역학 아카이브, CC BY 4.0)을 썼다.
    - RAFT 흐름과 Farneback 흐름으로 각각 동작 맵을 만들어 같은 분류기로 비교했다.
    - EfficientNet-B0 분류 정확도: RAFT 88%, Farneback 80%였다. 다른 분류기 3종에서도 RAFT가 6~8%p 높았다.
    - 저자는 RAFT가 밀집 군중의 가림(occlusion) 영향을 줄인다고 봤다.
    - 한계: 흐름 정확도가 아니라 하위 분류 정확도다. 군중 압력처럼 분산을 쓰는 지표에 그대로 옮겨지는지는 모른다.
- 정리: 군중에서는 "고전 DIS가 고전 방법 중 최고"[21]와 "RAFT가 Farneback보다 나음"[M12]이라는 두 근거가 있다. DIS와 RAFT를 직접 비교한 군중 자료는 찾지 못했다 (확인 필요).

### 1.5 DIS와 딥 모델의 위치

| 구분 | Farneback | DIS | RAFT (torchvision) | SEA-RAFT / NeuFlow v2 / ReCoVEr |
|---|---|---|---|---|
| 장치 | CPU | CPU | GPU 권장 | GPU |
| 추가 설치 | 없음 | 없음 | `torch`, `torchvision` | 저장소 클론 또는 `ptlflow` |
| 군중 근거 | DL4PuDe에서 RAFT보다 낮음 [M12] | TUB CrowdFlow 고전 방법 최고 [21] | DL4PuDe에서 Farneback보다 높음 [M12] | 군중 평가 없음 |
| 흐름 매끄러움 | 노이즈가 많다 | 중간 (변분 정제 포함) | 매끄럽다 | 매끄럽다 |
| Var(v)에 미치는 영향 | 노이즈가 분산을 키울 수 있다 (가정) | 중간 (가정) | 과평활화로 분산이 줄 수 있다 (가정) | RAFT와 비슷 (가정) |
| 교체 비용 | 기준 | 함수 1줄 | 모듈 1개 추가 | 환경 구성 필요 |

- 군중 압력 P는 속도 분산을 쓴다. 그래서 흐름 추정기의 노이즈 특성이 임계값 0.02/s²에 직접 영향을 준다. 이 점이 흐름 정확도보다 중요하다 (가정).
- DIS는 E4 계획에 이미 있다. 딥 모델은 E4에 비교군 하나로 더하는 정도가 범위에 맞다 `[토론]`.

---

## 2. 군중 특화 모델·데이터셋

### 2.1 모델

| 이름 | 연도·학회 | 내용 | 코드 | 가중치 | 군중 난류 관련성 | 판정 |
|---|---|---|---|---|---|---|
| MSMC-Net | 2023, AAAI 37(7) | 광학 흐름으로 그래프를 만들고 여러 축척에서 움직임 일관성을 학습해 군중 수준 이상(역류, 군중 난류)을 탐지한다 | 찾지 못함 | 찾지 못함 | **높음.** 난류를 대상에 명시하고 Hajj·Love Parade 데이터로 평가했다 | 인용만. 재현 불가 [M21] |
| DL4PuDe | 2022, Sensors / 2023, IEEE Access | RAFT 흐름 → 동작 맵 → EfficientNet-B0로 밀치기 분류 | BSD-3 (README), GitHub 메타데이터는 NOASSERTION | 분류기 저장소 포함. 학습·검증 세트는 요청 시 제공 | 중간. 출입구 밀치기이고 난류는 아니다 | 1.4절 근거로 인용 [M12] |
| Stampede detector (Cob-Parro 외) | 2025, Eng. Appl. AI 142권 | Farneback 흐름 특징 + 딥러닝 분류기로 프레임별 쇄도 판정 | 찾지 못함 | 찾지 못함 | 낮음~중간. 쇄도(달아남)이고 난류와 다르다 | Farneback 사용 사례로 인용 [M22] |
| StampSys / CrowdStampede (Nigam, Dutta) | 2022, SenSys·BuildSys 포스터 | 연합 학습 경량 모델로 쇄도·압사 영상 분류 | 찾지 못함 | 찾지 못함 | 중간. 압사 영상을 포함한다 | 확인 불가 [M23] |
| HAJJv2 기반 연구 (Alafif 외, YOLOv8·v9 후속) | 2022 arXiv, 2025 IEEE Access 등 | 개인 단위 이상 행동(역주행, 달리기, 앉기, 비인간 객체) 검출 | 찾지 못함 | 찾지 못함 | 낮음. 개인 행동이고 난류 라벨이 없다 | 개인 검출 방식이라 집계 원칙과 맞지 않는다 [M24] |
| 일반 영상 이상 탐지 (AnomalyCLIP, MTFL, GlanceVAD, MoGuP 등) | 2024~2025 | UCF-Crime·ShanghaiTech·XD-Violence의 범죄·폭력·이벤트 탐지 | 있음 | 있음 | 없음 | 쓰지 않는다 |

- 고전 방법인 사회적 힘 모델 [22]과 Loveparade 2010 흐름 분석 [2]은 학습 가중치가 없다. 판정 방법 비교는 `crowd_turbulence_research.md`에서 다룬다.
- 군중 데이터로 학습한 광학 흐름 모델(예: TUB CrowdFlow로 미세 조정한 RAFT)의 공개 가중치는 찾지 못했다 (확인 필요).

### 2.2 데이터셋

| 데이터셋 | 내용 | 고밀도 | 난류 라벨 | 공개·조건 |
|---|---|---|---|---|
| TUB CrowdFlow | 합성 군중, 정답 흐름·궤적 | 중~고 (371~1,451명) | 없음 | 학술용만. 저장소 404 (1.4절) [M20] |
| UMN | 군중이 갑자기 흩어지는 연출 영상 | 낮음 | 없음 (흩어짐 이벤트) | (확인 필요) |
| Hajj (MSMC-Net이 사용) | 하지 순례 군중 | 매우 높음 | MSMC-Net은 난류를 대상에 포함 | 배포 경로 (확인 필요) [M21] |
| Love Parade (MSMC-Net이 사용) | 2010 사고 영상 | 매우 높음 | MSMC-Net은 난류를 대상에 포함 | 배포 경로 (확인 필요) [M21] |
| HAJJv2 | 하지 개인 이상 행동 | 매우 높음 | 없음 | 다운로드 링크 찾지 못함 [M24] |
| GBA-Stampedes, GSMADC | 쇄도 연출 영상, 43,000 프레임 이상 | 낮음 (GBA 15명 이상, GSMADC 최대 6명) | 없음 (쇄도) | 저자는 공개했다고 밝힘. 링크 (확인 필요) [M22] |
| CrowdStampede | 쇄도·압사 영상 이미지 6천 장 | (확인 필요) | 압사 포함 | 링크 찾지 못함 [M23] |
| Jülich 보행자 동역학 아카이브 | 실험 영상·궤적 | 실험별 상이 | 없음 | CC BY 4.0 [M12] |

- 난류 정답이 있는 공개 데이터는 확인하지 못했다. "검출 성능 대신 관측 지표 + 민감도 분석"이라는 현재 방향과 맞다.

---

## 3. 점 추적

| 모델 | 연도·학회 | 라이선스 | 가중치 | 출력 | 판정 |
|---|---|---|---|---|---|
| CoTracker3 | 2024, arXiv 2410.11831 | **CC-BY-NC** (저장소 대부분) | `torch.hub.load("facebookresearch/co-tracker", "cotracker3_offline")` | 점 궤적 + 가시성 | 쓰지 않는다 [M25] |
| TAPIR / BootsTAPIR / TAPNext | 2023~2025, DeepMind | Apache-2.0 (가중치 포함) | PyTorch·JAX, HuggingFace `google/tapnet` | 점 궤적 | 쓰지 않는다 [M26] |
| LocoTrack | 2024, ECCV | Apache-2.0 (`cvlab-kaist/locotrack`) | 저장소에 링크 없음 (확인 필요) | 점 궤적 | 쓰지 않는다 [M27] |
| AllTracker | 2025, ICCV | MIT | HuggingFace `aharley/alltracker` (자동 다운로드) | 기준 프레임에서 다른 모든 프레임으로 가는 밀집 흐름 | 참고만 [M28] |

- 점 추적은 사람 위의 점을 프레임 내내 따라가므로 개인 궤적이 생긴다. "개인 위치를 저장하지 않는다"는 규칙과 충돌한다.
- 셀 격자 점만 추적하고 바로 셀 평균으로 집계하면 이론상 피할 수 있다. 그래도 2프레임 밀집 흐름보다 얻는 이득이 불분명하다.
- AllTracker는 출력이 밀집 흐름이라 궤적 저장 없이 쓸 수 있다. 하지만 장기 대응이 군중 압력(짧은 시간 속도 분산)에 꼭 필요하지는 않다 (가정).

---

## 4. 최근 군중 난류 영상 연구의 코드 공개 현황

- 이 장은 코드·가중치 공개 여부만 다룬다. 방법과 지표 자체는 `crowd_turbulence_research.md`를 본다.

| 연구 | 연도 | 난류·압사 직접 대상 | 코드 | 가중치 | 데이터 |
|---|---|---|---|---|---|
| MSMC-Net (Luo 외) | 2023 | 예 (난류·역류) | 찾지 못함 | 찾지 못함 | Hajj·Love Parade 배포 (확인 필요) |
| Stampede detector (Cob-Parro 외) | 2025 | 쇄도 | 찾지 못함 | 찾지 못함 | 공개했다고 밝힘 (확인 필요) |
| StampSys / CrowdStampede | 2022 | 쇄도·압사 | 찾지 못함 | 찾지 못함 | 찾지 못함 |
| DL4PuDe (Alia 외) | 2022~2023 | 밀치기 | 있음 (BSD-3) | 분류기 포함 | 테스트 세트 공개, 학습 세트는 요청 시 |
| HAJJv2 계열 | 2022~2025 | 개인 이상 행동 | 찾지 못함 | 찾지 못함 | 찾지 못함 |

- 2023~2026년 연구 중 "영상 → 군중 압력·난류 자동 판정"을 코드와 가중치까지 공개한 것은 찾지 못했다.
- 이태원 참사 영상에 흐름·밀도 분석을 적용하고 코드를 공개한 연구도 찾지 못했다.

---

## 5. 통합 방법

### 5.1 공통 원칙

- 흐름장은 메모리 안에서만 쓰고 바로 셀 통계(평균, 제곱 평균)로 줄인다. 파일로 저장하지 않는다 (CLAUDE.md 개인정보 규칙).
- 같은 셀 격자와 같은 집계 함수를 모든 흐름 추정기에 쓴다. 그래야 E4 비교가 공정하다.
- 흐름 단위는 px/frame이다. 군중 압력 단위(1/s²)를 맞추려면 프레임 간격(초)과 호모그래피로 m/s로 바꾼다. 이 변환은 [1]의 임계값과 비교하려면 반드시 필요하다.
    - 픽셀 격자 셀이면 셀마다 원근이 달라 1픽셀의 실제 길이가 다르다. 셀 중심의 지면 축척을 곱하는 근사를 쓸 수 있다 (가정).
    - 지면 격자 셀이면 흐름의 시작점과 끝점을 호모그래피로 옮겨 지면 변위를 구한 뒤 집계한다 (가정).
- Var(v)를 공간 분산(셀 안 픽셀 간)으로 볼지 시간 분산(셀 평균의 시간 창 안 변화)으로 볼지는 `crowd_turbulence_research.md`의 정의를 따른다. 아래 코드는 둘 다 만들 수 있게 평균과 제곱 평균을 함께 낸다.

### 5.2 후보 1: OpenCV DIS (추가 설치 없음)

- 입력: 회색조 `uint8` 프레임 2장.
- 프리셋: `ULTRAFAST`·`FAST`·`MEDIUM`이 있다. TUB CrowdFlow의 DIS4·DIS2 표기와 프리셋의 대응은 (확인 필요)다.

```python
import cv2

dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
flow = dis.calc(prev_gray, next_gray, None)  # (H, W, 2), float32, px/frame
```

### 5.3 후보 2: torchvision RAFT

- 설치: `torch`, `torchvision`. 현재 `requirements.txt`에는 아무 패키지도 없다. 추가하려면 팀 승인이 필요하다 (CLAUDE.md 패키지 규칙). P2PNet도 PyTorch를 쓰므로 같은 버전을 공유하는 것이 좋다 (가정).
- 가중치: `Raft_Large_Weights.DEFAULT`(= `C_T_SKHT_V2`, 20.1MB) 또는 `Raft_Small_Weights.DEFAULT`(3.8MB). 첫 실행 때 자동으로 내려받는다 [M2].
- 입력 조건 [M2]:
    - 높이·너비가 8의 배수여야 한다. 아니면 `ValueError`가 난다.
    - 최소 128×128이다.
    - `weights.transforms()`가 값을 [-1, 1]로 바꾼다.
- 해상도: 1080p 원본은 무겁다. 960×544처럼 8의 배수로 줄여 넣고, 흐름 값에 축소 비율을 다시 곱해 원래 픽셀 단위로 돌린다 (가정).
- 반복 횟수: 기본 `num_flow_updates=12`다. 줄이면 빨라지고 정확도가 떨어진다.

```python
import torch
import torch.nn.functional as F
from torchvision.models.optical_flow import raft_large, Raft_Large_Weights

weights = Raft_Large_Weights.DEFAULT
model = raft_large(weights=weights).eval().cuda()
preprocess = weights.transforms()


@torch.no_grad()
def cell_flow_stats(img1: torch.Tensor, img2: torch.Tensor, cell_px: int) -> tuple[torch.Tensor, torch.Tensor]:
    """두 프레임의 흐름을 구해 셀 평균 속도와 셀 내부 속도 분산만 돌려준다.

    img1, img2: (1, 3, H, W) uint8 텐서. H, W는 8과 cell_px의 배수.
    흐름장 자체는 반환하지도 저장하지도 않는다.
    """
    a, b = preprocess(img1, img2)
    flow = model(a.cuda(), b.cuda())[-1]                   # (1, 2, H, W), 마지막 반복 결과
    mean = F.avg_pool2d(flow, cell_px)                      # 셀 평균 (u, v)
    sq = F.avg_pool2d((flow ** 2).sum(1, keepdim=True), cell_px)
    var = sq - (mean ** 2).sum(1, keepdim=True)             # 셀 내부 속도 분산 (px^2/frame^2)
    return mean.cpu(), var.cpu()
```

- 이 함수는 픽셀 격자 셀 기준이다. 지면 격자 셀이면 5.1의 변환 후 셀 마스크별로 평균을 구한다.
- 같은 함수에 Farneback·DIS 흐름(`numpy` 배열)을 텐서로 바꿔 넣으면 같은 집계로 비교할 수 있다.

### 5.4 후보 3: ptlflow 경유 (SEA-RAFT, NeuFlow v2, ReCoVEr)

- 설치: `pip install ptlflow` [M19]. PyTorch 2.3~2.9가 먼저 있어야 한다.
- 장점: 모델 이름만 바꿔 여러 모델을 같은 코드로 비교할 수 있다.
- 사용 API와 모델 이름 문자열은 ptlflow 문서를 따른다 (확인 필요). 이 문서에는 검증하지 않은 코드를 적지 않는다.
- 가중치 라이선스: ptlflow 자체 학습 가중치(CC BY-NC-SA 4.0)인지, 원 저자 가중치인지 모델 폴더에서 확인한다.

### 5.5 처리 시간 추정 (가정)

- 분석 주기를 1Hz로 잡으면 영상 1분당 흐름 계산은 60쌍이다.
- RAFT large가 540×960에서 쌍당 140.7ms(RTX 3090)라면 1분 영상에 약 8.4초다 [M7]. 노트북 GPU에서는 몇 배 느릴 수 있다 (확인 필요).
- 오프라인 사전 분석이므로 실시간이 필요 없다. 총 처리 시간과 VRAM 한도 안에 드는지가 기준이다.

---

## 6. 위험

| 위험 | 내용 | 대응 |
|---|---|---|
| 도메인 차이 | 딥 흐름 모델은 Sintel·KITTI·Spring·TartanAir 같은 합성·주행 데이터로 학습됐다. 원거리 CCTV 군중은 사람이 몇 픽셀이고, 압축 노이즈와 반복 질감이 많다. TUB CrowdFlow 저자도 기존 순위가 군중에 옮겨지지 않는다고 했다 [21] | 벤치마크 순위로 고르지 않는다. 우리 영상에서 정지 구간 노이즈와 Var(v) 분포를 직접 비교한다 |
| 임계값 의존 | 0.02/s²는 메카 측정값이다 [1]. 흐름 추정기가 바뀌면 같은 장면의 Var(v)가 바뀐다 | 민감도 분석에 "흐름 추정기"를 축으로 넣는다. 정지 배경의 분산(노이즈 바닥)을 함께 보고한다 |
| 라이선스 | 학술용만: DPFlow 가중치, UFM 가중치(CC BY-NC-SA), ptlflow 자체 학습 가중치, CoTracker3(CC-BY-NC), FlowSeek이 쓰는 Depth Anything v2 Base/Large(CC-BY-NC), TUB CrowdFlow 데이터. 명시 없음: ReCoVEr 가중치 | 사업성 절을 고려하면 BSD-3·Apache·MIT 모델(RAFT, SEA-RAFT, NeuFlow v2, UniMatch)을 우선한다. P2PNet 학술용 제약 [60]과 같은 수준으로 기록한다 |
| 연산 자원 | 트랜스포머·다중 프레임 계열(FlowFormer++, VideoFlow, MemFlow, WAFT, UFM)은 노트북 VRAM을 넘을 수 있다 (확인 필요) | 입력을 줄이고 RAFT small·NeuFlow v2 같은 경량 모델을 먼저 시험한다 |
| 환경 충돌 | WAFT는 PyTorch 2.7·CUDA 12.8, VideoFlow는 PyTorch 1.6을 요구한다. P2PNet 환경과 버전이 엇갈릴 수 있다 | 공용 환경에는 torchvision RAFT만 넣는다. 나머지는 별도 가상환경에서 시험한다 `[토론]` |
| 프라이버시 | 점 추적은 개인 궤적을 만든다. 밀집 흐름도 픽셀 단위로 저장하면 개인 움직임이 남는다 | 점 추적은 쓰지 않는다. 흐름장은 메모리에서 바로 셀 통계로 줄이고 저장하지 않는다 |
| 출처 소실 | TUB CrowdFlow 저장소가 404다. `references.md` [66] 링크가 깨졌다 | 보관 사이트 기록 [M20]을 보조 출처로 단다. `references.md` 수정 여부는 팀이 정한다 `[토론]` |
| 일정 | 코드 동결까지 10일이다 | 딥 모델은 E4 비교군 1개로 제한한다 |

---

## 7. 제안 `[토론]`

- 아래는 Claude의 제안이다. 팀 회의에서 정한다.

| 순서 | 제안 | 근거 | 비용 |
|---|---|---|---|
| 1 | Farneback 유지, E4에서 DIS 비교 (기존 계획) | 7.2.3 결정, TUB CrowdFlow [21] | 낮음 |
| 2 | E4에 torchvision RAFT를 비교군으로 추가 `[토론]` | 군중 영상에서 Farneback 대비 우위 보고 [M12]. BSD-3. 설치가 `torchvision` 하나다 | 1~2일 (가정) |
| 3 | 비교 지표는 EPE가 아니라 "같은 클립의 셀 Var(v)·P 분포, 정지 구간 노이즈 바닥, 처리 시간"으로 한다 `[토론]` | 우리 영상에는 정답 흐름이 없다 | 낮음 |
| 4 | TUB CrowdFlow를 내려받을 수 있으면 RAFT의 EPE를 직접 재 7.2.3 표의 빈칸을 채운다 `[토론]` | 이 벤치마크의 딥 모델 수치가 없다 | 다운로드 가능 여부 (확인 필요) |
| 5 | 여유가 있으면 ptlflow로 SEA-RAFT·NeuFlow v2·ReCoVEr를 같은 실험에 더한다 (G2 이후) | 속도·VRAM 대안 | 별도 환경 필요 |
| 6 | 점 추적, 일반 영상 이상 탐지, 학술용만 허용된 가중치는 MVP에서 쓰지 않는다 | 프라이버시·도메인·라이선스 | 없음 |

- `references.md`에 새 출처(SEA-RAFT, DL4PuDe 등)를 추가할지는 기획서에 인용할 때 정한다. 추가하면 기존 번호 뒤에 붙인다.

---

## 출처

`(= references.md [n])`은 팀 공용 출처 목록과 같은 자료라는 뜻이다. 본문의 [1], [2], [18]~[22], [60], [66]은 `references.md` 번호다.

- [M1] Teed, Z., Deng, J. (2020). RAFT: Recurrent All-Pairs Field Transforms for Optical Flow. *ECCV*. <https://arxiv.org/abs/2003.12039> 코드: <https://github.com/princeton-vl/RAFT> (= references.md [20])
- [M2] torchvision RAFT 문서와 소스. <https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.optical_flow.raft_large.html>, <https://github.com/pytorch/vision/blob/main/torchvision/models/optical_flow/raft.py>
- [M3] Xu, H. 외 (2023). Unifying Flow, Stereo and Depth Estimation. *IEEE TPAMI*. <https://arxiv.org/abs/2211.05783> 코드: <https://github.com/autonomousvision/unimatch> (MODEL_ZOO.md)
- [M4] FlowFormer++ 공식 저장소. <https://github.com/XiaoyuShi97/FlowFormerPlusPlus> (FlowFormer: <https://github.com/drinkingcoder/FlowFormer-Official>)
- [M5] VideoFlow 공식 저장소 (ICCV 2023). <https://github.com/XiaoyuShi97/VideoFlow>
- [M6] Dong, Q., Fu, Y. (2024). MemFlow. *CVPR*. <https://github.com/DQiaole/MemFlow>
- [M7] Wang, Y., Lipson, L., Deng, J. (2024). SEA-RAFT: Simple, Efficient, Accurate RAFT for Optical Flow. *ECCV*. <https://arxiv.org/abs/2405.14793> 코드: <https://github.com/princeton-vl/SEA-RAFT>
- [M8] Zhang, Z. 외 (2024). NeuFlow v2: Push High-Efficiency Optical Flow To the Limit. arXiv 2408.10161. <https://arxiv.org/abs/2408.10161> 코드: <https://github.com/neufieldrobotics/NeuFlow_v2>
- [M9] Morimitsu, H. 외 (2025). DPFlow: Adaptive Optical Flow Estimation with a Dual-Pyramid Framework. *CVPR*. <https://arxiv.org/abs/2503.14880> 가중치 라이선스: <https://github.com/hmorimitsu/ptlflow/tree/main/ptlflow/models/dpflow>
- [M10] Kiefhaber, S., Roth, S., Schaub-Meyer, S. (2025). Removing Cost Volumes from Optical Flow Estimators (ReCoVEr). *ICCV*. <https://arxiv.org/abs/2510.13317> 코드: <https://github.com/visinf/recover>
- [M11] MEMFOF 공식 저장소 (ICCV 2025 Highlight). <https://github.com/msu-video-group/memfof>
- [M12] Alia, A., Maree, M., Chraibi, M. (2022). A Hybrid Deep Learning and Visualization Framework for Pushing Behavior Detection in Pedestrian Dynamics. *Sensors*, 22(11), 4040. <https://pmc.ncbi.nlm.nih.gov/articles/PMC9185482/> 코드: <https://github.com/PedestrianDynamics/DL4PuDe>
- [M13] Poggi, M., Tosi, F. (2025). FlowSeek: Optical Flow Made Easier with Depth Foundation Models and Motion Bases. *ICCV*. <https://arxiv.org/abs/2509.05297> 코드: <https://github.com/mattpoggi/flowseek>
- [M14] Depth Anything V2 저장소 (모델 크기별 라이선스). <https://github.com/DepthAnything/Depth-Anything-V2>
- [M15] UFM: Unified Flow & Matching (NeurIPS 2025). <https://github.com/UniFlowMatch/UFM>
- [M16] WAFT: Warping-Alone Field Transforms for Optical Flow (ICLR 2026). <https://arxiv.org/abs/2506.21526> 코드: <https://github.com/princeton-vl/WAFT>
- [M17] Zhang, D., Wang, F., Pollefeys, M., Xu, H. (2026). MegaFlow: Zero-Shot Large Displacement Optical Flow. arXiv 2603.25739. <https://arxiv.org/abs/2603.25739> 코드: <https://github.com/cvg/megaflow>
- [M18] Flow-Anything: Learning Real-World Optical Flow Estimation from Large-Scale Single-view Images. arXiv 2506.07740. <https://arxiv.org/abs/2506.07740>
- [M19] ptlflow 저장소·설치 문서. <https://github.com/hmorimitsu/ptlflow>, <https://ptlflow.readthedocs.io/en/latest/starting/installation.html>
- [M20] Schröder, G., Senst, T., Bochinski, E., Sikora, T. (2018). Optical Flow Dataset and Benchmark for Visual Crowd Analysis. *AVSS*. <https://arxiv.org/abs/1811.07170> (= references.md [21]). 저장소 <https://github.com/tsenst/CrowdFlow> (= references.md [66], 2026-11-09 접속 시 404). 보관 기록: <https://awesome.ecosyste.ms/api/v1/projects/github.com%2Ftsenst%2Fcrowdflow>
- [M21] Luo, L. 외 (2023). Crowd-Level Abnormal Behavior Detection via Multi-Scale Motion Consistency Learning. *AAAI*, 37(7), 8984–8992. <https://arxiv.org/abs/2212.00501>, <https://ojs.aaai.org/index.php/AAAI/article/view/26079>
- [M22] Cob-Parro, A. C., Losada-Gutiérrez, C., Marrón-Romera, M. (2025). Stampede detector based on deep learning models using dense optical flow. *Engineering Applications of Artificial Intelligence*, 142, 109940. DOI 10.1016/j.engappai.2024.109940. <https://ebuah.uah.es/dspace/handle/10017/64014>
- [M23] Nigam, N., Dutta, T. (2022). StampSys (SenSys 2022) / 군중 압사 탐지 포스터 (BuildSys 2022). <https://idr-sdlib.iitbhu.ac.in/items/c00dc65d-8ee1-4840-b27f-4ba87fea0de4/full>
- [M24] Alafif, T. 외 (2022). Hybrid Classifiers for Spatio-temporal Real-time Abnormal Behaviors Detection, Tracking, and Recognition in Massive Hajj Crowds. arXiv 2207.11931. <https://arxiv.org/abs/2207.11931>
- [M25] CoTracker 저장소 (CoTracker3, arXiv 2410.11831). <https://github.com/facebookresearch/co-tracker>
- [M26] DeepMind TAPNet 저장소 (TAPIR, BootsTAPIR, TAPNext). <https://github.com/google-deepmind/tapnet>
- [M27] LocoTrack 저장소 (ECCV 2024). <https://github.com/cvlab-kaist/locotrack>
- [M28] AllTracker 저장소 (ICCV 2025, arXiv 2506.07310). <https://github.com/aharley/alltracker>
- 그 밖에 본문이 인용한 `references.md` 출처: [1] Helbing 외 2007, [2] Krausz·Bauckhage 2012, [18] Farnebäck 2003, [19] Kroeger 외 2016 (DIS), [22] Mehran 외 2009, [60] P2PNet 저장소.
