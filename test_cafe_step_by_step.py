"""
네이버 카페 글 수정 - 단계별 디버그 버전
각 단계마다 확인하면서 진행

실행: python test_cafe_step_by_step.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
from pathlib import Path
import os

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
║     네이버 카페 글 수정 - 단계별 디버그               ║
╚════════════════════════════════════════════════════════╝
    """)
    
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    target_board = input("변경할 게시판명: ").strip()
    new_title = input("새 제목: ").strip()
    new_content = input("새 본문: ").strip()
    keyword = input("태그: ").strip()
    
    driver = setup_driver()
    
    try:
        # Step 1: 네이버 메인 → 로그인
        print("\n" + "="*60)
        print("Step 1: 네이버 로그인")
        print("="*60)
        
        # 네이버 메인 접속
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        print("✅ 네이버 메인 접속")
        
        # 로그인 버튼 클릭 (정확한 XPath)
        print("\n로그인 버튼 클릭...")
        login_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="account"]/div/a'))
        )
        login_btn.click()
        random_delay(2, 3)
        print("✅ 로그인 페이지 이동")
        
        # 로그인
        print("\nID/PW 입력 중...")
        id_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'id'))
        )
        human_type(id_input, account_id)
        random_delay()
        
        pw_input = driver.find_element(By.ID, 'pw')
        human_type(pw_input, account_pw)
        random_delay()
        
        # Enter로 로그인
        pw_input.send_keys(Keys.ENTER)
        random_delay(3, 5)
        
        if 'nid.naver.com' in driver.current_url:
            print("⚠️ 캡챠 표시")
            input("캡챠 해결 후 Enter...")
        
        print("✅ 로그인 완료\n")
        input("Step 1 완료. Enter를 눌러 계속...")
        
        # Step 2: 신규발행 글 접속
        print("\n" + "="*60)
        print("Step 2: 신규발행 글 접속")
        print("="*60)
        
        driver.get(draft_url)
        random_delay(5, 7)
        print(f"현재 URL: {driver.current_url}")
        
        # iframe 전환
        print("\niframe 전환...")
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        print("✅ iframe 전환 완료\n")
        input("Step 2 완료. Enter를 눌러 계속...")
        
        # Step 3: 수정 버튼 클릭
        print("\n" + "="*60)
        print("Step 3: 수정 버튼 클릭")
        print("="*60)
        
        # 현재 탭 개수
        original_tabs = driver.window_handles
        print(f"현재 탭 개수: {len(original_tabs)}")
        
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", modify_btn)
        random_delay()
        modify_btn.click()
        print("✅ 수정 버튼 클릭")
        random_delay(3, 5)
        
        # 새 탭이 열렸는지 확인
        new_tabs = driver.window_handles
        print(f"클릭 후 탭 개수: {len(new_tabs)}")
        
        if len(new_tabs) > len(original_tabs):
            # 새 탭으로 전환
            new_tab = [tab for tab in new_tabs if tab not in original_tabs][0]
            driver.switch_to.window(new_tab)
            print("✅ 새 탭으로 전환 완료!")
            random_delay(3, 5)  # 페이지 로드 대기
        else:
            print("⚠️ 같은 탭에서 페이지 이동")
        
        print(f"현재 URL: {driver.current_url}\n")
        input("Step 3 완료. Enter를 눌러 계속...")
        
        # Step 4: 글쓰기 페이지 분석
        print("\n" + "="*60)
        print("Step 4: 글쓰기 페이지 분석")
        print("="*60)
        
        print(f"\n현재 탭 개수: {len(driver.window_handles)}")
        print(f"현재 URL: {driver.current_url}")
        
        # iframe 확인
        iframes = driver.find_elements(By.TAG_NAME, 'iframe')
        print(f"iframe 개수: {len(iframes)}")
        
        # ⭐ iframe 전환하지 않음! (메인 페이지에서 직접 작업)
        print("✅ iframe 전환 없이 메인 페이지에서 직접 작업")
        
        # 요소 찾기
        print("\n요소 분석:")
        
        # 카테고리
        try:
            cat_btns = driver.find_elements(By.CSS_SELECTOR, 'button, div.FormSelectBox button')
            print(f"  버튼: {len(cat_btns)}개")
        except:
            print("  버튼: 못 찾음")
        
        # 제목
        try:
            titles = driver.find_elements(By.CSS_SELECTOR, 'textarea, input[type="text"]')
            print(f"  입력란: {len(titles)}개")
            for t in titles[:3]:
                ph = t.get_attribute('placeholder')
                if ph:
                    print(f"    - {ph}")
        except:
            print("  입력란: 못 찾음")
        
        # 본문
        try:
            articles = driver.find_elements(By.CSS_SELECTOR, 'article')
            print(f"  article: {len(articles)}개")
        except:
            print("  article: 못 찾음")
        
        # 태그
        try:
            tags = driver.find_elements(By.CSS_SELECTOR, 'input.tag_input, input[placeholder*="태그"]')
            print(f"  태그 입력: {len(tags)}개")
        except:
            print("  태그: 못 찾음")
        
        # 댓글 허용
        try:
            comment_cb = driver.find_element(By.ID, 'coment')
            print(f"  댓글 허용: 있음")
        except:
            print("  댓글 허용: 못 찾음")
        
        # 스크린샷
        driver.save_screenshot('debug_write_page.png')
        print("\n✅ 스크린샷 저장: debug_write_page.png")
        
        print("\n브라우저와 스크린샷을 확인하세요!")
        input("\nStep 4 완료. 확인 후 Enter...")
        
        # Step 5: 실제 작업 시도
        print("\n" + "="*60)
        print("Step 5: 카테고리 변경 시도")
        print("="*60)
        
        try:
            category_btn = driver.find_element(By.CSS_SELECTOR, 'div.FormSelectBox button')
            print(f"카테고리 버튼 찾음: {category_btn.text}")
            category_btn.click()
            random_delay(1, 2)
            
            options = driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
            print(f"옵션 {len(options)}개 발견")
            
            for opt in options:
                opt_text = opt.find_element(By.CSS_SELECTOR, 'span.option_text').text
                if target_board in opt_text:
                    print(f"✅ '{opt_text}' 클릭")
                    opt.click()
                    random_delay()
                    break
            
            input("\n카테고리 변경 완료. Enter...")
            
        except Exception as e:
            print(f"❌ 카테고리 오류: {e}")
            input("오류 확인 후 Enter...")
        
        # Step 6: 제목 입력 시도
        print("\n" + "="*60)
        print("Step 6: 제목 입력 시도")
        print("="*60)
        
        try:
            title_textarea = driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
            print(f"제목란 찾음")
            print(f"현재 값: '{title_textarea.get_attribute('value')}'")
            
            title_textarea.click()
            random_delay()
            title_textarea.send_keys(Keys.CONTROL + 'a')
            title_textarea.send_keys(Keys.DELETE)
            random_delay()
            
            human_type(title_textarea, new_title)
            print(f"✅ 제목 입력 완료")
            
            input("\n제목 입력 완료. Enter...")
            
        except Exception as e:
            print(f"❌ 제목 오류: {e}")
            import traceback
            traceback.print_exc()
            input("오류 확인 후 Enter...")
        
        # Step 7: 본문 입력 시도
        print("\n" + "="*60)
        print("Step 7: 본문 입력 시도")
        print("="*60)
        
        try:
            # article 찾기
            articles = driver.find_elements(By.CSS_SELECTOR, 'article.se-components-wrap')
            print(f"article 개수: {len(articles)}")
            
            if articles:
                article = articles[0]
                
                # article 내부의 실제 입력 가능한 요소 찾기
                print("본문 입력 가능한 요소 찾기...")
                
                # 방법 1: p 태그 찾기
                p_tags = article.find_elements(By.CSS_SELECTOR, 'p.se-text-paragraph')
                print(f"  p 태그: {len(p_tags)}개")
                
                # 방법 2: span 태그 찾기
                span_tags = article.find_elements(By.CSS_SELECTOR, 'span.__se-node')
                print(f"  span 태그: {len(span_tags)}개")
                
                # 방법 3: contenteditable 요소
                editables = article.find_elements(By.CSS_SELECTOR, '[contenteditable="true"]')
                print(f"  contenteditable: {len(editables)}개")
                
                # 입력 시도: JavaScript 사용
                print("\nJavaScript로 본문 삭제 및 입력...")
                
                # 기존 내용 삭제
                driver.execute_script("""
                    const article = arguments[0];
                    const paragraphs = article.querySelectorAll('p.se-text-paragraph');
                    paragraphs.forEach(p => p.remove());
                """, article)
                random_delay()
                
                # 새 내용 추가
                lines = new_content.split('\n')
                for i, line in enumerate(lines):
                    if line.strip():
                        driver.execute_script("""
                            const article = arguments[0];
                            const text = arguments[1];
                            
                            // 새 p 태그 생성
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
                        print(f"  → 줄 {i+1} 추가")
                
                print("✅ 본문 입력 완료 (JavaScript)")
                random_delay(1, 2)
            else:
                print("❌ article 못 찾음")
            
            input("\n본문 입력 완료. Enter...")
            
        except Exception as e:
            print(f"❌ 본문 오류: {str(e)[:100]}")
            import traceback
            traceback.print_exc()
            input("오류 확인 후 Enter...")
        
        # Step 7.5: 사진 업로드 (테스트)
        print("\n" + "="*60)
        print("Step 7.5: 사진 업로드 테스트")
        print("="*60)
        
        image_test = input("\n사진 업로드 테스트하시겠습니까? (y/n): ").lower() == 'y'
        
        if image_test:
            image_path = input("이미지 경로: ").strip()
            
            # 따옴표 제거
            image_path = image_path.strip('"').strip("'")
            
            if image_path and Path(image_path).exists():
                try:
                    print("\n숨겨진 파일 input 찾기...")
                    
                    # 모든 file input 찾기
                    file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                    print(f"file input {len(file_inputs)}개 발견")
                    
                    # 이미지용 file input 찾기
                    image_input = None
                    for inp in file_inputs:
                        accept = inp.get_attribute('accept')
                        if accept and 'image' in accept:
                            image_input = inp
                            print(f"✅ 이미지 input 찾음 (accept: {accept})")
                            break
                    
                    if not image_input and file_inputs:
                        # accept 없으면 첫 번째 사용
                        image_input = file_inputs[0]
                        print("✅ 첫 번째 file input 사용")
                    
                    if image_input:
                        # 절대 경로로 변환
                        abs_path = str(Path(image_path).resolve())
                        print(f"파일 경로: {abs_path}")
                        print(f"파일 존재: {Path(abs_path).exists()}")
                        
                        # input이 보이는지 확인
                        is_displayed = image_input.is_displayed()
                        print(f"input 보임: {is_displayed}")
                        
                        # 직접 파일 경로 전달 (탐색기 없이!)
                        print("파일 경로 전송 중...")
                        image_input.send_keys(abs_path)
                        
                        print("업로드 대기 중...")
                        random_delay(5, 7)  # 업로드 대기
                        
                        print(f"✅ 이미지 업로드 시도 완료")
                        print("   브라우저에서 이미지가 추가되었는지 확인하세요!")
                    else:
                        print("❌ file input을 찾을 수 없음")
                    
                except Exception as e:
                    print(f"❌ 사진 업로드 실패: {str(e)[:100]}")
                    import traceback
                    traceback.print_exc()
            else:
                print("⚠️ 파일 경로가 유효하지 않습니다")
            
            input("\n사진 업로드 테스트 완료. Enter...")
        else:
            print("⏭️ 사진 업로드 건너뛰기")
        
        # Step 8: 태그 입력 시도
        print("\n" + "="*60)
        print("Step 8: 태그 입력 시도")
        print("="*60)
        
        if keyword:
            try:
                # 태그 입력란 여러 선택자 시도
                tag_input = None
                selectors = [
                    'input.tag_input',
                    'input[placeholder*="태그"]',
                    'div.tag_input_box input'
                ]
                
                for selector in selectors:
                    try:
                        tag_input = driver.find_element(By.CSS_SELECTOR, selector)
                        print(f"✅ 태그 입력란 찾음: {selector}")
                        break
                    except:
                        continue
                
                if tag_input:
                    tag_input.click()
                    random_delay()
                    human_type(tag_input, keyword)
                    tag_input.send_keys(Keys.ENTER)
                    print(f"✅ 태그 '{keyword}' 입력 완료")
                else:
                    print("❌ 태그 입력란을 찾을 수 없음")
                
                input("\n태그 입력 완료. Enter...")
                
            except Exception as e:
                print(f"❌ 태그 오류: {e}")
                import traceback
                traceback.print_exc()
                input("오류 확인 후 Enter...")
        
        # Step 9: 댓글 허용 체크
        print("\n" + "="*60)
        print("Step 9: 댓글 허용 체크 시도")
        print("="*60)
        
        try:
            # JavaScript로 체크박스 상태 확인 및 변경
            is_checked = driver.execute_script('return document.getElementById("coment").checked')
            print(f"현재 상태: {'체크됨' if is_checked else '체크 안됨'}")
            
            if not is_checked:
                # label 클릭 (더 안전)
                label = driver.find_element(By.CSS_SELECTOR, 'label[for="coment"]')
                driver.execute_script("arguments[0].click();", label)
                print("✅ 댓글 허용 체크 완료 (label 클릭)")
                
                # 재확인
                is_checked_after = driver.execute_script('return document.getElementById("coment").checked')
                print(f"체크 후 상태: {'체크됨' if is_checked_after else '체크 안됨'}")
            
            random_delay(1, 2)
            input("\n댓글 허용 완료. Enter...")
            
        except Exception as e:
            print(f"❌ 댓글 허용 오류: {str(e)[:100]}")
            import traceback
            traceback.print_exc()
            input("\n오류 확인 후 Enter...")
        
        # Step 10: 등록 버튼 확인
        print("\n" + "="*60)
        print("Step 10: 등록 버튼 확인")
        print("="*60)
        
        try:
            submit_btns = driver.find_elements(By.CSS_SELECTOR, 'a.BaseButton, button.BaseButton')
            print(f"버튼 {len(submit_btns)}개 발견:")
            for i, btn in enumerate(submit_btns[:10], 1):
                text = btn.text.strip()
                classes = btn.get_attribute('class')
                print(f"  {i}. '{text}' (class: {classes[:40]})")
            
            # 등록 버튼 찾기
            submit_btn = driver.find_element(By.XPATH, '//a[.//span[text()="등록"]]')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
            print("\n✅ 등록 버튼 발견 (클릭 안 함)")
            
        except Exception as e:
            print(f"❌ 등록 버튼 오류: {e}")
        
        # 최종 확인
        print("\n" + "="*60)
        print("최종 확인")
        print("="*60)
        print("\n브라우저를 확인하세요:")
        print("  - 카테고리가 변경되었나요?")
        print("  - 제목이 입력되었나요?")
        print("  - 본문이 입력되었나요?")
        print("  - 태그가 입력되었나요?")
        print("  - 댓글 허용이 체크되었나요?")
        
        print("\n수동으로 [등록] 버튼을 눌러 최종 테스트하세요!")
        
        input("\n등록 완료 후 Enter...")
        
        final_url = driver.current_url
        print(f"\n📍 최종 URL: {final_url}")
        print("이것을 저장하세요!")
        
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\nEnter를 누르면 종료...")
        driver.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")

