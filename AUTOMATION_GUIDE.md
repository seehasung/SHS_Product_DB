# 🤖 네이버 카페 자동화 시스템 - 설정 및 운영 가이드

## 📋 목차
1. [시스템 개요](#시스템-개요)
2. [초기 설정](#초기-설정)
3. [작업 PC 설정](#작업-pc-설정)
4. [서버 설정](#서버-설정)
5. [운영 방법](#운영-방법)
6. [문제 해결](#문제-해결)

---

## 시스템 개요

### 🏗️ 아키텍처

```
┌─────────────────────────────────────┐
│     SCORP 서버 (중앙 관제)           │
│  - FastAPI 백엔드                   │
│  - PostgreSQL 데이터베이스           │
│  - WebSocket 통신                   │
│  - Claude API 연동                  │
└─────────────────────────────────────┘
              ↕️ WebSocket
┌─────────────────────────────────────┐
│      작업 PC들 (Worker Agents)       │
│  PC #1    PC #2    PC #3    ...     │
│  IP: A    IP: B    IP: C            │
│  Selenium Selenium Selenium         │
└─────────────────────────────────────┘
```

### 🎯 핵심 기능
- ✅ 글 자동 작성 (휴먼/AI 모드)
- ✅ 댓글 자동 작성 (계층 구조 지원)
- ✅ 여러 PC 동시 작업
- ✅ 실시간 모니터링
- ✅ 봇 감지 우회
- ✅ 작업 큐 관리

---

## 초기 설정

### 1. 데이터베이스 마이그레이션

서버에서 실행:

```bash
# 마이그레이션 파일 생성
python -m alembic revision --autogenerate -m "add_automation_system"

# 마이그레이션 실행
python -m alembic upgrade head
```

### 2. 환경 변수 설정 (.env)

`.env` 파일에 추가:

```env
# Claude API (AI 모드용)
ANTHROPIC_API_KEY=sk-ant-...your-key-here
```

### 3. 필수 패키지 설치

서버:
```bash
pip install anthropic
```

작업 PC:
```bash
pip install selenium
pip install websockets
pip install psutil
pip install requests
```

Chrome 드라이버 설치:
```bash
pip install webdriver-manager
```

---

## 작업 PC 설정

### 📌 각 PC별 고유 IP 설정

**중요:** 네이버 계정별로 IP가 달라야 합니다!

#### Windows 고정 IP 설정:
1. `제어판` → `네트워크 및 인터넷` → `네트워크 연결`
2. 이더넷 우클릭 → `속성`
3. `Internet Protocol Version 4 (TCP/IPv4)` 선택 → `속성`
4. `다음 IP 주소 사용` 선택:
   ```
   PC #1: 192.168.1.101
   PC #2: 192.168.1.102
   PC #3: 192.168.1.103
   ...
   ```

### 📥 Worker Agent 설치

#### 1. Python 설치 (3.9 이상)
- https://www.python.org/downloads/

#### 2. 프로젝트 파일 복사
각 PC에 다음 파일 복사:
```
worker_agent.py
requirements.txt (작업 PC용)
```

#### 3. 패키지 설치
```bash
pip install selenium websockets psutil requests webdriver-manager
```

#### 4. Chrome 브라우저 설치
- https://www.google.com/chrome/

### 🚀 Worker Agent 실행

#### PC별 실행:

**PC #1:**
```bash
python worker_agent.py 1
```

**PC #2:**
```bash
python worker_agent.py 2
```

**PC #3:**
```bash
python worker_agent.py 3
```

#### 자동 시작 설정 (Windows)

`작업 스케줄러`로 부팅 시 자동 실행:

1. `작업 스케줄러` 실행
2. `기본 작업 만들기` 클릭
3. 설정:
   - 이름: `Worker Agent PC1`
   - 트리거: `컴퓨터 시작 시`
   - 동작: `프로그램 시작`
   - 프로그램: `python.exe`
   - 인수: `C:\path\to\worker_agent.py 1`

---

## 서버 설정

### 1. PC 등록

서버 관리자 페이지에서 PC 등록:

```
/automation/cafe → PC 관리
```

또는 API로 등록:

```bash
curl -X POST https://scorp274.com/automation/api/pcs/register \
  -F "pc_number=1" \
  -F "pc_name=Worker PC #1" \
  -F "ip_address=192.168.1.101"
```

### 2. 네이버 계정 등록

```
/automation/cafe → 계정 관리 → 계정 추가
```

데이터:
- 계정 ID: naver_account_1
- 비밀번호: ****
- 할당 PC: PC #1

### 3. 카페 등록

```
/automation/cafe → 카페 관리 → 카페 추가
```

데이터:
- 카페명: 테스트 카페
- URL: https://cafe.naver.com/testcafe
- 카페 ID: testcafe

### 4. 프롬프트 등록 (AI 모드)

```
/automation/cafe → 프롬프트 관리 → 프롬프트 추가
```

**글 작성 프롬프트 예시:**

**시스템 프롬프트:**
```
당신은 네이버 카페 글 작성 전문가입니다. 
자연스럽고 유익한 정보를 제공하는 글을 작성합니다.
광고처럼 보이지 않고 진정성 있게 작성합니다.
```

**사용자 프롬프트 템플릿:**
```
다음 상품에 대해 {keyword} 키워드로 카페 글을 작성해주세요.

상품명: {product_name}
키워드: {keyword}

요구사항:
1. 제목: 20~30자, {keyword} 포함
2. 본문: 300~500자
3. 자연스럽고 진정성 있게
4. 광고 티 나지 않게
5. 유용한 정보 제공

형식:
제목: [여기에 제목]
---
[여기에 본문]
```

---

## 운영 방법

### 📅 스케줄 생성

#### 휴먼 모드 (사람이 작성한 글)

1. 기존 마케팅 카페에서 글 작성 완료
2. `/automation/cafe`에서 **휴먼 모드 스케줄 생성**
3. 작성된 글 선택
4. 카페 및 날짜 설정
5. 생성 → 자동 작업 큐에 추가됨

#### AI 모드 (Claude가 작성)

1. `/automation/cafe`에서 **AI 모드 스케줄 생성**
2. 설정:
   - 상품 선택
   - 프롬프트 선택
   - 하루 작성 개수
   - 기간 (시작일~종료일)
   - 주말 포함 여부 ✅
3. 생성 → AI가 글 자동 생성 → 작업 큐에 추가

### 📊 실시간 모니터링

대시보드: `/automation/cafe`

**확인 가능한 정보:**
- 🖥️ 각 PC 상태 (온라인/작업중/오프라인)
- 💻 CPU/메모리 사용률
- 📍 IP 주소
- 🔐 로그인된 계정
- 📋 현재 작업
- ⏰ 작업 대기 목록
- ✅ 완료된 작업
- ❌ 실패한 작업

### 🔄 작업 흐름

1. **스케줄 생성** → 작업 큐에 추가
2. **Worker Agent 대기** → 서버로부터 작업 수신
3. **작업 할당** → 사용 가능한 PC에 할당
4. **글/댓글 작성** → Selenium으로 자동 작성
5. **완료 보고** → 서버에 결과 전송
6. **다음 작업** → 대기 중인 작업 처리

---

## 문제 해결

### ❓ PC가 오프라인으로 표시됨

**원인:**
- Worker Agent 미실행
- 네트워크 연결 끊김
- 서버 WebSocket 연결 실패

**해결:**
1. Worker Agent 재실행
2. 네트워크 확인
3. 서버 로그 확인: `tail -f logs/automation.log`

### ❓ 계정이 로그인되지 않음

**원인:**
- 잘못된 계정 정보
- 네이버 보안 조치 (캡챠)
- IP 차단

**해결:**
1. 계정 정보 확인
2. 수동 로그인 시도
3. IP 변경 또는 대기

### ❓ 글 작성이 실패함

**원인:**
- 카페 권한 부족
- 카페 URL 변경
- 네이버 페이지 구조 변경

**해결:**
1. 카페 가입 및 권한 확인
2. 카페 URL 업데이트
3. Worker Agent 코드 수정 (선택자 업데이트)

### ❓ 봇으로 감지됨

**원인:**
- 너무 빠른 작성
- 패턴이 일정함
- IP 문제

**해결:**
1. 랜덤 지연 시간 증가
2. 작성 패턴 다양화
3. IP 변경
4. 작성 빈도 감소

### ❓ AI 생성 글이 이상함

**원인:**
- 프롬프트 부적절
- API 키 문제

**해결:**
1. 프롬프트 수정
2. API 키 확인
3. Claude 모델 변경

---

## 📝 주의사항

### ⚠️ 필수 준수 사항

1. **IP 관리**
   - 계정당 고유 IP 사용
   - IP 변경 시 재로그인

2. **작성 빈도**
   - 하루 5~10개 이하 권장
   - 시간 간격 충분히 두기

3. **콘텐츠 품질**
   - 스팸성 글 금지
   - 유용한 정보 제공
   - 자연스러운 문체

4. **계정 관리**
   - 계정 상태 주기적 확인
   - 차단된 계정 즉시 교체

5. **서버 보안**
   - API 키 노출 금지
   - 계정 정보 암호화
   - 로그 정기 삭제

---

## 🎯 최적화 팁

### 성능 향상

1. **PC 성능**
   - RAM 8GB 이상 권장
   - SSD 사용
   - Chrome 캐시 정기 삭제

2. **네트워크**
   - 유선 연결 권장
   - 안정적인 인터넷
   - VPN 사용 금지 (IP 일관성)

3. **작업 효율**
   - 피크 시간 피하기 (12~14시, 19~21시)
   - 새벽/이른 아침 활용
   - 주말 활용 (AI 모드)

### 봇 감지 우회

1. **랜덤 요소 강화**
   - 타이핑 속도 다양화
   - 마우스 이동 랜덤
   - 페이지 스크롤 추가

2. **휴먼 행동 모방**
   - 간헐적 휴식
   - 다른 페이지 방문
   - 검색 활동

3. **IP 관리**
   - 고정 IP 사용
   - 프록시 사용 시 품질 좋은 것
   - 차단 시 즉시 교체

---

## 📞 기술 지원

### 문제 발생 시

1. **로그 확인**
   - Worker Agent 콘솔
   - 서버 로그: `/var/log/automation.log`
   - 브라우저 개발자 도구

2. **디버그 모드**
   ```python
   # worker_agent.py에서
   DEBUG = True
   ```

3. **스크린샷 저장**
   - 오류 발생 시 자동 스크린샷
   - `screenshots/` 폴더에 저장

---

## 🔄 업데이트 및 유지보수

### 정기 업데이트

**월간:**
- Worker Agent 버전 확인
- Chrome 드라이버 업데이트
- 네이버 페이지 구조 변경 확인

**주간:**
- 작업 통계 분석
- 실패 패턴 확인
- 계정 상태 점검

**일간:**
- 대시보드 모니터링
- 오류 로그 확인
- PC 상태 점검

---

## ✅ 체크리스트

### 초기 설정
- [ ] 데이터베이스 마이그레이션
- [ ] 환경 변수 설정
- [ ] PC IP 설정
- [ ] Worker Agent 설치
- [ ] 계정 등록
- [ ] 카페 등록
- [ ] 프롬프트 등록 (AI 모드)

### 운영 전
- [ ] 모든 PC 온라인 확인
- [ ] 계정 로그인 확인
- [ ] 스케줄 생성
- [ ] 대시보드 모니터링 준비

### 운영 중
- [ ] 실시간 모니터링
- [ ] 오류 즉시 대응
- [ ] 통계 수집
- [ ] 품질 관리

---

## 🎓 추가 학습 자료

- Selenium 공식 문서: https://www.selenium.dev/documentation/
- WebSocket 가이드: https://websockets.readthedocs.io/
- Claude API 문서: https://docs.anthropic.com/

---

**마지막 업데이트:** 2025-12-30
**버전:** 1.0
**작성자:** SHS Development Team

