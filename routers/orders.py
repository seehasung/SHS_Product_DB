# routers/orders.py

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, desc
from datetime import datetime, date
import pandas as pd
import os
from typing import Optional
import requests
from utils.courier_parsers import parse_lotte_tracking
import xml.etree.ElementTree as ET
from typing import Optional
from customs_7customs_scraper import scrape_7customs, format_7customs_for_modal


from bs4 import BeautifulSoup
from database import get_db, Order, User

router = APIRouter(prefix="/orders", tags=["orders"])
templates = Jinja2Templates(directory="templates")

# 관세청 API 설정
CUSTOMS_API_KEY = "m230t285b102t292j090l050g2"
CUSTOMS_API_BASE_URL = "https://unipass.customs.go.kr:38010/ext/rest"

# ============================================
# 통관 조회 관련 (API + 함수)
# ============================================

# 관세청 API 설정
CUSTOMS_API_KEY = "m230t285b102t292j090l050g2"
CUSTOMS_API_BASE_URL = "https://unipass.customs.go.kr:38010/ext/rest"

# ===== 헬퍼 함수 =====
def get_xml_text(element, tag_name):
    """XML 요소에서 텍스트 추출"""
    tag = element.find(tag_name)
    return tag.text if tag is not None and tag.text else ""


# ===== 일반화물 통관 조회 (M B/L 또는 H B/L) =====
def get_customs_progress(master_bl: Optional[str] = None, house_bl: Optional[str] = None):
    """
    관세청 API - 일반화물 통관 진행정보 조회
    M B/L 또는 H B/L 중 하나만 있어도 조회 가능
    """
    try:
        # M B/L 또는 H B/L 중 하나는 필수
        if not master_bl and not house_bl:
            return {
                "success": False,
                "message": "Master B/L 또는 House B/L 번호가 필요합니다."
            }
        
        print(f"🔍 일반화물 통관 조회 시작: M-BL={master_bl or 'None'}, H-BL={house_bl or 'None'}")
        
        url = f"{CUSTOMS_API_BASE_URL}/cargCsclPrgsInfoQry/retrieveCargCsclPrgsInfo"
        
        # ⭐ 연도 파라미터 추가 (현재 년도)
        from datetime import datetime
        current_year = datetime.now().year
        
        params = {
            "crtfKey": CUSTOMS_API_KEY,
            "blYy": str(current_year),  # ⭐ 연도 필수!
        }
        
        # ⭐ H B/L만 있는 경우: blNo와 hblNo 모두 사용
        if not master_bl and house_bl:
            params["blNo"] = house_bl  # ⭐ M B/L 자리에 H-BL 입력
            params["hblNo"] = house_bl  # ⭐ H B/L 자리에도 입력 (둘 다 시도)
        
        # M B/L이 있는 경우
        elif master_bl:
            params["blNo"] = master_bl
            # H B/L도 있으면 함께 전송
            if house_bl and house_bl != master_bl:
                params["hblNo"] = house_bl
        
        else:
            return {
                "success": False,
                "message": "Master B/L 또는 House B/L 번호가 필요합니다."
            }
        
        print(f"  📤 최종 API 요청: {params}")  # ⭐ 확인용 로그
        
        response = requests.get(url, params=params, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"관세청 API 호출 실패 (HTTP {response.status_code})"
            }
        
        root = ET.fromstring(response.text)
        tCnt = root.find('.//tCnt')
        
        if tCnt is not None and tCnt.text == '0':
            return {
                "success": False,
                "message": "해당 B/L 번호로 조회된 통관 정보가 없습니다."
            }
        
        customs_info = []
        for item in root.findall('.//cargCsclPrgsInfo'):
            info = {
                "bl_no": get_xml_text(item, 'blNo'),
                "house_bl_no": get_xml_text(item, 'hblNo'),
                "csclPrgsStts": get_xml_text(item, 'csclPrgsStts'),
                "prnm": get_xml_text(item, 'prnm'),
                "shipNat": get_xml_text(item, 'shipNat'),
                "dstnNat": get_xml_text(item, 'dstnNat'),
                "rlbrDt": get_xml_text(item, 'rlbrDt'),
            }
            customs_info.append(info)
        
        events = []
        for event in root.findall('.//event'):
            event_info = {
                "eventDate": get_xml_text(event, 'evntDt'),
                "eventTime": get_xml_text(event, 'evntTm'),
                "eventName": get_xml_text(event, 'evntNm'),
                "location": get_xml_text(event, 'evntPlc'),
            }
            events.append(event_info)
        
        # ⭐ 데이터가 없으면 실패로 처리
        if len(customs_info) == 0:
            print(f"  ⚠️ 일반화물 조회 결과 0건 (실패 처리)")
            return {
                "success": False,
                "message": "해당 B/L 번호로 조회된 통관 정보가 없습니다."
            }
        
        print(f"  ✅ 일반화물 조회 성공: {len(customs_info)}건")
        
        return {
            "success": True,
            "query_type": "general",
            "master_bl": master_bl,
            "house_bl": house_bl,
            "customs_info": customs_info,
            "events": events,
            "total_count": len(customs_info),
            "data_source": "customs_api"
        }
        
    except Exception as e:
        print(f"❌ 일반화물 통관 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"통관 조회 중 오류 발생: {str(e)}"
        }


# ===== 특송화물 통관 조회 (관세청 API) =====
def get_express_customs_by_hbl(hbl_no: str):
    """관세청 API - 특송화물 통관내역 조회 (H B/L 번호만 필요)"""
    try:
        print(f"🔍 특송화물 통관 조회 시작 (관세청 API): H-BL={hbl_no}")
        
        url = f"{CUSTOMS_API_BASE_URL}/spsCrwsTrnmDtlsQry/retrieveSpsCrwsTrnmDtls"
        params = {
            "crtfKey": CUSTOMS_API_KEY,
            "hblNo": hbl_no,
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"관세청 API 호출 실패 (HTTP {response.status_code})"
            }
        
        root = ET.fromstring(response.text)
        
        # 조회 결과 개수 확인
        tCnt = root.find('.//tCnt')
        if tCnt is not None and tCnt.text == '0':
            return {
                "success": False,
                "message": "해당 송장번호로 조회된 통관 정보가 없습니다."
            }
        
        # 특송화물 통관 정보 추출
        customs_list = []
        for item in root.findall('.//spsCrwsTrnmDtls'):
            customs_info = {
                "hblNo": get_xml_text(item, 'hblNo'),              # 송장번호
                "prgsStts": get_xml_text(item, 'prgsStts'),        # 진행상태
                "prgsSttsNm": get_xml_text(item, 'prgsSttsNm'),    # 진행상태명
                "prcsDttm": get_xml_text(item, 'prcsDttm'),        # 처리일시
                "rlbrDttm": get_xml_text(item, 'rlbrDttm'),        # 반출일시
                "shipNatNm": get_xml_text(item, 'shipNatNm'),      # 선적국가명
                "shipNat": get_xml_text(item, 'shipNat'),          # 선적국가코드
                "csclPrgsSttsCd": get_xml_text(item, 'csclPrgsSttsCd'),  # 통관진행상태코드
                "csclPrgsSttsNm": get_xml_text(item, 'csclPrgsSttsNm'),  # 통관진행상태명
            }
            customs_list.append(customs_info)
        
        # 이벤트 정보 추출 (있는 경우)
        events = []
        for event in root.findall('.//event'):
            event_info = {
                "eventDate": get_xml_text(event, 'evntDt'),
                "eventTime": get_xml_text(event, 'evntTm'),
                "eventName": get_xml_text(event, 'evntNm'),
                "location": get_xml_text(event, 'evntPlc'),
            }
            events.append(event_info)
        
        # ⭐ 데이터가 없으면 실패로 처리
        if len(customs_list) == 0:
            print(f"  ⚠️ 특송화물 조회 결과 0건 (실패 처리)")
            return {
                "success": False,
                "message": "해당 송장번호로 조회된 통관 정보가 없습니다."
            }
        
        print(f"  ✅ 특송화물 조회 성공: {len(customs_list)}건")
        
        return {
            "success": True,
            "query_type": "express",
            "hbl_no": hbl_no,
            "customs_info": customs_list,
            "events": events,
            "total_count": len(customs_list),
            "data_source": "customs_api"  # 데이터 출처 표시
        }
        
    except Exception as e:
        print(f"❌ 특송화물 통관 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"통관 조회 중 오류 발생: {str(e)}"
        }


