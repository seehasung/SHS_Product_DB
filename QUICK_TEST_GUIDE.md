# 🧪 댓글 시스템 빠른 테스트 가이드

## 1️⃣ 로컬 파싱 테스트 (1분)

```bash
python test_comment_parser_simple.py
```

**결과:** 5개 댓글 파싱 완료 ✅

---

## 2️⃣ 서버 배포 (5분)

### Git 커밋 & 푸시

```bash
git add .
git commit -m "Add comment sequential system"
git push origin main
```

Render.com이 자동으로 배포합니다 (3-5분 소요)

---

## 3️⃣ 데이터베이스 마이그레이션 (2분)

Render.com Shell에서:

```bash
cd /opt/render/project/src
alembic revision --autogenerate -m "Add comment_script table"
alembic upgrade head
```

---

## 4️⃣ Worker PC 준비 (각 PC마다 1분)

### PC #1에서:

```bash
cd C:\Users\서하성\Desktop\프로그램\파이썬\cs-system\SHS_Product_DB
python worker_agent.py 1
```

### PC #2에서:

```bash
python worker_agent.py 2
```

**자동 업데이트가 실행됩니다!** ⚡

---

## 5️⃣ 웹 관리 페이지 테스트 (10분)

### 5-1. 관리자 로그인

```
https://scorp274.com/automation/cafe
```

### 5-2. PC 확인

- "PC 관리" 탭
- Worker PC #1, #2가 🟢 online 상태인지 확인

### 5-3. 계정 등록

- "계정 관리" 탭
- 네이버 계정 추가 (최소 2개)
- PC에 할당

### 5-4. 카페 등록

- "카페 관리" 탭
- 테스트할 카페 URL 추가

### 5-5. 본문 글 스케줄 생성

- "스케줄 관리" 탭
- "스케줄 생성" 클릭
- 모드: 휴먼
- 상품/카페 선택
- 오늘 날짜, 1개

### 5-6. 댓글 원고 입력

- "대시보드" 탭
- 대기 중인 Task 찾기
- 💬 버튼 클릭
- 댓글 원고 입력:

```
1-1: PC1 도와주세요ㅠㅜㅠㅠㅠ
1-2: PC2 저도 궁금하네요
1-3: PC1 오 대박...

2-1: PC2 다들 고민이네요
2-2: PC1 맞아요 진짜
```

- 저장 클릭

---

## 6️⃣ 실행 및 모니터링

### 6-1. 본문 글 작성 대기

Worker PC가 자동으로 본문 글 작성
→ URL 획득

### 6-2. 댓글 Task 생성

- "완료" 탭에서 완료된 글 찾기
- "➕ 댓글" 버튼 클릭
- 자동으로 5개 댓글 Task 생성!

### 6-3. 순차 실행 관찰

```
PC1: 1-1 댓글 작성 ✅
  ↓ (2초 대기)
PC2: 1-2 댓글 작성 ✅
  ↓ (2초 대기)
PC1: 1-3 댓글 작성 ✅
  ↓ (2초 대기)
PC2: 2-1 새 댓글 ✅
  ↓ (2초 대기)
PC1: 2-2 대댓글 (2-1에 답글) ✅
```

---

## ✅ 성공 확인

1. 네이버 카페 글에 접속
2. 댓글 5개가 순서대로 작성되었는지 확인
3. 2-2 댓글이 2-1의 답글로 작성되었는지 확인

---

## 🐛 문제 해결

### Worker PC가 online이 안 돼요

- PC에서 `python worker_agent.py 1` 실행
- 방화벽 확인
- VPN 연결 확인

### 댓글이 작성 안 돼요

- Worker PC 콘솔에서 오류 확인
- 네이버 로그인 상태 확인
- 캡챠 수동 해결 필요

### 댓글 선택자를 못 찾아요

- `test_naver_comment.py` 실행
- 브라우저 F12로 선택자 확인
- `worker_agent.py`의 `comment_selectors` 수정

---

## 📞 지원

문제가 있으면:
1. Render.com Logs 확인
2. Worker PC 콘솔 확인
3. 브라우저 F12 Network 탭 확인

---

**행운을 빕니다!** 🍀

