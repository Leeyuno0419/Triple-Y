# 군중난류 감지 조사 (crowd turbulence research)

## 문서 상태

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-09 |
| 작성자 | 조영준 (Claude 작성 보조) |
| 상태 | 초안. 팀 검토 전이다 |
| 대상 | 흐름·군중 불안정 모듈(`src/flow/`) 설계, E5 실험 계획 |
| 기준 문서 | `docs/proposal.md` 3.3·3.4, `docs/proposal-detail.md` 3.4(3)·7.2.3·7.2.4 |

- 이 문서는 조사 자료다. 범위·담당·일정의 기준은 여전히 `docs/proposal.md`다.
- 출처 번호 `[Rn]`은 이 문서 끝의 출처 목록이다. `references.md`에 이미 있는 출처는 `(= references.md [n])`로 함께 적었다.
- 팀이 정하지 않은 제안은 `[토론]` 또는 `(가정)`, 원문으로 검증하지 못한 내용은 `(확인 필요)`로 표시했다.

---

## 요약

- **군중난류는 극고밀도에서 생긴다.** 메카 2006년 사고 영상에서는 층류 → 정지·진행파(11:53) → 난류(12:19) 순으로 바뀌었고, 사고는 난류 시작 약 10분 뒤에 시작됐다 [R1]. 이때 국소 밀도는 10명/㎡를 넘었다 [R1]. 이태원 사고 골목의 특수본 추정 밀도는 사고 시각 7.72~8.39명/㎡, 최대 9.07~10.74명/㎡였다 [R12].
- **0.02/s²는 그대로 옮겨 쓸 수 있는 값이 아니다.** 원 저자들이 직접 "측정 방법의 매개변수, 특히 R에 따라 달라지고 군중 종류에도 달라질 수 있으므로 보정해야 한다"고 썼다 [R2]. 원 연구는 개인 추적 궤적, 반경 R = 1m 가우시안 가중, 8fps, 그리고 45분 시간 평균 속도와의 차이로 분산을 계산했다 [R1].
- **현재 계획의 `Var_c(v)`는 원 정의와 다른 양이다.** 계획은 한 순간 셀 안의 픽셀 속도 퍼짐(공간 분산)을 쓰는데, 원 정의는 같은 위치에서 시간에 따른 속도 흔들림(시간 분산)이다. 또 광학 흐름 잡음이 분산에 그대로 더해진다. 잡음 0.1m/s 수준이면 밀도 5명/㎡에서 잡음만으로 0.02/s²를 넘을 수 있다(계산 예시, 5.4).
- **최근 연구는 추적 없이 속도장으로 감지하는 방향이다.** 2025년 Nature 논문은 P2PNet 머리 검출 + 호모그래피로 밀도를 구하고, PIV(영상 상관 기반 속도장)로 속도장을 구해, 4.0±0.5명/㎡ 이상에서 주기 약 18초의 집단 진동을 찾았다 [R4]. 저자들은 운동에너지 스펙트럼의 주파수 추적을 추적 없이 쓸 수 있는 실시간 감시 방법으로 제안했다 [R4]. 데이터·영상은 CC BY 4.0으로 공개됐다 [R5].
- **정답 라벨이 있는 "난류" 데이터셋은 찾지 못했다.** 대신 (1) 궤적 정답이 있는 고밀도 실험 영상(Jülich 자료실, 10명/㎡ 초과 사례, CC BY 4.0) [R20][R21], (2) 1초 단위 밀기(pushing) 라벨 [R21], (3) 고밀도 실제 영상(팜플로나) [R5], (4) 시뮬레이터(PySocialForce MIT, JuPedSim LGPLv3)로 검증할 수 있다.
- **제안 요지** `[토론]`: 군중 압력은 유지하되 (1) 시간 분산으로 정의를 바꾸고, (2) 장면별 잡음 바닥을 빼고, (3) 0.02/s²는 "참고선"으로만 두고 경보 기준은 장면 기준선 대비 상대값으로 잡고, (4) 정지·진행파 지표와 역방향 흐름 비율을 보조로 둔다. E5의 "재현율 0.8" 기준은 양성 라벨이 없어 측정할 수 없으므로 검증 방식을 바꾼다.

---

## 1. 현상: 군중난류란 무엇인가

### 1.1 정의와 단계

- **군중난류(crowd turbulence)**: 극고밀도 군중에서 사람들이 스스로 움직임을 통제하지 못하고, 군중 전체가 갑자기 여러 방향으로 밀리는 불규칙 운동이다 [R1].
    - "crowd quake"(군중 지진)라고도 부른다. 쌓인 힘이 갑자기 풀리면서 사람들이 수 미터씩 밀리고 넘어진다 [R1][R8].
- **정지·진행파(stop-and-go wave)**: 앞으로 가다 멈추기를 반복하는 움직임이 군중 뒤쪽으로 전파되는 파동이다 [R1].
- **힘 사슬(force chain)**: 빽빽한 입자(사람) 사이에 접촉력이 사슬처럼 이어져 힘이 멀리 전달되는 구조다. 입상 물질(모래 같은 알갱이 물질) 연구의 개념이다 [R1].
- 메카 2006년 사고 영상에서 관찰된 흐름 단계는 아래와 같다 [R1].

| 시각 (2006-01-12) | 흐름 상태 | 관찰 내용 |
|---|---|---|
| ~11:53 | 층류 → 정지·진행파 | 평균 유량이 0.8명/(m·s) 아래로 떨어지면서 시작. 상류로 전파되며 20분 넘게 지속 |
| 12:19 | 정지·진행파 → 난류 | "압력"이 0.02/s²를 넘은 시점 |
| 약 12:29 | 사고 시작 | 난류 시작 약 10분 뒤, 압력이 최고일 때 |

- 원 연구의 난류 특징은 다음과 같다 [R1].
    - 속도 증분 분포가 짧은 시간 간격에서 뾰족한(비정규) 모양이 된다. 층류와 구분되는 특징이다.
    - 정지 사이 변위 분포가 멱법칙(기울기 2.01±0.15)을 따른다. 지진 규모 분포와 닮았다.
    - 큰 소용돌이는 보이지 않는다. 유체 난류와의 유사성은 제한적이며, 덩어리가 여러 크기로 쪼개지는 "계층적 분열"에 가깝다.
- 원 연구는 이 "압력"이 기계적 압력(몸이 받는 힘)과 다르다고 밝힌다. 다만 둘 사이에 단조 증가 관계가 있을 것으로 본다 [R1].

### 1.2 밀도 기준

| 출처 | 밀도 | 내용 |
|---|---|---|
| Helbing 외 2007 [R1] | 국소 > 10명/㎡ | R = 1m 기준 국소 밀도. 국소 최대는 평균의 약 2배. 평균 밀도는 6명/㎡을 거의 넘지 않았다 |
| Helbing 외 2007 [R1] | 6명/㎡ 초과 | 국소 유량이 3배 이상 감소 |
| Fruin (Helbing 외 2007에서 인용) [R1] | 약 7명/㎡ | "군중이 거의 유체 덩어리가 된다." 충격파가 사람을 3m 이상 밀어낼 수 있다 |
| Gu 외 2025 [R4] | 4.0±0.5명/㎡ | 집단 진동(키랄 진동)이 시작되는 임계 밀도. 평균 약 6명/㎡, 국소 약 9명/㎡까지 관찰 |
| Gu 외 2025 [R4] | 8±1명/㎡ | 러브 퍼레이드 영상 한 장면의 추정 밀도 (영상 1장 수작업 주석) |
| 특수본 (뉴시스) [R12] | 7.72~8.39 → 9.07~10.74명/㎡ | 이태원 사고 골목, 22:15 → 22:25 |
| Liang 외 2024 [R10] | 평균 7.57, 최대 9.95명/㎡ | 이태원 재현 유체역학 시뮬레이션 결과 (측정값 아님) |
| Adrian 외 2020 [R20] | 일부 10명/㎡ 초과 | 입구 실험, 넓은 통로·높은 동기 조건, 목표 2m 이내 |

