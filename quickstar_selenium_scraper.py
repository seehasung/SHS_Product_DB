"""
quickstar.co.kr Selenium 스크래퍼
헤드리스 브라우저로 실제 로그인 및 검색
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import time


class QuickstarSeleniumScraper:
    """퀵스타 Selenium 스크래퍼"""
    
    def __init__(self):
        self.driver = None
        self.base_url = "https://quickstar.co.kr"
        self.username = "aaa10130"
        self.password = "tjgktjd123"
        self.is_logged_in = False
    
    def init_driver(self):
        """Chrome 드라이버 초기화 (헤드리스)"""
        if self.driver:
            return
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 헤드리스 모드
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        print(f"✅ Chrome 드라이버 초기화")
    
    def login(self):
        """퀵스타 로그인 (Selenium)"""
        try:
            if self.is_logged_in:
                return True
            
            self.init_driver()
            
            print(f"🔐 퀵스타 로그인 시도 (Selenium)...")
            
            # 로그인 페이지 접속
            self.driver.get(self.base_url)
            time.sleep(2)
            
            # 아이디 입력
            id_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="ol_id"]'))
            )
            id_input.clear()
            id_input.send_keys(self.username)
            
            # 비밀번호 입력
            pw_input = self.driver.find_element(By.XPATH, '//*[@id="ol_pw"]')
            pw_input.clear()
            pw_input.send_keys(self.password)
            
            # 로그인 버튼 클릭
            login_btn = self.driver.find_element(By.XPATH, '//*[@id="ol_before"]/form/div/div[3]/button')
            login_btn.click()
            
            time.sleep(3)
            
            # 로그인 확인
            try:
                welcome_element = self.driver.find_element(By.XPATH, '//*[@id="main_wrapper2"]/div[1]/div[3]/div[1]/div[1]')
                if '서하성' in welcome_element.text:
                    self.is_logged_in = True
                    print(f"✅ 퀵스타 로그인 성공 (환영: {welcome_element.text.strip()})")
                    return True
            except:
                pass
            
            print(f"❌ 퀵스타 로그인 실패 (환영 메시지 없음)")
            return False
            
        except Exception as e:
            print(f"❌ 로그인 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_tracking_number(self, taobao_order_number: str):
        """타오바오 주문번호로 송장번호 조회 (Selenium)"""
        try:
            if not self.is_logged_in:
                if not self.login():
                    return None
            
            # 타오바오 주문번호 19자 추출
            digits = ''.join(filter(str.isdigit, taobao_order_number))
            if len(digits) < 19:
                print(f"⚠️ 타오바오 번호 부족: {len(digits)}자")
                return None
            
            taobao_number = digits[:19]
            
            print(f"🔍 Selenium으로 조회: {taobao_number}")
            
            # 날짜 설정
            current_year = datetime.now().year
            previous_year = current_year - 1
            
            # 검색 URL
            search_url = (
                f"{self.base_url}/mypage/service_list.php"
                f"?mb_id={self.username}"
                f"&dtype=add"
                f"&sdate={previous_year}-01-01"
                f"&edate={current_year}-12-31"
                f"&find=it_local_order"
                f"&value={taobao_number}"
                f"&or_de_no=&state=&type=ship&pageblock=20"
            )
            
            print(f"📤 URL 접속...")
            self.driver.get(search_url)
            time.sleep(3)  # 페이지 로드 대기
            
            # 송장번호 찾기 (invoice 링크)
            try:
                # invoice 링크 찾기
                invoice_links = self.driver.find_elements(By.XPATH, '//a[contains(@href, "invoice=")]')
                
                if invoice_links:
                    # 첫 번째 링크에서 송장번호 추출
                    href = invoice_links[0].get_attribute('href')
                    
                    import re
                    match = re.search(r'invoice=(\d{12,13})', href)
                    if match:
                        tracking = match.group(1)
                        print(f"✅ 송장번호 발견: {tracking}")
                        return tracking
                
            except Exception as e:
                print(f"  ❌ 송장번호 추출 오류: {e}")
            
            print(f"⚠️ 송장번호 없음 (검색 결과 없음)")
            return None
            
        except Exception as e:
            print(f"❌ 조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def close(self):
        """브라우저 종료"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.is_logged_in = False
            print(f"🔐 브라우저 종료")
    
    def __del__(self):
        """객체 소멸 시 브라우저 자동 종료"""
        self.close()


# 테스트
if __name__ == "__main__":
    scraper = QuickstarSeleniumScraper()
    
    try:
        tracking = scraper.get_tracking_number("4963787281722525634")
        if tracking:
            print(f"✅ 성공: {tracking}")
        else:
            print(f"❌ 실패")
    finally:
        scraper.close()

