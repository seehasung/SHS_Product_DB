# 🚀 초간편 배포 가이드 (8대 PC)

단 **3단계**로 전체 시스템 배포 완료!

---

## 📦 준비물

- ✅ USB 메모리 1개
- ✅ 8대 PC (Windows 10/11)
- ✅ 네트워크 (인터넷 연결)

---

## 🎯 서버 배포 (5분)

### 1단계: 데이터베이스 생성

```bash
# 서버 SSH 접속
ssh user@scorp274.com

# 프로젝트 폴더로 이동
cd /path/to/SHS_Product_DB

# SQL 실행
psql -U username -d database_name -f migration_automation_system.sql
```

**예상 출력:**
```
✅ 자동화 시스템 테이블 생성 완료!
   - automation_worker_pcs
   - automation_accounts
   ...
```

### 2단계: 초기 데이터 설정

```bash
# 계정 파일 준비 (선택)
cp accounts.txt.sample accounts.txt
nano accounts.txt  # 실제 계정 정보 입력

# 초기화 스크립트 실행
python init_automation_data.py
```

**대화형으로 진행:**
```
1. PC 등록 → 자동 (8대)
2. 계정 등록 → 파일 선택 (accounts.txt)
3. 카페 등록 → 입력 또는 나중에
4. 프롬프트 → 예
```

### 3단계: 서버 재시작

```bash
sudo systemctl restart shs-product-db
```

**확인:**
```
https://scorp274.com/automation/cafe
```

✅ 서버 배포 완료!

---

## 🖥️ PC 배포 (PC당 3분, 총 24분)

### 준비: USB 패키지 생성 (서버에서)

```bash
# USB 패키지 생성
python prepare_usb_package.py

# ZIP 파일을 USB에 복사
cp USB_Worker_Package.zip /media/usb/
```

### PC #1~8 배포 (각 PC에서)

#### ✨ 원클릭 배포!

1. **USB 파일 복사** (30초)
   ```
   USB:\USB_Worker_Package를 C:\WorkerPC에 복사
   ```

2. **자동 설치 실행** (1분)
   ```
   install_worker.py 더블클릭
   
   → PC 번호 입력 (1~8)
   → 자동으로 모든 설정 완료!
   ```

3. **IP 설정** (1분)
   ```
   Win + R → ncpa.cpl
   이더넷 우클릭 → 속성 → IPv4
   
   PC #1: 192.168.1.101
   PC #2: 192.168.1.102
   PC #3: 192.168.1.103
   PC #4: 192.168.1.104
   PC #5: 192.168.1.105
   PC #6: 192.168.1.106
   PC #7: 192.168.1.107
   PC #8: 192.168.1.108
   
   서브넷: 255.255.255.0
   게이트웨이: 192.168.1.1
   DNS: 8.8.8.8
   ```

4. **실행** (즉시)
   ```
   바탕화면 "Worker PC #X" 아이콘 더블클릭!
   ```

✅ PC 배포 완료!

---

## ⚡ 빠른 IP 설정 (PowerShell)

관리자 권한으로 PowerShell 실행 후:

```powershell
# PC #1
New-NetIPAddress -InterfaceAlias "이더넷" -IPAddress 192.168.1.101 -PrefixLength 24 -DefaultGateway 192.168.1.1
Set-DnsClientServerAddress -InterfaceAlias "이더넷" -ServerAddresses ("8.8.8.8","8.8.4.4")

# PC #2
New-NetIPAddress -InterfaceAlias "이더넷" -IPAddress 192.168.1.102 -PrefixLength 24 -DefaultGateway 192.168.1.1
Set-DnsClientServerAddress -InterfaceAlias "이더넷" -ServerAddresses ("8.8.8.8","8.8.4.4")

# PC #3~8도 동일 (IP만 변경)
```

---

## 📋 체크리스트 (한눈에 확인)

### ☑️ 서버
- [ ] SQL 실행
- [ ] 초기 데이터 설정
- [ ] 서버 재시작
- [ ] 웹 접속 확인

### ☑️ 각 PC (1~8)
- [ ] USB 파일 복사
- [ ] install_worker.py 실행
- [ ] IP 설정
- [ ] Worker Agent 실행
- [ ] 서버에서 연결 확인

