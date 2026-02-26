@echo off
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

echo 다운로드 undetected-chromedriver...
python -m pip install undetected-chromedriver -q
echo OK undetected-chromedriver

echo 다운로드 pyperclip...
python -m pip install pyperclip -q
echo OK pyperclip

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
set DESKTOP=%%USERPROFILE%%\Desktop
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%%DESKTOP%%\Worker PC %PC_NUM%.lnk'); $Shortcut.TargetPath = '%%CD%%\실행_Worker_PC%PC_NUM%.bat'; $Shortcut.WorkingDirectory = '%%CD%%'; $Shortcut.IconLocation = 'shell32.dll,14'; $Shortcut.Save()" 2>nul

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