- **주의**: Helbing 외는 Weidmann 곡선과 맞추려고 밀도에 0.7을 곱한 비교도 했다. 체격 차이 때문이라고 설명한다 [R1]. 밀도 기준값은 집단의 체격에 따라 달라질 수 있다.
- **우리 등급과의 관계**: 등급표의 "심각"은 5명/㎡이다(`proposal.md` 3.2). 위 문헌에서 난류는 대체로 6~7명/㎡ 이상에서 보고된다. 즉 난류 지표는 이미 "심각"에 가까운 상황에서만 의미가 커진다. 반면 집단 진동은 4명/㎡ 부근에서 시작된다는 보고가 있다 [R4].

### 1.3 주요 실증 연구

| 연구 | 대상 | 방법 | 핵심 결과 |
|---|---|---|---|
| Helbing, Johansson, Al-Abideen 2007 [R1] | 메카 2006 사고 영상 | 자체 머리 검출·추적, 25px/m, 8fps, 20m×14m 중심 구역, 3천만 개 이상 위치·속도 쌍 | 두 번의 급격한 전이, 군중 압력 제안 |
| Johansson 외 2008 [R2] | 같은 현장 | 같은 방법, 상세 방법론 | 밀도·발산·회전·압력 지도 비교. 압력이 위험 위치·시간을 가장 잘 짚음. 기준값은 보정 필요라고 명시 |
| Krausz, Bauckhage 2011·2012 [R6][R7] | 러브 퍼레이드 2010 공개 영상 | Farneback 광학 흐름, 셀별 흐름 히스토그램 | 정체·충격파 감지 시도. 추적 없이 실시간, 사생활 보호 장점 |
| Helbing, Mukerji 2012 [R8] | 러브 퍼레이드 2010 | 공개 영상·계획 자료 정성 분석 | 공황이 아니라 체계적 실패. 넘어짐이 도미노처럼 이어짐 |
| Sieben, Seyfried 2023 [R9] | 러브 퍼레이드 2010 | 목격자 진술 내용 분석 | 군중 내부 경험 분석. 의도적·비의도적 밀기 구분 |
| Gu 외 2025 [R4] | 팜플로나 산 페르민 축제 (2019·2022·2023·2024) | P2PNet + 호모그래피 + PIV, 4K, 25/30fps, 관측 높이 16m | 4명/㎡ 이상에서 주기 약 18초 집단 진동. 러브 퍼레이드 영상에서도 같은 진동 |
| Liang 외 2024 [R10] | 이태원 2022 | 이동통신 자료 + 유체역학 시뮬레이션 | 양방향 충돌 재현, 밀도·압력·속도 엔트로피 산출 |
| 황·김 외 2025 [R11] | 이태원 2022 | 밀도별로 모델을 바꾸는 시뮬레이션(4명/㎡ 이상에서 SPH 유체 모델) | CCTV 영상과 비교해 현상 재현을 주장 |

- **아스트로월드(2021)**: 동료 심사를 거친 정량 분석 논문은 찾지 못했다 (확인 필요). 언론 조사 보도만 확인됐다.
- **하지(Hajj)**: 2006년 이후 정량 영상 분석은 [R1][R2]가 대표적이다. 최근에는 메카 영상으로 개인 속도 이상 감지를 다룬 프리프린트가 있다 [R31].

### 1.4 통제 실험

| 실험 | 내용 | 활용성 |
|---|---|---|
| Jülich·BaSiGo 2013 (뒤셀도르프) | 통로 단방향·양방향·교차·입구 실험. 궤적 공개 | 고밀도 궤적 정답 [R21] |
| 입구 실험 2018 (`crowdqueue`) [R20][R21] | 통로 폭 1.2~5.6m, 490명, 24회. 25fps 궤적·영상 | 10명/㎡ 초과 사례, 머리 위 시점 |
| 밀기 라벨 2022 (`effect_on_pushing`) [R21] | 위 실험 14회에 1초 단위 4단계 라벨(강한 밀기·약한 밀기·걷기·뒤처짐) | 사람 단위 "불안정 행동" 약한 정답 |
| 충격 전파 2022 [R21] | 작은 정지 군중에서 밀기 전파 | 힘 전파 연구 (확인 필요: 영상 상세) |
| Garcimartín 외 2017 [R19] | 경쟁적 대피, 서로 적당히 밀기 허용 | 경쟁도에 따라 밀도 등고선 모양이 바뀜 |
| Bain, Bartolo 2019 [R18] | 마라톤 출발 대기 군중 | 속도 정보는 수백 m 전파, 방향 정보는 수 m 안에 사라짐. 전파 속도는 1m/s 남짓(보도자료 기준) |
| Bottinelli 외 2016 [R17] | 시뮬레이션(능동 물질 모델) | 고밀도 집단 운동의 구조적 기전(골드스톤 모드, 무른 지점, 확률 공명) |

- BaSiGo 참가자 수는 출처마다 다르다(약 2,000명, 약 2,100명 등) (확인 필요).

---

## 2. 지표

### 2.1 군중 압력 (Helbing 외 2007)

**정의** [R1]

```
국소 밀도   rho(r,t) = Σ_j f(r_j(t) − r)
가중 함수   f(d)     = (1 / (π R²)) · exp(−|d|² / R²)
국소 속도   V(r,t)   = Σ_j v_j f(r_j − r) / Σ_j f(r_j − r)
시간 평균   U(r)     = <V(r,t)>_t                    (11:45~12:30, 45분 평균)
속도 분산   Var_rt(V) = <[V(r,t) − U(r)]²>_t
군중 압력   P(r,t)   = rho(r,t) · Var_rt(V)          단위: (1/m²)·(m²/s²) = 1/s²
```

- R은 측정 반경이다. 원 연구의 기본값은 R = 1m다. 반경 R 안의 사람이 가중치의 63%를 차지한다 [R1].
- 시간 그래프(Fig. 3c)는 다른 정의를 썼다. 중심 구역 전체의 공간 평균 밀도 × 공간 분산 `<[V(r,t) − <V>_r]²>_r`이다 [R1]. 즉 원 논문 안에서도 정의가 두 가지다.
- 0.02/s²는 이 시간 그래프에서 난류가 시작된 12:19의 값이다 [R1].

**전이 가능성 판단**

- 원 저자들의 직접 언급: "임계 유량 0.8과 임계 압력 0.02/s²는 측정 방법의 매개변수, 특히 R의 선택에 따라 달라지고 군중 종류 같은 다른 요인에도 달라질 수 있다. 따라서 이 기준은 적절히 보정해야 한다" [R2].
- 같은 글에서 저자들은 자동 경보보다 "빨리 감기 영상을 보며 정지·진행파와 난류를 찾는 방식"을 권하고, 영상에 압력 강도를 겹쳐 보여 주는 방식을 제안했다 [R2].
- 원 연구는 자기 데이터에 대해서도 2005년 같은 장소에서는 압력이 그렇게 높지 않았고 사고가 없었다고만 썼다 [R1]. 다른 장소·장비에서 0.02/s²를 독립 검증한 연구는 찾지 못했다 (확인 필요).
- 2차 문헌(예: [R35])에 "0.04/s²에서 압사 시작"이라는 서술이 있다고 검색 요약에서 봤다 (확인 필요). 원 논문에서는 이 값을 확인하지 못했다. 원 논문 Fig. 3c의 0.04는 축 눈금이다. 쓰지 않는다.

**정리**

| 항목 | 원 연구 [R1][R2] | 현재 계획 (`proposal-detail.md` 3.4) |
|---|---|---|
| 속도 출처 | 개인 머리 추적 | Farneback 픽셀 흐름 (머리 주변 픽셀) |
| 공간 단위 | 가우시안 R = 1m | 2m×2m 셀 |
| 분산 종류 | 시간 분산 (45분 평균과의 차이) 또는 구역 공간 분산 | 순간 셀 내부 공간 분산 |
| 시간 해상도 | 8fps | Δt = 0.2초, 판정 1Hz |
| 밀도 | 같은 추적 자료로 계산 | P2PNet + 호모그래피, EMA 평활 |
| 기준 | 0.02/s² (보정 필요라고 명시) | 0.02/s² 시작값, ROC로 조정 |

### 2.2 속도 분산 단독

- 밀도를 곱하지 않은 `Var(V)` 자체다. 단위는 m²/s²다.
- 장점: 밀도 추정 오차와 분리된다. 밀도는 따로 등급 판정에 쓰이므로 중복을 줄인다.
- 단점: 저밀도에서 사람들이 자유롭게 엇갈려 걸어도 커진다. 원 저자들이 밀도를 곱한 이유가 이것이다 [R2].
- Gu 외는 임계 밀도 위에서 속도 흔들림이 밀도에 따라 선형으로 커진다고 보고했다 [R4]. 속도 흔들림이 고밀도 위험 신호라는 점은 지지된다.

