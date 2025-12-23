from bs4 import BeautifulSoup
import re
from typing import Dict, List, Any

def parse_lotte_tracking(html_content: str) -> Dict[str, Any]:
    """
    롯데택배 HTML 응답을 파싱하여 배송 정보를 추출합니다.
    
    Args:
        html_content: 롯데택배 조회 HTML 응답
        
    Returns:
        파싱된 배송 정보 딕셔너리
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "tracking_number": "",
        "sender_name": "-",
        "receiver_name": "-",
        "details": []
    }
    
    try:
        # 1. 기본 정보 테이블 파싱 (table.tblH.mt60)
        basic_table = soup.select_one('table.tblH.mt60')
        if basic_table:
            tbody = basic_table.select_one('tbody')
            if tbody:
                tds = tbody.select('td')
                if len(tds) >= 4:
                    result["tracking_number"] = tds[0].get_text(strip=True)
                    # 발송지: tds[1], 도착지: tds[2] (필요시 사용)
        
        # 2. 배송 상세 정보 테이블 파싱
        all_tables = soup.select('table.tblH')
        
        if len(all_tables) >= 2:
            detail_table = all_tables[1]  # 두 번째 테이블
            tbody = detail_table.select_one('tbody')
            
            if tbody:
                rows = tbody.select('tr')
                
                for row in rows:
                    tds = row.select('td')
                    
                    if len(tds) >= 4:
                        # 시간 텍스트 추출 (예: "2025-12-05&nbsp;11:36")
                        time_text = tds[1].get_text(strip=True)
                        time_text = time_text.replace('\xa0', ' ')  # &nbsp; 제거
                        time_text = time_text.replace('&nbsp;', ' ')
                        
                        # 날짜와 시간 분리
                        date_part = ""
                        time_part = ""
                        
                        if ' ' in time_text and '--:--' not in time_text:
                            parts = time_text.split(' ', 1)
                            date_part = parts[0]
                            time_part = parts[1] if len(parts) > 1 else ""
                        elif '--:--' in time_text:
                            # "2025-12-04 --:--" 형태 처리
                            date_part = time_text.split(' ')[0] if ' ' in time_text else time_text
                            time_part = ""
                        else:
                            date_part = time_text
                            time_part = ""
                        
                        # 처리현황에서 <br> 태그를 공백으로 변환
                        description_td = tds[3]
                        # <br> 태그를 공백으로 변환
                        for br in description_td.find_all('br'):
                            br.replace_with(' ')
                        description = description_td.get_text(strip=True)
                        
                        detail = {
                            "date": date_part,
                            "time": time_part,
                            "location": tds[2].get_text(strip=True),
                            "status": tds[0].get_text(strip=True),
                            "description": description
                        }
                        
                        result["details"].append(detail)
        
        # 로그 출력 (디버깅용)
        print(f"✅ 롯데택배 파싱 완료: {len(result['details'])}개 이벤트")
        
    except Exception as e:
        print(f"❌ 롯데택배 파싱 오류: {e}")
        import traceback
        traceback.print_exc()
    
    return result