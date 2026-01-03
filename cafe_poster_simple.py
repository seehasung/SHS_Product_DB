"""
네이버 카페 글 수정 발행 - 간단 버전
로컬 파일 직접 사용

실행: python cafe_poster_simple.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
from pathlib import Path

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
║     네이버 카페 글 수정 발행 - 간단 버전               ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    target_board = input("변경할 게시판명: ").strip()
    new_title = input("새 제목: ").strip()
    new_content = input("새 본문: ").strip()
    
    # 로컬 이미지 (선택)
    local_images = []
    if input("\n로컬 이미지 추가? (y/n): ").lower() == 'y':
        while True:
            img_path = input("이미지 경로 (종료: Enter): ").strip().strip('"').strip("'")
            if not img_path:
                break
            if Path(img_path).exists():
                local_images.append(str(Path(img_path).absolute()))
                print(f"  ✅ {Path(img_path).name}")
            else:
                print(f"  ❌ 파일 없음")
    
    keyword = input("\n태그: ").strip()
    
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
        
        # Enter로 로그인 (더 자연스러움)
        pw_input.send_keys(Keys.ENTER)
        random_delay(3, 5)
        
        if 'nid.naver.com' in driver.current_url:
            input("캡챠 해결 후 Enter...")
        
        print("✅ 로그인 완료")
        
        # 신규발행 글
        print(f"\n📄 신규발행 글 접속...")
        driver.get(draft_url)
        random_delay(5, 7)
        
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        random_delay(2, 3)
        
        # 수정 버튼
        print("🖱️ 수정 버튼...")
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        modify_btn.click()
        random_delay(5, 7)
        
        # 새 탭 전환
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            random_delay(3, 5)
            print("✅ 새 탭 전환")
        
        # 카테고리
        print(f"\n📂 카테고리: {target_board}")
        
        try:
            btn = driver.find_element(By.CSS_SELECTOR, 'div.FormSelectBox button')
            btn.click()
            random_delay(1, 2)
            
            opts = driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
            
            for opt in opts:
                text = opt.find_element(By.CSS_SELECTOR, 'span.option_text').text
                if target_board in text:
                    opt.click()
                    random_delay()
                    print(f"  ✅ '{text}'")
                    break
        except Exception as e:
            print(f"  ⚠️ 카테고리 실패: {str(e)[:50]}")
        
        # 제목
        print(f"\n✍️ 제목...")
        
        title = driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
        title.click()
        random_delay()
        title.send_keys(Keys.CONTROL + 'a', Keys.DELETE)
        random_delay()
        human_type(title, new_title)
        
        print("✅ 제목 완료")
        
        # 본문
        print(f"\n📝 본문...")
        
        article = driver.find_element(By.CSS_SELECTOR, 'article.se-components-wrap')
        
        driver.execute_script("""
            const article = arguments[0];
            article.querySelectorAll('p').forEach(p => p.remove());
        """, article)
        
        for line in new_content.split('\n'):
            if line.strip():
                driver.execute_script("""
                    const article = arguments[0];
                    const p = document.createElement('p');
                    p.className = 'se-text-paragraph se-text-paragraph-align-left';
                    const span = document.createElement('span');
                    span.className = 'se-ff-system se-fs15';
                    span.textContent = arguments[1];
                    p.appendChild(span);
                    article.querySelector('.se-module-text').appendChild(p);
                """, article, line)
        
        print("✅ 본문 완료")
        
        # 이미지
        if local_images:
            print(f"\n📷 이미지 {len(local_images)}개...")
            
            file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            
            if file_inputs:
                # 모든 이미지를 한 input에 전달
                file_inputs[0].send_keys('\n'.join(local_images))
                random_delay(5, 7)
                print("✅ 이미지 업로드 완료")
        
        # 태그
        if keyword:
            print(f"\n🏷️ 태그...")
            
            tag = driver.find_element(By.CSS_SELECTOR, 'input.tag_input')
            tag.click()
            human_type(tag, keyword)
            tag.send_keys(Keys.ENTER)
            
            print("✅ 태그 완료")
        
        # 댓글 허용
        print("\n💬 댓글 허용...")
        
        driver.execute_script('document.getElementById("coment").checked = true')
        print("✅ 댓글 허용 완료")
        
        # 완료
        print("\n" + "="*60)
        print("✅ 모든 내용 입력 완료!")
        print("="*60)
        print("\n브라우저를 확인하고 수동으로 [등록] 버튼을 누르세요!")
        
        input("\n등록 후 Enter...")
        
        print(f"\n📍 URL: {driver.current_url}")
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nEnter로 종료...")
        driver.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")