### 2.3 회전(와도)·발산

```
와도   ω   = ∂v_y/∂x − ∂v_x/∂y        단위 1/s
발산   div = ∂v_x/∂x + ∂v_y/∂y        단위 1/s
```

- **와도(vorticity)**: 속도장의 국소 회전 세기다.
- **발산(divergence)**: 속도장이 퍼지는지(양수) 모이는지(음수) 나타낸다. 음수가 크면 압축이다.
- Johansson 외는 메카 자료로 밀도·음의 발산·회전·압력 지도를 비교했다. 사고 지점을 가장 잘 짚은 것은 압력이었다 [R2].
- 와도는 부호가 회전 방향을 뜻하므로, 질서 있는 회전(예: 춤추는 두 사람)도 큰 값을 낸다 [R14]. 단독 경보로 쓰기 어렵다.

### 2.4 혼잡도(congestion level)·군중 위험도(crowd danger) (Feliciani, Nishinari 2018)

**정의** [R13][R14]

```
속도장        격자 0.2m, 표본 구간 2.5초 (궤적 미분 → 셀 평균)
와도          ω = (∇ × v)_z, 중앙 차분
혼잡도        CL = (ω_max − ω_min) / |v_avg|       단위 1/m
               ROI(관심 영역) = 지름 7셀(1.4m) 원형, ω_max·ω_min·|v_avg|는 ROI 안 값
군중 위험도   CD = CL × rho                        단위 1/m³
```

- 실험에서 최대 CL은 약 15 m⁻¹에서 포화되는 경향을 보였다 [R14].
- 저자들은 CD의 경고 기준을 확정하지 못했고, "75 m⁻³ 이상이면 주의가 필요하다고 추측한다"고 썼다 [R14]. 검증된 기준이 아니다.
- 후속 연구는 CL이 무차원 수가 아니어서 해석이 어렵고, 국소량(회전)과 전역량(최댓값·평균)을 섞었다고 비판했다 [R15][R16].
    - 대안으로 **혼잡수(Congestion Number, CN)**를 제안했다. 운영 정의는 `CN ≈ CL × R / 6`(R은 ROI 반경)이다 [R15].
    - 원 실험의 최대 CN은 약 0.5로 추정되며, 1에 가까우면 극심한 혼잡이다. 다만 1을 넘을 수도 있다 [R15].
    - 2023년 TRC 논문으로 정식 게재됐다 [R16].
- 입력: 0.2m 격자의 속도장. 원 연구는 궤적에서 만들었다. 광학 흐름 속도장의 0.2m 해상도는 머리 크기(약 0.2m)와 같아, CCTV 원거리에서는 확보하기 어렵다 (가정).

### 2.5 엔트로피·무질서 지표

- **속도 엔트로피**: 국소 속도 방향·크기 분포의 무질서 정도다. Liang 외는 이태원 시뮬레이션에서 최대 속도 엔트로피 10.99를 보고했다 [R10]. 정확한 정의식은 확인하지 못했다 (확인 필요).
- Harding 외 2010은 정보이론으로 군중 무질서를 재서 압사 시작을 감지하는 방법을 제안했다 [R34]. 구체적 정의·검증 사건은 초록에서 확인하지 못했다 (확인 필요).
- 판단: 방향 히스토그램 엔트로피는 광학 흐름으로 바로 계산할 수 있다. 다만 고밀도 정체 상태에서는 속도가 작아 방향이 잡음에 지배된다 (가정). 크기 가중이 필요하다.

### 2.6 정지·진행파 지표

- 원 연구에서 정지·진행파는 평균 유량이 0.8명/(m·s) 아래로 떨어질 때 시작됐다 [R1]. 이 값도 R에 따라 달라진다고 명시됐다 [R2].
- 사고는 유량이 기준 아래로 떨어진 지 30분 넘게 지나서 일어났다 [R1]. 정지·진행파는 난류보다 이른 경고다.
- 원 저자들은 "늦어도 정지·진행파가 시작되면 대응해야 한다"고 썼다 [R2].
- 측정 후보 (가정):
    - 셀 평균 속도의 진행 방향 성분 `V_par(t)`의 시간 신호에서, 일정 주기 대역의 진동 세기(스펙트럼 에너지)를 잰다.
    - 인접 셀 사이 상관을 보면 상류 전파 여부를 확인할 수 있다.
- 주기·전파 속도의 일반값은 원 논문에 없다 [R1]. 마라톤 대기 군중의 속도 파동 전파 속도는 1m/s 남짓으로 보도됐다 [R18].

### 2.7 집단 진동 스펙트럼 (Gu 외 2025)

- **방법** [R4]
    - PIV로 속도장을 구한다. 창 크기 약 1.5m, 시간 간격 약 0.5초, 속도 오차 0.05~0.1m/s다.
    - 속도장에서 운동에너지 스펙트럼을 구하고, 3분 창을 1초씩 옮기며 시간-주파수 분석을 한다.
    - 임계 밀도 위에서 스펙트럼 최고점이 ω0 = 0.35±0.05 rad/s(주기 약 18초)에 나타난다.
- **장점**: 저자들은 이 방법이 원본 영상에서 바로 계산되고, 고급 검출·추적이 필요 없다고 밝혔다 [R4]. 변위가 한 사람 크기보다 작을 때도 전이를 감지할 수 있다고 보고했다 [R4].
- **한계**
    - 3분 창이 필요해 반응이 느리다. 1Hz 경보에는 맞지 않는다 (가정).
    - 팜플로나는 사방이 막힌 광장(약 50m×20m)이다. 골목·통로처럼 한 방향 흐름이 강한 곳에서도 같은 진동이 생기는지는 확인되지 않았다 (확인 필요).
    - 진동은 위험 상태의 "전조"이지 사고 그 자체가 아니다.

### 2.8 라그랑주 지표 (FTLE·LCS)

- **FTLE(유한시간 랴푸노프 지수)**: 속도장 위에 입자를 뿌려 일정 시간 흘려 보낸 뒤, 이웃 입자가 얼마나 빨리 멀어지는지 잰 값이다.
- **LCS(라그랑주 응집 구조)**: FTLE 값이 높은 능선이다. 서로 다른 흐름 영역의 경계가 된다.
- Ali, Shah 2007은 FTLE로 군중 흐름을 나누고, 영역 수가 시간에 따라 바뀌면 "불안정"으로 봤다 [R25]. 실험 영상은 인터넷 영상과 다큐멘터리였다 [R25].
- 판단: 안정성 분석이 "흐름 영역 개수 변화"라서 우리의 셀 단위 경보와 맞추기 어렵다. 입자 이류 계산도 추가로 든다. MVP에는 맞지 않는다 (가정).

### 2.9 사회적 힘 추정·기타

- **사회적 힘 모델(social force model)**: 사람을 목적지로 끄는 힘과 서로 밀어내는 힘의 합으로 움직임을 설명하는 모델이다.
- Mehran 외 2009는 광학 흐름 위 입자 이류로 상호작용 힘을 추정해 이상 행동을 감지했다 [R26]. 후속으로 유선(streakline) 표현을 제안했다 [R27].
- Krausz, Bauckhage는 고밀도 시점에서는 가림 때문에 입자 이류가 맞지 않는다고 판단했다 [R6].
- **모드 분석**: Bottinelli 외는 고밀도 군중을 입상 물질처럼 보고 진동 모드로 위험 구조를 분석했다 [R17]. 개인 위치가 필요하다.
- **무차원 수**: Cordes 외는 침입수·회피수라는 무차원 수로 군중 구조의 영역을 나눴다 [R33]. 개인 위치·속도가 필요하다. 정의식은 확인하지 못했다 (확인 필요).

### 2.10 지표 비교

