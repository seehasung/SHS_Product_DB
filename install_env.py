import os
import subprocess
import sys
import shlex

# 현재 작업 디렉토리
project_dir = os.getcwd()
venv_dir = os.path.join(project_dir, "venv")

# 1. 가상환경 생성
if not os.path.exists(venv_dir):
    subprocess.run([sys.executable, "-m", "venv", venv_dir])
    print(f"✅ 가상환경 생성 완료: {venv_dir}")
else:
    print(f"⚠️ 가상환경이 이미 존재합니다: {venv_dir}")

# 2. requirements.txt 생성
requirements = """
alembic==1.16.2
annotated-types==0.7.0
anyio==4.9.0
bcrypt==3.2.0
cffi==1.17.1
click==8.2.1
colorama==0.4.6
fastapi==0.115.14
greenlet==3.2.3
h11==0.16.0
idna==3.10
itsdangerous==2.2.0
Jinja2==3.1.6
Mako==1.3.10
MarkupSafe==3.0.2
passlib==1.7.4
pycparser==2.22
pydantic==2.11.7
pydantic_core==2.33.2
python-multipart==0.0.20
six==1.17.0
sniffio==1.3.1
SQLAlchemy==2.0.41
starlette==0.46.2
typing-inspection==0.4.1
typing_extensions==4.14.0
uvicorn==0.35.0
"""

with open("requirements.txt", "w", encoding="utf-8") as f:
    f.write(requirements.strip())

print("📄 requirements.txt 생성 완료")

# 3. pip 경로 설정 (Windows)
pip_path = os.path.join(venv_dir, "Scripts", "pip.exe")

# 4. 패키지 설치
result = subprocess.run([pip_path, "install", "-r", "requirements.txt"], text=True)
if result.returncode == 0:
    print("📦 패키지 설치 완료")
else:
    print("❌ 패키지 설치 실패")

# 5. 안내
activate_path = os.path.join(venv_dir, "Scripts", "activate.bat")
print(f"\n✅ 가상환경 활성화 명령어:\n\n    {activate_path}\n")
print("활성화 후 다음 명령으로 FastAPI 앱을 실행할 수 있습니다.")
print("    uvicorn main:app --reload")
