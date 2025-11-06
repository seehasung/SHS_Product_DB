#database.py
 
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, DateTime, Date, UniqueConstraint, Float, JSON
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
    daily_quota = Column(Integer, default=0)  # 일일 할당량 필드
    
    # 관계 추가
    schedules = relationship("PostSchedule", back_populates="worker")
    marketing_posts = relationship("MarketingPost", back_populates="worker")
    work_tasks = relationship("WorkTask", back_populates="worker")
    post_logs = relationship("PostLog", back_populates="worker")
    references_modified = relationship("Reference", back_populates="last_modified_by")
    login_logs = relationship("LoginLog", back_populates="user")

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
    user = relationship("User", backref="blog_worker_profile")
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
    platform = Column(String, default='naver_blog')  # 네이버 블로그
    account_id = Column(String, unique=True, nullable=False)
    account_pw = Column(String, nullable=False)
    blog_url = Column(String)  # 블로그 URL
    ip_address = Column(String)
    category = Column(String)
    assigned_worker_id = Column(Integer, ForeignKey('blog_workers.id'))  # 배정된 작업자
    assignment_order = Column(Integer)  # 배정 순서 (1, 2, 3...)
    daily_post_limit = Column(Integer, default=3)  # 일일 포스팅 제한
    status = Column(String, default='active')  # active, inactive
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
    is_active = Column(Boolean, default=True)  # 블로그에서 사용 여부
    order_index = Column(Integer, default=0)  # 순서
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
    keyword_text = Column(String, nullable=False)  # 사용된 키워드
    post_url = Column(String)  # 실제 게시된 URL
    
    # 통계 정보
    char_count = Column(Integer, default=0)  # 글자 수
    image_count = Column(Integer, default=0)  # 이미지 개수
    keyword_count = Column(Integer, default=0)  # 키워드 출현 횟수
    
    # 조회수 등
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # 관계
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    worker_id = Column(Integer, ForeignKey('blog_workers.id'), nullable=False)
    blog_account_id = Column(Integer, ForeignKey('blog_accounts.id'), nullable=False)
    
    is_registration_complete = Column(Boolean, default=True)  # 등록 완료 여부
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
    image_path = Column(String, nullable=False)  # 저장 경로
    image_filename = Column(String, nullable=False)  # 파일명
    image_order = Column(Integer, default=0)  # 순서
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
    status = Column(String, default='pending')  # pending, completed
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
    status = Column(String, default='pending')  # pending, completed, cancelled
    
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
    """통페이지 작업자"""
    __tablename__ = 'homepage_workers'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    status = Column(String, default='active')  # active, inactive, suspended
    daily_quota = Column(Integer, default=3)  # 일일 작업량
    current_product_id = Column(Integer, ForeignKey('marketing_products.id'))  # 현재 진행 중인 상품
    is_blog_manager = Column(Boolean, default=False)  # 블로그 관리자 여부
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = relationship("User", backref="blog_worker_profile")
    current_product = relationship("MarketingProduct", foreign_keys=[current_product_id])
    blog_accounts = relationship("BlogAccount", back_populates="assigned_worker")
    blog_posts = relationship("BlogPost", back_populates="worker")
    blog_tasks = relationship("BlogWorkTask", back_populates="worker")
    keyword_progress = relationship("BlogKeywordProgress", back_populates="worker")
    
    @property
    def required_accounts(self):
        """필요한 블로그 계정 수 계산 (하루 최대 3개씩)"""
        return math.ceil(self.daily_quota / 3)

	
class HomepageAccount(Base):
    """통페이지 계정"""
    __tablename__ = 'homepage_accounts'

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default='naver_blog')  # 네이버 블로그
    account_id = Column(String, unique=True, nullable=False)
    account_pw = Column(String, nullable=False)
    blog_url = Column(String)  # 블로그 URL
    ip_address = Column(String)
    category = Column(String)
    assigned_worker_id = Column(Integer, ForeignKey('blog_workers.id'))  # 배정된 작업자
    assignment_order = Column(Integer)  # 배정 순서 (1, 2, 3...)
    daily_post_limit = Column(Integer, default=3)  # 일일 포스팅 제한
    status = Column(String, default='active')  # active, inactive
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    assigned_worker = relationship("BlogWorker", back_populates="blog_accounts")
    blog_posts = relationship("BlogPost", back_populates="blog_account")
    blog_tasks = relationship("BlogWorkTask", back_populates="blog_account")