| 지표 | 식 (요약) | 입력 | 민감도·약점 | 근거 수준 |
|---|---|---|---|---|
| 군중 압력 | `rho × Var(V)` | 밀도, 속도장 | R·분산 정의·잡음에 민감 | 실제 사고 1건(메카)에서 시간·위치 일치 [R1][R2] |
| 속도 분산 | `Var(V)` | 속도장 | 저밀도 엇갈림에 반응 | 고밀도에서 밀도와 선형 증가 [R4] |
| 와도·발산 | `∂v_y/∂x − ∂v_x/∂y` 등 | 속도장 | 질서 있는 회전도 반응, 미분이라 잡음 증폭 | 메카 자료에서 압력보다 약함 [R2] |
| 혼잡도·위험도 | `CL = (ω_max − ω_min)/|v|`, `CD = CL × rho` | 0.2m 속도장, 밀도 | 저속에서 분모가 작아 불안정 (가정), 단위 해석 어려움 [R15] | 통제 실험 [R13][R14], 경고 기준 미확정 |
| 혼잡수 | `CN ≈ CL × R / 6` | 위와 같음 | 수치 방법에 따라 1 초과 가능 [R15] | 이론·시뮬레이션·교차 실험 [R15][R16] |
| 정지·진행파 | 진행 방향 속도의 진동 에너지 | 셀 평균 속도 시계열 | 창 길이 필요 | 메카에서 사고 30분 이상 전 출현 [R1] |
| 진동 스펙트럼 | `ω0(t)` 추적 | 속도장 (PIV) | 3분 창, 장소 형태 의존 가능 | 축제 4회 + 러브 퍼레이드 영상 [R4] |
| FTLE·LCS | 흐름 사상 변형 텐서 최대 고유값 | 속도장 시계열 | 계산량, 셀 경보와 연결 어려움 | 정성 사례 [R25] |
| 흐름 히스토그램 대칭 | 방향·크기 히스토그램과 좌우 반전의 차 | 셀 광학 흐름 | 정면 시점용, 정성 평가 | 러브 퍼레이드 영상 [R6] |

---

## 3. 영상 기반 감지 방법

### 3.1 고전 방법

**Krausz, Bauckhage 2011 (러브 퍼레이드)** [R6]

- Farneback 광학 흐름을 셀별로 계산한다. 원근을 반영해 먼 쪽 셀을 작게 잡는다.
- 셀마다 흐름의 방향·크기 2차원 히스토그램(36×100구간)을 만든다.
- **정체 감지**
    - 위에서 본 시점: 히스토그램 크기 중심값이 작으면 정체로 본다.
    - 정면 시점: 정체 때 사람들이 균형을 잡으려 좌우로 흔들려 히스토그램이 좌우 대칭이 된다. 대칭 정도를 특징으로 쓴다.
    - 비모수 CUSUM 변화점 감지로 경보를 낸다. 과거 90개 관측(15분)으로 기준 분포를 잡았다.
    - 경보 10건 중 7건이 영상 속 이상 상황과 맞았다. 다만 상당수는 구급차·경찰차 통과였다.
- **충격파 감지**
    - 셀 평균 흐름 크기의 급증 비율 `a_c = μ_t,c / μ_prev,c`를 구한다.
    - 방향 표준편차 `σ_dir,c`로 나눈 `p_c = a_c / σ_dir,c`가 프레임 평균보다 2.5σ 이상 크면 충격파 영역으로 본다.
    - 정량 평가는 없고 그림으로만 제시했다.
- 시사점: 우리와 같은 Farneback 기반이고, 개인을 추적하지 않아 사생활 측면에서 우리 원칙과 맞는다. 다만 정량 검증이 약하다.

**Perko 외 2013 (항공 영상)** [R29]

- 군중 압력 식을 인용하고 TV-L1 광학 흐름과 회귀 기반 밀도로 계산할 수 있다고 썼다. 압력 결과는 보고하지 않았다.
- 실무 팁: 인접 프레임이 아니라 10프레임 떨어진 프레임 사이 흐름을 구하고, 여러 흐름을 시간 평균했다. 작은 움직임을 잡음보다 크게 만들기 위해서다.

**Gu 외 2025 (팜플로나)** [R4]

- 현재 계획과 가장 가까운 최신 사례다. 처리 사슬을 아래에 적는다.

```
밀도     P2PNet 머리 검출 (ShanghaiTech + 수작업 주석으로 학습) → 가우시안 평활 밀도장
기하     평면 호모그래피 + 머리 높이 보정 (관측 높이 16±1m, 보행자 키 1.73m)
가림     깃발·풍선을 YOLOv8로 찾아 가림
속도     PIV, 창 약 1.5m, 시간 간격 약 0.5초, 오차 0.05~0.1m/s
분석     운동에너지 스펙트럼, 3분 창 시간-주파수 분석
```

### 3.2 학습 기반 방법

| 연구 | 대상 | 방법 | 데이터·평가 | 코드 |
|---|---|---|---|---|
| Alia 외 2022 [R22] | 입구 밀기 감지 | RAFT 흐름 → 휠 시각화 → EfficientNet-B0 분류 | Jülich 실험 영상 | 공개, BSD-3-Clause (`DL4PuDe`) |
| Alia 외 2023 [R23] | 실시간 밀기 조기 감지 | EfficientNetV2B0 + 사전학습 흐름 | 정확도 87% (저자 보고) | (확인 필요) |
| Alia 외 2024 [R24] | 사람 단위 밀기 감지 | 보로노이 영역 + EfficientNetV1B0 + 시그모이드 | 실제 실험 6건으로 만든 라벨 데이터 | (확인 필요) |
| Bhola 외 2026 [R28] | 혼잡·위험 4단계 분류 | Farneback + CNN-LSTM | UCSD 등 1만 프레임 수작업 라벨, UMN 교차 시험 10개 시퀀스 | 없음 (요청 시 데이터 제공) |
| He 외 2025 [R30] | 극고밀도 군중 분석·예측 | 연속체 능동 입자 물리 + 신경 확률미분방정식 | 저화질 실제 영상 (데이터 이름 확인 필요) | (확인 필요) |
| AlGhamdi 외 2025 [R31] | 고밀도 이상 움직임 | 머리 검출 + 조밀 흐름 → 개인 속도 4분류 + 백분위 점수 | 정량 결과 미기재(초록) | 없음 (확인 필요) |

- **밀기(pushing)**: 앞사람과의 공간을 차지하려고 몸으로 미는 행동이다. 난류의 원인 중 하나로 거론되지만 난류와 같은 것은 아니다 [R9].
- 학습 기반 연구의 공통 한계는 다음과 같다.
    - 라벨이 "밀기"나 "위험 등급(사람이 정함)"이다. 실제 난류 정답이 아니다.
    - Bhola 외는 검증 정확도 99%대를 보고했지만, 교차 데이터셋에서는 이상 5개 중 4개, 정상 5개 중 3개만 맞혔다 [R28]. 장면이 바뀌면 성능이 크게 떨어질 수 있다는 예다.
    - 개인 단위 방법([R24][R31])은 개인 위치·속도를 다룬다. 우리 저장 원칙(개인 궤적 비저장)과 충돌할 수 있다. 메모리 안 일시 계산만 허용할지 `[토론]`이다.
- 최근 리뷰도 고밀도에서는 접촉력·물리적 상호작용이 지배적이라 새 실험과 모델이 필요하다고 정리했다 [R32].
- 판단: 11-19 동결까지 학습 모델을 새로 만들 시간과 라벨이 없다. 7.2.4의 "딥러닝은 데이터 확보 후" 판단은 유지한다.

### 3.3 공개 코드 요약

| 이름 | 용도 | 라이선스 |
|---|---|---|
| OpenCV `calcOpticalFlowFarneback`, `DISOpticalFlow` | 조밀 광학 흐름 [R37][R38] | Apache 2.0 (OpenCV 4.5 이후) (확인 필요) |
| RAFT | 학습 기반 광학 흐름 [R39] | (확인 필요) |
| `DL4PuDe` | 밀기 감지 [R22] | BSD-3-Clause |
| Gu 외 `codes_theory.zip` | 진동 이론 시뮬레이션 [R5] | CC BY 4.0 (Zenodo 기록) |

---

## 4. 데이터셋과 시뮬레이션

### 4.1 실제·실험 데이터

