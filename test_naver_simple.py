"""
네이버 로그인 및 카페 글쓰기 단순 테스트
캡챠 우회 강화 버전

실행: python test_naver_simple.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import random

def random_delay(min_sec=0.5, max_sec=1.5):
    """랜덤 지연"""
    time.sleep(random.uniform(min_sec, max_sec))

def human_type_slow(element, text):
    """매우 느리게 타이핑 (캡챠 우회)"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.2, 0.5))  # 더 느리게!

def main():
    print("""
╔════════════════════════════════════════════════════════╗
║     네이버 로그인 및 카페 글쓰기 테스트                ║
║     캡챠 우회 강화 버전                                ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 입력
    print("테스트 정보를 입력하세요:\n")
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    cafe_url = input("카페 URL (예: https://cafe.naver.com/testcafe): ").strip()
    
    print("\n글 내용 (간단하게):")
    title = input("제목: ").strip() or "테스트 글입니다"
    content = input("본문: ").strip() or "테스트 내용입니다."
    
    print("\n" + "="*60)
    print("  테스트 시작")
    print("="*60 + "\n")
    
    # Chrome 옵션 (캡챠 우회 강화)
    options = webdriver.ChromeOptions()
    
    # 기본 우회
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # User-Agent (실제 사용자처럼)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # 추가 우회 옵션
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    
    # 일반 브라우저처럼 보이기
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=options)
    
    # WebDriver 속성 숨기기
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ko-KR', 'ko', 'en-US', 'en']
            });
        '''
    })
    
    driver.set_window_size(1400, 900)
    
    try:
        # Step 1: 네이버 메인 페이지 방문 (쿠키 설정)
        print("🌐 네이버 메인 페이지 방문 중...")
        driver.get('https://www.naver.com')
        random_delay(3, 5)  # 충분한 대기
        
        # Step 2: 네이버 로그인 페이지
        print("🔐 네이버 로그인 페이지 이동 중...")
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(3, 5)
        
        # Step 3: ID 입력 (매우 느리게)
        print("✍️  ID 입력 중... (천천히)")
        id_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'id'))
        )
        
        # 클릭 후 대기
        id_input.click()
        random_delay(1, 2)
        
        # 한 글자씩 천천히
        human_type_slow(id_input, account_id)
        random_delay(1, 2)
        
        # Step 4: PW 입력 (매우 느리게)
        print("✍️  비밀번호 입력 중... (천천히)")
        pw_input = driver.find_element(By.ID, 'pw')
        pw_input.click()
        random_delay(1, 2)
        
        human_type_slow(pw_input, account_pw)
        random_delay(2, 3)
        
        # Step 5: 로그인 버튼 클릭
        print("🖱️  로그인 버튼 클릭...")
        login_btn = driver.find_element(By.CSS_SELECTOR, '.btn_login')
        login_btn.click()
        
        random_delay(5, 7)  # 충분한 대기
        
        # Step 6: 로그인 성공 확인
        current_url = driver.current_url
        print(f"현재 URL: {current_url[:50]}...")
        
        if 'nid.naver.com' in current_url:
            print("\n⚠️  로그인 페이지에 여전히 있습니다")
            print("캡챠가 표시되었을 수 있습니다")
            print("\n수동으로 캡챠를 해결하세요...")
            input("캡챠 해결 후 Enter를 누르세요...")
        else:
            print("✅ 로그인 성공!")
        
        # Step 7: 카페 글쓰기
        print(f"\n📝 카페 글쓰기 페이지 이동...")
        write_url = f'{cafe_url}/ArticleWrite.nhn'
        driver.get(write_url)
        random_delay(3, 5)
        
        print("현재 페이지:", driver.current_url[:50])
        
        # Step 8: 제목 입력
        print("✍️  제목 입력 중...")
        try:
            title_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'subject'))
            )
            title_input.click()
            random_delay(1, 2)
            human_type_slow(title_input, title)
            print(f"✅ 제목 입력 완료: {title}")
        except Exception as e:
            print(f"❌ 제목 입력 실패: {e}")
            print("글쓰기 권한이 있는지 확인하세요")
            input("\n수동으로 확인 후 Enter...")
            return
        
        random_delay(2, 3)
        
        # Step 9: 본문 입력
        print("✍️  본문 입력 중...")
        try:
            # iframe 찾기
            iframe = driver.find_element(By.CSS_SELECTOR, 'iframe[id*="se2_iframe"]')
            driver.switch_to.frame(iframe)
            
            content_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.se2_inputarea, body'))
            )
            content_div.click()
            random_delay(1, 2)
            
            # 본문 입력
            human_type_slow(content_div, content)
            print(f"✅ 본문 입력 완료")
            
            # iframe 나오기
            driver.switch_to.default_content()
            random_delay(2, 3)
            
        except Exception as e:
            print(f"❌ 본문 입력 실패: {e}")
            driver.switch_to.default_content()
        
        # Step 10: 확인
        print("\n" + "="*60)
        print("✅ 테스트 완료!")
        print("="*60)
        print("\n브라우저를 확인하세요.")
        print("제목과 본문이 입력되어 있습니다.")
        print("\n수동으로 [등록] 버튼을 눌러 테스트를 완료하세요.")
        print("(자동 등록은 하지 않습니다)")
        print()
        
        input("테스트 완료 후 Enter를 누르면 브라우저가 종료됩니다...")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        input("\nEnter를 눌러 종료...")
    finally:
        try:
            driver.quit()
        except:
            pass
        print("\n✅ 테스트 종료")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️ 테스트 취소됨")





