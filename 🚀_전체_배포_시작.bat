@echo off
chcp 65001 >nul
title 자동화 시스템 전체 배포

echo ╔════════════════════════════════════════════════════════╗
echo ║     네이버 카페 자동화 시스템                          ║
echo ║     올인원 자동 배포 도구                              ║
echo ╔════════════════════════════════════════════════════════╝
echo.

echo 이 스크립트는 다음 작업을 자동으로 수행합니다:
echo.
echo   ✅ 1. 환경 확인
echo   ✅ 2. USB 배포 패키지 생성
echo   ✅ 3. 배포 가이드 생성
echo   ✅ 4. 준비 완료!
echo.

pause

echo.
echo ================================================
echo   배포 준비 시작...
echo ================================================
echo.

REM Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python이 설치되지 않았습니다!
    echo    https://www.python.org/downloads/ 에서 설치하세요
    pause
    exit /b 1
)

echo ✅ Python 확인 완료
echo.

REM 배포 스크립트 실행
echo 📦 배포 패키지 생성 중...
python deploy_all.py

echo.
echo ================================================
echo   배포 준비 완료!
echo ================================================
echo.

echo 📁 USB_Worker_Package 폴더를 USB에 복사하세요
echo 📄 배포가이드_8대PC.txt를 참고하세요
echo.

echo 💡 다음 단계:
echo    1. USB에 USB_Worker_Package 복사
echo    2. 서버에서 SQL 및 초기화 실행
echo    3. 8대 PC에 배포
echo.

explorer USB_Worker_Package

pause


