# routers/orders.py

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, desc
from datetime import datetime, date
import pandas as pd
import os
from typing import Optional
import requests

from bs4 import BeautifulSoup
from database import get_db, Order, User

router = APIRouter(prefix="/orders", tags=["orders"])
templates = Jinja2Templates(directory="templates")

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
            "경동이관여부": "is_kyungdong_transferred",  # ⭐ 추가
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
            "마진율": "profit_margin_rate"
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


import requests
from bs4 import BeautifulSoup


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
        
# 한진택배 조회
def get_hanjin_tracking(tracking_number: str, order: Order):
    """한진택배 배송 조회"""
    try:
        url = f"https://www.hanjin.com/kor/CMS/DeliveryMgr/WaybillResult.do?mCode=MN038&schLang=KR&wblnum={tracking_number}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {"success": False, "message": "한진택배 조회 실패"}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 기본 정보 추출
        basic_info = {}
        
        # 일반적으로 한진택배는 테이블 구조로 되어 있음
        info_table = soup.find('table', class_='table_vertical')
        if info_table:
            rows = info_table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    
                    if '송장번호' in key or '운송장' in key:
                        basic_info['tracking_number'] = value
                    elif '보내시는' in key or '송화인' in key:
                        basic_info['sender_name'] = value
                    elif '받으시는' in key or '수화인' in key:
                        basic_info['receiver_name'] = value
                    elif '제품명' in key or '품목' in key:
                        basic_info['product_name'] = value
        
        # 기본값 설정
        basic_info.setdefault('sender_name', '-')
        basic_info.setdefault('receiver_name', order.recipient_name or '-')
        basic_info.setdefault('product_name', order.product_name or '-')
        basic_info.setdefault('quantity', str(order.quantity or '-'))
        
        # 배송 추적 정보 추출
        details = []
        
        tracking_table = soup.find('table', class_='table_horizontal')
        if tracking_table:
            tbody = tracking_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 4:
                        detail = {
                            'date': cols[0].get_text(strip=True),
                            'time': cols[1].get_text(strip=True) if len(cols) > 1 else '',
                            'location': cols[2].get_text(strip=True) if len(cols) > 2 else '',
                            'status': cols[3].get_text(strip=True) if len(cols) > 3 else '',
                            'phone': cols[4].get_text(strip=True) if len(cols) > 4 else ''
                        }
                        details.append(detail)
        
        return {
            "success": True,
            "courier": "한진택배",
            "tracking_number": tracking_number,
            "basic_info": basic_info,
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
            "message": f"한진택배 조회 실패: {str(e)}"
        }

# 우체국택배 조회
def get_epost_tracking(tracking_number: str, order: Order):
    """우체국택배 배송 조회"""
    try:
        url = f"https://service.epost.go.kr/trace.RetrieveDomRigiTraceList.comm?sid1={tracking_number}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Accept-Language': 'ko-KR,ko;q=0.9',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {"success": False, "message": "우체국택배 조회 실패"}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 기본 정보
        basic_info = {
            'sender_name': '-',
            'receiver_name': order.recipient_name or '-',
            'product_name': order.product_name or '-',
            'quantity': str(order.quantity or '-')
        }
        
        # 상세 정보 추출
        details = []
        
        # 우체국택배 테이블 구조 파싱
        table = soup.find('table', class_='table_col')
        if table:
            tbody = table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        detail = {
                            'date': cols[0].get_text(strip=True).split()[0] if cols[0].get_text(strip=True) else '',
                            'time': cols[0].get_text(strip=True).split()[1] if len(cols[0].get_text(strip=True).split()) > 1 else '',
                            'location': cols[1].get_text(strip=True),
                            'status': cols[2].get_text(strip=True),
                            'phone': cols[3].get_text(strip=True) if len(cols) > 3 else ''
                        }
                        details.append(detail)
        
        return {
            "success": True,
            "courier": "우체국택배",
            "tracking_number": tracking_number,
            "basic_info": basic_info,
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
            "message": f"우체국택배 조회 실패: {str(e)}"
        }

