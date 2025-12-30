"""
USB 배포 패키지 생성 스크립트
8대 PC에 쉽게 배포하기 위한 패키지 생성

실행: python prepare_usb_package.py
"""

import os
import shutil
from pathlib import Path
import zipfile

def create_usb_package():
    """USB 배포용 패키지 생성"""
    
    print("""
╔════════════════════════════════════════════════════════╗
║     USB 배포 패키지 생성                               ║
║     8대 PC에 한 번에 배포!                             ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 패키지 폴더 생성
    package_dir = Path("USB_Worker_Package")
    
    if package_dir.exists():
        print("⚠️  기존 패키지 폴더가 있습니다. 삭제하고 다시 생성합니다.")
        shutil.rmtree(package_dir)
    
    package_dir.mkdir()
    print(f"📁 패키지 폴더 생성: {package_dir}")
    
    # 필수 파일 복사
    files_to_copy = [
        'worker_agent.py',
        'install_worker.py',
        'test_worker_setup.py'
    ]
    
    print("\n📋 파일 복사 중...")
    
    for file in files_to_copy:
        if Path(file).exists():
            shutil.copy(file, package_dir / file)
            print(f"  ✅ {file}")
        else:
            print(f"  ⚠️  {file} (없음 - 건너뜀)")
    
    # requirements.txt 생성
    requirements_content = """selenium==4.15.2
websockets==12.0
psutil==5.9.6
requests==2.31.0
webdriver-manager==4.0.1
"""
    
    with open(package_dir / 'requirements.txt', 'w') as f:
        f.write(requirements_content)
    print(f"  ✅ requirements.txt")
    
    # README 생성
    readme_content = """# Worker Agent 배포 패키지

## 🚀 빠른 시작 (3단계)

### 1단계: 설치
```
install_worker.py를 더블클릭하세요
```

### 2단계: IP 설정
PC 번호에 맞춰 IP를 설정하세요:
- PC #1: 192.168.1.101
- PC #2: 192.168.1.102
- PC #3: 192.168.1.103
- PC #4: 192.168.1.104
- PC #5: 192.168.1.105
- PC #6: 192.168.1.106
- PC #7: 192.168.1.107
- PC #8: 192.168.1.108

### 3단계: 실행
바탕화면의 "Worker PC #X" 아이콘을 더블클릭하세요!

## 📞 문제 발생 시
test_worker_setup.py를 실행하여 문제를 진단하세요
```

    with open(package_dir / 'README.txt', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"  ✅ README.txt")
    
    # IP 설정 가이드 생성 (이미지로)
    ip_guide_content = """# IP 설정 빠른 가이드

## Windows 10/11

1. Win + R 키를 누르세요
2. ncpa.cpl 입력 후 Enter
3. 이더넷 연결 우클릭 → 속성
4. "Internet Protocol Version 4" 선택 → 속성
5. "다음 IP 주소 사용" 선택
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
기본 설정 DNS 서버: 8.8.8.8
보조 DNS 서버: 8.8.4.4

7. 확인 → 확인

## IP 변경 확인

명령 프롬프트(cmd)를 열고:
```
ipconfig
```

이더넷 어댑터의 IPv4 주소가 설정한 IP와 같은지 확인!
"""
    
    with open(package_dir / 'IP설정가이드.txt', 'w', encoding='utf-8') as f:
        f.write(ip_guide_content)
    print(f"  ✅ IP설정가이드.txt")
    
    # 8대 PC용 빠른 실행 가이드
    quick_guide = """# 🚀 8대 PC 빠른 배포 가이드

## 준비물
- USB 메모리 (이 패키지 복사)
- 8대 PC
- 네트워크 연결

## 단계별 진행 (PC당 5분)

### PC #1
1. USB의 모든 파일을 C:\\WorkerPC에 복사
2. install_worker.py 더블클릭
3. PC 번호 1 입력
4. IP를 192.168.1.101로 설정
5. 바탕화면 아이콘 더블클릭
6. 서버에서 연결 확인

### PC #2
1. USB의 모든 파일을 C:\\WorkerPC에 복사
2. install_worker.py 더블클릭
3. PC 번호 2 입력
4. IP를 192.168.1.102로 설정
5. 바탕화면 아이콘 더블클릭
6. 서버에서 연결 확인

### PC #3 ~ #8 (동일)
같은 과정 반복, PC 번호와 IP만 변경

## ⏱️ 총 소요 시간: 약 40분

## ✅ 완료 확인
서버 대시보드 접속:
https://scorp274.com/automation/cafe

8대 PC 모두 🟢 온라인 표시 확인!
"""
    
    with open(package_dir / '빠른배포가이드.txt', 'w', encoding='utf-8') as f:
        f.write(quick_guide)
    print(f"  ✅ 빠른배포가이드.txt")
    
    # 완료
    print("\n" + "="*60)
    print("✅ USB 배포 패키지 생성 완료!")
    print("="*60)
    print(f"\n📦 패키지 위치: {package_dir.absolute()}")
    print(f"\n📝 포함된 파일:")
    for file in package_dir.iterdir():
        print(f"   - {file.name}")
    
    print(f"\n💡 사용 방법:")
    print(f"   1. '{package_dir}' 폴더를 USB에 복사")
    print(f"   2. 각 PC에서 USB 내용을 C:\\WorkerPC에 복사")
    print(f"   3. install_worker.py 실행")
    print(f"\n🎯 8대 PC에 한 번에 배포 완료!")
    
    # ZIP 파일도 생성 (옵션)
    create_zip = input("\nZIP 파일로도 생성하시겠습니까? (y/n): ").strip().lower() == 'y'
    
    if create_zip:
        zip_file = Path(f"{package_dir.name}.zip")
        
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in package_dir.rglob('*'):
                if file.is_file():
                    zipf.write(file, file.relative_to(package_dir.parent))
        
        print(f"\n✅ ZIP 파일 생성: {zip_file.absolute()}")
        print(f"   파일 크기: {zip_file.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    try:
        create_usb_package()
    except KeyboardInterrupt:
        print("\n\n⏹️ 취소됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()