| 데이터 | 내용 | 밀도 | 정답 | 접근·라이선스 | 활용 |
|---|---|---|---|---|---|
| Gu 외 Zenodo [R5] | 2023년 밀집 영상 1개(51.3MB), 밀도·속도 지도, 스펙트럼 자료, 시뮬레이션 코드 (전체 1.2GB) | 평균 약 6명/㎡ [R4] | 논문의 스펙트럼·밀도 값 | CC BY 4.0 | 실제 고밀도 영상에서 우리 사슬 재현 |
| Jülich `crowdqueue` (2018) [R20][R21] | 입구 실험 24회, 490명, 머리 위 시점 영상(1.1GB), 25fps 궤적 | 일부 > 10명/㎡ [R20] | 개인 궤적 | CC BY 4.0 (위키 기준, 데이터 개별 조건 확인 필요) | 광학 흐름 속도 대 궤적 속도 비교 |
| Jülich `effect_on_pushing` (2022) [R21] | 위 14회에 1초 단위 밀기 4단계 라벨, 이웃 정보 | 위와 같음 | 사람별 밀기 라벨 | CC BY 4.0 (위키 기준) | 불안정 지표의 약한 정답 |
| Jülich BaSiGo 등 (2013) [R21] | 통로·교차·입구 실험 궤적·영상 | (확인 필요) | 개인 궤적 | CC BY 4.0 (위키 기준) | 양방향·교차 흐름 시험 |
| Liang 외 Zenodo·Dryad [R10] | 이태원 현장 자료·시뮬레이션 결과 | 시뮬레이션 | 시뮬레이션 값 | (확인 필요) | 지표 비교용 참고 |
| TUB CrowdFlow [R36] | 합성 군중 영상 + 정답 광학 흐름 | (확인 필요) | 정답 흐름 | (확인 필요) | 흐름 오차(EPE) 측정 |
| 러브 퍼레이드 공개 영상 [R4][R6] | 공개 감시 영상 | 8±1명/㎡ (1장면) [R4] | 없음 | 저작권·윤리 검토 필요 `[토론]` | 정성 확인 |
| UMN·UCSD | 이상 행동 벤치마크 | 저·중밀도 (가정) | 이상/정상 | (확인 필요) | 난류 검증에는 부적합 |

- **결론**: "난류"라는 정답 라벨이 있는 공개 데이터셋은 찾지 못했다. 실제 사고 영상은 수가 적고, 사용 조건과 윤리 문제가 있다.
- Jülich 자료실은 데이터를 쓸 때 출처를 밝히라고 요구한다 [R21].

### 4.2 시뮬레이션

| 도구 | 언어·설치 | 모델 | 라이선스 | 비고 |
|---|---|---|---|---|
| PySocialForce [R42] | Python, `pip install pysocialforce` | 확장 사회적 힘 모델 | MIT | 가장 가볍다. 접촉력은 없다 (확인 필요) |
| JuPedSim [R40] | C++ + Python 바인딩, `pip install jupedsim` | Collision Free Speed Model, Generalized Centrifugal Force Model 등 | LGPLv3 | Jülich 개발. 출력 형식 확인 필요 |
| Vadere [R41] | (확인 필요) | 미시 보행 시뮬레이션 | GPLv3 | |
| Yu, Johansson 2007 [R3] | 논문 모델 | 사회적 힘 모델의 반발항을 고밀도용으로 확장 | – | 층류 → 정지·진행 → 난류 전이, 속도 증분 분포·구조 함수 재현 |

- **중요**: 일반 사회적 힘 모델은 고밀도 국소 상호작용을 충분히 표현하지 못해 난류를 잘 재현하지 못한다 [R3]. Yu, Johansson은 반발항을 바꿔 재현했다 [R3]. 원 저자들도 "유입만 늘려서 두 전이를 모두 재현하는 것은 아직 풀리지 않은 과제"라고 썼다 [R1].
- 따라서 기성 시뮬레이터로 "진짜 난류" 정답을 만들기는 어렵다. 시뮬레이션은 다음 용도로 제한한다 (가정).
    - 지표 계산 코드가 맞는지 확인하는 단위 시험 (알려진 속도장 → 알려진 분산).
    - 인위적 흔들림(밀기 충격, 정지·진행 주기)을 넣었을 때 지표가 반응하는지 보는 민감도 시험.
- 영상 렌더링까지 하려면 시간이 크게 든다. 11-19 이전에는 궤적 → 속도장 → 지표 경로만 시험한다 (가정).

---

## 5. 측정 실무 문제

### 5.1 고밀도 군중의 광학 흐름

- **조리개 문제(aperture problem)**: 작은 창 안에서는 무늬가 한 방향으로만 보이면 그 방향과 수직인 움직임만 잴 수 있는 문제다. 비슷한 머리·어깨가 빽빽이 반복되는 고밀도 장면에서 커진다 (가정).
- **반복 무늬와 가림**: 사람이 겹쳐 보이는 비스듬한 시점에서는 개인 추적과 입자 이류가 맞지 않는다 [R6].
- **신체 내부 움직임**: 팔·머리 흔들림, 걸음의 좌우 흔들림이 흐름에 들어간다. 정체 때 좌우 흔들림이 커진다는 관찰이 있다 [R6]. 이는 분산을 키우는 "신호 아닌 신호"일 수 있다.
- **작은 이동량**: 정체 상태에서는 프레임 간 이동이 1px 미만일 수 있다. 프레임 간격을 늘리거나(10프레임 간격 사례 [R29]) 시간 평균을 쓴다.
- **방법 선택**: TUB CrowdFlow 결과에서 정밀한 방법이 군중 움직임을 더 잘 잡지 못했다 [R36]. Farneback은 이 벤치마크에 없다 (= `proposal-detail.md` 7.2.3). E4에서 DIS와 비교하는 계획은 유지한다.

### 5.2 px/프레임 → m/s 변환

- 현재 계획: `v = (H·(p + f) − H·p) / Δt`, H는 바닥 호모그래피다.
- **문제**: 흐름이 잡히는 곳은 머리·어깨(약 1.6m 높이)다. 바닥 호모그래피로 변환하면 위치뿐 아니라 속도 크기도 틀린다. 카메라에서 먼 쪽으로 갈수록 오차가 커진다 (가정).
- Gu 외는 관측 높이 16m, 보행자 키 1.73m로 머리 높이 보정을 했다 [R4]. 우리도 속도 변환에는 머리 높이 평면 호모그래피를 쓰는 것이 맞다 (가정). 이미 `proposal-detail.md` 3.4(1)에 "오차가 크면 머리 높이 평면용 호모그래피로 보정"이 있다. 흐름에는 처음부터 적용하자고 제안한다 `[토론]`.
- 분산은 속도의 제곱이므로, 속도 척도 오차 k배는 분산·압력을 k²배로 바꾼다. 척도 10% 오차 → 압력 약 21% 오차다 (계산).

### 5.3 셀 크기·평균 창

| 선택 | 원 연구·문헌 | 현재 계획 | 영향 |
|---|---|---|---|
| 공간 척도 | R = 1m 가우시안 [R1], PIV 창 1.5m [R4], 격자 0.2m [R14] | 2m×2m 셀 | 셀이 크면 공간 분산에 큰 흐름 구조(예: 셀 안 두 방향 흐름)가 섞인다. 시간 분산은 셀 평균이라 흔들림이 줄어든다 |
| 시간 척도 | 45분 평균과의 차이 [R1], 2.5초 표본 [R14], 3분 창 [R4] | Δt = 0.2초 흐름, 1Hz 판정, EMA 밀도 | 분산 창이 너무 짧으면 잡음, 너무 길면 지연 |
| 프레임률 | 8fps [R1], 25/30fps [R4] | 미정 (Δt = 0.2초는 5fps 상당) | 0.2초 간격은 문헌 범위 안이다 |

- 원 저자들이 직접 "임계값은 R에 따라 달라진다"고 썼다 [R1][R2]. 셀 크기를 바꾸면 기준값도 다시 정해야 한다.

### 5.4 잡음 바닥 (noise floor)

- **잡음 바닥**: 실제 움직임이 없어도 측정 잡음 때문에 생기는 지표의 최소값이다.
- 계산 예시 (가정):
    - 성분별 속도 잡음 표준편차 σ = 0.1m/s라면, 잡음만으로 `|v − V|²`의 기대값이 2σ² = 0.02 m²/s²가 된다.
    - 밀도 5명/㎡을 곱하면 P = 0.1/s²다. 기준 0.02/s²의 5배다.
    - σ = 0.05m/s여도 P = 0.025/s²로 기준을 넘는다.
    - 참고로 Gu 외의 PIV 오차가 0.05~0.1m/s였다 [R4]. Farneback의 실제 잡음은 E4에서 재야 한다.
