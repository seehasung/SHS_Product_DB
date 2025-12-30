"""
Worker Agent 자동 설치 스크립트
모든 필수 패키지를 자동으로 설치하고 설정합니다

실행: python install_worker.py
"""

import subprocess
import sys
import platform
import os
from pathlib import Path
import json

class WorkerInstaller:
    """Worker Agent 자동 설치"""
    
    def __init__(self):
        self.install_dir = Path.cwd()
        self.config_file = self.install_dir / "worker_config.json"
        
    def print_header(self, text):
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}\n")
        
    def check_python(self):
        """Python 버전 확인"""
        self.print_header("1. Python 버전 확인")
        
        version = sys.version_info
        if version.major == 3 and version.minor >= 9:
            print(f"✅ Python {version.major}.{version.minor}.{version.micro} (OK)")
            return True
        else:
            print(f"❌ Python {version.major}.{version.minor}.{version.micro}")
            print("Python 3.9 이상이 필요합니다!")
            print("https://www.python.org/downloads/ 에서 설치하세요")
            return False
            
    def install_packages(self):
        """필수 패키지 설치"""
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
        
        print("\n설치 시작...\n")
        
        for pkg in packages:
            try:
                print(f"📦 {pkg} 설치 중...")
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT
                )
                print(f"✅ {pkg} 설치 완료")
            except Exception as e:
                print(f"❌ {pkg} 설치 실패: {e}")
                return False
        
        print("\n✅ 모든 패키지 설치 완료!")
        return True
        
    def configure_worker(self):
        """Worker 설정"""
        self.print_header("3. Worker 설정")
        
        print("Worker PC 정보를 입력하세요:\n")
        
        # PC 번호
        while True:
            pc_number = input("PC 번호 (1-8): ").strip()
            if pc_number.isdigit() and 1 <= int(pc_number) <= 8:
                pc_number = int(pc_number)
                break
            print("❌ 1에서 8 사이의 숫자를 입력하세요")
        
        # PC 이름
        pc_name = input(f"PC 이름 (기본값: Worker PC #{pc_number}): ").strip()
        if not pc_name:
            pc_name = f"Worker PC #{pc_number}"
        
        # 서버 URL
        server_url = input("서버 URL (기본값: scorp274.com): ").strip()
        if not server_url:
            server_url = "scorp274.com"
        
        # 자동 시작 여부
        auto_start = input("\nWindows 시작 시 자동 실행하시겠습니까? (y/n): ").strip().lower() == 'y'
        
        # 설정 저장
        config = {
            'pc_number': pc_number,
            'pc_name': pc_name,
            'server_url': server_url,
            'auto_start': auto_start
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 설정 저장됨: {self.config_file}")
        print(f"\n📝 설정 내용:")
        print(f"   PC 번호: {pc_number}")
        print(f"   PC 이름: {pc_name}")
        print(f"   서버: {server_url}")
        print(f"   자동 시작: {'예' if auto_start else '아니오'}")
        
        return config
        
    def create_startup_script(self, config):
        """시작 스크립트 생성"""
        self.print_header("4. 실행 스크립트 생성")
        
        # Windows 배치 파일
        if platform.system() == 'Windows':
            batch_file = self.install_dir / f"start_worker_pc{config['pc_number']}.bat"
            
            batch_content = f"""@echo off
title Worker Agent PC #{config['pc_number']}
cd /d "{self.install_dir}"
python worker_agent.py {config['pc_number']}
pause
"""
            
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            print(f"✅ 배치 파일 생성: {batch_file.name}")
            
            # 작업 스케줄러 등록 (자동 시작)
            if config['auto_start']:
                self.setup_windows_autostart(config, batch_file)
                
        # macOS/Linux 쉘 스크립트
        else:
            script_file = self.install_dir / f"start_worker_pc{config['pc_number']}.sh"
            
            script_content = f"""#!/bin/bash
cd "{self.install_dir}"
python3 worker_agent.py {config['pc_number']}
"""
            
            with open(script_file, 'w') as f:
                f.write(script_content)
            
            # 실행 권한 부여
            os.chmod(script_file, 0o755)
            
            print(f"✅ 쉘 스크립트 생성: {script_file.name}")
            
    def setup_windows_autostart(self, config, batch_file):
        """Windows 자동 시작 설정"""
        print("\n🔧 자동 시작 설정 중...")
        
        try:
            # VBS 스크립트 생성 (숨김 실행용)
            vbs_file = self.install_dir / f"start_worker_pc{config['pc_number']}.vbs"
            
            vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "{batch_file}" & Chr(34), 0
Set WshShell = Nothing
"""
            
            with open(vbs_file, 'w') as f:
                f.write(vbs_content)
            
            # 시작 프로그램 폴더에 바로가기 생성
            startup_folder = Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
            
            # PowerShell로 바로가기 생성
            ps_command = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{startup_folder / vbs_file.name}")
$Shortcut.TargetPath = "{vbs_file}"
$Shortcut.WorkingDirectory = "{self.install_dir}"
$Shortcut.Save()
"""
            
            subprocess.run(['powershell', '-Command', ps_command], check=True)
            
            print(f"✅ 자동 시작 설정 완료!")
            print(f"   위치: {startup_folder / vbs_file.name}")
            
        except Exception as e:
            print(f"⚠️  자동 시작 설정 실패: {e}")
            print("   수동으로 설정하세요 (가이드 참고)")
            
    def create_desktop_shortcut(self, config):
        """바탕화면 바로가기 생성"""
        if platform.system() == 'Windows':
            desktop = Path.home() / 'Desktop'
            batch_file = self.install_dir / f"start_worker_pc{config['pc_number']}.bat"
            
            try:
                ps_command = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{desktop / f'Worker PC {config["pc_number"]}.lnk'}")
$Shortcut.TargetPath = "{batch_file}"
$Shortcut.WorkingDirectory = "{self.install_dir}"
$Shortcut.IconLocation = "shell32.dll,14"
$Shortcut.Save()
"""
                subprocess.run(['powershell', '-Command', ps_command], check=True)
                print(f"✅ 바탕화면 바로가기 생성: Worker PC {config['pc_number']}.lnk")
            except:
                print("⚠️  바탕화면 바로가기 생성 실패 (무시 가능)")
                
    def run(self):
        """설치 실행"""
        print("""
╔════════════════════════════════════════════════════════╗
║     Worker Agent 자동 설치 프로그램                    ║
║     네이버 카페 자동화 시스템                           ║
╚════════════════════════════════════════════════════════╝
        """)
        
        # 1. Python 확인
        if not self.check_python():
            return False
        
        # 2. 패키지 설치
        if not self.install_packages():
            return False
        
        # 3. 설정
        config = self.configure_worker()
        
        # 4. 실행 스크립트 생성
        self.create_startup_script(config)
        
        # 5. 바탕화면 바로가기
        self.create_desktop_shortcut(config)
        
        # 완료
        self.print_header("설치 완료!")
        
        print("✅ Worker Agent 설치가 완료되었습니다!\n")
        print("📝 다음 단계:")
        print(f"   1. IP 주소를 192.168.1.{100 + config['pc_number']}로 설정")
        print(f"   2. start_worker_pc{config['pc_number']}.bat 실행")
        print("   3. 서버 대시보드에서 연결 확인")
        print("      → https://scorp274.com/automation/cafe\n")
        
        if platform.system() == 'Windows':
            print(f"💡 바탕화면의 'Worker PC {config['pc_number']}' 아이콘을 더블클릭하세요!\n")
        
        return True


if __name__ == "__main__":
    installer = WorkerInstaller()
    
    try:
        success = installer.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️ 설치 취소됨")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 설치 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

