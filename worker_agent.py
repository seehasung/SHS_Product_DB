"""
네이버 카페 자동화 Worker Agent
각 작업 PC에서 실행되는 프로그램

실행 방법:
    python worker_agent.py <PC번호>
    예: python worker_agent.py 1
"""

import subprocess
import sys

# ─────────────────────────────────────────────────────────────
# 필수 패키지 자동 설치 (최초 실행 시)
# ─────────────────────────────────────────────────────────────
def _auto_install(package: str, import_name: str = None):
    """패키지가 없으면 자동 설치"""
    name = import_name or package
    try:
        __import__(name)
    except ImportError:
        print(f"📦 {package} 설치 중...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package, "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            print(f"✅ {package} 설치 완료")
        except Exception as _e:
            print(f"⚠️ {package} 자동 설치 실패: {_e}")
            print(f"   직접 설치: pip install {package}")

_auto_install("undetected-chromedriver", "undetected_chromedriver")
_auto_install("pyperclip")
_auto_install("psutil")
_auto_install("requests")
_auto_install("websockets")
_auto_install("selenium")

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
    print("⚠️ undetected_chromedriver 로드 실패 - 일반 ChromeDriver 사용")
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
    print("⚠️ pyperclip 로드 실패 - 클립보드 로그인 불가")


class NaverCafeWorker:
    """네이버 카페 자동 작성 Worker"""
    
    VERSION = "2.6.0" # 현재 버전
    
    def __init__(self, pc_number: int, server_url: str = "scorp274.com"):
        self.pc_number = pc_number
        self.server_url = server_url
        self.driver = None
        self.websocket = None
        self.current_account = None
        self._saved_account_id = None   # 브라우저 복구 시 재로그인용
        self._saved_account_pw = None   # 브라우저 복구 시 재로그인용
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

    def _is_browser_alive(self) -> bool:
        """브라우저 세션이 살아있는지 확인"""
        try:
            _ = self.driver.window_handles
            return True
        except Exception:
            return False

    def _restart_browser_and_login(self) -> bool:
        """브라우저 창이 닫혔거나 세션이 죽은 경우 브라우저 재시작 + 재로그인"""
        print("🔄 브라우저 세션 오류 감지 → 브라우저 재시작 중...")
        try:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

            import time as _t
            _t.sleep(2)

            self.init_selenium()
            print("✅ 브라우저 재시작 완료")

            if self._saved_account_id and self._saved_account_pw:
                print(f"🔐 재로그인 시도: {self._saved_account_id}")
                login_ok = self.login_naver(self._saved_account_id, self._saved_account_pw)
                if login_ok:
                    print(f"✅ 재로그인 완료: {self._saved_account_id}")
                    return True
                else:
                    print(f"❌ 재로그인 실패: {self._saved_account_id}")
                    return False
            else:
                print("⚠️  저장된 계정 정보 없음 - 로그인 생략")
                return False
        except Exception as _e:
            print(f"❌ 브라우저 재시작 실패: {_e}")
            return False

    async def send_heartbeat(self):
        """주기적으로 서버에 상태 전송 (10초마다) + 브라우저 생존 감시"""
        _browser_check_counter = 0
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

                # ⭐ 30초마다 브라우저 생존 확인 (매 3번째 heartbeat = 30초)
                _browser_check_counter += 1
                if _browser_check_counter >= 3:
                    _browser_check_counter = 0
                    if not self._is_browser_alive():
                        print("⚠️  [Heartbeat] 브라우저 사망 감지 → 자동 재시작...")
                        recovered = self._restart_browser_and_login()
                        if recovered:
                            print("✅ [Heartbeat] 브라우저 복구 완료")
                        else:
                            print("❌ [Heartbeat] 브라우저 복구 실패 - 30초 후 재시도")

                await asyncio.sleep(10)
            except websockets.exceptions.ConnectionClosed:
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

    def _check_naver_modal(self) -> str | None:
        """네이버 HTML 모달 팝업 감지 (활동 정지, 글쓰기 불가 등)
        현재 컨텍스트(default_content 또는 iframe)에서 모달 텍스트 반환, 없으면 None"""
        _modal_selectors = [
            '.cafe-modal-wrap',
            '.AlertModal',
            '.error-message-wrap',
            '[class*="modal"][class*="alert"]',
            '[class*="Modal"]',
            '.se-popup-background',
            '.popup_wrap',
            '.layer_popup',
            '.dialog_wrap',
            '.notice_msg',
            '.error_content',
        ]
        try:
            for _sel in _modal_selectors:
                try:
                    for _el in self.driver.find_elements(By.CSS_SELECTOR, _sel):
                        if _el.is_displayed():
                            _txt = _el.text.strip()
                            if _txt and len(_txt) > 5:
                                return _txt[:200]
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def dismiss_alert(self, accept: bool = True) -> str | None:
        """Alert/Confirm 다이얼로그가 열려 있으면 닫고 텍스트 반환, 없으면 None"""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
            text = alert.text
            if accept:
                alert.accept()
            else:
                alert.dismiss()
            print(f"   ⚠️  Alert 닫힘: {text}")
            return text
        except Exception:
            return None

    @staticmethod
    def _truncate_title(title: str, max_bytes: int = 190) -> str:
        """제목을 byte 길이 기준으로 잘라서 반환 (네이버 제한: 200byte)"""
        encoded = title.encode('utf-8')
        if len(encoded) <= max_bytes:
            return title
        # 바이트 수 기준으로 자르되 완전한 문자(유니코드)만 포함
        truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
        print(f"   ⚠️  제목 자동 축약: {len(title)}자 → {len(truncated)}자 (byte초과)")
        return truncated

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
            # fal.ai / CDN 403 방지: 브라우저처럼 보이는 헤더 추가
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://cafe.naver.com/',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-fetch-dest': 'image',
                'sec-fetch-mode': 'no-cors',
                'sec-fetch-site': 'cross-site',
            }
            print(f"   🔗 이미지 다운로드 시도: {image_url[:80]}...")
            response = req.get(image_url, headers=headers, timeout=60, verify=False, allow_redirects=True)
            if response.status_code == 200:
                temp_dir = tempfile.gettempdir()
                # 확장자 추론
                content_type = response.headers.get('Content-Type', 'image/jpeg')
                ext = 'jpg'
                if 'png' in content_type:
                    ext = 'png'
                elif 'webp' in content_type:
                    ext = 'webp'
                filename = f"cafe_img_{int(time.time() * 1000)}.{ext}"
                temp_path = os.path.join(temp_dir, filename)
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                print(f"   ✅ 이미지 다운로드 완료: {filename} ({len(response.content)//1024}KB)")
                return temp_path
            else:
                print(f"   ❌ 이미지 다운로드 실패 (HTTP {response.status_code}): {image_url[:80]}")
                # 403인 경우 Referer 없이 재시도
                if response.status_code == 403:
                    print(f"   🔄 403 오류 - Referer 없이 재시도...")
                    headers2 = {k: v for k, v in headers.items() if k not in ('Referer', 'sec-fetch-site')}
                    headers2['sec-fetch-site'] = 'none'
                    response2 = req.get(image_url, headers=headers2, timeout=60, verify=False, allow_redirects=True)
                    if response2.status_code == 200:
                        temp_dir = tempfile.gettempdir()
                        filename = f"cafe_img_{int(time.time() * 1000)}.jpg"
                        temp_path = os.path.join(temp_dir, filename)
                        with open(temp_path, 'wb') as f:
                            f.write(response2.content)
                        print(f"   ✅ 재시도 다운로드 완료: {filename}")
                        return temp_path
                    else:
                        print(f"   ❌ 재시도도 실패 (HTTP {response2.status_code})")
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
        print(f"URL      : {draft_url}")
        print(f"제목     : {title}")
        print(f"본문 길이: {len(content)}자")
        print(f"본문 앞부분:")
        print(f"  {content[:300]}{'...' if len(content) > 300 else ''}")
        print(f"게시판   : {target_board or '변경 없음'}")
        print(f"키워드   : {keyword or '없음'}")
        print(f"이미지 수: {len(image_urls) if image_urls else 0}장")
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
                self.random_delay(1, 2)

                # ⭐ 수정 버튼 클릭 후 alert 팝업 최대 3초 반복 확인 (활동 정지 등 오류 팝업)
                import time as _ta_mod
                _alert_mod = None
                for _chk_mod in range(3):
                    _ta_mod.sleep(1)
                    _alert_mod = self.dismiss_alert(accept=True)
                    if _alert_mod:
                        break
                if _alert_mod:
                    print(f"❌ 수정 버튼 클릭 후 Alert 발생: {_alert_mod}")
                    raise Exception(f"[팝업 오류] {_alert_mod}")

                self.random_delay(3, 5)
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
            # ① \n 제거: Claude 응답이 "제목\nMenu" 형태로 오는 경우, \n을 human_type이 Enter키로 입력
            #    → Naver가 "줄바꿈 금지" 형식 오류를 "200byte 초과" 메시지로 표시
            # ② Tab 키 제거: 공지사항 있는 카페에서 잘못된 곳으로 포커스 이동됨
            clean_title = title.split('\n')[0].strip().strip('*').strip('#').strip()
            if clean_title != title:
                print(f"   ℹ️  제목 정리 (\\n 제거): '{title[:60]}' → '{clean_title}'")
            safe_title = self._truncate_title(clean_title, max_bytes=190)
            print(f"\n✍️ 제목 입력: {safe_title}")
            try:
                title_elem = self.driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
                title_elem.click()
                self.random_delay(0.5, 1)

                # JS로 기존 내용 초기화 (Ctrl+A+Delete 방식은 전체 페이지 선택될 위험 있음)
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.value = '';
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                """, title_elem)
                self.random_delay(0.3, 0.5)

                # 새 제목 타이핑 (줄바꿈 없는 순수 텍스트)
                self.human_type(title_elem, safe_title)
                self.random_delay(0.5, 1)
                print("   ✅ 제목 입력 완료")
            except Exception as e:
                print(f"   ⚠️  제목 입력 실패: {e}")

            # 제목 입력 후 혹시라도 Alert이 열려 있으면 즉시 닫기
            self.dismiss_alert(accept=True)
            self.random_delay(1, 2)

            # ── 본문 입력 ──────────────────────────────────────────────
            # ⚠️ 핵심 문제: 제목 입력 후 제목 textarea에 포커스가 남아 있으면
            #    본문을 클릭해도 active_element가 textarea → 본문이 제목란에 입력됨
            # 해결: ① 제목 포커스 강제 해제 ② ActionChains 실제 클릭 ③ 클립보드 붙여넣기 우선
            print(f"\n📝 본문 입력 시도... (총 {len(content)}자)")
            content_success = False

            # 공통: 제목란 포커스 강제 해제 후 본문 paragraph 찾기
            def _focus_body_editor():
                """본문 편집 영역에 포커스를 이동하고 paragraph 요소 반환"""
                # 1) 현재 포커스된 요소가 textarea(제목란)이면 강제 blur
                self.driver.execute_script("""
                    var el = document.activeElement;
                    if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
                        el.blur();
                    }
                """)
                self.random_delay(0.3, 0.5)

                # 2) 본문 paragraph 찾기
                para = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "div.se-content p.se-text-paragraph, .se-module-text p.se-text-paragraph"
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", para)
                self.random_delay(0.3, 0.5)

                # 3) ActionChains로 실제 마우스 클릭 (JS click()은 Smart Editor 이벤트 미작동)
                ActionChains(self.driver).move_to_element(para).click().perform()
                self.random_delay(0.5, 1)

                # 4) 클릭 후 active element 확인
                active = self.driver.switch_to.active_element
                tag = (active.tag_name or '').lower()
                print(f"   → 클릭 후 active element: <{tag}>")

                # 5) 여전히 textarea(제목)에 포커스 → 본문 span 직접 JS focus
                if tag in ('textarea', 'input'):
                    print("   ⚠️  여전히 제목란에 포커스 → JS로 본문 강제 포커스")
                    self.driver.execute_script("""
                        var para = document.querySelector('div.se-content p.se-text-paragraph');
                        if (para) {
                            para.click();
                            var span = para.querySelector('span.__se-node');
                            if (span) { span.click(); }
                        }
                    """)
                    self.random_delay(0.5, 1)
                    active = self.driver.switch_to.active_element
                    tag = (active.tag_name or '').lower()
                    print(f"   → 재시도 후 active element: <{tag}>")
                return para, active, tag

            # 방법 1 (우선순위): 클립보드 붙여넣기 - 포커스 위치에 무관하게 안전
            try:
                import pyperclip
                self.dismiss_alert()
                para, active, tag = _focus_body_editor()

                if tag not in ('textarea', 'input'):
                    # 포커스가 본문 쪽에 있음 → 클립보드 붙여넣기
                    pyperclip.copy(content)
                    active.send_keys(Keys.CONTROL + 'a')  # 기존 내용 전체 선택
                    self.random_delay(0.2, 0.3)
                    active.send_keys(Keys.CONTROL + 'v')  # 붙여넣기
                    self.random_delay(1, 2)
                    self.dismiss_alert()
                    check = self.driver.execute_script(
                        "var s=document.querySelector('div.se-content span.__se-node'); return s && s.textContent.length > 0;"
                    )
                    if check:
                        content_success = True
                        print("   ✅ 본문 입력 완료 (방법1: 클립보드 붙여넣기)")
                    else:
                        print("   ℹ️  방법1: 붙여넣기 확인 실패, 다음 방법 시도")
                else:
                    print("   ℹ️  방법1: 포커스가 제목란에 남아 있어 건너뜀")
            except Exception as e:
                self.dismiss_alert()
                print(f"   ℹ️  방법1 실패: {e}")

            # 방법 2: JavaScript로 span.__se-node에 직접 텍스트 주입
            if not content_success:
                try:
                    self.dismiss_alert()
                    result = self.driver.execute_script("""
                        var content = arguments[0];
                        var seContent = document.querySelector('div.se-content');
                        if (!seContent) seContent = document;
                        var placeholder = seContent.querySelector('.se-placeholder');
                        if (placeholder) { placeholder.style.display='none'; }
                        var textNode = seContent.querySelector('span.__se-node');
                        var paragraph = seContent.querySelector('p.se-text-paragraph');
                        if (!textNode && paragraph) {
                            textNode = document.createElement('span');
                            textNode.className = 'se-ff-system se-fs15 __se-node';
                            textNode.style.color = 'rgb(0,0,0)';
                            paragraph.appendChild(textNode);
                        }
                        if (textNode) {
                            textNode.textContent = content;
                            var module = seContent.querySelector('.se-module');
                            if (module) module.classList.remove('se-is-empty');
                            if (paragraph) {
                                paragraph.dispatchEvent(new Event('input', {bubbles:true}));
                                paragraph.dispatchEvent(new Event('change', {bubbles:true}));
                            }
                            return textNode.textContent.length > 0;
                        }
                        return false;
                    """, content)
                    self.dismiss_alert()
                    if result:
                        content_success = True
                        print("   ✅ 본문 입력 완료 (방법2: JavaScript 직접 주입)")
                except Exception as e:
                    self.dismiss_alert()
                    print(f"   ℹ️  방법2 실패: {e}")

            # 방법 3: ActionChains 클릭 후 직접 타이핑 (폴백)
            if not content_success:
                try:
                    self.dismiss_alert()
                    import pyperclip
                    # 제목 포커스 해제 후 ActionChains 클릭
                    self.driver.execute_script("if(document.activeElement) document.activeElement.blur();")
                    self.random_delay(0.3, 0.5)
                    paragraph = self.driver.find_element(
                        By.CSS_SELECTOR,
                        "div.se-content p.se-text-paragraph, .se-module-text p.se-text-paragraph"
                    )
                    ActionChains(self.driver).move_to_element(paragraph).click().perform()
                    self.random_delay(0.8, 1.2)
                    pyperclip.copy(content)
                    self.driver.switch_to.active_element.send_keys(Keys.CONTROL + 'v')
                    self.random_delay(1, 2)
                    self.dismiss_alert()
                    content_success = True
                    print("   ✅ 본문 입력 완료 (방법3: ActionChains+클립보드)")
                except Exception as e:
                    self.dismiss_alert()
                    print(f"   ℹ️  방법3 실패: {e}")

            if not content_success:
                print("   ⚠️ 본문 입력 실패 - 등록 계속 시도")

            # 이후 모든 단계 전에 Alert 완전 정리
            self.dismiss_alert()
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
                    self.dismiss_alert()  # 태그 입력 전 Alert 정리
                    tag_input = self.driver.find_element(By.CSS_SELECTOR, 'input.tag_input')
                    tag_input.click()
                    self.random_delay(0.5, 1)
                    self.human_type(tag_input, keyword)
                    tag_input.send_keys(Keys.ENTER)
                    self.random_delay(0.5, 1)
                    self.dismiss_alert()
                    print("   ✅ 태그 입력 완료")
                except Exception as e:
                    self.dismiss_alert()
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
            
            # 등록 버튼 클릭 전 Alert 완전 정리 (여러 번 시도)
            for _ in range(3):
                dismissed = self.dismiss_alert(accept=True)
                if dismissed is None:
                    break
                self.random_delay(0.5, 1)
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
                        # ⭐ 클릭 직후 alert 팝업 처리 (오류 팝업 뜨면 즉시 닫기)
                        import time as _ta
                        _ta.sleep(1)
                        alert_text = self.dismiss_alert(accept=True)
                        if alert_text:
                            print(f"   ⚠️  클릭 후 Alert 발생: {alert_text} → 닫고 계속 진행")
                        self.random_delay(1, 2)
                        
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
                        # ⭐ 예외 발생 시에도 alert 처리 시도
                        self.dismiss_alert(accept=True)
                        continue
                
                if clicked:
                    print("✅ 등록 버튼 자동 클릭 완료")
                    
                    # ⭐ 리다이렉트 대기 (실제 글 URL로 변경될 때까지)
                    print("⏳ 글 등록 후 리다이렉트 대기 중...")
                    import time
                    for i in range(15):  # 최대 15초
                        time.sleep(1)
                        # 대기 중 alert 팝업 즉시 처리
                        alert_text = self.dismiss_alert(accept=True)
                        if alert_text:
                            print(f"   ⚠️  리다이렉트 대기 중 Alert: {alert_text} → 닫음")
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
                            # 대기 중 alert 팝업 즉시 처리
                            alert_text = self.dismiss_alert(accept=True)
                            if alert_text:
                                print(f"   ⚠️  리다이렉트 대기 중 Alert: {alert_text} → 닫음")
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

                import re as _re

                # 버튼 클릭 (이미 페이지 이동한 경우 skip)
                if write_btn is not True:
                    write_btn.click()
                    print("  ✅ 글쓰기 버튼 클릭 완료")

                # 페이지 로딩 완료 대기 (최대 30초) → 완료 후 추가 2초 대기
                print("  ⏳ 에디터 페이지 로딩 대기 중...")
                try:
                    import time as _tload
                    _load_start = _tload.time()
                    while _tload.time() - _load_start < 30:
                        state = self.driver.execute_script("return document.readyState")
                        if state == "complete":
                            break
                        elapsed = int(_tload.time() - _load_start)
                        if elapsed % 5 == 0 and elapsed > 0:
                            print(f"  ⏳ 로딩 중... ({elapsed}초 경과)")
                        _tload.sleep(1)
                    else:
                        print("  ⚠️ 페이지 로딩 30초 타임아웃 (계속 진행)")
                    print(f"  ✅ 페이지 로딩 완료 ({int(_tload.time() - _load_start)}초 소요)")
                except Exception:
                    print("  ⚠️ 페이지 로딩 확인 실패 (계속 진행)")
                self.random_delay(2, 3)

                # 새 창 처리
                windows = self.driver.window_handles
                new_window = len(windows) > 1
                if new_window:
                    self.driver.switch_to.window(windows[-1])
                    # 새 창도 로딩 완료 대기
                    try:
                        _load_start2 = _tload.time()
                        while _tload.time() - _load_start2 < 30:
                            state2 = self.driver.execute_script("return document.readyState")
                            if state2 == "complete":
                                break
                            elapsed2 = int(_tload.time() - _load_start2)
                            if elapsed2 % 5 == 0 and elapsed2 > 0:
                                print(f"  ⏳ 새 창 로딩 중... ({elapsed2}초 경과)")
                            _tload.sleep(1)
                        print(f"  ✅ 새 창 로딩 완료")
                    except Exception:
                        pass
                    self.random_delay(1, 2)

                # iframe 전환 시도
                editor_iframe_found = False
                try:
                    self.driver.switch_to.default_content()
                    editor_frame = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "cafe_main"))
                    )
                    self.driver.switch_to.frame(editor_frame)
                    editor_iframe_found = True
                    print("  ✅ 에디터 iframe 전환 성공")
                except Exception:
                    pass

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
                    print(f"  ❌ 제목 입력 실패 - 탭 닫고 다음 작업 대기")
                    try:
                        self.driver.switch_to.default_content()
                        current_handles = self.driver.window_handles
                        for _h in current_handles[1:]:
                            self.driver.switch_to.window(_h)
                            self.driver.close()
                        self.driver.switch_to.window(current_handles[0])
                        print("  ✅ 탭 닫기 완료")
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

                # ★ URL 캡처 — 등록 후 자동으로 열리는 내 글 페이지의 URL 사용
                # 네이버 카페는 등록 완료 후 해당 글 페이지로 자동 redirect 됨
                from urllib.parse import unquote, parse_qs, urlparse

                def _extract_article_url(raw_url: str):
                    """URL에서 articleid를 추출하고 정규화된 글 URL 반환"""
                    # 직접 articleid 포함
                    m = _re.search(r'articleid=(\d+)', raw_url, _re.IGNORECASE)
                    if m:
                        return raw_url

                    # iframe_url_utf8 파라미터 안에 인코딩된 경우
                    # 예: ?iframe_url_utf8=%2FArticleRead.nhn%3Fclubid%3D...%26articleid%3D12345
                    try:
                        parsed = urlparse(raw_url)
                        qs = parse_qs(parsed.query)
                        for key in ['iframe_url_utf8', 'iframe_url']:
                            if key in qs:
                                decoded = unquote(unquote(qs[key][0]))  # 이중 인코딩 대응
                                m2 = _re.search(r'articleid=(\d+)', decoded, _re.IGNORECASE)
                                if m2:
                                    # 정규화된 URL 생성
                                    club_m = _re.search(r'clubid=(\d+)', decoded, _re.IGNORECASE)
                                    club_id = club_m.group(1) if club_m else ''
                                    article_id = m2.group(1)
                                    normalized = f"https://cafe.naver.com/ArticleRead.nhn?clubid={club_id}&articleid={article_id}"
                                    print(f"  ✅ iframe_url_utf8에서 articleid 추출: {article_id}")
                                    return normalized
                    except Exception:
                        pass
                    return None

                post_url = None
                try:
                    # 최대 15초 동안 현재 탭 URL이 articleid 포함 URL로 바뀌길 기다림
                    deadline = time.time() + 15
                    while time.time() < deadline:
                        current = self.driver.current_url
                        extracted = _extract_article_url(current)
                        if extracted:
                            post_url = extracted
                            print(f"  ✅ 내 글 URL 캡처 (redirect): {post_url[:80]}")
                            break
                        time.sleep(1)

                    # fallback: 새 창이 열렸을 경우 새 창 URL 확인
                    if not post_url:
                        try:
                            for handle in self.driver.window_handles:
                                self.driver.switch_to.window(handle)
                                url = self.driver.current_url
                                extracted = _extract_article_url(url)
                                if extracted:
                                    post_url = extracted
                                    print(f"  ✅ 내 글 URL 캡처 (새 탭): {post_url[:80]}")
                                    break
                        except Exception:
                            pass

                    if not post_url:
                        print(f"  ❌ URL 캡처 실패 — articleid를 찾지 못함 (현재: {self.driver.current_url[:80]})")

                    if post_url:
                        print(f"  ✅ 글 URL 캡처 완료: {post_url[:80]}...")
                except Exception as e:
                    print(f"  ❌ URL 캡처 오류: {e}")

                # 창 정리
                try:
                    self.driver.switch_to.default_content()
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

                # ★ 브라우저 창이 닫히거나 세션이 죽은 경우 → 재시작 후 재시도
                err_str = str(e).lower()
                is_browser_dead = (
                    'no such window' in err_str or
                    'target window already closed' in err_str or
                    'web view not found' in err_str or
                    'invalid session id' in err_str or
                    'session deleted' in err_str or
                    not self._is_browser_alive()
                )
                if is_browser_dead:
                    print("  ⚠️  브라우저 세션 사망 감지 → 재시작 시도...")
                    recovered = self._restart_browser_and_login()
                    if recovered:
                        print("  ✅ 브라우저 복구 완료 → 재시도합니다")
                    else:
                        print("  ❌ 브라우저 복구 실패 → 작업 중단")
                        break
                else:
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
            # ★ 작업 시작 전 브라우저 생존 확인 (NoSuchWindowException 사전 방어)
            if not self._is_browser_alive():
                print(f"⚠️  Task #{task_id} 시작 전 브라우저 세션 사망 감지 → 복구 시도...")
                recovered = self._restart_browser_and_login()
                if not recovered:
                    raise Exception("브라우저 복구 실패 - 작업 중단")
                print(f"✅ 브라우저 복구 완료 → 작업 재개")

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
                
                # 수신된 task 내용 상세 로그
                print(f"\n📋 [Task 수신 데이터]")
                print(f"   task_id     : {task_id}")
                print(f"   task_type   : {task_type}")
                print(f"   draft_url   : {task.get('draft_url', '없음')}")
                print(f"   title       : {task.get('title', '없음')}")
                _raw_content = task.get('content', '')
                print(f"   content 길이: {len(_raw_content)}자")
                if _raw_content:
                    print(f"   content 앞부분: {_raw_content[:200]}{'...' if len(_raw_content) > 200 else ''}")
                else:
                    print(f"   ⚠️  content가 비어있음!")
                print(f"   keyword     : {task.get('keyword', '없음')}")
                print(f"   image_urls  : {task.get('image_urls', [])}")
                print(f"   target_board: {task.get('target_board', '없음')}")
                
                # ⭐ run_in_executor: Selenium(동기)을 스레드에서 실행 → event loop 살림
                loop = asyncio.get_event_loop()
                if draft_url:
                    print(f"\n🔄 수정 발행: {draft_url[:50]}...")
                    _image_urls = task.get('image_urls') or []
                    _keyword = task.get('keyword') or None
                    if _image_urls:
                        print(f"   📸 이미지 {len(_image_urls)}장 포함")
                    if _keyword:
                        print(f"   🏷️  태그 키워드: {_keyword}")
                    try:
                        post_url = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda: self.modify_post(
                                    draft_url, task['title'], task['content'],
                                    task.get('target_board'), _image_urls, _keyword
                                )
                            ),
                            timeout=600  # 최대 10분 (이미지 3장 업로드 포함)
                        )
                    except asyncio.TimeoutError:
                        print(f"❌ 수정발행 타임아웃 (10분 초과) → 강제 실패 처리")
                        try:
                            _all_h = self.driver.window_handles
                            for _h in _all_h[1:]:
                                self.driver.switch_to.window(_h)
                                self.driver.close()
                            self.driver.switch_to.window(_all_h[0])
                        except Exception:
                            pass
                        raise Exception("수정발행 타임아웃 (활동정지 팝업 또는 로딩 지연)")
                else:
                    # draft_url이 없으면 수정 발행 불가 → 즉시 실패 처리
                    print(f"❌ draft_url이 없습니다. 수정 발행 URL이 서버에서 전달되지 않았습니다.")
                    print(f"   cafe_url: {task.get('cafe_url')}")
                    print(f"   이 작업은 반드시 기존 글 URL(draft_url)이 있어야 수행 가능합니다.")
                    raise Exception("draft_url 없음: 수정 발행할 URL이 지정되지 않았습니다. 서버에서 MODIFY_URL이 설정되지 않은 상태입니다.")
                
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
                try:
                    post_url = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.create_draft_post(cafe_url, draft_title, draft_body)
                        ),
                        timeout=180  # 최대 3분 (이미지 없는 단순 글쓰기)
                    )
                except asyncio.TimeoutError:
                    print(f"  ❌ 신규발행 타임아웃 (3분 초과) → 강제 실패 처리")
                    # 브라우저 탭 강제 닫기
                    try:
                        _all_h = self.driver.window_handles
                        for _h in _all_h[1:]:
                            self.driver.switch_to.window(_h)
                            self.driver.close()
                        self.driver.switch_to.window(_all_h[0])
                        print("  ✅ 타임아웃 탭 닫기 완료")
                    except Exception:
                        pass
                    raise Exception("신규발행 타임아웃 (활동정지 팝업 또는 로딩 지연)")

                if post_url:
                    # ⭐ ALERT: 접두사 = 팝업 오류 발생 (활동 정지 등)
                    if isinstance(post_url, str) and post_url.startswith('ALERT:'):
                        alert_msg = post_url[len('ALERT:'):]
                        print(f"  ❌ 글쓰기 팝업 오류: {alert_msg}")
                        raise Exception(f"[팝업 오류] {alert_msg}")
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
            # 오류 발생 시 서버에 알림 (WebSocket + HTTP 이중 보고)
            print(f"❌ 작업 실패: Task #{task_id} - {e}")

            # 1) WebSocket으로 실패 보고
            try:
                await self.websocket.send(json.dumps({
                    'type': 'task_failed',
                    'task_id': task_id,
                    'error': str(e)
                }))
                print(f"   📡 WebSocket 실패 보고 완료")
            except Exception as ws_err:
                print(f"   ⚠️ WebSocket 실패 보고 불가: {ws_err}")

            # 2) HTTP로도 실패 보고 (post 타입 + create_draft 타입 - 다음 그룹 트리거 목적)
            if task_type in ('post', 'create_draft'):
                try:
                    import requests as _req
                    _fail_url = f"https://{self.server_url}/automation/api/tasks/{task_id}/fail"
                    _r = _req.post(_fail_url, data={'error': str(e)}, timeout=15, verify=False)
                    if _r.status_code == 200:
                        print(f"   ✅ HTTP 실패 보고 완료 ({task_type})")
                    else:
                        print(f"   ⚠️ HTTP 실패 보고 응답: {_r.status_code}")
                except Exception as http_err:
                    print(f"   ⚠️ HTTP 실패 보고 오류: {http_err}")

            # ⭐ 실패 후 브라우저 생존 확인 → 죽었으면 자동 재시작
            err_str = str(e).lower()
            is_browser_dead = (
                'no such window' in err_str or
                'target window already closed' in err_str or
                'invalid session id' in err_str or
                'session deleted' in err_str or
                'web view not found' in err_str or
                not self._is_browser_alive()
            )
            if is_browser_dead:
                print(f"   ⚠️  브라우저 세션 사망 감지 → 자동 재시작 시도...")
                recovered = self._restart_browser_and_login()
                if recovered:
                    print(f"   ✅ 브라우저 복구 완료 → 다음 작업 대기")
                else:
                    print(f"   ❌ 브라우저 복구 실패 → 수동 재시작 필요")
            
    async def listen_for_tasks(self):
        """서버로부터 작업 수신"""
        # ★ 중복 실행 방지: 최근 처리한 task ID 집합 (set은 순서 없으므로 OrderedDict 유사 처리)
        _recently_completed_task_ids = set()
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
                    
                    # ★ 중복 실행 방지: 최근 완료/처리한 task ID 확인
                    _task_id_rcv = task['id']
                    if _task_id_rcv in _recently_completed_task_ids:
                        print(f"⚠️  Task #{_task_id_rcv} 이미 처리된 작업 → 건너뜀 (중복 방지)")
                        continue
                    
                    # 계정 로그인 확인
                    if task.get('account_id') and task['account_id'] != self.current_account:
                        print(f"🔄 계정 전환: {task['account_id']}")
                        if task.get('account_pw'):
                            self.login_naver(
                                task['account_id'],
                                task['account_pw']
                            )
                    
                    # 작업 처리 (예외가 나도 루프가 멈추지 않도록 try/except로 감쌈)
                    try:
                        await self.process_task(task)
                        # ★ 성공한 경우에만 중복 방지 set에 추가
                        _recently_completed_task_ids.add(_task_id_rcv)
                        if len(_recently_completed_task_ids) > 100:
                            _recently_completed_task_ids.discard(min(_recently_completed_task_ids))
                    except Exception as pt_err:
                        print(f"❌ process_task 처리 중 예상치 못한 오류: {pt_err}")
                        # 브라우저 죽었으면 재시작
                        if not self._is_browser_alive():
                            print("   ⚠️  브라우저 사망 → 자동 재시작 시도...")
                            self._restart_browser_and_login()
                        # 서버에 실패 보고
                        try:
                            await self.websocket.send(json.dumps({
                                'type': 'task_failed',
                                'task_id': task.get('id'),
                                'error': str(pt_err)
                            }))
                        except Exception:
                            pass
                        # HTTP 실패 보고 (post 타입)
                        if task.get('task_type') == 'post':
                            try:
                                import requests as _req2
                                _req2.post(
                                    f"https://{self.server_url}/automation/api/tasks/{task.get('id')}/fail",
                                    data={'error': str(pt_err)}, timeout=15, verify=False
                                )
                            except Exception:
                                pass
                    
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
                self._saved_account_id = account_id   # 복구용 저장
                self._saved_account_pw = account_pw   # 복구용 저장
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

