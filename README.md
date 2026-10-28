# Triple Y

Python/데이터/AI 팀 프로젝트 (3인).

> 프로젝트 목표와 개요는 정해지면 이 섹션에 작성한다.

## 폴더 구조
```
Triple Y/
├─ data/
│  ├─ raw/        # 원본 데이터 (수정 금지, git 제외)
│  └─ processed/  # 전처리 결과 (git 제외)
├─ src/           # 재사용 코드 (.py)
├─ notebooks/     # 탐색·실험용 .ipynb
├─ outputs/       # 모델, 그래프, 결과 파일
├─ docs/          # 문서, 발표 자료
└─ Images/        # 이미지 자료
```

## 시작하기
```powershell
git clone https://github.com/Leeyuno0419/Triple-Y.git
cd Triple-Y
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
- `requirements.txt`는 패키지를 추가할 때 만든다.
- 비밀키·API 키는 프로젝트 루트의 `.env`에 둔다 (git 제외).
- 데이터는 git에 올리지 않으므로 팀 공유 방식으로 별도 전달받는다.

## 협업 규칙
### 브랜치
| 브랜치 | 용도 | 누가 |
|---|---|---|
| `main` | 항상 돌아가는 상태만 | 직접 푸시 금지 |
| `feat/기능명` | 기능 개발 (문서·설정·리팩터링 포함) | 각자 |
| `fix/버그명` | 버그 수정 | 각자 |

- 이름은 소문자 영문과 하이픈만 쓴다. 예: `feat/data-preprocess`, `fix/null-handling`
- 브랜치 하나에는 목적 하나만 담고, 끝나면 빨리 병합한다.

### 작업 흐름
```powershell
git switch main; git pull                  # 1. main 최신화
git switch -c feat/기능명                   # 2. 브랜치 생성
# ... 작업 후 커밋 ...
git push -u origin feat/기능명              # 3. 푸시
```
4. GitHub에서 PR을 만든다. 제목은 커밋 메시지와 같은 `접두사: 내용` 형식.
5. 팀원 1명 이상이 승인하면 `main`에 병합한다.
6. 병합이 끝난 브랜치는 삭제하고 `main`을 다시 pull한다.

### `main` 보호 설정
- PR 필수, 승인 1명 이상 필요
- 강제 푸시(force push)와 브랜치 삭제 금지
- 저장소 소유자(관리자)는 예외로 직접 병합할 수 있다.

### 충돌 줄이는 법
- 작업 시작 전에 `main`을 pull하고, 긴 작업은 중간에 `main`을 반영한다.
- 같은 파일을 동시에 수정하지 않도록 담당을 나눈다. `.ipynb`는 한 번에 한 명만 수정한다.
- PR은 작게 자주 올린다.

### 커밋 메시지
`접두사: 내용` 형식. 접두사: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

### 코드 컨벤션
- PEP 8 준수, 함수·변수는 `snake_case`, 클래스는 `PascalCase`.
- 모든 함수에 타입힌트와 기능 설명 docstring을 쓴다.
- 노트북은 커밋 전에 출력을 지운다.
- 랜덤 시드를 고정하고 실험 파라미터와 결과를 기록한다.

자세한 규칙은 [CLAUDE.md](CLAUDE.md)를 참고한다.

## 팀원
| 이름 | 담당 |
|---|---|
| 이유노 | 팀장 (세부 담당 미정) |
| 조영준 | (미정) |
| 나예린 | (미정) |
