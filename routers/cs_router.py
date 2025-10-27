# cs_router.py - CS 관리 라우터

from fastapi import APIRouter, Request, Form, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import Optional, List
from datetime import datetime, timedelta
import json

from database import get_db
from cs_models import Customer, CSRecord, CustomerPurchase, Shipment
from models import Product, User, Order
from auth import get_current_user

router = APIRouter(prefix="/cs", tags=["customer-service"])
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def cs_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """CS 대시보드 메인 페이지"""
    # 오늘의 CS 통계
    today = datetime.now().date()
    
    # 오늘 상담 건수
    today_cs_count = db.query(CSRecord).filter(
        func.date(CSRecord.created_at) == today
    ).count()
    
    # 진행중인 CS
    ongoing_cs = db.query(CSRecord).filter(
        CSRecord.cs_status == "진행중"
    ).count()
    
    # 최근 CS 기록 (10건)
    recent_cs = db.query(CSRecord).order_by(
        CSRecord.created_at.desc()
    ).limit(10).all()
    
    # 긴급 CS
    urgent_cs = db.query(CSRecord).filter(
        CSRecord.priority == "긴급",
        CSRecord.cs_status != "완료"
    ).all()
    
    return templates.TemplateResponse("cs_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "today_cs_count": today_cs_count,
        "ongoing_cs": ongoing_cs,
        "recent_cs": recent_cs,
        "urgent_cs": urgent_cs,
        "today": today
    })

@router.get("/search-by-phone")
async def search_customer_by_phone(
    phone: str = Query(..., description="전화번호"),
    db: Session = Depends(get_db)
):
    """전화번호로 고객 정보 및 CS 이력 조회"""
    # 전화번호 정규화 (하이픈 제거 등)
    normalized_phone = phone.replace("-", "").replace(" ", "")
    
    # 고객 조회
    customer = db.query(Customer).filter(
        Customer.phone.contains(normalized_phone)
    ).first()
    
    if not customer:
        # 새 고객인 경우
        return {
            "is_new_customer": True,
            "phone": phone,
            "message": "신규 고객입니다"
        }
    
    # 기존 고객인 경우 - 상세 정보 조회
    # CS 이력 (최근 10건)
    cs_records = db.query(CSRecord).filter(
        CSRecord.customer_id == customer.id
    ).order_by(CSRecord.created_at.desc()).limit(10).all()
    
    # 구매 이력
    purchases = db.query(CustomerPurchase).filter(
        CustomerPurchase.customer_id == customer.id
    ).order_by(CustomerPurchase.purchase_date.desc()).all()
    
    # 진행중인 배송
    active_shipments = db.query(Shipment).filter(
        Shipment.customer_id == customer.id,
        Shipment.delivered_date == None
    ).all()
    
    # 데이터 직렬화
    customer_data = {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "address": customer.address,
        "memo": customer.memo,
        "created_at": customer.created_at.isoformat() if customer.created_at else None
    }
    
    cs_records_data = [{
        "id": record.id,
        "cs_type": record.cs_type,
        "cs_status": record.cs_status,
        "cs_content": record.cs_content,
        "cs_result": record.cs_result,
        "handler_name": record.handler_name,
        "marketplace": record.marketplace,
        "order_number": record.order_number,
        "tracking_number": record.tracking_number,
        "priority": record.priority,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "product": {
            "id": record.product.id,
            "name": record.product.name
        } if record.product else None
    } for record in cs_records]
    
    purchases_data = [{
        "id": purchase.id,
        "marketplace": purchase.marketplace,
        "order_number": purchase.order_number,
        "purchase_date": purchase.purchase_date.isoformat() if purchase.purchase_date else None,
        "quantity": purchase.quantity,
        "price": purchase.price,
        "status": purchase.status,
        "product": {
            "id": purchase.product.id,
            "name": purchase.product.name,
            "image": purchase.product.image
        } if purchase.product else None
    } for purchase in purchases]
    
    shipments_data = [{
        "id": shipment.id,
        "proxy_company": shipment.proxy_company,
        "proxy_application_number": shipment.proxy_application_number,
        "domestic_tracking": shipment.domestic_tracking,
        "domestic_status": shipment.domestic_status,
        "international_tracking": shipment.international_tracking,
        "international_status": shipment.international_status,
        "customs_status": shipment.customs_status,
        "customs_number": shipment.customs_number,
        "shipped_date": shipment.shipped_date.isoformat() if shipment.shipped_date else None,
        "arrival_date": shipment.arrival_date.isoformat() if shipment.arrival_date else None
    } for shipment in active_shipments]
    
    return {
        "is_new_customer": False,
        "customer": customer_data,
        "cs_records": cs_records_data,
        "purchases": purchases_data,
        "active_shipments": shipments_data,
        "total_cs_count": len(cs_records),
        "total_purchase_count": len(purchases)
    }

