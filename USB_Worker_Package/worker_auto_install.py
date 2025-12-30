"""
Worker Agent 올인원 자동 설치 프로그램
모든 것을 자동으로 다운로드하고 설치합니다

실행: python worker_auto_install.py
"""

import subprocess
import sys
import os
import urllib.request
import json
from pathlib import Path
import platform

class AutoInstaller:
    """자동 설치 프로그램"""
    
    def __init__(self):
        self.install_dir = Path.cwd()
        self.server_url = "https://scorp274.com"
        
    def print_header(self, text):
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}\n")
        
    def check_python(self):
        """Python 버전 확인"""
        self.print_header("1. Python 확인")
        
        version = sys.version_info
        if version.major == 3 and version.minor >= 9:
            print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
            return True
        else:
            print(f"❌ Python 버전이 낮습니다: {version.major}.{version.minor}")
            print("Python 3.9 이상이 필요합니다!")
            return False
            
    def install_packages(self):
        """필수 패키지 자동 설치"""
        self.print_header("2. 필수 패키지 설치")
        
        packages = [
            'selenium',
            'websockets',
            'psutil',
            'requests',
            'webdriver-manager'
        ]
        
        print("다음 패키지를 설치합니다:")
        for pkg in packages:
            print(f"  - {pkg}")
        
        print("\n설치 중... (1~2분 소요)\n")
        
        for pkg in packages:
            try:
                # 이미 설치되어 있는지 확인
                try:
                    __import__(pkg.replace('-', '_'))
                    print(f"✓ {pkg} (이미 설치됨)")
                    continue
                except ImportError:
                    pass
                
                # 설치
                print(f"⬇ {pkg} 다운로드 및 설치 중...")
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg, "-q"],
                    stdout=subprocess.DEVNULL
                )
                print(f"✅ {pkg}")
            except Exception as e:
                print(f"❌ {pkg} 설치 실패: {e}")
                return False
        
        print("\n✅ 모든 패키지 설치 완료!")
        return True
        
    def download_worker_agent(self):
        """Worker Agent 파일 다운로드"""
        self.print_header("3. Worker Agent 다운로드")
        
        # GitHub raw 또는 직접 URL에서 다운로드
        # 현재는 로컬에서 복사
        
        source_file = Path(__file__).parent / 'worker_agent.py'
        
        if not source_file.exists():
            print("❌ worker_agent.py를 찾을 수 없습니다")
            print("   이 파일과 worker_agent.py를 같은 폴더에 두세요")
            return False
        
        # 복사
        target_file = self.install_dir / 'worker_agent.py'
        if target_file.exists() and target_file.samefile(source_file):
            print("✅ worker_agent.py (이미 존재)")
        else:
            import shutil
            shutil.copy(source_file, target_file)
            print(f"✅ worker_agent.py → {target_file}")
        
        return True
        
    def configure(self):
        """설정"""
        self.print_header("4. Worker 설정")
        
        print("Worker PC 정보를 입력하세요:\n")
        
        # PC 번호
        while True:
            pc_number = input("PC 번호 (1-8): ").strip()
            if pc_number.isdigit() and 1 <= int(pc_number) <= 8:
                pc_number = int(pc_number)
                break
            print("❌ 1에서 8 사이의 숫자를 입력하세요")
        
        # 서버 URL
        server_url = input(f"서버 URL (기본값: scorp274.com): ").strip()
        if not server_url:
            server_url = "scorp274.com"
        
        # 자동 시작
        auto_start = input("\nWindows 시작 시 자동 실행? (y/n): ").strip().lower() == 'y'
        
        # 설정 저장
        config = {
            'pc_number': pc_number,
            'server_url': server_url,
            'auto_start': auto_start
        }
        
        config_file = self.install_dir / 'worker_config.json'
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n✅ 설정 저장: {config_file}")
        
        return config
        
    def create_startup_files(self, config):
        """실행 파일 생성"""
        self.print_header("5. 실행 파일 생성")
        
        pc_num = config['pc_number']
        
        # 배치 파일
        batch_file = self.install_dir / f"실행_Worker_PC{pc_num}.bat"
        
        batch_content = f"""@echo off
chcp 65001 >nul
title Worker Agent PC #{pc_num}

cd /d "{self.install_dir}"

echo ╔════════════════════════════════════════════════════════╗
echo ║     Worker Agent PC #{pc_num} 시작                          ║
echo ╚════════════════════════════════════════════════════════╝
echo.

python worker_agent.py {pc_num}

pause
"""
        
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(batch_content)
        
        print(f"✅ 실행 배치 파일: {batch_file.name}")
        
        # 바탕화면 바로가기
        if platform.system() == 'Windows':
            try:
                desktop = Path.home() / 'Desktop'
                shortcut_name = f"🚀 Worker PC {pc_num}.lnk"
                
                ps_command = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{desktop / shortcut_name}")
