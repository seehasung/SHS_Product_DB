"""
간단한 댓글 테스트 스크립트
Claude 없이 직접 댓글 내용을 입력하여 테스트

실행: python test_comment_simple.py
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import pyperclip

def random_delay(min_sec=1, max_sec=2):
    time.sleep(random.uniform(min_sec, max_sec))

def setup_driver():
    """브라우저 초기화"""
    print("\n🚀 브라우저 초기화...")
    
    options = uc.ChromeOptions()
    options.add_argument('--log-level=3')
    
    driver = uc.Chrome(options=options, version_main=None)
    driver.set_window_size(1400, 900)
    
    print("✅ 브라우저 준비 완료")
    return driver

def login_naver(driver, account_id, account_pw):
    """네이버 로그인"""
    print(f"\n🔐 로그인: {account_id}")
    
    try:
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        # ID 입력
        id_input = driver.find_element(By.ID, 'id')
        id_input.click()
        random_delay(0.5, 1)
        pyperclip.copy(account_id)
        id_input.send_keys(Keys.CONTROL, 'v')
        random_delay(0.5, 1)
        
        # PW 입력
        pw_input = driver.find_element(By.ID, 'pw')
        pw_input.click()
        random_delay(0.5, 1)
        pyperclip.copy(account_pw)
        pw_input.send_keys(Keys.CONTROL, 'v')
        random_delay(1, 2)
        
        # 로그인 버튼 클릭
        login_btn = driver.find_element(By.ID, 'log.login')
        login_btn.click()
        random_delay(3, 5)
        
        # 로그인 확인 루프
        max_wait = 30
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            current_url = driver.current_url
            
            if "nid.naver.com" not in current_url:
                driver.get("https://www.naver.com")
                random_delay(2, 3)
            
            # 로그인 확인
            try:
                logout_btn = driver.find_element(By.XPATH, '//*[@id="account"]/div[1]/div/button')
                if logout_btn:
                    print("✅ 로그인 성공!")
                    return True
            except:
                pass
            
            # 캡챠 체크
            page_source = driver.page_source
            if "captcha" in page_source.lower():
                print("⚠️ 캡챠 발생")
                input("캡챠 해결 후 Enter...")
                continue
            
            time.sleep(1)
        
        print("❌ 로그인 시간 초과")
        return False
        
    except Exception as e:
        print(f"❌ 로그인 오류: {e}")
        return False

def write_comment(driver, post_url, comment_text):
    """새 댓글 작성"""
    print(f"\n💬 댓글 작성: {comment_text[:30]}...")
    
    try:
        driver.get(post_url)
        random_delay(3, 5)
        
        # iframe 전환
        try:
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'cafe_main'))
            )
            driver.switch_to.frame(iframe)
            random_delay(2, 3)
            print("  ✅ iframe 전환")
        except:
            print("  ⚠️ iframe 없음")
        
        # 댓글 입력창
        comment_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea.comment_inbox_text'))
        )
        comment_input.click()
        random_delay(0.5, 1)
        
        # 내용 입력 (pyperclip으로 붙여넣기 - 이모지 지원)
        pyperclip.copy(comment_text)
        comment_input.send_keys(Keys.CONTROL, 'v')
        random_delay(1, 2)
        
        # 등록 버튼
        submit_btn = driver.find_element(By.CSS_SELECTOR, 'a.btn_register')
        submit_btn.click()
        random_delay(3, 4)
        
        print("  ✅ 댓글 작성 완료!")
        
        # 댓글 ID 추출
        try:
            random_delay(2, 3)
            latest_comment = driver.find_element(By.CSS_SELECTOR, "ul.comment_list > li.CommentItem:last-of-type")
            comment_id = latest_comment.get_attribute('id')
            print(f"  📌 댓글 ID: {comment_id}")
            return comment_id
        except:
            print("  ⚠️ 댓글 ID 추출 실패")
            return None
        
    except Exception as e:
        print(f"  ❌ 댓글 작성 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

def write_reply(driver, post_url, parent_comment_id, comment_text):
    """대댓글 작성"""
    print(f"\n💬 대댓글 작성: {comment_text[:30]}...")
    print(f"  부모 댓글 ID: {parent_comment_id}")
    
    try:
        driver.get(post_url)
        random_delay(3, 5)
        
        # iframe 전환
        try:
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'cafe_main'))
            )
            driver.switch_to.frame(iframe)
            random_delay(2, 3)
        except:
            pass
        
        # 부모 댓글 찾기 (숫자 ID는 속성 선택자 사용!)
        print(f"  🔍 부모 댓글 찾기...")
        parent_elem = driver.find_element(By.CSS_SELECTOR, f"[id='{parent_comment_id}']")
        
        # 답글쓰기 버튼 찾기
        buttons = parent_elem.find_elements(By.CSS_SELECTOR, "a.comment_info_button")
        reply_clicked = False
        for btn in buttons:
            if "답글" in btn.text:
                btn.click()
                random_delay(1, 2)
                print("  ✅ 답글쓰기 클릭")
                reply_clicked = True
                break
        
        if not reply_clicked:
            print("  ⚠️ 답글쓰기 버튼을 찾을 수 없습니다")
            return False
        
        # 댓글 입력창 (대댓글용)
        comment_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea.comment_inbox_text'))
        )
        comment_input.click()
        random_delay(0.5, 1)
        
        # 내용 입력 (pyperclip으로 붙여넣기 - 이모지 지원)
        pyperclip.copy(comment_text)
        comment_input.send_keys(Keys.CONTROL, 'v')
        random_delay(1, 2)
        
        # 등록 버튼
        submit_btn = driver.find_element(By.CSS_SELECTOR, 'a.btn_register')
        submit_btn.click()
        random_delay(2, 3)
        
        print("  ✅ 대댓글 작성 완료!")
        return True
        
    except Exception as e:
        print(f"  ❌ 대댓글 작성 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("""
