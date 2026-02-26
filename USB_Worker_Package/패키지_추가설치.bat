@echo off
chcp 65001 >nul
title 추가 패키지 설치

echo.
echo ============================================================
echo   undetected-chromedriver / pyperclip 설치
echo ============================================================
echo.

REM python 경로 자동 탐색
where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON=python
    goto :install
)

where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON=py
    goto :install
)

REM 일반 설치 경로 직접 탐색
for %%P in (
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe"
) do (
    if exist %%P (
        set PYTHON=%%P
        goto :install
    )
)

echo X Python을 찾을 수 없습니다.
echo   https://www.python.org/downloads/ 에서 Python을 설치하세요.
pause
exit /b 1

:install
echo OK Python 경로: %PYTHON%
echo.

echo [1/2] undetected-chromedriver 설치 중...
%PYTHON% -m pip install undetected-chromedriver --quiet
if errorlevel 1 (
    echo ! 설치 실패 - 다시 시도 중...
    %PYTHON% -m pip install undetected-chromedriver
) else (
    echo OK undetected-chromedriver 설치 완료
)

echo.
echo [2/2] pyperclip 설치 중...
%PYTHON% -m pip install pyperclip --quiet
if errorlevel 1 (
    echo ! 설치 실패 - 다시 시도 중...
    %PYTHON% -m pip install pyperclip
) else (
    echo OK pyperclip 설치 완료
)

echo.
echo ============================================================
echo   설치 완료! Worker Agent를 재시작하세요.
echo ============================================================
echo.
pause
