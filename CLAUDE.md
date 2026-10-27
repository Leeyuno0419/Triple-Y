# Triple Y 팀 프로젝트 지침

Python/데이터/AI 팀 프로젝트(3인). 전역 지침(`~/.claude/CLAUDE.md`)에 더해 아래 규칙을 따른다.

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
├─ Images/        # 이미지 자료
├─ requirements.txt
└─ .env           # 비밀키 (git 제외)
```
- 재사용할 로직은 `src/`의 `.py`로 두고, 노트북에서 import해서 쓴다.
- 원본 데이터(`data/raw/`)는 절대 덮어쓰거나 수정하지 않는다.

## Git 협업 규칙
- `main`은 직접 푸시하지 않는다. `feature/기능명` 브랜치에서 작업하고 PR로 병합한다.
- 커밋 메시지는 `접두사: 내용` 형식. 접두사: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- 커밋·푸시는 사용자가 요청할 때만 한다.

## 코드 컨벤션
- PEP 8 준수. 함수·변수는 `snake_case`, 클래스는 `PascalCase`.
- 모든 함수에 타입힌트를 쓰고, 기능 설명 docstring(한국어)을 붙인다.

## 데이터·AI 규칙
- 비밀키·API 키는 `.env`에만 두고 코드에 직접 쓰지 않는다. `.env`, `data/`는 git에 올리지 않는다.
- 패키지를 추가하면 `requirements.txt`에 반영하고 팀에 알린다. 설치·삭제는 승인 후 진행한다.
- 재현성: 랜덤 시드를 고정하고, 실험 파라미터와 결과를 기록한다.
- 노트북은 커밋 전에 출력을 지운다.

## 역할
- 담당 미정. 정해지면 이 섹션에 추가한다.
