"""
글쓰기 페이지 HTML 추출
수동으로 수정 버튼을 누른 후 실행

실행: python extract_html.py
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
║     글쓰기 페이지 HTML 추출 도구                       ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    
    driver = setup_driver()
    
    try:
        # 로그인
        print("\n🔐 로그인 페이지 접속...")
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
        
        # iframe 전환
        print("🔄 iframe 전환...")
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        random_delay(2, 3)
        
        # 수정 버튼 클릭
        print("🖱️ 수정 버튼 클릭...")
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        modify_btn.click()
        random_delay(5, 7)
        
        print("✅ 글쓰기 페이지 이동 완료")
        print(f"현재 URL: {driver.current_url}")
        
        # 이제 글쓰기 페이지에서 HTML 추출
        print("\n" + "="*60)
        print("글쓰기 페이지 HTML 추출")
        print("="*60)
        
        # iframe 확인
        print("\n1️⃣ iframe 상태:")
        driver.switch_to.default_content()
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        print(f"  총 {len(iframes)}개 iframe:")
        for i, ifr in enumerate(iframes, 1):
            iframe_id = ifr.get_attribute('id') or 'No ID'
            print(f"    {i}. {iframe_id}")
        
        # 다시 전환 시도
        print("\n2️⃣ iframe 재전환:")
        iframe_switched = False
        for iframe_id in ['cafe_main', None]:  # cafe_main 우선, 실패 시 첫 번째
            try:
                if iframe_id:
                    driver.switch_to.frame(iframe_id)
                else:
                    driver.switch_to.frame(0)  # 첫 번째 iframe
                print(f"  ✅ {'cafe_main' if iframe_id else '첫 번째 iframe'} 전환 성공")
                iframe_switched = True
                break
            except:
                continue
        
        if not iframe_switched:
            print("  ❌ iframe 전환 실패")
        
        random_delay(2, 3)
        
        # HTML 저장
        print("\n3️⃣ HTML 저장:")
        
        body_html = driver.find_element(By.TAG_NAME, 'body').get_attribute('innerHTML')
        
        with open('write_page.html', 'w', encoding='utf-8') as f:
            f.write(body_html)
        
        print("  ✅ write_page.html 저장됨")
        print("  HTML 길이:", len(body_html), "bytes")
        
        # 주요 요소 검색
        print("\n4️⃣ 주요 키워드 검색:")
        
        keywords = ['카테고리', '제목', '본문', '태그', '댓글', '등록']
        for kw in keywords:
            if kw in body_html:
                print(f"  ✅ '{kw}' 발견")
            else:
                print(f"  ❌ '{kw}' 없음")
        
        # 모든 input 찾기
        print("\n5️⃣ 모든 input 요소:")
        
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input, textarea')
        print(f"  총 {len(inputs)}개 발견:")
        for i, inp in enumerate(inputs[:10], 1):
            inp_type = inp.get_attribute('type')
            inp_id = inp.get_attribute('id')
            inp_class = inp.get_attribute('class')
            placeholder = inp.get_attribute('placeholder')
            print(f"    {i}. type={inp_type}, id={inp_id}, placeholder={placeholder}")
        
        # 모든 button 찾기
        print("\n6️⃣ 모든 button 요소:")
        
        buttons = driver.find_elements(By.CSS_SELECTOR, 'button, a.BaseButton')
        print(f"  총 {len(buttons)}개 발견 (상위 20개):")
        for i, btn in enumerate(buttons[:20], 1):
            text = btn.text.strip()[:30]
            btn_class = btn.get_attribute('class')[:50]
            print(f"    {i}. '{text}' (class: {btn_class})")
        
        # 스크린샷
        print("\n7️⃣ 스크린샷:")
        
        driver.save_screenshot('write_page_screenshot.png')
        print("  ✅ write_page_screenshot.png")
        
        print("\n" + "="*60)
        print("추출 완료!")
        print("="*60)
        print("\n생성된 파일:")
        print("  1. write_page.html (전체 HTML)")
        print("  2. write_page_screenshot.png (스크린샷)")
        print("\n이 파일들과 위 출력 결과를 보내주세요!")
        
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



