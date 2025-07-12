# 🥪 Git 협업 가이드

이 문서는 Hackathon 2025 팀 프로젝트의 Git 브랜치 네이버와 커미트 메시지 작성 규칙을 정의합니다.  
일관된 Git 사용으로 효율적인 협업을 진행합시다!

---

## ✅ 브랜치 네이버 규칙

```
<타입>/<작업내용-짧은설명>
```

### 브랜치 타입

| 타입      | 설명                         |
|-----------|------------------------------|
| feature   | 새로운 기능 개발             |
| fix       | 버그 수정                    |
| refactor  | 코드 리파터링 (기능 변화 없음) |
| docs      | 문서 작성 및 수정            |
| test      | 테스트 코드 작성 및 수정     |
| chore     | 설정, 환경 등 자비일           |
| hotfix    | 금기한 오류 수정             |

### 브랜치 예시

- `feature/signup-page`
- `fix/login-error`
- `refactor/api-structure`
- `docs/readme-update`
- `chore/init-project`

---

## ✅ 커미트 메시지 규칙

```
<타입>: <변경 요약>

(선택) 본문에 상세한 설명 추가 가능
```

### 커미트 타입

| 타입     | 설명                              |
|----------|-----------------------------------|
| feat     | 새로운 기능 추가                  |
| fix      | 버그 수정                         |
| refactor | 리파터링                          |
| docs     | 문서 작성 및 수정                 |
| test     | 테스트 코드 추가/수정             |
| chore    | 빌드/패키지/설정파일 등 자비일      |
| style    | 코드 포맷팅 (세미코롱, 드래곤시기 등) |
| hotfix   | 배포 지전/지후 금기 수정           |

### 커미트 메시지 예시

- `feat: 회원가입 페이지 UI 구현`
- `fix: 로그인 오류 alert 메시지 추가`
- `refactor: API 모듈 분리 및 폴더 구조 정리`
- `docs: README에 실행 방법 추가`
- `chore: .gitignore 및 환경 설정 파일 추가`

---

## 📚 Git 작업 예시

```bash
# 브랜치 생성 및 이동
git checkout -b feature/signup-page

# 작업 후 커미트
git add .
git commit -m "feat: 회원가입 폼 구현 및 유향성 검사 추가"

# 원겨 저장소에 푸시
git push origin feature/signup-page

# GitHub에서 Pull Request 생성
```

---

## 🛠 기타 규칙

- 브랜치는 항상 `main` 브랜치에서 파사하기
- PR 제목도 커미트 메시지 형식으로 작성
- 기능 완료 후 팀원과 리뷰 후 `main`에 막기

---

> 🎉 함께 만들는 깨끗한 코드와 기록!  
> 예진 팀 화이팅 💪
