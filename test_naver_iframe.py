"""
네이버 카페 iframe 전환 테스트
실제 콘텐츠는 cafe_main iframe 안에 있음!

실행: python test_naver_iframe.py
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
║     네이버 카페 iframe 테스트                          ║
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
            input("캡챠 해결 후 Enter...")
        
        print("✅ 로그인 완료")
        
        # 신규발행 글 접속
        print(f"\n📄 신규발행 글 접속...")
        driver.get(draft_url)
        random_delay(5, 7)
        
        print(f"현재 URL: {driver.current_url}")
        
        # ⭐ iframe 전환!
        print("\n🔄 cafe_main iframe으로 전환 중...")
        try:
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'cafe_main'))
            )
            driver.switch_to.frame(iframe)
            print("✅ iframe 전환 완료!")
            random_delay(2, 3)
            
        except Exception as e:
            print(f"❌ iframe 전환 실패: {e}")
            print("iframe 목록:")
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            for i, ifr in enumerate(iframes, 1):
                print(f"  {i}. ID: {ifr.get_attribute('id') or 'No ID'}")
            input("\n수동으로 확인 후 Enter...")
            return
        
        # iframe 안에서 요소 찾기
        print("\n🔍 iframe 안에서 요소 분석...")
        
        # 1. 수정 버튼 찾기
        print("\n1️⃣ 수정 버튼 찾기:")
        selectors = [
            ('Text 수정', '//a[contains(text(), "수정")]'),
            ('Text 편집', '//a[contains(text(), "편집")]'),
            ('Button 수정', '//button[contains(text(), "수정")]'),
            ('Span 수정', '//span[contains(text(), "수정")]'),
            ('CSS a', 'a'),
        ]
        
        modify_button = None
        for name, selector in selectors:
            try:
                if selector.startswith('//'):
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
                if elements:
                    print(f"  ✅ {name}: {len(elements)}개 발견")
                    for elem in elements[:5]:
                        text = elem.text.strip()
                        if text:
                            print(f"     - '{text}'")
                            if '수정' in text or '편집' in text:
                                modify_button = elem
                                print(f"     ⭐ 수정 버튼 발견!")
                                break
                else:
                    print(f"  ❌ {name}: 없음")
            except Exception as e:
                print(f"  ❌ {name}: 오류")
        
        if modify_button:
            print("\n🖱️  수정 버튼 클릭...")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modify_button)
            random_delay()
            modify_button.click()
            print("✅ 수정 버튼 클릭 완료!")
            random_delay(3, 5)
            
            # 수정 페이지로 이동되었는지 확인
            print(f"현재 URL: {driver.current_url}")
        else:
            print("\n❌ 수정 버튼을 찾을 수 없습니다")
            print("수동으로 수정 버튼을 눌러주세요")
            input("수정 버튼 클릭 후 Enter...")
        
        # 2. 카테고리 버튼 찾기
        print("\n2️⃣ 카테고리 드롭다운 찾기:")
        selectors = [
            ('Button select', 'button.select_current, button[class*="select"]'),
            ('Div select', 'div.select_option button'),
            ('All buttons', 'button'),
        ]
        
        for name, selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"  ✅ {name}: {len(elements)}개 발견")
                    for elem in elements[:3]:
                        text = elem.text.strip()[:30]
                        if text:
                            print(f"     - '{text}'")
            except:
                print(f"  ❌ {name}: 오류")
        
        # 3. 제목 입력란 찾기
        print("\n3️⃣ 제목 입력란 찾기:")
        selectors = [
            ('Textarea', 'textarea'),
            ('Input title', 'input[name*="title"], input[placeholder*="제목"]'),
        ]
        
        for name, selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"  ✅ {name}: {len(elements)}개 발견")
                    for elem in elements[:3]:
                        placeholder = elem.get_attribute('placeholder')
                        print(f"     - placeholder: '{placeholder}'")
            except:
                print(f"  ❌ {name}: 오류")
        
        # 4. 본문 입력란 찾기
        print("\n4️⃣ 본문 입력란 찾기:")
        selectors = [
            ('Article', 'article'),
            ('Content editable', '[contenteditable="true"]'),
            ('SE components', 'div[id*="SE-"]'),
        ]
        
        for name, selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"  ✅ {name}: {len(elements)}개 발견")
            except:
                print(f"  ❌ {name}: 오류")
        
        # 5. 스크린샷
        print("\n5️⃣ 스크린샷 저장:")
        
        # iframe 밖으로 나가서 전체 스크린샷
        driver.switch_to.default_content()
        driver.save_screenshot('debug_full.png')
        print("  ✅ debug_full.png (전체 페이지)")
        
        # iframe 안으로 다시 전환
        driver.switch_to.frame('cafe_main')
        driver.save_screenshot('debug_iframe.png')
        print("  ✅ debug_iframe.png (iframe 안)")
        
        print("\n" + "="*60)
        print("디버그 완료!")
        print("="*60)
        print("\n생성된 파일:")
        print("  - debug_full.png (전체 페이지)")
        print("  - debug_iframe.png (iframe 안)")
        print("\n이 이미지들을 확인하고")
        print("브라우저 F12에서 수정 버튼의 정확한 선택자를 알려주세요!")
        
        input("\nEnter를 누르면 종료...")
        
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