# 로젠택배 조회
def get_logen_tracking(tracking_number: str, order: Order):
    """로젠택배 배송 조회"""
    try:
        url = f"https://www.ilogen.com/web/personal/trace/{tracking_number}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Accept-Language': 'ko-KR,ko;q=0.9',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {"success": False, "message": "로젠택배 조회 실패"}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 기본 정보
        basic_info = {
            'sender_name': '-',
            'receiver_name': order.recipient_name or '-',
            'product_name': order.product_name or '-',
            'quantity': str(order.quantity or '-')
        }
        
        # 테이블에서 기본 정보 추출
        info_table = soup.find('table', class_='invoice_table')
        if info_table:
            rows = info_table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    
                    if '보내는분' in key:
                        basic_info['sender_name'] = value
                    elif '받는분' in key:
                        basic_info['receiver_name'] = value
                    elif '상품명' in key:
                        basic_info['product_name'] = value
        
        # 배송 추적 정보
        details = []
        
        tracking_table = soup.find('table', class_='dataTable')
        if tracking_table:
            tbody = tracking_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        datetime_text = cols[0].get_text(strip=True)
                        date_time = datetime_text.split()
                        
                        detail = {
                            'date': date_time[0] if len(date_time) > 0 else '',
                            'time': date_time[1] if len(date_time) > 1 else '',
                            'location': cols[1].get_text(strip=True),
                            'status': cols[2].get_text(strip=True),
                            'phone': cols[3].get_text(strip=True) if len(cols) > 3 else ''
                        }
                        details.append(detail)
        
        return {
            "success": True,
            "courier": "로젠택배",
            "tracking_number": tracking_number,
            "basic_info": basic_info,
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
            "message": f"로젠택배 조회 실패: {str(e)}"
        }


# 롯데택배 조회
def get_lotte_tracking(tracking_number: str, order: Order):
    """롯데택배 배송 조회"""
    try:
        # 세션 생성
        session = requests.Session()
        
        # 먼저 메인 페이지 접속 (쿠키 받기)
        session.get('https://www.lotteglogis.com/home/reservation/tracking/index', 
                   headers={'User-Agent': 'Mozilla/5.0'})
        
        # POST 요청으로 조회
        url = "https://www.lotteglogis.com/home/reservation/tracking/invoiceView"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.lotteglogis.com/home/reservation/tracking/index',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
        }
        
        data = {
            'InvNo': tracking_number
        }
        
        response = session.post(url, headers=headers, data=data, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return {"success": False, "message": "롯데택배 조회 실패"}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 기본 정보
        basic_info = {
            'sender_name': '-',
            'receiver_name': order.recipient_name or '-',
            'product_name': order.product_name or '-',
            'quantity': str(order.quantity or '-')
        }
        
        # 테이블에서 기본 정보 추출
        info_table = soup.find('table', class_='tblV')
        if info_table:
            rows = info_table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    
                    if '보내시는' in key:
                        basic_info['sender_name'] = value
                    elif '받으시는' in key:
                        basic_info['receiver_name'] = value
                    elif '상품' in key:
                        basic_info['product_name'] = value
        
        # 배송 추적 정보
        details = []
        
        tracking_table = soup.find('table', class_='tblH')
        if tracking_table:
            tbody = tracking_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        detail = {
                            'date': cols[0].get_text(strip=True),
                            'time': cols[1].get_text(strip=True) if len(cols) > 1 else '',
                            'location': cols[2].get_text(strip=True) if len(cols) > 2 else '',
                            'status': cols[3].get_text(strip=True) if len(cols) > 3 else '',
                            'phone': cols[4].get_text(strip=True) if len(cols) > 4 else ''
                        }
                        details.append(detail)
        
        return {
            "success": True,
            "courier": "롯데택배",
            "tracking_number": tracking_number,
            "basic_info": basic_info,
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
            "message": f"롯데택배 조회 실패: {str(e)}"
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