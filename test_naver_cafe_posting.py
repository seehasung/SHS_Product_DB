"""
네이버 카페 글 작성 테스트 스크립트
Worker Agent의 글 작성 기능을 독립적으로 테스트

실행: python test_naver_cafe_posting.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random

def random_delay(min_sec=0.1, max_sec=0.3):
    """랜덤 지연"""
    time.sleep(random.uniform(min_sec, max_sec))

def human_type(element, text):
    """사람처럼 한 글자씩 입력"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15))

def test_naver_login():
    """네이버 로그인 테스트"""
    print("="*60)
    print("  네이버 카페 글 작성 테스트")
    print("="*60)
    print()
    
    # 설정 입력
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    cafe_url = input("카페 URL (예: https://cafe.naver.com/xxx): ").strip()
    
    print("\n글 내용 입력:")
    title = input("제목: ").strip()
    content = input("본문: ").strip()
    
    print("\n" + "="*60)
    print("  테스트 시작")
    print("="*60)
    print()
    
    # Selenium 설정
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1400, 900)
    
    try:
        # 1. 네이버 로그인
        print("🔐 네이버 로그인 중...")
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        # ID 입력
        id_input = driver.find_element(By.ID, 'id')
        human_type(id_input, account_id)
        random_delay(0.5, 1)
        
        # PW 입력
        pw_input = driver.find_element(By.ID, 'pw')
        human_type(pw_input, account_pw)
        random_delay(0.5, 1)
        
        # 로그인 클릭
        login_btn = driver.find_element(By.CSS_SELECTOR, '.btn_login')
        login_btn.click()
        random_delay(3, 4)
        
        if 'nid.naver.com' not in driver.current_url:
            print("✅ 로그인 성공!")
        else:
            print("❌ 로그인 실패 (캡챠 또는 인증 필요)")
            input("수동으로 로그인 후 Enter를 누르세요...")
        
        # 2. 카페 글쓰기 페이지
        print("\n📝 카페 글쓰기 페이지 이동...")
        write_url = f'{cafe_url}/ArticleWrite.nhn'
        driver.get(write_url)
        random_delay(2, 3)
        
        # 3. 제목 입력
        print("✍️  제목 입력 중...")
        title_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'subject'))
        )
        title_input.click()
        random_delay(0.3, 0.5)
        human_type(title_input, title)
        print(f"✅ 제목: {title}")
        
        random_delay(1, 2)
        
        # 4. 본문 입력
        print("✍️  본문 입력 중...")
        
        # iframe 전환
        iframe = driver.find_element(By.CSS_SELECTOR, 'iframe[id*="se2_iframe"]')
        driver.switch_to.frame(iframe)
        
        content_div = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.se2_inputarea, body'))
        )
        content_div.click()
        random_delay(0.5, 1)
        
        # 문장 단위로 입력
        sentences = content.replace('.\n', '.|').replace('. ', '.|').split('|')
        for sentence in sentences:
            if sentence.strip():
                human_type(content_div, sentence.strip())
                if not sentence.endswith('\n'):
                    content_div.send_keys('.')
                content_div.send_keys('\n')
                random_delay(0.5, 1.5)
        
        print(f"✅ 본문 입력 완료")
        
        # iframe 나오기
        driver.switch_to.default_content()
        random_delay(1, 2)
        
        print("\n⚠️  자동 등록은 하지 않습니다.")
        print("브라우저를 확인하세요. 수동으로 등록 버튼을 눌러 테스트하세요.")
        print()
        
        input("테스트 완료 후 Enter를 눌러 종료...")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        input("\nEnter를 눌러 종료...")
    finally:
        driver.quit()
        print("\n✅ 테스트 종료")


if __name__ == "__main__":
    try:
        test_naver_login()
    except KeyboardInterrupt:
        print("\n\n⏹️ 테스트 취소됨")