- 시사점: 잡음을 빼지 않으면 "밀도가 높다"는 것만으로 압력 기준을 넘는다. 이 경우 불안정 지표가 밀도 등급과 같은 정보를 반복하게 된다.
- 대응 (가정):
    - 정지 장면·저속 장면에서 셀별 잡음 분산 `Var_noise_c`를 잰다.
    - `Var_eff = max(Var_c − Var_noise_c, 0)`을 쓴다.
    - 셀 평균을 먼저 하고 그 시간 분산을 쓰면, 픽셀 수 N에 따라 독립 잡음이 약 1/N로 준다. 다만 이웃 픽셀 흐름은 서로 상관이 있어 실제 감소는 더 작다.
- 위치 오차가 압사 위험 판정 확률을 크게 바꾸고 칼만 필터로도 완전히 없애지 못한다는 시뮬레이션 연구도 있다 [R35].

### 5.5 카메라 각도

- 머리 위 시점(실험 자료 [R20])은 가림이 적어 흐름·밀도가 정확하다.
- 비스듬한 CCTV 시점은 원근으로 먼 셀의 픽셀 수가 적어 잡음이 커진다. Krausz 외는 먼 셀을 작게 잡았다 [R6].
- 정면에 가까운 시점에서는 다가오는 움직임이 크기 변화로만 보여 속도 추정이 어렵다 [R6].
- 시사점: 셀마다 신뢰도(보행 가능 면적의 픽셀 수, 머리 점 수)를 함께 저장하고, 신뢰도가 낮은 셀은 지표를 판정에서 뺀다 (가정).

### 5.6 정답 없이 검증하는 방법

| 방법 | 내용 | 확인할 수 있는 것 | 한계 |
|---|---|---|---|
| 합성 속도장 단위 시험 | 알려진 평균·분산의 속도장을 넣는다 | 계산 코드 정확성 | 영상 단계 오차는 못 본다 |
| 궤적 정답 비교 | Jülich 영상에서 흐름으로 구한 셀 속도·분산 vs 궤적으로 구한 값 [R21] | 광학 흐름 → m/s → 분산 사슬의 오차 | 머리 위 시점이라 CCTV보다 쉽다 |
| 약한 라벨 비교 | 밀기 라벨이 많은 셀·시간에 지표가 높은가 [R21] | 지표의 방향성(순위 상관, AUC) | 밀기 ≠ 난류 |
| 실제 고밀도 재현 | 팜플로나 영상에서 논문 값(밀도, ω0)을 재현 [R4][R5] | 실제 고밀도에서 사슬이 도는가 | 짧은 영상 1개 |
| 민감도 분석 | 셀 크기·창 길이·흐름 방법·Δt를 바꿔 지표 분포 변화를 본다 | 기준값이 얼마나 흔들리는가 | 정답은 아니다 |
| 잡음 주입 | 흐름에 알려진 잡음을 더해 지표 상승을 잰다 | 잡음 바닥 모델 확인 | – |
| 전문가 판정 | 빨리 감기 영상에 지표를 겹쳐 사람이 본다 [R2] | 설명 가능성 | 주관적, 시간 소요 `[토론]` |

---

## 6. 현재 계획 평가와 제안

### 6.1 유지할 것

- **규칙 기반 지표**: 라벨이 없고 경보 근거를 설명해야 한다는 판단은 문헌과 맞는다. 학습 연구도 라벨 부족과 교차 장면 성능 저하를 보였다 [R28].
- **추적 없는 광학 흐름**: 고밀도 시점에서 추적이 어렵고 사생활 측면에서 유리하다는 근거가 있다 [R4][R6]. 개인 궤적 비저장 원칙과 맞다.
- **P2PNet + 호모그래피 밀도**: 같은 조합(P2PNet [R43])이 2025년 Nature 연구에서 고밀도 측정에 쓰였다 [R4].
- **Farneback 시작, DIS 비교 (E4)**: 교체 비용이 작다.
- **군중 압력 개념 자체**: 실제 사고 1건에서 위치·시간을 짚은 유일한 정량 지표다 [R1][R2].

### 6.2 바꿀 것 (제안)

| 번호 | 현재 | 제안 | 이유 |
|---|---|---|---|
| C1 | `Var_c(v) = mean(|v − V_c|²)` 셀 내부 순간 공간 분산 | 셀 평균 속도 `V_c(t)`의 시간 분산 `Var_t(V_c) = <|V_c(t) − U_c(t)|²>`, `U_c`는 최근 T초 이동 평균 (가정: T = 30초) `[토론]` | 원 정의 [R1]에 가깝다. 셀 안 신체 움직임·두 방향 흐름 혼입을 줄인다 |
| C2 | 잡음 처리 없음 | `Var_eff = max(Var − Var_noise_c, 0)` (가정) | 잡음만으로 기준 초과 가능 (5.4) |
| C3 | 바닥 호모그래피로 속도 변환 | 머리 높이 평면 호모그래피 `[토론]` | 흐름은 머리·어깨 높이에서 잡힌다 [R4] |
| C4 | θ_P = 0.02/s² 시작값 → ROC로 조정 | 0.02/s²는 "문헌 참고선"으로만 표시. 경보 기준은 장면 기준선 대비 상대값(예: 정상 시간대 분포의 상위 백분위) (가정) `[토론]` | 원 저자가 보정 필요라고 명시 [R2]. 양성 라벨이 없어 ROC 불가 |
| C5 | E5 "재현율 0.8 이상이 되는 값" | E5를 (1) 궤적 대비 오차, (2) 밀기 라벨 AUC, (3) 민감도 표, (4) 잡음 바닥 표로 바꾼다 `[토론]` | 난류 양성 클립이 없어 재현율을 잴 수 없다 |
| C6 | 명칭 "군중난류 지표" | "흐름 불안정 지표"로 부르고, 난류 감지라고 주장하지 않는다 `[토론]` | 검증 자료가 난류 정답이 아니다. 설명 책임 |
| C7 | 와도를 보조 지표로 | 와도 대신 역방향 흐름 비율·정지·진행파 지표를 우선 (가정) | 와도는 미분이라 잡음에 약하고 단독 기준이 없다 [R2][R14] |

- C1에서 T를 길게 잡으면 정지·진행파 흔들림도 분산에 들어간다. 원 연구의 45분 평균도 그런 성격이다 [R1]. T를 몇 개로 바꿔 보는 것이 민감도 분석의 핵심이다.
- C4의 상대 기준은 "평소와 다르다"를 뜻할 뿐 "위험하다"를 뜻하지 않는다. 등급 판정은 밀도 기준이 주가 되고, 불안정 지표는 "심각" 승격의 보조 조건으로 두는 현재 구조(`proposal.md` 3.2)가 맞다.

### 6.3 더할 것 (제안)

- **A1 정지·진행파 지표** (가정): 셀 평균 진행 방향 속도의 주기 성분 세기. 원 연구에서 사고 30분 이상 전에 나타난 경고였다 [R1]. 1Hz 셀 평균 시계열만 있으면 된다. 공수가 작다.
- **A2 신뢰도 마스크** (가정): 셀별 픽셀 수·머리 점 수·흐름 잔차로 신뢰도를 매기고, 낮으면 지표를 비운다.
- **A3 집단 진동 스펙트럼** (여유 시): 3분 창 운동에너지 스펙트럼 최고점 [R4]. 경보가 아니라 상황판 보조 그래프로만 쓴다. G2 통과 후 검토한다.
- **A4 혼잡수(CN)** (여유 시): 속도장 해상도가 충분한 근거리 카메라에서만 시험한다 [R15][R16].

### 6.4 후보 지표 세트 (MVP) `[토론]`

