#database.py
 
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, DateTime, Date, UniqueConstraint, Float, JSON, Index, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.declarative import declarative_base
from passlib.hash import bcrypt
from datetime import datetime, date, timedelta, timezone
import pytz
import math

KST = pytz.timezone('Asia/Seoul')

# 한국 시간 반환 함수
def get_kst_now():
    """현재 한국 시간 반환"""
    return datetime.now(KST) 

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
    can_manage_orders = Column(Boolean, default=False)  # ⭐ 추가
    daily_quota = Column(Integer, default=0)  # 일일 할당량 필드
    
    
    # 관계 추가
    schedules = relationship("PostSchedule", back_populates="worker")
    marketing_posts = relationship("MarketingPost", back_populates="worker")
    work_tasks = relationship("WorkTask", back_populates="worker")
    post_logs = relationship("PostLog", back_populates="worker")
    references_modified = relationship("Reference", back_populates="last_modified_by")
    login_logs = relationship("LoginLog", back_populates="user")
    blog_worker = relationship("BlogWorker", back_populates="user", uselist=False)
    homepage_worker = relationship("HomepageWorker", back_populates="user", uselist=False)
    
    
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
    naver_link = Column(String(2083), nullable=True)  # ⭐ 새로 추가!
    taobao_link = Column(String(2083), nullable=True)
    coupang_options = Column(Text, nullable=True)
    taobao_options = Column(Text, nullable=True)
    naver_options = Column(Text, nullable=True)  # ⭐ 새로 추가!
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
    created_at = Column(DateTime, default=get_kst_now)
    reference_id = Column(Integer, ForeignKey("references.id", ondelete="CASCADE"))
    parent_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    
    # 관계
    reference = relationship("Reference", back_populates="comments")
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")

class WorkTask(Base):
    __tablename__ = "work_tasks"
    id = Column(Integer, primary_key=True, index=True)
    task_date = Column(DateTime, default=get_kst_now)
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
    is_live = Column(Boolean, default=False)
    marketing_product_id = Column(Integer, ForeignKey("marketing_products.id", ondelete="CASCADE"))
    worker_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("marketing_accounts.id", ondelete="SET NULL"), nullable=True)
    cafe_id = Column(Integer, ForeignKey("target_cafes.id", ondelete="SET NULL"), nullable=True)
    
    # ⭐ created_at 필드 추가 (통계를 위해 필요!)
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
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
    posted_at = Column(DateTime, default=get_kst_now)
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
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
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
    created_at = Column(DateTime, default=get_kst_now)
    
    # 관계
    marketing_product = relationship("MarketingProduct", back_populates="rounds")


class LoginLog(Base):
    """로그인 기록 테이블"""
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    login_time = Column(DateTime, default=get_kst_now)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    success = Column(Boolean, default=True)  # 로그인 성공 여부
    
    # 관계
    user = relationship("User", back_populates="login_logs")
    
class TaskAssignment(Base):
    """업무 지시 테이블"""
    __tablename__ = "task_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 지시 정보
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    
    # 사용자 정보
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # 지시자
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # 담당자
    
    # 우선순위 및 마감
    priority = Column(String(20), default="normal")  # urgent, important, normal
    deadline_type = Column(String(50), nullable=True)  # 2시간 내, 오늘 중, 이번 주, 직접입력
    deadline = Column(DateTime(timezone=True), nullable=True)
    
    # 상태 관리 (6단계)
    status = Column(String(20), default="new")  # new, confirmed, in_progress, completed, on_hold, cancelled
    
    # 상태별 추가 정보
    estimated_completion_time = Column(DateTime, nullable=True)  # 진행중일 때 예상 완료 시간
    completion_note = Column(Text, nullable=True)  # 완료 시 결과 내용
    hold_reason = Column(Text, nullable=True)  # 보류 사유
    hold_resume_date = Column(Date, nullable=True)  # 보류 후 재개 예정일
    cancel_reason = Column(Text, nullable=True)  # 취소 사유
    
    # 일괄 지시 여부
    is_batch = Column(Boolean, default=False)
    batch_group_id = Column(String(50), nullable=True)  # 같은 일괄 지시는 같은 ID
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 읽음 여부
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    
    # 관계 설정
    creator = relationship("User", foreign_keys=[creator_id], backref="created_tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], backref="assigned_tasks")
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    files = relationship("TaskFile", back_populates="task", cascade="all, delete-orphan")
    notifications = relationship("TaskNotification", back_populates="task", cascade="all, delete-orphan")


class TaskComment(Base):
    """업무 지시 댓글 테이블"""
    __tablename__ = "task_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    
    # 읽음 여부 (수신자가 읽었는지)
    is_read = Column(Boolean, default=False)
    
    # 관계
    task = relationship("TaskAssignment", back_populates="comments")
    user = relationship("User", backref="task_comments")
    files = relationship("TaskFile", back_populates="comment", cascade="all, delete-orphan")


class TaskFile(Base):
    """업무 지시 첨부파일 테이블"""
    __tablename__ = "task_files"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(Integer, ForeignKey("task_comments.id", ondelete="CASCADE"), nullable=True)
    
    filename = Column(String(500), nullable=False)
    filepath = Column(String(1000), nullable=False)
    filesize = Column(Integer, nullable=True)  # bytes
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    
    # 관계
    task = relationship("TaskAssignment", back_populates="files")
    comment = relationship("TaskComment", back_populates="files")
    uploader = relationship("User", backref="uploaded_task_files")


class TaskNotification(Base):
    """업무 지시 알림 로그 테이블 (3개월 보관)"""
    __tablename__ = "task_notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    notification_type = Column(String(50), nullable=False)  # new_task, comment, deadline_warning, status_change
    message = Column(Text, nullable=False)
    
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    auto_delete_at = Column(DateTime(timezone=True), nullable=True)
    
    # 관계
    task = relationship("TaskAssignment", back_populates="notifications")
    user = relationship("User", backref="task_notifications")



# ============================================
# database.py - 블로그/통페이지 모델 전체 수정
# ============================================
# 기존의 BlogWorker부터 HomepagePostSchedule까지 전체를 이 코드로 교체하세요

# ============================================
# 블로그 마케팅 시스템 모델
# ============================================

class BlogWorker(Base):
    """블로그 작업자 (사이트 회원 중 블로그 작업 권한을 가진 사람)"""
    __tablename__ = 'blog_workers'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    status = Column(String, default='active')  # active, inactive, suspended
    daily_quota = Column(Integer, default=3)  # 일일 작업량
    current_product_id = Column(Integer, ForeignKey('marketing_products.id'))  # 현재 진행 중인 상품
    is_blog_manager = Column(Boolean, default=False)  # 블로그 관리자 여부
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="blog_worker")  # ⭐ 수정!
    current_product = relationship("MarketingProduct", foreign_keys=[current_product_id])
    blog_accounts = relationship("BlogAccount", back_populates="assigned_worker")
    blog_posts = relationship("BlogPost", back_populates="worker")
    blog_tasks = relationship("BlogWorkTask", back_populates="worker")
    keyword_progress = relationship("BlogKeywordProgress", back_populates="worker")
    
    @property
    def required_accounts(self):
        """필요한 블로그 계정 수 계산 (하루 최대 3개씩)"""
        return math.ceil(self.daily_quota / 3)


