import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, DateTime, Date, UniqueConstraint
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

# === 기존 모델들 ===

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False)
    can_manage_products = Column(Boolean, default=False)
    can_manage_marketing = Column(Boolean, default=False)
    daily_quota = Column(Integer, default=0)  # 일일 할당량 필드
    
    # 관계 추가
    schedules = relationship("PostSchedule", back_populates="worker")
    marketing_posts = relationship("MarketingPost", back_populates="worker")
    work_tasks = relationship("WorkTask", back_populates="worker")
    post_logs = relationship("PostLog", back_populates="worker")
    references_modified = relationship("Reference", back_populates="last_modified_by")

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
    
    # 관계 추가
    marketing_products = relationship("MarketingProduct", back_populates="product")

class MarketingAccount(Base):
    __tablename__ = "marketing_accounts"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default="Naver")
    account_id = Column(String, unique=True, index=True)
    account_pw = Column(String)
    ip_address = Column(String, nullable=True)
    category = Column(String, nullable=False, server_default='최적화')
    
    # 관계 추가
    memberships = relationship("CafeMembership", back_populates="account")
    schedules = relationship("PostSchedule", back_populates="account")
    marketing_posts = relationship("MarketingPost", back_populates="account")
    work_tasks = relationship("WorkTask", back_populates="account")
    usages = relationship("AccountCafeUsage", back_populates="account")

class TargetCafe(Base):
    __tablename__ = "target_cafes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    
    # 관계 추가
    memberships = relationship("CafeMembership", back_populates="cafe")
    schedules = relationship("PostSchedule", back_populates="cafe")
    marketing_posts = relationship("MarketingPost", back_populates="cafe")
    work_tasks = relationship("WorkTask", back_populates="cafe")
    usages = relationship("AccountCafeUsage", back_populates="cafe")

class CafeMembership(Base):
    __tablename__ = "cafe_memberships"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id", ondelete="CASCADE"))
    cafe_id = Column(Integer, ForeignKey("target_cafes.id", ondelete="CASCADE"))
    status = Column(String, default="active")
    new_post_count = Column(Integer, default=0)
    edited_post_count = Column(Integer, default=0)
    
    # 관계
    account = relationship("MarketingAccount", back_populates="memberships")
    cafe = relationship("TargetCafe", back_populates="memberships")
    post_logs = relationship("PostLog", back_populates="membership")

class MarketingProduct(Base):
    __tablename__ = "marketing_products"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    keywords = Column(Text, nullable=True)  # 키워드 목록 (JSON)
    
    # 관계
    product = relationship("Product", back_populates="marketing_products")
    posts = relationship("MarketingPost", back_populates="marketing_product", cascade="all, delete-orphan")
    tasks = relationship("WorkTask", back_populates="marketing_product", cascade="all, delete-orphan")
    schedules = relationship("PostSchedule", back_populates="marketing_product")
    usages = relationship("AccountCafeUsage", back_populates="marketing_product")
    rounds = relationship("PostingRound", back_populates="marketing_product")

class Reference(Base):
    __tablename__ = "references"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, unique=True, index=True)
    content = Column(Text, nullable=True)
    ref_type = Column(String, default="기타")
    last_modified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 관계
    last_modified_by = relationship("User", back_populates="references_modified")
    comments = relationship("Comment", back_populates="reference", cascade="all, delete-orphan")
    post_logs = relationship("PostLog", back_populates="reference")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    account_sequence = Column(Integer, nullable=False, server_default='0')
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    reference_id = Column(Integer, ForeignKey("references.id", ondelete="CASCADE"))
    parent_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    
    # 관계
    reference = relationship("Reference", back_populates="comments")
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")

class WorkTask(Base):
    __tablename__ = "work_tasks"
    id = Column(Integer, primary_key=True, index=True)
    task_date = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="todo")
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    marketing_product_id = Column(Integer, ForeignKey("marketing_products.id", ondelete="CASCADE"))
    keyword_text = Column(String)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id", ondelete="SET NULL"), nullable=True)
    cafe_id = Column(Integer, ForeignKey("target_cafes.id", ondelete="SET NULL"), nullable=True)
    completed_post_id = Column(Integer, ForeignKey("marketing_posts.id", ondelete="SET NULL"), nullable=True)
    
    # 관계
    worker = relationship("User", back_populates="work_tasks")
    marketing_product = relationship("MarketingProduct", back_populates="tasks")
    account = relationship("MarketingAccount", back_populates="work_tasks")
    cafe = relationship("TargetCafe", back_populates="work_tasks")
    completed_post = relationship("MarketingPost", foreign_keys=[completed_post_id])

