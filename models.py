# models.py

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    
    # 관계 추가
    schedules = relationship("MarketingSchedule", back_populates="user")
    posts = relationship("MarketingPost", back_populates="user")


class MarketingSchedule(Base):
    __tablename__ = "marketing_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    scheduled_date = Column(Date, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("marketing_posts.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("marketing_products.id"))
    account_id = Column(Integer, ForeignKey("marketing_accounts.id"))
    cafe_id = Column(Integer, ForeignKey("target_cafes.id"))
    keyword = Column(String(255))
    status = Column(String(50), default="pending")
    priority = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # 관계 설정
    user = relationship("User", back_populates="schedules")
    post = relationship("MarketingPost", back_populates="schedule")
    product = relationship("MarketingProduct", back_populates="schedules")
    account = relationship("MarketingAccount", back_populates="schedules")
    cafe = relationship("TargetCafe", back_populates="schedules")


# 다른 필요한 모델들도 정의해야 함
class MarketingPost(Base):
    __tablename__ = "marketing_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    content = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("marketing_products.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 관계
    user = relationship("User", back_populates="posts")
    product = relationship("MarketingProduct", back_populates="posts")
    schedule = relationship("MarketingSchedule", back_populates="post", uselist=False)


class MarketingProduct(Base):
    __tablename__ = "marketing_products"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    name = Column(String(255))
    keywords = Column(Text)  # JSON 형태로 저장
    active = Column(Boolean, default=True)
    
    # 관계
    posts = relationship("MarketingPost", back_populates="product")
    schedules = relationship("MarketingSchedule", back_populates="product")


class MarketingAccount(Base):
    __tablename__ = "marketing_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(100), unique=True)
    password = Column(String(255))
    active = Column(Boolean, default=True)
    
    # 관계
    schedules = relationship("MarketingSchedule", back_populates="account")


class TargetCafe(Base):
    __tablename__ = "target_cafes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    cafe_url = Column(String(500))
    cafe_id = Column(String(100))
    active = Column(Boolean, default=True)
    
    # 관계
    schedules = relationship("MarketingSchedule", back_populates="cafe")


# Product 모델 (이미 있다면 schedules 관계만 추가)
class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String(100))
    name = Column(String(255))
    price = Column(Float)
    thumbnail = Column(String(500))
    details = Column(Text)
    # ... 다른 필드들
    
# models.py에 추가

class LoginLog(Base):
    __tablename__ = "login_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100))
    ip_address = Column(String(45))  # IPv6 대응
    login_time = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    user_agent = Column(String(500))
    
    # 관계 설정
    user = relationship("User", back_populates="login_logs")

class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True)
    reference_id = Column(Integer, ForeignKey("references.id"))
    text = Column(Text, nullable=False)
    account_sequence = Column(Integer, default=0)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 관계 설정
    reference = relationship("Reference", back_populates="comments")
    parent = relationship("Comment", remote_side=[id], back_populates="replies")
    replies = relationship("Comment", back_populates="parent")