class BlogAccount(Base):
    """블로그 계정 (네이버 블로그)"""
    __tablename__ = 'blog_accounts'
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default='naver_blog')
    account_id = Column(String, unique=True, nullable=False)
    account_pw = Column(String, nullable=False)
    blog_url = Column(String)
    ip_address = Column(String)
    category = Column(String)
    assigned_worker_id = Column(Integer, ForeignKey('blog_workers.id'))
    assignment_order = Column(Integer)
    daily_post_limit = Column(Integer, default=3)
    status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    assigned_worker = relationship("BlogWorker", back_populates="blog_accounts")
    blog_posts = relationship("BlogPost", back_populates="blog_account")
    blog_tasks = relationship("BlogWorkTask", back_populates="blog_account")


class BlogProductKeyword(Base):
    """블로그용 상품 키워드 ON/OFF 관리"""
    __tablename__ = 'blog_product_keywords'
    
    id = Column(Integer, primary_key=True, index=True)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    marketing_product = relationship("MarketingProduct", backref="blog_keywords")


class BlogPost(Base):
    """블로그 글"""
    __tablename__ = 'blog_posts'
    
    id = Column(Integer, primary_key=True, index=True)
    post_title = Column(String, nullable=False)
    post_body = Column(Text, nullable=False)
    keyword_text = Column(String, nullable=False)
    post_url = Column(String)
    
    char_count = Column(Integer, default=0)
    image_count = Column(Integer, default=0)
    keyword_count = Column(Integer, default=0)
    
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    worker_id = Column(Integer, ForeignKey('blog_workers.id'), nullable=False)
    blog_account_id = Column(Integer, ForeignKey('blog_accounts.id'), nullable=False)
    
    is_registration_complete = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    marketing_product = relationship("MarketingProduct", backref="blog_posts")
    worker = relationship("BlogWorker", back_populates="blog_posts")
    blog_account = relationship("BlogAccount", back_populates="blog_posts")
    images = relationship("BlogPostImage", back_populates="blog_post", cascade="all, delete-orphan")


class BlogPostImage(Base):
    """블로그 글 이미지"""
    __tablename__ = 'blog_post_images'
    
    id = Column(Integer, primary_key=True, index=True)
    blog_post_id = Column(Integer, ForeignKey('blog_posts.id'), nullable=False)
    image_path = Column(String, nullable=False)
    image_filename = Column(String, nullable=False)
    image_order = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    blog_post = relationship("BlogPost", back_populates="images")


class BlogKeywordProgress(Base):
    """작업자별 키워드 진행 상황"""
    __tablename__ = 'blog_keyword_progress'
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('blog_workers.id'), nullable=False)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_post_id = Column(Integer, ForeignKey('blog_posts.id'))
    completed_at = Column(DateTime)
    
    # Relationships
    worker = relationship("BlogWorker", back_populates="keyword_progress")
    marketing_product = relationship("MarketingProduct", backref="blog_keyword_progress")
    completed_post = relationship("BlogPost", foreign_keys=[completed_post_id])


class BlogWorkTask(Base):
    """블로그 일일 작업 할당"""
    __tablename__ = 'blog_work_tasks'
    
    id = Column(Integer, primary_key=True, index=True)
    task_date = Column(Date, nullable=False)
    status = Column(String, default='pending')
    keyword_text = Column(String, nullable=False)
    
    worker_id = Column(Integer, ForeignKey('blog_workers.id'), nullable=False)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    blog_account_id = Column(Integer, ForeignKey('blog_accounts.id'), nullable=False)
    completed_post_id = Column(Integer, ForeignKey('blog_posts.id'))
    
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)
    
    # Relationships
    worker = relationship("BlogWorker", back_populates="blog_tasks")
    marketing_product = relationship("MarketingProduct", backref="blog_work_tasks")
    blog_account = relationship("BlogAccount", back_populates="blog_tasks")
    completed_post = relationship("BlogPost", foreign_keys=[completed_post_id])


