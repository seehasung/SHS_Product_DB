"""
작업 PC 설정 및 테스트 스크립트
Worker Agent가 제대로 작동하는지 확인

실행: python test_worker_setup.py
"""

import sys
import subprocess
import platform
import socket
import psutil
from pathlib import Path

class WorkerSetupTest:
    """Worker 설정 테스트"""
    
    def __init__(self):
        self.results = []
        self.errors = []
        
    def print_header(self, text):
        """헤더 출력"""
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}\n")
        
    def test_python_version(self):
        """Python 버전 확인"""
        print("🐍 Python 버전 확인...")
        version = sys.version_info
        
        if version.major == 3 and version.minor >= 9:
            print(f"✅ Python {version.major}.{version.minor}.{version.micro} (OK)")
            self.results.append(("Python 버전", True))
        else:
            print(f"❌ Python {version.major}.{version.minor}.{version.micro} (3.9 이상 필요)")
            self.errors.append("Python 버전이 낮습니다")
            self.results.append(("Python 버전", False))
            
    def test_packages(self):
        """필수 패키지 확인"""
        print("\n📦 필수 패키지 확인...")
        
        packages = [
            ('selenium', 'Selenium'),
            ('websockets', 'WebSockets'),
            ('psutil', 'PSUtil'),
            ('requests', 'Requests')
        ]
        
        for package, name in packages:
            try:
                __import__(package)
                print(f"✅ {name}")
                self.results.append((f"패키지: {name}", True))
            except ImportError:
                print(f"❌ {name} (설치 필요: pip install {package})")
                self.errors.append(f"{name} 패키지 미설치")
                self.results.append((f"패키지: {name}", False))
                
    def test_chrome(self):
        """Chrome 브라우저 확인"""
        print("\n🌐 Chrome 브라우저 확인...")
        
        if platform.system() == 'Windows':
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
        elif platform.system() == 'Darwin':  # macOS
            chrome_paths = ["/Applications/Google Chrome.app"]
        else:  # Linux
            chrome_paths = ["/usr/bin/google-chrome", "/usr/bin/chromium"]
        
        chrome_found = False
        for path in chrome_paths:
            if Path(path).exists():
                print(f"✅ Chrome 발견: {path}")
                chrome_found = True
                self.results.append(("Chrome 브라우저", True))
                break
        
        if not chrome_found:
            print("❌ Chrome 브라우저를 찾을 수 없습니다")
            print("   https://www.google.com/chrome/ 에서 설치하세요")
            self.errors.append("Chrome 미설치")
            self.results.append(("Chrome 브라우저", False))
            
    def test_network(self):
        """네트워크 연결 확인"""
        print("\n🌐 네트워크 확인...")
        
        # 로컬 IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            print(f"✅ 로컬 IP: {local_ip}")
            self.results.append(("네트워크", True))
        except:
            print("❌ 네트워크 연결 확인 실패")
            self.errors.append("네트워크 연결 없음")
            self.results.append(("네트워크", False))
            
        # 인터넷 연결
        try:
            import requests
            response = requests.get("https://www.google.com", timeout=5)
            if response.status_code == 200:
                print("✅ 인터넷 연결 정상")
            else:
                print("⚠️  인터넷 연결 불안정")
        except:
            print("❌ 인터넷 연결 없음")
            self.errors.append("인터넷 연결 없음")
            
    def test_system_resources(self):
        """시스템 리소스 확인"""
        print("\n💻 시스템 리소스 확인...")
        
        # CPU
        cpu_count = psutil.cpu_count()
        print(f"✅ CPU 코어: {cpu_count}개")
        
        # 메모리
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        print(f"✅ 메모리: {memory_gb:.1f}GB")
        
        if memory_gb < 4:
            print("⚠️  메모리가 부족할 수 있습니다 (4GB 이상 권장)")
            
        # 디스크
        disk = psutil.disk_usage('.')
        disk_free_gb = disk.free / (1024**3)
        print(f"✅ 디스크 여유 공간: {disk_free_gb:.1f}GB")
        
        self.results.append(("시스템 리소스", True))
        
    def test_worker_file(self):
        """Worker Agent 파일 확인"""
        print("\n📄 Worker Agent 파일 확인...")
        
        if Path('worker_agent.py').exists():
            print("✅ worker_agent.py 파일 존재")
            self.results.append(("Worker Agent 파일", True))
        else:
            print("❌ worker_agent.py 파일이 없습니다")
            print("   프로젝트 루트에 worker_agent.py를 복사하세요")
            self.errors.append("worker_agent.py 파일 없음")
            self.results.append(("Worker Agent 파일", False))
            
    def test_server_connection(self):
        """서버 연결 테스트"""
        print("\n🔌 서버 연결 테스트...")
        
        server_url = "scorp274.com"
        
        try:
            import requests
            # HTTPS 연결 테스트
            response = requests.get(f"https://{server_url}", timeout=10)
            if response.status_code in [200, 301, 302, 404]:  # 페이지가 존재하면 OK
                print(f"✅ 서버 연결 성공: {server_url}")
                self.results.append(("서버 연결", True))
            else:
                print(f"⚠️  서버 응답 이상: {response.status_code}")
        except Exception as e:
            print(f"❌ 서버 연결 실패: {e}")
            print(f"   {server_url}에 접속할 수 없습니다")
            self.errors.append("서버 연결 실패")
            self.results.append(("서버 연결", False))
            
    def print_summary(self):
        """테스트 결과 요약"""
        self.print_header("테스트 결과 요약")
        
        success_count = sum(1 for _, result in self.results if result)
        total_count = len(self.results)
        
        print(f"전체: {total_count}개")
        print(f"성공: {success_count}개")
        print(f"실패: {total_count - success_count}개\n")
        
        if self.errors:
            print("❌ 발견된 문제:")
            for i, error in enumerate(self.errors, 1):
                print(f"   {i}. {error}")
            print("\n해결 후 다시 테스트하세요.")
            return False
        else:
            print("✅ 모든 테스트 통과!")
            print("\nWorker Agent를 실행할 준비가 되었습니다.")
            print("\n실행 방법:")
            print("   python worker_agent.py <PC번호>")
            print("\n예:")
            print("   python worker_agent.py 1")
            return True
            
    def run(self):
        """모든 테스트 실행"""
        self.print_header("Worker PC 설정 테스트")
        
        self.test_python_version()
        self.test_packages()
        self.test_chrome()
        self.test_network()
        self.test_system_resources()
        self.test_worker_file()
        self.test_server_connection()
        
        return self.print_summary()


def install_packages():
    """누락된 패키지 자동 설치"""
    print("\n📦 누락된 패키지 설치 중...")
    
    packages = [
        'selenium',
        'websockets',
        'psutil',
        'requests',
        'webdriver-manager'
    ]
    
    for package in packages:
        try:
            __import__(package if package != 'webdriver-manager' else 'webdriver_manager')
            print(f"✅ {package} (이미 설치됨)")
        except ImportError:
            print(f"⬇️  {package} 설치 중...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ {package} 설치 완료")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════╗
║     Worker PC 설정 테스트                              ║
║     네이버 카페 자동화 시스템                           ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 옵션 확인
    if len(sys.argv) > 1 and sys.argv[1] == '--install':
        install_packages()
        print("\n패키지 설치 완료! 다시 테스트를 실행하세요.")
        sys.exit(0)
    
    # 테스트 실행
    tester = WorkerSetupTest()
    success = tester.run()
    
    if not success:
        print("\n💡 Tip: 자동으로 패키지를 설치하려면:")
        print("   python test_worker_setup.py --install")
    
    sys.exit(0 if success else 1)