---

## 🎯 배포 시간표

| 단계 | 작업 | 소요 시간 |
|------|------|-----------|
| 1 | 서버 배포 | 5분 |
| 2 | USB 패키지 준비 | 2분 |
| 3 | PC #1 설정 | 3분 |
| 4 | PC #2 설정 | 3분 |
| 5 | PC #3 설정 | 3분 |
| 6 | PC #4 설정 | 3분 |
| 7 | PC #5 설정 | 3분 |
| 8 | PC #6 설정 | 3분 |
| 9 | PC #7 설정 | 3분 |
| 10 | PC #8 설정 | 3분 |
| 11 | 최종 확인 | 2분 |
| **합계** | | **약 35분** |

---

## 🔧 자동화 도구 모음

### 서버용
```bash
# 1. SQL 실행
psql -U username -d database_name -f migration_automation_system.sql

# 2. 초기 데이터
python init_automation_data.py

# 3. USB 패키지 생성
python prepare_usb_package.py

# 4. 서버 재시작
sudo systemctl restart shs-product-db
```

### PC용
```bash
# 1. 자동 설치
python install_worker.py

# 2. 테스트
python test_worker_setup.py

# 3. 실행 (바탕화면 아이콘 또는)
python worker_agent.py <PC번호>
```

---

## 💡 팁: 더 빠른 배포

### 방법 1: 첫 PC 완전 설정 → 복제

1. PC #1 완전 설정 (설치 + 설정)
2. 디스크 이미지 생성 (Clonezilla, Ghost)
3. 나머지 PC에 이미지 복원
4. 각 PC에서 IP만 변경 + install_worker.py 재실행 (PC 번호만 변경)

⏱️ **시간 단축: 35분 → 15분**

### 방법 2: 원격 배포 (PowerShell)

관리자 PC에서 원격으로 모든 PC 설정:

```powershell
# 8대 PC에 동시 배포
$pcs = 1..8
foreach ($pc in $pcs) {
    Invoke-Command -ComputerName "PC$pc" -ScriptBlock {
        cd C:\WorkerPC
        python install_worker.py --auto --pc-number $using:pc
    }
}
```

⏱️ **시간 단축: 35분 → 5분**

---

## 🎊 최종 확인

### 대시보드 접속
```
https://scorp274.com/automation/cafe
```

**확인 사항:**
```
✅ 8대 PC 모두 🟢 온라인
✅ 각 PC에 계정 할당됨
✅ CPU/메모리 사용률 표시
✅ 작업 대기 목록 비어있음 (정상)
```

### 테스트 작업 실행

1. 웹에서 테스트 스케줄 생성
2. 작업이 PC에 할당되는지 확인
3. 실제 카페에 글이 작성되는지 확인

---

## 🆘 긴급 상황 대응

### 전체 PC 재시작
각 PC에서:
```
Ctrl + C (Worker Agent 종료)
바탕화면 아이콘 다시 더블클릭
```

### 설정 초기화
```bash
# 설정 파일 삭제
del worker_config.json

# 재설치
python install_worker.py
```

### 서버 초기화
```bash
# 모든 작업 초기화 (주의!)
python init_automation_data.py --reset
```

---

## 📞 빠른 도움말

### 자주 묻는 질문

**Q: PC가 연결 안 돼요**  
A: Worker Agent 재실행, 네트워크 확인

**Q: 설치가 안 돼요**  
A: Python 버전 확인 (3.9+), 관리자 권한으로 실행

**Q: IP 설정을 잊었어요**  
A: IP설정가이드.txt 참고

**Q: 어떤 PC가 몇 번인지 헷갈려요**  
A: Worker Agent 콘솔 상단에 PC 번호 표시됨

---

## ✨ 결론

**초간편 3단계 배포:**

1. 🖥️ **서버** → SQL + 초기화 (5분)
2. 💿 **USB 준비** → 패키지 생성 (2분)  
3. 🖱️ **8대 PC** → 복사 + 클릭 + IP (24분)

**총 소요 시간: 약 30분!** ⚡

이제 8대 PC가 완벽하게 작동합니다! 🎉

