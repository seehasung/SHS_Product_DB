import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from passlib.hash import bcrypt
import datetime

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수가 설정되지 않았습니다.")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# --- 기존 User, Product 모델 (변경 없음) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False)
    can_manage_products = Column(Boolean, default=False)
    can_manage_marketing = Column(Boolean, default=False)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String, unique=True, index=True, nullable=True)
    name = Column(String(255), nullable=False)
    price = Column(Integer, nullable=True)
    kd_paid = Column(Boolean, default=False)
    customs_paid = Column(Boolean, default=False)
    customs_cost = Column(Integer, default=0)
    coupang_link = Column(String(2083), nullable=True)
    taobao_link = Column(String(2083), nullable=True)
    coupang_options = Column(Text, nullable=True)
    taobao_options = Column(Text, nullable=True)
    thumbnail = Column(String(2083), nullable=True)
    details = Column(Text, nullable=True)

# --- ▼▼▼ 신규 및 수정된 마케팅 모델 ▼▼▼ ---

class MarketingAccount(Base):
    __tablename__ = "marketing_accounts"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default="Naver")
    account_id = Column(String, unique=True, index=True)
    account_pw = Column(String)
    ip_address = Column(String, nullable=True)

class TargetCafe(Base):
    __tablename__ = "target_cafes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    # is_suspended 필드는 CafeMembership으로 이동

# CafeMembership: 계정과 카페의 다대다 관계를 위한 연결 테이블
class CafeMembership(Base):
    __tablename__ = "cafe_memberships"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id"))
    cafe_id = Column(Integer, ForeignKey("target_cafes.id"))
    is_suspended = Column(Boolean, default=False)
    new_post_count = Column(Integer, default=0)
    edited_post_count = Column(Integer, default=0)
    
    account = relationship("MarketingAccount")
    cafe = relationship("TargetCafe")

class MarketingProduct(Base):
    __tablename__ = "marketing_products"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    keywords = Column(Text)
    product = relationship("Product")

class Reference(Base):
    __tablename__ = "references"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    ref_type = Column(String)

class PostLog(Base):
    __tablename__ = "post_logs"
    id = Column(Integer, primary_key=True, index=True)
    posted_at = Column(DateTime, default=datetime.datetime.utcnow)
    post_url = Column(String, nullable=True)
    status = Column(String)
    
    membership_id = Column(Integer, ForeignKey("cafe_memberships.id")) # CafeMembership과 연결
    keyword_used = Column(String)
    reference_id = Column(Integer, ForeignKey("references.id"))
    worker_id = Column(Integer, ForeignKey("users.id"))
    
    membership = relationship("CafeMembership")
    reference = relationship("Reference")
    worker = relationship("User")

# --- ▲▲▲ 신규 및 수정된 마케팅 모델 ▲▲▲ ---

__all__ = [
    "User", "Product", "MarketingAccount", "TargetCafe", "CafeMembership",
    "MarketingProduct", "Reference", "PostLog", "SessionLocal", "Base"
]