```
입력       셀 c, 1Hz
           rho*_c(t)         EMA 밀도                              ← counting 모듈 (기존)
           V_c(t)            셀 평균 지면 속도 [m/s]                ← 머리 높이 H, 머리 주변 픽셀 (C3)
기준선     U_c(t)            V_c의 최근 T초 이동 평균 (T = 30초, 가정)
불안정     S_c(t) = max( <|V_c − U_c|²>_T − Var_noise_c , 0 )      [m²/s²]   (C1, C2)
압력       P_c(t) = rho*_c(t) × S_c(t)                              [1/s²]
참고선     0.02 /s²                                                 ← [R1], 표시만 (C4)
경보 기준  θ_c = 정상 구간 P_c 분포의 상위 q 백분위 (q는 E5로 정함, 가정)
정지·진행  W_c(t) = 진행 방향 V_c 성분의 대역 에너지 (대역은 E5로 정함, 가정)
역방향     B_c(t) = 셀 주 흐름과 반대 방향 픽셀 비율                ← 기존 보조 지표
신뢰도     Q_c(t) = 유효 픽셀 수, 머리 점 수
```

- `timeline.json`에는 셀·구역 집계값(`P_c`, `S_c`, `W_c`, `B_c`, `Q_c`)만 넣는다. 원본 영상·머리 좌표·개인 궤적은 저장하지 않는다.
- 판정 규칙의 "3초 이상 초과 → 감지, 10초 유지"는 그대로 쓸 수 있다. 다만 `S_c` 자체가 T초 창이라 지연이 생긴다.

### 6.5 검증 계획 후보 `[토론]`

| 순서 | 실험 | 자료 | 산출물 | 예상 공수 (가정) |
|---|---|---|---|---|
| V1 | 합성 속도장 단위 시험 | 코드로 생성 | `S_c`·`P_c` 계산 정확성 테스트 | 0.5인일 |
| V2 | 잡음 바닥 측정 | 우리 시연 영상의 정지·저속 구간 | 셀별 `Var_noise_c` 표 | 0.5인일 |
| V3 | 궤적 정답 비교 | Jülich `crowdqueue` 일부 회차 [R21] | 셀 속도 오차(m/s), 분산 상관 | 1~1.5인일 |
| V4 | 밀기 라벨 비교 | Jülich `effect_on_pushing` [R21] | 셀·초 단위 지표 vs 밀기 비율 AUC | 1인일 |
| V5 | 민감도 분석 | V3·V4 자료 + 시연 영상 | 셀 크기(1·2m)·T(10·30·60초)·흐름 방법별 지표 분포 표 | 0.5~1인일 |
| V6 | 실제 고밀도 재현 (여유 시) | 팜플로나 영상 [R5] | 밀도·스펙트럼 최고점이 논문 값 근처인지 | 1인일 |

- 합계 약 4.5~6인일이다 (가정). 흐름 모듈 AI 공수와 비교해 범위를 정해야 한다. V1·V2·V5는 필수, V3·V4는 둘 중 하나 이상, V6은 여유 시로 제안한다 `[토론]`.
- Jülich 자료는 머리 위 시점이라 CCTV보다 쉬운 조건이다. 결과를 발표할 때 이 차이를 밝힌다.

### 6.6 실현 가능성 (11-19 동결 기준)

| 항목 | 판단 | 근거 |
|---|---|---|
| C1·C2·C4 (정의 변경, 잡음 빼기, 상대 기준) | 가능 | 셀 평균 시계열 위 계산이다. 추가 모델 없음 |
| C3 (머리 높이 호모그래피) | 가능 | counting 모듈과 같은 H 보정을 공유한다. 담당자와 상의 필요 |
| A1 (정지·진행파) | 가능 | 1Hz 시계열 FFT 또는 대역 필터 |
| V1·V2·V5 | 가능 | 자료가 이미 있거나 생성 가능 |
| V3·V4 | 빠듯함 | 자료 내려받기(영상 1.1GB)와 좌표계 맞추기 시간이 든다 |
| A3·A4·V6 | 동결 전 어려움 | 여유 시 |
| 학습 기반 감지 | 불가 | 라벨·시간 부족 |

---

## 7. 남은 질문

- `[토론]` 지표 이름을 "군중난류"에서 "흐름 불안정"으로 바꿀지. 기획서 표현과 발표 메시지에 영향이 있다.
- `[토론]` 시간 분산 창 T의 시작값(10·30·60초)과, 등급 판정 지연을 얼마까지 허용할지.
- `[토론]` 경보 기준을 상대 기준(장면 백분위)으로 할지, 0.02/s²를 그대로 시작값으로 둘지.
- `[토론]` 머리 높이 호모그래피를 counting 모듈과 공유할지. 담당자(이유노)와 상의가 필요하다.
- `[토론]` 개인 단위 계산(머리 점 주변 흐름, 사람별 속도)을 메모리 안에서만 일시적으로 허용할지. 저장 원칙과의 경계를 정해야 한다.
- `[토론]` 러브 퍼레이드 등 사고 영상을 검증·발표에 쓸지. 저작권과 피해자 존중 문제가 있다.
- (확인 필요) 0.02/s²를 다른 장소에서 독립 검증한 연구가 있는지.
- (확인 필요) TUB CrowdFlow, Liang 외 데이터, OpenCV·RAFT의 정확한 라이선스.
- (확인 필요) Jülich 개별 데이터셋에 위키와 다른 이용 조건이 있는지.
- (확인 필요) 집단 진동(약 18초 주기)이 골목·통로처럼 한 방향 흐름이 강한 곳에서도 나타나는지.
- (확인 필요) Farneback의 실제 속도 잡음 크기. E4·V2에서 잰다.

---

## 출처

**군중 동역학·사고 분석**

