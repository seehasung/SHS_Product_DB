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
import os

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

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    print("⚠️ pyperclip이 없습니다. 클립보드 로그인 불가 (설치: pip install pyperclip)")


class NaverCafeWorker:
    """네이버 카페 자동 작성 Worker"""
    
    VERSION = "1.1.0" # 현재 버전
    
    def __init__(self, pc_number: int, server_url: str = "scorp274.com"):
        self.pc_number = pc_number
        self.server_url = server_url
        self.driver = None
        self.websocket = None
        self.current_account = None
        self.is_running = False
        self.pending_completions = []  # ⭐ 미전송 완료 신호 큐 (연결 끊겨도 유실 방지)
        
    async def report_task_complete(self, task_id: int, post_url: str = None, cafe_comment_id: str = None):
        """완료 신호 HTTP 전송 - 최대 5분간 재시도 (순서 보장 필수!)"""
        import requests
        data = {}
        if post_url:
            data['post_url'] = post_url
        if cafe_comment_id:
            data['cafe_comment_id'] = cafe_comment_id
            print(f"   📤 댓글 ID 전송: {cafe_comment_id}")
        
        # ⭐ 최대 5분(300초) 동안 30초 간격으로 재시도 = 최대 10회
        max_wait_seconds = 300
        retry_interval = 30
        max_attempts = max_wait_seconds // retry_interval  # 10회
        
        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    f"https://{self.server_url}/automation/api/tasks/{task_id}/complete",
                    data=data,
                    timeout=30,
                    verify=False
                )
                if response.status_code == 200:
                    print(f"   ✅ 완료 보고 성공 (HTTP, 시도: {attempt+1})")
                    # 큐에서 제거 (재시도였다면)
                    self.pending_completions = [c for c in self.pending_completions if c['task_id'] != task_id]
                    return True
                else:
                    print(f"   ⚠️  완료 보고 실패: HTTP {response.status_code} (시도: {attempt+1}/{max_attempts})")
            except Exception as e:
                elapsed = (attempt + 1) * retry_interval
                remaining = max_wait_seconds - elapsed
                print(f"   ⚠️  완료 보고 오류: {e} (시도: {attempt+1}/{max_attempts}, 경과: {elapsed}초, 남은: {remaining}초)")
            
            if attempt < max_attempts - 1:
                print(f"   🔄 {retry_interval}초 후 재시도...")
                await asyncio.sleep(retry_interval)
        
        # ⭐ 5분 모두 실패 → 큐에 저장 (재연결 후 재전송)
        print(f"   ❌ 5분 재시도 후도 완료 보고 실패 → 큐에 저장 (재연결 후 재시도)")
        if not any(c['task_id'] == task_id for c in self.pending_completions):
            self.pending_completions.append({'task_id': task_id, 'data': data})
        return False

    async def flush_pending_completions(self):
        """재연결 후 미전송 완료 신호 일괄 재전송"""
        if not self.pending_completions:
            return
        
        print(f"\n🔄 미전송 완료 신호 재전송 시작: {len(self.pending_completions)}개")
        import requests
        success_ids = []
        for item in list(self.pending_completions):
            task_id = item['task_id']
            data = item['data']
            try:
                response = requests.post(
                    f"https://{self.server_url}/automation/api/tasks/{task_id}/complete",
                    data=data,
                    timeout=30,
                    verify=False
                )
                if response.status_code == 200:
                    print(f"   ✅ Task #{task_id} 완료 보고 재전송 성공")
                    success_ids.append(task_id)
                else:
                    print(f"   ⚠️  Task #{task_id} 재전송 실패: HTTP {response.status_code}")
            except Exception as e:
                print(f"   ⚠️  Task #{task_id} 재전송 오류: {e}")
        
        self.pending_completions = [c for c in self.pending_completions if c['task_id'] not in success_ids]
        if success_ids:
            print(f"   ✅ {len(success_ids)}개 재전송 완료")

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
            
            # ⭐ 연결 성공 후 미전송 완료 신호 재전송
            await self.flush_pending_completions()
            
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
            except websockets.exceptions.ConnectionClosed:
                # ⭐ Heartbeat 실패 시 재연결 시도
                print(f"❌ Heartbeat 전송 실패 (연결 끊김) → 재연결 시도...")
                await asyncio.sleep(3)
                try:
                    await self.connect_to_server()
                except:
                    pass
                await asyncio.sleep(5)
            except Exception as e:
                print(f"❌ Heartbeat 전송 실패: {e}")
                await asyncio.sleep(10)
            
    def random_delay(self, min_sec: float = 0.1, max_sec: float = 0.3):
        """랜덤 지연 - 동기 버전 (Selenium 내부에서 사용)"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    async def async_delay(self, min_sec: float = 0.1, max_sec: float = 0.3):
        """랜덤 지연 - 비동기 버전 (이벤트 루프 살림, 긴 대기 시 사용)"""
        await asyncio.sleep(random.uniform(min_sec, max_sec))
        
    def human_type(self, element, text: str):
        """사람처럼 한 글자씩 입력"""
        for char in text:
            element.send_keys(char)
            self.random_delay(0.05, 0.15)  # 글자당 0.05~0.15초
            
    def login_naver(self, account_id: str, account_pw: str):
        """네이버 로그인 - 클립보드 붙여넣기 방식 (캡챠 우회)"""
        print(f"🔐 네이버 로그인 시도: {account_id}")
        
        try:
            # ⭐ 1. 네이버 메인 먼저 접속 (쿠키/세션 초기화)
            self.driver.get('https://www.naver.com')
            self.random_delay(2, 3)
            
            # ⭐ 2. 로그인 페이지로 이동
            self.driver.get('https://nid.naver.com/nidlogin.login')
            self.random_delay(2, 3)
            
            # ⭐ 3. ID 입력 - 클립보드 붙여넣기 (캡챠 방지 핵심)
            id_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'id'))
            )
            id_input.click()
            self.random_delay(0.5, 1)
            if PYPERCLIP_AVAILABLE:
                pyperclip.copy(account_id)
                id_input.send_keys(Keys.CONTROL, 'v')
            else:
                self.human_type(id_input, account_id)
            self.random_delay(0.5, 1)
            
            # ⭐ 4. PW 입력 - 클립보드 붙여넣기 (캡챠 방지 핵심)
            pw_input = self.driver.find_element(By.ID, 'pw')
            pw_input.click()
            self.random_delay(0.5, 1)
            if PYPERCLIP_AVAILABLE:
                pyperclip.copy(account_pw)
                pw_input.send_keys(Keys.CONTROL, 'v')
            else:
                self.human_type(pw_input, account_pw)
            self.random_delay(0.5, 1)
            
            # ⭐ 5. 로그인 버튼 클릭
            self.random_delay(1, 2)
            login_btn = self.driver.find_element(By.ID, 'log.login')
            login_btn.click()
            
            self.random_delay(3, 5)
            
            # ⭐ 6. 로그인 결과 확인 루프 (최대 30초)
            max_wait = 30
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                current_url = self.driver.current_url
                page_source = self.driver.page_source
                
                # 아이디/비밀번호 오류 체크
                if ("아이디(로그인 전용 아이디) 또는 비밀번호를 잘못 입력했습니다" in page_source or
                        "입력하신 아이디와 비밀번호가 일치하지 않습니다" in page_source or
                        "error=110" in current_url):
                    print(f"❌ {account_id} 아이디/비밀번호 불일치")
                    return False
                
                # 캡챠 체크
                try:
                    captcha = self.driver.find_element(By.ID, "captcha")
                    if captcha:
                        print(f"⚠️ {account_id} 캡챠 발생 - 건너뜀")
                        return False
                except:
                    pass
                
                # 브라우저 등록 페이지 처리 (새 기기 인증)
                if ("새로운 기기(브라우저)에서 로그인되었습니다" in page_source or
                        "deviceConfirm" in current_url):
                    print(f"📱 {account_id} 브라우저 등록 페이지 감지 - 자동 등록 시도")
                    register_selectors = [
                        (By.XPATH, "//button[contains(text(), '등록')]"),
                        (By.XPATH, "//a[contains(text(), '등록')]"),
                        (By.CSS_SELECTOR, "button.btn_confirm"),
                        (By.CSS_SELECTOR, "button[type='submit']"),
                    ]
                    for by, selector in register_selectors:
                        try:
                            btn = self.driver.find_element(by, selector)
                            if btn.is_displayed() and btn.is_enabled():
                                btn.click()
                                print(f"✅ 브라우저 등록 버튼 클릭")
                                self.random_delay(3, 5)
                                break
                        except:
                            continue
                    continue
                
                # nid.naver.com이 아니면 네이버 메인으로 이동해서 로그인 확인
                if 'nid.naver.com' not in current_url:
                    self.driver.get('https://www.naver.com')
                    self.random_delay(2, 3)
                
                # 로그아웃 버튼으로 로그인 성공 확인
                try:
                    logout_btn = self.driver.find_element(By.XPATH, '//*[@id="account"]/div[1]/div/button')
                    if logout_btn:
                        self.current_account = account_id
                        print(f"✅ {account_id} 로그인 성공 (로그아웃 버튼 확인)")
                        return True
                except:
                    pass
                
                # 추가 확인 방법
                try:
                    logout_els = self.driver.find_elements(By.XPATH, "//button[contains(text(), '로그아웃')]")
                    if logout_els:
                        self.current_account = account_id
                        print(f"✅ {account_id} 로그인 성공")
                        return True
                    account_el = self.driver.find_elements(By.CSS_SELECTOR, "#account")
                    if account_el and "로그아웃" in account_el[0].get_attribute("innerHTML"):
                        self.current_account = account_id
                        print(f"✅ {account_id} 로그인 성공 (계정 영역 확인)")
                        return True
                except:
                    pass
                
                elapsed = int(time.time() - start_time)
                if elapsed % 5 == 0:
                    print(f"  로그인 확인 중... ({elapsed}초 경과) URL: {current_url[:60]}")
                
                time.sleep(1)
            
            print(f"❌ {account_id} 로그인 시간 초과")
            return False
                
        except Exception as e:
            print(f"❌ 로그인 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def download_image(self, image_url: str) -> Optional[str]:
        """이미지 URL에서 임시 파일로 다운로드 후 경로 반환"""
        try:
            import requests as req
            import tempfile
            response = req.get(image_url, timeout=30, verify=False)
            if response.status_code == 200:
                temp_dir = tempfile.gettempdir()
                filename = f"cafe_img_{int(time.time() * 1000)}.jpg"
                temp_path = os.path.join(temp_dir, filename)
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                print(f"   ✅ 이미지 다운로드 완료: {filename}")
                return temp_path
            else:
                print(f"   ❌ 이미지 다운로드 실패 (HTTP {response.status_code})")
                return None
        except Exception as e:
            print(f"   ❌ 이미지 다운로드 오류: {e}")
            return None

    def _find_image_file_input(self):
        """Smart Editor ONE에서 이미지 file input 탐색
        
        핵심 원리:
        - 사진 버튼 클릭 → 내부적으로 input[type=file].click() 호출 → 네이티브 다이얼로그 오픈
        - JS 프로토타입 오버라이드로 .click() 차단 → 다이얼로그 없이 file input 참조만 획득
        - 이후 send_keys()로 파일 경로 직접 전달 (Selenium 표준 업로드 방식)
        """

        def search_in_current_frame():
            """현재 프레임에서 이미지용 file input 탐색"""
            inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            for fi in inputs:
                accept = fi.get_attribute('accept') or ''
                if 'image' in accept.lower() or not accept:
                    return fi
            return None

        # ── Step 1: 버튼 클릭 없이 직접 탐색 ──────────────────────
        result = search_in_current_frame()
        if result:
            print(f"   [발견] 메인 문서 file input (버튼 클릭 불필요)")
            return result

        # ── Step 2: 다이얼로그 차단 JS 주입 ───────────────────────
        # Object.defineProperty로 프로토타입 오버라이드 + capture 이벤트 리스너 병행
        self.driver.execute_script("""
            window._seLastFileInput = null;
            if (!window._seClickOverridden) {
                window._seClickOverridden = true;
                try {
                    var _origProto = HTMLInputElement.prototype.click;
                    Object.defineProperty(HTMLInputElement.prototype, 'click', {
                        configurable: true,
                        writable: true,
                        value: function() {
                            if (this.type === 'file') {
                                window._seLastFileInput = this;
                                return;  // 네이티브 다이얼로그 차단
                            }
                            return _origProto.apply(this, arguments);
                        }
                    });
                } catch(e) {}
                // capture phase 이벤트도 차단
                document.addEventListener('click', function(e) {
                    if (e.target && e.target.tagName === 'INPUT' && e.target.type === 'file') {
                        window._seLastFileInput = e.target;
                        e.preventDefault();
                        e.stopImmediatePropagation();
                    }
                }, true);
            }
        """)

        # ── Step 3: 이미지 버튼 클릭 ──────────────────────────────
        # 실제 확인된 버튼 HTML:
        # <button class="se-image-toolbar-button" data-name="image"
        #         data-group="documentToolbar" data-log="dot.img">
        image_btn_selectors = [
            'button.se-image-toolbar-button[data-name="image"]',
            'button[data-name="image"][data-group="documentToolbar"]',
            'button[data-log="dot.img"]',
            'button.se-image-toolbar-button',
            'button[data-name="image"]',
            '.__se__toolbar li[data-name="image"] button',
            'button[title*="사진"]',
            'button[title*="이미지"]',
        ]

        btn_clicked = False
        for sel in image_btn_selectors:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                self.driver.execute_script("arguments[0].click();", btn)
                self.random_delay(1.5, 2)
                btn_clicked = True
                print(f"   [클릭] 이미지 버튼: {sel}")
                break
            except Exception:
                continue

        if not btn_clicked:
            print(f"   ⚠️  이미지 버튼 못 찾음")

        # ── Step 4: JS intercept 결과 확인 ────────────────────────
        intercepted = self.driver.execute_script("return window._seLastFileInput;")
        if intercepted:
            print(f"   [감지] JS 프로토타입 intercept 성공 - 다이얼로그 없이 file input 획득")
            return intercepted

        # ── Step 5: DOM 재탐색 (동적 생성됐을 수 있음) ────────────
        result = search_in_current_frame()
        if result:
            print(f"   [발견] 버튼 클릭 후 DOM에서 file input 발견")
            return result

        # ── Step 6: 다이얼로그 열린 경우 ESC로 닫기 후 재탐색 ─────
        # (JS 오버라이드 실패 시 - 네이티브 다이얼로그가 열렸을 가능성)
        print(f"   ⚠️  JS 차단 실패 - 네이티브 다이얼로그 닫기 시도")
        closed = False
        try:
            import pyautogui
            pyautogui.press('escape')
            self.random_delay(1, 1.5)
            closed = True
            print(f"   [ESC] pyautogui로 다이얼로그 닫음")
        except ImportError:
            pass

        if not closed:
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                self.random_delay(0.5, 1)
                print(f"   [ESC] ActionChains ESC 전송")
            except Exception:
                pass

        result = search_in_current_frame()
        if result:
            print(f"   [발견] ESC 후 file input 발견")
            return result

        # ── Step 7: 모든 iframe 탐색 ──────────────────────────────
        iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
        print(f"   [iframe] {len(iframes)}개 iframe 탐색...")
        for i, iframe in enumerate(iframes):
            try:
                self.driver.switch_to.frame(iframe)
                result = search_in_current_frame()
                if result:
                    print(f"   [발견] iframe[{i}]에서 file input 발견")
                    return result  # ⚠️ iframe 컨텍스트 유지 - send_keys 후 default_content() 복원 필요
                self.driver.switch_to.default_content()
            except Exception:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass

        print(f"   ❌ 모든 방법으로도 file input 없음")
        return None

    def upload_images_to_editor(self, temp_files: list):
        """스마트 에디터에 이미지 파일 업로드 (file input 방식)"""
        if not temp_files:
            return
        print(f"\n📤 이미지 {len(temp_files)}장 에디터 업로드 중...")
        for idx, temp_file in enumerate(temp_files, 1):
            try:
                print(f"   이미지 {idx}/{len(temp_files)}: {os.path.basename(temp_file)}")

                image_input = self._find_image_file_input()

                if not image_input:
                    print(f"   ❌ file input 없음 - 이미지 {idx} 건너뜀")
                    continue

                # JS로 강제 표시
                self.driver.execute_script("""
                    var inp = arguments[0];
                    inp.style.cssText = [
                        'display:block !important',
                        'visibility:visible !important',
                        'opacity:1 !important',
                        'position:fixed !important',
                        'top:0 !important',
                        'left:0 !important',
                        'z-index:99999 !important',
                        'width:200px !important',
                        'height:50px !important'
                    ].join(';');
                """, image_input)
                self.random_delay(0.5, 1)

                # 파일 경로 전달 (로컬 탐색기 없이 직접 전송)
                image_input.send_keys(temp_file)
                self.random_delay(5, 7)  # 업로드 완료 대기

                # 업로드 완료 후 숨기기
                try:
                    self.driver.execute_script("arguments[0].style.display='none';", image_input)
                except Exception:
                    pass

                # iframe 컨텍스트 복원
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass

                # JS intercept 리셋
                self.driver.execute_script("window._seLastFileInput = null;")

                print(f"   ✅ 이미지 {idx} 업로드 완료")

            except Exception as e:
                print(f"   ❌ 이미지 {idx} 업로드 오류: {e}")
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass

    def modify_post(self, draft_url: str, title: str, content: str, target_board: str = None, image_urls: list = None, keyword: str = None) -> Optional[str]:
        """기존 글 수정 발행 (새 탭에서 작업)"""
        print(f"\n{'='*60}")
        print(f"🔄 글 수정 발행 시작")
        print(f"{'='*60}")
        print(f"URL: {draft_url}")
        print(f"제목: {title}")
        print(f"본문: {content[:100]}...")
        print(f"게시판: {target_board or '변경 없음'}")
        print(f"{'='*60}\n")
        
        # 현재 탭 저장 (네이버 홈 탭)
        original_window = self.driver.current_window_handle
        
        try:
            # ⭐ 새 탭 열기
            print("📑 새 탭 열기...")
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            print("✅ 새 탭으로 전환 완료")
            
            # ⭐ 게시판 변경 대상 결정 (파라미터 우선, 없으면 API 조회)
            if not target_board:
                cafe_info = self.get_cafe_info_from_url(draft_url)
                if cafe_info and cafe_info.get('target_board'):
                    target_board = cafe_info.get('target_board')
            
            if target_board:
                print(f"📋 자동 게시판 변경 예정: {target_board}")
            else:
                print(f"📋 게시판 변경 없음 (target_board 미설정)")
            
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
                print(f"\n📋 게시판 자동 변경 시작: '{target_board}'")
                try:
                    # 카테고리 드롭다운 버튼 대기 후 클릭
                    category_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.FormSelectBox button'))
                    )
                    category_btn.click()
                    self.random_delay(1, 2)
                    
                    # 옵션 목록에서 선택
                    options = self.driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
                    available_boards = []
                    matched = False
                    for opt in options:
                        try:
                            opt_text = opt.find_element(By.CSS_SELECTOR, 'span.option_text').text.strip()
                        except:
                            opt_text = opt.text.strip()
                        available_boards.append(opt_text)
                        # 양방향 포함 검색 (대소문자 무시)
                        if target_board in opt_text or opt_text in target_board:
                            self.driver.execute_script("arguments[0].click();", opt)
                            self.random_delay(0.5, 1)
                            print(f"   ✅ 게시판 변경 완료: '{opt_text}'")
                            matched = True
                            break
                    
                    if not matched:
                        print(f"   ⚠️  '{target_board}' 게시판을 찾을 수 없습니다")
                        print(f"   📋 사용 가능한 게시판: {available_boards}")
                        # 드롭다운 닫기 (ESC)
                        from selenium.webdriver.common.keys import Keys as K
                        self.driver.find_element(By.CSS_SELECTOR, 'div.FormSelectBox button').send_keys(K.ESCAPE)
                        
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
                self.random_delay(0.5, 1)
                
                # Tab키로 본문으로 이동
                title_elem.send_keys(Keys.TAB)
                self.random_delay(1, 2)
                print("   ✅ 제목 입력 완료, 본문으로 이동")
            except Exception as e:
                print(f"   ⚠️  제목 입력 실패: {e}")
            
            # 본문 수정
            print("📝 본문 입력 시도...")
            print(f"   본문 길이: {len(content)}자")
            
            content_success = False
            
            # 직접 타이핑 방식 (Tab으로 이동한 상태)
            try:
                print("   직접 타이핑 방식으로 본문 입력...")
                
                # Tab으로 이동한 active element 사용
                active = self.driver.switch_to.active_element
                self.random_delay(0.5, 1)
                
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
            
            # ⭐ 이미지 업로드 (image_urls가 있는 경우)
            temp_files = []
            if image_urls:
                print(f"\n📷 이미지 업로드 준비 ({len(image_urls)}장)...")
                for img_url in image_urls:
                    temp_path = self.download_image(img_url)
                    if temp_path:
                        temp_files.append(temp_path)
                
                if temp_files:
                    self.upload_images_to_editor(temp_files)
                    self.random_delay(2, 3)
                    
                    # 업로드 완료 후 임시 파일 정리
                    for tf in temp_files:
                        try:
                            os.remove(tf)
                        except Exception:
                            pass
                    print(f"   🗑️ 임시 파일 정리 완료")
                else:
                    print("   ⚠️ 다운로드된 이미지 없음, 업로드 건너뜀")
            
            # ⭐ 태그(키워드) 입력
            if keyword:
                print(f"\n🏷️ 태그 입력: {keyword}")
                try:
                    tag_input = self.driver.find_element(By.CSS_SELECTOR, 'input.tag_input')
                    tag_input.click()
                    self.random_delay(0.5, 1)
                    self.human_type(tag_input, keyword)
                    tag_input.send_keys(Keys.ENTER)
                    self.random_delay(0.5, 1)
                    print("   ✅ 태그 입력 완료")
                except Exception as e:
                    print(f"   ⚠️  태그 입력 실패: {e} (계속 진행)")
            
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
                        try:
                            # 방법 1: label 클릭 시도
                            label = self.driver.find_element(By.CSS_SELECTOR, 'label[for="coment"]')
                            label.click()
                            self.random_delay(0.5, 1)
                            print("   ✅ 댓글 허용 체크 완료 (label 클릭)")
                        except:
                            try:
                                # 방법 2: JavaScript로 직접 체크
                                self.driver.execute_script("arguments[0].checked = true;", comment_checkbox)
                                self.random_delay(0.5, 1)
                                print("   ✅ 댓글 허용 체크 완료 (JS)")
                            except Exception as e:
                                print(f"   ⚠️  댓글 체크 실패: {e}")
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
                    
                    # ⭐ 리다이렉트 대기 (실제 글 URL로 변경될 때까지)
                    print("⏳ 글 등록 후 리다이렉트 대기 중...")
                    import time
                    for i in range(15):  # 최대 15초
                        time.sleep(1)
                        current = self.driver.current_url
                        
                        # /modify가 없고 /articles/가 있으면 실제 글 URL
                        if '/modify' not in current and ('/articles/' in current or '/ArticleRead' in current):
                            print(f"   ✅ 실제 글 URL 확인: {current[:80]}...")
                            break
                    else:
                        print("   ⚠️  타임아웃, 현재 URL 사용")
                        
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
                        
                        # ⭐ 리다이렉트 대기
                        print("⏳ 글 등록 후 리다이렉트 대기 중...")
                        import time
                        for i in range(15):
                            time.sleep(1)
                            current = self.driver.current_url
                            if '/modify' not in current and ('/articles/' in current or '/ArticleRead' in current):
                                print(f"   ✅ 실제 글 URL 확인: {current[:80]}...")
                                break
                        else:
                            print("   ⚠️  타임아웃, 현재 URL 사용")
                            
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
        
    def create_draft_post(self, cafe_url: str, post_title: str, post_body: str) -> Optional[str]:
        """카페에 신규 인사글(가입인사) 작성 후 URL 반환"""
        print(f"📋 신규발행 인사글 작성 시작: {cafe_url[:50]}...")
        max_retries = 2

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"  🔄 재시도 {attempt}/{max_retries - 1}")

                # 카페 접속
                self.driver.get(cafe_url)
                self.random_delay(3, 5)

                if "cafe.naver.com" not in self.driver.current_url:
                    print("  ❌ 카페 페이지 로드 실패")
                    continue

                # iframe 전환 시도 (구형 카페)
                iframe_found = False
                try:
                    cafe_iframe = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "cafe_main"))
                    )
                    self.driver.switch_to.frame(cafe_iframe)
                    iframe_found = True
                    print("  ✅ iframe 전환 성공")
                except Exception:
                    print("  ℹ️  iframe 없음, 일반 페이지 진행")

                # 글쓰기 버튼 클릭
                # 우선순위: 정확한 XPath → 범용 선택자 순으로 시도
                write_btn = None
                write_selectors = [
                    (By.XPATH, '//*[@id="cafe_content"]/div[4]/div/div[2]/a'),   # ★ 신규 카페 정확한 위치
                    (By.XPATH, '//*[@id="cafe_content"]//a[contains(@class,"write")]'),
                    (By.XPATH, '//a[contains(@class, "write")]'),
                    (By.XPATH, '//span[contains(text(), "글쓰기")]'),
                    (By.CLASS_NAME, 'btn_write'),
                    (By.XPATH, '//a[contains(@href, "ArticleWrite")]'),
                    (By.XPATH, '//button[contains(text(), "글쓰기")]'),
                    (By.XPATH, '//a[contains(text(), "글쓰기")]'),
                    (By.CSS_SELECTOR, 'a.cafe-write-btn'),
                    (By.CSS_SELECTOR, '[class*="write"]'),
                ]
                for by, value in write_selectors:
                    try:
                        for elem in self.driver.find_elements(by, value):
                            if elem.is_displayed():
                                write_btn = elem
                                print(f"  ✅ 글쓰기 버튼 발견: {value}")
                                break
                        if write_btn:
                            break
                    except Exception:
                        continue

                if not write_btn:
                    print("  ❌ 글쓰기 버튼 없음 - JavaScript로 재시도")
                    # JavaScript로 버튼 탐색
                    try:
                        write_btn_href = self.driver.execute_script("""
                            var links = document.querySelectorAll('a');
                            for(var i=0; i<links.length; i++){
                                var txt = links[i].textContent.trim();
                                var cls = links[i].className || '';
                                var href = links[i].href || '';
                                if(txt==='글쓰기' || cls.indexOf('write')>-1 || href.indexOf('ArticleWrite')>-1){
                                    return links[i].href;
                                }
                            }
                            return null;
                        """)
                        if write_btn_href:
                            self.driver.get(write_btn_href)
                            self.random_delay(3, 5)
                            write_btn = True  # 이미 이동했으므로 플래그만 세팅
                            print(f"  ✅ 글쓰기 페이지 직접 이동: {write_btn_href[:60]}")
                    except Exception as js_e:
                        print(f"  ❌ JS 버튼 탐색 실패: {js_e}")

                if not write_btn:
                    print("  ❌ 글쓰기 버튼 최종 실패")
                    if iframe_found:
                        self.driver.switch_to.default_content()
                    continue

                # 버튼 클릭 (이미 페이지 이동한 경우 skip)
                if write_btn is not True:
                    write_btn.click()
                self.random_delay(3, 5)

                # 새 창 처리
                windows = self.driver.window_handles
                new_window = len(windows) > 1
                if new_window:
                    self.driver.switch_to.window(windows[-1])
                    self.random_delay(2, 3)

                # 제목 입력 (다양한 방법 시도)
                title_success = False

                # 방법 1: textarea (구형 에디터)
                try:
                    for title_input in self.driver.find_elements(By.TAG_NAME, 'textarea'):
                        if title_input.is_displayed():
                            title_input.click()
                            self.random_delay(0.5, 1)
                            title_input.clear()
                            title_input.send_keys(post_title)
                            self.random_delay(0.5, 1)
                            if title_input.get_attribute('value'):
                                title_success = True
                                print("  ✅ 제목 입력 완료 (textarea)")
                            break
                except Exception:
                    pass

                # 방법 2: input[type=text] / 제목 placeholder (신형 에디터)
                if not title_success:
                    title_selectors = [
                        'input[placeholder*="제목"]',
                        'input.se-input-title',
                        'input[name="subject"]',
                        'input[name="title"]',
                        '.se-title-input input',
                        '#subject',
                        '#title',
                    ]
                    for sel in title_selectors:
                        try:
                            el = self.driver.find_element(By.CSS_SELECTOR, sel)
                            if el.is_displayed():
                                el.click()
                                self.random_delay(0.3, 0.6)
                                el.clear()
                                el.send_keys(post_title)
                                self.random_delay(0.3, 0.6)
                                title_success = True
                                print(f"  ✅ 제목 입력 완료 ({sel})")
                                break
                        except Exception:
                            continue

                # 방법 3: contenteditable 제목 영역
                if not title_success:
                    try:
                        editable_els = self.driver.find_elements(
                            By.CSS_SELECTOR, '[contenteditable="true"]'
                        )
                        for el in editable_els:
                            placeholder = el.get_attribute('data-placeholder') or ''
                            aria_label = el.get_attribute('aria-label') or ''
                            if '제목' in placeholder or '제목' in aria_label:
                                el.click()
                                self.random_delay(0.3, 0.6)
                                el.send_keys(Keys.CONTROL, 'a')
                                el.send_keys(post_title)
                                title_success = True
                                print("  ✅ 제목 입력 완료 (contenteditable)")
                                break
                    except Exception:
                        pass

                if not title_success:
                    print("  ❌ 제목 입력 실패 - 작업 중단")
                    try:
                        if new_window and len(self.driver.window_handles) > 1:
                            self.driver.close()
                            self.driver.switch_to.window(windows[0])
                        if iframe_found:
                            self.driver.switch_to.default_content()
                    except Exception:
                        pass
                    return None

                # 본문 입력 (3가지 방법 시도)
                self.random_delay(1, 2)
                content_success = False

                # 방법 1: p.se-text-paragraph 클릭 후 직접 입력
                try:
                    paragraph = self.driver.find_element(By.CSS_SELECTOR, "p.se-text-paragraph")
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", paragraph)
                    self.random_delay(0.5, 1)
                    paragraph.click()
                    self.random_delay(0.5, 1)
                    active = self.driver.switch_to.active_element
                    active.send_keys(".")
                    self.random_delay(0.2, 0.3)
                    active.send_keys(Keys.CONTROL, 'a')
                    self.random_delay(0.2, 0.3)
                    active.send_keys(post_body)
                    self.random_delay(0.5, 1)
                    check = self.driver.execute_script(
                        "var s=document.querySelector('span.__se-node'); return s && s.textContent.length > 0;"
                    )
                    if check:
                        content_success = True
                        print("  ✅ 본문 입력 완료 (직접 입력)")
                except Exception as e:
                    print(f"  ℹ️  직접 입력 실패: {e}")

                # 방법 2: JavaScript 강제 입력
                if not content_success:
                    try:
                        result = self.driver.execute_script("""
                            var content = arguments[0];
                            var placeholder = document.querySelector('.se-placeholder');
                            if (placeholder) { placeholder.style.display='none'; placeholder.remove(); }
                            var textNode = document.querySelector('span.__se-node');
                            var paragraph = document.querySelector('p.se-text-paragraph');
                            if (!textNode && paragraph) {
                                textNode = document.createElement('span');
                                textNode.className = 'se-ff-system se-fs15 __se-node';
                                textNode.style.color = 'rgb(0,0,0)';
                                paragraph.appendChild(textNode);
                            }
                            if (textNode) {
                                textNode.textContent = content;
                                textNode.innerText = content;
                                var module = document.querySelector('.se-module');
                                if (module) module.classList.remove('se-is-empty');
                                if (paragraph) {
                                    paragraph.dispatchEvent(new Event('input', {bubbles:true}));
                                    paragraph.dispatchEvent(new Event('change', {bubbles:true}));
                                    paragraph.click(); paragraph.focus();
                                }
                                return textNode.textContent.length > 0;
                            }
                            return false;
                        """, post_body)
                        if result:
                            content_success = True
                            print("  ✅ 본문 입력 완료 (JavaScript)")
                    except Exception as e:
                        print(f"  ℹ️  JS 입력 실패: {e}")

                # 방법 3: 클립보드 붙여넣기
                if not content_success:
                    try:
                        import pyperclip
                        paragraph = self.driver.find_element(By.CSS_SELECTOR, "p.se-text-paragraph")
                        paragraph.click()
                        self.random_delay(0.5, 1)
                        pyperclip.copy(post_body)
                        self.driver.switch_to.active_element.send_keys(Keys.CONTROL, 'v')
                        self.random_delay(0.5, 1)
                        content_success = True
                        print("  ✅ 본문 입력 완료 (클립보드)")
                    except Exception as e:
                        print(f"  ℹ️  클립보드 입력 실패: {e}")

                if not content_success:
                    print("  ⚠️  본문 입력 실패 - 등록 계속 시도")

                # 댓글 비허용 처리 (코멘트 체크박스 해제)
                self.random_delay(1, 2)
                try:
                    cb = self.driver.find_element(By.ID, "coment")
                    if cb.is_selected():
                        try:
                            self.driver.find_element(By.CSS_SELECTOR, "label[for='coment']").click()
                        except Exception:
                            cb.click()
                        print("  ✅ 댓글 허용 해제")
                except Exception:
                    try:
                        self.driver.execute_script("""
                            var cb=document.getElementById('coment');
                            if(cb && cb.checked){cb.checked=false;cb.dispatchEvent(new Event('change',{bubbles:true}));}
                        """)
                    except Exception:
                        pass

                # 등록 버튼 클릭
                self.random_delay(2, 3)
                submit_success = False
                try:
                    btn = self.driver.find_element(By.XPATH, '//*[@id="app"]/div/div/section/div/div[1]/div/a')
                    btn.click()
                    submit_success = True
                    print("  ✅ 등록 버튼 클릭 (XPath)")
                except Exception:
                    for by, value in [
                        (By.XPATH, '//a[contains(text(), "등록")]'),
                        (By.XPATH, '//button[contains(text(), "등록")]'),
                        (By.CSS_SELECTOR, 'a.btn'),
                        (By.CSS_SELECTOR, 'button.btn'),
                    ]:
                        try:
                            for elem in self.driver.find_elements(by, value):
                                if elem.is_displayed() and ("등록" in elem.text or "작성" in elem.text):
                                    elem.click()
                                    submit_success = True
                                    break
                            if submit_success:
                                break
                        except Exception:
                            continue

                # Alert 처리
                self.random_delay(2, 3)
                try:
                    alert = self.driver.switch_to.alert
                    alert_text = alert.text
                    alert.accept()
                    print(f"  ℹ️  Alert 닫음: {alert_text}")
                except Exception:
                    pass

                # URL 캡처
                self.random_delay(3, 5)
                post_url = None
                try:
                    current = self.driver.current_url
                    if "articleid=" in current.lower():
                        post_url = current
                    elif "cafe.naver.com" in current:
                        try:
                            if not new_window:
                                self.driver.switch_to.default_content()
                                cafe_iframe = self.driver.find_element(By.ID, "cafe_main")
                                self.driver.switch_to.frame(cafe_iframe)
                            links = self.driver.find_elements(By.XPATH, "//a[contains(@href,'articleid=')]")
                            if links:
                                post_url = links[0].get_attribute('href')
                        except Exception:
                            pass
                    if not post_url:
                        post_url = current
                    print(f"  ✅ 글 URL 캡처: {post_url[:80]}...")
                except Exception as e:
                    print(f"  ❌ URL 캡처 실패: {e}")

                # 창 정리
                try:
                    if new_window and len(self.driver.window_handles) > 1:
                        self.driver.close()
                        self.driver.switch_to.window(windows[0])
                    if iframe_found:
                        self.driver.switch_to.default_content()
                except Exception:
                    pass

                print(f"  ✅ 신규발행 인사글 완료: {post_url}")
                return post_url

            except Exception as e:
                print(f"  ❌ 신규발행 오류 (시도 {attempt+1}): {e}")
                import traceback
                traceback.print_exc()
                try:
                    if len(self.driver.window_handles) > 1:
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    self.random_delay(3, 5)

        print("  ❌ 신규발행 최종 실패")
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
                
                # ⭐ 댓글/대댓글 작성 후 ID 추출 (모두!)
                comment_id = None
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
                        # 대댓글이면 True 반환 (ID 없어도 성공!)
                        if is_reply:
                            comment_id = "reply_success"
                except Exception as e:
                    print(f"  ⚠️ 댓글 ID 추출 오류: {e}")
                    # 대댓글이면 True 반환
                    if is_reply:
                        comment_id = "reply_success"
                
                print(f"✅ {comment_type} 작성 완료")
                
                # ⭐ 작업 완료 후 탭 닫기
                print("📑 작업 탭 닫기...")
                self.driver.close()
                self.driver.switch_to.window(original_window)
                print("✅ 네이버 홈 탭으로 복귀 완료")
                
                # 댓글/대댓글 모두 ID 반환 (다음 대댓글의 부모가 될 수 있음!)
                return comment_id
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
                
                # ⭐ run_in_executor: Selenium(동기)을 스레드에서 실행 → event loop 살림
                loop = asyncio.get_event_loop()
                if draft_url:
                    print(f"🔄 수정 발행: {draft_url[:50]}...")
                    _image_urls = task.get('image_urls') or []
                    _keyword = task.get('keyword') or None
                    if _image_urls:
                        print(f"   📸 이미지 {len(_image_urls)}장 포함")
                    if _keyword:
                        print(f"   🏷️  태그 키워드: {_keyword}")
                    post_url = await loop.run_in_executor(
                        None,
                        lambda: self.modify_post(
                            draft_url, task['title'], task['content'],
                            task.get('target_board'), _image_urls, _keyword
                        )
                    )
                else:
                    print(f"📝 새 글 작성: {task['cafe_url']}")
                    post_url = await loop.run_in_executor(
                        None,
                        lambda: self.write_post(task['cafe_url'], task['title'], task['content'])
                    )
                
                if post_url:
                    # ⭐ 공통 완료 보고 함수 사용 (실패 시 큐에 저장)
                    await self.report_task_complete(task_id, post_url=post_url)
                    
                    # WebSocket으로도 전송 (백업)
                    try:
                        await self.websocket.send(json.dumps({
                            'type': 'task_completed',
                            'task_id': task_id,
                            'post_url': post_url
                        }))
                    except:
                        pass
                else:
                    raise Exception("글 작성/수정 실패")
                
            elif task_type == 'create_draft':
                # 신규발행 인사글 작성
                cafe_url = task.get('cafe_url')
                draft_title = task.get('draft_title', '안녕하세요')
                draft_body = task.get('draft_body', '안녕하세요! 오늘 카페에 새로 가입했습니다.\n앞으로 잘 부탁드립니다! ^^')

                print(f"📋 신규발행 정보:")
                print(f"   카페 URL: {cafe_url}")
                print(f"   제목: {draft_title}")

                loop = asyncio.get_event_loop()
                post_url = await loop.run_in_executor(
                    None,
                    lambda: self.create_draft_post(cafe_url, draft_title, draft_body)
                )

                if post_url:
                    await self.report_task_complete(task_id, post_url=post_url)
                    try:
                        await self.websocket.send(json.dumps({
                            'type': 'task_completed',
                            'task_id': task_id,
                            'post_url': post_url
                        }))
                    except Exception:
                        pass
                else:
                    raise Exception("신규발행 인사글 작성 실패")

            elif task_type in ['comment', 'reply']:
                # 댓글 작성
                is_reply = (task_type == 'reply')
                parent_comment_id = task.get('parent_comment_id')
                
                print(f"📋 댓글 정보:")
                print(f"   타입: {task_type}")
                print(f"   is_reply: {is_reply}")
                print(f"   parent_comment_id: {parent_comment_id}")
                print(f"   post_url: {task['post_url'][:80] if task.get('post_url') else 'None'}...")
                
                # ⭐ run_in_executor: Selenium(동기)을 스레드에서 실행 → event loop 살림
                loop = asyncio.get_event_loop()
                post_url_for_comment = task['post_url']
                content_for_comment = task['content']
                result = await loop.run_in_executor(
                    None,
                    lambda: self.write_comment(
                        post_url_for_comment,
                        content_for_comment,
                        is_reply=is_reply,
                        parent_comment_id=parent_comment_id
                    )
                )
                
                if result:
                    # ⭐ 공통 완료 보고 함수 사용 (실패 시 큐에 저장)
                    cafe_comment_id = result if isinstance(result, str) else None
                    await self.report_task_complete(task_id, cafe_comment_id=cafe_comment_id)
                    
                    # WebSocket으로도 전송 (백업)
                    try:
                        message = {
                            'type': 'task_completed',
                            'task_id': task_id
                        }
                        if isinstance(result, str):
                            message['cafe_comment_id'] = result
                        await self.websocket.send(json.dumps(message))
                    except:
                        pass
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