# ===== 특송화물 통관 조회 (7customs.com 백업) =====
def get_express_customs_info(tracking_number: str, order_date: str = None):
    """7customs.com - 특송화물 통관 조회 (백업용)"""
    # order_date가 없으면 올해로 설정
    if not order_date:
        from datetime import datetime
        order_date = datetime.now().strftime("%Y-%m-%d")
    
    # 7customs.com에서 조회
    result = scrape_7customs(tracking_number, order_date)
    
    if not result.get("success"):
        return result
    
    # 기존 API 응답 형식에 맞게 변환
    formatted = format_7customs_for_modal(result)
    formatted["query_type"] = "express"
    formatted["data_source"] = "7customs"  # 데이터 출처 표시
    
    return formatted


# ===== 통합 통관 조회 (자동 판단 - H B/L 우선) =====
def get_customs_info_auto(tracking_number: str = None, master_bl: str = None, house_bl: str = None, order_date: str = None):
    """
    통관 조회 자동 판단 (다단계 시도)
    1. Master B/L 있음 → 일반화물 API (M-BL + H-BL)
    2. House B/L만 있음 → 일반화물 API (H-BL만) ⭐ 가장 일반적
    3. 송장번호만 있음 → 특송화물 → 일반화물 → 7customs.com
    """
    
    # 1순위: Master B/L이 있으면 일반화물 조회 (M-BL + H-BL)
    if master_bl:
        print(f"📦 일반화물 조회 시도 (M-BL 있음): M-BL={master_bl}, H-BL={house_bl}")
        return get_customs_progress(master_bl, house_bl)
    
    # 2순위: House B/L만 있으면 일반화물 조회 (H-BL만) ⭐ 핵심!
    elif house_bl:
        print(f"📦 일반화물 조회 시도 (H-BL만): H-BL={house_bl}")
        result = get_customs_progress(None, house_bl)
        
        if result.get("success"):
            print(f"  └─ ✅ H-BL 조회 성공!")
            return result
        
        print(f"  └─ ⚠️ H-BL 조회 실패, 7customs.com 시도...")
        
        # H-BL로 실패하면 7customs.com 백업
        if order_date:
            backup_result = get_express_customs_info(house_bl, order_date)
            if backup_result.get("success"):
                print(f"  └─ ✅ 7customs.com 백업 성공!")
                return backup_result
        
        return result  # 실패 메시지 반환
    
    # 3순위: tracking_number만 있으면 다단계 시도
    elif tracking_number:
        print(f"🔍 송장번호로 통관 조회 시작: {tracking_number}")
        
        # 3-1. 특송화물 API 시도
        print(f"  ├─ [1단계] 특송화물 API 시도...")
        express_result = get_express_customs_by_hbl(tracking_number)
        
        if express_result.get("success"):
            print(f"  └─ ✅ 특송화물 API 성공!")
            return express_result
        
        print(f"  ├─ ⚠️ 특송화물 API 실패: {express_result.get('message', '알 수 없음')}")
        
        # 3-2. 일반화물 API 시도
        print(f"  ├─ [2단계] 일반화물 API 시도 (H-BL로)...")
        general_result = get_customs_progress(None, tracking_number)
        
        if general_result.get("success"):
            print(f"  └─ ✅ 일반화물 API 성공!")
            return general_result
        
        print(f"  ├─ ⚠️ 일반화물 API 실패: {general_result.get('message', '알 수 없음')}")
        
        # 3-3. 7customs.com 백업
        print(f"  ├─ [3단계] 7customs.com 백업 시도...")
        backup_result = get_express_customs_info(tracking_number, order_date)
        
        if backup_result.get("success"):
            print(f"  └─ ✅ 7customs.com 백업 성공!")
            return backup_result
        
        # 모든 방법 실패
        print(f"  └─ ❌ 모든 조회 방법 실패")
        return {
            "success": False,
            "message": "통관 정보를 조회할 수 없습니다. 송장번호를 확인해주세요."
        }
    
    else:
        return {"success": False, "message": "송장번호 또는 B/L 번호를 입력하세요"}

# ===== API 엔드포인트 =====

@router.get("/customs", response_class=HTMLResponse)
def customs_search_page(request: Request):
    """통관 조회 페이지"""
    return templates.TemplateResponse("customs_search.html", {"request": request})