- [R1] (= references.md [1]) Helbing, D., Johansson, A., Al-Abideen, H. Z. (2007). The Dynamics of Crowd Disasters: An Empirical Study. *Physical Review E*, 75, 046109. <https://arxiv.org/abs/physics/0701203>
- [R2] Johansson, A., Helbing, D., Al-Abideen, H. Z., Al-Bosta, S. (2008). From Crowd Dynamics to Crowd Safety: A Video-Based Analysis. *Advances in Complex Systems*, 11(4), 497–527. <https://arxiv.org/abs/0810.4590>
- [R3] Yu, W., Johansson, A. (2007). Modeling Crowd Turbulence by Many-Particle Simulations. *Physical Review E*, 76, 046105. <https://arxiv.org/abs/0708.3282>
- [R4] Gu, F., Guiselin, B., Bain, N., Zuriguel, I., Bartolo, D. (2025). Emergence of collective oscillations in massive human crowds. *Nature*, 638, 112–119. DOI 10.1038/s41586-024-08514-6. <https://pmc.ncbi.nlm.nih.gov/articles/PMC11798876>
- [R5] Gu, F. 외 (2025). Emergence of collective oscillations in massive human crowds. Video, figures data and simulations code (Zenodo 14050598, CC BY 4.0). <https://zenodo.org/records/14050598>
- [R6] Krausz, B., Bauckhage, C. (2011). Automatic Detection of Dangerous Motion Behavior in Human Crowds. Fraunhofer IAIS (게재 학회 확인 필요). <https://publica-rest.fraunhofer.de/server/api/core/bitstreams/d30a33ba-a7a9-4918-adb2-18fb1a0e5e47/content>
- [R7] (= references.md [2]) Krausz, B., Bauckhage, C. (2012). Loveparade 2010: Automatic video analysis of a crowd disaster. *Computer Vision and Image Understanding*, 116(3), 307–319. <https://www.sciencedirect.com/science/article/abs/pii/S1077314211002037>
- [R8] Helbing, D., Mukerji, P. (2012). Crowd Disasters as Systemic Failures: Analysis of the Love Parade Disaster. arXiv:1206.5856 (학술지 게재 정보 확인 필요). <https://arxiv.org/abs/1206.5856>
- [R9] Sieben, A., Seyfried, A. (2023). Inside a life-threatening crowd: Analysis of the Love Parade disaster from the perspective of eyewitnesses. *Safety Science*, 106229. <https://arxiv.org/abs/2303.03977>
- [R10] Liang, Lee, Sun, Wong (2024) (이름 전체 확인 필요). Unraveling the causes of the Seoul Halloween crowd-crush disaster. *PLOS ONE*. DOI 10.1371/journal.pone.0306764. <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11244771/> (자료: <https://datadryad.org/dataset/doi:10.5061/dryad.kprr4xhb9>)
- [R11] 이화여대 그래픽스 연구실 (2025). Virtual Reenactment of the Itaewon Crowd Crush Using Kinodynamic Simulation. *Computer Animation and Virtual Worlds* (저자 목록 확인 필요). <https://graphics.ewha.ac.kr/Crowd/>
- [R12] (= references.md [31]) 뉴시스 (2023-01-13). 특수본 "이태원 참사 원인, 군중 유체화…기관 대처 미흡". <https://www.newsis.com/view/NISX20230113_0002158128>

**지표**

- [R13] (= references.md [3]) Feliciani, C., Nishinari, K. (2018). Measurement of congestion and intrinsic risk in pedestrian crowds. *Transportation Research Part C*, 91, 124–155.
- [R14] Feliciani, C., Nishinari, K. (2018). Investigation of pedestrian evacuation scenarios through congestion level and crowd danger. *PED2018 Proceedings*, Collective Dynamics. <https://collective-dynamics.eu/index.php/cod/article/view/A45>
- [R15] Zanlungo, F., Feliciani, C., Yücel, Z., Nishinari, K., Kanda, T. (2020). Some considerations on crowd Congestion Level. arXiv:2004.01883. <https://arxiv.org/abs/2004.01883>
- [R16] Zanlungo, F., Feliciani, C., Yücel, Z., Jia, X., Nishinari, K., Kanda, T. (2023). A pure number to assess "congestion" in pedestrian crowds. *Transportation Research Part C*, 148, 104041. DOI 10.1016/j.trc.2023.104041.
- [R17] Bottinelli, A., Sumpter, D. T. J., Silverberg, J. L. (2016). Emergent Structural Mechanisms for High-Density Collective Motion Inspired by Human Crowds. *Physical Review Letters*, 117, 228301. <https://arxiv.org/abs/1606.08835>
- [R18] Bain, N., Bartolo, D. (2019). Dynamic response and hydrodynamics of polarized crowds. *Science*. DOI 10.1126/science.aat9891. CNRS 보도자료: <https://www.cnrs.fr/en/press/model-describing-hydrodynamics-crowds>
- [R19] Garcimartín, A., Pastor, J. M., Martín-Gómez, C., Parisi, D., Zuriguel, I. (2017). Pedestrian collective motion in competitive room evacuation. *Scientific Reports*, 7, 10792. <https://pmc.ncbi.nlm.nih.gov/articles/PMC5589747>
- [R33] Cordes, J., Schadschneider, A., Nicolas, A. (2023/2024). Dimensionless Numbers Reveal Distinct Regimes in the Structure and Dynamics of Pedestrian Crowds. arXiv:2307.12786 (*PNAS Nexus* 게재 예정으로 표기). <https://arxiv.org/abs/2307.12786>
- [R34] Harding, P. J., Gwynne, S. M. V., Amos, M. (2010). An early warning method for crush. arXiv:1008.2160. <https://arxiv.org/abs/1008.2160>
- [R35] Zhang, L., Lai, D., Miranskyy, A. V. (2018). The Impact of Position Errors on Crowd Simulation. arXiv:1810.11131 (*Simulation Modelling Practice and Theory* 채택). <https://arxiv.org/abs/1810.11131>

**실험 데이터**

- [R20] Adrian, J., Boltes, M., Holl, S., Sieben, A., Seyfried, A. (2020). Crowding and Queuing in Entrance Scenarios: Influence of Corridor Width in Front of Bottlenecks. *Collective Dynamics*, 5, 189–196. <https://arxiv.org/abs/2007.06396> / Adrian, J., Seyfried, A., Sieben, A. (2020). Crowds in front of bottlenecks at entrances from the perspective of physics and social psychology. *J. R. Soc. Interface*. DOI 10.1098/rsif.2019.0871.
- [R21] Forschungszentrum Jülich. Pedestrian Dynamics Data Archive (DOI 10.34735/ped.da, CC BY 4.0). <https://ped.fz-juelich.de/da/doku.php> — `crowdqueue` (10.34735/ped.2018.1): <https://ped.fz-juelich.de/da/doku.php?id=crowdqueue>, `effect_on_pushing` (10.34735/ped.2022.4): <https://ped.fz-juelich.de/da/doku.php?id=effect_on_pushing>

**영상 감지 방법**

- [R22] Alia, A., Maree, M., Chraibi, M. (2022). A Hybrid Deep Learning and Visualization Framework for Pushing Behavior Detection in Pedestrian Dynamics. *Sensors*, 22(11), 4040. 코드: <https://github.com/PedestrianDynamics/DL4PuDe> (BSD-3-Clause)
- [R23] Alia, A. 외 (2023). A Cloud-based Deep Learning Framework for Early Detection of Pushing at Crowded Event Entrances. *IEEE Access*. DOI 10.1109/ACCESS.2023.3273770. <https://arxiv.org/abs/2302.08237>
- [R24] Alia, A., Maree, M., Chraibi, M., Seyfried, A. (2024). A novel Voronoi-based convolutional neural network framework for pushing person detection in crowd videos. *Complex & Intelligent Systems*, 10(4), 5005–5031. DOI 10.1007/s40747-024-01422-2. <https://arxiv.org/abs/2310.07416>
- [R25] Ali, S., Shah, M. (2007). A Lagrangian Particle Dynamics Approach for Crowd Flow Segmentation and Stability Analysis. *CVPR*. DOI 10.1109/CVPR.2007.382977.
- [R26] (= references.md [22]) Mehran, R., Oyama, A., Shah, M. (2009). Abnormal Crowd Behavior Detection using Social Force Model. *CVPR*.
- [R27] Mehran, R., Moore, B. E., Shah, M. (2010). A Streakline Representation of Flow in Crowded Scenes. *ECCV*.
- [R28] Bhola, G., Srivastava, S., Nidhan, H. R., Kathed, S. (2026). Stampede detection and crowd analysis using CNN-LSTM and farneback optical flow. *Scientific Reports*, 16, 16155. DOI 10.1038/s41598-026-45262-1. <https://pmc.ncbi.nlm.nih.gov/articles/PMC13201541/>
- [R29] Perko, R., Schnabel, T., Fritz, G., Almer, A., Paletta, L. (2013). Counting people from above: Airborne video based crowd analysis. arXiv:1304.6213. <https://arxiv.org/abs/1304.6213>
- [R30] He, F., Yue, J., Zhu, J., Seyfried, A., Casas, D., Pettré, J., Wang, H. (2025). Learning Extremely High Density Crowds as Active Matters. *CVPR*, 540–550. <https://arxiv.org/abs/2503.12168>
- [R31] AlGhamdi, F. 외 (2025). VelocityNet: Real-Time Crowd Anomaly Detection via Person-Specific Velocity Analysis. arXiv:2510.18187. <https://arxiv.org/abs/2510.18187>
- [R32] Chatagnon, T., Tordeux, A., Chraibi, M. (2025). Exploring Dense Crowd Dynamics: State of the Art and Emerging Paradigms. arXiv:2505.05826 (*Crowd Dynamics, Volume 5* 수록 예정). <https://arxiv.org/abs/2505.05826>

**광학 흐름**

- [R36] (= references.md [21], 저장소 [66]) Schröder, G., Senst, T., Bochinski, E., Sikora, T. (2018). Optical Flow Dataset and Benchmark for Visual Crowd Analysis. *AVSS*. <https://arxiv.org/abs/1811.07170>
- [R37] (= references.md [18]) Farnebäck, G. (2003). Two-Frame Motion Estimation Based on Polynomial Expansion. *SCIA*, LNCS 2749.
- [R38] (= references.md [19]) Kroeger, T., Timofte, R., Dai, D., Van Gool, L. (2016). Fast Optical Flow using Dense Inverse Search. *ECCV*.
- [R39] (= references.md [20]) Teed, Z., Deng, J. (2020). RAFT: Recurrent All-Pairs Field Transforms for Optical Flow. *ECCV*. <https://arxiv.org/abs/2003.12039>

**시뮬레이션 도구**

- [R40] JuPedSim (LGPLv3). <https://github.com/PedestrianDynamics/jupedsim>, 문서 <https://www.jupedsim.org/stable/>
- [R41] Vadere (GPLv3). <https://gitlab.lrz.de/vadere/vadere>
- [R42] PySocialForce (MIT). <https://github.com/yuxiang-gao/PySocialForce>, <https://pypi.org/project/pysocialforce>

**기타**

- [R43] (= references.md [13]) Song, Q. 외 (2021). Rethinking Counting and Localization in Crowds: A Purely Point-Based Framework. *ICCV*. <https://arxiv.org/abs/2107.12746>
