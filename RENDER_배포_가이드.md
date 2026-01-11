# 🚀 Render 서버 배포 가이드

**긴급:** AI 테이블 생성 필요!

---

## ⚠️ 현재 문제

```
sqlalchemy.exc.ProgrammingError: 
relation "ai_marketing_schedules" does not exist
```

**원인:** AI 자동화 테이블이 Render PostgreSQL에 생성되지 않음

---

## 🔧 해결 방법 (3가지 중 선택)

### **방법 1: SQL 파일 직접 실행 (추천, 가장 빠름)**

```bash
# 1. Render Dashboard → Shell 클릭
# 2. 다음 명령어 실행:

cd /opt/render/project/src
psql $DATABASE_URL < create_ai_tables.sql
```

**장점:**
- ✅ 가장 빠름 (1분)
- ✅ 확실함
- ✅ 에러 메시지 명확

---

### **방법 2: Python 스크립트 실행**

```bash
# 1. Render Dashboard → Shell 클릭
# 2. 다음 명령어 실행:

cd /opt/render/project/src
python create_ai_tables.py
```

**장점:**
- ✅ 자동화
- ✅ 테이블 존재 여부 자동 확인
- ✅ 상세한 진행 상황 표시

---

### **방법 3: psql에서 직접 입력 (수동)**

```bash
# 1. Render Dashboard → Shell 클릭
# 2. psql 접속:

psql $DATABASE_URL

# 3. 테이블 확인:
\dt ai_*

# 4. 없으면 SQL 실행:
# create_ai_tables.sql의 내용을 복사해서 붙여넣기
```

---

## 📋 실행 후 확인

### **테이블 생성 확인:**

```bash
psql $DATABASE_URL

# 테이블 목록 확인
\dt ai_*

# 예상 출력:
# ai_marketing_products
# ai_product_keywords
# ai_product_references
# ai_prompt_templates
# ai_prompts
# ai_marketing_schedules
# ai_generated_posts

# 종료
\q
```

---

## 🔄 서버 재시작

### **방법 1: Render Dashboard (권장)**
```
1. Render Dashboard 접속
2. 해당 서비스 선택
3. "Manual Deploy" 클릭
4. "Deploy latest commit" 클릭
5. 3-5분 대기
```

### **방법 2: 코드 Push (자동 배포)**
```bash
# 로컬에서
git add .
git commit -m "AI 테이블 생성 스크립트 추가"
git push

# Render가 자동으로 재배포 (3-5분)
```

---

## ✅ 배포 완료 확인

### **1. 서버 접속:**
```
https://scorp274.com
```

### **2. 로그인 후 확인:**
```
자동화 → 카페 관리 → AI 상품 세팅 탭
```

### **3. 에러 없이 로드되면 성공!**

---

## 📝 단계별 실행 가이드

### **Step 1: Render Shell 접속**
1. https://dashboard.render.com 접속
2. "SHS Product DB" 서비스 클릭
3. 우측 상단 "Shell" 버튼 클릭

### **Step 2: 테이블 생성**
```bash
cd /opt/render/project/src
python create_ai_tables.py
```

**예상 출력:**
```
============================================================
AI 자동화 시스템 테이블 생성 시작
============================================================

✅ 데이터베이스 연결: postgresql://...

📊 기존 테이블: XX개

🔍 AI 테이블 확인:
  ❌ ai_marketing_products (없음)
  ❌ ai_product_keywords (없음)
  ❌ ai_product_references (없음)
  ❌ ai_prompt_templates (없음)
  ❌ ai_prompts (없음)
  ❌ ai_marketing_schedules (없음)
  ❌ ai_generated_posts (없음)

🔨 누락된 테이블 생성 중... (7개)
  🔨 ai_marketing_products 생성 중...
  ✅ ai_marketing_products 생성 완료
  ...
  
✅ 모든 AI 테이블 생성 완료!

============================================================
✅ AI 자동화 시스템 테이블 생성 완료!
============================================================
```

### **Step 3: 서버 재시작**
```bash
# Shell 종료 (Ctrl+D)

# Render Dashboard에서:
Manual Deploy → Deploy latest commit
```

### **Step 4: 확인**
```
https://scorp274.com/automation/cafe
→ AI 상품 세팅 탭 클릭
→ 에러 없이 로드되면 성공!
```

---

## 🐛 문제 해결

### **문제 1: 권한 에러**
```
ERROR: permission denied for table
```

**해결:**
```bash
# Render Shell에서
psql $DATABASE_URL

# 권한 확인
\du

# 필요시 권한 부여
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
```

### **문제 2: 외래키 에러**
```
ERROR: relation "marketing_products" does not exist
```

**해결:**
- 기본 테이블이 없는 경우
- `init_db.py` 먼저 실행

### **문제 3: 스크립트 파일 없음**
```
ERROR: No such file
```

**해결:**
```bash
# Git에 추가되었는지 확인
ls -la create_ai_tables.*

# 없으면 로컬에서 Push
git add create_ai_tables.py create_ai_tables.sql
git commit -m "Add AI table creation scripts"
git push
```

---

## 📞 긴급 지원

### **즉시 실행 명령어:**

```bash
# Render Shell에서 한 번에 복사/붙여넣기

cd /opt/render/project/src && \
python create_ai_tables.py && \
echo "✅ 완료! 서버를 재시작하세요."
```

---

## 🎯 배포 후 할 일

1. ✅ 테이블 생성 확인
2. ✅ 서버 재시작
3. ✅ AI 상품 추가 테스트
4. ✅ 키워드 동기화 테스트
5. ✅ 프롬프트 생성 테스트
6. ✅ Claude API 연동 확인

---

**긴급 배포이므로 바로 실행하세요!** 🚀
