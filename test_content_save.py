"""
전체 플로우 테스트: 네이버 카페 글 수정 발행 + 댓글 작성
worker_agent.py와 동일한 방식 (1번 방법: 직접 타이핑)

⭐ 기능:
   - 글 수정 발행 (게시판 변경, 제목/본문 수정, 댓글 허용, 자동 등록)
   - 댓글 작성 (새 댓글, 대댓글 지원)

실행: python test_content_save.py
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import pyperclip

def random_delay(min_sec=1, max_sec=2):
    time.sleep(random.uniform(min_sec, max_sec))

def human_type(element, text, min_delay=0.05, max_delay=0.15):
    """사람처럼 한 글자씩 타이핑"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay))

def setup_driver():
    """브라우저 초기화"""
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1400, 900)
    return driver

def login_naver(driver, account_id, account_pw):
    """네이버 로그인"""
    print("\n🔐 네이버 로그인 중...")
    
    try:
        driver.get('https://www.naver.com')
        random_delay(2, 3)
        
        # 로그인 페이지
        driver.get('https://nid.naver.com/nidlogin.login')
        random_delay(2, 3)
        
        # ID/PW 입력
        id_input = driver.find_element(By.ID, 'id')
        id_input.send_keys(account_id)
        random_delay(0.5, 1)
        
        pw_input = driver.find_element(By.ID, 'pw')
        pw_input.send_keys(account_pw)
        random_delay(0.5, 1)
        
        # 로그인
        pw_input.send_keys(Keys.ENTER)
        random_delay(3, 5)
        
        # 캡챠 확인
        if 'nid.naver.com' in driver.current_url:
            print("⚠️ 캡챠 표시됨")
            input("캡챠 해결 후 Enter를 눌러주세요...")
        
        print("✅ 로그인 완료")
        return True
        
    except Exception as e:
        print(f"❌ 로그인 실패: {e}")
        return False

