# 🚀 배포 체크리스트

네이버 카페 자동화 시스템 배포를 위한 단계별 가이드

---

## 📋 배포 전 체크리스트

### ✅ 1. 데이터베이스 마이그레이션

서버에서 실행:

```bash
# PostgreSQL 데이터베이스에 접속
psql -U username -d database_name

# SQL 파일 실행
\i migration_automation_system.sql

# 또는 직접 실행
psql -U username -d database_name -f migration_automation_system.sql

# 테이블 생성 확인
\dt automation_*
```

예상 출력:
```
automation_worker_pcs
automation_accounts
automation_cafes
automation_prompts
automation_schedules
automation_tasks
automation_posts
automation_comments
```

---

### ✅ 2. 환경 변수 설정

`.env` 파일에 추가:

```bash
# Claude API 키 (AI 모드용)
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here

# 기타 설정 (이미 있음)
DATABASE_URL=postgresql://...
SECRET_KEY=...
```

---

### ✅ 3. 서버 재시작

```bash
# 서버 프로세스 재시작
sudo systemctl restart shs-product-db

# 또는 수동 재시작
pkill -f "uvicorn main:app"
uvicorn main:app --host 0.0.0.0 --port 10000 --reload
```

---

### ✅ 4. 서버 접속 확인

브라우저에서:
```
https://scorp274.com/automation/cafe
```

로그인 후 다음 확인:
- [ ] 페이지가 정상적으로 로드됨
- [ ] 통계 카드가 표시됨 (0개여도 OK)
- [ ] PC 상태 카드가 비어있음 (정상)

---

## 🖥️ 작업 PC 설정

### PC #1 설정

#### 1. 파일 복사
```
C:\WorkerPC\
├── worker_agent.py
├── test_worker_setup.py
└── requirements-worker.txt
```

#### 2. 고정 IP 설정
- IP: `192.168.1.101`
- 서브넷: `255.255.255.0`
- 게이트웨이: `192.168.1.1`
- DNS: `8.8.8.8, 8.8.4.4`

#### 3. 패키지 설치
```bash
cd C:\WorkerPC
pip install selenium websockets psutil requests webdriver-manager
```

#### 4. 테스트
```bash
python test_worker_setup.py
```

모든 테스트 통과 확인!

#### 5. Worker Agent 실행
```bash
python worker_agent.py 1
```

#### 6. 서버 대시보드 확인
```
https://scorp274.com/automation/cafe
```
PC #1이 🟢 온라인으로 표시되어야 함

### PC #2, #3, ... (동일 과정)
- IP만 변경: 192.168.1.102, 192.168.1.103, ...
- Worker Agent 실행 시 번호 변경: 2, 3, ...

---

## 🎯 초기 데이터 설정

### 1. 네이버 계정 등록

서버에서:
```
https://scorp274.com/automation/cafe → 계정 관리 → 계정 추가
```

예시:
```
계정 ID: test_account_1
비밀번호: ********
할당 PC: PC #1
```

최소 3~5개 계정 등록 권장

### 2. 카페 등록

```
https://scorp274.com/automation/cafe → 카페 관리 → 카페 추가
```

예시:
```
카페명: 테스트 카페
URL: https://cafe.naver.com/testcafe
카페 ID: testcafe
```

### 3. 프롬프트 등록 (AI 모드)

#### 방법 1: 기존 레퍼런스 변환
```bash
# 서버에서 실행
python convert_references_to_prompts.py

# 옵션 1 선택 (전체 변환)
```

#### 방법 2: 수동 등록
```
https://scorp274.com/automation/cafe → 프롬프트 관리 → 프롬프트 추가
```

---

## 🧪 테스트 시나리오

### 테스트 1: 휴먼 모드

1. 기존 마케팅 카페에서 글 작성
2. 자동화 스케줄 생성
3. 작업 할당 확인
4. 실제 카페에 글 작성되는지 확인

### 테스트 2: AI 모드

1. 프롬프트 등록 확인
2. 상품 선택
3. AI 스케줄 자동 생성
4. Claude가 글 생성하는지 확인
5. 작업 큐에 추가되는지 확인

---

## 📊 모니터링

### 대시보드 확인

#### 메인 대시보드
```
https://scorp274.com/automation/cafe
```

확인 사항:
- [ ] PC 상태 (온라인/오프라인)
- [ ] CPU/메모리 사용률
- [ ] 작업 대기 목록
- [ ] 진행 중인 작업
- [ ] 완료된 작업

#### 통계 대시보드
```
https://scorp274.com/automation/stats
```

확인 사항:
- [ ] 전체 작업 통계
- [ ] 일별 추이 그래프
- [ ] PC별 성능
- [ ] 계정 사용 통계

---

## ⚠️ 주의사항

### 보안
- [ ] API 키 노출 금지 (.env 파일 관리)
- [ ] 계정 정보 암호화
- [ ] 로그 파일 정기 삭제

### 운영
- [ ] 하루 작성량 제한 (계정당 5~10개)
- [ ] IP 고정 확인
- [ ] 계정 상태 주기적 점검

### 성능
- [ ] PC 성능 모니터링
- [ ] 네트워크 안정성 확인
- [ ] Chrome 캐시 정리

---

## 🔧 문제 해결

### PC가 연결되지 않음
1. Worker Agent 실행 확인
2. 네트워크 연결 확인
3. 방화벽 설정 확인

### 작업이 실패함
1. 로그 확인 (Worker Agent 콘솔)
2. 계정 로그인 상태 확인
3. 카페 권한 확인

### AI 글 생성 안됨
1. ANTHROPIC_API_KEY 확인
2. 프롬프트 등록 확인
3. API 잔액 확인

---

## 📞 지원

### 로그 위치
- Worker Agent: 콘솔 출력
- 서버: `/var/log/shs-product-db/automation.log`

### 디버그 모드
```python
# worker_agent.py 수정
DEBUG = True
```

---

## ✅ 최종 체크리스트

### 서버
- [ ] 데이터베이스 마이그레이션 완료
- [ ] 환경 변수 설정 완료
- [ ] 서버 재시작 완료
- [ ] 웹 페이지 접속 확인

### 작업 PC
- [ ] Python 설치 (3.9+)
- [ ] Chrome 설치
- [ ] 고정 IP 설정
- [ ] 패키지 설치
- [ ] Worker Agent 실행
- [ ] 서버 연결 확인

### 데이터
- [ ] 계정 등록 (3개 이상)
- [ ] 카페 등록 (1개 이상)
- [ ] 프롬프트 등록 (AI 모드용)

### 테스트
- [ ] 휴먼 모드 테스트
- [ ] AI 모드 테스트
- [ ] 모니터링 확인
- [ ] 통계 확인

---

**배포 일자:** _____________  
**담당자:** _____________  
**버전:** 1.0