class MarketingPost(Base):
    __tablename__ = "marketing_posts"
    id = Column(Integer, primary_key=True, index=True)
    post_title = Column(Text, nullable=True)
    post_body = Column(Text, nullable=True)
    post_comments = Column(Text, nullable=True)
    is_registration_complete = Column(Boolean, default=False)
    post_url = Column(String, nullable=True)
    keyword_text = Column(String, index=True)
    is_live = Column(Boolean, default=True)
    marketing_product_id = Column(Integer, ForeignKey("marketing_products.id", ondelete="CASCADE"))
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id", ondelete="SET NULL"), nullable=True)
    cafe_id = Column(Integer, ForeignKey("target_cafes.id", ondelete="SET NULL"), nullable=True)
    
    # ⭐ created_at 필드 추가 (통계를 위해 필요!)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 통계 필드 추가 (선택사항)
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # 관계
    marketing_product = relationship("MarketingProduct", back_populates="posts")
    worker = relationship("User", back_populates="marketing_posts")
    account = relationship("MarketingAccount", back_populates="marketing_posts")
    cafe = relationship("TargetCafe", back_populates="marketing_posts")
    schedules = relationship("PostSchedule", back_populates="marketing_post")
    work_tasks = relationship("WorkTask", foreign_keys="WorkTask.completed_post_id", overlaps="completed_post")

class PostLog(Base):
    __tablename__ = "post_logs"
    id = Column(Integer, primary_key=True, index=True)
    posted_at = Column(DateTime, default=datetime.datetime.utcnow)
    post_url = Column(String, nullable=True)
    status = Column(String)
    membership_id = Column(Integer, ForeignKey("cafe_memberships.id", ondelete="CASCADE"))
    keyword_used = Column(String)
    reference_id = Column(Integer, ForeignKey("references.id"))
    worker_id = Column(Integer, ForeignKey("users.id"))
    
    # 관계
    membership = relationship("CafeMembership", back_populates="post_logs")
    reference = relationship("Reference", back_populates="post_logs")
    worker = relationship("User", back_populates="post_logs")

# === 스케줄 관련 모델들 ===

class PostSchedule(Base):
    """날짜별 글 작성 스케줄 테이블"""
    __tablename__ = "post_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    scheduled_date = Column(Date, nullable=False, index=True)
    
    # 할당 정보
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id", ondelete="SET NULL"), nullable=True)
    cafe_id = Column(Integer, ForeignKey("target_cafes.id", ondelete="SET NULL"), nullable=True)
    marketing_product_id = Column(Integer, ForeignKey("marketing_products.id", ondelete="CASCADE"))
    keyword_text = Column(String, nullable=False)
    
    # 상태 관리
    status = Column(String, default="pending")  # pending, in_progress, completed, skipped
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    marketing_post_id = Column(Integer, ForeignKey("marketing_posts.id", ondelete="SET NULL"), nullable=True)
    
    # 메모
    notes = Column(Text, nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # 관계 설정
    worker = relationship("User", back_populates="schedules")
    account = relationship("MarketingAccount", back_populates="schedules")
    cafe = relationship("TargetCafe", back_populates="schedules")
    marketing_product = relationship("MarketingProduct", back_populates="schedules")
    marketing_post = relationship("MarketingPost", back_populates="schedules")

class AccountCafeUsage(Base):
    """계정-카페-키워드별 사용 횟수 추적"""
    __tablename__ = "account_cafe_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id"))
    cafe_id = Column(Integer, ForeignKey("target_cafes.id"))
    keyword_text = Column(String, index=True)
    marketing_product_id = Column(Integer, ForeignKey("marketing_products.id"))
    usage_count = Column(Integer, default=0)  # 사용 횟수 (최대 2)
    last_used_date = Column(Date, nullable=True)
    
    # 관계
    account = relationship("MarketingAccount", back_populates="usages")
    cafe = relationship("TargetCafe", back_populates="usages")
    marketing_product = relationship("MarketingProduct", back_populates="usages")
    
    __table_args__ = (
        UniqueConstraint('account_id', 'cafe_id', 'keyword_text', 'marketing_product_id'),
    )

class PostingRound(Base):
    """글 작성 라운드 관리 (1회전, 2회전 추적)"""
    __tablename__ = "posting_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    marketing_product_id = Column(Integer, ForeignKey("marketing_products.id"))
    round_number = Column(Integer, default=1)  # 현재 라운드 (1 or 2)
    current_keyword_index = Column(Integer, default=0)  # 현재 진행중인 키워드 인덱스
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # 관계
    marketing_product = relationship("MarketingProduct", back_populates="rounds")

# __all__ 리스트 업데이트
__all__ = [
    "User", "Product", "MarketingAccount", "TargetCafe", "CafeMembership",
    "MarketingProduct", "Reference", "PostLog", "Comment", "MarketingPost",
    "WorkTask", "PostSchedule", "AccountCafeUsage", "PostingRound",
    "SessionLocal", "Base", "engine"
]