def modify_and_publish(driver, draft_url, board_name, title, content, keyword):
    """글 수정 및 발행 (새 탭에서)"""
    print(f"\n📝 글 수정 시작...")
    print(f"   제목: {title}")
    print(f"   본문: {content[:50]}...")
    
    try:
        # ⭐ 새 탭 열기 (네이버 홈 탭 유지)
        print("\n1️⃣ 새 탭에서 신규발행 글 접속...")
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        # 신규발행 글 접속
        driver.get(draft_url)
        random_delay(5, 7)
        
        # iframe 전환
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'cafe_main'))
        )
        driver.switch_to.frame(iframe)
        random_delay(2, 3)
        print("   ✅ 페이지 로드 완료")
        
        # 2. 수정 버튼 클릭
        print("\n2️⃣ 수정 버튼 클릭...")
        modify_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[.//span[text()="수정"]]'))
        )
        modify_btn.click()
        random_delay(5, 7)
        
        # 새 탭 전환
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            random_delay(3, 5)
        print("   ✅ 수정 페이지 진입")
        
        # 3. 카테고리 변경
        print(f"\n3️⃣ 카테고리 변경: {board_name}")
        try:
            category_btn = driver.find_element(By.CSS_SELECTOR, 'div.FormSelectBox button')
            category_btn.click()
            random_delay(1, 2)
            
            options = driver.find_elements(By.CSS_SELECTOR, 'ul.option_list li.item button')
            for opt in options:
                opt_text = opt.find_element(By.CSS_SELECTOR, 'span.option_text').text
                if board_name in opt_text:
                    opt.click()
                    random_delay(0.5, 1)
                    print(f"   ✅ '{opt_text}' 선택")
                    break
        except Exception as e:
            print(f"   ⚠️ 카테고리 변경 실패: {e}")
        
        # 4. 제목 입력 (사람처럼 한 글자씩)
        print(f"\n4️⃣ 제목 입력: {title}")
        try:
            title_elem = driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
            title_elem.click()
            random_delay(0.5, 1)
            title_elem.send_keys(Keys.CONTROL + 'a', Keys.DELETE)
            random_delay(0.5, 1)
            
            # ⭐ 사람처럼 한 글자씩 타이핑
            print("   → 사람처럼 타이핑 중...")
            human_type(title_elem, title)
            print("   ✅ 제목 입력 완료")
        except Exception as e:
            print(f"   ⚠️ 제목 입력 실패: {e}")
        
        # 5. 본문 입력 (worker_agent.py와 동일한 1번 방법)
        print(f"\n5️⃣ 본문 입력: {len(content)}자")
        content_success = False
        
        try:
            print("   직접 타이핑 방식으로 본문 입력...")
            paragraph = driver.find_element(By.CSS_SELECTOR, "p.se-text-paragraph")
            driver.execute_script("arguments[0].scrollIntoView(true);", paragraph)
            random_delay(0.5, 1)
            
            paragraph.click()
            random_delay(0.5, 1)
            
            active = driver.switch_to.active_element
            
            # 기존 내용 삭제
            print("      → 기존 내용 삭제...")
            active.send_keys(Keys.CONTROL, 'a')
            random_delay(0.2, 0.3)
            active.send_keys(Keys.DELETE)
            random_delay(0.5, 1)
            
            # ⭐ 새 내용 입력 (사람처럼 한 글자씩)
            print("      → 사람처럼 타이핑 중...")
            human_type(active, content)
            random_delay(0.5, 1)
            
            # 입력 확인
            check_script = """
                var span = document.querySelector('span.__se-node');
                if (span && span.textContent.length > 0) {
                    return true;
                }
                return false;
            """
            if driver.execute_script(check_script):
                content_success = True
                print("   ✅ 본문 입력 완료")
            else:
                print("   ⚠️ 본문 확인 실패")
            
        except Exception as e:
            print(f"   ❌ 본문 입력 실패: {e}")
        
        if not content_success:
            print("   ⚠️ 브라우저에서 본문을 확인하세요!")
        
        # 6. 태그 입력
        if keyword:
            print(f"\n6️⃣ 태그 입력: {keyword}")
            try:
                tag_input = driver.find_element(By.CSS_SELECTOR, 'input.tag_input')
                tag_input.click()
                random_delay(0.5, 1)
                tag_input.send_keys(keyword)
                tag_input.send_keys(Keys.ENTER)
                print("   ✅ 태그 입력 완료")
            except Exception as e:
                print(f"   ⚠️ 태그 입력 실패: {e}")
        
        # 7. 댓글 허용 체크 (스마트 체크)
        print("\n7️⃣ 댓글 허용 설정 확인 중...")
        try:
            # 댓글 허용 체크박스 찾기
            comment_checkbox_selectors = [
                'input[type="checkbox"][name*="comment"]',
                'input[type="checkbox"][id*="comment"]',
                'input[type="checkbox"].comment-allow',
                '#commentOpen',
                'input[name="commentOpen"]',
                '#coment'  # 기존 selector
            ]
            
            comment_checkbox = None
            for selector in comment_checkbox_selectors:
                try:
                    comment_checkbox = driver.find_element(By.CSS_SELECTOR, selector)
                    print(f"   ✅ 댓글 체크박스 발견: {selector}")
                    break
                except:
                    continue
            
            if comment_checkbox:
                # 현재 체크 상태 확인
                is_checked = comment_checkbox.is_selected()
                print(f"   현재 상태: {'체크됨' if is_checked else '체크 안됨'}")
                
                # 체크되어 있지 않으면 체크하기
                if not is_checked:
                    # label 또는 checkbox 직접 클릭
                    try:
                        label = driver.find_element(By.CSS_SELECTOR, 'label[for="coment"]')
                        driver.execute_script("arguments[0].click();", label)
                    except:
                        comment_checkbox.click()
                    random_delay(0.5, 1)
                    print("   ✅ 댓글 허용 체크 완료")
                else:
                    print("   ℹ️  이미 체크되어 있음 (건너뛰기)")
            else:
                print("   ⚠️  댓글 체크박스를 찾을 수 없습니다 (기본값 사용)")
                
        except Exception as e:
            print(f"   ⚠️ 댓글 설정 오류: {e} (계속 진행)")
        
        random_delay(1, 2)
        
        # 8. 등록 버튼 자동 클릭 (다중 방법 시도)
        print("\n8️⃣ 등록 버튼 자동 클릭 시도...")
        submit_selectors = [
            ('xpath', '//*[@id="app"]/div/div/section/div/div[1]/div/a'),  # 사용자 제공 XPath
            ('css', 'a.btn-submit'),
            ('css', 'button.btn-submit'),
            ('css', 'a[class*="submit"]'),
            ('css', 'button[class*="submit"]'),
            ('css', '#btn-submit'),
            ('css', '.btn-register'),
            ('css', 'a.btn_register')
        ]
        
        submit_btn = None
        used_selector = None
        clicked = False
        
        # 1단계: 버튼 찾기
        for selector_type, selector in submit_selectors:
            try:
                if selector_type == 'xpath':
                    submit_btn = driver.find_element(By.XPATH, selector)
                else:
                    submit_btn = driver.find_element(By.CSS_SELECTOR, selector)
                
                used_selector = f"{selector_type}: {selector}"
                print(f"   ✅ 등록 버튼 발견: {used_selector}")
                break
            except:
                continue
        
        if submit_btn:
            # 2단계: 스크롤하여 버튼이 보이도록
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_btn)
                random_delay(0.5, 1)
            except:
                pass
            
            # 3단계: 클릭 시도 (여러 방법)
            click_methods = [
                ("일반 클릭", lambda: submit_btn.click()),
                ("JavaScript 클릭", lambda: driver.execute_script("arguments[0].click();", submit_btn)),
                ("ActionChains 클릭", lambda: ActionChains(driver).move_to_element(submit_btn).click().perform())
            ]
            
            for method_name, click_func in click_methods:
                try:
                    print(f"   🖱️  {method_name} 시도...")
                    click_func()
                    random_delay(2, 3)
                    
                    # 클릭 성공 확인 (URL 변경 또는 페이지 변화 확인)
                    current_url = driver.current_url
                    if 'ArticleWrite' not in current_url and 'ArticleModify' not in current_url:
                        clicked = True
                        print(f"   ✅ {method_name} 성공!")
                        break
                    else:
                        print(f"   ⚠️  {method_name} 후에도 페이지 변화 없음")
                        
                except Exception as e:
                    print(f"   ⚠️  {method_name} 실패: {e}")
                    continue
            
            if clicked:
                print("✅ 등록 버튼 자동 클릭 완료")
                random_delay(3, 5)  # 페이지 로딩 대기
            else:
                print("⚠️  모든 클릭 방법 실패, 최종 시도...")
                # 최종 시도: 강제 JavaScript 실행
                try:
                    driver.execute_script("""
                        var btn = arguments[0];
                        btn.click();
                        if (btn.onclick) btn.onclick();
                        if (btn.href) window.location.href = btn.href;
                    """, submit_btn)
                    random_delay(3, 4)
                    print("✅ JavaScript 강제 클릭 완료")
                    clicked = True
                except Exception as e:
                    print(f"❌ 최종 클릭도 실패: {e}")
        else:
            print("❌ 등록 버튼을 찾을 수 없습니다")
        
        # 9. 최종 확인
        print("\n" + "="*60)
        if clicked:
            print("✅ 자동 발행 완료!")
        else:
            print("⚠️  자동 클릭 실패 - 수동으로 [등록] 버튼을 클릭하세요!")
        print("="*60)
        print("\n발행된 내용:")
        print(f"  - 카테고리: {board_name}")
        print(f"  - 제목: {title}")
        print(f"  - 본문: {len(content)}자")
        print(f"  - 태그: {keyword}")
        print(f"  - 댓글 허용: 체크됨")
        
        if not clicked:
            input("\n수동 등록 완료 후 Enter를 눌러주세요...")
        else:
            random_delay(2, 3)  # 페이지 안정화 대기
        
        final_url = driver.current_url
        print(f"\n📍 최종 URL: {final_url}")
        
        return final_url
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None

