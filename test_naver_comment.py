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

def random_delay(min_sec=1, max_sec=2):
    time.sleep(random.uniform(min_sec, max_sec))

def human_type(element, text):
    """사람처럼 한 글자씩 입력"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)
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
            
            # 여러 가능한 선택자 시도
            selectors_to_try = [
                f"#cmt_{parent_comment_id}",
                f"div[id='cmt_{parent_comment_id}']",
                f"li[id='cmt_{parent_comment_id}']",
                f"//*[@id='cmt_{parent_comment_id}']"
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
            
            # 답글 버튼 찾기
            print("  🔍 답글 버튼 찾기...")
            reply_btn_selectors = [
                "a.comment_reply",
                "button.comment_reply",
                ".comment_reply",
                "//a[contains(text(), '답글')]",
                "//button[contains(text(), '답글')]",
                "//span[contains(text(), '답글')]"
            ]
            
            reply_clicked = False
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
        
        # 댓글 입력창 찾기
        print("  🔍 댓글 입력창 찾기...")
        
        input_selectors = [
            "textarea.comment_inbox",
            "textarea.comment_text_input",
            "textarea[placeholder*='댓글']",
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
        
        # 등록 버튼 찾기
        print("  🔍 등록 버튼 찾기...")
        
        submit_selectors = [
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
        # 로그인
        print("\n🔐 로그인...")
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        id_input = driver.find_element(By.ID, 'id')
        human_type(id_input, account_id)
        random_delay()
        
        pw_input = driver.find_element(By.ID, 'pw')
        human_type(pw_input, account_pw)
        random_delay()
        
        pw_input.send_keys(Keys.ENTER)
        random_delay(3, 5)
        
        if 'nid.naver.com' in driver.current_url:
            input("캡챠 해결 후 Enter...")
        
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



