"""
수동 보조 테스트
사람이 주요 단계를 수행하고, 스크립트가 정보 추출

실행: python test_manual_assisted.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
import time

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
║     수동 보조 테스트                                   ║
║     사람이 작업하면서 스크립트가 정보 추출             ║
╚════════════════════════════════════════════════════════╝
    """)
    
    print("\n이 테스트는:")
    print("  1. 당신이 수동으로 로그인")
    print("  2. 당신이 수동으로 신규발행 글 접속")
    print("  3. 당신이 수동으로 수정 버튼 클릭")
    print("  4. 스크립트가 각 요소의 정확한 위치 추출")
    print()
    
    input("준비되면 Enter를 누르세요...")
    
    driver = setup_driver()
    
    try:
        print("\n1️⃣ 네이버 카페 메인으로 이동합니다...")
        driver.get('https://cafe.naver.com')
        time.sleep(3)
        
        print("\n" + "="*60)
        print("수동 작업 단계")
        print("="*60)
        print("\n브라우저에서 다음을 수행하세요:")
        print("  1. 로그인")
        print("  2. 신규발행 글 접속")
        print("  3. 수정 버튼 클릭")
        print("  4. 글쓰기 페이지 도달")
        print()
        
        input("글쓰기 페이지에 도착하면 Enter를 누르세요...")
        
        print("\n" + "="*60)
        print("요소 추출 시작")
        print("="*60)
        
        # 현재 URL
        print(f"\n현재 URL: {driver.current_url}")
        
        # 탭 개수
        print(f"탭 개수: {len(driver.window_handles)}")
        
        # iframe 확인
        print("\niframe 확인:")
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        for i, iframe in enumerate(iframes, 1):
            iframe_id = iframe.get_attribute('id')
            print(f"  {i}. {iframe_id}")
        
        # 카테고리 드롭다운
        print("\n📂 카테고리 버튼:")
        cat_btns = driver.find_elements(By.CSS_SELECTOR, 'button')
        for i, btn in enumerate(cat_btns[:20], 1):
            text = btn.text.strip()
            classes = btn.get_attribute('class')
            if text and ('가입' in text or '인사' in text or '질문' in text or '수다' in text):
                print(f"  {i}. '{text}'")
                print(f"     class: {classes}")
                print(f"     CSS: button:nth-of-type({i})")
        
        # 제목 textarea
        print("\n✍️ 제목 입력란:")
        textareas = driver.find_elements(By.CSS_SELECTOR, 'textarea')
        for i, ta in enumerate(textareas, 1):
            placeholder = ta.get_attribute('placeholder')
            value = ta.get_attribute('value')
            print(f"  {i}. placeholder: '{placeholder}'")
            print(f"     value: '{value[:20] if value else ''}'")
        
        # 본문 article
        print("\n📝 본문 영역:")
        articles = driver.find_elements(By.CSS_SELECTOR, 'article')
        for i, art in enumerate(articles, 1):
            art_class = art.get_attribute('class')
            print(f"  {i}. class: {art_class}")
            
            # 내부 편집 가능한 요소
            inner_editable = art.find_elements(By.CSS_SELECTOR, '[contenteditable="true"]')
            print(f"     contenteditable: {len(inner_editable)}개")
            
            inner_p = art.find_elements(By.CSS_SELECTOR, 'p')
            print(f"     p 태그: {len(inner_p)}개")
        
        # 파일 input
        print("\n📷 파일 input:")
        file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        for i, fi in enumerate(file_inputs, 1):
            accept = fi.get_attribute('accept')
            name = fi.get_attribute('name')
            is_displayed = fi.is_displayed()
            print(f"  {i}. accept: {accept}, name: {name}, 보임: {is_displayed}")
        
        # 태그 input
        print("\n🏷️ 태그 입력:")
        tag_inputs = driver.find_elements(By.CSS_SELECTOR, 'input.tag_input, input[placeholder*="태그"]')
        for i, ti in enumerate(tag_inputs, 1):
            placeholder = ti.get_attribute('placeholder')
            print(f"  {i}. placeholder: '{placeholder}'")
        
        # 댓글 허용
        print("\n💬 댓글 허용 체크박스:")
        try:
            coment_cb = driver.find_element(By.ID, 'coment')
            is_checked = coment_cb.is_selected()
            print(f"  ✅ 찾음: coment")
            print(f"     체크 상태: {is_checked}")
            print(f"     보임: {coment_cb.is_displayed()}")
            
            # label 확인
            label = driver.find_element(By.CSS_SELECTOR, 'label[for="coment"]')
            print(f"     label 텍스트: '{label.text}'")
        except:
            print("  ❌ 못 찾음")
        
        # 등록 버튼
        print("\n✅ 등록 버튼:")
        green_btns = driver.find_elements(By.CSS_SELECTOR, 'a.BaseButton--skinGreen, button.BaseButton--skinGreen')
        for i, btn in enumerate(green_btns, 1):
            text = btn.text.strip()
            print(f"  {i}. '{text}'")
        
        # 스크린샷
        print("\n📸 스크린샷 저장...")
        driver.save_screenshot('manual_test_screenshot.png')
        print("  ✅ manual_test_screenshot.png")
        
        # HTML 저장
        print("\n💾 HTML 저장...")
        with open('manual_test_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print("  ✅ manual_test_page.html")
        
        print("\n" + "="*60)
        print("추출 완료!")
        print("="*60)
        print("\n생성된 파일:")
        print("  - manual_test_screenshot.png")
        print("  - manual_test_page.html")
        print("\n이 정보로 정확한 선택자를 확인할 수 있습니다!")
        
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




