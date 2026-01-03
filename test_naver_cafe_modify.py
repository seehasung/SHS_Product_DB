"""
네이버 카페 글 수정 발행 테스트
로컬에서 독립적으로 실행 가능

실행: python test_naver_cafe_modify.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
from pathlib import Path

def random_delay(min_sec=0.5, max_sec=1.5):
    """랜덤 지연"""
    time.sleep(random.uniform(min_sec, max_sec))

def human_type(element, text):
    """사람처럼 한 글자씩 입력"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.1, 0.3))

def setup_driver():
    """Chrome 드라이버 설정"""
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)
    
    # WebDriver 속성 숨기기
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        '''
    })
    
    driver.set_window_size(1400, 900)
    return driver

def test_cafe_modify():
    """카페 글 수정 발행 테스트"""
    
    print("""
╔════════════════════════════════════════════════════════╗
║     네이버 카페 글 수정 발행 테스트                    ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 입력
    print("테스트 정보를 입력하세요:\n")
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    
    print("\n수정할 내용:")
    target_board = input("변경할 게시판명 (예: 용품 질문방): ").strip()
    new_title = input("새 제목: ").strip()
    new_content = input("새 본문: ").strip()
    
    # 이미지 (선택)
    image_paths = []
    if input("\n이미지를 추가하시겠습니까? (y/n): ").lower() == 'y':
        while True:
            img_path = input("이미지 경로 (종료: Enter): ").strip()
            if not img_path:
                break
            if Path(img_path).exists():
                image_paths.append(img_path)
                print(f"  ✅ {Path(img_path).name}")
            else:
                print(f"  ❌ 파일을 찾을 수 없습니다")
    
    tag = input("\n태그 (키워드): ").strip()
    
    print("\n" + "="*60)
    print("  테스트 시작")
    print("="*60 + "\n")
    
    driver = setup_driver()
    
    try:
        # Step 1: 네이버 로그인
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
        random_delay(3, 5)
        
        if 'nid.naver.com' in driver.current_url:
            print("⚠️  캡챠가 표시되었을 수 있습니다")
            input("수동으로 캡챠 해결 후 Enter를 누르세요...")
        else:
            print("✅ 로그인 성공!")
        
        # Step 2: 신규발행 글 접속
        print(f"\n📄 신규발행 글 접속: {draft_url}")
        driver.get(draft_url)
        random_delay(3, 5)
        
        # Step 3: 수정 버튼 클릭
        print("🖱️  수정 버튼 찾는 중...")
        try:
            # XPath: //*[@id="app"]/div/div/div[3]/div[1]/a[3]/span
            modify_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/div/div/div[3]/div[1]/a[3]'))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modify_btn)
            random_delay(0.5, 1)
            modify_btn.click()
            print("✅ 수정 버튼 클릭")
            random_delay(3, 5)
        except Exception as e:
            print(f"❌ 수정 버튼 찾기 실패: {e}")
            print("수동으로 수정 버튼을 눌러주세요")
            input("수정 버튼 클릭 후 Enter...")
        
        # Step 4: 카테고리 선택
        print(f"\n📂 카테고리 변경: {target_board}")
        try:
            # 카테고리 드롭박스 버튼
            category_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="app"]/div/div/section/div/div[2]/div[1]/div[1]/div/div[1]/div[1]/div/div[1]/button'))
            )
            category_btn.click()
            print("✅ 카테고리 드롭박스 열림")
            random_delay(1, 2)
            
            # 옵션 리스트에서 찾기
            option_list = driver.find_element(By.XPATH, '//*[@id="app"]/div/div/section/div/div[2]/div[1]/div[1]/div/div[1]/div[1]/div/div[2]/ul')
            options = option_list.find_elements(By.CSS_SELECTOR, 'li button span.option_text')
            
            print(f"  📋 총 {len(options)}개 카테고리 발견")
            
            # 텍스트 매칭
            for idx, option in enumerate(options):
                option_text = option.text.strip()
                if target_board in option_text or option_text in target_board:
                    print(f"  ✅ 카테고리 발견: {option_text}")
                    option.click()
                    random_delay(1, 2)
                    break
            else:
                print(f"  ⚠️  '{target_board}'를 찾을 수 없습니다")
                print("  사용 가능한 카테고리:")
                for i, opt in enumerate(options[:10], 1):
                    print(f"    {i}. {opt.text}")
                input("\n수동으로 카테고리 선택 후 Enter...")
                
        except Exception as e:
            print(f"❌ 카테고리 변경 실패: {e}")
            input("수동으로 선택 후 Enter...")
        
        # Step 5: 제목 입력
        print(f"\n✍️  제목 입력: {new_title}")
        try:
            title_textarea = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="app"]/div/div/section/div/div[2]/div[1]/div[1]/div/div[2]/div/textarea'))
            )
            
            # 기존 제목 지우기
            title_textarea.click()
            random_delay(0.5, 1)
            title_textarea.send_keys(Keys.CONTROL + 'a')
            random_delay(0.2, 0.3)
            title_textarea.send_keys(Keys.DELETE)
            random_delay(0.5, 1)
            
            # 새 제목 입력
            human_type(title_textarea, new_title)
            print("✅ 제목 입력 완료")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"❌ 제목 입력 실패: {e}")
            input("수동으로 입력 후 Enter...")
        
        # Step 6: 본문 입력
        print(f"\n✍️  본문 입력: {new_content}")
        try:
            # 본문 article 찾기 (동적 ID)
            article = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article.se-components-wrap'))
            )
            
            # 기존 내용 지우기
            article.click()
            random_delay(0.5, 1)
            
            # 전체 선택 및 삭제
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
            random_delay(0.3, 0.5)
            actions.send_keys(Keys.DELETE).perform()
            random_delay(0.5, 1)
            
            # 새 내용 입력 (줄바꿈 포함)
            lines = new_content.split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    human_type(article, line)
                if i < len(lines) - 1:
                    article.send_keys(Keys.ENTER)
                    random_delay(0.3, 0.5)
            
            print("✅ 본문 입력 완료")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"❌ 본문 입력 실패: {e}")
            print("수동으로 입력하세요")
            input("본문 입력 후 Enter...")
        
        # Step 7: 이미지 업로드 (있으면)
        if image_paths:
            print(f"\n📷 이미지 업로드 중... ({len(image_paths)}개)")
            try:
                # 사진 버튼 찾기 (동적 ID)
                photo_btn = driver.find_element(By.CSS_SELECTOR, 'button[aria-label="사진"], li button[title*="사진"]')
                photo_btn.click()
                random_delay(2, 3)
                
                # 파일 선택 input 찾기
                file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"][accept*="image"]')
                
                # 모든 이미지 경로를 한 번에 전달
                file_input.send_keys('\n'.join(image_paths))
                random_delay(3, 5)
                
                print(f"✅ 이미지 {len(image_paths)}개 업로드 완료")
                
            except Exception as e:
                print(f"⚠️  이미지 업로드 실패: {e}")
                print("수동으로 업로드하세요")
                input("업로드 후 Enter...")
        
        # Step 8: 태그 입력
        if tag:
            print(f"\n🏷️  태그 입력: {tag}")
            try:
                # 태그 입력란 찾기
                tag_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder*="태그"], input.tag_input')
                tag_input.click()
                random_delay(0.5, 1)
                human_type(tag_input, tag)
                random_delay(0.5, 1)
                
                print("✅ 태그 입력 완료")
                
            except Exception as e:
                print(f"⚠️  태그 입력 실패: {e}")
                print("태그는 선택사항입니다")
        
        # Step 9: 댓글 허용 체크
        print("\n💬 댓글 허용 설정...")
        try:
            comment_checkbox = driver.find_element(By.ID, 'coment')
            if not comment_checkbox.is_selected():
                comment_checkbox.click()
                print("✅ 댓글 허용 체크")
            else:
                print("✅ 댓글 허용 이미 체크됨")
            random_delay(1, 2)
            
        except Exception as e:
            print(f"⚠️  댓글 허용 체크 실패: {e}")
        
        # Step 10: 등록 버튼 확인
        print("\n" + "="*60)
        print("✅ 글 수정 준비 완료!")
        print("="*60)
        print("\n브라우저를 확인하세요:")
        print("  ✅ 카테고리 변경됨")
        print("  ✅ 제목 입력됨")
        print("  ✅ 본문 입력됨")
        if image_paths:
            print("  ✅ 이미지 업로드됨")
        if tag:
            print("  ✅ 태그 입력됨")
        print("  ✅ 댓글 허용 체크됨")
        
        print("\n🚨 중요: 자동 등록은 하지 않습니다!")
        print("브라우저에서 내용을 확인하고")
        print("수동으로 [등록] 버튼을 눌러 테스트를 완료하세요.")
        print()
        
        # 등록 버튼 찾기만 (클릭 안함)
        try:
            submit_btn = driver.find_element(By.XPATH, '//*[@id="app"]/div/div/section/div/div[1]/div/a')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            print("📍 등록 버튼 위치 표시됨")
            print(f"   XPath: //*[@id=\"app\"]/div/div/section/div/div[1]/div/a")
        except:
            print("⚠️  등록 버튼을 찾을 수 없습니다")
        
        print("\n" + "="*60)
        input("\n수동으로 등록 완료 후 Enter를 누르면 종료됩니다...")
        
        # 등록 후 새 URL 확인
        final_url = driver.current_url
        print(f"\n📍 현재 URL: {final_url}")
        print("이것이 수정 발행된 새 글 URL입니다!")
        
        print("\n✅ 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        input("\nEnter를 눌러 종료...")
    finally:
        input("\nEnter를 누르면 브라우저가 종료됩니다...")
        driver.quit()
        print("\n✅ 테스트 종료")


# 추가: 댓글 작성 테스트
def test_cafe_comment():
    """카페 댓글 작성 테스트"""
    
    print("""
╔════════════════════════════════════════════════════════╗
║     네이버 카페 댓글 작성 테스트                       ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 입력
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    post_url = input("글 URL: ").strip()
    comment_text = input("댓글 내용: ").strip()
    
    print("\n" + "="*60)
    print("  테스트 시작")
    print("="*60 + "\n")
    
    driver = setup_driver()
    
    try:
        # 로그인
        print("🔐 네이버 로그인 중...")
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        id_input = driver.find_element(By.ID, 'id')
        human_type(id_input, account_id)
        random_delay(0.5, 1)
        
        pw_input = driver.find_element(By.ID, 'pw')
        human_type(pw_input, account_pw)
        random_delay(0.5, 1)
        
        login_btn = driver.find_element(By.CSS_SELECTOR, '.btn_login')
        login_btn.click()
        random_delay(3, 5)
        
        if 'nid.naver.com' in driver.current_url:
            input("캡챠 해결 후 Enter...")
        
        # 글 페이지 접속
        print(f"\n📄 글 페이지 접속...")
        driver.get(post_url)
        random_delay(3, 5)
        
        # 댓글 입력
        print(f"💬 댓글 입력: {comment_text}")
        try:
            # 댓글 입력창 찾기 (여러 선택자 시도)
            comment_input = None
            selectors = [
                'textarea.comment_inbox',
                'textarea[placeholder*="댓글"]',
                'div[contenteditable="true"]',
                'textarea.input_comment'
            ]
            
            for selector in selectors:
                try:
                    comment_input = driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            if comment_input:
                comment_input.click()
                random_delay(0.5, 1)
                human_type(comment_input, comment_text)
                print("✅ 댓글 입력 완료")
                random_delay(1, 2)
                
                print("\n수동으로 등록 버튼을 눌러 댓글을 달아주세요")
            else:
                print("❌ 댓글 입력창을 찾을 수 없습니다")
                print("수동으로 댓글을 달아주세요")
                
        except Exception as e:
            print(f"❌ 댓글 입력 실패: {e}")
        
        input("\n댓글 등록 후 Enter...")
        print("✅ 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nEnter를 누르면 종료...")
        driver.quit()


if __name__ == "__main__":
    print("""
테스트 선택:
1. 글 수정 발행 테스트
2. 댓글 작성 테스트
    """)
    
    choice = input("선택 (1-2): ").strip()
    
    try:
        if choice == '1':
            test_cafe_modify()
        elif choice == '2':
            test_cafe_comment()
        else:
            print("잘못된 선택")
    except KeyboardInterrupt:
        print("\n\n⏹️ 테스트 취소됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")