class BlogPostSchedule(Base):
    """블로그 포스트 스케줄 (관리자용)"""
    __tablename__ = 'blog_post_schedules'
    
    id = Column(Integer, primary_key=True, index=True)
    scheduled_date = Column(Date, nullable=False)
    status = Column(String, default='pending')
    
    worker_id = Column(Integer, ForeignKey('blog_workers.id'), nullable=False)
    blog_account_id = Column(Integer, ForeignKey('blog_accounts.id'), nullable=False)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    blog_post_id = Column(Integer, ForeignKey('blog_posts.id'))
    
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    worker = relationship("BlogWorker", foreign_keys=[worker_id])
    blog_account = relationship("BlogAccount", foreign_keys=[blog_account_id])
    marketing_product = relationship("MarketingProduct", foreign_keys=[marketing_product_id])
    blog_post = relationship("BlogPost", foreign_keys=[blog_post_id])


# ============================================
# 통페이지 마케팅 시스템 모델
# ============================================

class HomepageWorker(Base):
    """통페이지 작업자 (사이트 회원 중 통페이지 작업 권한을 가진 사람)"""
    __tablename__ = 'homepage_workers'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    status = Column(String, default='active')
    daily_quota = Column(Integer, default=3)
    current_product_id = Column(Integer, ForeignKey('marketing_products.id'))
    is_homepage_manager = Column(Boolean, default=False)  # ⭐ 수정!
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="homepage_worker")  # ⭐ 수정!
    current_product = relationship("MarketingProduct", foreign_keys=[current_product_id])
    homepage_accounts = relationship("HomepageAccount", back_populates="assigned_worker")
    homepage_posts = relationship("HomepagePost", back_populates="worker")
    homepage_tasks = relationship("HomepageWorkTask", back_populates="worker")
    keyword_progress = relationship("HomepageKeywordProgress", back_populates="worker")
    
    @property
    def required_accounts(self):
        """필요한 통페이지 계정 수 계산 (하루 최대 3개씩)"""
        return math.ceil(self.daily_quota / 3)


class HomepageAccount(Base):
    """통페이지 계정 (네이버 블로그)"""
    __tablename__ = 'homepage_accounts'
    
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default='naver_blog')
    account_id = Column(String, unique=True, nullable=False)
    account_pw = Column(String, nullable=False)
    blog_url = Column(String)
    ip_address = Column(String)
    category = Column(String)
    assigned_worker_id = Column(Integer, ForeignKey('homepage_workers.id'))  # ⭐ 수정!
    assignment_order = Column(Integer)
    daily_post_limit = Column(Integer, default=3)
    status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    assigned_worker = relationship("HomepageWorker", back_populates="homepage_accounts")
    homepage_posts = relationship("HomepagePost", back_populates="homepage_account")
    homepage_tasks = relationship("HomepageWorkTask", back_populates="homepage_account")


class HomepageProductKeyword(Base):
    """통페이지용 상품 키워드 ON/OFF 관리"""
    __tablename__ = 'homepage_product_keywords'
    
    id = Column(Integer, primary_key=True, index=True)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    marketing_product = relationship("MarketingProduct", backref="homepage_keywords")


class HomepagePost(Base):
    """통페이지 글"""
    __tablename__ = 'homepage_posts'
    
    id = Column(Integer, primary_key=True, index=True)
    post_title = Column(String, nullable=False)
    post_body = Column(Text, nullable=False)
    keyword_text = Column(String, nullable=False)
    post_url = Column(String)
    
    char_count = Column(Integer, default=0)
    image_count = Column(Integer, default=0)
    keyword_count = Column(Integer, default=0)
    
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    worker_id = Column(Integer, ForeignKey('homepage_workers.id'), nullable=False)  # ⭐ 수정!
    homepage_account_id = Column(Integer, ForeignKey('homepage_accounts.id'), nullable=False)  # ⭐ 수정!
    
    is_registration_complete = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    marketing_product = relationship("MarketingProduct", backref="homepage_posts")
    worker = relationship("HomepageWorker", back_populates="homepage_posts")
    homepage_account = relationship("HomepageAccount", back_populates="homepage_posts")
    images = relationship("HomepagePostImage", back_populates="homepage_post", cascade="all, delete-orphan")


class HomepagePostImage(Base):
    """통페이지 글 이미지"""
    __tablename__ = 'homepage_post_images'
    
    id = Column(Integer, primary_key=True, index=True)
    homepage_post_id = Column(Integer, ForeignKey('homepage_posts.id'), nullable=False)  # ⭐ 수정!
    image_path = Column(String, nullable=False)
    image_filename = Column(String, nullable=False)
    image_order = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    homepage_post = relationship("HomepagePost", back_populates="images")


class HomepageKeywordProgress(Base):
    """작업자별 키워드 진행 상황"""
    __tablename__ = 'homepage_keyword_progress'
    
    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey('homepage_workers.id'), nullable=False)  # ⭐ 수정!
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_post_id = Column(Integer, ForeignKey('homepage_posts.id'))  # ⭐ 수정!
    completed_at = Column(DateTime)
    
    # Relationships
    worker = relationship("HomepageWorker", back_populates="keyword_progress")
    marketing_product = relationship("MarketingProduct", backref="homepage_keyword_progress")
    completed_post = relationship("HomepagePost", foreign_keys=[completed_post_id])


