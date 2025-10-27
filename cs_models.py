# cs_models.py - CS 관리를 위한 추가 모델

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Customer(Base):
    """고객 정보"""
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=False)  # 전화번호로 조회
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    memo = Column(Text, nullable=True)  # 고객 메모
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 관계 설정
    cs_records = relationship("CSRecord", back_populates="customer", order_by="CSRecord.created_at.desc()")
    purchases = relationship("CustomerPurchase", back_populates="customer")
    shipments = relationship("Shipment", back_populates="customer")

class CSRecord(Base):
    """CS 상담 기록"""
    __tablename__ = "cs_records"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    
    # CS 정보
    cs_type = Column(String(50))  # 문의유형: 배송, 교환, 환불, 일반문의 등
    cs_status = Column(String(50), default="진행중")  # 진행중, 완료, 보류
    cs_content = Column(Text, nullable=False)  # 상담 내용
    cs_result = Column(Text, nullable=True)  # 처리 결과
    
    # 담당자 정보
    handler_id = Column(Integer, ForeignKey("users.id"))  # 응대한 직원
    handler_name = Column(String(100))  # 담당자 이름 (빠른 조회용)
    
    # 주문/배송 정보
    marketplace = Column(String(50))  # 구매처: 쿠팡, 네이버, 타오바오 등
    order_number = Column(String(100))  # 마켓 주문번호
    taobao_order_number = Column(String(100))  # 타오바오 주문번호
    proxy_application_number = Column(String(100))  # 배송대행지 신청서 번호
    tracking_number = Column(String(100))  # 송장번호
    
    # 추가 정보
    attachments = Column(JSON)  # 첨부파일 경로들
    tags = Column(JSON)  # 태그들
    priority = Column(String(20), default="일반")  # 긴급, 중요, 일반
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 관계 설정
    customer = relationship("Customer", back_populates="cs_records")
    product = relationship("Product")
    handler = relationship("User")

class CustomerPurchase(Base):
    """고객 구매 이력"""
    __tablename__ = "customer_purchases"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    # 구매 정보
    marketplace = Column(String(50))  # 구매처
    order_number = Column(String(100))  # 주문번호
    purchase_date = Column(DateTime)  # 구매일
    quantity = Column(Integer, default=1)
    price = Column(Float)
    status = Column(String(50))  # 주문완료, 배송중, 배송완료 등
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 관계 설정
    customer = relationship("Customer", back_populates="purchases")
    product = relationship("Product")
    order = relationship("Order")

class Shipment(Base):
    """배송/통관 정보"""
    __tablename__ = "shipments"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    # 배송 정보
    proxy_company = Column(String(100))  # 배송대행지
    proxy_application_number = Column(String(100))  # 신청서 번호
    taobao_order_number = Column(String(100))  # 타오바오 주문번호
    
    # 국내 배송
    domestic_tracking = Column(String(100))  # 국내 송장번호
    domestic_carrier = Column(String(50))  # 국내 택배사
    domestic_status = Column(String(50))  # 국내 배송 상태
    
    # 국제 배송
    international_tracking = Column(String(100))  # 국제 송장번호
    international_carrier = Column(String(50))  # 국제 운송사
    international_status = Column(String(50))  # 국제 배송 상태
    
    # 통관 정보
    customs_status = Column(String(50))  # 통관 상태: 대기, 진행중, 완료, 보류
    customs_number = Column(String(100))  # 통관번호
    customs_date = Column(DateTime)  # 통관일
    customs_issue = Column(Text)  # 통관 이슈
    
    # 날짜 정보
    order_date = Column(DateTime)  # 주문일
    shipped_date = Column(DateTime)  # 발송일
    arrival_date = Column(DateTime)  # 도착예정일
    delivered_date = Column(DateTime)  # 배송완료일
    
    # 추가 정보
    weight = Column(Float)  # 무게(kg)
    shipping_fee = Column(Float)  # 배송비
    customs_fee = Column(Float)  # 관세
    status_log = Column(JSON)  # 상태 변경 로그
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 관계 설정
    customer = relationship("Customer", back_populates="shipments")
    order = relationship("Order")