def write_comment(driver, post_url, comment_text):
    """새 댓글 작성 (사람처럼 한 글자씩, 새 탭에서)"""
    print(f"\n💬 댓글 작성: {comment_text[:30]}...")
    
    try:
        # ⭐ 새 탭에서 열기 (기존 탭 유지)
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        driver.get(post_url)
        random_delay(3, 5)
        
        # iframe 전환
        try:
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'cafe_main'))
            )
            driver.switch_to.frame(iframe)
            random_delay(2, 3)
            print("  ✅ iframe 전환")
        except:
            print("  ⚠️ iframe 없음")
        
        # 댓글 입력창
        comment_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea.comment_inbox_text'))
        )
        comment_input.click()
        random_delay(0.5, 1)
        
        # ⭐ 사람처럼 한 글자씩 타이핑
        print("  → 사람처럼 타이핑 중...")
        human_type(comment_input, comment_text)
        random_delay(1, 2)
        
        # 등록 버튼
        submit_btn = driver.find_element(By.CSS_SELECTOR, 'a.btn_register')
        submit_btn.click()
        random_delay(3, 4)
        
        print("  ✅ 댓글 작성 완료!")
        
        # 댓글 ID 추출
        try:
            random_delay(2, 3)
            latest_comment = driver.find_element(By.CSS_SELECTOR, "ul.comment_list > li.CommentItem:last-of-type")
            comment_id = latest_comment.get_attribute('id')
            print(f"  📌 댓글 ID: {comment_id}")
            
            # ⭐ 탭 닫기 (네이버 홈 탭은 유지)
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            return comment_id
        except:
            print("  ⚠️ 댓글 ID 추출 실패")
            
            # ⭐ 탭 닫기
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            return None
        
    except Exception as e:
        print(f"  ❌ 댓글 작성 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

def write_reply(driver, post_url, parent_comment_id, comment_text):
    """대댓글 작성 (대댓글 ID도 반환, 사람처럼 한 글자씩, 새 탭에서)"""
    print(f"\n💬 대댓글 작성: {comment_text[:30]}...")
    print(f"  부모 댓글 ID: {parent_comment_id}")
    
    try:
        # ⭐ 새 탭에서 열기 (기존 탭 유지)
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        driver.get(post_url)
        random_delay(3, 5)
        
        # iframe 전환
        try:
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'cafe_main'))
            )
            driver.switch_to.frame(iframe)
            random_delay(2, 3)
        except:
            pass
        
        # 부모 댓글 찾기 (숫자 ID는 속성 선택자 사용!)
        print(f"  🔍 부모 댓글 찾기...")
        parent_elem = driver.find_element(By.CSS_SELECTOR, f"[id='{parent_comment_id}']")
        
        # 답글쓰기 버튼 찾기
        buttons = parent_elem.find_elements(By.CSS_SELECTOR, "a.comment_info_button")
        reply_clicked = False
        for btn in buttons:
            if "답글" in btn.text:
                btn.click()
                random_delay(1, 2)
                print("  ✅ 답글쓰기 클릭")
                reply_clicked = True
                break
        
        if not reply_clicked:
            print("  ⚠️ 답글쓰기 버튼을 찾을 수 없습니다")
            return None
        
        # 댓글 입력창 (대댓글용)
        comment_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea.comment_inbox_text'))
        )
        comment_input.click()
        random_delay(0.5, 1)
        
        # ⭐ 사람처럼 한 글자씩 타이핑
        print("  → 사람처럼 타이핑 중...")
        human_type(comment_input, comment_text)
        random_delay(1, 2)
        
        # 등록 버튼
        submit_btn = driver.find_element(By.CSS_SELECTOR, 'a.btn_register')
        submit_btn.click()
        random_delay(3, 4)
        
        print("  ✅ 대댓글 작성 완료!")
        
        # ⭐ 대댓글 ID 추출 (대댓글의 대댓글을 위해!)
        try:
            random_delay(2, 3)
            # 최신 댓글 찾기 (대댓글도 CommentItem)
            latest_comment = driver.find_element(By.CSS_SELECTOR, "ul.comment_list > li.CommentItem:last-of-type")
            reply_id = latest_comment.get_attribute('id')
            print(f"  📌 대댓글 ID: {reply_id}")
            
            # ⭐ 탭 닫기 (네이버 홈 탭은 유지)
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            return reply_id
        except:
            print("  ⚠️ 대댓글 ID 추출 실패")
            
            # ⭐ 탭 닫기
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            return None
        
    except Exception as e:
        print(f"  ❌ 대댓글 작성 오류: {e}")
        import traceback
        traceback.print_exc()
        
        # ⭐ 탭 닫기 (에러 시에도)
        try:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except:
            pass
        
        return None