class HomepageWorkTask(Base):
    """통페이지 일일 작업 할당"""
    __tablename__ = 'homepage_work_tasks'
    
    id = Column(Integer, primary_key=True, index=True)
    task_date = Column(Date, nullable=False)
    status = Column(String, default='pending')
    keyword_text = Column(String, nullable=False)
    
    worker_id = Column(Integer, ForeignKey('homepage_workers.id'), nullable=False)  # ⭐ 수정!
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    homepage_account_id = Column(Integer, ForeignKey('homepage_accounts.id'), nullable=False)  # ⭐ 수정!
    completed_post_id = Column(Integer, ForeignKey('homepage_posts.id'))  # ⭐ 수정!
    
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)
    
    # Relationships
    worker = relationship("HomepageWorker", back_populates="homepage_tasks")
    marketing_product = relationship("MarketingProduct", backref="homepage_work_tasks")
    homepage_account = relationship("HomepageAccount", back_populates="homepage_tasks")
    completed_post = relationship("HomepagePost", foreign_keys=[completed_post_id])


class HomepagePostSchedule(Base):
    """통페이지 포스트 스케줄 (관리자용)"""
    __tablename__ = 'homepage_post_schedules'
    
    id = Column(Integer, primary_key=True, index=True)
    scheduled_date = Column(Date, nullable=False)
    status = Column(String, default='pending')
    
    worker_id = Column(Integer, ForeignKey('homepage_workers.id'), nullable=False)  # ⭐ 수정!
    homepage_account_id = Column(Integer, ForeignKey('homepage_accounts.id'), nullable=False)  # ⭐ 수정!
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    homepage_post_id = Column(Integer, ForeignKey('homepage_posts.id'))  # ⭐ 수정!
    
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    worker = relationship("HomepageWorker", foreign_keys=[worker_id])
    homepage_account = relationship("HomepageAccount", foreign_keys=[homepage_account_id])
    marketing_product = relationship("MarketingProduct", foreign_keys=[marketing_product_id])
    homepage_post = relationship("HomepagePost", foreign_keys=[homepage_post_id])
    
# ============================================
# 개인 메모 시스템 모델 (데일리 일지)
# ============================================

class PersonalMemo(Base):
    """개인 메모/데일리 일지 테이블"""
    __tablename__ = "personal_memos"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 메모 정보
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    
    # 작성자 (자기 자신에게 작성)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # 우선순위
    priority = Column(String(20), default="normal")  # urgent, important, normal
    
    # 상태 관리
    status = Column(String(20), default="active")  # active, completed, archived
    
    # 완료 정보
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_kst_now, onupdate=get_kst_now)
    
    # 관계 설정
    user = relationship("User", backref="personal_memos")
    files = relationship("MemoFile", back_populates="memo", cascade="all, delete-orphan")


class MemoFile(Base):
    """메모 첨부파일 테이블"""
    __tablename__ = "memo_files"
    
    id = Column(Integer, primary_key=True, index=True)
    memo_id = Column(Integer, ForeignKey("personal_memos.id", ondelete="CASCADE"), nullable=False)
    
    filename = Column(String(500), nullable=False)
    filepath = Column(String(1000), nullable=False)
    filesize = Column(Integer, nullable=True)  # bytes
    uploaded_at = Column(DateTime(timezone=True), default=get_kst_now, nullable=False)
    
    # 관계
    memo = relationship("PersonalMemo", back_populates="files")
    
