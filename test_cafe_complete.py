"""
네이버 카페 글 수정 발행 - 완성 버전
정확한 선택자 사용

실행: python test_cafe_complete.py
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
    """사람처럼 한 글자씩 입력"""
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
║     네이버 카페 글 수정 발행 - 완성 버전               ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 입력
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    
    print("\n수정할 내용:")
    target_board = input("변경할 게시판명 (예: 용품 질문방): ").strip()
    new_title = input("새 제목: ").strip()
    
    print("\n본문 입력 (여러 줄 가능, 빈 줄 입력 시 종료):")
    content_lines = []
    while True:
        line = input("  ")
        if not line:
            break
        content_lines.append(line)
    new_content = '\n'.join(content_lines) if content_lines else "테스트 본문입니다."
    
    # 이미지 (선택)
    image_paths = []
    if input("\n이미지 추가? (y/n): ").lower() == 'y':
        while True:
            img_path = input("이미지 경로 (종료: Enter): ").strip()
            if not img_path:
                break
            if Path(img_path).exists():
                image_paths.append(img_path)
                print(f"  ✅ {Path(img_path).name}")
            else:
                print(f"  ❌ 파일 없음")
    
    keyword = input("\n태그 (키워드): ").strip()
    
    print("\n" + "="*60)
    print("  테스트 시작")
    print("="*60 + "\n")
    
    driver = setup_driver()
    
    try:
        # Step 1: 로그인
        print("🔐 로그인 중...")
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
        
        # Step 3: iframe 전환
        print("🔄 iframe 전환...")
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        print("✅ iframe 전환 완료")
        random_delay(2, 3)
        
        # Step 4: 수정 버튼 클릭
        print("🖱️ 수정 버튼 클릭...")
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modify_btn)
        random_delay()
        modify_btn.click()
        print("✅ 수정 버튼 클릭 완료")
        random_delay(5, 7)  # 페이지 로드 대기
        
        print(f"현재 URL: {driver.current_url}")
        
        # Step 5: 카테고리 변경
        print(f"\n📂 카테고리 변경: {target_board}")
        try:
            # 카테고리 드롭다운 버튼
            category_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.FormSelectBox button, button.select_current'))
            )
            category_btn.click()
            print("✅ 드롭다운 열림")
            random_delay(1, 2)
            
            # 옵션 찾기
            options = driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
            
            print(f"  📋 {len(options)}개 카테고리 발견")
            
            for option in options:
                option_text = option.find_element(By.CSS_SELECTOR, 'span.option_text').text.strip()
                if target_board in option_text or option_text in target_board:
                    print(f"  ✅ 찾음: {option_text}")
                    option.click()
                    random_delay(1, 2)
                    break
            else:
                print(f"  ⚠️ '{target_board}' 못 찾음")
                print("  사용 가능:")
                for i, opt in enumerate(options[:10], 1):
                    text = opt.find_element(By.CSS_SELECTOR, 'span.option_text').text
                    print(f"    {i}. {text}")
                input("\n수동으로 선택 후 Enter...")
                
        except Exception as e:
            print(f"❌ 카테고리 오류: {str(e)[:80]}")
            input("수동 선택 후 Enter...")
        
        # Step 6: 제목 입력
        print(f"\n✍️ 제목 입력: {new_title}")
        try:
            title_textarea = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea.textarea_input'))
            )
            
            title_textarea.click()
            random_delay(0.5, 1)
            
            # 기존 제목 삭제
            title_textarea.send_keys(Keys.CONTROL + 'a')
            random_delay(0.2, 0.3)
            title_textarea.send_keys(Keys.DELETE)
            random_delay(0.5, 1)
            
            # 새 제목 입력
            human_type(title_textarea, new_title)
            print("✅ 제목 입력 완료")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"❌ 제목 오류: {str(e)[:80]}")
            input("수동 입력 후 Enter...")
        
        # Step 7: 본문 입력
        print(f"\n✍️ 본문 입력 (줄바꿈 포함)...")
        try:
            # article 영역 찾기
            content_area = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article.se-components-wrap'))
            )
            
            content_area.click()
            random_delay(0.5, 1)
            
            # 기존 본문 삭제
            content_area.send_keys(Keys.CONTROL + 'a')
            random_delay(0.2, 0.3)
            content_area.send_keys(Keys.DELETE)
            random_delay(0.5, 1)
            
            # 새 본문 입력 (줄바꿈 처리)
            lines = new_content.split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    human_type(content_area, line)
                    print(f"  → 줄 {i+1} 입력 완료")
                
                if i < len(lines) - 1:
                    content_area.send_keys(Keys.ENTER)
                    random_delay(0.3, 0.5)
            
            print("✅ 본문 입력 완료")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"❌ 본문 오류: {str(e)[:80]}")
            input("수동 입력 후 Enter...")
        
        # Step 8: 이미지 업로드 (있으면)
        if image_paths:
            print(f"\n📷 이미지 업로드 ({len(image_paths)}개)...")
            try:
                photo_btn = driver.find_element(By.CSS_SELECTOR, 'button.se-image-toolbar-button')
                photo_btn.click()
                random_delay(2, 3)
                
                # 파일 input 대기
                file_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"][accept*="image"]'))
                )
                
                # 모든 이미지 한 번에
                file_input.send_keys('\n'.join(image_paths))
                random_delay(3, 5)
                
                print(f"✅ 이미지 {len(image_paths)}개 업로드 완료")
                
            except Exception as e:
                print(f"⚠️ 이미지 업로드 실패: {str(e)[:80]}")
                input("수동 업로드 후 Enter...")
        
        # Step 9: 태그 입력
        if keyword:
            print(f"\n🏷️ 태그 입력: {keyword}")
            try:
                tag_input = driver.find_element(By.CSS_SELECTOR, 'input.tag_input')
                tag_input.click()
                random_delay(0.5, 1)
                
                human_type(tag_input, keyword)
                tag_input.send_keys(Keys.ENTER)  # 태그 추가
                random_delay(0.5, 1)
                
                print("✅ 태그 입력 완료")
                
            except Exception as e:
                print(f"⚠️ 태그 실패: {str(e)[:80]}")
        
        # Step 10: 댓글 허용 체크
        print("\n💬 댓글 허용 설정...")
        try:
            comment_checkbox = driver.find_element(By.ID, 'coment')
            if not comment_checkbox.is_selected():
                comment_checkbox.click()
                print("✅ 댓글 허용 체크")
            else:
                print("✅ 이미 체크됨")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"⚠️ 댓글 체크 실패: {str(e)[:80]}")
        
        # Step 11: 등록 버튼 확인 (클릭 안 함)
        print("\n📍 등록 버튼 찾기...")
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, 'a.BaseButton--skinGreen')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            print("✅ 등록 버튼 발견")
            print(f"   선택자: a.BaseButton--skinGreen")
            
        except Exception as e:
            print(f"⚠️ 등록 버튼 못 찾음: {str(e)[:80]}")
        
        # 완료
        print("\n" + "="*60)
        print("✅ 글 수정 준비 완료!")
        print("="*60)
        print("\n브라우저를 확인하세요:")
        print(f"  ✅ 카테고리: {target_board}")
        print(f"  ✅ 제목: {new_title}")
        print(f"  ✅ 본문: {len(content_lines)}줄")
        if image_paths:
            print(f"  ✅ 이미지: {len(image_paths)}개")
        if keyword:
            print(f"  ✅ 태그: {keyword}")
        print("  ✅ 댓글 허용: 체크")
        
        print("\n🚨 자동 등록은 하지 않습니다!")
        print("브라우저에서 내용을 확인하고")
        print("수동으로 [등록] 버튼을 눌러주세요.")
        
        input("\n등록 완료 후 Enter를 누르세요...")
        
        # 등록 후 URL 확인
        final_url = driver.current_url
        print(f"\n📍 수정 후 URL: {final_url}")
        print("이것이 새로 발행된 글 URL입니다!")
        print("이 URL을 저장하세요!")
        
        print("\n✅ 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nEnter를 누르면 브라우저가 종료됩니다...")
        driver.quit()
        print("\n✅ 테스트 종료")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 테스트 취소됨")







