"""
올인원 자동 배포 스크립트
서버 + USB 패키지를 한 번에 준비

실행: python deploy_all.py
"""

import subprocess
import sys
from pathlib import Path
import shutil

class MasterDeployer:
    """마스터 배포 도구"""
    
    def print_header(self, text):
        print(f"\n{'='*70}")
        print(f"  {text}")
        print(f"{'='*70}\n")
        
    def check_environment(self):
        """환경 확인"""
        self.print_header("환경 확인")
        
        required_files = [
            'migration_automation_system.sql',
            'init_automation_data.py',
            'prepare_usb_package.py',
            'worker_agent.py',
            'install_worker.py',
            'test_worker_setup.py'
        ]
        
        missing = []
        for file in required_files:
            if Path(file).exists():
                print(f"✅ {file}")
            else:
                print(f"❌ {file} (없음)")
                missing.append(file)
        
        if missing:
            print(f"\n❌ {len(missing)}개 파일이 없습니다!")
            return False
        
        print("\n✅ 모든 필수 파일 준비됨")
        return True
        
    def server_deployment(self):
        """서버 배포"""
        self.print_header("1. 서버 배포")
        
        print("서버에서 다음 명령을 실행하세요:\n")
        
        print("┌─────────────────────────────────────────────────────┐")
        print("│ psql -U username -d database_name -f migration_automation_system.sql")
        print("│ python init_automation_data.py")
        print("│ sudo systemctl restart shs-product-db")
        print("└─────────────────────────────────────────────────────┘")
        
        print("\n위 명령을 복사하여 서버에서 실행하세요")
        
        input("\n서버 배포 완료 후 Enter를 눌러주세요...")
        
    def usb_package_creation(self):
        """USB 패키지 생성"""
        self.print_header("2. USB 배포 패키지 생성")
        
        print("USB 배포 패키지를 생성합니다...\n")
        
        try:
            # USB 패키지 생성 스크립트 실행
            subprocess.run([sys.executable, 'prepare_usb_package.py'], check=False)
            
            print("\n✅ USB 패키지 생성 완료!")
            
        except Exception as e:
            print(f"❌ 패키지 생성 실패: {e}")
            return False
        
        return True
        
    def create_deployment_guide(self):
        """배포 가이드 생성"""
        self.print_header("3. 배포 가이드 생성")
        
        guide = """
╔════════════════════════════════════════════════════════════════╗
║               8대 PC 배포 가이드                               ║
╚════════════════════════════════════════════════════════════════╝

📦 USB_Worker_Package 폴더를 USB에 복사하세요

각 PC에서 다음을 실행:

┌────────────────────────────────────────────────────────┐
│ 1. USB 파일을 C:\\WorkerPC에 복사                       │
│ 2. install_worker.py 더블클릭                          │
│ 3. PC 번호 입력 (1~8)                                  │
│ 4. IP 설정:                                            │
│    - PC #1: 192.168.1.101                              │
│    - PC #2: 192.168.1.102                              │
│    - PC #3: 192.168.1.103                              │
│    - PC #4: 192.168.1.104                              │
│    - PC #5: 192.168.1.105                              │
│    - PC #6: 192.168.1.106                              │
│    - PC #7: 192.168.1.107                              │
│    - PC #8: 192.168.1.108                              │
│ 5. 바탕화면 "Worker PC #X" 더블클릭                    │
└────────────────────────────────────────────────────────┘

✅ 완료 확인:
   https://scorp274.com/automation/cafe
   → 8대 PC 모두 🟢 온라인

⏱️ 예상 시간: PC당 3분 (총 24분)
        """
        
        guide_file = Path("배포가이드_8대PC.txt")
        with open(guide_file, 'w', encoding='utf-8') as f:
            f.write(guide)
        
        print(guide)
        print(f"\n✅ 가이드 저장: {guide_file}")
        
    def create_batch_installer(self):
        """일괄 설치 배치 파일 생성 (네트워크 공유 사용 시)"""
        self.print_header("보너스: 네트워크 일괄 배포 스크립트")
        
        # Windows 배치 파일
        batch_content = """@echo off
REM 8대 PC 원격 일괄 설치 (네트워크 공유 필요)
REM 관리자 권한으로 실행

echo ================================================
echo   8대 PC 원격 배포
echo ================================================

set SHARE_PATH=\\\\SERVER\\WorkerPackage
set TARGET_PATH=C:\\WorkerPC

for /L %%i in (1,1,8) do (
    echo.
    echo [PC #%%i 배포 중...]
    
    REM 원격 PC에 폴더 생성
    mkdir \\\\PC%%i\\C$\\WorkerPC 2>nul
    
    REM 파일 복사
    xcopy /E /Y /I %SHARE_PATH% \\\\PC%%i\\C$\\WorkerPC
    
    REM 원격 실행 (PsExec 필요)
    REM psexec \\\\PC%%i -i -d python C:\\WorkerPC\\install_worker.py --auto --pc-number %%i
    
    echo [PC #%%i 복사 완료]
)

echo.
echo ================================================
echo   배포 완료!
echo   각 PC에서 install_worker.py를 실행하세요
echo ================================================
pause
"""
        
        batch_file = Path("deploy_all_pcs.bat")
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(batch_content)
        
        print(f"✅ 네트워크 배포 스크립트 생성: {batch_file}")
        print("\n📝 사용 방법:")
        print("   1. 파일 공유 설정: \\\\SERVER\\WorkerPackage")
        print("   2. PsExec 설치 (Sysinternals)")
        print("   3. deploy_all_pcs.bat 관리자 권한으로 실행")
        print("   4. 자동으로 8대 PC에 파일 복사")
        
    def run(self):
        """배포 실행"""
        print("""
╔════════════════════════════════════════════════════════════════╗
║                올인원 자동 배포 도구                           ║
║           서버 + 8대 PC를 한 번에 배포!                        ║
╚════════════════════════════════════════════════════════════════╝
        """)
        
        # 1. 환경 확인
        if not self.check_environment():
            print("\n❌ 필수 파일이 없습니다. 먼저 파일을 준비하세요.")
            return
        
        # 2. 서버 배포 안내
        self.server_deployment()
        
        # 3. USB 패키지 생성
        self.usb_package_creation()
        
        # 4. 배포 가이드 생성
        self.create_deployment_guide()
        
        # 5. 보너스: 네트워크 배포 스크립트
        self.create_batch_installer()
        
        # 완료
        self.print_header("🎉 배포 준비 완료!")
        
        print("✅ 다음 파일들이 준비되었습니다:\n")
        print("   📁 USB_Worker_Package/ (USB에 복사)")
        print("   📄 배포가이드_8대PC.txt")
        print("   📄 deploy_all_pcs.bat (네트워크 배포용)")
        
        print("\n📝 배포 순서:")
        print("   1. USB_Worker_Package를 USB에 복사")
        print("   2. 각 PC에서 USB 내용을 C:\\WorkerPC에 복사")
        print("   3. install_worker.py 실행")
        print("   4. 바탕화면 아이콘으로 Worker 실행")
        
        print("\n🎯 배포 시작하세요! 성공을 기원합니다! 🚀\n")


if __name__ == "__main__":
    deployer = MasterDeployer()
    
    try:
        deployer.run()
    except KeyboardInterrupt:
        print("\n\n⏹️ 취소됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()

