# database.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime

# SQLite 데이터베이스 설정
SQLALCHEMY_DATABASE_URL = "sqlite:///./shs_corp.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 사용자 모델
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    password = Column(String(255))
    is_admin = Column(Boolean, default=False)
    can_manage_products = Column(Boolean, default=False)
    can_manage_marketing = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 상품 모델 - 네이버 링크 추가!
class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String(100), unique=True, index=True, nullable=True)
    name = Column(String(255), nullable=False)
    price = Column(Integer, nullable=True)
    
    # 결제 상태
    kd_paid = Column(Boolean, default=False)
    customs_paid = Column(Boolean, default=False)
    customs_cost = Column(Integer, default=0)
    
    # 쇼핑몰 링크들 - 네이버 추가!
    coupang_link = Column(String(2083), nullable=True)
    taobao_link = Column(String(2083), nullable=True)
    naver_link = Column(String(2083), nullable=True)  # ⭐ 새로 추가!
    
    # 옵션 정보
    coupang_options = Column(Text, nullable=True)
    taobao_options = Column(Text, nullable=True)
    naver_options = Column(Text, nullable=True)  # ⭐ 새로 추가!
    
    # 이미지 및 상세 정보
    thumbnail = Column(String(2083), nullable=True)
    details = Column(Text, nullable=True)
    
    # 추가 필드
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# 문의 모델
class Inquiry(Base):
    __tablename__ = "inquiries"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100))
    contact = Column(String(100))
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    inquiry_type = Column(String(50))  # 구매문의, 배송문의, 환불문의 등
    content = Column(Text)
    status = Column(String(20), default="pending")  # pending, processing, completed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 관계 설정
    product = relationship("Product", backref="inquiries")

# 마케팅 자료 모델
class MarketingMaterial(Base):
    __tablename__ = "marketing_materials"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    content = Column(Text)
    material_type = Column(String(50))  # blog, social, email 등
    tags = Column(String(500))  # 쉼표로 구분된 태그
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# 테이블 생성
Base.metadata.create_all(bind=engine)

# 의존성 주입용 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()