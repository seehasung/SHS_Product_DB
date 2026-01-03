"""
네이버 카페 자동 글 수정 발행 - 최종 완성 버전
서버에서 이미지 다운로드 + 자동 업로드

실행: python cafe_poster_final.py
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
            # 임시 파일로 저장
            temp_dir = tempfile.gettempdir()
            filename = f"cafe_image_{int(time.time())}.jpg"
            temp_path = os.path.join(temp_dir, filename)
            
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✅ 다운로드 완료: {filename}")
            return temp_path
        else:
            print(f"  ❌ 다운로드 실패: {response.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ 다운로드 오류: {e}")
        return None

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1400, 900)
    return driver

def post_to_cafe(account_id, account_pw, draft_url, target_board, new_title, new_content, image_urls=None, keyword=None):
    """카페에 글 수정 발행"""
    
    driver = setup_driver()
    temp_files = []  # 임시 파일 목록
    
    try:
        # Step 1: 로그인
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
            print("⚠️ 캡챠 표시")
            input("캡챠 해결 후 Enter...")
        
        print("✅ 로그인 완료")
        
        # Step 2: 신규발행 글 접속
        print(f"\n📄 신규발행 글 접속...")
        driver.get(draft_url)
        random_delay(5, 7)
        
        # iframe 전환
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        random_delay(2, 3)
        
        # Step 3: 수정 버튼
        print("🖱️ 수정 버튼 클릭...")
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        modify_btn.click()
        random_delay(5, 7)
        
        # 새 탭 전환
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            random_delay(3, 5)
        
        print("✅ 글쓰기 페이지 이동")
        
        # Step 4: 카테고리 변경
        print(f"\n📂 카테고리 변경: {target_board}")
        
        # 드롭다운 버튼 찾기
        category_btn = driver.find_element(By.CSS_SELECTOR, 'div.FormSelectBox button')
        category_btn.click()
        random_delay(1, 2)
        
        # 옵션 찾기
        options = driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
        print(f"  옵션 {len(options)}개")
        
        for option in options:
            opt_text = option.find_element(By.CSS_SELECTOR, 'span.option_text').text.strip()
            if target_board in opt_text or opt_text in target_board:
                print(f"  ✅ '{opt_text}' 클릭")
                option.click()
                random_delay(1, 2)
                break
        
        # Step 5: 제목
        print(f"\n✍️ 제목: {new_title}")
        
        title_textarea = driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
        title_textarea.click()
        random_delay()
        title_textarea.send_keys(Keys.CONTROL + 'a')
        title_textarea.send_keys(Keys.DELETE)
        random_delay()
        human_type(title_textarea, new_title)
        
        print("✅ 제목 완료")
        
        # Step 6: 본문 (JavaScript)
        print(f"\n📝 본문 입력...")
        
        article = driver.find_element(By.CSS_SELECTOR, 'article.se-components-wrap')
        
        # 기존 내용 삭제
        driver.execute_script("""
            const article = arguments[0];
            const paragraphs = article.querySelectorAll('p.se-text-paragraph');
            paragraphs.forEach(p => p.remove());
        """, article)
        random_delay()
        
        # 새 내용 추가
        lines = new_content.split('\n')
        for line in lines:
            if line.strip():
                driver.execute_script("""
                    const article = arguments[0];
                    const text = arguments[1];
                    
                    const p = document.createElement('p');
                    p.className = 'se-text-paragraph se-text-paragraph-align-left';
                    p.style.lineHeight = '1.6';
                    
                    const span = document.createElement('span');
                    span.className = 'se-ff-system se-fs15 __se-node';
                    span.style.color = 'rgb(0, 0, 0)';
                    span.textContent = text;
                    
                    p.appendChild(span);
                    article.querySelector('.se-module-text').appendChild(p);
                """, article, line)
        
        print("✅ 본문 완료")
        random_delay(1, 2)
        
        # Step 7: 이미지 (서버에서 다운로드)
        if image_urls:
            print(f"\n📷 이미지 업로드 ({len(image_urls)}개)...")
            
            for i, img_url in enumerate(image_urls, 1):
                print(f"\n이미지 {i}/{len(image_urls)}: {img_url}")
                
                # 서버에서 다운로드
                temp_path = download_image_from_server(img_url)
                if temp_path:
                    temp_files.append(temp_path)
            
            # 모든 이미지 다운로드 완료 후 업로드
            if temp_files:
                print(f"\n📤 {len(temp_files)}개 이미지 업로드 중...")
                
                # 이미지를 하나씩 업로드
                for idx, temp_file in enumerate(temp_files, 1):
                    try:
                        print(f"\n이미지 {idx}/{len(temp_files)} 업로드 중...")
                        
                        # file input 모두 찾기
                        file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                        print(f"  file input {len(file_inputs)}개 발견")
                        
                        if file_inputs:
                            # accept 속성 확인
                            for fi in file_inputs:
                                accept = fi.get_attribute('accept')
                                print(f"    accept: {accept}")
                            
                            # 이미지용 file input 찾기
                            image_input = None
                            for fi in file_inputs:
                                accept = fi.get_attribute('accept') or ''
                                if 'image' in accept.lower() or not accept:
                                    image_input = fi
                                    break
                            
                            if image_input:
                                # JavaScript로 강제 표시
                                driver.execute_script("""
                                    const input = arguments[0];
                                    input.style.display = 'block';
                                    input.style.visibility = 'visible';
                                    input.style.opacity = '1';
                                    input.style.position = 'fixed';
                                    input.style.top = '0';
                                    input.style.left = '0';
                                    input.style.zIndex = '9999';
                                """, image_input)
                                
                                random_delay(0.5, 1)
                                
                                # 파일 경로 전달
                                print(f"  파일 전송: {Path(temp_file).name}")
                                image_input.send_keys(temp_file)
                                
                                random_delay(3, 5)  # 업로드 대기
                                
                                # input 다시 숨기기
                                driver.execute_script("""
                                    const input = arguments[0];
                                    input.style.display = 'none';
                                """, image_input)
                                
                                print(f"  ✅ 이미지 {idx} 업로드 완료")
                            else:
                                print("  ❌ 이미지용 file input 없음")
                        else:
                            print("  ❌ file input 없음")
                            
                    except Exception as e:
                        print(f"  ❌ 오류: {str(e)[:100]}")
                        import traceback
                        traceback.print_exc()
                
                print(f"\n✅ 모든 이미지 업로드 완료!")
        
        # Step 8: 태그
        if keyword:
            print(f"\n🏷️ 태그: {keyword}")
            
            tag_input = driver.find_element(By.CSS_SELECTOR, 'input.tag_input')
            tag_input.click()
            random_delay()
            human_type(tag_input, keyword)
            tag_input.send_keys(Keys.ENTER)
            
            print("✅ 태그 완료")
            random_delay(1, 2)
        
        # Step 9: 댓글 허용
        print("\n💬 댓글 허용...")
        
        try:
            label = driver.find_element(By.CSS_SELECTOR, 'label[for="coment"]')
            driver.execute_script("arguments[0].click();", label)
            print("✅ 댓글 허용 체크")
        except:
            print("⚠️ 댓글 허용 실패")
        
        random_delay(1, 2)
        
        # Step 10: 등록
        print("\n" + "="*60)
        print("✅ 글 수정 완료!")
        print("="*60)
        print("\n수동으로 [등록] 버튼을 눌러주세요")
        
        input("\n등록 완료 후 Enter...")
        
        # 새 URL
        final_url = driver.current_url
        print(f"\n📍 새 글 URL: {final_url}")
        
        return final_url
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        # 임시 파일 삭제
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
                print(f"🗑️ 임시 파일 삭제: {Path(temp_file).name}")
            except:
                pass
        
        input("\nEnter를 누르면 종료...")
        driver.quit()


def main():
    print("""
╔════════════════════════════════════════════════════════╗
║     네이버 카페 자동 글 수정 발행 - 최종 버전         ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 입력
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
            print(f"  추가: {img_url}")
    
    keyword = input("\n태그 (키워드): ").strip()
    
    print("\n" + "="*60)
    print("자동 발행 시작")
    print("="*60)
    
    final_url = post_to_cafe(
        account_id, account_pw, draft_url,
        target_board, new_title, new_content,
        image_urls, keyword
    )
    
    if final_url:
        print(f"\n✅ 발행 성공!")
        print(f"새 글 URL: {final_url}")
    else:
        print(f"\n❌ 발행 실패")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")

