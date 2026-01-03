"""
네이버 카페 글 수정 발행 - pyautogui 버전
Windows 파일 탐색기 직접 제어

실행: python cafe_poster_with_pyautogui.py
필수: pip install pyautogui
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import os
import requests
from pathlib import Path
import tempfile
import pyautogui
import pyperclip

# ⭐ undetected-chromedriver (캡챠 우회)
try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    UNDETECTED_AVAILABLE = False
    print("⚠️ undetected_chromedriver가 없습니다")
    print("   설치: pip install undetected-chromedriver")

def random_delay(min_sec=1, max_sec=2):
    time.sleep(random.uniform(min_sec, max_sec))

def human_type(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))

def download_image_from_server(image_url):
    """서버에서 이미지 다운로드"""
    try:
        response = requests.get(image_url, timeout=30, verify=False)
        if response.status_code == 200:
            temp_dir = tempfile.gettempdir()
            
            # URL에서 파일명 추출
            url_filename = image_url.split('/')[-1]  # 예: 5e9eb055-3f51-4b2c-98be-83dfec0ba55b.png
            
            # 확장자 확인
            if '.' in url_filename:
                # 원본 파일명 사용
                filename = url_filename
            else:
                # 확장자 없으면 .jpg 추가
                filename = f"{url_filename}.jpg"
            
            temp_path = os.path.join(temp_dir, filename)
            
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✅ 다운로드: {filename}")
            print(f"  📁 경로: {temp_path}")
            return temp_path
        else:
            print(f"  ❌ 다운로드 실패: {response.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ 다운로드 오류: {e}")
        return None

def upload_image_with_pyautogui(file_path):
    """pyautogui + pyperclip으로 Windows 탐색기 제어"""
    try:
        # Windows 탐색기가 열릴 때까지 대기
        print("     탐색기 로드 대기 중...")
        time.sleep(3)
        
        # 전체 파일 경로를 클립보드에 복사
        print(f"     클립보드에 경로 복사: {file_path}")
        pyperclip.copy(file_path)
        time.sleep(0.5)
        
        # 파일명 입력란 직접 타이핑으로 활성화
        print("     파일명 타이핑하여 입력란 활성화...")
        
        # 파일명만 추출
        filename = os.path.basename(file_path)
        
        # 첫 글자만 타이핑 (파일명 입력란 활성화)
        pyautogui.write(filename[0], interval=0.1)
        time.sleep(0.3)
        
        # 기존 입력 삭제 후 전체 경로 붙여넣기
        pyautogui.hotkey('ctrl', 'a')  # 전체 선택
        time.sleep(0.2)
        
        # 클립보드에서 붙여넣기 (전체 경로!)
        print("     Ctrl+V로 전체 경로 붙여넣기...")
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(1)
        
        # Enter로 열기
        print("     Enter로 열기...")
        pyautogui.press('enter')
        time.sleep(2)
        
        print("     ✅ 완료")
        return True
        
    except Exception as e:
        print(f"     ❌ pyautogui 오류: {e}")
        return False

def setup_driver():
    """브라우저 초기화 (캡챠 우회)"""
    if UNDETECTED_AVAILABLE:
        # ⭐ undetected-chromedriver 사용
        print("🚀 undetected-chromedriver로 브라우저 실행 (캡챠 우회)")
        
        options = uc.ChromeOptions()
        options.add_argument('--log-level=3')
        
        driver = uc.Chrome(options=options, version_main=None)
        driver.set_window_size(1400, 900)
        return driver
    else:
        # 일반 ChromeDriver
        print("🚀 일반 ChromeDriver로 브라우저 실행")
        
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
║  네이버 카페 글 수정 발행 - pyautogui 버전            ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    target_board = input("변경할 게시판명: ").strip()
    new_title = input("새 제목: ").strip()
    new_content = input("새 본문: ").strip()
    
    # 이미지 (서버 URL)
    image_urls = []
    if input("\n이미지 추가? (y/n): ").lower() == 'y':
        while True:
            img_url = input("이미지 URL (종료: Enter): ").strip()
            if not img_url:
                break
            image_urls.append(img_url)
    
    keyword = input("\n태그: ").strip()
    
    driver = setup_driver()
    temp_files = []
    
    try:
        # ⭐ 로그인 (캡챠 우회 버전)
        print("\n🔐 로그인...")
        
        # 1. 네이버 메인 먼저 접속
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        
        # 2. 로그인 페이지로 이동
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        # 3. ID 입력 (pyperclip + Ctrl+V)
        id_input = driver.find_element(By.ID, 'id')
        id_input.click()
        random_delay(0.5, 1)
        
        pyperclip.copy(account_id)
        id_input.send_keys(Keys.CONTROL, 'v')
        random_delay(0.5, 1)
        
        # 4. PW 입력 (pyperclip + Ctrl+V)
        pw_input = driver.find_element(By.ID, 'pw')
        pw_input.click()
        random_delay(0.5, 1)
        
        pyperclip.copy(account_pw)
        pw_input.send_keys(Keys.CONTROL, 'v')
        random_delay(1, 2)
        
        # 5. 로그인 버튼 클릭
        login_btn = driver.find_element(By.ID, 'log.login')
        login_btn.click()
        random_delay(3, 5)
        
        # 6. 로그인 확인
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        
        try:
            logout_btn = driver.find_element(By.XPATH, '//*[@id="account"]/div[1]/div/button')
            if logout_btn:
                print("✅ 로그인 성공 (캡챠 없음!)")
        except:
            if 'nid.naver.com' in driver.current_url:
                print("⚠️ 캡챠 발생")
                input("캡챠 해결 후 Enter...")
            else:
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
        
        print("✅ 글쓰기 페이지")
        
        # 카테고리
        print(f"\n📂 카테고리: {target_board}")
        
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
        
        # 이미지 (pyautogui 사용!)
        if image_urls:
            print(f"\n📷 이미지 업로드 ({len(image_urls)}개)...")
            
            # 이미지 다운로드
            for img_url in image_urls:
                temp_file = download_image_from_server(img_url)
                if temp_file:
                    temp_files.append(temp_file)
            
            if temp_files:
                print(f"\n📤 {len(temp_files)}개 이미지 업로드 (pyautogui)...")
                
                for idx, temp_file in enumerate(temp_files, 1):
                    print(f"\n이미지 {idx}/{len(temp_files)}...")
                    print(f"  📁 파일 경로: {temp_file}")
                    print(f"  📄 파일 존재: {os.path.exists(temp_file)}")
                    print(f"  📏 파일 크기: {os.path.getsize(temp_file) / 1024:.1f} KB")
                    
                    try:
                        # 사진 버튼 클릭 (동적 선택자)
                        photo_btn = driver.find_element(By.CSS_SELECTOR, 'button.se-image-toolbar-button')
                        photo_btn.click()
                        
                        print("  ✅ 사진 버튼 클릭 (Windows 탐색기 열림)")
                        print("  ⏳ 탐색기가 완전히 열릴 때까지 3초 대기...")
                        time.sleep(3)  # 탐색기 로드 대기
                        
                        # pyautogui로 파일 경로 입력
                        print(f"  ⌨️ pyautogui로 파일 경로 입력 중...")
                        print(f"     경로: {temp_file}")
                        
                        success = upload_image_with_pyautogui(temp_file)
                        
                        if success:
                            print(f"  ✅ 이미지 {idx} 업로드 완료")
                        else:
                            print(f"  ⚠️ 이미지 {idx} 업로드 실패 (pyautogui 오류)")
                            print("     수동으로 파일을 선택해주세요")
                            input("     파일 선택 후 Enter...")
                        
                        random_delay(2, 3)  # 다음 이미지 전 대기
                        
                    except Exception as e:
                        print(f"  ❌ 오류: {str(e)[:100]}")
                
                print(f"\n✅ 모든 이미지 업로드 완료!")
        
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
        print("\n브라우저를 확인하고 [등록] 버튼을 누르세요!")
        
        input("\n등록 후 Enter...")
        
        print(f"\n📍 URL: {driver.current_url}")
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 임시 파일 삭제
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except:
                pass
        
        input("\nEnter로 종료...")
        driver.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")