@router.get("/api/customs/{order_id}")
def get_customs_info_by_order(order_id: int, db: Session = Depends(get_db)):
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        
        if not order:
            return {"success": False, "message": "주문을 찾을 수 없습니다"}
        
        # ✅ 디버그: 주문 데이터 로깅
        print(f"📋 주문 데이터 확인 (Order ID: {order_id}):")
        print(f"  - tracking_number: {order.tracking_number}")
        print(f"  - master_bl: {order.master_bl}")
        print(f"  - house_bl: {order.house_bl}")
        print(f"  - customs_number: {order.customs_number}")
        print(f"  - courier_company: {order.courier_company}")
        
        # ✅ 송장번호 정리 (.0 제거)
        tracking_number = clean_tracking_number(order.tracking_number)
        
        # ✅ order_date 가져오기
        order_date = str(order.order_date) if order.order_date else None
        
        # ⭐ 송장번호가 없으면 에러
        if not tracking_number and not order.master_bl and not order.house_bl:
            return {"success": False, "message": "송장번호 또는 B/L 번호가 등록되지 않았습니다"}
        
        # ⭐ tracking_number를 house_bl로 전달 (DB에 house_bl이 없으면)
        house_bl_to_use = order.house_bl if order.house_bl else tracking_number
        
        print(f"  🔍 조회에 사용할 H-BL: {house_bl_to_use}")
        
        # ✅ 통관 조회 (tracking_number를 house_bl로 사용)
        result = get_customs_info_auto(
            tracking_number=None,  # ⭐ tracking_number는 사용 안함
            master_bl=order.master_bl,
            house_bl=house_bl_to_use,  # ⭐ tracking_number를 house_bl로 사용
            order_date=order_date
        )
        
        if result.get("success"):
            result["order_info"] = {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name,
                "product_name": order.product_name,
                "courier_company": order.courier_company
            }
        
        return result
        
    except Exception as e:
        print(f"❌ 통관 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"통관 조회 중 오류: {str(e)}"}


@router.get("/api/customs/search/tracking")
def search_customs_by_tracking(tracking_number: str):
    """송장번호로 특송화물 통관 직접 조회"""
    if not tracking_number:
        return {"success": False, "message": "송장번호를 입력하세요"}
    
    return get_express_customs_info(tracking_number)


@router.get("/api/customs/search")
def search_customs_by_bl(master_bl: Optional[str] = None, house_bl: Optional[str] = None):
    """B/L 번호로 일반화물 통관 직접 조회 (M B/L 또는 H B/L 중 하나 필수)"""
    if not master_bl and not house_bl:
        return {"success": False, "message": "Master B/L 또는 House B/L 번호를 입력하세요"}
    
    return get_customs_progress(master_bl, house_bl)


#**********************************************************************************
#**********************************************************************************
#**********************************************************************************




# ============================================
# 권한 체크 함수
# ============================================
def check_order_permission(request: Request):
    """주문 관리 권한 체크"""
    username = request.session.get("user")
    is_admin = request.session.get("is_admin", False)
    can_manage_orders = request.session.get("can_manage_orders", False)
    
    if not username:
        return None
    
    # 관리자는 모든 권한
    if is_admin:
        return {"username": username, "is_admin": True, "can_manage_orders": True}
    
    if can_manage_orders:
        return {"username": username, "is_admin": False, "can_manage_orders": True}
    
    return None


# routers/orders.py - 추가할 코드

# ============================================
# 주문 상태 통합 함수
# ============================================
def normalize_order_status(status, db):
    """주문 상태를 DB 매핑 테이블 기반으로 분류"""
    if not status:
        return "미분류"
    
    status = str(status).strip()
    
    # DB에서 매핑 조회
    from database import OrderStatusMapping
    mapping = db.query(OrderStatusMapping).filter(
        OrderStatusMapping.original_status == status
    ).first()
    
    if mapping:
        return mapping.normalized_status
    else:
        return "미분류"


# ============================================
# 1. 전체 현황 (대시보드) - 개선 버전
# ============================================
@router.get("/dashboard", response_class=HTMLResponse)
def order_dashboard(
    request: Request,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    """주문 전체 현황 대시보드"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    from datetime import timedelta
    
    # ⭐ 기간 기본값 설정
    if not start_date or not end_date:
        today = date.today()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    # 기본 통계 (전체)
    total_orders = db.query(Order).count()
    today_str = date.today().strftime('%Y-%m-%d')
    today_orders = db.query(Order).filter(
        Order.order_date.like(f'{today_str}%')
    ).count()
    
    # ============================================
    # ⭐ 통계 카드 (그대로 유지)
    # ============================================
    
    # 1. 가송장 사용 건
    valid_couriers = [
        'CJ대한통운', 'CJ택배', '대한통운', '로젠택배', '롯데택배',
        '우체국택배', '천일택배', '편의점택배(GS25)', '한진택배'
    ]

    all_orders = db.query(Order).all()
    fake_tracking_count = 0

    for order in all_orders:
        courier = order.courier_company or ''
        is_valid_courier = any(valid in courier for valid in valid_couriers)
        tracking = order.tracking_number or ''
        
        # ⭐ 송장번호 .0 제거
        if tracking.endswith('.0'):
            tracking = tracking[:-2]
        
        # ⭐ 송장번호 앞 4자리가 2025~2030인지 확인
        is_fake_tracking = False
        if len(tracking) >= 4:
            prefix = tracking[:4]
            if prefix in ['2025', '2026', '2027', '2028', '2029', '2030']:
                is_fake_tracking = True
        
        # 유효하지 않은 택배사 + 가송장 형식 = 가송장
        if not is_valid_courier and is_fake_tracking:
            fake_tracking_count += 1
    
    # 2. 네이버 송장 흐름
    naver_delivery_count = 0
    
    # 3. 경동 이관
    kyungdong_count = db.query(Order).filter(
        Order.is_kyungdong_transferred == True
    ).count()
    
    # 4. 통관 절차 이상
    customs_issue_count = db.query(Order).filter(
        or_(
            Order.customs_number.like('%알수없음%'),
            Order.customs_number.like('%반출취소%'),
            Order.customs_number.like('%반출불가%'),
            Order.customs_number.like('%불가%'),
            Order.customs_number.like('%취소%'),
            Order.customs_number.like('%이상%'),
            Order.customs_number.like('%오류%'),
            Order.customs_number.like('%문제%'),
            Order.customs_number.like('%지연%')
        )
    ).count()
    
    # 5. 장기 미배송 (2주 = 14일)
    two_weeks_ago = (date.today() - timedelta(days=14)).strftime('%Y-%m-%d')
    
    long_undelivered_count = db.query(Order).filter(
        and_(
            Order.order_date < two_weeks_ago,
            or_(
                Order.order_status == '발송대기',
                Order.order_status == '발송대기(발주확인)',
                Order.order_status == '배송중',
                Order.order_status == '배송지시'
            )
        )
    ).count()
    
    # ============================================
    # ⭐ 상태별 통계 (선택한 기간, 통합된 상태)
    # ============================================
    
    # 선택한 기간의 주문만 조회
    month_orders = db.query(Order).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date + ' 23:59:59'
    ).all()
    
    # 상태별 집계 (통합된 상태)
    status_counts = {}
    for order in month_orders:
        normalized_status = normalize_order_status(order.order_status, db)  # ⭐ db 전달
        status_counts[normalized_status] = status_counts.get(normalized_status, 0) + 1

    # 정렬 (배송중 > 배송완료 > 취소 > 반품 > 교환 > 미분류 순)
    status_order = ["배송중", "배송완료", "취소", "반품", "교환", "미분류"]
    status_stats = [(status, status_counts.get(status, 0)) for status in status_order if status_counts.get(status, 0) > 0]
    
    # 기간 표시 텍스트
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    if start_dt.month == end_dt.month and start_dt.year == end_dt.year:
        period_text = start_dt.strftime('%Y년 %m월')
    else:
        period_text = f"{start_dt.strftime('%Y.%m.%d')} ~ {end_dt.strftime('%Y.%m.%d')}"
    
    return templates.TemplateResponse("order_dashboard.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"],
        "total_orders": total_orders,
        "today_orders": today_orders,
        "status_stats": status_stats,
        "fake_tracking_count": fake_tracking_count,
        "naver_delivery_count": naver_delivery_count,
        "kyungdong_count": kyungdong_count,
        "customs_issue_count": customs_issue_count,
        "long_undelivered_count": long_undelivered_count,
        "current_month": period_text,
        "start_date": start_date,
        "end_date": end_date
    })


# ============================================
# 2. 특정 조건별 주문 목록 API
# ============================================
@router.get("/api/orders/by-condition")
def get_orders_by_condition(
    request: Request,
    condition: str,
    db: Session = Depends(get_db)
):
    """조건별 주문 목록 조회"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    from datetime import timedelta
    
    orders = []
    
    if condition == "fake_tracking":
        # 가송장 사용 건
        valid_couriers = [
            'CJ대한통운', 'CJ택배', '대한통운', '로젠택배', '롯데택배',
            '우체국택배', '천일택배', '편의점택배(GS25)', '한진택배'
        ]
        
        all_orders = db.query(Order).all()
        for order in all_orders:
            courier = order.courier_company or ''
            is_valid_courier = any(valid in courier for valid in valid_couriers)
            tracking = order.tracking_number or ''
            
            # ⭐ 송장번호 .0 제거
            if tracking.endswith('.0'):
                tracking = tracking[:-2]
            
            # ⭐ 송장번호 앞 4자리가 2025~2030인지 확인
            is_fake_tracking = False
            if len(tracking) >= 4:
                prefix = tracking[:4]
                if prefix in ['2025', '2026', '2027', '2028', '2029', '2030']:
                    is_fake_tracking = True
            
            # 유효하지 않은 택배사 + 가송장 형식 = 가송장
            if not is_valid_courier and is_fake_tracking:
                orders.append(order)
        
    elif condition == "kyungdong":
        # 경동 이관
        orders = db.query(Order).filter(
            Order.is_kyungdong_transferred == True
        ).all()
    
    elif condition == "customs_issue":
        # 통관 절차 이상
        orders = db.query(Order).filter(
            or_(
                Order.customs_number.like('%알수없음%'),
                Order.customs_number.like('%반출취소%'),
                Order.customs_number.like('%반출불가%'),
                Order.customs_number.like('%불가%'),
                Order.customs_number.like('%취소%'),
                Order.customs_number.like('%이상%'),
                Order.customs_number.like('%오류%'),
                Order.customs_number.like('%문제%'),
                Order.customs_number.like('%지연%')
            )
        ).all()
    
    elif condition == "long_undelivered":
        # 장기 미배송
        two_weeks_ago = (date.today() - timedelta(days=14)).strftime('%Y-%m-%d')
        orders = db.query(Order).filter(
            and_(
                Order.order_date < two_weeks_ago,
                or_(
                    Order.order_status == '발송대기',
                    Order.order_status == '발송대기(발주확인)',
                    Order.order_status == '배송중',
                    Order.order_status == '배송지시'
                )
            )
        ).all()
    
    # JSON 응답
    return {
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "sales_channel": o.sales_channel,  # ⭐ 추가
                "order_status": o.order_status,
                "order_date": o.order_date[:10] if o.order_date else '-',
                "buyer_name": o.buyer_name,
                "recipient_name": o.recipient_name,
                "product_name": o.product_name,
                "payment_amount": o.payment_amount,
                "tracking_number": o.tracking_number[:-2] if o.tracking_number and o.tracking_number.endswith('.0') else o.tracking_number,  # ⭐ .0 제거
                "courier_company": o.courier_company
            }
            for o in orders[:100]  # 최대 100개
        ]
    }


# ============================================
# 3. 상태별 주문 목록 API (기간 필터 포함)
# ============================================
@router.get("/api/orders/by-status")
def get_orders_by_status(
    request: Request,
    status: str,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    """상태별 주문 목록 조회 (기간 필터)"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    # 기본값: 이번 달
    if not start_date:
        today = date.today()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')
    
    # 모든 주문 조회 (기간 필터)
    query = db.query(Order).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date + ' 23:59:59'
    )
    
    all_orders = query.all()
    
    # 상태로 필터링
    filtered_orders = [
        o for o in all_orders 
        if normalize_order_status(o.order_status, db) == status
    ]
    
    return {
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "sales_channel": o.sales_channel,
                "order_status": o.order_status,
                "normalized_status": normalize_order_status(o.order_status, db),  # ⭐ db 추가!
                "order_date": o.order_date[:10] if o.order_date else '-',
                "buyer_name": o.buyer_name,
                "recipient_name": o.recipient_name,
                "product_name": o.product_name,
                "payment_amount": o.payment_amount,
                "tracking_number": o.tracking_number[:-2] if o.tracking_number and o.tracking_number.endswith('.0') else o.tracking_number,
                "courier_company": o.courier_company
            }
            for o in filtered_orders[:100]
        ]
    }

# ============================================
# 2. 데이터 업로드 페이지
# ============================================
@router.get("/upload", response_class=HTMLResponse)
def order_upload_page(request: Request):
    """엑셀 업로드 페이지"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("order_upload.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"]
    })


