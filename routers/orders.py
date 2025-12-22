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


# ============================================
# 1. 전체 현황 (대시보드)
# ============================================
# routers/orders.py - order_dashboard 함수 (완전 교체)

@router.get("/dashboard", response_class=HTMLResponse)
def order_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """주문 전체 현황 대시보드"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    from datetime import timedelta
    
    # 기본 통계
    total_orders = db.query(Order).count()
    today_str = date.today().strftime('%Y-%m-%d')
    today_orders = db.query(Order).filter(
        Order.order_date.like(f'{today_str}%')
    ).count()
    
    # ============================================
    # ⭐ 1. 가송장 사용 건 (앞 6자리만 확인)
    # ============================================
    valid_couriers = [
        'CJ대한통운', 'CJ택배', '대한통운', '로젠택배', '롯데택배',
        '우체국택배', '천일택배', '편의점택배(GS25)', '한진택배'
    ]
    
    all_orders = db.query(Order).all()
    fake_tracking_count = 0
    
    for order in all_orders:
        # 택배사 확인
        courier = order.courier_company or ''
        is_valid_courier = any(valid in courier for valid in valid_couriers)
        
        # 송장번호 앞 6자리가 날짜 형식인지 확인
        tracking = order.tracking_number or ''
        is_date_format = False
        
        if len(tracking) >= 6:
            prefix = tracking[:6]  # ⭐ 무조건 앞 6자리만
            
            if prefix.isdigit():
                # YYMMDD 또는 YYYYMM 형식 체크
                try:
                    # 251220 형식 (YYMMDD)
                    year_part = int(prefix[:2])
                    month = int(prefix[2:4])
                    day = int(prefix[4:6])
                    
                    # 유효한 날짜인지 확인
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        is_date_format = True
                    # 또는 202512 형식 (YYYYMM)
                    elif 20 <= year_part <= 30:  # 2020~2030년대
                        month_check = int(prefix[4:6])
                        if 1 <= month_check <= 12:
                            is_date_format = True
                except (ValueError, IndexError):
                    pass
        
        # 가송장 조건: 정상 택배사 아님 AND 날짜 형식 송장번호
        if not is_valid_courier and is_date_format and tracking:
            fake_tracking_count += 1
    
    # ============================================
    # ⭐ 2. 네이버 송장 흐름 (TODO: 외부 API 연동 필요)
    # ============================================
    naver_delivery_count = 0  # 일단 0으로 표시
    
    # ============================================
    # ⭐ 3. 경동 이관 (DB 컬럼 기반)
    # ============================================
    kyungdong_count = db.query(Order).filter(
        Order.is_kyungdong_transferred == True
    ).count()
    
    # ============================================
    # ⭐ 4. 통관 절차 이상
    # ============================================
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
    
    # ============================================
    # ⭐ 5. 장기 미배송 (2주 = 14일)
    # ============================================
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
    
    # 상태별 통계
    status_stats = db.query(
        Order.order_status,
        func.count(Order.id).label("count")
    ).group_by(Order.order_status).all()
    
    # 최근 주문 10개
    recent_orders = db.query(Order).order_by(desc(Order.created_at)).limit(10).all()
    
    return templates.TemplateResponse("order_dashboard.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"],
        "total_orders": total_orders,
        "today_orders": today_orders,
        "status_stats": status_stats,
        "recent_orders": recent_orders,
        "fake_tracking_count": fake_tracking_count,
        "naver_delivery_count": naver_delivery_count,  # 0
        "kyungdong_count": kyungdong_count,
        "customs_issue_count": customs_issue_count,
        "long_undelivered_count": long_undelivered_count
    })


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
        success_count = 0
        error_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                # 주문번호 확인
                order_number = row.get("order_number")
                if not order_number or order_number == "None":
                    error_count += 1
                    errors.append(f"행 {idx+2}: 주문번호 누락")
                    continue
                
                # 기존 주문 확인
                existing_order = db.query(Order).filter(
                    Order.order_number == order_number
                ).first()
                
                if existing_order:
                    if update_mode == "skip":
                        continue
                    elif update_mode == "update":
                        # 업데이트
                        for key, value in row.items():
                            if key in column_mapping.values():
                                setattr(existing_order, key, value)
                        existing_order.updated_at = datetime.now()
                        success_count += 1
                else:
                    # 새 주문 생성
                    order_data = {}
                    for key, value in row.items():
                        if key in column_mapping.values():
                            order_data[key] = value
                    
                    new_order = Order(**order_data)
                    db.add(new_order)
                    success_count += 1
                    
                
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                # 오류 메시지 정리
                if "duplicate key" in error_msg.lower():
                    errors.append(f"행 {idx+2}: 중복된 주문번호 ({order_number})")
                else:
                    errors.append(f"행 {idx+2}: {error_msg[:100]}")
                continue  # 오류 발생해도 다음 행 계속 처리
        
        # ⭐ 최종 커밋 (한 번만!)
        db.commit()
        print("=" * 50)
        print(f"✅ 업로드 완료: 성공 {success_count}건, 실패 {error_count}건")
        
        return JSONResponse({
            "success": True,
            "message": f"업로드 완료: 성공 {success_count}건, 실패 {error_count}건",
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors[:20]  # 최대 20개만 표시
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