@router.post("/create-customer")
async def create_customer(
    name: str = Form(...),
    phone: str = Form(...),
    email: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    memo: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """새 고객 생성"""
    # 전화번호 정규화
    normalized_phone = phone.replace("-", "").replace(" ", "")
    
    # 중복 확인
    existing = db.query(Customer).filter(
        Customer.phone == normalized_phone
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 전화번호입니다")
    
    new_customer = Customer(
        name=name,
        phone=normalized_phone,
        email=email,
        address=address,
        memo=memo
    )
    
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    
    return {"success": True, "customer_id": new_customer.id}

@router.post("/create-cs-record")
async def create_cs_record(
    customer_id: int = Form(...),
    product_id: Optional[int] = Form(None),
    cs_type: str = Form(...),
    cs_content: str = Form(...),
    marketplace: Optional[str] = Form(None),
    order_number: Optional[str] = Form(None),
    taobao_order_number: Optional[str] = Form(None),
    proxy_application_number: Optional[str] = Form(None),
    tracking_number: Optional[str] = Form(None),
    priority: str = Form("일반"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """CS 기록 생성"""
    new_record = CSRecord(
        customer_id=customer_id,
        product_id=product_id,
        cs_type=cs_type,
        cs_content=cs_content,
        cs_status="진행중",
        handler_id=current_user.id,
        handler_name=current_user.username,
        marketplace=marketplace,
        order_number=order_number,
        taobao_order_number=taobao_order_number,
        proxy_application_number=proxy_application_number,
        tracking_number=tracking_number,
        priority=priority
    )
    
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    
    return {
        "success": True, 
        "cs_record_id": new_record.id,
        "message": "CS 기록이 저장되었습니다"
    }

@router.post("/update-cs-record/{record_id}")
async def update_cs_record(
    record_id: int,
    cs_status: Optional[str] = Form(None),
    cs_result: Optional[str] = Form(None),
    tracking_number: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """CS 기록 업데이트"""
    record = db.query(CSRecord).filter(CSRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="CS 기록을 찾을 수 없습니다")
    
    if cs_status:
        record.cs_status = cs_status
    if cs_result:
        record.cs_result = cs_result
    if tracking_number:
        record.tracking_number = tracking_number
    
    record.updated_at = datetime.now()
    db.commit()
    
    return {"success": True, "message": "CS 기록이 업데이트되었습니다"}

@router.get("/shipment-tracking/{tracking_number}")
async def track_shipment(
    tracking_number: str,
    db: Session = Depends(get_db)
):
    """송장번호로 배송 추적"""
    shipment = db.query(Shipment).filter(
        or_(
            Shipment.domestic_tracking == tracking_number,
            Shipment.international_tracking == tracking_number
        )
    ).first()
    
    if not shipment:
        return {"found": False, "message": "배송 정보를 찾을 수 없습니다"}
    
    return {
        "found": True,
        "shipment": {
            "id": shipment.id,
            "customer_name": shipment.customer.name if shipment.customer else None,
            "proxy_company": shipment.proxy_company,
            "domestic_tracking": shipment.domestic_tracking,
            "domestic_status": shipment.domestic_status,
            "international_tracking": shipment.international_tracking,
            "international_status": shipment.international_status,
            "customs_status": shipment.customs_status,
            "customs_number": shipment.customs_number,
            "shipped_date": shipment.shipped_date.isoformat() if shipment.shipped_date else None,
            "arrival_date": shipment.arrival_date.isoformat() if shipment.arrival_date else None,
            "delivered_date": shipment.delivered_date.isoformat() if shipment.delivered_date else None
        }
    }

@router.get("/customs-check/{customs_number}")
async def check_customs(
    customs_number: str,
    db: Session = Depends(get_db)
):
    """통관번호로 통관 상태 확인"""
    shipment = db.query(Shipment).filter(
        Shipment.customs_number == customs_number
    ).first()
    
    if not shipment:
        return {"found": False, "message": "통관 정보를 찾을 수 없습니다"}
    
    return {
        "found": True,
        "customs": {
            "customs_number": shipment.customs_number,
            "customs_status": shipment.customs_status,
            "customs_date": shipment.customs_date.isoformat() if shipment.customs_date else None,
            "customs_issue": shipment.customs_issue,
            "customs_fee": shipment.customs_fee,
            "customer_name": shipment.customer.name if shipment.customer else None,
            "tracking_number": shipment.domestic_tracking
        }
    }

@router.get("/cs-history/{customer_id}")
async def get_cs_history(
    customer_id: int,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """고객의 전체 CS 이력 조회"""
    records = db.query(CSRecord).filter(
        CSRecord.customer_id == customer_id
    ).order_by(CSRecord.created_at.desc()).limit(limit).all()
    
    return {
        "customer_id": customer_id,
        "total_count": len(records),
        "records": [{
            "id": r.id,
            "cs_type": r.cs_type,
            "cs_status": r.cs_status,
            "cs_content": r.cs_content,
            "cs_result": r.cs_result,
            "handler_name": r.handler_name,
            "priority": r.priority,
            "created_at": r.created_at.isoformat() if r.created_at else None
        } for r in records]
    }

@router.get("/statistics")
async def get_cs_statistics(
    db: Session = Depends(get_db)
):
    """CS 통계 조회"""
    # 이번 달 통계
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    
    monthly_cs = db.query(CSRecord).filter(
        CSRecord.created_at >= start_of_month
    ).count()
    
    # CS 유형별 통계
    cs_by_type = db.query(
        CSRecord.cs_type,
        func.count(CSRecord.id).label('count')
    ).group_by(CSRecord.cs_type).all()
    
    # 담당자별 통계
    cs_by_handler = db.query(
        CSRecord.handler_name,
        func.count(CSRecord.id).label('count')
    ).filter(
        CSRecord.created_at >= start_of_month
    ).group_by(CSRecord.handler_name).all()
    
    # 평균 처리 시간 (완료된 건만)
    completed_cs = db.query(CSRecord).filter(
        CSRecord.cs_status == "완료",
        CSRecord.created_at >= start_of_month
    ).all()
    
    avg_resolution_time = None
    if completed_cs:
        total_time = sum([
            (cs.updated_at - cs.created_at).total_seconds() / 3600
            for cs in completed_cs if cs.updated_at
        ])
        avg_resolution_time = total_time / len(completed_cs)
    
    return {
        "monthly_total": monthly_cs,
        "by_type": {t: c for t, c in cs_by_type},
        "by_handler": {h: c for h, c in cs_by_handler if h},
        "avg_resolution_hours": round(avg_resolution_time, 1) if avg_resolution_time else None
    }