# ============================================
# 3. 엑셀 업로드 처리
# ============================================
# routers/orders.py - 엑셀 업로드 부분만 (오류 처리 개선)

# routers/orders.py - 엑셀 업로드 함수 업데이트

@router.post("/api/upload")
async def upload_orders(
    request: Request,
    file: UploadFile = File(...),
    update_mode: str = Form("append"),
    db: Session = Depends(get_db)
):
    """엑셀 파일 업로드 및 DB 저장 (오류 행 건너뛰기)"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    try:
        # 엑셀 파일 읽기
        df = pd.read_excel(file.file)
        
        # 컬럼명 매핑 (한글 → 영문)
        column_mapping = {
            "주문상태": "order_status",
            "주문일자": "order_date",
            "클레임일자": "claim_date",
            "클레임사유": "claim_reason",
            "판매처／계정": "sales_channel",
            "주문번호": "order_number",
            "구매자": "buyer_name",
            "수령자": "recipient_name",
            "택배사": "courier_company",
            "송장번호": "tracking_number",
            "경동이관여부": "is_kyungdong_transferred",
            "제품명": "product_name",
            "옵션": "product_option",
            "수량": "quantity",
            "연락처": "contact_number",
            "통관번호": "customs_number",
            "우편번호": "postal_code",
            "주소": "address",
            "결제금액": "payment_amount",
            "배송비（고객）": "customer_shipping_fee",
            "마켓수수료": "market_commission",
            "정산예정금": "settlement_amount",
            "타바－주문번호": "taobao_order_number",
            "타바－위안": "taobao_yuan",
            "주문처리일": "order_processing_date",
            "환율": "exchange_rate",
            "관세대납": "customs_prepayment",
            "화물대납": "freight_prepayment",
            "배대지": "warehouse_fee",
            "마진": "profit_margin",
            "마진율": "profit_margin_rate",
            # ⭐ B/L 번호 매핑 추가
            "Master B/L": "master_bl",
            "마스터 B/L": "master_bl",
            "House B/L": "house_bl",
            "하우스 B/L": "house_bl",
            "H-BL": "house_bl",
            "M-BL": "master_bl"
        }
        
        # 컬럼명 변경
        df.rename(columns=column_mapping, inplace=True)
        
        # ⭐ 특수 파싱: 주문처리일 → 환율
        if "order_processing_date" in df.columns:
            def parse_exchange_rate(x):
                try:
                    if pd.notna(x) and "-" in str(x):
                        return str(x).split("-")[-1]
                    return None
                except:
                    return None
            
            df["exchange_rate"] = df["order_processing_date"].apply(parse_exchange_rate)
        
        # ⭐ 경동이관여부 처리 (TRUE/FALSE → Boolean)
        if "is_kyungdong_transferred" in df.columns:
            df["is_kyungdong_transferred"] = df["is_kyungdong_transferred"].apply(
                lambda x: True if str(x).upper() in ['TRUE', 'T', '1', 'YES', 'Y', '예', 'O'] else False
            )
        
        # 모든 값을 문자열로 변환 (NaN은 None으로)
        for col in df.columns:
            if col == "is_kyungdong_transferred":  # Boolean은 제외
                continue
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) and str(x) != 'nan' else None)
        
        # 업데이트 모드 처리
        if update_mode == "replace":
            db.query(Order).delete()
            db.commit()
        
        # DB에 저장 (각 행을 개별 처리)
        print("6. DB 저장 시작...")
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []
        processed_order_numbers = set()  # ⭐ 엑셀 파일 내 중복 추적

        for idx, row in df.iterrows():
            try:
                # 주문번호 확인
                order_number = row.get("order_number")
                if not order_number or order_number == "None":
                    error_count += 1
                    errors.append(f"행 {idx+2}: 주문번호 누락")
                    continue
                
                # ⭐ 1. 엑셀 파일 내 중복 체크
                if order_number in processed_order_numbers:
                    skip_count += 1
                    continue  # 조용히 건너뛰기
                
                # ⭐ 2. DB에 이미 있는지 체크
                existing = db.query(Order).filter(
                    Order.order_number == order_number
                ).first()
                
                if existing:
                    skip_count += 1
                    continue  # 조용히 건너뛰기
                
                # ⭐ 3. 중복 아니면 등록
                processed_order_numbers.add(order_number)
                
                order_data = {}
                for key, value in row.items():
                    if key in column_mapping.values() or key == "is_kyungdong_transferred":
                        order_data[key] = value
                
                new_order = Order(**order_data)
                db.add(new_order)
                success_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                print(f"❌ 행 {idx+2} 오류: {error_msg[:200]}")
                errors.append(f"행 {idx+2}: {error_msg[:100]}")
                continue

        # 최종 커밋
        db.commit()
        print("=" * 50)
        print(f"✅ 업로드 완료: 성공 {success_count}건, 중복 건너뛰기 {skip_count}건, 오류 {error_count}건")

        return JSONResponse({
            "success": True,
            "message": f"업로드 완료: 성공 {success_count}건, 중복 건너뛰기 {skip_count}건, 오류 {error_count}건",
            "success_count": success_count,
            "skip_count": skip_count,
            "error_count": error_count,
            "errors": errors[:20]
        })
        
    except Exception as e:
        db.rollback()
        return JSONResponse({
            "success": False,
            "message": f"업로드 실패: {str(e)}"
        }, status_code=500)


# ============================================
# 4. 주문조회 (통합 페이지)
# ============================================
@router.get("/search", response_class=HTMLResponse)
def order_search(
    request: Request,
    db: Session = Depends(get_db)
):
    """주문조회 통합 페이지 (고객/배송/통관 탭)"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("order_search.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"]
    })


# ============================================
# 5. 주문조회 API (고객 탭)
# ============================================
@router.get("/api/search/customers")
def search_customers(
    request: Request,
    search: str = "",
    db: Session = Depends(get_db)
):
    """고객별 주문 조회 API"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    # 검색 조건
    query = db.query(Order)
    if search:
        query = query.filter(
            or_(
                Order.buyer_name.like(f"%{search}%"),
                Order.recipient_name.like(f"%{search}%"),
                Order.contact_number.like(f"%{search}%")
            )
        )
    
    orders = query.all()
    
    # ⭐ Python에서 고객별로 그룹화 및 집계
    customer_dict = {}
    
    for order in orders:
        key = (order.buyer_name, order.recipient_name, order.contact_number)
        
        if key not in customer_dict:
            customer_dict[key] = {
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name,
                "tracking_number": clean_tracking_number(order.tracking_number),  # ✅ 정리
                "contact_number": order.contact_number,
                "order_count": 0,
                "total_amount": 0
            }
        
        customer_dict[key]["order_count"] += 1
        
        # 금액 합계
        try:
            if order.payment_amount:
                amount_str = str(order.payment_amount).replace(',', '')
                customer_dict[key]["total_amount"] += float(amount_str)
        except (ValueError, AttributeError):
            pass
    
    # 리스트로 변환
    result = [
        {
            "buyer_name": v["buyer_name"],
            "recipient_name": v["recipient_name"],
            "contact_number": v["contact_number"],
            "order_count": v["order_count"],
            "total_amount": round(v["total_amount"], 2)
        }
        for v in customer_dict.values()
    ]
    
    return {"customers": result}


# ============================================
# 6. 주문조회 API (배송 탭)
# ============================================
@router.get("/api/search/delivery")
def search_delivery(
    request: Request,
    search: str = "",
    db: Session = Depends(get_db)
):
    """배송 조회 API"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    # 송장번호가 있는 주문만
    query = db.query(Order).filter(
        Order.tracking_number.isnot(None),
        Order.tracking_number != ''
    )
    
    if search:
        query = query.filter(
            or_(
                Order.tracking_number.like(f"%{search}%"),
                Order.order_number.like(f"%{search}%"),
                Order.recipient_name.like(f"%{search}%")
            )
        )
    
    deliveries = query.order_by(desc(Order.created_at)).limit(100).all()
    
    return {
        "deliveries": [
            {
                "id": d.id,
                "order_number": d.order_number,
                "tracking_number": d.tracking_number,
                "courier_company": d.courier_company,
                "recipient_name": d.recipient_name,
                "order_date": d.order_date,
                "order_status": d.order_status
            }
            for d in deliveries
        ]
    }