class HomepageProductKeyword(Base):
    """통페이지용 상품 키워드"""
    __tablename__ = 'homepage_product_keywords'

    id = Column(Integer, primary_key=True, index=True)
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    keyword_text = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)  # 블로그에서 사용 여부
    order_index = Column(Integer, default=0)  # 순서
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    marketing_product = relationship("MarketingProduct", backref="blog_keywords")


class HomepagePost(Base):
    """통페이지 글"""
    __tablename__ = 'homepage_posts'

    id = Column(Integer, primary_key=True, index=True)
    post_title = Column(String, nullable=False)
    post_body = Column(Text, nullable=False)
    keyword_text = Column(String, nullable=False)  # 사용된 키워드
    post_url = Column(String)  # 실제 게시된 URL
    
    # 통계 정보
    char_count = Column(Integer, default=0)  # 글자 수
    image_count = Column(Integer, default=0)  # 이미지 개수
    keyword_count = Column(Integer, default=0)  # 키워드 출현 횟수
    
    # 조회수 등
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # 관계
    marketing_product_id = Column(Integer, ForeignKey('marketing_products.id'), nullable=False)
    worker_id = Column(Integer, ForeignKey('blog_workers.id'), nullable=False)
    blog_account_id = Column(Integer, ForeignKey('blog_accounts.id'), nullable=False)
    
    is_registration_complete = Column(Boolean, default=True)  # 등록 완료 여부
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    marketing_product = relationship("MarketingProduct", backref="blog_posts")
    worker = relationship("BlogWorker", back_populates="blog_posts")
    blog_account = relationship("BlogAccount", back_populates="blog_posts")
    images = relationship("BlogPostImage", back_populates="blog_post", cascade="all, delete-orphan")


class HomepagePostImage(Base):
    """통페이지 글 이미지"""
    __tablename__ = 'homepage_post_images'

    id = Column(Integer, primary_key=True, index=True)
    blog_post_id = Column(Integer, ForeignKey('blog_posts.id'), nullable=False)
    image_path = Column(String, nullable=False)  # 저장 경로
    image_filename = Column(String, nullable=False)  # 파일명
    image_order = Column(Integer, default=0)  # 순서
    uploaded_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    blog_post = relationship("BlogPost", back_populates="images")


class HomepageKeywordProgress(Base):
    """작업자별 키워드 진행 상황"""
    __tablename__ = 'homepage_keyword_progress'

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


class HomepageWorkTask(Base):
    """통페이지 일일 작업 할당"""
    __tablename__ = 'homepage_work_tasks'

    id = Column(Integer, primary_key=True, index=True)
    task_date = Column(Date, nullable=False)
    status = Column(String, default='pending')  # pending, completed
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


class HomepagePostSchedule(Base):
    """통페이지 포스트 스케줄"""
    __tablename__ = 'homepage_post_schedules'

    id = Column(Integer, primary_key=True, index=True)
    scheduled_date = Column(Date, nullable=False)
    status = Column(String, default='pending')  # pending, completed, cancelled
    
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
    "SessionLocal", "Base", "engine",
    "get_db", "HomepageWorker", "HomepageAccount", "HomepageProductKeyword", "HomepagePost",
    "HomepagePostImage", "HomepageKeywordProgress", "HomepageWorkTask", "HomepagePostSchedule",
    "BlogWorker", "BlogAccount", "BlogProductKeyword", "BlogPost", 
    "BlogPostImage", "BlogKeywordProgress", "BlogWorkTask", "BlogPostSchedule"    
    
]