class Order(Base):
    """주문 정보 테이블 (모든 필드 TEXT - 크기 제한 없음)"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # 주문 기본 정보
    # ============================================
    order_status = Column(Text, nullable=True)  # 주문상태
    order_date = Column(Text, nullable=True)  # 주문일자
    claim_date = Column(Text, nullable=True)  # 클레임일자
    claim_reason = Column(Text, nullable=True)  # 클레임사유
    
    # ============================================
    # 판매/고객 정보
    # ============================================
    sales_channel = Column(Text, nullable=True)  # 판매처/계정
    order_number = Column(Text, unique=True, index=True)  # 주문번호
    buyer_name = Column(Text, nullable=True)  # 구매자
    recipient_name = Column(Text, nullable=True)  # 수령자
    
    # ============================================
    # 배송 정보
    # ============================================
    courier_company = Column(Text, nullable=True)  # 택배사
    tracking_number = Column(Text, nullable=True)  # 송장번호
    is_kyungdong_transferred = Column(Boolean, default=False, nullable=True)  # 경동이관여부 ⭐

    # ============================================
    # 상품 정보
    # ============================================
    product_name = Column(Text, nullable=True)  # 제품명
    product_option = Column(Text, nullable=True)  # 옵션
    quantity = Column(Text, nullable=True)  # 수량
    
    # ============================================
    # 연락처/주소
    # ============================================
    contact_number = Column(Text, nullable=True)  # 연락처
    customs_number = Column(Text, nullable=True)  # 통관번호
    postal_code = Column(Text, nullable=True)  # 우편번호
    address = Column(Text, nullable=True)  # 주소
    
    # ============================================
    # 금액 정보
    # ============================================
    payment_amount = Column(Text, nullable=True)  # 결제금액
    customer_shipping_fee = Column(Text, nullable=True)  # 배송비(고객)
    market_commission = Column(Text, nullable=True)  # 마켓수수료
    settlement_amount = Column(Text, nullable=True)  # 정산예정금
    
    # ============================================
    # 타오바오 정보
    # ============================================
    taobao_order_number = Column(Text, nullable=True)  # 타바-주문번호
    taobao_yuan = Column(Text, nullable=True)  # 타바-위안
    
    # ============================================
    # ⭐ 특수 파싱 필드
    # ============================================
    order_processing_date = Column(Text, nullable=True)  # 주문처리일 (원본)
    exchange_rate = Column(Text, nullable=True)  # 환율 (파싱된 값)
    
    # ============================================
    # 비용 정보
    # ============================================
    customs_prepayment = Column(Text, nullable=True)  # 관세대납
    freight_prepayment = Column(Text, nullable=True)  # 화물대납
    warehouse_fee = Column(Text, nullable=True)  # 배대지
    profit_margin = Column(Text, nullable=True)  # 마진
    profit_margin_rate = Column(Text, nullable=True)  # 마진율
    
    # ============================================
    # 타임스탬프
    # ============================================
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # ============================================
    # 통관정보
    # ============================================
    master_bl = Column(String(100), nullable=True, index=True)  # 마스터 B/L
    house_bl = Column(String(100), nullable=True, index=True)   # 하우스 B/L
    customs_status = Column(String(50), nullable=True)          # 통관 상태
    
    
    # ============================================
    # 인덱스 (검색 성능 향상)
    # ============================================
    __table_args__ = (
        Index('idx_order_date', 'order_date'),
        Index('idx_order_status', 'order_status'),
        Index('idx_recipient_name', 'recipient_name'),
        Index('idx_kyungdong_transferred', 'is_kyungdong_transferred'),  # ⭐
    )
    
class OrderStatusMapping(Base):
    """주문 상태 매핑 테이블"""
    __tablename__ = "order_status_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    original_status = Column(String(200), unique=True, nullable=False, index=True)  # 원본 상태
    normalized_status = Column(String(50), nullable=False)  # 분류 (배송중/배송완료/취소/반품/교환/미분류)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ============================================
# 네이버 카페 자동화 시스템 모델
# ============================================

class AutomationWorkerPC(Base):
    """작업 PC 정보 (여러 대의 PC 관리)"""
    __tablename__ = "automation_worker_pcs"
    
    id = Column(Integer, primary_key=True, index=True)
    pc_number = Column(Integer, unique=True, nullable=False, index=True)  # PC 번호 (1, 2, 3...)
    pc_name = Column(String(100), nullable=False)  # PC 식별명
    ip_address = Column(String(50), nullable=False)  # IP 주소
    status = Column(String(20), default='offline')  # online, busy, offline
    current_task_id = Column(Integer, ForeignKey('automation_tasks.id'), nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)  # 마지막 통신 시간
    
    # 성능 정보
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    assigned_accounts = relationship("AutomationAccount", back_populates="assigned_pc")


class AutomationAccount(Base):
    """자동화용 네이버 계정 (사람 계정과 분리)"""
    __tablename__ = "automation_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(100), unique=True, nullable=False, index=True)
    account_pw = Column(String(255), nullable=False)
    assigned_pc_id = Column(Integer, ForeignKey('automation_worker_pcs.id'), nullable=True)
    status = Column(String(20), default='active')  # active, suspended, banned
    login_status = Column(String(20), default='logged_out')  # logged_in, logged_out, error
    
    # 사용 통계
    total_posts = Column(Integer, default=0)
    total_comments = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    assigned_pc = relationship("AutomationWorkerPC", back_populates="assigned_accounts")
    posts = relationship("AutomationPost", back_populates="account")
    tasks = relationship("AutomationTask", back_populates="assigned_account")


class AutomationCafe(Base):
    """자동화용 타겟 카페 (사람 카페와 분리)"""
    __tablename__ = "automation_cafes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), unique=True, nullable=False, index=True)
    cafe_id = Column(String(100), nullable=True)
    status = Column(String(20), default='active')
    characteristics = Column(Text, nullable=True)  # 카페 특성 (AI가 톤 맞추기용)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    tasks = relationship("AutomationTask", back_populates="cafe")
    posts = relationship("AutomationPost", back_populates="cafe")


class AutomationPrompt(Base):
    """Claude API 프롬프트 관리 (레퍼런스 대신)"""
    __tablename__ = "automation_prompts"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # 프롬프트 이름
    prompt_type = Column(String(50), nullable=False)  # post, comment, reply
    system_prompt = Column(Text, nullable=False)  # 시스템 프롬프트
    user_prompt_template = Column(Text, nullable=False)  # 사용자 프롬프트 템플릿
    
    # Claude API 설정
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=1000)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    schedules = relationship("AutomationSchedule", back_populates="prompt")


class AutomationSchedule(Base):
    """자동화 스케줄 (휴먼/AI 모드)"""
    __tablename__ = "automation_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String(20), nullable=False)  # human, ai
    
    # 스케줄 정보
    scheduled_date = Column(Date, nullable=False, index=True)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'))
    keyword_text = Column(String(255), nullable=False)
    
    # 휴먼 모드: 기존 MarketingPost 연결
    marketing_post_id = Column(Integer, ForeignKey('marketing_posts.id'), nullable=True)
    
    # AI 모드: 프롬프트 사용
    prompt_id = Column(Integer, ForeignKey('automation_prompts.id'), nullable=True)
    
    # 상태
    status = Column(String(20), default='pending')  # pending, processing, completed, failed
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    marketing_product = relationship("MarketingProduct")
    marketing_post = relationship("MarketingPost")
    prompt = relationship("AutomationPrompt", back_populates="schedules")
    tasks = relationship("AutomationTask", back_populates="schedule", cascade="all, delete-orphan")


class AutomationTask(Base):
    """작업 큐 (글/댓글 작성 작업)"""
    __tablename__ = "automation_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(20), nullable=False)  # post, comment, reply
    mode = Column(String(20), nullable=False)  # human, ai
    
    # 스케줄 정보
    schedule_id = Column(Integer, ForeignKey('automation_schedules.id'))
    scheduled_time = Column(DateTime, nullable=False, index=True)
    
    # 작업 내용
    title = Column(String(500), nullable=True)  # 글 제목 (post만)
    content = Column(Text, nullable=False)  # 내용
    parent_task_id = Column(Integer, ForeignKey('automation_tasks.id'), nullable=True)  # 댓글/대댓글용
    order_sequence = Column(Integer, default=0)  # 댓글 순서
    
    # 할당 정보
    assigned_pc_id = Column(Integer, ForeignKey('automation_worker_pcs.id'), nullable=True)
    assigned_account_id = Column(Integer, ForeignKey('automation_accounts.id'), nullable=True)
    cafe_id = Column(Integer, ForeignKey('automation_cafes.id'))
    
    # 상태 관리
    status = Column(String(20), default='pending')  # pending, assigned, in_progress, completed, failed
    priority = Column(Integer, default=0)  # 우선순위 (높을수록 먼저)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    
    # 결과
    post_url = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    schedule = relationship("AutomationSchedule", back_populates="tasks")
    cafe = relationship("AutomationCafe", back_populates="tasks")
    assigned_account = relationship("AutomationAccount", back_populates="tasks")
    parent_task = relationship("AutomationTask", remote_side=[id], foreign_keys=[parent_task_id], backref="child_tasks")


class AutomationPost(Base):
    """자동화로 작성된 글 (저장용)"""
    __tablename__ = "automation_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String(20), nullable=False)  # human, ai
    
    # 글 정보
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    post_url = Column(String(500), nullable=True)
    
    # 작성 정보
    account_id = Column(Integer, ForeignKey('automation_accounts.id'))
    cafe_id = Column(Integer, ForeignKey('automation_cafes.id'))
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'))
    keyword_text = Column(String(255), nullable=True)
    
    # 통계
    view_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    account = relationship("AutomationAccount", back_populates="posts")
    cafe = relationship("AutomationCafe", back_populates="posts")
    marketing_product = relationship("MarketingProduct")
    comments = relationship("AutomationComment", back_populates="post", cascade="all, delete-orphan")


class AutomationComment(Base):
    """자동화로 작성된 댓글 (저장용)"""
    __tablename__ = "automation_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    mode = Column(String(20), nullable=False)  # human, ai
    
    post_id = Column(Integer, ForeignKey('automation_posts.id'))
    parent_comment_id = Column(Integer, ForeignKey('automation_comments.id'), nullable=True)
    
    content = Column(Text, nullable=False)
    account_id = Column(Integer, ForeignKey('automation_accounts.id'))
    order_sequence = Column(Integer, default=0)  # 댓글 순서
    
    created_at = Column(DateTime, default=get_kst_now)
    
    # 관계
    post = relationship("AutomationPost", back_populates="comments")
    account = relationship("AutomationAccount")
    parent = relationship("AutomationComment", remote_side=[id], backref="replies")


class CafeBoardMapping(Base):
    """카페별 게시판 맵핑"""
    __tablename__ = "cafe_board_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    cafe_id = Column(Integer, ForeignKey('automation_cafes.id'), nullable=False)
    board_name = Column(String(255), nullable=False)  # 실제 게시판 이름
    board_value = Column(String(100), nullable=False)  # 게시판 선택 value
    is_default = Column(Boolean, default=False)  # 기본 게시판 여부
    
    created_at = Column(DateTime, default=get_kst_now)
    
    # 관계
    cafe = relationship("AutomationCafe")


class CafeAccountLink(Base):
    """카페-계정 연동 관리"""
    __tablename__ = "cafe_account_links"
    
    id = Column(Integer, primary_key=True, index=True)
    cafe_id = Column(Integer, ForeignKey('automation_cafes.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('automation_accounts.id'), nullable=False)
    is_member = Column(Boolean, default=True)  # 가입 여부
    status = Column(String(20), default='active')  # active, suspended, banned
    
    # 신규발행 글 현황
    draft_post_count = Column(Integer, default=0)  # 사용 가능한 신규발행 글 수
    used_post_count = Column(Integer, default=0)  # 사용된 신규발행 글 수
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    cafe = relationship("AutomationCafe")
    account = relationship("AutomationAccount")
    draft_posts = relationship("DraftPost", back_populates="link", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('cafe_id', 'account_id', name='unique_cafe_account'),
    )


class DraftPost(Base):
    """신규발행 글 (가입인사글) URL 관리"""
    __tablename__ = "draft_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey('cafe_account_links.id'), nullable=False)
    
    # 가입인사글 정보
    draft_url = Column(String(500), nullable=False, unique=True)  # 원본 URL
    article_id = Column(String(50), nullable=False)  # 글 번호
    
    # 사용 상태
    status = Column(String(20), default='available')  # available, used, deleted
    
    # 수정 발행 정보
    modified_url = Column(String(500), nullable=True)  # 수정 발행 후 새 URL
    used_at = Column(DateTime, nullable=True)  # 사용 시간
    
    created_at = Column(DateTime, default=get_kst_now)
    
    # 관계
    link = relationship("CafeAccountLink", back_populates="draft_posts")
    
    
class CommentScript(Base):
    """댓글 원고 스크립트 (순차 작성용)"""
    __tablename__ = "comment_scripts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 연관 Task (본문 글 작성 Task)
    post_task_id = Column(Integer, ForeignKey('automation_tasks.id'), nullable=False)
    
    # 그룹-순서 (1-1, 1-2, 2-1...)
    group_number = Column(Integer, nullable=False)  # 그룹 (1, 2, 3...)
    sequence_number = Column(Integer, nullable=False)  # 순서 (1, 2, 3...)
    
    # PC 번호 (PC1, PC2...)
    pc_number = Column(Integer, nullable=False)
    
    # 댓글 내용
    content = Column(Text, nullable=False)
    
    # 댓글 타입
    is_new_comment = Column(Boolean, default=True)  # True: 새 댓글, False: 대댓글
    parent_group = Column(Integer, nullable=True)  # 대댓글이면 부모 그룹 번호
    
    # 실행 상태
    status = Column(String(20), default='pending')  # pending, in_progress, completed, failed
    completed_at = Column(DateTime, nullable=True)
    
    # 생성된 Task ID (실제 실행할 AutomationTask)
    generated_task_id = Column(Integer, ForeignKey('automation_tasks.id'), nullable=True)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    post_task = relationship("AutomationTask", foreign_keys=[post_task_id], backref="comment_scripts")
    generated_task = relationship("AutomationTask", foreign_keys=[generated_task_id])
    
    # 인덱스
    __table_args__ = (
        Index('idx_post_task_group_seq', 'post_task_id', 'group_number', 'sequence_number'),
    )


# ============================================
# AI 자동화 마케팅 시스템 모델
# ============================================

class AIMarketingProduct(Base):
    """AI 자동화용 상품 설정"""
    __tablename__ = "ai_marketing_products"
    
    id = Column(Integer, primary_key=True, index=True)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), unique=True, nullable=False)
    
    # 플랫폼 권한 (체크박스)
    use_for_blog = Column(Boolean, default=False)  # 블로그 사용 여부
    use_for_cafe = Column(Boolean, default=False)  # 카페 사용 여부
    
    # 상품 상세 정보 (필수)
    product_name = Column(String(500), nullable=False)  # 1. 우리제품명
    core_value = Column(Text, nullable=False)  # 2. 우리 제품의 핵심
    sub_core_value = Column(Text, nullable=False)  # 3. 우리 제품의 서브 핵심
    size_weight = Column(Text, nullable=False)  # 4. 우리 제품 사이즈 & 무게
    difference = Column(Text, nullable=False)  # 5. 타사 제품과 차별점
    famous_brands = Column(Text, nullable=False)  # 6. 해당 제품의 유명 브랜드들
    market_problem = Column(Text, nullable=False)  # 7. 기존 시장의 문제점
    our_price = Column(String(100), nullable=False)  # 8. 우리 제품의 가격
    market_avg_price = Column(String(100), nullable=False)  # 9. 기존 시장의 평균 가격
    target_age = Column(String(100), nullable=False)  # 10. 고객의 예상 연령대
    target_gender = Column(String(50), nullable=False)  # 11. 고객의 예상 성별
    additional_info = Column(Text, nullable=True)  # 12. 기타 추가 특이사항 (선택)
    
    # 마케팅 링크 (필수)
    marketing_link = Column(String(2083), nullable=False)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    marketing_product = relationship("MarketingProduct")
    keywords = relationship("AIProductKeyword", back_populates="ai_product", cascade="all, delete-orphan")
    references = relationship("AIProductReference", back_populates="ai_product", cascade="all, delete-orphan")
    prompt_templates = relationship("AIPromptTemplate", back_populates="ai_product")


class AIProductKeyword(Base):
    """AI 상품별 키워드 관리 (대안성/정보성 분류)"""
    __tablename__ = "ai_product_keywords"
    
    id = Column(Integer, primary_key=True, index=True)
    ai_product_id = Column(Integer, ForeignKey('ai_marketing_products.id'), nullable=False)
    
    keyword_text = Column(String(255), nullable=False)
    keyword_type = Column(String(20), nullable=False)  # alternative(대안성), informational(정보성), unclassified(미분류)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    ai_product = relationship("AIMarketingProduct", back_populates="keywords")
    
    __table_args__ = (
        UniqueConstraint('ai_product_id', 'keyword_text', name='unique_ai_keyword_per_product'),
    )


class AIProductReference(Base):
    """AI 상품별 레퍼런스 관리 (대안성/정보성 분류)"""
    __tablename__ = "ai_product_references"
    
    id = Column(Integer, primary_key=True, index=True)
    ai_product_id = Column(Integer, ForeignKey('ai_marketing_products.id'), nullable=False)
    
    # 기존 Reference 연결
    reference_id = Column(Integer, ForeignKey('references.id'), nullable=False)
    
    # 분류
    reference_type = Column(String(20), nullable=False)  # alternative(대안성), informational(정보성), unclassified(미분류)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    ai_product = relationship("AIMarketingProduct", back_populates="references")
    reference = relationship("Reference")
    
    __table_args__ = (
        UniqueConstraint('ai_product_id', 'reference_id', name='unique_ai_reference_per_product'),
    )


class AIPromptTemplate(Base):
    """AI 프롬프트 템플릿 (대안성/정보성별)"""
    __tablename__ = "ai_prompt_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 템플릿 정보
    template_name = Column(String(255), nullable=False)  # 템플릿 이름
    template_type = Column(String(20), nullable=False)  # alternative(대안성), informational(정보성)
    
    # 프롬프트 내용
    user_prompt_template = Column(Text, nullable=False)  # 변수 포함된 템플릿
    
    is_template = Column(Boolean, default=True)  # True: 템플릿, False: 실제 상품용 프롬프트
    ai_product_id = Column(Integer, ForeignKey('ai_marketing_products.id'), nullable=True)  # 실제 상품용일 경우
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    ai_product = relationship("AIMarketingProduct", back_populates="prompt_templates")


class AIPrompt(Base):
    """AI 프롬프트 관리 (상품별)"""
    __tablename__ = "ai_prompts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 상품 연결
    ai_product_id = Column(Integer, ForeignKey('ai_marketing_products.id'), nullable=False)
    
    # 프롬프트 정보
    keyword_classification = Column(String(20), nullable=False)  # alternative(대안성), informational(정보성)
    system_prompt = Column(Text, nullable=False)  # 시스템 프롬프트
    user_prompt = Column(Text, nullable=False)  # 사용자 프롬프트 (변수 치환 완료)
    
    # Claude API 설정
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    
    # 이미지 생성 여부
    generate_images = Column(Boolean, default=False)
    
    # 카페 특성 반영 여부
    apply_cafe_context = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    ai_product = relationship("AIMarketingProduct")
    schedules = relationship("AIMarketingSchedule", back_populates="prompt")


class AIMarketingSchedule(Base):
    """AI 마케팅 스케줄 관리"""
    __tablename__ = "ai_marketing_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 스케줄 정보
    ai_product_id = Column(Integer, ForeignKey('ai_marketing_products.id'), nullable=False)
    prompt_id = Column(Integer, ForeignKey('ai_prompts.id'), nullable=False)
    
    # 기간 및 개수
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    daily_post_count = Column(Integer, nullable=False)  # 하루 작성 개수
    
    # 예상 통계
    expected_total_posts = Column(Integer, nullable=False)  # 예상 총 글 발행 수
    
    # 상태
    status = Column(String(20), default='scheduled')  # scheduled(진행예정), in_progress(진행중), completed(종료)
    
    created_at = Column(DateTime, default=get_kst_now)
    updated_at = Column(DateTime, default=get_kst_now, onupdate=get_kst_now)
    
    # 관계
    ai_product = relationship("AIMarketingProduct")
    prompt = relationship("AIPrompt", back_populates="schedules")


class AIGeneratedPost(Base):
    """AI로 생성된 신규 발행 글 관리"""
    __tablename__ = "ai_generated_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 상품 및 스케줄 정보
    ai_product_id = Column(Integer, ForeignKey('ai_marketing_products.id'), nullable=False)
    schedule_id = Column(Integer, ForeignKey('ai_marketing_schedules.id'), nullable=False)
    
    # 계정 및 카페 정보
    account_id = Column(Integer, ForeignKey('automation_accounts.id'), nullable=False)
    cafe_id = Column(Integer, ForeignKey('automation_cafes.id'), nullable=False)
    
    # 글 내용
    post_title = Column(Text, nullable=False)
    post_body = Column(Text, nullable=False)
    post_url = Column(String(500), nullable=True)
    
    # 이미지 정보
    image_urls = Column(JSON, nullable=True)  # 생성된 이미지 URL 리스트
    
    # 상태
    status = Column(String(20), default='draft')  # draft(초안), published(발행완료)
    
    created_at = Column(DateTime, default=get_kst_now)
    published_at = Column(DateTime, nullable=True)
    
    # 관계
    ai_product = relationship("AIMarketingProduct")
    schedule = relationship("AIMarketingSchedule")
    account = relationship("AutomationAccount")
    cafe = relationship("AutomationCafe")
    
    
def get_db():
    """데이터베이스 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# __all__ 리스트 업데이트
