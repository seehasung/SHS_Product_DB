# 🖥️ 작업 PC 설정 가이드

## 📋 목차
1. [PC 준비사항](#pc-준비사항)
2. [단계별 설정](#단계별-설정)
3. [자동 시작 설정](#자동-시작-설정)
4. [테스트 및 검증](#테스트-및-검증)

---

## PC 준비사항

### 💻 최소 사양
- **OS:** Windows 10/11, macOS, Linux
- **CPU:** 2코어 이상
- **RAM:** 4GB 이상 (8GB 권장)
- **저장공간:** 10GB 이상 여유 공간
- **네트워크:** 안정적인 인터넷 연결 (유선 권장)

### 📌 필수 소프트웨어
- ✅ Python 3.9 이상
- ✅ Google Chrome 브라우저
- ✅ 고정 IP 설정

---

## 단계별 설정

### 1️⃣ Python 설치

#### Windows:
```bash
# 1. https://www.python.org/downloads/ 접속
# 2. Python 3.11 다운로드
# 3. 설치 시 "Add Python to PATH" 체크 필수!
```

설치 확인:
```bash
python --version
# Python 3.11.x 출력되면 성공
```

#### macOS:
```bash
brew install python@3.11
```

#### Linux (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install python3.11 python3-pip
```

---

### 2️⃣ 고정 IP 설정

**중요:** 각 PC는 고유한 IP를 사용해야 합니다!

#### Windows 고정 IP 설정:

1. **제어판** 열기
   ```
   Win + R → ncpa.cpl 입력 → Enter
   ```

2. **이더넷 연결** 우클릭 → **속성**

3. **Internet Protocol Version 4 (TCP/IPv4)** 선택 → **속성**

4. **다음 IP 주소 사용** 선택:
   ```
   PC #1:
   - IP 주소: 192.168.1.101
   - 서브넷 마스크: 255.255.255.0
   - 기본 게이트웨이: 192.168.1.1
   - DNS: 8.8.8.8, 8.8.4.4
   
   PC #2:
   - IP 주소: 192.168.1.102
   - 서브넷 마스크: 255.255.255.0
   - 기본 게이트웨이: 192.168.1.1
   - DNS: 8.8.8.8, 8.8.4.4
   
   PC #3:
   - IP 주소: 192.168.1.103
   ...
   ```

5. **확인** 클릭

#### IP 확인:
```bash
# Windows
ipconfig

# macOS/Linux
ifconfig
```

---

### 3️⃣ Chrome 설치

```
https://www.google.com/chrome/
```

설치 후 한 번 실행하여 초기 설정 완료

---

### 4️⃣ 프로젝트 파일 복사

각 PC에 다음 파일들을 복사:

```
작업PC/
├── worker_agent.py          # Worker Agent 프로그램
├── test_worker_setup.py     # 설정 테스트 스크립트
└── requirements-worker.txt  # 필수 패키지 목록
```

#### requirements-worker.txt 내용:
```txt
selenium==4.15.2
websockets==12.0
psutil==5.9.6
requests==2.31.0
webdriver-manager==4.0.1
```

---

### 5️⃣ 패키지 설치

```bash
# 프로젝트 폴더로 이동
cd C:\WorkerPC

# 필수 패키지 설치
pip install -r requirements-worker.txt

# 또는 개별 설치
pip install selenium websockets psutil requests webdriver-manager
```

---

### 6️⃣ 설정 테스트

```bash
python test_worker_setup.py
```

**예상 출력:**
```
╔════════════════════════════════════════════════════════╗
║     Worker PC 설정 테스트                              ║
║     네이버 카페 자동화 시스템                           ║
╚════════════════════════════════════════════════════════╝

============================================================
  Python 버전 확인
============================================================

🐍 Python 버전 확인...
✅ Python 3.11.5 (OK)

📦 필수 패키지 확인...
✅ Selenium
✅ WebSockets
✅ PSUtil
✅ Requests

🌐 Chrome 브라우저 확인...
✅ Chrome 발견: C:\Program Files\Google\Chrome\Application\chrome.exe

🌐 네트워크 확인...
✅ 로컬 IP: 192.168.1.101
✅ 인터넷 연결 정상

💻 시스템 리소스 확인...
✅ CPU 코어: 8개
✅ 메모리: 16.0GB
✅ 디스크 여유 공간: 250.5GB

📄 Worker Agent 파일 확인...
✅ worker_agent.py 파일 존재

🔌 서버 연결 테스트...
✅ 서버 연결 성공: scorp274.com

============================================================
  테스트 결과 요약
============================================================

전체: 7개
성공: 7개
실패: 0개

✅ 모든 테스트 통과!

Worker Agent를 실행할 준비가 되었습니다.

실행 방법:
   python worker_agent.py <PC번호>

예:
   python worker_agent.py 1
```

---

### 7️⃣ Worker Agent 실행

#### 수동 실행:

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

#### 실행 확인:
```
╔════════════════════════════════════════════════════════╗
║     네이버 카페 자동화 Worker Agent v1.0              ║
║                                                        ║
║     PC 번호: 01                                        ║
║     서버: scorp274.com                                 ║
╚════════════════════════════════════════════════════════╝

🚀 Selenium 브라우저 초기화 중...
✅ 브라우저 준비 완료
✅ PC #1 서버 연결 성공: wss://scorp274.com/automation/ws/worker/1
✅ Worker 준비 완료! 작업 대기 중...
```

---

## 자동 시작 설정

PC 부팅 시 Worker Agent를 자동으로 실행하도록 설정

### Windows - 작업 스케줄러

1. **작업 스케줄러** 실행
   ```
   Win + R → taskschd.msc → Enter
   ```

2. **우측 패널** → **기본 작업 만들기** 클릭

3. **기본 작업 만들기 마법사:**

   - **이름:** `Worker Agent PC1`
   - **설명:** `네이버 카페 자동화 Worker PC #1`
   - **다음** 클릭

4. **트리거:**
   - **컴퓨터 시작 시** 선택
   - **다음** 클릭

5. **동작:**
   - **프로그램 시작** 선택
   - **다음** 클릭

6. **프로그램/스크립트:**
   ```
   프로그램/스크립트: C:\Users\YourName\AppData\Local\Programs\Python\Python311\python.exe
   
   인수 추가: C:\WorkerPC\worker_agent.py 1
   
   시작 위치: C:\WorkerPC
   ```

7. **마침** 클릭

8. **고급 설정 (선택사항):**
   - 작업 우클릭 → **속성**
   - **최고 권한으로 실행** 체크
   - **확인**

### macOS - LaunchAgent

1. plist 파일 생성:
```bash
nano ~/Library/LaunchAgents/com.scorp.worker.plist
```

2. 내용 입력:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.scorp.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YourName/WorkerPC/worker_agent.py</string>
        <string>1</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

3. 등록:
```bash
launchctl load ~/Library/LaunchAgents/com.scorp.worker.plist
```

### Linux - systemd

1. 서비스 파일 생성:
```bash
sudo nano /etc/systemd/system/worker-agent.service
```

2. 내용 입력:
```ini
[Unit]
Description=Naver Cafe Automation Worker Agent
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/WorkerPC
ExecStart=/usr/bin/python3 /home/youruser/WorkerPC/worker_agent.py 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. 서비스 등록 및 시작:
```bash
sudo systemctl daemon-reload
sudo systemctl enable worker-agent
sudo systemctl start worker-agent

# 상태 확인
sudo systemctl status worker-agent
```

---

## 테스트 및 검증

### 1. 연결 확인

서버 대시보드에서 확인:
```
https://scorp274.com/automation/cafe
```

PC 상태가 **🟢 온라인**으로 표시되어야 함

### 2. 로그 확인

Worker Agent 콘솔에서 다음 메시지 확인:
```
✅ PC #1 서버 연결 성공
✅ Worker 준비 완료! 작업 대기 중...
```

### 3. 테스트 작업 실행

서버에서 간단한 테스트 작업 할당:
1. 계정 등록
2. 카페 등록  
3. 휴먼 모드 스케줄 생성
4. 작업 할당 확인

---

## ❓ 문제 해결

### PC가 오프라인으로 표시됨

**확인 사항:**
1. Worker Agent 실행 중인지 확인
2. 네트워크 연결 상태
3. 방화벽 설정 (WebSocket 포트 허용)

**해결:**
```bash
# Worker Agent 재시작
python worker_agent.py <PC번호>
```

### 패키지 설치 오류

**해결:**
```bash
# pip 업그레이드
python -m pip install --upgrade pip

# 패키지 재설치
pip install --force-reinstall selenium websockets psutil requests webdriver-manager
```

### Chrome 드라이버 오류

**해결:**
```bash
# webdriver-manager 재설치
pip install --upgrade webdriver-manager

# 수동 다운로드
# https://chromedriver.chromium.org/downloads
```

### 서버 연결 실패

**확인:**
1. 서버 URL 확인: `scorp274.com`
2. 인터넷 연결 상태
3. 방화벽/안티바이러스 설정

**테스트:**
```bash
# 서버 접속 테스트
ping scorp274.com

# 브라우저에서
https://scorp274.com
```

---

## 📝 체크리스트

### 초기 설정
- [ ] Python 3.9+ 설치
- [ ] Chrome 브라우저 설치
- [ ] 고정 IP 설정 (PC별 고유 IP)
- [ ] 프로젝트 파일 복사
- [ ] 필수 패키지 설치
- [ ] 설정 테스트 통과

### 운영 준비
- [ ] Worker Agent 정상 실행
- [ ] 서버 연결 확인 (대시보드)
- [ ] 자동 시작 설정 (선택)
- [ ] 계정 등록 (서버)
- [ ] 테스트 작업 성공

---

## 🎓 추가 정보

### 로그 파일 위치
- Windows: `C:\WorkerPC\logs\worker.log`
- macOS/Linux: `~/WorkerPC/logs/worker.log`

### 업데이트 방법
```bash
# 최신 worker_agent.py 다운로드
# 기존 파일 백업
cp worker_agent.py worker_agent.py.backup

# 새 파일로 교체
# Worker Agent 재시작
```

### 성능 모니터링
```bash
# CPU/메모리 사용률 확인
# Windows: 작업 관리자
# macOS: Activity Monitor
# Linux: htop
```

---

**마지막 업데이트:** 2025-12-30  
**버전:** 1.0