# ============================================
# 7. 주문조회 API (통관 탭)
# ============================================
@router.get("/api/search/customs")
def search_customs(
    request: Request,
    search: str = "",
    db: Session = Depends(get_db)
):
    """통관 조회 API"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    # 통관번호가 있는 주문만
    query = db.query(Order).filter(
        Order.customs_number.isnot(None),
        Order.customs_number != ''
    )
    
    if search:
        query = query.filter(
            or_(
                Order.customs_number.like(f"%{search}%"),
                Order.order_number.like(f"%{search}%"),
                Order.recipient_name.like(f"%{search}%")
            )
        )
    
    customs = query.order_by(desc(Order.created_at)).limit(100).all()
    
    return {
        "customs": [
            {
                "id": c.id,
                "order_number": c.order_number,
                "customs_number": c.customs_number,
                "recipient_name": c.recipient_name,
                "order_date": c.order_date,
                "order_status": c.order_status,
                "customs_prepayment": c.customs_prepayment or "0"
            }
            for c in customs
        ]
    }
    
    

@router.get("/api/search/all")
def search_orders_all(
    search: str = Query(..., description="검색어"),
    db: Session = Depends(get_db)
):
    """
    통합 주문 검색 API
    검색 필드: 고객명(구매자), 수령자명, 연락처, 송장번호, 상품명
    """
    try:
        print(f"🔍 통합 검색 시작: {search}")
        
        # 검색어가 비어있으면 빈 결과 반환
        if not search or not search.strip():
            return {"orders": [], "search_term": ""}
        
        search_term = f"%{search.strip()}%"
        
        # 지정된 필드에서만 검색
        query = db.query(Order).filter(
            or_(
                Order.buyer_name.ilike(search_term),        # 고객명
                Order.recipient_name.ilike(search_term),    # 수령자명
                Order.contact_number.ilike(search_term),    # 연락처
                Order.tracking_number.ilike(search_term),   # 송장번호
                Order.product_name.ilike(search_term)       # 상품명
            )
        )
        
        # 주문일자 기준 내림차순 정렬
        orders = query.order_by(Order.order_date.desc()).all()
        
        # 결과를 딕셔너리로 변환
        results = []
        for order in orders:
            results.append({
                "id": order.id,
                "order_number": order.order_number,
                "sales_channel": order.sales_channel,
                "order_status": order.order_status,
                "courier_company": order.courier_company,
                "tracking_number": order.tracking_number,
                "order_date": order.order_date.strftime("%Y-%m-%d") if order.order_date else None,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name,
                "contact_number": order.contact_number,
                "product_name": order.product_name,
                "payment_amount": order.payment_amount
            })
        
        print(f"✅ 검색 완료: {len(results)}건")
        
        # 검색어도 함께 반환 (프론트엔드에서 하이라이트용)
        return {
            "orders": results,
            "search_term": search.strip()
        }
        
    except Exception as e:
        print(f"❌ 검색 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# 8. 네이버 송장 팔로우
# ============================================
@router.get("/naver-tracking", response_class=HTMLResponse)
def naver_tracking(request: Request):
    """네이버 송장 팔로우 페이지"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("order_naver_tracking.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"]
    })


# ============================================
# 9. 경동 송장 팔로우
# ============================================
@router.get("/kyungdong-tracking", response_class=HTMLResponse)
def kyungdong_tracking(request: Request):
    """경동 송장 팔로우 페이지"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("order_kyungdong_tracking.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"]
    })
    
# ============================================
# 10. 주문 상세 정보 API
# ============================================
@router.get("/api/{order_id}/detail")
def get_order_detail(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db)
):
    """주문 상세 정보 조회"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다")
    
    return {
        "id": order.id,
        "order_number": order.order_number,
        "order_status": order.order_status,
        "order_date": order.order_date,
        "claim_date": order.claim_date,
        "claim_reason": order.claim_reason,
        "sales_channel": order.sales_channel,
        "buyer_name": order.buyer_name,
        "recipient_name": order.recipient_name,
        "contact_number": order.contact_number,
        "postal_code": order.postal_code,
        "address": order.address,
        "product_name": order.product_name,
        "product_option": order.product_option,
        "quantity": order.quantity,
        "payment_amount": order.payment_amount,
        "customer_shipping_fee": order.customer_shipping_fee,
        "market_commission": order.market_commission,
        "settlement_amount": order.settlement_amount,
        "courier_company": order.courier_company,
        "tracking_number": order.tracking_number,
        "customs_number": order.customs_number,
        "taobao_order_number": order.taobao_order_number,
        "taobao_yuan": order.taobao_yuan,
        "order_processing_date": order.order_processing_date,
        "exchange_rate": order.exchange_rate,
        "customs_prepayment": order.customs_prepayment,
        "freight_prepayment": order.freight_prepayment,
        "warehouse_fee": order.warehouse_fee,
        "profit_margin": order.profit_margin,
        "profit_margin_rate": order.profit_margin_rate,
        "is_kyungdong_transferred": order.is_kyungdong_transferred
    }


# ============================================
# 11. 주문 삭제 API (관리자 전용)
# ============================================
@router.post("/api/{order_id}/delete")
def delete_order(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db)
):
    """주문 삭제 (관리자 전용)"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    # 관리자만 삭제 가능
    if not user_info["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다")
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다")
    
    try:
        db.delete(order)
        db.commit()
        return {"success": True, "message": "삭제되었습니다"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"삭제 실패: {str(e)}"}
    
# ============================================
# 미분류 상태 목록 조회 API
# ============================================
@router.get("/api/unmapped-statuses")
def get_unmapped_statuses(
    request: Request,
    db: Session = Depends(get_db)
):
    """미분류 상태 목록 조회"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    from database import OrderStatusMapping
    
    # 모든 주문에서 고유한 상태 추출
    all_statuses = db.query(Order.order_status).distinct().all()
    all_statuses = [s[0] for s in all_statuses if s[0]]
    
    # 매핑되지 않은 상태 필터링
    unmapped = []
    
    for status in all_statuses:
        mapping = db.query(OrderStatusMapping).filter(
            OrderStatusMapping.original_status == status
        ).first()
        
        if not mapping:
            # 해당 상태의 주문 개수
            count = db.query(Order).filter(Order.order_status == status).count()
            unmapped.append({
                "original_status": status,
                "count": count
            })
    
    return {"unmapped_statuses": unmapped}


# ============================================
# 상태 매핑 저장 API
# ============================================
@router.post("/api/save-status-mapping")
def save_status_mapping(
    request: Request,
    original_status: str = Form(...),
    normalized_status: str = Form(...),
    db: Session = Depends(get_db)
):
    """상태 매핑 저장"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    # 관리자만 가능
    if not user_info["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    
    from database import OrderStatusMapping
    
    # 기존 매핑 확인
    existing = db.query(OrderStatusMapping).filter(
        OrderStatusMapping.original_status == original_status
    ).first()
    
    if existing:
        # 업데이트
        existing.normalized_status = normalized_status
        existing.updated_at = datetime.now()
    else:
        # 새로 추가
        new_mapping = OrderStatusMapping(
            original_status=original_status,
            normalized_status=normalized_status
        )
        db.add(new_mapping)
    
    db.commit()
    
    return {"success": True, "message": "저장되었습니다"}


# ============================================
# 모든 매핑 조회 API
# ============================================
@router.get("/api/all-mappings")
def get_all_mappings(
    request: Request,
    db: Session = Depends(get_db)
):
    """모든 상태 매핑 조회"""
    user_info = check_order_permission(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="권한 없음")
    
    from database import OrderStatusMapping
    
    mappings = db.query(OrderStatusMapping).order_by(
        OrderStatusMapping.normalized_status,
        OrderStatusMapping.original_status
    ).all()
    
    return {
        "mappings": [
            {
                "id": m.id,
                "original_status": m.original_status,
                "normalized_status": m.normalized_status
            }
            for m in mappings
        ]
    }

# ============================================
# 매핑 관리 페이지
# ============================================
@router.get("/mappings", response_class=HTMLResponse)
def mappings_page(request: Request, db: Session = Depends(get_db)):
    """매핑 관리 페이지"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    # 관리자만 접근 가능
    if not user_info["is_admin"]:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "username": user_info["username"],
            "is_admin": user_info["is_admin"],
            "error_message": "관리자만 접근할 수 있습니다."
        })
    
    from database import OrderStatusMapping
    
    # 전체 매핑 조회
    mappings = db.query(OrderStatusMapping).order_by(
        OrderStatusMapping.normalized_status,
        OrderStatusMapping.original_status
    ).all()
    
    # 분류별 개수
    status_counts = {}
    for m in mappings:
        status_counts[m.normalized_status] = status_counts.get(m.normalized_status, 0) + 1
    
    return templates.TemplateResponse("order_mappings.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"],
        "mappings": mappings,
        "status_counts": status_counts
    })