__all__ = [
    "User", "Product", "MarketingAccount", "TargetCafe", "CafeMembership",
    "MarketingProduct", "Reference", "PostLog", "Comment", "MarketingPost",
    "WorkTask", "PostSchedule", "AccountCafeUsage", "PostingRound", "LoginLog",
    "TaskAssignment", "TaskComment", "TaskFile", "TaskNotification",
    "PersonalMemo", "MemoFile",
    "Order", "OrderStatusMapping",
    "SessionLocal", "Base", "engine",
    "get_db", "HomepageWorker", "HomepageAccount", "HomepageProductKeyword", "HomepagePost",
    "HomepagePostImage", "HomepageKeywordProgress", "HomepageWorkTask", "HomepagePostSchedule",
    "BlogWorker", "BlogAccount", "BlogProductKeyword", "BlogPost", 
    "BlogPostImage", "BlogKeywordProgress", "BlogWorkTask", "BlogPostSchedule",
    # ⭐ 자동화 시스템
    "AutomationWorkerPC", "AutomationAccount", "AutomationCafe", "AutomationPrompt",
    "AutomationSchedule", "AutomationTask", "AutomationPost", "AutomationComment",
    # ⭐ 신규발행 글 관리
    "CafeBoardMapping", "CafeAccountLink", "DraftPost",
    # ⭐ 댓글 원고 시스템
    "CommentScript",
    # ⭐ AI 자동화 마케팅 시스템
    "AIMarketingProduct", "AIProductKeyword", "AIProductReference", "AIPromptTemplate",
    "AIPrompt", "AIMarketingSchedule", "AIGeneratedPost"
]