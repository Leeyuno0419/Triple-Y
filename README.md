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
| `feat/기능명` | 기능 개발 | 각자 |
| `fix/버그명` | 버그 수정 | 각자 |

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
| (미정) | (미정) |
