# Triple Y 팀 프로젝트 지침

CrowdSight — CCTV 기반 군중 밀도·흐름 불안정·60초 변화 예측 시스템. 3인 팀 프로젝트 (AI: Python / 서버: Spring Boot / 화면: React).
전역 지침(`~/.claude/CLAUDE.md`)에 더해 아래 규칙을 따른다.

## 폴더 구조
```
Triple Y/
├─ src/           # 사전 분석 (Python) - 재사용 코드 (.py)
│  ├─ counting/   # 인원 추정·밀도 (이유노)
│  ├─ flow/       # 흐름·군중 불안정 (조영준)
│  └─ predict/    # 60초 예측 (나예린)
├─ server/        # Spring Boot - 타임라인 재생·등급 판정·알림 API
├─ web/           # React - 상황실 대시보드
├─ infra/         # 구역 설정
├─ notebooks/     # 탐색·실험용 .ipynb
├─ data/
│  ├─ raw/        # 원본 데이터 (수정 금지, git 제외)
│  └─ processed/  # 전처리 결과 (git 제외)
├─ outputs/       # 실험 결과 표·그래프 (모델 가중치는 git 제외)
├─ docs/          # 기획서(proposal.md)·상세 문서(proposal-detail.md)·출처(references.md), 발표 자료
├─ Images/        # 이미지 자료 (기획서 그림: Images/proposal/)
├─ requirements.txt
└─ .env           # 비밀키 (git 제외)
```
- 담당마다 폴더가 나뉜다: AI `src/counting/`(인원·밀도)·`src/flow/`(흐름·불안정)·`src/predict/`(예측), 서버 `server/`, 화면 `web/`, 실행 설정 `infra/`. 다른 사람의 폴더는 담당자와 상의한 뒤 수정한다.
- AI 모듈끼리는 기획서 3.4의 입출력과 `timeline.json` 규격으로만 주고받는다. `timeline.json`에는 구역 ID와 셀·구역 집계값만 넣는다.
- 재사용할 로직은 `src/`의 `.py`로 두고, 노트북에서 import해서 쓴다.
- 원본 데이터(`data/raw/`)는 절대 덮어쓰거나 수정하지 않는다.

## Git 협업 규칙
### 브랜치
| 브랜치 | 용도 | 누가 |
|---|---|---|
| `main` | 항상 돌아가는 상태만 | 직접 푸시 금지 |
| `feat/기능명` | 기능 개발 (문서·설정·리팩터링 포함) | 각자 |
| `fix/버그명` | 버그 수정 | 각자 |

- 이름은 소문자 영문과 하이픈만 쓴다. 예: `feat/data-preprocess`, `fix/null-handling`
- 브랜치 하나에는 목적 하나만 담는다. 작업이 끝나면 빨리 병합하고 오래 끌지 않는다.

### 작업 흐름
1. `main` 최신화: `git switch main; git pull`
2. 브랜치 생성: `git switch -c feat/기능명`
3. 작업 후 커밋, 푸시: `git push -u origin feat/기능명`
4. GitHub에서 PR 생성. 제목은 커밋 메시지와 같은 `접두사: 내용` 형식.
5. 팀원 1명 이상 승인 후 `main`에 병합.
6. 병합이 끝난 브랜치는 삭제하고 `main`을 다시 pull한다.

### `main` 보호 설정 (GitHub에 적용됨)
- PR 필수, 승인 1명 이상 필요
- 강제 푸시(force push)와 브랜치 삭제 금지
- 저장소 소유자(관리자)는 예외로 직접 병합 가능. 팀원이 합류한 뒤에는 소유자도 승인 절차를 따른다.

### 충돌 줄이는 법
- 작업을 시작하기 전에 `main`을 pull하고, 긴 작업은 중간에 `main`을 반영한다.
- 같은 파일을 여러 명이 동시에 수정하지 않도록 담당을 나눈다. 특히 `.ipynb`는 병합 충돌이 어려우니 한 번에 한 명만 수정한다.
- PR은 작게 자주 올린다.