# ============================================
# 매핑 수정 API
# ============================================
@router.post("/api/mapping/update")
def update_mapping(
    request: Request,
    mapping_id: int = Form(...),
    normalized_status: str = Form(...),
    db: Session = Depends(get_db)
):
    """매핑 수정"""
    user_info = check_order_permission(request)
    if not user_info or not user_info["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    
    from database import OrderStatusMapping
    
    mapping = db.query(OrderStatusMapping).filter(
        OrderStatusMapping.id == mapping_id
    ).first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="매핑을 찾을 수 없습니다")
    
    mapping.normalized_status = normalized_status
    mapping.updated_at = datetime.now()
    db.commit()
    
    return {"success": True, "message": "수정되었습니다"}


# ============================================
# 매핑 삭제 API
# ============================================
@router.post("/api/mapping/delete")
def delete_mapping(
    request: Request,
    mapping_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """매핑 삭제"""
    user_info = check_order_permission(request)
    if not user_info or not user_info["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    
    from database import OrderStatusMapping
    
    mapping = db.query(OrderStatusMapping).filter(
        OrderStatusMapping.id == mapping_id
    ).first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="매핑을 찾을 수 없습니다")
    
    db.delete(mapping)
    db.commit()
    
    return {"success": True, "message": "삭제되었습니다"}



def get_cj_tracking(tracking_number, order):
    """CJ대한통운 배송 조회"""
    try:
        # CJ 대한통운 API 호출
        url = "https://trace.cjlogistics.com/next/rest/selectTrackingWaybil.do"
        
        response = requests.post(url, data={"wblNo": tracking_number}, timeout=10)
        data = response.json()
        
        if data.get("resultCode") != 200 or not data.get("data"):
            return {
                "success": False,
                "message": "유효하지 않은 운송장번호입니다."
            }
        
        waybill = data["data"]
        
        # 배송 상세 정보 조회
        detail_url = "https://trace.cjlogistics.com/next/rest/selectTrackingDetailList.do"
        detail_response = requests.post(detail_url, data={"wblNo": tracking_number}, timeout=10)
        detail_data = detail_response.json()
        
        details = []
        if detail_data.get("resultCode") == 200 and detail_data.get("data"):
            for item in detail_data["data"].get("svcOutList", []):
                details.append({
                    "location": item.get("branNm", "-"),
                    "phone": item.get("procBranTelNo", "-"),
                    "date": item.get("workDt", "-"),
                    "time": item.get("workHms", "-"),
                    "status": item.get("crgStDnm", "-"),
                    "detail": item.get("crgStDcdVal", "-"),
                    "partner": item.get("patnBranNm", "-")
                })
        
        return {
            "success": True,
            "courier": "CJ대한통운",
            "tracking_number": tracking_number,
            "basic_info": {
                "sender_name": waybill.get("sndrNm", "-"),
                "sender_phone": waybill.get("sndrClphno", "-"),
                "sender_address": waybill.get("sndrAddr", "-"),
                "receiver_name": waybill.get("rcvrNm", "-"),
                "receiver_phone": waybill.get("rcvrClphno", "-"),
                "receiver_address": waybill.get("rcvrAddr", "-"),
                "product_name": f"{waybill.get('repGoodsNm', '')} {waybill.get('goodsDtlNm', '')}".strip(),
                "quantity": waybill.get("qty", "-"),
                "receiver": waybill.get("acprNm", "-"),
                "receiver_relation": waybill.get("acprRlpDnm", "-")
            },
            "details": details,
            "order_info": {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"조회 중 오류가 발생했습니다: {str(e)}"
        }


def get_kdexp_tracking(tracking_number, order):
    """경동택배 배송 조회"""
    try:
        # 경동택배 API 호출
        url = "https://kdexp.com/service/delivery/new/ajax_basic.do"
        
        response = requests.get(url, params={"barcode": tracking_number}, timeout=10)
        data = response.json()
        
        if data.get("result") != "suc" or not data.get("data"):
            return {
                "success": False,
                "message": "배송 정보가 없습니다."
            }
        
        info = data["data"]
        scan_list = info.get("scanList", [])
        
        # 역순 정렬 (최신순)
        scan_list.reverse()
        
        details = []
        for item in scan_list:
            # 날짜/시간 파싱
            scan_dt = item.get("scanDt", "")
            if scan_dt:
                parts = scan_dt.split(" ")
                date_part = parts[0] if len(parts) > 0 else "-"
                time_part = parts[1][:5] if len(parts) > 1 else "-"
            else:
                date_part = "-"
                time_part = "-"
            
            details.append({
                "date": date_part,
                "time": time_part,
                "location": item.get("strtPointNm", "-"),
                "phone": item.get("strtPointTelno", "-"),
                "status": item.get("scanTypeNm", "-")
            })
        
        return {
            "success": True,
            "courier": "경동택배",
            "tracking_number": tracking_number,
            "basic_info": {
                "send_branch": info.get("branSndnNm", "-"),
                "arrival_branch": info.get("branArvlNm", "-"),
                "sender_name": info.get("snCustNm", "-"),
                "receiver_name": info.get("rvCustNm", "-"),
                "product_name": info.get("prodName", "-"),
                "quantity": f"{info.get('count', '')} {info.get('wrapStatus', '')}".strip() or "-"
            },
            "details": details,
            "order_info": {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"조회 중 오류가 발생했습니다: {str(e)}"
        }
        

        
# ===== 한진택배 파싱 함수 =====
def parse_hanjin_tracking(html_content: str):
    """
    한진택배 HTML 응답을 파싱하여 배송 정보를 추출합니다.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "tracking_number": "",
        "sender_name": "-",
        "receiver_name": "-",
        "product_name": "-",
        "details": []
    }
    
    try:
        # 1. 기본 정보 테이블 파싱 (table.board-list-table.delivery-tbl)
        basic_table = soup.select_one('table.board-list-table.delivery-tbl')
        if basic_table:
            tbody = basic_table.select_one('tbody')
            if tbody:
                tds = tbody.select('td')
                if len(tds) >= 5:
                    result["product_name"] = tds[0].get_text(strip=True)
                    result["sender_name"] = tds[1].get_text(strip=True)
                    result["receiver_name"] = tds[2].get_text(strip=True)
                    # 받는 주소: tds[3], 운임: tds[4]
        
        # 2. 배송 상세 정보 테이블 파싱 (div.waybill-tbl > table)
        waybill_div = soup.select_one('div.waybill-tbl')
        
        if waybill_div:
            detail_table = waybill_div.select_one('table.board-list-table')
            
            if detail_table:
                tbody = detail_table.select_one('tbody')
                
                if tbody:
                    rows = tbody.select('tr')
                    
                    for row in rows:
                        # 날짜
                        date_td = row.select_one('td.w-date')
                        date_part = date_td.get_text(strip=True) if date_td else ""
                        
                        # 시간
                        time_td = row.select_one('td.w-time')
                        time_part = time_td.get_text(strip=True) if time_td else ""
                        
                        # 위치
                        org_td = row.select_one('td.w-org')
                        location = org_td.get_text(strip=True) if org_td else ""
                        
                        # 상태 및 설명
                        process_td = row.select_one('td.w-preocess')
                        if process_td:
                            # stateDesc에서 상태 추출
                            state_span = process_td.select_one('span.stateDesc')
                            if state_span:
                                # <strong> 태그 제거하고 텍스트 추출
                                for strong in state_span.find_all('strong'):
                                    strong.unwrap()  # strong 태그만 제거하고 내용은 유지
                                description = state_span.get_text(strip=True)
                                
                                # <br> 이후의 담당자 정보 추출
                                br_tag = process_td.find('br')
                                if br_tag and br_tag.next_sibling:
                                    contact_info = br_tag.next_sibling
                                    if isinstance(contact_info, str):
                                        contact_text = contact_info.strip()
                                        if contact_text:
                                            description += " " + contact_text
                            else:
                                description = process_td.get_text(strip=True)
                            
                            # 상태 추출 (간단하게)
                            status = "진행중"
                            if "접수" in description:
                                status = "상품접수"
                            elif "입고" in description:
                                status = "터미널 입고"
                            elif "이동" in description:
                                status = "상품 이동중"
                            elif "도착" in description:
                                status = "터미널 도착"
                            elif "배송출발" in description:
                                status = "배송 출발"
                            elif "배송완료" in description:
                                status = "배송 완료"
                        else:
                            status = ""
                            description = ""
                        
                        detail = {
                            "date": date_part,
                            "time": time_part,
                            "location": location,
                            "status": status,
                            "description": description
                        }
                        
                        result["details"].append(detail)
        
        print(f"✅ 한진택배 파싱 완료: {len(result['details'])}개 이벤트")
        
    except Exception as e:
        print(f"❌ 한진택배 파싱 오류: {e}")
        import traceback
        traceback.print_exc()
    
    return result


# ===== 한진택배 조회 함수 =====
def get_hanjin_tracking(tracking_number: str, order):
    """
    한진택배 배송 조회
    """
    try:
        print(f"🔍 한진택배 조회 시작: {tracking_number}")
        
        # 한진택배 조회 URL
        hanjin_url = f"https://www.hanjin.com/kor/CMS/DeliveryMgr/WaybillResult.do?mCode=MN038&schLang=KR&wblnumText2={tracking_number}"
        
        # HTML 가져오기
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(hanjin_url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"❌ 한진택배 HTTP 오류: {response.status_code}")
            return {
                "success": False,
                "message": f"한진택배 조회 실패 (HTTP {response.status_code})"
            }
        
        # HTML 파싱
        parsed_data = parse_hanjin_tracking(response.text)
        
        # details가 비어있으면 경고
        if not parsed_data.get("details"):
            print("⚠️ 경고: 한진택배 배송 이력이 없습니다")
        
        # 결과 구성
        result = {
            "success": True,
            "courier": "한진택배",
            "tracking_number": tracking_number,
            "basic_info": {
                "sender_name": parsed_data.get("sender_name", "-"),
                "receiver_name": parsed_data.get("receiver_name") or order.recipient_name or "-",
                "product_name": parsed_data.get("product_name") or order.product_name or "-",
                "quantity": str(order.quantity) if order.quantity else "-"
            },
            "details": parsed_data.get("details", []),
            "order_info": {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name
            }
        }
        
        print(f"✅ 한진택배 조회 성공: {len(result['details'])}개 이벤트")
        return result
        
    except requests.Timeout:
        print(f"❌ 한진택배 타임아웃")
        return {
            "success": False,
            "message": "한진택배 서버 응답 시간 초과"
        }
        
    except Exception as e:
        print(f"❌ 한진택배 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"한진택배 조회 중 오류 발생: {str(e)}"
        }

# ===== 우체국택배 파싱 함수 =====
def parse_epost_tracking(html_content: str):
    """
    우체국택배 HTML 응답을 파싱하여 배송 정보를 추출합니다.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "tracking_number": "",
        "sender_name": "-",
        "receiver_name": "-",
        "details": []
    }
    
    try:
        # 1. 기본 정보 테이블 파싱 (첫 번째 table.table_col)
        basic_tables = soup.select('table.table_col')
        if basic_tables:
            basic_table = basic_tables[0]  # 첫 번째 테이블
            tbody = basic_table.select_one('tbody')
            if tbody:
                tr = tbody.select_one('tr')
                if tr:
                    th = tr.select_one('th')
                    tds = tr.select('td')
                    
                    if th:
                        result["tracking_number"] = th.get_text(strip=True)
                    
                    if len(tds) >= 2:
                        # 보내는 분 (td[0])
                        sender_text = tds[0].get_text(strip=True).split('\n')[0].split('<br')[0]
                        result["sender_name"] = sender_text.split('/')[0].strip()
                        
                        # 받는 분 (td[1])
                        receiver_text = tds[1].get_text(strip=True).split('\n')[0].split('<br')[0]
                        result["receiver_name"] = receiver_text.strip()
        
        # 2. 배송 상세 정보 테이블 파싱 (table#processTable)
        detail_table = soup.select_one('table#processTable')
        
        if detail_table:
            tbody = detail_table.select_one('tbody')
            
            if tbody:
                rows = tbody.select('tr')
                
                for row in rows:
                    tds = row.select('td')
                    
                    if len(tds) >= 4:
                        # 날짜
                        date_part = tds[0].get_text(strip=True)
                        
                        # 시간
                        time_part = tds[1].get_text(strip=True)
                        
                        # 발생국 (location)
                        location_td = tds[2]
                        location_link = location_td.select_one('a')
                        if location_link:
                            location = location_link.get_text(strip=True)
                        else:
                            location = location_td.get_text(strip=True)
                        
                        # 처리현황
                        status_td = tds[3]
                        evtnm_span = status_td.select_one('span.evtnm')
                        
                        if evtnm_span:
                            status = evtnm_span.get_text(strip=True)
                            
                            # 전체 텍스트에서 추가 정보 추출
                            full_text = status_td.get_text(separator=' ', strip=True)
                            # evtnm 이후의 텍스트를 description으로
                            description = full_text.replace(status, '', 1).strip()
                            
                            # 괄호 안의 정보 정리
                            if '(' in description:
                                description = description.replace('\n', ' ').replace('  ', ' ')
                        else:
                            status = status_td.get_text(strip=True)
                            description = ""
                        
                        detail = {
                            "date": date_part,
                            "time": time_part,
                            "location": location,
                            "status": status,
                            "description": description
                        }
                        
                        result["details"].append(detail)
        
        print(f"✅ 우체국택배 파싱 완료: {len(result['details'])}개 이벤트")
        
    except Exception as e:
        print(f"❌ 우체국택배 파싱 오류: {e}")
        import traceback
        traceback.print_exc()
    
    return result


# ===== 우체국택배 조회 함수 =====
def get_epost_tracking(tracking_number: str, order):
    """
    우체국택배 배송 조회
    """
    try:
        print(f"🔍 우체국택배 조회 시작: {tracking_number}")
        
        # 우체국택배 조회 URL
        epost_url = f"https://service.epost.go.kr/trace.RetrieveDomRigiTrace6789List.comm?sid1={tracking_number}&displayHeader=N"
        
        # HTML 가져오기
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(epost_url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"❌ 우체국택배 HTTP 오류: {response.status_code}")
            return {
                "success": False,
                "message": f"우체국택배 조회 실패 (HTTP {response.status_code})"
            }
        
        # HTML 파싱
        parsed_data = parse_epost_tracking(response.text)
        
        # details가 비어있으면 경고
        if not parsed_data.get("details"):
            print("⚠️ 경고: 우체국택배 배송 이력이 없습니다")
        
        # 결과 구성
        result = {
            "success": True,
            "courier": "우체국택배",
            "tracking_number": tracking_number,
            "basic_info": {
                "sender_name": parsed_data.get("sender_name", "-"),
                "receiver_name": parsed_data.get("receiver_name") or order.recipient_name or "-",
                "product_name": order.product_name or "-",
                "quantity": str(order.quantity) if order.quantity else "-"
            },
            "details": parsed_data.get("details", []),
            "order_info": {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name
            }
        }
        
        print(f"✅ 우체국택배 조회 성공: {len(result['details'])}개 이벤트")
        return result
        
    except requests.Timeout:
        print(f"❌ 우체국택배 타임아웃")
        return {
            "success": False,
            "message": "우체국택배 서버 응답 시간 초과"
        }
        
    except Exception as e:
        print(f"❌ 우체국택배 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"우체국택배 조회 중 오류 발생: {str(e)}"
        }

# ===== 로젠택배 파싱 함수 =====
def parse_logen_tracking(html_content: str):
    """
    로젠택배 HTML 응답을 파싱하여 배송 정보를 추출합니다.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "tracking_number": "",
        "sender_name": "-",
        "receiver_name": "-",
        "product_name": "-",
        "details": []
    }
    
    try:
        # 1. 기본 정보 테이블 파싱 (table.horizon.pdInfo)
        basic_table = soup.select_one('table.horizon.pdInfo')
        if basic_table:
            tbody = basic_table.select_one('tbody')
            if tbody:
                rows = tbody.select('tr')
                for row in rows:
                    tds = row.select('td')
                    for i in range(0, len(tds), 2):
                        if i + 1 < len(tds):
                            label = tds[i].get_text(strip=True)
                            value = tds[i + 1].get_text(strip=True)
                            
                            if label == "송장번호":
                                result["tracking_number"] = value
                            elif label == "상품명":
                                result["product_name"] = value
                            elif label == "보내시는 분":
                                result["sender_name"] = value
                            elif label == "받으시는 분":
                                result["receiver_name"] = value
        
        # 2. 배송 상세 정보 테이블 파싱 (table.data.tkInfo)
        detail_table = soup.select_one('table.data.tkInfo')
        
        if detail_table:
            tbody = detail_table.select_one('tbody')
            
            if tbody:
                rows = tbody.select('tr')
                
                for row in rows:
                    tds = row.select('td')
                    
                    if len(tds) >= 8:
                        # 날짜 및 시간 파싱
                        datetime_text = tds[0].get_text(strip=True)
                        date_part = ""
                        time_part = ""
                        
                        if ' ' in datetime_text:
                            parts = datetime_text.split(' ', 1)
                            date_part = parts[0]
                            time_part = parts[1] if len(parts) > 1 else ""
                        else:
                            date_part = datetime_text
                        
                        # 사업장
                        location = tds[1].get_text(strip=True)
                        
                        # 배송상태
                        status = tds[2].get_text(strip=True)
                        
                        # 배송내용
                        description = tds[3].get_text(strip=True)
                        
                        # 담당직원 + 영업소 + 연락처
                        staff = tds[4].get_text(strip=True)
                        office = tds[6].get_text(strip=True)
                        contact = tds[7].get_text(strip=True)
                        
                        # 추가 정보 결합
                        if staff or office or contact:
                            extra_info = []
                            if staff:
                                extra_info.append(f"담당: {staff}")
                            if office:
                                extra_info.append(f"영업소: {office}")
                            if contact:
                                extra_info.append(f"연락처: {contact}")
                            if extra_info:
                                description += " (" + ", ".join(extra_info) + ")"
                        
                        detail = {
                            "date": date_part,
                            "time": time_part,
                            "location": location,
                            "status": status,
                            "description": description
                        }
                        
                        result["details"].append(detail)
        
        print(f"✅ 로젠택배 파싱 완료: {len(result['details'])}개 이벤트")
        
    except Exception as e:
        print(f"❌ 로젠택배 파싱 오류: {e}")
        import traceback
        traceback.print_exc()
    
    return result


# ===== 로젠택배 조회 함수 =====
def get_logen_tracking(tracking_number: str, order):
    """
    로젠택배 배송 조회
    """
    try:
        print(f"🔍 로젠택배 조회 시작: {tracking_number}")
        
        # 로젠택배 조회 URL
        logen_url = f"https://www.ilogen.com/web/personal/trace/{tracking_number}"
        
        # HTML 가져오기
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(logen_url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"❌ 로젠택배 HTTP 오류: {response.status_code}")
            return {
                "success": False,
                "message": f"로젠택배 조회 실패 (HTTP {response.status_code})"
            }
        
        # HTML 파싱
        parsed_data = parse_logen_tracking(response.text)
        
        # details가 비어있으면 경고
        if not parsed_data.get("details"):
            print("⚠️ 경고: 로젠택배 배송 이력이 없습니다")
        
        # 결과 구성
        result = {
            "success": True,
            "courier": "로젠택배",
            "tracking_number": tracking_number,
            "basic_info": {
                "sender_name": parsed_data.get("sender_name", "-"),
                "receiver_name": parsed_data.get("receiver_name") or order.recipient_name or "-",
                "product_name": parsed_data.get("product_name") or order.product_name or "-",
                "quantity": str(order.quantity) if order.quantity else "-"
            },
            "details": parsed_data.get("details", []),
            "order_info": {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name
            }
        }
        
        print(f"✅ 로젠택배 조회 성공: {len(result['details'])}개 이벤트")
        return result
        
    except requests.Timeout:
        print(f"❌ 로젠택배 타임아웃")
        return {
            "success": False,
            "message": "로젠택배 서버 응답 시간 초과"
        }
        
    except Exception as e:
        print(f"❌ 로젠택배 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"로젠택배 조회 중 오류 발생: {str(e)}"
        }


# ===== 롯데택배 파싱 함수 =====
def parse_lotte_tracking(html_content: str):
    """
    롯데택배 HTML 응답을 파싱하여 배송 정보를 추출합니다.
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
        
        # 2. 배송 상세 정보 테이블 파싱 (두 번째 table.tblH)
        all_tables = soup.select('table.tblH')
        
        if len(all_tables) >= 2:
            detail_table = all_tables[1]  # 두 번째 테이블
            tbody = detail_table.select_one('tbody')
            
            if tbody:
                rows = tbody.select('tr')
                
                for row in rows:
                    tds = row.select('td')
                    
                    if len(tds) >= 4:
                        # 시간 텍스트 추출 및 정리
                        time_text = tds[1].get_text(strip=True)
                        time_text = time_text.replace('\xa0', ' ').replace('&nbsp;', ' ')
                        
                        # 날짜와 시간 분리
                        date_part = ""
                        time_part = ""
                        
                        if ' ' in time_text and '--:--' not in time_text:
                            parts = time_text.split(' ', 1)
                            date_part = parts[0]
                            time_part = parts[1] if len(parts) > 1 else ""
                        elif '--:--' in time_text:
                            date_part = time_text.split(' ')[0] if ' ' in time_text else time_text
                            time_part = ""
                        else:
                            date_part = time_text
                            time_part = ""
                        
                        # 처리현황에서 <br> 태그를 공백으로 변환
                        description_td = tds[3]
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
        
        print(f"✅ 롯데택배 파싱 완료: 송장 {result['tracking_number']}, {len(result['details'])}개 이벤트")
        
    except Exception as e:
        print(f"❌ 롯데택배 파싱 오류: {e}")
        import traceback
        traceback.print_exc()
    
    return result


# ===== 롯데택배 조회 함수 =====
def get_lotte_tracking(tracking_number: str, order):
    """
    롯데택배 배송 조회
    """
    try:
        print(f"🔍 롯데택배 조회 시작: {tracking_number}")
        
        # 롯데택배 조회 URL
        lotte_url = f"https://www.lotteglogis.com/home/reservation/tracking/linkView?InvNo={tracking_number}"
        
        # HTML 가져오기
        response = requests.get(lotte_url, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"❌ 롯데택배 HTTP 오류: {response.status_code}")
            return {
                "success": False,
                "message": f"롯데택배 조회 실패 (HTTP {response.status_code})"
            }
        
        # HTML 파싱
        parsed_data = parse_lotte_tracking(response.text)
        
        # details가 비어있으면 경고
        if not parsed_data.get("details"):
            print("⚠️ 경고: 롯데택배 배송 이력이 없습니다")
        
        # 결과 구성
        result = {
            "success": True,
            "courier": "롯데택배",
            "tracking_number": tracking_number,
            "basic_info": {
                "sender_name": parsed_data.get("sender_name", "-"),
                "receiver_name": order.recipient_name or "-",
                "product_name": order.product_name or "-",
                "quantity": str(order.quantity) if order.quantity else "-"
            },
            "details": parsed_data.get("details", []),
            "order_info": {
                "order_number": order.order_number,
                "buyer_name": order.buyer_name,
                "recipient_name": order.recipient_name
            }
        }
        
        print(f"✅ 롯데택배 조회 성공: {len(result['details'])}개 이벤트")
        return result
        
    except requests.Timeout:
        print(f"❌ 롯데택배 타임아웃")
        return {
            "success": False,
            "message": "롯데택배 서버 응답 시간 초과"
        }
        
    except Exception as e:
        print(f"❌ 롯데택배 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"롯데택배 조회 중 오류 발생: {str(e)}"
        }

# 기존 /orders/api/tracking/{order_id} 엔드포인트 수정
@router.get("/api/tracking/{order_id}")
def get_tracking(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order or not order.tracking_number:
        return {"success": False, "message": "송장번호가 없습니다"} 
    
        # ⭐ 송장번호 .0 제거 (더 안전한 방식)
    tracking_number = str(order.tracking_number)
    if tracking_number.endswith('.0'):
        tracking_number = tracking_number[:-2]
    
    courier_company = (order.courier_company or "").lower()
    
    # CJ대한통운
    if any(keyword in courier_company for keyword in ['cj', '대한통운', 'cjgls', 'CJ택배', 'cj대한통운']):
        return get_cj_tracking(tracking_number, order)
    
    # 경동택배
    elif any(keyword in courier_company for keyword in ['경동', 'kdexp', '경동택배']):
        return get_kdexp_tracking(tracking_number, order)
    
    # 한진택배
    elif any(keyword in courier_company for keyword in ['한진', 'hanjin', '한진택배']):
        return get_hanjin_tracking(tracking_number, order)
    
    # 우체국택배
    elif any(keyword in courier_company for keyword in ['우체국', 'epost', '우편', '우체국택배']):
        return get_epost_tracking(tracking_number, order)
    
    # 로젠택배
    elif any(keyword in courier_company for keyword in ['로젠', 'logen', '일로젠', '로젠택배']):
        return get_logen_tracking(tracking_number, order)
    
    # 롯데택배
    elif any(keyword in courier_company for keyword in ['롯데', 'lotte', '롯데택배']):
        return get_lotte_tracking(tracking_number, order)
    
    else:
        return {
            "success": False,
            "message": f"지원하지 않는 택배사입니다: {order.courier_company}"
        }
        
# 송장번호 정리 함수 추가
def clean_tracking_number(tracking_number):
    """송장번호에서 .0 제거"""
    if not tracking_number:
        return ""
    
    tracking_str = str(tracking_number)
    if tracking_str.endswith('.0'):
        return tracking_str[:-2]
    
    return tracking_str


