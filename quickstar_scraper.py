"""
quickstar.co.kr 배송대행지 스크래퍼
타오바오 주문번호로 송장번호 조회
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re


class QuickstarScraper:
    """퀵스타 배송대행지 스크래퍼"""
    
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://quickstar.co.kr"
        self.username = "aaa10130"
        self.password = "tjgktjd123"
        self.is_logged_in = False
    
    def login(self):
        """퀵스타 로그인"""
        try:
            print(f"🔐 퀵스타 로그인 시도...")
            
            login_url = f"{self.base_url}/member/login.php"
            
            data = {
                'mb_id': self.username,
                'mb_password': self.password,
                'url': '/'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.base_url
            }
            
            response = self.session.post(login_url, data=data, headers=headers)
            
            if response.status_code == 200:
                # 로그인 성공 확인 (쿠키 확인)
                if 'mb_id' in self.session.cookies.get_dict():
                    self.is_logged_in = True
                    print(f"✅ 퀵스타 로그인 성공")
                    return True
            
            print(f"❌ 퀵스타 로그인 실패")
            return False
            
        except Exception as e:
            print(f"❌ 로그인 오류: {e}")
            return False
    
    def get_tracking_number(self, taobao_order_number: str):
        """타오바오 주문번호로 송장번호 조회"""
        try:
            if not self.is_logged_in:
                if not self.login():
                    return None
            
            # 타오바오 주문번호에서 숫자만 19자 추출
            digits = ''.join(filter(str.isdigit, taobao_order_number))
            if len(digits) < 19:
                print(f"⚠️ 타오바오 주문번호가 너무 짧음: {len(digits)}자")
                return None
            
            taobao_number = digits[:19]  # 앞 19자만 사용
            
            print(f"🔍 타오바오 번호로 조회: {taobao_number}")
            
            # 날짜 설정 (전년도 1월 1일 ~ 올해 12월 31일)
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
                f"&type=ship"
                f"&pageblock=20#page1"
            )
            
            print(f"📤 URL: {search_url[:100]}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = self.session.get(search_url, headers=headers)
            
            if response.status_code != 200:
                print(f"❌ HTTP 오류: {response.status_code}")
                return None
            
            # HTML 파싱
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 송장번호 추출 (실제 HTML 구조 기반)
            # <a href="...&invoice=송장번호" id="송장번호">송장번호</a>
            
            # 방법 1: href에 invoice= 패턴 찾기 (가장 확실)
            links = soup.find_all('a', href=re.compile(r'invoice=\d{12,13}'))
            
            if links:
                # 첫 번째 링크에서 송장번호 추출
                href = links[0].get('href', '')
                match = re.search(r'invoice=(\d{12,13})', href)
                if match:
                    tracking = match.group(1)
                    print(f"✅ 송장번호 발견 (첫 번째): {tracking}")
                    return tracking
            
            # 방법 2: 택배사 이름 근처 숫자 찾기 (백업)
            courier_pattern = r'(CJ대한통운|CJ택배|로젠택배|롯데택배|한진택배).*?(\d{12,13})'
            text = soup.get_text()
            match = re.search(courier_pattern, text)
            if match:
                tracking = match.group(2)
                if tracking != taobao_number:
                    print(f"✅ 송장번호 발견 (택배사 근처): {tracking}")
                    return tracking
            
            print(f"⚠️ 송장번호를 찾을 수 없음 (타오바오 번호: {taobao_number})")
            return None
            
        except Exception as e:
            print(f"❌ 조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return None


# 테스트 코드
if __name__ == "__main__":
    scraper = QuickstarScraper()
    
    # 테스트
    test_taobao = "4666740374680525634 메모내용"
    tracking = scraper.get_tracking_number(test_taobao)
    
    if tracking:
        print(f"✅ 송장번호: {tracking}")
    else:
        print(f"❌ 실패")

