"""
네이버 카페 댓글 작성 테스트
정확한 선택자 파악 및 작동 확인

실행: python test_naver_comment.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random

# ⭐ undetected-chromedriver (캡챠 우회)
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
    print("✅ undetected-chromedriver 사용 가능")
except ImportError:
    UNDETECTED_AVAILABLE = False
    print("⚠️ undetected_chromedriver가 없습니다. 일반 ChromeDriver 사용")
    print("   설치 권장: pip install undetected-chromedriver")

def random_delay(min_sec=1, max_sec=2):
    time.sleep(random.uniform(min_sec, max_sec))

def human_type(element, text):
    """사람처럼 한 글자씩 입력"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))

def setup_driver():
    """브라우저 초기화 (봇 감지 우회)"""
    if UNDETECTED_AVAILABLE:
        # ⭐ undetected-chromedriver (캡챠 우회!)
        print("🚀 undetected-chromedriver로 브라우저 실행")
        
        options = uc.ChromeOptions()
        options.add_argument('--log-level=3')
        
        driver = uc.Chrome(options=options, version_main=None)
        driver.set_window_size(1400, 900)
        
        print("✅ 고급 봇 감지 우회 활성화")
        return driver
    else:
        # 일반 ChromeDriver
        print("🚀 일반 ChromeDriver로 브라우저 실행")
        
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument('--log-level=3')
        
        driver = webdriver.Chrome(options=options)
        
        # WebDriver 속성 숨기기
        try:
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })
        except:
            pass
        
        driver.set_window_size(1400, 900)
        return driver