$Shortcut.TargetPath = "{batch_file}"
$Shortcut.WorkingDirectory = "{self.install_dir}"
$Shortcut.IconLocation = "shell32.dll,14"
$Shortcut.Description = "Worker Agent PC {pc_num}"
$Shortcut.Save()
'''
                subprocess.run(['powershell', '-Command', ps_command], check=True, capture_output=True)
                print(f"✅ 바탕화면 바로가기: {shortcut_name}")
            except:
                print("⚠️ 바탕화면 바로가기 생성 실패 (무시 가능)")
        
        # 자동 시작
        if config['auto_start'] and platform.system() == 'Windows':
            self.setup_autostart(batch_file, pc_num)
        
        return batch_file
        
    def setup_autostart(self, batch_file, pc_num):
        """자동 시작 설정"""
        print(f"\n🔧 자동 시작 설정 중...")
        
        try:
            startup_folder = Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
            
            # VBS 파일 (숨김 실행)
            vbs_file = self.install_dir / f"start_worker_hidden.vbs"
            vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "{batch_file}" & Chr(34), 0
Set WshShell = Nothing
'''
            with open(vbs_file, 'w') as f:
                f.write(vbs_content)
            
            # 바로가기 생성
            ps_command = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{startup_folder / f'Worker PC {pc_num}.lnk'}")
$Shortcut.TargetPath = "{vbs_file}"
$Shortcut.WorkingDirectory = "{self.install_dir}"
$Shortcut.Save()
'''
            subprocess.run(['powershell', '-Command', ps_command], check=True, capture_output=True)
            print(f"✅ 자동 시작 설정 완료!")
            
        except Exception as e:
            print(f"⚠️ 자동 시작 설정 실패 (무시 가능): {e}")
            
    def run(self):
        """설치 실행"""
        print("""
╔════════════════════════════════════════════════════════╗
║     Worker Agent 올인원 자동 설치                     ║
║     모든 것을 자동으로 설치합니다!                     ║
╚════════════════════════════════════════════════════════╝
        """)
        
        # 1. Python 확인
        if not self.check_python():
            input("\nEnter를 눌러 종료...")
            return False
        
        # 2. 패키지 설치
        if not self.install_packages():
            input("\nEnter를 눌러 종료...")
            return False
        
        # 3. Worker Agent 확인
        if not self.download_worker_agent():
            input("\nEnter를 눌러 종료...")
            return False
        
        # 4. 설정
        config = self.configure()
        
        # 5. 실행 파일 생성
        batch_file = self.create_startup_files(config)
        
        # 완료
        self.print_header("✅ 설치 완료!")
        
        print("🎉 Worker Agent 설치가 완료되었습니다!\n")
        print("📝 다음 단계:")
        print(f"   1. VPN 연결 (각 PC마다 다른 서버)")
        print(f"   2. 바탕화면 '🚀 Worker PC {config['pc_number']}' 아이콘 더블클릭")
        print("   3. 서버에서 연결 확인:")
        print("      → https://scorp274.com/automation/cafe\n")
        
        # 즉시 실행 여부
        run_now = input("지금 바로 실행하시겠습니까? (y/n): ").strip().lower() == 'y'
        
        if run_now:
            print("\n🚀 Worker Agent 시작 중...\n")
            subprocess.run([sys.executable, 'worker_agent.py', str(config['pc_number'])])
        else:
            print(f"\n💡 실행 방법:")
            print(f"   바탕화면 '🚀 Worker PC {config['pc_number']}' 더블클릭!")
        
        return True


if __name__ == "__main__":
    installer = AutoInstaller()
    
    try:
        installer.run()
    except KeyboardInterrupt:
        print("\n\n⏹️ 설치 취소됨")
    except Exception as e:
        print(f"\n❌ 설치 오류: {e}")
        import traceback
        traceback.print_exc()
        input("\nEnter를 눌러 종료...")

