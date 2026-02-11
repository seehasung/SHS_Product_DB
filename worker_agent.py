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


class NaverCafeWorker:
    """네이버 카페 자동 작성 Worker"""
    
    VERSION = "1.0.1"  # 현재 버전
    
    def __init__(self, pc_number: int, server_url: str = "scorp274.com"):
        self.pc_number = pc_number
        self.server_url = server_url
        self.driver = None
        self.websocket = None
        self.current_account = None
        self.is_running = False
        
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
            
            # 버전 비교
            if server_version == self.VERSION:
                print(f"✅ 최신 버전입니다 (v{self.VERSION})")
                return False
            
            # 새 버전 발견
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
            current_file = Path(__file__)
            backup_file = current_file.with_suffix('.py.backup')
            
            import shutil
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
                ping_interval=30,  # 30초로 늘림
                ping_timeout=30,   # 30초로 늘림
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
            import pyperclip
            from selenium.webdriver.common.keys import Keys
            
            # ⭐ 1. 네이버 메인 먼저 접속
            self.driver.get('https://www.naver.com')
            self.random_delay(2, 3)
            
            # ⭐ 2. 로그인 페이지로 이동
            self.driver.get('https://nid.naver.com/nidlogin.login')
            self.random_delay(2, 3)
            
            # ⭐ 3. ID 입력 (pyperclip + Ctrl+V)
            id_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, 'id'))
            )
            id_input.click()
            self.random_delay(0.5, 1)
            
            pyperclip.copy(account_id)
            id_input.send_keys(Keys.CONTROL, 'v')
            self.random_delay(0.5, 1)
            
            # ⭐ 4. PW 입력 (pyperclip + Ctrl+V)
            pw_input = self.driver.find_element(By.ID, 'pw')
            pw_input.click()
            self.random_delay(0.5, 1)
            
            pyperclip.copy(account_pw)
            pw_input.send_keys(Keys.CONTROL, 'v')
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
                return False
                
        except Exception as e:
            print(f"❌ 로그인 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
        
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
        """댓글/대댓글 작성 (봇 감지 우회)"""
        comment_type = "대댓글" if is_reply else "댓글"
        print(f"💬 {comment_type} 작성 시작: {content[:30]}...")
        
        try:
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
            
            # ⭐ 댓글 내용 입력 (pyperclip - 이모지 지원)
            import pyperclip
            pyperclip.copy(content)
            comment_input.send_keys(Keys.CONTROL, 'v')
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
                return comment_id if not is_reply else True
            else:
                print("❌ 댓글 등록 버튼을 찾을 수 없습니다")
                return False
                
        except Exception as e:
            print(f"❌ {comment_type} 작성 오류: {e}")
            import traceback
            traceback.print_exc()
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
                # 글 작성
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
                    raise Exception("글 작성 실패")
                
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
                except json.JSONDecodeError:
                    print(f"⚠️ JSON 파싱 실패: {message[:50]}")
                    continue
                
                if data.get('type') == 'new_task':
                    task = data.get('task', {})
                    
                    if not task or 'id' not in task:
                        print("⚠️ 유효하지 않은 작업 데이터")
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
║     네이버 카페 자동화 Worker Agent v{self.VERSION}              ║
║                                                        ║
║     PC 번호: {self.pc_number:02d}                                    ║
║     서버: {self.server_url:40s} ║
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

