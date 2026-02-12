# 🔐 Worker PC 자동 로그인 가이드

## ✨ 새로운 기능

Worker 프로그램이 **시작 시 자동으로 네이버에 로그인**합니다!

### 🎯 주요 개선사항

1. ✅ **프로그램 시작 시 자동 로그인**
   - 서버에서 해당 PC에 할당된 계정 정보 자동 조회
   - 네이버 로그인 자동 수행
   - 로그인 성공 시 네이버 홈 탭 유지

2. ✅ **로그인 세션 지속**
   - 네이버 홈 탭을 닫지 않고 유지
   - 작업 신호가 오면 새 탭에서 작업 수행
   - 작업 완료 후 홈 탭으로 복귀

3. ✅ **빠른 작업 시작**
   - 작업 신호 수신 시 로그인 없이 바로 작업 시작
   - 불필요한 로그인 과정 제거로 시간 절약

---

## 🚀 사용 방법

### 1️⃣ 서버에서 계정 할당

먼저 https://scorp274.com/automation/cafe 에서 **설정 > 계정 관리**로 이동:

1. 네이버 계정 추가
2. 각 계정을 Worker PC에 할당 (PC #1, #2, #3 등)

### 2️⃣ Worker PC에서 프로그램 실행

```bash
cd C:\worker
python worker_agent.py 1
```

### 3️⃣ 자동 로그인 확인

프로그램 실행 시 다음과 같이 표시됩니다:

```
============================================================
🔐 네이버 자동 로그인 시작
============================================================
🔍 계정 정보 조회 중...
✅ 계정 정보 조회 성공: your_account@naver.com
📋 할당된 계정: your_account@naver.com
🚀 로그인 시도 중...
🔐 네이버 로그인 시도: your_account@naver.com
✅ your_account@naver.com 로그인 성공!
✅ your_account@naver.com 로그인 완료!
🏠 네이버 홈 탭 유지 (이 탭은 닫지 마세요)
============================================================

✅ PC #1 서버 연결 성공: wss://scorp274.com/automation/ws/worker/1
✅ Worker 준비 완료! 작업 대기 중...
```

---

## 🔧 API 변경사항

### 새로운 API 엔드포인트

**`GET /automation/api/pcs/{pc_number}/account`**

PC 번호로 해당 PC에 할당된 계정 정보를 조회합니다.

**요청 예시:**
```
GET https://scorp274.com/automation/api/pcs/1/account
```

**응답 예시:**
```json
{
  "success": true,
  "account": {
    "id": 1,
    "account_id": "your_account@naver.com",
    "account_pw": "encrypted_password",
    "status": "active"
  },
  "pc": {
    "id": 1,
    "pc_number": 1,
    "pc_name": "Worker PC #1"
  }
}
```

---

## 📝 코드 변경사항

### 1. `routers/automation.py`

새로운 API 엔드포인트 추가:
```python
@router.get("/api/pcs/{pc_number}/account")
async def get_pc_account(pc_number: int, db: Session = Depends(get_db)):
    """PC에 할당된 계정 정보 조회"""
```

### 2. `worker_agent.py`

**새 메서드 추가:**
```python
def get_my_account_from_server(self) -> Optional[Dict]:
    """서버에서 내 PC에 할당된 계정 정보 가져오기"""
```

**`run()` 메서드 수정:**
- Selenium 초기화 후 자동 로그인 수행
- 로그인 성공 시 네이버 홈 탭 유지
- 서버 연결 및 작업 대기

---

## ⚠️ 주의사항

1. **계정 할당 필수**
   - 서버에서 PC에 계정이 할당되지 않으면 자동 로그인되지 않습니다
   - https://scorp274.com/automation/cafe 에서 계정을 할당해주세요

2. **네이버 홈 탭 유지**
   - 로그인 후 네이버 홈 탭은 자동으로 닫히지 않습니다
   - 이 탭을 수동으로 닫으면 안 됩니다!
   - 모든 작업은 새 탭에서 수행되고, 완료 후 홈 탭으로 복귀합니다

3. **CAPTCHA 발생 시**
   - 자동 로그인 실패 시 수동 로그인 안내가 표시됩니다
   - 브라우저에서 수동으로 로그인 후 Enter 키를 누르면 계속 진행됩니다

---

## 🎉 장점

✅ **시간 절약**: 작업마다 로그인하지 않아도 됨  
✅ **사용자 경험 개선**: 프로그램 시작만 하면 모든 준비 완료  
✅ **안정성 향상**: 로그인 세션을 지속적으로 유지  
✅ **자동화 강화**: 사람 개입 최소화

---

## 📞 문제 해결

### "PC에 할당된 계정이 없습니다" 메시지가 뜨는 경우

1. https://scorp274.com/automation/cafe 접속
2. **설정 > 계정 관리** 메뉴로 이동
3. 계정 추가 및 PC 할당

### 로그인 실패 시

1. **CAPTCHA 확인**: 브라우저에 CAPTCHA가 표시되는지 확인
2. **수동 로그인**: 안내에 따라 브라우저에서 수동으로 로그인
3. **계정 확인**: 계정 ID/PW가 정확한지 서버에서 확인

### 서버 연결 실패 시

1. 인터넷 연결 확인
2. https://scorp274.com 접속 가능한지 확인
3. 방화벽 설정 확인

---

## 🔄 업데이트 방법

Worker PC는 자동 업데이트됩니다!

1. **자동 업데이트 (권장)**
   - 프로그램 실행 시 자동으로 최신 버전 확인
   - 새 버전 발견 시 자동 다운로드 및 재시작

2. **수동 업데이트**
   - 최신 `worker_agent.py`를 `C:\worker\`에 복사
   - 프로그램 재실행

---

**✨ 이제 Worker PC를 실행하기만 하면 모든 준비가 완료됩니다! 🎊**
