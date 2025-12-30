"""
USB 배포 패키지 생성 스크립트
8대 PC에 쉽게 배포하기 위한 패키지 생성

실행: python prepare_usb_package.py
"""

import os
import shutil
from pathlib import Path

def create_usb_package():
    """USB 배포용 패키지 생성"""
    
    print("\n" + "="*60)
    print("     USB 배포 패키지 생성")
    print("     8대 PC에 한 번에 배포!")
    print("="*60 + "\n")
    
    # 패키지 폴더 생성
    package_dir = Path("USB_Worker_Package")
    
    if package_dir.exists():
        print("기존 패키지 폴더가 있습니다. 삭제하고 다시 생성합니다.")
        shutil.rmtree(package_dir)
    
    package_dir.mkdir()
    print(f"폴더 생성: {package_dir}\n")
    
    # 필수 파일 복사
    files_to_copy = [
        'worker_agent.py',
        'install_worker.py',
        'test_worker_setup.py',
        'worker_auto_install.py'
    ]
    
    print("파일 복사 중...\n")
    
    for file in files_to_copy:
        if Path(file).exists():
            shutil.copy(file, package_dir / file)
            print(f"  OK {file}")
        else:
            print(f"  SKIP {file} (파일 없음)")
    
    # 원클릭 설치 배치 파일 생성
    batch_content = """@echo off
chcp 65001 >nul
title Worker Agent 원클릭 설치

cls
echo.
echo ============================================================
echo.
echo      Worker Agent 원클릭 자동 설치
echo.
echo      모든 것을 자동으로 설치합니다!
echo.
echo ============================================================
echo.
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo X Python이 설치되지 않았습니다!
    echo.
    echo https://www.python.org/downloads/
    echo 위 사이트에서 Python을 설치하세요
    echo.
    pause
    exit /b 1
)

echo OK Python 확인 완료
python --version
echo.
echo.

echo ============================================================
echo   필수 패키지 자동 설치 중...
echo ============================================================
echo.

echo 다운로드 selenium...
python -m pip install selenium -q
echo OK selenium

echo 다운로드 websockets...
python -m pip install websockets -q
echo OK websockets

echo 다운로드 psutil...
python -m pip install psutil -q
echo OK psutil

echo 다운로드 requests...
python -m pip install requests -q
echo OK requests

echo 다운로드 webdriver-manager...
python -m pip install webdriver-manager -q
echo OK webdriver-manager

echo.
echo OK 모든 패키지 설치 완료!
echo.
echo.

echo ============================================================
echo   Worker 설정
echo ============================================================
echo.

set /p PC_NUM="PC 번호 (1-8): "

if "%PC_NUM%"=="" (
    echo X PC 번호를 입력하세요
    pause
    exit /b 1
)

echo.
echo OK PC #%PC_NUM% 로 설정됨
echo.

REM 실행 배치 파일 생성
(
echo @echo off
echo chcp 65001 ^>nul
echo title Worker Agent PC #%PC_NUM%
echo cd /d "%%~dp0"
echo python worker_agent.py %PC_NUM%
echo pause
) > "실행_Worker_PC%PC_NUM%.bat"

echo OK 실행 파일 생성
echo.

REM 바탕화면 바로가기 생성
set DESKTOP=%%USERPROFILE%%\\Desktop
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%%DESKTOP%%\\Worker PC %PC_NUM%.lnk'); $Shortcut.TargetPath = '%%CD%%\\실행_Worker_PC%PC_NUM%.bat'; $Shortcut.WorkingDirectory = '%%CD%%'; $Shortcut.IconLocation = 'shell32.dll,14'; $Shortcut.Save()" 2>nul

if errorlevel 1 (
    echo ! 바탕화면 바로가기 생성 실패
) else (
    echo OK 바탕화면 바로가기 생성
)

echo.
echo.
echo ============================================================
echo.
echo      OK 설치 완료!
echo.
echo ============================================================
echo.
echo 다음 단계:
echo    1. VPN 연결 (각 PC마다 다른 서버)
echo    2. 바탕화면 'Worker PC %PC_NUM%' 더블클릭
echo    3. https://scorp274.com/automation/cafe 에서 확인
echo.
echo.

set /p RUN_NOW="지금 바로 실행하시겠습니까? (y/n): "

if /i "%%RUN_NOW%%"=="y" (
    echo.
    echo Worker Agent 시작 중...
    echo.
    python worker_agent.py %PC_NUM%
) else (
    echo.
    echo 바탕화면 'Worker PC %PC_NUM%' 아이콘을 더블클릭하세요!
    echo.
    pause
)
"""
    
    with open(package_dir / '원클릭_설치.bat', 'w', encoding='utf-8') as f:
        f.write(batch_content)
    print(f"  OK 원클릭_설치.bat")
    
    # requirements.txt 생성
    requirements_content = """selenium==4.15.2
websockets==12.0
psutil==5.9.6
requests==2.31.0
webdriver-manager==4.0.1
"""
    
    with open(package_dir / 'requirements.txt', 'w', encoding='utf-8') as f:
        f.write(requirements_content)
    print(f"  OK requirements.txt")
    
    # README 생성
    readme_content = """Worker Agent 배포 패키지

=== 빠른 시작 ===

1단계: 설치
  install_worker.py를 더블클릭하세요

2단계: IP 설정
  PC 번호에 맞춰 IP를 설정하세요:
  - PC #1: 192.168.1.101
  - PC #2: 192.168.1.102
  - PC #3: 192.168.1.103
  - PC #4: 192.168.1.104
  - PC #5: 192.168.1.105
  - PC #6: 192.168.1.106
  - PC #7: 192.168.1.107
  - PC #8: 192.168.1.108

3단계: 실행
  바탕화면의 "Worker PC #X" 아이콘을 더블클릭하세요!

=== 문제 발생 시 ===
test_worker_setup.py를 실행하여 문제를 진단하세요
"""
    
    with open(package_dir / 'README.txt', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"  OK README.txt")
    
    # IP 설정 가이드
    ip_guide = """IP 설정 빠른 가이드

Windows 10/11:

1. Win + R 키를 누르세요
2. ncpa.cpl 입력 후 Enter
3. 이더넷 연결 우클릭 > 속성
4. Internet Protocol Version 4 선택 > 속성
5. 다음 IP 주소 사용 선택
6. PC 번호에 맞춰 입력:

PC #1: 192.168.1.101
PC #2: 192.168.1.102
PC #3: 192.168.1.103
PC #4: 192.168.1.104
PC #5: 192.168.1.105
PC #6: 192.168.1.106
PC #7: 192.168.1.107
PC #8: 192.168.1.108

서브넷 마스크: 255.255.255.0
기본 게이트웨이: 192.168.1.1
DNS 서버: 8.8.8.8
보조 DNS: 8.8.4.4

7. 확인 > 확인

IP 변경 확인:
cmd 열고 ipconfig 입력
"""
    
    with open(package_dir / 'IP설정가이드.txt', 'w', encoding='utf-8') as f:
        f.write(ip_guide)
    print(f"  OK IP설정가이드.txt")
    
    # 빠른 배포 가이드
    quick_guide = """8대 PC 빠른 배포 가이드

=== 단계별 진행 (PC당 5분) ===

PC #1:
1. USB의 모든 파일을 C:\\WorkerPC에 복사
2. install_worker.py 더블클릭
3. PC 번호 1 입력
4. IP를 192.168.1.101로 설정
5. 바탕화면 아이콘 더블클릭
6. 서버에서 연결 확인

PC #2:
1. USB의 모든 파일을 C:\\WorkerPC에 복사
2. install_worker.py 더블클릭
3. PC 번호 2 입력
4. IP를 192.168.1.102로 설정
5. 바탕화면 아이콘 더블클릭
6. 서버에서 연결 확인

PC #3 ~ #8 (동일):
같은 과정 반복, PC 번호와 IP만 변경

=== 총 소요 시간: 약 40분 ===

=== 완료 확인 ===
서버 대시보드 접속:
https://scorp274.com/automation/cafe

8대 PC 모두 온라인 표시 확인!
"""
    
    with open(package_dir / '빠른배포가이드.txt', 'w', encoding='utf-8') as f:
        f.write(quick_guide)
    print(f"  OK 빠른배포가이드.txt")
    
    # 완료
    print("\n" + "="*60)
    print("USB 배포 패키지 생성 완료!")
    print("="*60)
    print(f"\n패키지 위치: {package_dir.absolute()}")
    print(f"\n포함된 파일:")
    for file in package_dir.iterdir():
        print(f"   - {file.name}")
    
    print(f"\n사용 방법:")
    print(f"   1. '{package_dir}' 폴더를 USB에 복사")
    print(f"   2. 각 PC에서 USB 내용을 C:\\WorkerPC에 복사")
    print(f"   3. install_worker.py 실행")
    print(f"\n8대 PC에 한 번에 배포 완료!\n")


if __name__ == "__main__":
    try:
        create_usb_package()
    except KeyboardInterrupt:
        print("\n취소됨")
    except Exception as e:
        print(f"\n오류: {e}")
        import traceback
        traceback.print_exc()
