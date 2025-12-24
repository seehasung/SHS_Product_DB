"""
7customs.com 웹 스크래핑 구현
기존 관세청 API를 대체하여 7customs.com에서 통관 정보를 스크래핑
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from datetime import datetime


def scrape_7customs(tracking_number: str, order_date: str) -> Dict:
    """
    7customs.com에서 통관 정보 스크래핑
    
    Args:
        tracking_number: 송장번호 (예: 509486204604)
        order_date: 주문일자 (형식: 2025-12-19)
    
    Returns:
        통관 정보 딕셔너리
    """
    try:
        # 1. URL 생성
        year = order_date.split('-')[0]  # "2025-12-19" -> "2025"
        url = f"https://www.7customs.com/customs/{year}/hbl/{tracking_number}"
        
        print(f"🔍 7customs.com 조회 시작")
        print(f"   URL: {url}")
        print(f"   송장번호: {tracking_number}")
        print(f"   주문일자: {order_date}")
        
        # 2. 페이지 요청
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"7customs.com 접속 실패 (HTTP {response.status_code})"
            }
        
        # 3. HTML 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 4. 데이터 추출
        result = {
            "success": True,
            "tracking_number": tracking_number,
            "url": url,
        }
        
        # 4.1 통관 상태 추출
        customs_status_elem = soup.select_one('h3.center.mgt0.prgs-ready strong')
        if customs_status_elem:
            result["customs_status"] = customs_status_elem.text.strip()
            print(f"✅ 통관 상태: {result['customs_status']}")
        
        # 4.2 통관완료 예상일 추출
        expected_date_rows = soup.select('table.table-hover tr')
        for row in expected_date_rows:
            td_header = row.select_one('td.td-header')
            if td_header and '통관완료' in td_header.text and '예상일' in td_header.text:
                date_span = row.select_one('span.red.f18, span.text-color-white.f18')
                if date_span:
                    result["expected_clearance_date"] = date_span.text.strip()
                    print(f"✅ 통관완료 예상일: {result['expected_clearance_date']}")
                break
        
        # 4.3 입항일 추출
        for row in expected_date_rows:
            td_header = row.select_one('td.td-header')
            if td_header and '입항일' in td_header.text:
                arrival_td = row.select('td')[1] if len(row.select('td')) > 1 else None
                if arrival_td:
                    result["arrival_date"] = arrival_td.text.strip()
                    print(f"✅ 입항일: {result['arrival_date']}")
                break
        
        # 4.4 통관정보에서 물품정보 추출
        customs_info_tables = soup.find_all('table', class_='table-hover')
        for table in customs_info_tables:
            rows = table.find_all('tr')
            for row in rows:
                td_header = row.find('td', class_='td-header')
                if td_header and '물품정보' in td_header.text:
                    product_td = row.find_all('td')[1] if len(row.find_all('td')) > 1 else None
                    if product_td:
                        product_span = product_td.find('span')
                        if product_span:
                            result["product_info"] = product_span.text.strip()
                            print(f"✅ 물품정보: {result['product_info']}")
                    break
        
        # 4.5 통관정보 전체 추출 (추가 필드)
        result["customs_details"] = {}
        for table in customs_info_tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    td_header = cells[0]
                    if 'td-header' in td_header.get('class', []):
                        header_text = td_header.text.strip()
                        value_text = cells[1].text.strip()
                        
                        # 주요 정보만 저장
                        key_map = {
                            '통관진행상태': 'progress_status',
                            '진행상태': 'current_status',
                            '적출국': 'origin_country',
                            '적재항': 'loading_port',
                            '화물구분': 'cargo_type',
                            '컨테이너번호': 'container_number',
                            '세관명': 'customs_office',
                            '입항명': 'port_name',
                            '장치장': 'warehouse',
                            '입항일': 'arrival_date_detail',
                            '처리일시': 'processing_datetime'
                        }
                        
                        for korean, english in key_map.items():
                            if korean in header_text:
                                result["customs_details"][english] = value_text
        
        # 4.6 통관상세내역 추출
        detail_table = None
        for p_tag in soup.find_all('p'):
            if '통관상세내역' in p_tag.text:
                parent = p_tag.find_parent('div', class_='col-lg-12')
                if parent:
                    next_div = parent.find_next_sibling('div')
                    if next_div:
                        detail_table = next_div.find('table', class_='list-table')
                break
        
        # Alternative: search directly for list-table
        if not detail_table:
            detail_table = soup.find('table', class_='list-table')
        
        if detail_table:
            result["customs_history"] = []
            rows = detail_table.find_all('tr')[1:]  # 첫 번째 행(헤더) 제외
            
            for row in rows:
                # mobile-only 행은 스킵
                if 'mobile-only' in row.get('class', []):
                    continue
                
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # 장치장명, 처리구분, 내용, 처리일시
                    warehouse = cells[0].text.strip() if len(cells) > 0 else ""
                    process_type = cells[1].text.strip() if len(cells) > 1 else ""
                    
                    # pc-td 클래스를 가진 셀 찾기 (내용)
                    content = ""
                    processing_datetime = ""
                    
                    for i, cell in enumerate(cells):
                        if 'pc-td' in cell.get('class', []):
                            content = cell.text.strip()
                        elif i == len(cells) - 1:  # 마지막 셀이 처리일시
                            processing_datetime = cell.text.strip()
                    
                    if warehouse or process_type:
                        history_entry = {
                            "warehouse": warehouse,
                            "process_type": process_type,
                            "content": content,
                            "processing_datetime": processing_datetime
                        }
                        result["customs_history"].append(history_entry)
                        print(f"   📋 {process_type} - {processing_datetime}")
        
        # 결과 확인
        if result.get("customs_status") or result.get("customs_history"):
            print("✅ 7customs.com 조회 성공")
            return result
        else:
            return {
                "success": False,
                "message": "통관 정보를 찾을 수 없습니다. 송장번호와 주문일자를 확인해주세요."
            }
        
    except requests.Timeout:
        print("❌ 7customs.com 연결 타임아웃")
        return {
            "success": False,
            "message": "7customs.com 연결 시간 초과. 잠시 후 다시 시도해주세요."
        }
    
    except Exception as e:
        print(f"❌ 7customs.com 스크래핑 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"통관 조회 중 오류 발생: {str(e)}"
        }


def format_7customs_for_modal(data: Dict) -> Dict:
    """
    7customs.com 데이터를 모달에 표시할 형식으로 변환
    
    Args:
        data: scrape_7customs 함수의 반환값
    
    Returns:
        모달에 표시할 형식으로 변환된 데이터
    """
    if not data.get("success"):
        return data
    
    formatted = {
        "success": True,
        "source": "7customs.com",
        "tracking_number": data.get("tracking_number"),
        "url": data.get("url"),
        
        # 기본 정보
        "basic_info": {
            "customs_status": data.get("customs_status", "정보 없음"),
            "arrival_date": data.get("arrival_date", "정보 없음"),
            "expected_clearance_date": data.get("expected_clearance_date", "정보 없음"),
            "product_info": data.get("product_info", "정보 없음"),
        },
        
        # 상세 정보
        "details": data.get("customs_details", {}),
        
        # 진행 이력
        "history": data.get("customs_history", [])
    }
    
    return formatted


# 테스트 코드
if __name__ == "__main__":
    # 예제 테스트
    test_tracking = "509486204604"
    test_order_date = "2025-12-19"
    
    print("=== 7customs.com 스크래핑 테스트 ===\n")
    result = scrape_7customs(test_tracking, test_order_date)
    
    print("\n=== 결과 ===")
    if result["success"]:
        print(f"✅ 성공")
        print(f"   통관 상태: {result.get('customs_status')}")
        print(f"   예상일: {result.get('expected_clearance_date')}")
        print(f"   입항일: {result.get('arrival_date')}")
        print(f"   물품정보: {result.get('product_info')}")
        if result.get('customs_history'):
            print(f"   이력 개수: {len(result['customs_history'])}개")
    else:
        print(f"❌ 실패: {result.get('message')}")
    
    print("\n=== 포맷팅된 데이터 ===")
    formatted = format_7customs_for_modal(result)
    import json
    print(json.dumps(formatted, ensure_ascii=False, indent=2))