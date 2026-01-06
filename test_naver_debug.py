"""
네이버 카페 요소 찾기 디버그 스크립트
어떤 요소들이 있는지 확인

실행: python test_naver_debug.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
║     네이버 카페 요소 디버그                            ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    
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
        random_delay(5, 7)  # 충분한 대기
        
        print(f"현재 URL: {driver.current_url}")
        print(f"페이지 제목: {driver.title}")
        
        # 요소 찾기 시도
        print("\n" + "="*60)
        print("페이지 분석 중...")
        print("="*60)
        
        # 1. 수정 버튼 찾기 (여러 방법 시도)
        print("\n1️⃣ 수정 버튼 찾기:")
        
        selectors = [
            ('XPath (원본)', '//*[@id="app"]/div/div/div[3]/div[1]/a[3]'),
            ('Text 포함', '//a[contains(text(), "수정")]'),
            ('Button 수정', '//button[contains(text(), "수정")]'),
            ('Span 수정', '//span[contains(text(), "수정")]'),
            ('CSS .btn', 'a.btn, button.btn'),
        ]
        
        for name, selector in selectors:
            try:
                if selector.startswith('//'):
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
                if elements:
                    print(f"  ✅ {name}: {len(elements)}개 발견")
                    for i, elem in enumerate(elements[:3]):
                        print(f"     - 텍스트: '{elem.text[:30]}'")
                else:
                    print(f"  ❌ {name}: 없음")
            except Exception as e:
                print(f"  ❌ {name}: 오류 ({str(e)[:30]})")
        
        # 2. 모든 버튼/링크 찾기
        print("\n2️⃣ 모든 버튼과 링크:")
        
        try:
            all_buttons = driver.find_elements(By.CSS_SELECTOR, 'button, a')
            print(f"  총 {len(all_buttons)}개 버튼/링크 발견")
            print("\n  상위 10개:")
            for i, btn in enumerate(all_buttons[:10], 1):
                text = btn.text.strip()[:20]
                tag = btn.tag_name
                print(f"    {i}. <{tag}> '{text}'")
        except:
            print("  ❌ 버튼 찾기 실패")
        
        # 3. iframe 확인
        print("\n3️⃣ iframe 확인:")
        
        try:
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            print(f"  총 {len(iframes)}개 iframe 발견")
            for i, iframe in enumerate(iframes, 1):
                print(f"    {i}. ID: {iframe.get_attribute('id') or 'No ID'}")
        except:
            print("  ❌ iframe 없음")
        
        # 4. 페이지 소스 일부
        print("\n4️⃣ 페이지 HTML (일부):")
        
        try:
            body_html = driver.find_element(By.TAG_NAME, 'body').get_attribute('innerHTML')
            print(f"  HTML 길이: {len(body_html)} bytes")
            
            if '수정' in body_html:
                print("  ✅ '수정' 텍스트 발견")
            else:
                print("  ❌ '수정' 텍스트 없음")
                
        except:
            print("  ❌ HTML 읽기 실패")
        
        # 5. 스크린샷
        print("\n5️⃣ 스크린샷 저장:")
        
        try:
            screenshot_path = 'debug_screenshot.png'
            driver.save_screenshot(screenshot_path)
            print(f"  ✅ 스크린샷 저장: {screenshot_path}")
            print("     → 이 이미지를 확인하세요!")
        except:
            print("  ❌ 스크린샷 실패")
        
        print("\n" + "="*60)
        print("디버그 완료!")
        print("="*60)
        print("\n브라우저를 직접 확인하세요.")
        print("수정 버튼이 어디에 있는지 F12로 확인해주세요")
        print()
        
        input("Enter를 누르면 종료...")
        
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





