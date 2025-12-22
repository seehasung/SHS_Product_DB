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
@router.get("/dashboard", response_class=HTMLResponse)
def order_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """주문 전체 현황 대시보드"""
    user_info = check_order_permission(request)
    if not user_info:
        return RedirectResponse(url="/login", status_code=302)
    
    # 통계 데이터
    total_orders = db.query(Order).count()
    today_orders = db.query(Order).filter(
        func.date(Order.order_date) == date.today()
    ).count()
    
    # 상태별 통계
    status_stats = db.query(
        Order.order_status,
        func.count(Order.id).label("count")
    ).group_by(Order.order_status).all()
    
    # 최근 주문 10개
    recent_orders = db.query(Order).order_by(desc(Order.created_at)).limit(10).all()
    
    # 금액 통계
    total_amount = db.query(func.sum(Order.payment_amount)).scalar() or 0
    total_profit = db.query(func.sum(Order.profit_margin)).scalar() or 0
    
    return templates.TemplateResponse("order_dashboard.html", {
        "request": request,
        "username": user_info["username"],
        "is_admin": user_info["is_admin"],
        "can_manage_orders": user_info["can_manage_orders"],
        "total_orders": total_orders,
        "today_orders": today_orders,
        "status_stats": status_stats,
        "recent_orders": recent_orders,
        "total_amount": total_amount,
        "total_profit": total_profit
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
@router.post("/api/upload")
async def upload_orders(
    request: Request,
    file: UploadFile = File(...),
    update_mode: str = Form("append"),
    db: Session = Depends(get_db)
):
    """엑셀 파일 업로드 및 DB 저장"""
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
            df["exchange_rate"] = df["order_processing_date"].apply(
                lambda x: float(str(x).split("-")[-1]) if pd.notna(x) and "-" in str(x) else None
            )
        
        # NaN 값 처리
        df = df.where(pd.notna(df), None)
        
        # 업데이트 모드 처리
        if update_mode == "replace":
            db.query(Order).delete()
            db.commit()
        
        # DB에 저장
        success_count = 0
        error_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                order_number = row.get("order_number")
                if not order_number:
                    error_count += 1
                    errors.append(f"행 {idx+2}: 주문번호 누락")
                    continue
                
                existing_order = db.query(Order).filter(
                    Order.order_number == order_number
                ).first()
                
                if existing_order:
                    if update_mode == "skip":
                        continue
                    elif update_mode == "update":
                        for key, value in row.items():
                            if key in column_mapping.values() and value is not None:
                                setattr(existing_order, key, value)
                        existing_order.updated_at = datetime.now()
                        success_count += 1
                else:
                    order_data = {
                        key: value for key, value in row.items()
                        if key in column_mapping.values()
                    }
                    
                    for date_field in ["order_date", "claim_date"]:
                        if date_field in order_data and order_data[date_field]:
                            try:
                                order_data[date_field] = pd.to_datetime(order_data[date_field]).date()
                            except:
                                order_data[date_field] = None
                    
                    new_order = Order(**order_data)
                    db.add(new_order)
                    success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"행 {idx+2}: {str(e)}")
        
        db.commit()
        
        return JSONResponse({
            "success": True,
            "message": f"업로드 완료: 성공 {success_count}건, 실패 {error_count}건",
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors[:10]
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
    
    query = db.query(
        Order.buyer_name,
        Order.recipient_name,
        Order.contact_number,
        func.count(Order.id).label("order_count"),
        func.sum(Order.payment_amount).label("total_amount")
    ).group_by(Order.buyer_name, Order.recipient_name, Order.contact_number)
    
    if search:
        query = query.filter(
            or_(
                Order.buyer_name.ilike(f"%{search}%"),
                Order.recipient_name.ilike(f"%{search}%"),
                Order.contact_number.ilike(f"%{search}%")
            )
        )
    
    customers = query.all()
    
    return {
        "customers": [
            {
                "buyer_name": c.buyer_name,
                "recipient_name": c.recipient_name,
                "contact_number": c.contact_number,
                "order_count": c.order_count,
                "total_amount": float(c.total_amount) if c.total_amount else 0
            }
            for c in customers
        ]
    }


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
    
    query = db.query(Order).filter(Order.tracking_number.isnot(None))
    
    if search:
        query = query.filter(
            or_(
                Order.tracking_number.ilike(f"%{search}%"),
                Order.order_number.ilike(f"%{search}%"),
                Order.recipient_name.ilike(f"%{search}%")
            )
        )
    
    deliveries = query.order_by(desc(Order.order_date)).limit(100).all()
    
    return {
        "deliveries": [
            {
                "id": d.id,
                "order_number": d.order_number,
                "tracking_number": d.tracking_number,
                "courier_company": d.courier_company,
                "recipient_name": d.recipient_name,
                "order_date": d.order_date.isoformat() if d.order_date else None,
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
    
    query = db.query(Order).filter(Order.customs_number.isnot(None))
    
    if search:
        query = query.filter(
            or_(
                Order.customs_number.ilike(f"%{search}%"),
                Order.order_number.ilike(f"%{search}%"),
                Order.recipient_name.ilike(f"%{search}%")
            )
        )
    
    customs = query.order_by(desc(Order.order_date)).limit(100).all()
    
    return {
        "customs": [
            {
                "id": c.id,
                "order_number": c.order_number,
                "customs_number": c.customs_number,
                "recipient_name": c.recipient_name,
                "order_date": c.order_date.isoformat() if c.order_date else None,
                "order_status": c.order_status,
                "customs_prepayment": float(c.customs_prepayment) if c.customs_prepayment else 0
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