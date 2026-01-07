"""
네이버 카페 글 수정 최종 테스트
정확한 선택자 사용

실행: python test_naver_final.py
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

def main():
    print("""
╔════════════════════════════════════════════════════════╗
║     네이버 카페 글 수정 최종 테스트                    ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    target_board = input("변경할 게시판명: ").strip()
    new_title = input("새 제목: ").strip()
    new_content = input("새 본문: ").strip()
    
    driver = setup_driver()
    
    try:
        # 로그인
        print("\n🔐 로그인 중...")
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        id_input = driver.find_element(By.ID, 'id')
        human_type(id_input, account_id)
        random_delay()
        
        pw_input = driver.find_element(By.ID, 'pw')
        human_type(pw_input, account_pw)
        random_delay()
        
        driver.find_element(By.CSS_SELECTOR, '.btn_login').click()
        random_delay(3, 5)
        
        if 'nid.naver.com' in driver.current_url:
            print("⚠️ 캡챠 표시됨")
            input("캡챠 해결 후 Enter...")
        
        print("✅ 로그인 완료")
        
        # 신규발행 글 접속
        print(f"\n📄 신규발행 글 접속...")
        driver.get(draft_url)
        random_delay(5, 7)
        
        # iframe 전환
        print("\n🔄 iframe 전환 중...")
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        print("✅ iframe 전환 완료")
        random_delay(2, 3)
        
        # 수정 버튼 클릭
        print("\n🖱️  수정 버튼 찾기...")
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modify_btn)
        random_delay()
        modify_btn.click()
        print("✅ 수정 버튼 클릭!")
        random_delay(3, 5)
        
        print(f"현재 URL: {driver.current_url}")
        
        # 카테고리 변경
        print(f"\n📂 카테고리 변경: {target_board}")
        try:
            # 카테고리 드롭다운 버튼 클릭
            category_btn = driver.find_element(By.CSS_SELECTOR, 'button.select_current, div.select_wrap button')
            category_btn.click()
            print("✅ 카테고리 드롭다운 열림")
            random_delay(1, 2)
            
            # 옵션 리스트에서 찾기
            options = driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li button span.option_text')
            
            print(f"  📋 {len(options)}개 카테고리 발견")
            
            for option in options:
                option_text = option.text.strip()
                if target_board in option_text:
                    print(f"  ✅ 카테고리 발견: {option_text}")
                    option.click()
                    random_delay(1, 2)
                    break
            else:
                print(f"  ⚠️ '{target_board}' 못 찾음")
                print("  사용 가능한 카테고리 (일부):")
                for i, opt in enumerate(options[:10], 1):
                    print(f"    {i}. {opt.text}")
                input("\n수동으로 선택 후 Enter...")
                
        except Exception as e:
            print(f"❌ 카테고리 변경 실패: {str(e)[:100]}")
            input("수동으로 선택 후 Enter...")
        
        # 제목 입력
        print(f"\n✍️  제목 입력: {new_title}")
        try:
            # textarea 찾기
            title_textarea = driver.find_element(By.CSS_SELECTOR, 'textarea')
            title_textarea.click()
            random_delay()
            
            # 기존 내용 삭제
            title_textarea.send_keys(Keys.CONTROL + 'a')
            random_delay(0.2, 0.3)
            title_textarea.send_keys(Keys.DELETE)
            random_delay()
            
            # 새 제목 입력
            human_type(title_textarea, new_title)
            print("✅ 제목 입력 완료")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"❌ 제목 입력 실패: {str(e)[:100]}")
            input("수동으로 입력 후 Enter...")
        
        # 본문 입력
        print(f"\n✍️  본문 입력: {new_content}")
        try:
            # article 또는 contenteditable 찾기
            content_area = driver.find_element(By.CSS_SELECTOR, 'article, [contenteditable="true"]')
            content_area.click()
            random_delay()
            
            # 기존 내용 삭제
            content_area.send_keys(Keys.CONTROL + 'a')
            random_delay(0.2, 0.3)
            content_area.send_keys(Keys.DELETE)
            random_delay()
            
            # 새 본문 입력
            lines = new_content.split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    human_type(content_area, line)
                if i < len(lines) - 1:
                    content_area.send_keys(Keys.ENTER)
                    random_delay(0.3, 0.5)
            
            print("✅ 본문 입력 완료")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"❌ 본문 입력 실패: {str(e)[:100]}")
            input("수동으로 입력 후 Enter...")
        
        # 댓글 허용
        print("\n💬 댓글 허용 체크...")
        try:
            # ID로 찾기 (여러 시도)
            comment_checkbox = driver.find_element(By.ID, 'coment')
            if not comment_checkbox.is_selected():
                comment_checkbox.click()
                print("✅ 댓글 허용 체크")
            else:
                print("✅ 이미 체크됨")
        except:
            print("⚠️ 댓글 허용 체크박스를 찾을 수 없습니다")
        
        # 등록 버튼
        print("\n📍 등록 버튼 찾기...")
        try:
            submit_btn = driver.find_element(By.XPATH, '//a[.//span[text()="등록"]]')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            print("✅ 등록 버튼 발견 (클릭 안 함)")
        except:
            print("⚠️ 등록 버튼을 찾을 수 없습니다")
        
        print("\n" + "="*60)
        print("✅ 테스트 완료!")
        print("="*60)
        print("\n브라우저를 확인하세요:")
        print("  - 카테고리가 변경되었나요?")
        print("  - 제목이 입력되었나요?")
        print("  - 본문이 입력되었나요?")
        print("\n수동으로 [등록] 버튼을 눌러 최종 테스트하세요!")
        
        input("\n등록 완료 후 Enter...")
        
        # 새 URL 확인
        final_url = driver.current_url
        print(f"\n📍 수정 후 URL: {final_url}")
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nEnter를 누르면 종료...")
        driver.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")