def write_comment(driver, post_url, comment_text, is_reply=False, parent_comment_id=None):
    """
    댓글/대댓글 작성
    
    Args:
        driver: Selenium WebDriver
        post_url: 글 URL
        comment_text: 댓글 내용
        is_reply: 대댓글 여부
        parent_comment_id: 부모 댓글 ID (대댓글인 경우)
    """
    print(f"\n{'💬 대댓글' if is_reply else '💬 댓글'} 작성 시작...")
    print(f"  내용: {comment_text}")
    
    try:
        # 글 URL 접속
        print(f"  📄 글 접속: {post_url}")
        driver.get(post_url)
        random_delay(3, 5)
        
        # iframe 전환
        print("  🔄 iframe 전환 중...")
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        random_delay(2, 3)
        print("  ✅ iframe 전환 완료")
        
        if is_reply and parent_comment_id:
            # 대댓글 작성
            print(f"  🔍 부모 댓글 찾기 (ID: {parent_comment_id})...")
            
            # ⭐ 네이버 카페 실제 구조: <li id="510247118">
            # 숫자로 시작하는 ID는 속성 선택자 사용!
            selectors_to_try = [
                f"[id='{parent_comment_id}']",  # ⭐ 속성 선택자 (가장 확실)
                f"li[id='{parent_comment_id}']",
                f"div[id='{parent_comment_id}']",
                f"//*[@id='{parent_comment_id}']"
            ]
            
            parent_found = False
            for selector in selectors_to_try:
                try:
                    if selector.startswith('/'):
                        parent_elem = driver.find_element(By.XPATH, selector)
                    else:
                        parent_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    parent_found = True
                    print(f"  ✅ 부모 댓글 발견: {selector}")
                    break
                except:
                    continue
            
            if not parent_found:
                print("  ⚠️ 부모 댓글을 찾을 수 없습니다. 수동으로 확인 필요")
                input("  브라우저에서 부모 댓글을 확인하고 Enter...")
            
            # ⭐ 답글쓰기 버튼 찾기 (실제 네이버 카페 구조)
            print("  🔍 답글쓰기 버튼 찾기...")
            
            reply_clicked = False
            try:
                # ⭐ 실제 구조: <a class="comment_info_button">답글쓰기</a>
                buttons = parent_elem.find_elements(By.CSS_SELECTOR, "a.comment_info_button")
                for btn in buttons:
                    if "답글" in btn.text:
                        btn.click()
                        reply_clicked = True
                        print(f"  ✅ 답글쓰기 버튼 클릭")
                        random_delay(1, 2)
                        break
            except:
                pass
            
            # 다른 선택자들도 시도
            if not reply_clicked:
                reply_btn_selectors = [
                    "a.comment_reply",
                    "button.comment_reply",
                    ".comment_reply",
                    "//a[contains(text(), '답글')]",
                    "//button[contains(text(), '답글')]"
                ]
                
                for selector in reply_btn_selectors:
                    try:
                        if selector.startswith('/'):
                            reply_btn = parent_elem.find_element(By.XPATH, selector)
                        else:
                            reply_btn = parent_elem.find_element(By.CSS_SELECTOR, selector)
                        
                        reply_btn.click()
                        reply_clicked = True
                        print(f"  ✅ 답글 버튼 클릭: {selector}")
                        random_delay(1, 2)
                        break
                    except:
                        continue
            
            if not reply_clicked:
                print("  ⚠️ 답글 버튼을 찾을 수 없습니다")
                input("  브라우저에서 답글 버튼을 클릭하고 Enter...")
        
        # ⭐ 댓글 입력창 찾기 (실제 네이버 카페 구조)
        print("  🔍 댓글 입력창 찾기...")
        
        input_selectors = [
            "textarea.comment_inbox_text",  # ⭐ 실제 class!
            "textarea[placeholder*='댓글']",
            "textarea.comment_inbox",
            "textarea.comment_text_input",
            "div.comment_inbox textarea",
            "#comment_text_input",
            ".comment_write textarea"
        ]
        
        comment_input = None
        for selector in input_selectors:
            try:
                comment_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"  ✅ 입력창 발견: {selector}")
                break
            except:
                continue
        
        if not comment_input:
            print("  ❌ 댓글 입력창을 찾을 수 없습니다!")
            print("  브라우저 개발자 도구(F12)로 확인 필요")
            input("  Enter로 계속...")
            return False
        
        # 댓글 입력
        print("  ✍️ 댓글 입력 중...")
        comment_input.click()
        random_delay(0.5, 1)
        human_type(comment_input, comment_text)
        print(f"  ✅ 입력 완료: {comment_text}")
        
        # ⭐ 등록 버튼 찾기 (실제 네이버 카페 구조)
        print("  🔍 등록 버튼 찾기...")
        
        submit_selectors = [
            "a.btn_register",  # ⭐ 실제 class!
            "a.button.btn_register",
            "button.btn_register",
            "button.comment_submit",
            "a.comment_submit",
            "button[class*='submit']",
            "a[class*='submit']",
            "//button[contains(text(), '등록')]",
            "//a[contains(text(), '등록')]"
        ]
        
        submit_btn = None
        for selector in submit_selectors:
            try:
                if selector.startswith('/'):
                    submit_btn = driver.find_element(By.XPATH, selector)
                else:
                    submit_btn = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"  ✅ 등록 버튼 발견: {selector}")
                break
            except:
                continue
        
        if not submit_btn:
            print("  ⚠️ 등록 버튼을 찾을 수 없습니다")
            print("  수동으로 등록 버튼을 눌러주세요")
            input("  등록 후 Enter...")
            return True
        
        # 등록
        print("  📤 등록 버튼 클릭...")
        submit_btn.click()
        random_delay(2, 3)
        
        print("  ✅ 댓글 등록 완료!")
        return True
        
    except Exception as e:
        print(f"  ❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("""
╔════════════════════════════════════════════════════════╗
║  네이버 카페 댓글 작성 테스트                          ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    post_url = input("글 URL: ").strip()
    
    print("\n=== 테스트 모드 선택 ===")
    print("1. 새 댓글 작성")
    print("2. 대댓글 작성")
    mode = input("선택 (1/2): ").strip()
    
    comment_text = input("\n댓글 내용: ").strip()
    
    parent_comment_id = None
    if mode == '2':
        parent_comment_id = input("부모 댓글 ID (예: 12345): ").strip()
    
    driver = setup_driver()
    
    try:
        import pyperclip
        
        # ⭐ 로그인 (캡챠 우회 버전)
        print("\n🔐 로그인...")
        
        # 1. 네이버 메인 먼저 접속
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        
        # 2. 로그인 페이지로 이동
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        # 3. ID 입력 (pyperclip + Ctrl+V)
        id_input = driver.find_element(By.ID, 'id')
        id_input.click()
        random_delay(0.5, 1)
        
        pyperclip.copy(account_id)
        id_input.send_keys(Keys.CONTROL, 'v')
        random_delay(0.5, 1)
        
        # 4. PW 입력 (pyperclip + Ctrl+V)
        pw_input = driver.find_element(By.ID, 'pw')
        pw_input.click()
        random_delay(0.5, 1)
        
        pyperclip.copy(account_pw)
        pw_input.send_keys(Keys.CONTROL, 'v')
        random_delay(1, 2)
        
        # 5. 로그인 버튼 클릭
        login_btn = driver.find_element(By.ID, 'log.login')
        login_btn.click()
        random_delay(3, 5)
        
        # 6. 로그인 확인
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        
        try:
            logout_btn = driver.find_element(By.XPATH, '//*[@id="account"]/div[1]/div/button')
            if logout_btn:
                print("✅ 로그인 성공 (캡챠 없음!)")
        except:
            if 'nid.naver.com' in driver.current_url:
                print("⚠️ 캡챠 발생 가능성 있음")
                input("캡챠 해결 후 Enter...")
            else:
                print("✅ 로그인 완료")
        
        # 댓글 작성
        is_reply = (mode == '2')
        success = write_comment(
            driver, 
            post_url, 
            comment_text, 
            is_reply=is_reply,
            parent_comment_id=parent_comment_id
        )
        
        if success:
            print("\n" + "="*60)
            print("✅ 테스트 성공!")
            print("="*60)
            print("\n브라우저에서 댓글이 정상적으로 작성되었는지 확인하세요.")
        else:
            print("\n⚠️ 테스트 실패")
        
        input("\nEnter로 종료...")
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")