### Claude 작업 시 규칙
- `main`에 직접 커밋·푸시하지 않는다. 항상 위 이름 규칙의 브랜치를 만들어 작업한다.
- 커밋·푸시·PR 생성은 사용자가 요청할 때만 한다.
- 커밋 메시지는 `접두사: 내용` 형식. 접두사: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## 코드 컨벤션
- PEP 8 준수. 함수·변수는 `snake_case`, 클래스는 `PascalCase`.
- 모든 함수에 타입힌트를 쓰고, 기능 설명 docstring(한국어)을 붙인다.
- `server/`(Java)·`web/`(JavaScript) 규칙은 각 담당자가 개발을 시작할 때 정해 이 절에 추가한다.

## 데이터·AI 규칙
- 비밀키·API 키는 `.env`에만 두고 코드에 직접 쓰지 않는다. `.env`, `data/`는 git에 올리지 않는다.
- 패키지를 추가하면 `requirements.txt`에 반영하고 팀에 알린다. 설치·삭제는 승인 후 진행한다.
- 재현성: 랜덤 시드를 고정하고, 실험 파라미터와 결과를 기록한다.
- 노트북은 커밋 전에 출력을 지운다.
- 모델 가중치(`*.pth`, `*.pt`, `*.onnx`)는 git에 올리지 않는다. 용량 문제와 함께, P2PNet 공식 가중치는 학술 연구 용도로만 쓸 수 있다.
- 원본 영상·머리 좌표·사용자 위치는 저장하지 않는다. 셀·구역 단위 집계값만 저장한다.

## 진행 원칙 (MVP)
- 범위·담당·일정의 기준은 `docs/proposal.md`다. MVP 밖 기능(여유 시)은 G2를 통과하고 시간이 남을 때만 만든다.
- 기본 구역 1개로 먼저 끝까지 만들고 검증 게이트(G0 11-10, G1 11-13, G2 11-18)를 통과한 뒤 넓힌다. 여러 구역을 한꺼번에 붙이지 않는다.
- 타임라인·API에는 처음부터 `zone_id`·`camera_id`를 둔다. 그래야 영상·구역 추가가 등록 작업으로 끝난다.
- 11-19에 코드를 동결한다. RPA 프로젝트는 11-23~25에 진행된다고 가정하며, 일정이 정해지면 조정한다.

## 기획서
- 기획서(`docs/proposal.md`, `docs/proposal.pdf`) 작업 시 `docs/proposal-guide.md`를 따른다.
- `docs/proposal.md`는 제출용 요약본이고, 이번 발표 범위(MVP)·담당·일정의 기준이다.
- 설계 근거·수식·기술 비교·사업성·여유 시 기능 설계는 `docs/proposal-detail.md`(내부용 상세 문서)에, 출처는 `docs/references.md`에 있다. 기능을 만들기 전에 상세 문서의 해당 절을 먼저 읽는다.

## 역할
| 이름 | AI 모듈 | 서비스 파트 | 담당 폴더 |
|---|---|---|---|
| 이유노 (팀장) | 인원 추정·밀도 (P2PNet, 호모그래피, 분석 스크립트 통합) | PM, 데이터, 구역 설정, G0·G1·G2 검증·성능 측정 | `src/counting/`, `infra/` |
| 조영준 | 흐름·군중 불안정 (광학 흐름, 군중 압력, 유입 경보, E5) | Spring Boot 판정·알림·WebSocket | `src/flow/`, `server/` |
| 나예린 | 60초 예측 (E6) | React 상황실 대시보드 | `src/predict/`, `web/` |

- 모두 AI 과정을 들으므로 1인 = AI 모듈 1개 + 서비스 파트 1개로 나눴다. 바꾸면 이 표와 `README.md`, 기획서 3.4를 함께 고친다.
