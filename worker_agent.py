"""
네이버 카페 자동화 Worker Agent
각 작업 PC에서 실행되는 프로그램

실행 방법:
    python worker_agent.py <PC번호>
    예: python worker_agent.py 1
"""

import asyncio
import websockets
import json
import warnings
import logging

# 경고 메시지 숨기기
warnings.filterwarnings('ignore')
logging.getLogger('selenium').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

# SSL 경고 무시
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

# ⭐ undetected-chromedriver (캡챠 우회)
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False
    print("⚠️ undetected_chromedriver가 없습니다. 일반 ChromeDriver 사용")
    print("   설치: pip install undetected-chromedriver")
import time
import random
import requests
from typing import Dict, Optional
import psutil
import socket
import sys
from datetime import datetime
from pathlib import Path


class NaverCafeWorker:
    """네이버 카페 자동 작성 Worker"""
    
    VERSION = "1.0.2" # 현재 버전
    
    def __init__(self, pc_number: int, server_url: str = "scorp274.com"):
        self.pc_number = pc_number
        self.server_url = server_url
        self.driver = None
        self.websocket = None
        self.current_account = None
        self.is_running = False
        
    def get_my_account_from_server(self) -> Optional[Dict]:
        """서버에서 내 PC에 할당된 계정 정보 가져오기"""
        try:
            api_url = f"https://{self.server_url}/automation/api/pcs/{self.pc_number}/account"
            response = requests.get(
                api_url,
                timeout=10,
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    account_info = data.get('account')
                    print(f"✅ 계정 정보 조회 성공: {account_info['account_id']}")
                    return account_info
                else:
                    print(f"⚠️  {data.get('error', '계정 정보를 찾을 수 없습니다')}")
                    return None
            else:
                print(f"⚠️  서버 응답 오류 (HTTP {response.status_code})")
                return None
                
        except Exception as e:
            print(f"❌ 계정 정보 조회 실패: {e}")
            return None
    
    def get_cafe_info_from_url(self, post_url: str) -> Optional[Dict]:
        """URL에서 카페 정보 조회"""
        try:
            from urllib.parse import urlparse
            
            # URL 파싱
            parsed = urlparse(post_url)
            cafe_domain = f"{parsed.scheme}://{parsed.netloc}"
            
            print(f"🔍 카페 정보 조회 중... (도메인: {cafe_domain})")
            
            # 서버에 카페 정보 요청
            api_url = f"https://{self.server_url}/automation/api/cafes/by-url"
            response = requests.get(
                api_url,
                params={'url': post_url},
                timeout=10,
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    cafe_info = data.get('cafe')
                    print(f"✅ 카페 정보 조회 성공")
                    print(f"   카페명: {cafe_info.get('name')}")
                    print(f"   게시판명: {cafe_info.get('target_board') or '미설정'}")
                    return cafe_info
            
            print(f"⚠️  등록되지 않은 카페입니다")
            return None
            
        except Exception as e:
            print(f"❌ 카페 정보 조회 실패: {e}")
            return None
    
    def change_board_category(self, target_board: str) -> bool:
        """게시판 카테고리 변경"""
        try:
            print(f"📋 게시판 변경 시도: '{target_board}'")
            
            # 게시판 선택 버튼/드롭다운 찾기
            category_selectors = [
                'select[name="menuid"]',
                'select.select-menu',
                'select#menuid',
                '.board-select select'
            ]
            
            for selector in category_selectors:
                try:
                    print(f"   시도: {selector}")
                    category_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    # 드롭다운에서 target_board와 일치하는 옵션 찾기
                    from selenium.webdriver.support.ui import Select
                    select = Select(category_elem)
                    
                    # 옵션 목록 확인
                    options = select.options
                    print(f"   사용 가능한 게시판: {[opt.text for opt in options]}")
                    
                    # target_board 이름으로 찾기
                    for option in options:
                        if target_board in option.text or option.text in target_board:
                            select.select_by_visible_text(option.text)
                            print(f"✅ 게시판 변경 완료: {option.text}")
                            self.random_delay(0.5, 1)
                            return True
                    
                    print(f"   ⚠️  '{target_board}' 게시판을 찾을 수 없습니다")
                    return False
                    
                except Exception as e:
                    print(f"   실패: {e}")
                    continue
            
            print("❌ 게시판 선택 요소를 찾을 수 없습니다")
            return False
            
        except Exception as e:
            print(f"❌ 게시판 변경 실패: {e}")
            return False
        
    def check_for_updates(self) -> bool:
        """서버에서 업데이트 확인 및 자동 다운로드"""
        try:
            print("🔍 업데이트 확인 중...")
            
            # 서버에서 최신 버전 정보 가져오기 (API 사용)
            version_url = f"https://{self.server_url}/automation/api/worker/version"
            response = requests.get(version_url, timeout=10, verify=False)
            
            if response.status_code != 200:
                print("⚠️  버전 정보를 가져올 수 없습니다 (건너뛰기)")
                return False
            
            server_version_info = response.json()
            server_version = server_version_info['version']
            
            # 버전을 숫자로 변환하여 비교
            def version_to_tuple(ver):
                return tuple(map(int, ver.replace('v', '').split('.')))
            
            current_ver = version_to_tuple(self.VERSION)
            server_ver = version_to_tuple(server_version)
            
            if server_ver == current_ver:
                print(f"✅ 최신 버전입니다 (v{self.VERSION})")
                return False
            elif server_ver < current_ver:
                print(f"ℹ️  개발 버전 사용 중 (v{self.VERSION} > v{server_version})")
                return False
            
            # 새 버전 발견 (server_ver > current_ver)
            print(f"\n🎉 새 버전 발견!")
            print(f"   현재: v{self.VERSION}")
            print(f"   최신: v{server_version}")
            print(f"\n📝 변경 사항:")
            for change in server_version_info.get('changelog', []):
                print(f"   - {change}")
            
            # 자동 다운로드
            print(f"\n⬇️  업데이트 다운로드 중...")
            
            download_url = f"https://{self.server_url}/automation/api/worker/download"
            response = requests.get(download_url, timeout=30, verify=False)
            
            if response.status_code != 200:
                print("❌ 다운로드 실패")
                return False
            
            # 백업 생성
            from pathlib import Path  # 함수 안에서 import
            import shutil
            
            current_file = Path(__file__)
            backup_file = current_file.with_suffix('.py.backup')
            shutil.copy(current_file, backup_file)
            print(f"✅ 백업 생성: {backup_file.name}")
            
            # 새 파일 저장
            with open(current_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            print(f"✅ 업데이트 완료!")
            print(f"\n🔄 Worker를 재시작합니다...")
            
            # 재시작
            import subprocess
            subprocess.Popen([sys.executable, str(current_file), str(self.pc_number)])
            
            return True
            
        except Exception as e:
            print(f"⚠️  업데이트 확인 실패 (무시하고 계속): {str(e)[:50]}")
            return False
    
    def get_local_ip(self) -> str:
        """VPN IP 포함 실제 외부 IP 주소 가져오기"""
        try:
            # 여러 외부 IP 조회 서비스 시도 (VPN IP 반환)
            services = [
                'https://api.ipify.org',
                'https://icanhazip.com',
                'https://ifconfig.me/ip',
                'https://checkip.amazonaws.com'
            ]
            
            for service in services:
                try:
                    response = requests.get(service, timeout=3)
                    if response.status_code == 200:
                        ip = response.text.strip()
                        return ip
                except:
                    continue
            
            # 모두 실패 시 로컬 IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
            
        except:
            return "Unknown"
    
    async def connect_to_server(self):
        """서버에 WebSocket 연결"""
        import ssl
        
        ws_url = f"wss://{self.server_url}/automation/ws/worker/{self.pc_number}"
        
        try:
            # SSL 인증서 검증 비활성화 (자체 서명 인증서 대응)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.websocket = await websockets.connect(
                ws_url,
                ssl=ssl_context,
                ping_interval=None,  # ping 비활성화 (heartbeat 사용)
                ping_timeout=None,
                close_timeout=10
            )
            print(f"✅ PC #{self.pc_number} 서버 연결 성공: {ws_url}")
        except Exception as e:
            print(f"❌ 서버 연결 실패: {e}")
            print(f"   재연결 시도 중...")
            await asyncio.sleep(5)
            await self.connect_to_server()
        
    def init_selenium(self):
        """Selenium 초기화 (봇 감지 우회 설정)"""
        print("🚀 Selenium 브라우저 초기화 중...")
        
        if UNDETECTED_AVAILABLE:
            # ⭐ undetected-chromedriver 사용 (캡챠 우회!)
            print("  ✅ undetected-chromedriver 사용 (고급 봇 감지 우회)")
            
            options = uc.ChromeOptions()
            
            # 기본 설정
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--log-level=3')
            
            # 브라우저 생성
            self.driver = uc.Chrome(options=options, version_main=None)
            
        else:
            # 일반 ChromeDriver (기존 방식)
            print("  ⚠️ 일반 ChromeDriver 사용")
        
        options = webdriver.ChromeOptions()
        
        # 봇 감지 우회 설정
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # User-Agent 설정
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 기타 설정
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--log-level=3')
        options.add_argument('--silent')
        options.add_argument('--disable-logging')
        
        # 브라우저 생성
        self.driver = webdriver.Chrome(options=options)
        
        # WebDriver 속성 숨기기
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                '''
            })
        except:
            pass
        
        # 창 크기 설정
        self.driver.set_window_size(1400, 900)
        
        print("✅ 브라우저 준비 완료")
        
    async def send_heartbeat(self):
        """주기적으로 서버에 상태 전송 (10초마다)"""
        while self.is_running:
            try:
                status = {
                    'type': 'heartbeat',
                    'pc_number': self.pc_number,
                    'status': 'online',
                    'cpu_usage': psutil.cpu_percent(),
                    'memory_usage': psutil.virtual_memory().percent,
                    'current_account': self.current_account,
                    'ip_address': self.get_local_ip()
                }
                await self.websocket.send(json.dumps(status))
                await asyncio.sleep(10)
            except Exception as e:
                print(f"❌ Heartbeat 전송 실패: {e}")
                await asyncio.sleep(10)
            
    def random_delay(self, min_sec: float = 0.1, max_sec: float = 0.3):
        """랜덤 지연 (봇 감지 방지)"""
        time.sleep(random.uniform(min_sec, max_sec))
        
    def human_type(self, element, text: str):
        """사람처럼 한 글자씩 입력"""
        for char in text:
            element.send_keys(char)
            self.random_delay(0.05, 0.15)  # 글자당 0.05~0.15초
            
    def login_naver(self, account_id: str, account_pw: str):
        """네이버 로그인 (캡챠 우회 버전)"""
        print(f"🔐 네이버 로그인 시도: {account_id}")
        
        try:
            from selenium.webdriver.common.keys import Keys
            
            # ⭐ 1. 네이버 메인 먼저 접속
            self.driver.get('https://www.naver.com')
            self.random_delay(2, 3)
            
            # ⭐ 2. 로그인 페이지로 이동
            self.driver.get('https://nid.naver.com/nidlogin.login')
            self.random_delay(2, 3)
            
            # ⭐ 3. ID 입력 (직접 입력)
            id_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'id'))
            )
            id_input.click()
            self.random_delay(0.5, 1)
            self.human_type(id_input, account_id)
            self.random_delay(0.5, 1)
            
            # ⭐ 4. PW 입력 (직접 입력)
            pw_input = self.driver.find_element(By.ID, 'pw')
            pw_input.click()
            self.random_delay(0.5, 1)
            self.human_type(pw_input, account_pw)
            self.random_delay(0.5, 1)
            
            # ⭐ 5. 로그인 버튼 클릭 (정확한 ID 사용)
            self.random_delay(1, 2)
            login_btn = self.driver.find_element(By.ID, 'log.login')
            login_btn.click()
            
            self.random_delay(3, 5)
            
            # ⭐ 6. 로그인 성공 확인
            current_url = self.driver.current_url
            
            # 네이버 메인으로 이동해서 확인
            if 'nid.naver.com' not in current_url:
                self.driver.get('https://www.naver.com')
                self.random_delay(2, 3)
            
            # 로그아웃 버튼으로 로그인 확인
            try:
                logout_btn = self.driver.find_element(By.XPATH, '//*[@id="account"]/div[1]/div/button')
                if logout_btn:
                    self.current_account = account_id
                    print(f"✅ {account_id} 로그인 성공 (로그아웃 버튼 확인)")
                    return True
            except:
                pass
            
            # 대체 확인 방법
            if 'nid.naver.com' not in self.driver.current_url:
                self.current_account = account_id
                print(f"✅ {account_id} 로그인 성공")
                return True
            else:
                print(f"❌ {account_id} 로그인 실패 (캡챠 또는 오류)")
                print(f"\n{'='*60}")
                print(f"⏸️  수동 로그인 모드")
                print(f"{'='*60}")
                print(f"계정: {account_id}")
                print(f"")
                print(f"브라우저에서 수동으로 로그인해주세요.")
                print(f"로그인 완료 후 아무 키나 누르세요...")
                print(f"{'='*60}")
                
                # 사용자 입력 대기
                input("▶ 로그인 완료 후 Enter 키를 누르세요: ")
                
                print("✅ 수동 로그인 완료로 간주합니다")
                self.current_account = account_id
                return True
                
        except Exception as e:
            print(f"❌ 로그인 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def modify_post(self, draft_url: str, title: str, content: str) -> Optional[str]:
        """기존 글 수정 발행 (새 탭에서 작업)"""
        print(f"\n{'='*60}")
        print(f"🔄 글 수정 발행 시작")
        print(f"{'='*60}")
        print(f"URL: {draft_url}")
        print(f"제목: {title}")
        print(f"본문: {content[:100]}...")
        print(f"{'='*60}\n")
        
        # 현재 탭 저장 (네이버 홈 탭)
        original_window = self.driver.current_window_handle
        
        try:
            # ⭐ 새 탭 열기
            print("📑 새 탭 열기...")
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            print("✅ 새 탭으로 전환 완료")
            
            # ⭐ 카페 정보 조회 및 게시판 변경
            cafe_info = self.get_cafe_info_from_url(draft_url)
            target_board = None
            if cafe_info and cafe_info.get('target_board'):
                target_board = cafe_info.get('target_board')
                print(f"📋 자동 게시판 변경 예정: {target_board}")
            
            # 기존 글 URL 접속
            print("📡 URL 접속 중...")
            self.driver.get(draft_url)
            self.random_delay(3, 5)
            print("✅ URL 접속 완료")
            
            # iframe 전환 (신규발행 글 보기 페이지)
            try:
                iframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, 'cafe_main'))
                )
                self.driver.switch_to.frame(iframe)
                self.random_delay(2, 3)
                print("✅ iframe 전환 완료")
            except Exception as e:
                print(f"⚠️  iframe 전환 실패: {e}")
            
            # 수정 버튼 찾기 (XPath 사용 - test_content_save 방식)
            print("🔍 수정 버튼 찾기...")
            try:
                edit_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
                )
                edit_btn.click()
                self.random_delay(5, 7)
                print("✅ 수정 버튼 클릭 완료")
            except Exception as e:
                print(f"❌ 수정 버튼 클릭 실패: {e}")
                return None
            
            # ⭐ 새 탭으로 자동 전환 (수정 페이지는 새 탭에서 열림!)
            if len(self.driver.window_handles) > 2:  # 네이버 홈 + 카페 글 + 수정 페이지
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.random_delay(3, 5)
                print("✅ 수정 페이지 탭으로 전환 완료")
            
            print("✅ 수정 화면 진입 완료")
            print("✅ 수정 화면 진입 완료")
            
            # ⭐ 게시판 변경 (target_board가 있는 경우)
            if target_board:
                print(f"\n📋 게시판 자동 변경 시작: {target_board}")
                try:
                    # 카테고리 드롭다운 클릭
                    category_btn = self.driver.find_element(By.CSS_SELECTOR, 'div.FormSelectBox button')
                    category_btn.click()
                    self.random_delay(1, 2)
                    
                    # 옵션 목록에서 선택
                    options = self.driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
                    for opt in options:
                        opt_text = opt.find_element(By.CSS_SELECTOR, 'span.option_text').text
                        if target_board in opt_text:
                            opt.click()
                            self.random_delay(0.5, 1)
                            print(f"   ✅ '{opt_text}' 선택 완료")
                            break
                except Exception as e:
                    print(f"   ⚠️  게시판 변경 실패: {e} (계속 진행)")
            
            # 제목 수정
            print(f"\n✍️ 제목 입력: {title}")
            try:
                title_elem = self.driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
                title_elem.click()
                self.random_delay(0.5, 1)
                title_elem.send_keys(Keys.CONTROL + 'a', Keys.DELETE)
                self.random_delay(0.5, 1)
                
                # ⭐ 사람처럼 한 글자씩 타이핑
                print("   → 사람처럼 타이핑 중...")
                self.human_type(title_elem, title)
                print("   ✅ 제목 입력 완료")
            except Exception as e:
                print(f"   ⚠️  제목 입력 실패: {e}")
            
            # 본문 수정 (test_full_post_flow 방식)
            print("📝 본문 입력 시도...")
            print(f"   본문 길이: {len(content)}자")
            
            content_success = False
            
            # 방법 1: p.se-text-paragraph 직접 클릭 후 타이핑 (test_full_post_flow 검증된 방식)
            try:
                print("   직접 타이핑 방식으로 본문 입력...")
                paragraph = self.driver.find_element(By.CSS_SELECTOR, "p.se-text-paragraph")
                self.driver.execute_script("arguments[0].scrollIntoView(true);", paragraph)
                self.random_delay(0.5, 1)
                
                paragraph.click()
                self.random_delay(0.5, 1)
                
                active = self.driver.switch_to.active_element
                
                # 기존 내용 전체 삭제
                print("      → 기존 내용 삭제 중...")
                active.send_keys(Keys.CONTROL, 'a')  # 전체 선택
                self.random_delay(0.2, 0.3)
                active.send_keys(Keys.DELETE)  # 삭제
                self.random_delay(0.5, 1)
                
                # ⭐ 새 내용 입력 (사람처럼 한 글자씩)
                print("      → 사람처럼 타이핑 중...")
                self.human_type(active, content)
                self.random_delay(0.5, 1)
                
                # 입력 확인
                check_script = """
                    var span = document.querySelector('span.__se-node');
                    if (span && span.textContent.length > 0) {
                        return true;
                    }
                    return false;
                """
                if self.driver.execute_script(check_script):
                    content_success = True
                    print("✅ 본문 입력 완료")
                else:
                    print("   ⚠️ 입력 확인 실패")
                
            except Exception as e:
                print(f"   ❌ 본문 입력 실패: {e}")
            
            # 최종 확인
            if not content_success:
                print("❌ 본문 입력 실패")
                print("   수동으로 본문을 입력해주세요!")
            
            self.random_delay(2, 3)
            
            # ⭐ 댓글 허용 체크박스 확인 및 설정
            print("\n💬 댓글 허용 설정 확인 중...")
            try:
                # 댓글 허용 체크박스 찾기
                comment_checkbox_selectors = [
                    '#coment',  # 네이버 카페 표준 (오타: coment)
                    'input[id="coment"]',
                    'input[type="checkbox"][name*="comment"]',
                    'input[type="checkbox"][id*="comment"]',
                    'input[type="checkbox"].comment-allow',
                    '#commentOpen',
                    'input[name="commentOpen"]'
                ]
                
                comment_checkbox = None
                for selector in comment_checkbox_selectors:
                    try:
                        comment_checkbox = self.driver.find_element(By.CSS_SELECTOR, selector)
                        print(f"   ✅ 댓글 체크박스 발견: {selector}")
                        break
                    except:
                        continue
                
                if comment_checkbox:
                    # 현재 체크 상태 확인
                    is_checked = comment_checkbox.is_selected()
                    print(f"   현재 상태: {'체크됨' if is_checked else '체크 안됨'}")
                    
                    # 체크되어 있지 않으면 체크하기
                    if not is_checked:
                        comment_checkbox.click()
                        self.random_delay(0.5, 1)
                        print("   ✅ 댓글 허용 체크 완료")
                    else:
                        print("   ℹ️  이미 체크되어 있음 (건너뛰기)")
                else:
                    print("   ⚠️  댓글 체크박스를 찾을 수 없습니다 (기본값 사용)")
                    
            except Exception as e:
                print(f"   ⚠️  댓글 설정 오류: {e} (계속 진행)")
            
            self.random_delay(1, 2)
            
            # ⭐ 등록 버튼 자동 클릭 (다중 방법 시도)
            print("\n📤 등록 버튼 자동 클릭 시도...")
            submit_selectors = [
                ('xpath', '//*[@id="app"]/div/div/section/div/div[1]/div/a'),  # 사용자 제공 XPath
                ('css', 'a.btn-submit'),
                ('css', 'button.btn-submit'),
                ('css', 'a[class*="submit"]'),
                ('css', 'button[class*="submit"]'),
                ('css', '#btn-submit'),
                ('css', '.btn-register'),
                ('css', 'a.btn_register')
            ]
            
            submit_btn = None
            used_selector = None
            clicked = False
            
            # 1단계: 버튼 찾기
            for selector_type, selector in submit_selectors:
                try:
                    if selector_type == 'xpath':
                        submit_btn = self.driver.find_element(By.XPATH, selector)
                    else:
                        submit_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    used_selector = f"{selector_type}: {selector}"
                    print(f"   ✅ 등록 버튼 발견: {used_selector}")
                    break
                except:
                    continue
            
            if submit_btn:
                # 2단계: 스크롤하여 버튼이 보이도록
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
                    self.random_delay(0.5, 1)
                except:
                    pass
                
                # 3단계: 클릭 시도 (여러 방법)
                click_methods = [
                    ("일반 클릭", lambda: submit_btn.click()),
                    ("JavaScript 클릭", lambda: self.driver.execute_script("arguments[0].click();", submit_btn)),
                    ("ActionChains 클릭", lambda: ActionChains(self.driver).move_to_element(submit_btn).click().perform())
                ]
                
                for method_name, click_func in click_methods:
                    try:
                        print(f"   🖱️  {method_name} 시도...")
                        click_func()
                        self.random_delay(2, 3)
                        
                        # 클릭 성공 확인 (URL 변경 또는 페이지 변화 확인)
                        current_url = self.driver.current_url
                        if 'ArticleWrite' not in current_url or 'ArticleModify' not in current_url:
                            clicked = True
                            print(f"   ✅ {method_name} 성공!")
                            break
                        else:
                            print(f"   ⚠️  {method_name} 후에도 페이지 변화 없음")
                            
                    except Exception as e:
                        print(f"   ⚠️  {method_name} 실패: {e}")
                        continue
                
                if clicked:
                    print("✅ 등록 버튼 자동 클릭 완료")
                    self.random_delay(2, 3)  # 페이지 로딩 대기
                else:
                    print("⚠️  모든 클릭 방법 실패, 최종 시도...")
                    # 최종 시도: 강제 JavaScript 실행
                    try:
                        self.driver.execute_script("""
                            var btn = arguments[0];
                            btn.click();
                            if (btn.onclick) btn.onclick();
                            if (btn.href) window.location.href = btn.href;
                        """, submit_btn)
                        self.random_delay(3, 4)
                        print("✅ JavaScript 강제 클릭 완료")
                    except Exception as e:
                        print(f"❌ 최종 클릭도 실패: {e}")
            else:
                print("❌ 등록 버튼을 찾을 수 없습니다")
            
            post_url = self.driver.current_url
            print(f"\n{'='*60}")
            print(f"✅ 수정 발행 완료")
            print(f"{'='*60}")
            print(f"URL: {post_url}")
            print(f"{'='*60}\n")
            
            # ⭐ 작업 완료 후 열린 탭들 모두 닫기 (수정 페이지 + 카페 글 보기 탭)
            print("📑 작업 탭들 닫기...")
            current_handles = self.driver.window_handles
            
            # 네이버 홈 탭 외의 모든 탭 닫기
            for handle in current_handles:
                if handle != original_window:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
            
            # 네이버 홈 탭으로 복귀
            self.driver.switch_to.window(original_window)
            print("✅ 네이버 홈 탭으로 복귀 완료")
            
            return post_url
            
        except Exception as e:
            print(f"❌ 수정 발행 오류: {e}")
            import traceback
            traceback.print_exc()
            
            # ⭐ 오류 발생 시에도 열린 탭들 모두 닫기
            try:
                current_handles = self.driver.window_handles
                for handle in current_handles:
                    if handle != original_window:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                
                self.driver.switch_to.window(original_window)
                print("✅ 오류 후 네이버 홈 탭으로 복귀")
            except:
                pass
            
            return None
    
    def write_post(self, cafe_url: str, title: str, content: str) -> Optional[str]:
        """카페 글 작성 (봇 감지 우회)"""
        print(f"📝 글 작성 시작: {title[:30]}...")
        
        try:
            # 카페 글쓰기 페이지 이동
            write_url = f'{cafe_url}/ArticleWrite.nhn'
            self.driver.get(write_url)
            self.random_delay(2, 3)
            
            # 제목 입력 (한 글자씩)
            title_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'subject'))
            )
            title_input.click()
            self.random_delay(0.3, 0.5)
            self.human_type(title_input, title)
            
            self.random_delay(1, 2)
            
            # 내용 입력 (iframe 전환)
            # 스마트에디터 iframe 찾기
            iframe = self.driver.find_element(By.CSS_SELECTOR, 'iframe[id*="se2_iframe"]')
            self.driver.switch_to.frame(iframe)
            
            # 본문 입력 영역
            content_div = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.se2_inputarea, body'))
            )
            content_div.click()
            self.random_delay(0.5, 1)
            
            # 문장 단위로 입력 (더 자연스럽게)
            sentences = content.replace('.\n', '.|').replace('. ', '.|').split('|')
            for sentence in sentences:
                if sentence.strip():
                    self.human_type(content_div, sentence.strip())
                    
                    # 문장 끝에 휴식
                    if not sentence.endswith('\n'):
                        content_div.send_keys('.')
                    content_div.send_keys('\n')
                    
                    self.random_delay(0.5, 1.5)
            
            # iframe에서 나오기
            self.driver.switch_to.default_content()
            self.random_delay(1, 2)
            
            # 등록 버튼 찾기 및 클릭
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, 'a.btn-submit, button.btn-submit, a[class*="submit"], button[class*="submit"]')
            
            # 스크롤하여 버튼이 보이도록
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            self.random_delay(0.5, 1)
            
            submit_btn.click()
            self.random_delay(3, 4)
            
            # 작성된 글 URL 추출
            post_url = self.driver.current_url
            
            print(f"✅ 글 작성 완료: {post_url}")
            return post_url
            
        except Exception as e:
            print(f"❌ 글 작성 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def write_comment(self, post_url: str, content: str, is_reply: bool = False, parent_comment_id: Optional[str] = None) -> bool:
        """댓글/대댓글 작성 (새 탭에서 작업)"""
        comment_type = "대댓글" if is_reply else "댓글"
        print(f"💬 {comment_type} 작성 시작: {content[:30]}...")
        
        # 현재 탭 저장 (네이버 홈 탭)
        original_window = self.driver.current_window_handle
        
        try:
            # ⭐ 새 탭 열기
            print("📑 새 탭 열기...")
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            print("✅ 새 탭으로 전환 완료")
            
            # 글 페이지로 이동
            self.driver.get(post_url)
            self.random_delay(3, 5)
            
            # iframe 전환 (네이버 카페)
            try:
                iframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, 'cafe_main'))
                )
                self.driver.switch_to.frame(iframe)
                self.random_delay(2, 3)
                print("  ✅ iframe 전환 완료")
            except:
                print("  ⚠️ iframe 전환 실패 (일반 페이지로 진행)")
            
            # 대댓글인 경우: 부모 댓글 찾아서 답글 버튼 클릭
            if is_reply and parent_comment_id:
                print(f"  🔍 부모 댓글 찾기 (ID: {parent_comment_id})...")
                
                # ⭐ 네이버 카페 실제 구조: <li id="510247118">
                # 숫자로 시작하는 ID는 속성 선택자 사용!
                parent_selectors = [
                    f"[id='{parent_comment_id}']",  # ⭐ 속성 선택자 (가장 확실)
                    f"li[id='{parent_comment_id}']",
                    f"div[id='{parent_comment_id}']"
                ]
                
                parent_found = False
                for selector in parent_selectors:
                    try:
                        parent_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        parent_found = True
                        print(f"  ✅ 부모 댓글 발견: {selector}")
                        
                        # ⭐ 답글쓰기 버튼 찾기 (실제 구조)
                        reply_btn_selectors = [
                            "a.comment_info_button",  # ⭐ 실제 class!
                            "a[role='button']:contains('답글')",
                            ".comment_info_button",
                            "a.comment_reply",
                            "button.comment_reply"
                        ]
                        
                        reply_clicked = False
                        for btn_selector in reply_btn_selectors:
                            try:
                                # 여러 버튼이 있을 수 있으므로 모두 찾기
                                buttons = parent_elem.find_elements(By.CSS_SELECTOR, "a.comment_info_button")
                                for btn in buttons:
                                    if "답글" in btn.text:
                                        btn.click()
                                        self.random_delay(1, 2)
                                        print(f"  ✅ 답글쓰기 버튼 클릭")
                                        reply_clicked = True
                                        break
                                if reply_clicked:
                                    break
                            except:
                                continue
                        
                        if not reply_clicked:
                            print("  ⚠️ 답글쓰기 버튼을 찾을 수 없습니다")
                        
                        break
                    except:
                        continue
                
                if not parent_found:
                    print("  ⚠️ 부모 댓글을 찾을 수 없습니다")
            
            # ⭐ 댓글 입력창 찾기 (실제 네이버 카페 구조)
            comment_selectors = [
                'textarea.comment_inbox_text',  # ⭐ 실제 class!
                'textarea[placeholder*="댓글"]',
                'textarea.comment_inbox',
                'textarea.comment_text_input',
                'textarea[id*="comment"]',
                'textarea.comment-box',
                'div[contenteditable="true"]',
                'textarea.textarea'
            ]
            
            comment_input = None
            for selector in comment_selectors:
                try:
                    comment_input = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    print(f"  ✅ 입력창 발견: {selector}")
                    break
                except:
                    continue
            
            if not comment_input:
                print("❌ 댓글 입력창을 찾을 수 없습니다")
                return False
            
            # 댓글 입력창 클릭
            comment_input.click()
            self.random_delay(0.5, 1)
            
            # ⭐ 댓글 내용 입력
            self.human_type(comment_input, content)
            self.random_delay(1, 2)
            print(f"  ✅ 내용 입력 완료")
            
            # ⭐ 등록 버튼 찾기 (실제 네이버 카페 구조)
            submit_selectors = [
                'a.btn_register',  # ⭐ 실제 class!
                'a.button.btn_register',
                'button.btn_register',
                'a[role="button"]:contains("등록")',
                'button.comment_submit',
                'a.comment_submit',
                'button[class*="submit"]',
                'a[class*="submit"]'
            ]
            
            submit_btn = None
            for selector in submit_selectors:
                try:
                    submit_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    print(f"  ✅ 등록 버튼 발견: {selector}")
                    break
                except:
                    continue
            
            if submit_btn:
                submit_btn.click()
                self.random_delay(2, 3)
                print(f"✅ {comment_type} 등록 버튼 클릭")
                
                # ⭐ 댓글 작성 후 ID 추출 (새 댓글인 경우만)
                comment_id = None
                if not is_reply:
                    try:
                        # 페이지 새로고침 없이 최신 댓글 찾기
                        self.random_delay(3, 4)  # 댓글이 DOM에 추가될 때까지 대기
                        
                        # ⭐ 네이버 카페 실제 구조: <li id="510247118" class="CommentItem">
                        comment_id_selectors = [
                            "ul.comment_list > li.CommentItem:last-of-type",  # ⭐ 실제 구조!
                            "ul.comment_list > li:last-of-type",
                            ".comment_list > li:last-child",
                            "li.CommentItem:last-of-type",
                            "div[id^='cmt_']:last-of-type",
                            "li[id^='cmt_']:last-of-type"
                        ]
                        
                        for selector in comment_id_selectors:
                            try:
                                latest_comment = self.driver.find_element(By.CSS_SELECTOR, selector)
                                element_id = latest_comment.get_attribute('id')
                                
                                if element_id:
                                    # ⭐ 네이버 카페는 숫자만 (예: 510247118)
                                    comment_id = element_id.replace('cmt_', '')  # 혹시 cmt_가 있으면 제거
                                    print(f"  📌 작성된 댓글 ID: {comment_id} (선택자: {selector})")
                                    break
                            except:
                                continue
                        
                        if not comment_id:
                            print("  ⚠️ 댓글 ID를 자동으로 찾을 수 없습니다")
                            print("  💡 수동으로 확인 필요: F12 → Elements → 최신 댓글의 id 속성")
                    except Exception as e:
                        print(f"  ⚠️ 댓글 ID 추출 오류: {e}")
                
                print(f"✅ {comment_type} 작성 완료")
                
                # ⭐ 작업 완료 후 탭 닫기
                print("📑 작업 탭 닫기...")
                self.driver.close()
                self.driver.switch_to.window(original_window)
                print("✅ 네이버 홈 탭으로 복귀 완료")
                
                return comment_id if not is_reply else True
            else:
                print("❌ 댓글 등록 버튼을 찾을 수 없습니다")
                
                # ⭐ 실패 시에도 탭 닫기
                try:
                    self.driver.close()
                    self.driver.switch_to.window(original_window)
                    print("✅ 실패 후 네이버 홈 탭으로 복귀")
                except:
                    pass
                
                return False
                
        except Exception as e:
            print(f"❌ {comment_type} 작성 오류: {e}")
            import traceback
            traceback.print_exc()
            
            # ⭐ 오류 발생 시에도 탭 닫기
            try:
                self.driver.close()
                self.driver.switch_to.window(original_window)
                print("✅ 오류 후 네이버 홈 탭으로 복귀")
            except:
                pass
            
            return False
        
    async def process_task(self, task: Dict):
        """작업 처리"""
        task_id = task['id']
        task_type = task['task_type']
        
        try:
            # 서버에 작업 시작 알림
            await self.websocket.send(json.dumps({
                'type': 'task_started',
                'task_id': task_id,
                'pc_number': self.pc_number
            }))
            
            print(f"\n{'='*60}")
            print(f"🎯 작업 처리 시작: Task #{task_id} ({task_type})")
            print(f"{'='*60}")
            
            if task_type == 'post':
                # draft_url이 있으면 수정 발행, 없으면 새 글
                draft_url = task.get('draft_url')
                
                if draft_url:
                    print(f"🔄 수정 발행: {draft_url[:50]}...")
                    post_url = self.modify_post(draft_url, task['title'], task['content'])
                else:
                    print(f"📝 새 글 작성: {task['cafe_url']}")
                    post_url = self.write_post(
                        task['cafe_url'],
                        task['title'],
                        task['content']
                    )
                
                if post_url:
                    # 서버에 완료 알림
                    await self.websocket.send(json.dumps({
                        'type': 'task_completed',
                        'task_id': task_id,
                        'post_url': post_url
                    }))
                else:
                    raise Exception("글 작성/수정 실패")
                
            elif task_type in ['comment', 'reply']:
                # 댓글 작성
                is_reply = (task_type == 'reply')
                parent_comment_id = task.get('parent_comment_id')
                
                result = self.write_comment(
                    task['post_url'],
                    task['content'],
                    is_reply=is_reply,
                    parent_comment_id=parent_comment_id
                )
                
                if result:
                    # 새 댓글인 경우 댓글 ID를 받음
                    message = {
                        'type': 'task_completed',
                        'task_id': task_id
                    }
                    
                    # 댓글 ID가 있으면 추가
                    if isinstance(result, str) and not is_reply:
                        message['cafe_comment_id'] = result
                        print(f"  📤 댓글 ID 전송: {result}")
                    
                    await self.websocket.send(json.dumps(message))
                else:
                    raise Exception("댓글 작성 실패")
            
            print(f"✅ 작업 완료: Task #{task_id}")
            
        except Exception as e:
            # 오류 발생 시 서버에 알림
            print(f"❌ 작업 실패: Task #{task_id} - {e}")
            await self.websocket.send(json.dumps({
                'type': 'task_failed',
                'task_id': task_id,
                'error': str(e)
            }))
            
    async def listen_for_tasks(self):
        """서버로부터 작업 수신"""
        while self.is_running:
            try:
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=30.0  # 30초 타임아웃
                )
                
                # ping/pong 처리
                if message == 'ping':
                    await self.websocket.send('pong')
                    continue
                
                try:
                    data = json.loads(message)
                    print(f"📨 메시지 받음: type={data.get('type')}")  # 디버그 로그
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON 파싱 실패: {message[:100]}")
                    print(f"   에러: {e}")
                    continue
                except Exception as e:
                    print(f"❌ 메시지 처리 에러: {e}")
                    continue
                
                if data.get('type') == 'new_task':
                    task = data.get('task', {})
                    
                    if not task or 'id' not in task:
                        print("⚠️ 유효하지 않은 작업 데이터")
                        print(f"   데이터: {data}")
                        continue
                    
                    print(f"\n📥 새 작업 수신: Task #{task['id']}")
                    
                    # 계정 로그인 확인
                    if task.get('account_id') and task['account_id'] != self.current_account:
                        print(f"🔄 계정 전환: {task['account_id']}")
                        if task.get('account_pw'):
                            self.login_naver(
                                task['account_id'],
                                task['account_pw']
                            )
                    
                    # 작업 처리
                    await self.process_task(task)
                    
                elif data.get('type') == 'start_comment':
                    # 댓글 시작 신호 (순차 실행)
                    task_id = data.get('task_id')
                    group = data.get('group')
                    sequence = data.get('sequence')
                    
                    print(f"\n🚀 댓글 시작 신호: 그룹 {group}-{sequence} (Task #{task_id})")
                    
                    # 서버에서 Task 정보 가져오기 (API 호출)
                    # 여기서는 바로 처리하지 않고 new_task로 재전송받음
                    
                elif data.get('type') == 'shutdown':
                    print("⏹️ 종료 명령 수신")
                    self.is_running = False
                    break
                    
            except asyncio.TimeoutError:
                # 타임아웃은 정상 (계속 대기)
                continue
                    
            except websockets.exceptions.ConnectionClosed:
                print("❌ WebSocket 연결이 끊어졌습니다. 재연결 중...")
                await asyncio.sleep(3)
                try:
                    await self.connect_to_server()
                except:
                    print("❌ 재연결 실패, 5초 후 재시도...")
                    await asyncio.sleep(5)
                    
            except Exception as e:
                print(f"❌ 메시지 처리 오류: {e}")
                await asyncio.sleep(1)
                
    async def run(self):
        """Worker 실행"""
        self.is_running = True
        
        print(f"""
╔════════════════════════════════════════════════════════╗
║     네이버 카페 자동화 Worker Agent v{self.VERSION}       ║
║                                                        ║
║     PC 번호: {self.pc_number:02d}                       ║
║     서버: {self.server_url:40s}                         ║
╚════════════════════════════════════════════════════════╝
        """)
        
        # 업데이트 확인
        updated = self.check_for_updates()
        if updated:
            # 업데이트 후 재시작됨
            print("✅ 업데이트 완료! 재시작 중...")
            return
        
        # Selenium 초기화
        self.init_selenium()
        
        # 🔐 자동 로그인
        print("\n" + "="*60)
        print("🔐 네이버 자동 로그인 시작")
        print("="*60)
        
        account_info = self.get_my_account_from_server()
        if account_info:
            account_id = account_info['account_id']
            account_pw = account_info['account_pw']
            
            print(f"📋 할당된 계정: {account_id}")
            print(f"🚀 로그인 시도 중...")
            
            login_success = self.login_naver(account_id, account_pw)
            
            if login_success:
                print(f"✅ {account_id} 로그인 완료!")
                print(f"🏠 네이버 홈 탭 유지 (이 탭은 닫지 마세요)")
                self.current_account = account_id
            else:
                print(f"❌ 로그인 실패 - 수동으로 로그인이 필요합니다")
        else:
            print(f"⚠️  PC #{self.pc_number}에 할당된 계정이 없습니다")
            print(f"    https://{self.server_url}/automation/cafe 에서 계정을 할당해주세요")
        
        print("="*60 + "\n")
        
        # 서버 연결
        await self.connect_to_server()
        
        print("✅ Worker 준비 완료! 작업 대기 중...")
        
        # Heartbeat & 작업 수신 동시 실행
        await asyncio.gather(
            self.send_heartbeat(),
            self.listen_for_tasks()
        )
        
    def cleanup(self):
        """정리"""
        print("\n🧹 정리 중...")
        
        if self.driver:
            try:
                self.driver.quit()
                print("✅ 브라우저 종료")
            except:
                pass
        
        if self.websocket:
            try:
                asyncio.get_event_loop().run_until_complete(self.websocket.close())
                print("✅ WebSocket 연결 종료")
            except:
                pass
        
        print("✅ Worker 종료 완료")


# ============================================
# 메인 실행
# ============================================

if __name__ == "__main__":
    # 명령줄 인자: python worker_agent.py <PC번호>
    if len(sys.argv) < 2:
        print("""
사용법:
    python worker_agent.py <PC번호>
    
예:
    python worker_agent.py 1  # PC #1로 실행
    python worker_agent.py 2  # PC #2로 실행
        """)
        sys.exit(1)
    
    pc_number = int(sys.argv[1])
    
    # 서버 URL (필요시 변경)
    server_url = "scorp274.com"  # 또는 "localhost:10000" (로컬 테스트)
    
    worker = NaverCafeWorker(
        pc_number=pc_number,
        server_url=server_url
    )
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 종료됨")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        worker.cleanup()