╔════════════════════════════════════════════════════════╗
║          간단한 댓글 테스트 스크립트                   ║
║      (Claude 없이 직접 입력하여 테스트)                ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 1. 발행된 글 정보
    print("\n=== Step 1: 글 정보 입력 ===")
    post_url = input("발행된 글 URL: ").strip()
    
    # 2. 계정 정보
    print("\n=== Step 2: 계정 정보 ===")
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    
    # 3. 댓글 정보
    print("\n=== Step 3: 댓글 내용 입력 ===")
    print("여러 개의 댓글을 작성할 수 있습니다.")
    print("형식: 댓글 내용만 입력 (대댓글은 나중에 선택)")
    print()
    
    comments = []
    idx = 1
    while True:
        comment = input(f"댓글 {idx} (종료: 엔터): ").strip()
        if not comment:
            break
        comments.append(comment)
        idx += 1
    
    if not comments:
        print("❌ 댓글이 입력되지 않았습니다.")
        return
    
    print(f"\n총 {len(comments)}개의 댓글이 입력되었습니다.")
    
    # 4. 브라우저 실행 및 로그인
    driver = setup_driver()
    
    try:
        if not login_naver(driver, account_id, account_pw):
            print("❌ 로그인 실패")
            return
        
        # 5. 댓글 작성
        print("\n=== Step 4: 댓글 작성 시작 ===")
        
        if input("\n댓글 작성을 시작하시겠습니까? (y/n): ").lower() != 'y':
            print("취소되었습니다.")
            return
        
        # 댓글 ID 저장 (대댓글용)
        written_comments = []  # [(index, comment_id, text)]
        
        for idx, comment in enumerate(comments, 1):
            print(f"\n[{idx}/{len(comments)}] 댓글 작성")
            
            # 대댓글 여부 선택
            is_reply = False
            parent_id = None
            
            if len(written_comments) > 0:
                reply_choice = input(f"  대댓글로 작성하시겠습니까? (y/n): ").strip().lower()
                if reply_choice == 'y':
                    print("\n  작성된 댓글 목록:")
                    for w_idx, w_id, w_text in written_comments:
                        if w_id:
                            print(f"    [{w_idx}] {w_text[:30]}... (ID: {w_id})")
                    
                    parent_num = input("  부모 댓글 번호: ").strip()
                    if parent_num.isdigit():
                        parent_idx = int(parent_num)
                        for w_idx, w_id, w_text in written_comments:
                            if w_idx == parent_idx and w_id:
                                parent_id = w_id
                                is_reply = True
                                break
            
            # 댓글 작성
            if is_reply and parent_id:
                success = write_reply(driver, post_url, parent_id, comment)
                if success:
                    written_comments.append((idx, None, comment))
            else:
                comment_id = write_comment(driver, post_url, comment)
                written_comments.append((idx, comment_id, comment))
            
            # 다음 댓글 전 대기
            if idx < len(comments):
                wait_time = random.randint(3, 5)
                print(f"  ⏳ 다음 댓글까지 {wait_time}초 대기...")
                time.sleep(wait_time)
        
        print("\n" + "="*60)
        print("🎉 모든 댓글 작성 완료!")
        print("="*60)
        print(f"작성된 댓글: {len(comments)}개")
        print("\n브라우저에서 댓글을 확인하세요!")
        
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