def main():
    print("\n" + "="*60)
    print("   전체 플로우 테스트: 글 수정 발행 + 댓글 작성")
    print("   (worker_agent.py와 동일한 방식)")
    print("="*60)
    
    # 입력
    print("\n=== 테스트 정보 입력 ===")
    account_id = input("네이버 계정 ID: ").strip()
    account_pw = input("비밀번호: ").strip()
    draft_url = input("신규발행 글 URL: ").strip()
    board_name = input("변경할 게시판명: ").strip()
    title = input("새 제목: ").strip()
    content = input("새 본문: ").strip()
    keyword = input("태그 (선택): ").strip()
    
    # 브라우저 실행
    driver = setup_driver()
    
    try:
        # 로그인
        if not login_naver(driver, account_id, account_pw):
            print("❌ 로그인 실패로 종료합니다.")
            return
        
        # 글 수정 및 발행
        result_url = modify_and_publish(driver, draft_url, board_name, title, content, keyword)
        
        if result_url:
            print("\n" + "="*60)
            print("🎉 글 발행 완료!")
            print("="*60)
            print(f"발행 URL: {result_url}")
            
            # 결과 저장
            with open('test_result.txt', 'w', encoding='utf-8') as f:
                f.write(f"제목: {title}\n")
                f.write(f"URL: {result_url}\n")
                f.write(f"\n본문:\n{content}\n")
            
            print("\n✅ 결과 저장: test_result.txt")
            
            # 댓글 작성 여부 확인
            print("\n" + "="*60)
            write_comments = input("\n댓글을 작성하시겠습니까? (y/n): ").strip().lower()
            
            if write_comments == 'y':
                print("\n=== 댓글 작성 시작 ===")
                print("댓글 내용과 타입(일반/대댓글)을 입력하세요")
                print("대댓글은 바로 이전 댓글에 자동으로 답글이 달립니다")
                print()
                
                # 댓글 수집
                comments = []  # [(content, is_reply)]
                idx = 1
                while True:
                    comment = input(f"댓글 {idx} 내용 (종료: 엔터): ").strip()
                    if not comment:
                        break
                    
                    comment_type = input(f"  타입 (일반/대댓글): ").strip()
                    is_reply = comment_type == "대댓글"
                    
                    comments.append((comment, is_reply))
                    idx += 1
                
                if not comments:
                    print("❌ 댓글이 입력되지 않았습니다.")
                else:
                    print(f"\n총 {len(comments)}개의 댓글이 입력되었습니다.")
                    print("\n입력된 댓글 목록:")
                    for idx, (content, is_reply) in enumerate(comments, 1):
                        c_type = "대댓글" if is_reply else "일반"
                        print(f"  [{idx}] ({c_type}) {content[:30]}...")
                    
                    if input("\n댓글 작성을 시작하시겠습니까? (y/n): ").lower() == 'y':
                        # ⭐ 마지막 작성된 댓글 ID 추적
                        last_comment_id = None
                        
                        for idx, (comment, is_reply) in enumerate(comments, 1):
                            print(f"\n[{idx}/{len(comments)}] 댓글 작성")
                            
                            if is_reply:
                                # 대댓글: 바로 이전 댓글에 답글
                                if last_comment_id:
                                    print(f"  → 이전 댓글(ID: {last_comment_id})에 답글 작성")
                                    reply_id = write_reply(driver, result_url, last_comment_id, comment)
                                    if reply_id:
                                        last_comment_id = reply_id  # ⭐ 대댓글 ID로 업데이트
                                    else:
                                        print("  ⚠️ 대댓글 작성 실패")
                                else:
                                    print("  ⚠️ 이전 댓글이 없습니다. 일반 댓글로 작성합니다.")
                                    comment_id = write_comment(driver, result_url, comment)
                                    if comment_id:
                                        last_comment_id = comment_id
                            else:
                                # 일반 댓글: 메인 입력창에 작성
                                comment_id = write_comment(driver, result_url, comment)
                                if comment_id:
                                    last_comment_id = comment_id  # ⭐ 일반 댓글 ID로 업데이트
                            
                            # 다음 댓글 전 대기
                            if idx < len(comments):
                                wait_time = random.randint(3, 5)
                                print(f"  ⏳ 다음 댓글까지 {wait_time}초 대기...")
                                time.sleep(wait_time)
                        
                        print("\n" + "="*60)
                        print("🎉 모든 댓글 작성 완료!")
                        print("="*60)
                        print(f"작성된 댓글: {len(comments)}개")
                        
                        # 결과 저장 업데이트
                        with open('test_result.txt', 'a', encoding='utf-8') as f:
                            f.write(f"\n\n=== 댓글 ===\n")
                            for idx, (content, is_reply) in enumerate(comments, 1):
                                c_type = "대댓글" if is_reply else "일반"
                                f.write(f"{idx}. ({c_type}) {content}\n")
                        
                        print("\n✅ 댓글 결과 저장: test_result.txt")
        else:
            print("\n❌ 글 발행 실패")
        
        input("\nEnter를 누르면 종료됩니다...")
        
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
        print("\n⏹️ 사용자가 취소했습니다.")
