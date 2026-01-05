from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from typing import List, Optional
from datetime import datetime, date, timedelta
import random
import math
import re
import os
import uuid
import zipfile
from pathlib import Path
from io import BytesIO
from urllib.parse import quote


# 기존 database.py에서 import
from database import (
    get_db, User, MarketingProduct, Product,
    BlogWorker, BlogAccount, BlogProductKeyword, BlogPost, BlogPostImage,
    BlogKeywordProgress, BlogWorkTask, BlogPostSchedule
)

router = APIRouter()


UPLOAD_DIR = "/opt/render/project/src/static/uploads"

# ============================================
# 유틸리티 함수
# ============================================


def get_current_user(request: Request, db: Session):
    """현재 로그인한 사용자 가져오기"""
    # 세션에서 사용자명 가져오기 (키: 'user')
    username = request.session.get('user')
    
    if not username:
        # 디버깅 정보 (나중에 삭제 가능)
        print(f"❌ [BLOG] 세션에 'user' 키 없음. 세션 내용: {dict(request.session)}")
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    
    # 사용자 조회
    user = db.query(User).filter(User.username == username).first()
    if not user:
        print(f"❌ [BLOG] 사용자 '{username}' DB에 없음")
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    print(f"✅ [BLOG] 사용자 인증 성공: {user.username} (ID: {user.id})")
    return user


def check_blog_access(user: User, db: Session):
    """블로그 접근 권한 체크"""
    # 전체 관리자는 항상 접근 가능
    if user.is_admin:
        # 블로그 작업자 프로필 자동 생성
        blog_worker = db.query(BlogWorker).filter(
            BlogWorker.user_id == user.id
        ).first()
        
        if not blog_worker:
            blog_worker = BlogWorker(
                user_id=user.id,
                status='active',
                daily_quota=0,
                is_blog_manager=True
            )
            db.add(blog_worker)
            db.commit()
            db.refresh(blog_worker)
        
        return True, blog_worker
    
    # 마케팅 권한 체크
    if not user.can_manage_marketing:
        return False, "마케팅 권한이 필요합니다"
    
    # 블로그 작업자 등록 여부 체크
    blog_worker = db.query(BlogWorker).filter(
        BlogWorker.user_id == user.id,
        BlogWorker.status == 'active'
    ).first()
    
    if not blog_worker:
        return False, "블로그 작업자로 등록되지 않았습니다"
    
    return True, blog_worker

def check_is_blog_manager(user: User, db: Session):  # ⭐ 함수명 변경
    """블로그 관리자 여부 체크"""
    if user.is_admin:
        return True
    
    blog_worker = db.query(BlogWorker).filter(
        BlogWorker.user_id == user.id
    ).first()
    
    return blog_worker and blog_worker.is_blog_manager

def count_keyword_occurrences(text: str, keyword: str):
    """텍스트에서 키워드 출현 횟수 세기"""
    return text.lower().count(keyword.lower())

def count_chars_without_spaces(text: str):
    """공백과 특수문자를 제외한 순수 글자 수 세기 (한글, 영문, 숫자만)"""
    import re
    # 한글, 영문, 숫자만 남기고 나머지 모두 제거
    pure_text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
    return len(pure_text)


def update_worker_accounts(worker: BlogWorker, db: Session):
    """작업자의 할당량에 따라 블로그 계정 자동 배정/해제"""
    required = worker.required_accounts
    
    # 현재 배정된 계정 수
    current_accounts = db.query(BlogAccount).filter(
        BlogAccount.assigned_worker_id == worker.id
    ).order_by(BlogAccount.assignment_order).all()
    
    current_count = len(current_accounts)
    
    # 계정 추가 필요
    if required > current_count:
        additional = required - current_count
        
        # 미배정 계정 찾기
        available = db.query(BlogAccount).filter(
            BlogAccount.assigned_worker_id == None,
            BlogAccount.status == 'active'
        ).limit(additional).all()
        
        if len(available) < additional:
            raise HTTPException(
                status_code=400,
                detail=f"사용 가능한 블로그 계정이 부족합니다. (필요: {additional}개, 사용 가능: {len(available)}개)"
            )
        
        # 계정 배정
        for i, account in enumerate(available):
            account.assigned_worker_id = worker.id
            account.assignment_order = current_count + i + 1
            db.add(account)
    
    # 계정 제거 필요
    elif required < current_count:
        remove_count = current_count - required
        
        # assignment_order가 높은 순서대로 해제
        accounts_to_remove = sorted(current_accounts, key=lambda x: x.assignment_order, reverse=True)[:remove_count]
        
        for account in accounts_to_remove:
            account.assigned_worker_id = None
            account.assignment_order = None
            db.add(account)
    
    db.commit()


# ============================================
# 메인 페이지
# ============================================

@router.get("/blog")
def blog_main_page(request: Request, db: Session = Depends(get_db)):
    """블로그 메인 페이지"""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=blog_worker_or_error)
    
    blog_worker = blog_worker_or_error if not user.is_admin else db.query(BlogWorker).filter(
        BlogWorker.user_id == user.id
    ).first()
    
    is_manager = check_is_blog_manager(user, db)
    
    # ⭐⭐⭐ 여기에 추가! ⭐⭐⭐
    print("=" * 80)
    print(f"🔍 [BLOG PAGE] 사용자: {user.username}")
    print(f"🔍 [BLOG PAGE] user.is_admin: {user.is_admin}")
    print(f"🔍 [BLOG PAGE] blog_worker: {blog_worker}")
    if blog_worker:
        print(f"🔍 [BLOG PAGE] blog_worker.id: {blog_worker.id}")
        print(f"🔍 [BLOG PAGE] blog_worker.is_blog_manager: {blog_worker.is_blog_manager}")
        print(f"🔍 [BLOG PAGE] blog_worker.status: {blog_worker.status}")
    print(f"🔍 [BLOG PAGE] is_manager (템플릿 전달값): {is_manager}")
    print("=" * 80)
    # ⭐⭐⭐ 여기까지 추가! ⭐⭐⭐
    
    return templates.TemplateResponse("marketing_blog.html", {
        "request": request,
        "user": user,
        "blog_worker": blog_worker,
        "is_manager": is_manager
    })

@router.get("/blog/schedules")
def blog_schedules_page(request: Request, db: Session = Depends(get_db)):
    """블로그 전체 스케줄 페이지"""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=blog_worker_or_error)
    
    blog_worker = blog_worker_or_error if not user.is_admin else db.query(BlogWorker).filter(
        BlogWorker.user_id == user.id
    ).first()
    
    is_manager = check_is_blog_manager(user, db)
    
    # 스케줄 조회
    if is_manager:
        # 관리자: 모든 작업 조회
        tasks = db.query(BlogWorkTask).order_by(
            desc(BlogWorkTask.task_date),
            desc(BlogWorkTask.id)
        ).all()
    else:
        # 일반 작업자: 자신의 작업만 조회
        tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.worker_id == blog_worker.id
        ).order_by(
            desc(BlogWorkTask.task_date),
            desc(BlogWorkTask.id)
        ).all()
    
    # 작업 정보 구성
    schedules = []
    for task in tasks:
        # 작업자 정보
        worker_name = "미할당"
        if task.worker_id:
            worker_obj = db.query(BlogWorker).filter(
                BlogWorker.id == task.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        # 계정 정보
        account_id = "미할당"
        if task.blog_account_id:
            account = db.query(BlogAccount).filter(
                BlogAccount.id == task.blog_account_id
            ).first()
            if account:
                account_id = account.account_id
        
        # 상품 정보
        product_name = "-"
        if task.marketing_product_id:
            marketing_product = db.query(MarketingProduct).filter(
                MarketingProduct.id == task.marketing_product_id
            ).first()
            
            if marketing_product and marketing_product.product_id:
                product = db.query(Product).filter(
                    Product.id == marketing_product.product_id
                ).first()
                if product:
                    product_name = product.name
        
        # 키워드
        keyword_text = task.keyword_text if task.keyword_text else "-"
        
        # 작성된 글 정보
        post_title = None
        post_url = None
        
        if task.completed_post_id:
            post = db.query(BlogPost).filter(
                BlogPost.id == task.completed_post_id
            ).first()
            
            if post:
                post_title = post.post_title
                post_url = post.post_url
        
        schedules.append({
            "id": task.id,
            "task_date": task.task_date,
            "worker_name": worker_name,
            "account_id": account_id,
            "product_name": product_name,
            "keyword": keyword_text,
            "status": task.status,
            "post_title": post_title,
            "post_url": post_url,
            "post_id": task.completed_post_id
        })
    
    return templates.TemplateResponse("marketing_blog.html", {
        "request": request,
        "user": user,
        "blog_worker": blog_worker,
        "is_manager": is_manager,
        "schedules": schedules,
        "view_mode": "schedules"
    })
    
# ============================================
# 전체 현황 API
# ============================================

@router.get("/blog/api/dashboard")
def get_dashboard_stats(
    request: Request, 
    date: Optional[str] = None,  # ⭐ date_param → date로 변경!
    db: Session = Depends(get_db)
):
    """전체 현황 통계 + 작업 목록"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=blog_worker_or_error)
    
    blog_worker = blog_worker_or_error if not user.is_admin else None
    is_manager = check_is_blog_manager(user, db)
    
    # 날짜 파싱
    if date:  # ⭐ date로 변경
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()
    
    # ⭐ 디버깅 로그
    print("=" * 80)
    print(f"📊 [DASHBOARD API] 요청 받음")
    print(f"   - 사용자: {user.username}")
    print(f"   - date 파라미터: {date}")
    print(f"   - target_date: {target_date}")
    print("=" * 80)
    
    # ============ 통계 계산 ============
    if is_manager:
        tasks_query = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == target_date
        )
        
        total_tasks = tasks_query.count()
        completed = tasks_query.filter(BlogWorkTask.status == 'completed').count()
        in_progress = tasks_query.filter(BlogWorkTask.status == 'in_progress').count()
        pending = tasks_query.filter(BlogWorkTask.status == 'pending').count()
        
        total_posts = db.query(BlogPost).count()
        today_posts = db.query(BlogPost).filter(
            func.date(BlogPost.created_at) == target_date
        ).count()
    else:
        tasks_query = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == target_date,
            BlogWorkTask.worker_id == blog_worker.id
        )
        
        total_tasks = tasks_query.count()
        completed = tasks_query.filter(BlogWorkTask.status == 'completed').count()
        in_progress = tasks_query.filter(BlogWorkTask.status == 'in_progress').count()
        pending = tasks_query.filter(BlogWorkTask.status == 'pending').count()
        
        total_posts = db.query(BlogPost).filter(
            BlogPost.worker_id == blog_worker.id
        ).count()
        today_posts = db.query(BlogPost).filter(
            BlogPost.worker_id == blog_worker.id,
            func.date(BlogPost.created_at) == target_date
        ).count()
    
    active_workers = db.query(BlogWorker).filter(
        BlogWorker.status == 'active'
    ).count()
    
    # ============ ⭐ 작업 목록 가져오기 ============
    if is_manager:
        tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == target_date
        ).order_by(BlogWorkTask.id.desc()).all()
    else:
        tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == target_date,
            BlogWorkTask.worker_id == blog_worker.id
        ).order_by(BlogWorkTask.id.desc()).all()
    
    # ⭐ 작업 목록을 프론트엔드 형식으로 변환
    schedules = []
    for task in tasks:
        # 작업자 정보
        worker_name = "미할당"
        if task.worker_id:
            worker_obj = db.query(BlogWorker).filter(
                BlogWorker.id == task.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        # 계정 정보
        account_id = "미할당"
        if task.blog_account_id:
            account = db.query(BlogAccount).filter(
                BlogAccount.id == task.blog_account_id
            ).first()
            if account:
                account_id = account.account_id
        
        # ⭐ 상품 정보 (MarketingProduct → Product)
        product_name = "-"
        if task.marketing_product_id:
            marketing_product = db.query(MarketingProduct).filter(
                MarketingProduct.id == task.marketing_product_id
            ).first()
            
            if marketing_product and marketing_product.product_id:
                product = db.query(Product).filter(
                    Product.id == marketing_product.product_id
                ).first()
                if product:
                    product_name = product.name
        
        # ⭐ 키워드 (직접 필드 사용)
        keyword_text = task.keyword_text if task.keyword_text else "-"
        
        # 작성된 글 정보
        post_title = None
        post_url = None
        char_count = 0
        keyword_count = 0
        images = []
        
        if task.completed_post_id:
            post = db.query(BlogPost).filter(
                BlogPost.id == task.completed_post_id
            ).first()
            
            if post:
                post_title = post.post_title
                post_url = post.post_url
                char_count = post.char_count
                keyword_count = post.keyword_count
                
                # 이미지 목록
                post_images = db.query(BlogPostImage).filter(
                    BlogPostImage.blog_post_id == post.id
                ).all()
                
                images = [
                    {"filename": img.image_filename} 
                    for img in post_images
                ]
        
        schedules.append({
            "id": task.id,
            "scheduled_date": str(task.task_date),
            "worker_name": worker_name,
            "account_id": account_id,
            "product_name": product_name,
            "keyword": keyword_text,
            "status": task.status,
            "is_completed": task.status == 'completed',
            
            # 작성된 글 정보
            "post_id": task.completed_post_id,
            "post_title": post_title,
            "post_url": post_url,
            "char_count": char_count,
            "keyword_count": keyword_count,
            "images": images
        })
    
    return {
        # 통계
        "total": total_tasks,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "total_posts": total_posts,
        "today_posts": today_posts,
        "active_workers": active_workers,
        
        # 작업 목록
        "schedules": schedules
    }

@router.get("/blog/api/tasks/today")
def get_today_tasks(request: Request, db: Session = Depends(get_db)):
    """오늘의 작업 목록 조회"""
    user = get_current_user(request, db)
    
    today = date.today()
    
    # 기본 쿼리 (오늘 작업만)
    query = db.query(BlogWorkTask).filter(BlogWorkTask.task_date == today)
    
    # ⭐ 관리자 체크
    is_manager = check_is_blog_manager(user, db)
    
    # ⭐ 일반 사용자는 자기 작업만 필터링
    if not is_manager:
        worker = db.query(BlogWorker).filter(BlogWorker.user_id == user.id).first()
        if worker:
            query = query.filter(BlogWorkTask.worker_id == worker.id)
        else:
            # 작업자가 아니면 빈 결과 반환
            return []
    
    # ⭐ 관리자는 모든 작업 표시
    tasks = query.all()
    
    result = []
    for task in tasks:
        # 상품명 조회 (Product 테이블에서)
        product_name = ""
        if task.marketing_product_id:
            marketing_product = db.query(MarketingProduct).filter(
                MarketingProduct.id == task.marketing_product_id
            ).first()
            
            if marketing_product and marketing_product.product_id:
                product = db.query(Product).filter(
                    Product.id == marketing_product.product_id
                ).first()
                if product:
                    product_name = product.name
        
        # 작업자명 조회
        worker_name = ""
        if task.worker_id:
            worker_obj = db.query(BlogWorker).filter(
                BlogWorker.id == task.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        # 계정 ID 조회
        account_id = ""
        if task.blog_account_id:
            account = db.query(BlogAccount).filter(
                BlogAccount.id == task.blog_account_id
            ).first()
            if account:
                account_id = account.account_id
        
        result.append({
            "id": task.id,
            "task_date": str(task.task_date),
            "keyword": task.keyword_text,
            "product_name": product_name,
            "worker_name": worker_name,
            "account_id": account_id,
            "status": task.status,
            "post_id": task.completed_post_id
        })
    
    return result


@router.get("/blog/api/tasks")
def get_tasks_by_date(
    request: Request,
    date: Optional[str] = None,  # ⭐ 날짜 파라미터
    db: Session = Depends(get_db)
):
    """날짜별 작업 목록 조회"""
    user = get_current_user(request, db)
    
    # 날짜 파싱
    if date:
        try:
            task_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            task_date = date.today()
    else:
        task_date = date.today()
    
    print(f"🔍 [GET TASKS] 날짜: {task_date}, 사용자: {user.username}")
    
    # 기본 쿼리
    query = db.query(BlogWorkTask).filter(BlogWorkTask.task_date == task_date)
    
    # 관리자 체크
    is_manager = check_is_blog_manager(user, db)
    
    # 일반 사용자는 자기 작업만
    if not is_manager:
        worker = db.query(BlogWorker).filter(BlogWorker.user_id == user.id).first()
        if worker:
            query = query.filter(BlogWorkTask.worker_id == worker.id)
        else:
            return []
    
    tasks = query.all()
    
    result = []
    for task in tasks:
        # 상품명 조회
        product_name = ""
        if task.marketing_product_id:
            marketing_product = db.query(MarketingProduct).filter(
                MarketingProduct.id == task.marketing_product_id
            ).first()
            
            if marketing_product and marketing_product.product_id:
                product = db.query(Product).filter(
                    Product.id == marketing_product.product_id
                ).first()
                if product:
                    product_name = product.name
        
        # 작업자명 조회
        worker_name = ""
        if task.worker_id:
            worker_obj = db.query(BlogWorker).filter(
                BlogWorker.id == task.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        # 계정 ID 조회
        account_id = ""
        if task.blog_account_id:
            account = db.query(BlogAccount).filter(
                BlogAccount.id == task.blog_account_id
            ).first()
            if account:
                account_id = account.account_id
        
        result.append({
            "id": task.id,
            "task_date": str(task.task_date),
            "keyword": task.keyword_text,
            "product_name": product_name,
            "worker_name": worker_name,
            "account_id": account_id,
            "status": task.status,
            "post_id": task.completed_post_id
        })
    
    print(f"✅ [GET TASKS] {len(result)}개 작업 반환")
    return result


# ⭐ 작업 상태 변경 API 추가
@router.post("/blog/api/tasks/{task_id}/change-status")
def change_task_status(
    task_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    """작업 상태 변경"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    task = db.query(BlogWorkTask).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    
    # 권한 체크
    blog_worker = blog_worker_or_error if not user.is_admin else None
    if not check_is_blog_manager(user, db) and blog_worker and task.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    task.status = status
    db.commit()
    
    print(f"✅ [CHANGE STATUS] 작업 {task_id}: {status}")
    return {"message": "상태 변경 완료", "status": status}


@router.post("/blog/api/tasks/{task_id}/delete")
def delete_blog_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """블로그 작업 삭제"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    task = db.query(BlogWorkTask).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    
    # 권한 체크 - 관리자만 삭제 가능
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    try:
        # 1단계: 관련 진행상황 삭제 또는 초기화
        if task.worker_id and task.marketing_product_id and task.keyword_text:
            progress = db.query(BlogKeywordProgress).filter(
                BlogKeywordProgress.worker_id == task.worker_id,
                BlogKeywordProgress.marketing_product_id == task.marketing_product_id,
                BlogKeywordProgress.keyword_text == task.keyword_text
            ).first()
            
            if progress:
                # 완료되지 않은 진행상황은 삭제
                if not progress.is_completed:
                    db.delete(progress)
                    print(f"🗑️ [DELETE TASK] 진행상황 삭제: {task.keyword_text}")
                else:
                    # 완료된 경우는 completed_post_id만 제거
                    progress.completed_post_id = None
                    db.add(progress)
                    print(f"🔄 [DELETE TASK] 진행상황 참조 제거: {task.keyword_text}")
        
        # 2단계: 작업 삭제
        keyword_text = task.keyword_text
        task_date = task.task_date
        db.delete(task)
        db.commit()
        
        print(f"✅ [DELETE TASK] 작업 ID {task_id} 삭제 완료 (키워드: {keyword_text}, 날짜: {task_date})")
        
        return {"message": "작업이 삭제되었습니다"}
        
    except Exception as e:
        db.rollback()
        print(f"❌ [DELETE TASK] 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"삭제 중 오류 발생: {str(e)}")


# ============================================
# 상품 관리 API
# ============================================

@router.get("/blog/api/products")
def get_blog_products(request: Request, db: Session = Depends(get_db)):
    """블로그 상품 목록"""
    user = get_current_user(request, db)
    has_access, _ = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    # MarketingProduct 조회
    marketing_products = db.query(MarketingProduct).order_by(MarketingProduct.id).all()
    
    result = []
    for mp in marketing_products:
        # product_id로 Product 조회
        product = None
        if hasattr(mp, 'product_id') and mp.product_id:
            product = db.query(Product).filter(Product.id == mp.product_id).first()
        
        # MarketingProduct의 기본 키워드 처리
        if isinstance(mp.keywords, str):
            try:
                import json
                base_keywords = json.loads(mp.keywords)
            except:
                base_keywords = []
        elif isinstance(mp.keywords, list):
            base_keywords = mp.keywords
        else:
            base_keywords = []
        
        # 블로그용 키워드 설정 조회
        blog_keywords = db.query(BlogProductKeyword).filter(
            BlogProductKeyword.marketing_product_id == mp.id
        ).order_by(BlogProductKeyword.order_index).all()
        
        keywords_info = []
        for bk in blog_keywords:
            # ⭐⭐⭐ 핵심 추가: 이 키워드로 작성된 글 개수 계산 ⭐⭐⭐
            post_count = db.query(BlogPost).filter(
                BlogPost.marketing_product_id == mp.id,
                BlogPost.keyword_text == bk.keyword_text
            ).count()
            
            keywords_info.append({
                "id": bk.id,
                "text": bk.keyword_text,
                "is_active": bk.is_active,
                "order_index": bk.order_index,
                "post_count": post_count  # ⭐ 추가
            })
        
        result.append({
            "id": mp.id,
            "product_code": product.product_code if product else f"MP-{mp.id}",
            "name": product.name if product else f"마케팅 상품 #{mp.id}",
            "base_keywords": base_keywords,
            "blog_keywords": keywords_info
        })
    
    return result

@router.post("/blog/api/products/{product_id}/sync-keywords")
def sync_product_keywords(product_id: int, request: Request, db: Session = Depends(get_db)):
    """상품의 기본 키워드를 블로그 키워드로 동기화"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    product = db.query(MarketingProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    # ⭐ keywords 파싱
    if isinstance(product.keywords, str):
        try:
            import json
            keywords = json.loads(product.keywords)
        except:
            print(f"⚠️ [SYNC] 상품 {product_id}: keywords 파싱 실패")
            keywords = []
    elif isinstance(product.keywords, list):
        keywords = product.keywords
    else:
        print(f"⚠️ [SYNC] 상품 {product_id}: keywords가 없거나 형식이 이상함")
        keywords = []
    
    # 디버깅 로그
    print(f"🔍 [SYNC] 상품 {product_id}: 동기화할 키워드 수 = {len(keywords)}")
    
    if len(keywords) == 0:
        return {
            "message": "동기화할 키워드가 없습니다. 먼저 상품에 키워드를 추가해주세요.",
            "keyword_count": 0
        }
    
    # 기존 블로그 키워드 삭제
    deleted_count = db.query(BlogProductKeyword).filter(
        BlogProductKeyword.marketing_product_id == product_id
    ).delete()
    print(f"🗑️ [SYNC] 기존 키워드 {deleted_count}개 삭제")
    
    # ⭐ 새로 생성 (dict 또는 string 모두 처리)
    added_count = 0
    for i, keyword_item in enumerate(keywords):
        # dict 형식인 경우: {'keyword': '...', 'active': True}
        if isinstance(keyword_item, dict):
            keyword_text = keyword_item.get('keyword', '')
            is_active = keyword_item.get('active', True)
        # string 형식인 경우: '키워드'
        elif isinstance(keyword_item, str):
            keyword_text = keyword_item
            is_active = True
        else:
            continue
        
        # 빈 문자열 제외
        if keyword_text and keyword_text.strip():
            blog_keyword = BlogProductKeyword(
                marketing_product_id=product_id,
                keyword_text=keyword_text.strip(),
                is_active=is_active,  # ⭐ active 상태 유지
                order_index=i
            )
            db.add(blog_keyword)
            added_count += 1
            print(f"➕ [SYNC] 키워드 추가: {keyword_text.strip()} (active={is_active})")
    
    db.commit()
    
    print(f"✅ [SYNC] 총 {added_count}개 키워드 동기화 완료")
    
    return {
        "message": f"키워드 동기화 완료 ({added_count}개)",
        "keyword_count": added_count
    }


@router.put("/blog/api/keywords/{keyword_id}/toggle")
def toggle_keyword_active(keyword_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 키워드 ON/OFF 토글"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    keyword = db.query(BlogProductKeyword).get(keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")
    
    keyword.is_active = not keyword.is_active
    db.commit()
    
    return {"is_active": keyword.is_active}


# ============================================
# 글 관리 API
# ============================================

@router.get("/blog/api/posts")
def get_blog_posts(request: Request, db: Session = Depends(get_db)):
    """블로그 글 목록"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    blog_worker = blog_worker_or_error if not user.is_admin else None
    is_manager = check_is_blog_manager(user, db)
    
    query = db.query(BlogPost)
    
    # 일반 작업자는 자신의 글만
    if not is_manager and blog_worker:
        query = query.filter(BlogPost.worker_id == blog_worker.id)
    
    posts = query.order_by(desc(BlogPost.created_at)).all()
    
    result = []
    for post in posts:
        # ⭐ Product 테이블에서 이름 가져오기
        product_name = ""
        if post.marketing_product_id:
            marketing_product = db.query(MarketingProduct).filter(
                MarketingProduct.id == post.marketing_product_id
            ).first()
            
            if marketing_product and marketing_product.product_id:
                product = db.query(Product).filter(
                    Product.id == marketing_product.product_id
                ).first()
                if product:
                    product_name = product.name
        
        worker_name = ""
        if post.worker_id:
            worker_obj = db.query(BlogWorker).filter(
                BlogWorker.id == post.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        account_id = ""
        if post.blog_account_id:
            account = db.query(BlogAccount).filter(
                BlogAccount.id == post.blog_account_id
            ).first()
            if account:
                account_id = account.account_id
        
        result.append({
            "id": post.id,
            "title": post.post_title,
            "keyword": post.keyword_text,
            "product_name": product_name,
            "worker_name": worker_name,
            "account_id": account_id,
            "char_count": post.char_count,
            "image_count": post.image_count,
            "keyword_count": post.keyword_count,
            "images": [
                {
                    "id": img.id,  # ⭐ 추가 (일관성)
                    "path": img.image_path, 
                    "filename": img.image_filename
                } 
                for img in post.images
            ],
            "created_at": post.created_at.strftime("%Y-%m-%d %H:%M"),
            "post_url": post.post_url
        })
    
    return result


@router.post("/blog/api/posts")
async def create_blog_post(
    request: Request,
    task_id: int = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    post_url: str = Form(None),
    images: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """블로그 글 작성"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    blog_worker = blog_worker_or_error if not user.is_admin else db.query(BlogWorker).filter(
        BlogWorker.user_id == user.id
    ).first()
    
    # 작업 조회
    task = db.query(BlogWorkTask).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    
    # ⭐ 권한 체크 (일반 작업자는 자신의 작업만)
    if not check_is_blog_manager(user, db) and task.worker_id != blog_worker.id:  # ⭐ 수정!
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 통계 계산
    char_count = count_chars_without_spaces(body)  # ✅
    keyword_count = count_keyword_occurrences(title + " " + body, task.keyword_text)
    
    # 블로그 글 생성
    blog_post = BlogPost(
        post_title=title,
        post_body=body,
        keyword_text=task.keyword_text,
        post_url=post_url,
        char_count=char_count,
        image_count=0,
        keyword_count=keyword_count,
        marketing_product_id=task.marketing_product_id,
        worker_id=task.worker_id,
        blog_account_id=task.blog_account_id,
        is_registration_complete=True
    )
    db.add(blog_post)
    db.flush()
    
    # 이미지 저장
    if images:
        upload_dir = Path(f"{UPLOAD_DIR}/blog_images")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        for i, image in enumerate(images):
            if image.filename:
                ext = os.path.splitext(image.filename)[1]
                filename = f"{uuid.uuid4()}{ext}"
                filepath = upload_dir / filename
                
                with open(filepath, "wb") as f:
                    content = await image.read()
                    f.write(content)
                
                blog_image = BlogPostImage(
                    blog_post_id=blog_post.id,
                    image_path=str(filepath),
                    image_filename=filename,
                    image_order=i
                )
                db.add(blog_image)
        
        blog_post.image_count = len(images)
    
    # 작업 완료 처리
    task.status = 'completed'
    task.completed_post_id = blog_post.id
    task.completed_at = datetime.now()
    
    # 진행 상황 업데이트
    progress = db.query(BlogKeywordProgress).filter(
        BlogKeywordProgress.worker_id == task.worker_id,
        BlogKeywordProgress.marketing_product_id == task.marketing_product_id,
        BlogKeywordProgress.keyword_text == task.keyword_text
    ).first()
    
    if progress:
        progress.is_completed = True
        progress.completed_post_id = blog_post.id
        progress.completed_at = datetime.now()
    
    db.commit()
    
    return {"message": "글 작성 완료", "post_id": blog_post.id}


@router.get("/blog/api/posts/{post_id}")
def get_blog_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 글 상세"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    post = db.query(BlogPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 권한 체크
    blog_worker = blog_worker_or_error if not user.is_admin else None
    if not check_is_blog_manager(user, db) and blog_worker and post.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # Product 테이블에서 이름 가져오기
    product_name = ""
    if post.marketing_product_id:
        marketing_product = db.query(MarketingProduct).filter(
            MarketingProduct.id == post.marketing_product_id
        ).first()
        
        if marketing_product and marketing_product.product_id:
            product = db.query(Product).filter(
                Product.id == marketing_product.product_id
            ).first()
            if product:
                product_name = product.name
    
    worker_name = ""
    if post.worker_id:
        worker_obj = db.query(BlogWorker).filter(
            BlogWorker.id == post.worker_id
        ).first()
        if worker_obj and worker_obj.user:
            worker_name = worker_obj.user.username
    
    account_id = ""
    if post.blog_account_id:
        account = db.query(BlogAccount).filter(
            BlogAccount.id == post.blog_account_id
        ).first()
        if account:
            account_id = account.account_id
    
    # ⭐ task_id 찾기
    task_id = None
    task = db.query(BlogWorkTask).filter(
        BlogWorkTask.completed_post_id == post_id
    ).first()
    if task:
        task_id = task.id
    
    return {
        "id": post.id,
        "task_id": task_id,  # ⭐ 추가
        "title": post.post_title,
        "body": post.post_body,
        "keyword": post.keyword_text,
        "post_url": post.post_url,
        "char_count": post.char_count,
        "image_count": post.image_count,
        "keyword_count": post.keyword_count,
        "images": [
            {
                "id": img.id,  # ⭐ 추가 (일관성)
                "path": img.image_path, 
                "filename": img.image_filename
            } 
            for img in post.images
        ],
        "product_name": product_name,
        "worker_name": worker_name,
        "account_id": account_id,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M")
    }

@router.put("/blog/api/posts/{post_id}")
async def update_blog_post(
    post_id: int,
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    post_url: str = Form(None),
    images: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """블로그 글 수정"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    post = db.query(BlogPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 권한 체크
    blog_worker = blog_worker_or_error if not user.is_admin else None
    if not check_is_blog_manager(user, db) and blog_worker and post.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 글 수정
    post.post_title = title
    post.post_body = body
    post.post_url = post_url
    
    # 통계 재계산
    post.char_count = count_chars_without_spaces(body)  # ✅
    post.keyword_count = count_keyword_occurrences(title + " " + body, post.keyword_text)  
      
    # 새 이미지 추가
    if images:
        upload_dir = Path(f"{UPLOAD_DIR}/blog_images")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 기존 이미지 개수
        existing_count = len(post.images)
        
        for i, image in enumerate(images):
            if image.filename:
                ext = os.path.splitext(image.filename)[1]
                filename = f"{uuid.uuid4()}{ext}"
                filepath = upload_dir / filename
                
                with open(filepath, "wb") as f:
                    content = await image.read()
                    f.write(content)
                
                blog_image = BlogPostImage(
                    blog_post_id=post.id,
                    image_path=str(filepath),
                    image_filename=filename,
                    image_order=existing_count + i
                )
                db.add(blog_image)
        
        post.image_count = existing_count + len(images)
    
    db.commit()
    
    return {"message": "글 수정 완료", "post_id": post.id}

@router.delete("/blog/api/posts/{post_id}")
def delete_blog_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 글 삭제"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    post = db.query(BlogPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    try:
        # 1단계: BlogWorkTask에서 참조 제거
        related_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.completed_post_id == post_id
        ).all()
        
        print(f"🔍 [DELETE] 관련 작업 {len(related_tasks)}개 발견")
        
        for task in related_tasks:
            print(f"   - 작업 ID {task.id}: completed_post_id 제거")
            task.completed_post_id = None
            task.status = 'pending'
            task.completed_at = None
            db.add(task)
        
        # 2단계: BlogKeywordProgress에서 참조 제거
        related_progress = db.query(BlogKeywordProgress).filter(
            BlogKeywordProgress.completed_post_id == post_id
        ).all()
        
        print(f"🔍 [DELETE] 관련 진행상황 {len(related_progress)}개 발견")
        
        for progress in related_progress:
            print(f"   - 진행상황 ID {progress.id}: completed_post_id 제거")
            progress.completed_post_id = None
            progress.is_completed = False
            progress.completed_at = None
            db.add(progress)
        
        # 먼저 참조를 제거한 상태로 커밋
        db.commit()
        print(f"✅ [DELETE] 참조 제거 완료")
        
        # 3단계: 이미지 파일 삭제
        for image in post.images:
            try:
                if os.path.exists(image.image_path):
                    os.remove(image.image_path)
                    print(f"🗑️ [DELETE] 이미지 삭제: {image.image_filename}")
            except Exception as e:
                print(f"⚠️ [DELETE] 이미지 삭제 실패: {image.image_path} - {e}")
        
        # 4단계: 글 삭제
        db.delete(post)
        db.commit()
        print(f"✅ [DELETE] 글 ID {post_id} 삭제 완료")
        
        return {"message": "글이 삭제되었습니다. 관련 작업은 다시 대기 상태가 되었습니다."}
        
    except Exception as e:
        db.rollback()
        print(f"❌ [DELETE] 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"삭제 중 오류 발생: {str(e)}")


@router.delete("/blog/api/posts/{post_id}/images/{image_id}")
def delete_post_image(
    post_id: int,
    image_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """블로그 글의 이미지 삭제"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    # 글 조회
    post = db.query(BlogPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 권한 체크
    blog_worker = blog_worker_or_error if not user.is_admin else None
    if not check_is_blog_manager(user, db) and blog_worker and post.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 이미지 조회
    image = db.query(BlogPostImage).filter(
        BlogPostImage.id == image_id,
        BlogPostImage.blog_post_id == post_id
    ).first()
    
    if not image:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다")
    
    try:
        # 파일 삭제
        if os.path.exists(image.image_path):
            os.remove(image.image_path)
            print(f"✅ [DELETE IMAGE] 파일 삭제: {image.image_filename}")
        else:
            print(f"⚠️ [DELETE IMAGE] 파일 없음: {image.image_path}")
        
        # DB에서 삭제
        db.delete(image)
        
        # 이미지 개수 업데이트
        remaining_count = db.query(BlogPostImage).filter(
            BlogPostImage.blog_post_id == post_id
        ).count() - 1  # 현재 삭제 중인 것 제외
        
        post.image_count = max(0, remaining_count)
        
        db.commit()
        
        print(f"✅ [DELETE IMAGE] 이미지 ID {image_id} 삭제 완료")
        print(f"   남은 이미지: {post.image_count}개")
        
        return {
            "message": "이미지가 삭제되었습니다",
            "remaining_images": post.image_count
        }
        
    except Exception as e:
        db.rollback()
        print(f"❌ [DELETE IMAGE] 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"이미지 삭제 중 오류 발생: {str(e)}")


@router.get("/blog/api/posts/{post_id}/images/download")
def download_post_images(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """블로그 글의 모든 이미지를 ZIP으로 다운로드"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    # 글 조회
    post = db.query(BlogPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 권한 체크
    blog_worker = blog_worker_or_error if not user.is_admin else None
    if not check_is_blog_manager(user, db) and blog_worker and post.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 이미지 조회
    images = db.query(BlogPostImage).filter(
        BlogPostImage.blog_post_id == post_id
    ).order_by(BlogPostImage.image_order).all()
    
    if not images:
        raise HTTPException(status_code=404, detail="다운로드할 이미지가 없습니다")
    
    # ZIP 파일 생성
    zip_buffer = BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, image in enumerate(images):
                if os.path.exists(image.image_path):
                    # 파일 이름: 순서_원본파일명
                    arcname = f"{i+1:02d}_{image.image_filename}"
                    zip_file.write(image.image_path, arcname)
                    print(f"✅ [ZIP] 추가: {arcname}")
                else:
                    print(f"⚠️ [ZIP] 파일 없음: {image.image_path}")
        
        zip_buffer.seek(0)
        
        # ⭐⭐⭐ 파일명 생성 (한글 지원) ⭐⭐⭐
        safe_title = "".join(c for c in post.post_title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:50]  # 최대 50자
        
        if safe_title:
            filename = f"{safe_title}_images.zip"
        else:
            filename = f"blog_post_{post_id}_images.zip"
        
        # ⭐ RFC 5987 인코딩 (한글 지원)
        encoded_filename = quote(filename.encode('utf-8'))
        
        print(f"✅ [ZIP] 다운로드 준비 완료: {filename} ({len(images)}개 이미지)")
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
        
    except Exception as e:
        print(f"❌ [ZIP] 오류: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"ZIP 생성 중 오류: {str(e)}")


# ============================================
# 계정 관리 API
# ============================================

@router.get("/blog/api/accounts")
def get_blog_accounts(request: Request, db: Session = Depends(get_db)):
    """블로그 계정 목록"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    accounts = db.query(BlogAccount).order_by(BlogAccount.id).all()
    
    result = []
    for account in accounts:
        result.append({
            "id": account.id,
            "account_id": account.account_id,
            "blog_url": account.blog_url,
            "ip_address": account.ip_address,
            "category": account.category,
            "assigned_worker_name": account.assigned_worker.user.username if account.assigned_worker else None,
            "assignment_order": account.assignment_order,
            "status": account.status
        })
    
    return result


@router.post("/blog/api/accounts")
def create_blog_account(
    account_id: str = Form(...),
    account_pw: str = Form(...),
    blog_url: str = Form(None),
    ip_address: str = Form(None),
    category: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """블로그 계정 추가"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 중복 체크
    existing = db.query(BlogAccount).filter(
        BlogAccount.account_id == account_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="이미 존재하는 계정입니다")
    
    account = BlogAccount(
        account_id=account_id,
        account_pw=account_pw,
        blog_url=blog_url,
        ip_address=ip_address,
        category=category,
        status='active'
    )
    db.add(account)
    db.commit()
    
    return {"message": "계정 추가 완료", "account_id": account.id}


@router.put("/blog/api/accounts/{account_id}")
def update_blog_account(
    account_id: int,
    account_pw: str = Form(None),
    blog_url: str = Form(None),
    ip_address: str = Form(None),
    category: str = Form(None),
    status: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """블로그 계정 수정"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    account = db.query(BlogAccount).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    
    if account_pw:
        account.account_pw = account_pw
    if blog_url:
        account.blog_url = blog_url
    if ip_address:
        account.ip_address = ip_address
    if category:
        account.category = category
    if status:
        account.status = status
    
    db.commit()
    
    return {"message": "계정 수정 완료"}


@router.put("/blog/api/accounts/{account_id}/assign-worker")
def assign_worker_to_account(
    account_id: int,
    worker_id: int = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """블로그 계정에 작업자 수동 배정/해제"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    account = db.query(BlogAccount).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    
    # 기존 작업자 정보 저장
    old_worker_id = account.assigned_worker_id
    
    # worker_id가 None이거나 0이면 배정 해제
    if worker_id is None or worker_id == 0:
        account.assigned_worker_id = None
        account.assignment_order = None
        db.commit()
        
        print(f"✅ [ASSIGN] 계정 {account.account_id}: 작업자 배정 해제")
        return {"message": "작업자 배정이 해제되었습니다"}
    
    # 새 작업자 존재 확인
    new_worker = db.query(BlogWorker).get(worker_id)
    if not new_worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    # 기존 작업자와 동일하면 변경 없음
    if old_worker_id == worker_id:
        return {"message": "이미 해당 작업자에게 배정되어 있습니다"}
    
    # 새 작업자의 현재 계정 수 확인
    current_accounts = db.query(BlogAccount).filter(
        BlogAccount.assigned_worker_id == worker_id
    ).order_by(BlogAccount.assignment_order).all()
    
    # assignment_order 계산 (기존 계정 수 + 1)
    new_order = len(current_accounts) + 1
    
    # 계정 재배정
    account.assigned_worker_id = worker_id
    account.assignment_order = new_order
    
    db.commit()
    
    worker_name = new_worker.user.username if new_worker.user else f"작업자 #{worker_id}"
    print(f"✅ [ASSIGN] 계정 {account.account_id}: {worker_name}에게 배정 (순서: {new_order})")
    
    return {
        "message": f"계정이 {worker_name}에게 배정되었습니다",
        "worker_name": worker_name,
        "assignment_order": new_order
    }


@router.delete("/blog/api/accounts/{account_id}")
def delete_blog_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 계정 삭제"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    account = db.query(BlogAccount).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    
    try:
        # 0단계: 이 계정으로 작성된 글이 있는지 확인
        existing_posts = db.query(BlogPost).filter(
            BlogPost.blog_account_id == account_id
        ).count()
        
        if existing_posts > 0:
            print(f"⚠️ [DELETE ACCOUNT] 계정 {account.account_id}: 작성된 글 {existing_posts}개 있음 → 삭제 불가")
            raise HTTPException(
                status_code=400, 
                detail=f"이 계정으로 작성된 글이 {existing_posts}개 있어 삭제할 수 없습니다.\n"
                       f"계정 상태를 '비활성'으로 변경하거나, 먼저 글을 삭제해주세요."
            )
        
        # ⭐ 1단계: 해당 계정으로 배정된 미완료 작업 삭제 (NOT NULL 제약조건 때문)
        related_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.blog_account_id == account_id,
            BlogWorkTask.status.in_(['pending', 'in_progress'])
        ).all()
        
        if related_tasks:
            print(f"⚠️ [DELETE ACCOUNT] 계정 {account.account_id}: 미완료 작업 {len(related_tasks)}개 발견")
            
            # ⭐ blog_account_id가 NOT NULL이므로 작업 자체를 삭제
            for task in related_tasks:
                # 관련된 진행상황도 확인
                progress = db.query(BlogKeywordProgress).filter(
                    BlogKeywordProgress.worker_id == task.worker_id,
                    BlogKeywordProgress.marketing_product_id == task.marketing_product_id,
                    BlogKeywordProgress.keyword_text == task.keyword_text
                ).first()
                
                if progress and not progress.is_completed:
                    # 미완료 진행상황도 삭제
                    db.delete(progress)
                    print(f"   - 진행상황 삭제: {task.keyword_text}")
                
                db.delete(task)
            
            print(f"🗑️ [DELETE ACCOUNT] 미완료 작업 {len(related_tasks)}개 삭제")
        
        # 2단계: 완료된 작업 확인 (completed_post_id가 있는 경우)
        completed_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.blog_account_id == account_id,
            BlogWorkTask.status == 'completed'
        ).count()
        
        if completed_tasks > 0:
            print(f"⚠️ [DELETE ACCOUNT] 계정 {account.account_id}: 완료된 작업 {completed_tasks}개 있음 → 삭제 불가")
            raise HTTPException(
                status_code=400,
                detail=f"이 계정으로 완료된 작업이 {completed_tasks}개 있어 삭제할 수 없습니다.\n"
                       f"계정 상태를 '비활성'으로 변경해주세요."
            )
        
        # 3단계: 배정된 작업자 정보 저장
        assigned_worker = None
        if account.assigned_worker_id:
            assigned_worker = db.query(BlogWorker).get(account.assigned_worker_id)
            worker_name = assigned_worker.user.username if assigned_worker else "알 수 없음"
            print(f"🔄 [DELETE ACCOUNT] 계정 {account.account_id}: 작업자 {worker_name}에서 배정 해제")
        
        # 4단계: 계정 삭제
        db.delete(account)
        db.flush()
        
        # 5단계: 작업자에게 자동으로 다른 계정 재배정
        if assigned_worker:
            try:
                print(f"🔄 [DELETE ACCOUNT] 작업자 {assigned_worker.user.username}에게 계정 자동 재배정 시도...")
                update_worker_accounts(assigned_worker, db)
                print(f"✅ [DELETE ACCOUNT] 작업자에게 새 계정 자동 배정 완료")
            except HTTPException as e:
                print(f"⚠️ [DELETE ACCOUNT] 자동 재배정 실패: {e.detail}")
                db.commit()
                
                return {
                    "message": f"계정이 삭제되었습니다.\n⚠️ 경고: {e.detail}",
                    "warning": True
                }
        
        db.commit()
        
        print(f"✅ [DELETE ACCOUNT] 계정 {account.account_id} 삭제 완료")
        
        message = "계정이 삭제되었습니다."
        if related_tasks:
            message += f"\n미완료 작업 {len(related_tasks)}개도 함께 삭제되었습니다."
        if assigned_worker:
            message += f"\n작업자에게 자동으로 새 계정이 배정되었습니다."
        
        return {"message": message, "warning": False}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ [DELETE ACCOUNT] 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"삭제 중 오류 발생: {str(e)}")

# ============================================
# 작업자 관리 API
# ============================================

@router.get("/blog/api/workers")
def get_blog_workers(request: Request, db: Session = Depends(get_db)):
    """블로그 작업자 목록"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    workers = db.query(BlogWorker).order_by(BlogWorker.id).all()
    
    result = []
    for worker in workers:
        # ⭐ 안전하게 상품 이름 가져오기
        current_product_name = None
        if worker.current_product_id:
            marketing_product = db.query(MarketingProduct).filter(
                MarketingProduct.id == worker.current_product_id
            ).first()
            
            if marketing_product and marketing_product.product_id:
                product = db.query(Product).filter(
                    Product.id == marketing_product.product_id
                ).first()
                current_product_name = product.name if product else f"상품 #{marketing_product.id}"
            elif marketing_product:
                current_product_name = f"마케팅상품 #{marketing_product.id}"
        
        # 진행률 계산
        if worker.current_product_id:
            total_keywords = db.query(BlogProductKeyword).filter(
                BlogProductKeyword.marketing_product_id == worker.current_product_id,
                BlogProductKeyword.is_active == True
            ).count()
            
            completed_keywords = db.query(BlogKeywordProgress).filter(
                BlogKeywordProgress.worker_id == worker.id,
                BlogKeywordProgress.marketing_product_id == worker.current_product_id,
                BlogKeywordProgress.is_completed == True
            ).count()
            
            progress = f"{completed_keywords}/{total_keywords}"
            progress_percent = round(completed_keywords / total_keywords * 100, 1) if total_keywords > 0 else 0
        else:
            progress = "0/0"
            progress_percent = 0
        
        result.append({
            "id": worker.id,
            "username": worker.user.username,  # ⭐ relationship 있으면 이대로 사용 가능
            "user_id": worker.user_id,
            "accounts": [acc.account_id for acc in worker.blog_accounts],  # ⭐ relationship 있으면 이대로
            "current_product": current_product_name,  # ⭐ 수정된 부분
            "progress": progress,
            "progress_percent": progress_percent,
            "daily_quota": worker.daily_quota,
            "status": worker.status,
            "is_blog_manager": worker.is_blog_manager
        })
    
    return result


@router.get("/blog/api/available-users")
def get_available_users(request: Request, db: Session = Depends(get_db)):
    """블로그 작업자로 추가 가능한 사용자 목록"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 마케팅 권한이 있고, 아직 블로그 작업자가 아닌 사용자
    existing_worker_ids = db.query(BlogWorker.user_id).all()
    existing_worker_ids = [w[0] for w in existing_worker_ids]
    
    users = db.query(User).filter(
        User.can_manage_marketing == True,
        User.id.notin_(existing_worker_ids)
    ).all()
    
    return [{"id": u.id, "username": u.username} for u in users]


@router.post("/blog/api/workers")
def create_blog_worker(
    user_id: int = Form(...),
    daily_quota: int = Form(...),
    product_id: int = Form(...),
    is_blog_manager: bool = Form(False),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """블로그 작업자 추가"""
    admin_user = get_current_user(request, db)
    
    if not check_is_blog_manager(admin_user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 사용자 존재 확인
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    # 이미 작업자인지 확인
    existing = db.query(BlogWorker).filter(
        BlogWorker.user_id == user_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="이미 블로그 작업자입니다")
    
    # 작업자 생성
    worker = BlogWorker(
        user_id=user_id,
        daily_quota=daily_quota,
        current_product_id=product_id,
        is_blog_manager=is_blog_manager,
        status='active'
    )
    db.add(worker)
    db.flush()
    
    # 계정 자동 배정
    try:
        update_worker_accounts(worker, db)
    except HTTPException as e:
        db.rollback()
        raise e
    
    db.commit()
    
    return {"message": "작업자 추가 완료", "worker_id": worker.id}


@router.put("/blog/api/workers/{worker_id}/quota")
def update_worker_quota(
    worker_id: int,
    daily_quota: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """작업자 할당량 변경"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(BlogWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    worker.daily_quota = daily_quota
    
    # 계정 자동 재배정
    try:
        update_worker_accounts(worker, db)
    except HTTPException as e:
        db.rollback()
        raise e
    
    db.commit()
    
    return {"message": "할당량 변경 완료"}


@router.put("/blog/api/workers/{worker_id}/status")
def update_worker_status(
    worker_id: int,
    status: str = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """작업자 상태 변경"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(BlogWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    worker.status = status
    db.commit()
    
    return {"message": "상태 변경 완료"}


@router.put("/blog/api/workers/{worker_id}/product")
def update_worker_product(
    worker_id: int,
    product_id: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    
    """작업자 현재 상품 변경"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(BlogWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    worker.current_product_id = product_id
    db.commit()
    
    return {"message": "상품 변경 완료"}


@router.put("/blog/api/workers/{worker_id}/blog-manager")
def update_worker_blog_manager(
    worker_id: int,
    is_blog_manager: bool = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """작업자 블로그 관리자 권한 변경"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(BlogWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    # 자기 자신의 관리자 권한은 해제할 수 없음
    if worker.user_id == user.id and not is_blog_manager:
        raise HTTPException(
            status_code=400, 
            detail="자신의 관리자 권한은 해제할 수 없습니다"
        )
    
    worker.is_blog_manager = is_blog_manager
    db.commit()
    
    status_text = "관리자로 지정" if is_blog_manager else "일반 작업자로 변경"
    print(f"✅ [WORKER] {worker.user.username}: {status_text}")
    
    return {"message": f"{status_text}되었습니다"}


# ============================================
# 스케줄 자동 배정 (Cron Job용)
# ============================================

@router.post("/blog/api/schedule/auto-assign")
def auto_assign_daily_tasks(
    date: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """일일 작업 자동 배정 - 관리자는 전체, 일반 작업자는 자기 자신만"""
    user = get_current_user(request, db)
    
    # 접근 권한 체크
    has_access, blog_worker_or_error = check_blog_access(user, db)
    if not has_access:
        raise HTTPException(status_code=403, detail=blog_worker_or_error)
    
    blog_worker = blog_worker_or_error if not user.is_admin else db.query(BlogWorker).filter(
        BlogWorker.user_id == user.id
    ).first()
    
    is_manager = check_is_blog_manager(user, db)
    
    # 날짜 설정
    if date:
        try:
            task_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            task_date = date.today()
    else:
        task_date = date.today()
    
    print("=" * 80)
    print(f"🔍 [AUTO-ASSIGN] 작업 배정 시작")
    print(f"   - 사용자: {user.username}")
    print(f"   - is_manager: {is_manager}")
    print(f"   - 날짜: {task_date}")
    print("=" * 80)
    
    # 이미 배정된 작업이 있는지 확인
    if is_manager:
        existing = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == task_date
        ).first()
        
        if existing:
            print(f"⚠️ [AUTO-ASSIGN] {task_date}에 이미 작업 배정됨")
            raise HTTPException(
                status_code=400, 
                detail=f"{task_date} 날짜에 이미 배정된 작업이 있습니다"
            )
    else:
        existing = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == task_date,
            BlogWorkTask.worker_id == blog_worker.id
        ).first()
        
        if existing:
            print(f"⚠️ [AUTO-ASSIGN] {user.username}에게 {task_date} 작업 이미 배정됨")
            raise HTTPException(
                status_code=400, 
                detail=f"{task_date} 날짜에 이미 배정된 작업이 있습니다"
            )
    
    # 작업자 필터링
    if is_manager:
        active_workers = db.query(BlogWorker).filter(
            BlogWorker.status == 'active'
        ).all()
        print(f"📋 [AUTO-ASSIGN] 관리자 모드 - 전체 활성 작업자 {len(active_workers)}명")
    else:
        active_workers = [blog_worker]
        print(f"📋 [AUTO-ASSIGN] 일반 작업자 모드 - {user.username}에게만 배정")
    
    if not active_workers:
        print(f"⚠️ [AUTO-ASSIGN] 활성 작업자 없음!")
        raise HTTPException(status_code=400, detail="활성 작업자가 없습니다")
    
    # ⭐⭐⭐ 핵심 수정: 해당 날짜에 이미 배정된 키워드 조회 ⭐⭐⭐
    already_assigned = db.query(BlogWorkTask.keyword_text).filter(
        BlogWorkTask.task_date == task_date
    ).all()
    today_assigned_keywords = {k[0] for k in already_assigned}
    
    print(f"🔍 [AUTO-ASSIGN] {task_date}에 이미 배정된 키워드: {len(today_assigned_keywords)}개")
    if today_assigned_keywords:
        print(f"   키워드 목록: {list(today_assigned_keywords)[:5]}{'...' if len(today_assigned_keywords) > 5 else ''}")
    
    total_assigned = 0
    
    for worker in active_workers:
        print(f"\n📋 [AUTO-ASSIGN] 작업자: {worker.user.username} (ID: {worker.id})")
        print(f"   - current_product_id: {worker.current_product_id}")
        print(f"   - daily_quota: {worker.daily_quota}")
        
        if not worker.current_product_id:
            print(f"   ⚠️ 상품이 설정되지 않음 → 스킵")
            continue
        
        if worker.daily_quota <= 0:
            print(f"   ⚠️ 작업량이 0 → 스킵")
            continue
        
        # 이 상품의 활성 키워드
        active_kws = db.query(BlogProductKeyword.keyword_text).filter(
            BlogProductKeyword.marketing_product_id == worker.current_product_id,
            BlogProductKeyword.is_active == True
        ).all()
        active_keywords = {k[0] for k in active_kws}
        print(f"   - 활성 키워드: {len(active_keywords)}개")
        
        
        if len(active_keywords) == 0:
            print(f"   ⚠️ 활성 키워드 없음 → 스킵")
            continue
        
        # 작업자의 블로그 계정들
        accounts = db.query(BlogAccount).filter(
            BlogAccount.assigned_worker_id == worker.id
        ).order_by(BlogAccount.assignment_order).all()
        
        print(f"   - 배정된 계정: {len(accounts)}개")
        
        if not accounts:
            print(f"   ⚠️ 배정된 계정 없음 → 스킵")
            continue
        
        # ⭐⭐⭐ 핵심 변경: 각 계정별로 사용 가능한 키워드 계산 ⭐⭐⭐
        account_available_keywords = {}
        
        for account in accounts:
            # 이 계정으로 이미 작성된 키워드 조회
            used_in_account = db.query(BlogPost.keyword_text).filter(
                BlogPost.blog_account_id == account.id,
                BlogPost.marketing_product_id == worker.current_product_id
            ).distinct().all()
            used_keywords = {k[0] for k in used_in_account}
            
            # 이 계정에서 사용 가능한 키워드 = 활성 키워드 - 이미 사용한 키워드 - 오늘 배정된 키워드
            available_for_account = active_keywords - used_keywords - today_assigned_keywords
            account_available_keywords[account.id] = available_for_account
            
            print(f"   - 계정 {account.account_id}: 사용함={len(used_keywords)}개, 사용 가능={len(available_for_account)}개")
        
        # 모든 계정에서 사용 가능한 키워드 합산
        total_available = set()
        for keywords in account_available_keywords.values():
            total_available.update(keywords)
        
        print(f"   - 전체 배정 가능 키워드: {len(total_available)}개")
        
        if len(total_available) == 0:
            print(f"   ⚠️ 배정 가능한 키워드 없음 → 스킵")
            continue
        
        # ⭐ 계정별로 작업 배정 (각 계정당 최대 3개, 계정별로 사용 가능한 키워드만)
        assigned_for_worker = 0
        remaining_quota = worker.daily_quota
        
        for account in accounts:
            if remaining_quota <= 0:
                break
            
            # 이 계정에서 사용 가능한 키워드
            available = list(account_available_keywords.get(account.id, set()))
            
            if not available:
                print(f"   - 계정 {account.account_id}: 사용 가능한 키워드 없음")
                continue
            
            # 이 계정에 배정할 개수 (최대 3개)
            count_for_account = min(3, len(available), remaining_quota)
            selected_for_account = random.sample(available, count_for_account)
            
            print(f"   - 계정 {account.account_id}: {count_for_account}개 키워드 배정 - {selected_for_account}")
            
            for keyword in selected_for_account:
                task = BlogWorkTask(
                    task_date=task_date,
                    status='pending',
                    keyword_text=keyword,
                    worker_id=worker.id,
                    marketing_product_id=worker.current_product_id,
                    blog_account_id=account.id
                )
                db.add(task)
                assigned_for_worker += 1
                remaining_quota -= 1
                
                # 진행 상황 기록 (선택사항 - 유지)
                progress = db.query(BlogKeywordProgress).filter(
                    BlogKeywordProgress.worker_id == worker.id,
                    BlogKeywordProgress.marketing_product_id == worker.current_product_id,
                    BlogKeywordProgress.keyword_text == keyword
                ).first()
                
                if not progress:
                    progress = BlogKeywordProgress(
                        worker_id=worker.id,
                        marketing_product_id=worker.current_product_id,
                        keyword_text=keyword,
                        is_completed=False
                    )
                    db.add(progress)
                
                # ⭐ 배정된 키워드를 today_assigned_keywords에 추가
                today_assigned_keywords.add(keyword)
        
        print(f"   ✅ 이 작업자에게 {assigned_for_worker}개 작업 배정")
        total_assigned += assigned_for_worker
    
    db.commit()
    
    print("=" * 80)
    print(f"✅ [AUTO-ASSIGN] 총 {total_assigned}개 작업 배정 완료")
    print(f"✅ [AUTO-ASSIGN] 최종 배정된 키워드 수: {len(today_assigned_keywords)}개")
    print("=" * 80)
    
    if is_manager:
        message = f"{task_date} 전체 작업 배정 완료 (총 {total_assigned}개)"
    else:
        message = f"{task_date} 내 작업 배정 완료 (총 {total_assigned}개)"
    
    return {
        "message": message,
        "assigned_count": total_assigned,
        "workers_count": len(active_workers)
    }
    
@router.delete("/blog/api/workers/{worker_id}")
def delete_blog_worker(worker_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 작업자 삭제"""
    user = get_current_user(request, db)
    
    if not check_is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(BlogWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    try:
        # ⭐ 1단계: 관련된 blog_keyword_progress 레코드 먼저 삭제
        deleted_progress = db.query(BlogKeywordProgress).filter(
            BlogKeywordProgress.worker_id == worker_id
        ).delete()
        print(f"🗑️ [DELETE WORKER] 진행상황 {deleted_progress}개 삭제")
        
        # ⭐ 2단계: 관련된 blog_work_task 레코드 삭제 또는 worker_id 해제
        related_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.worker_id == worker_id
        ).all()
        
        for task in related_tasks:
            task.worker_id = None
            task.status = 'pending'
            db.add(task)
        
        print(f"🔄 [DELETE WORKER] 작업 {len(related_tasks)}개 worker_id 해제")
        
        # ⭐ 3단계: 배정된 계정 모두 해제
        accounts = db.query(BlogAccount).filter(
            BlogAccount.assigned_worker_id == worker_id
        ).all()
        
        for account in accounts:
            account.assigned_worker_id = None
            account.assignment_order = None
            db.add(account)
        
        print(f"🔄 [DELETE WORKER] 계정 {len(accounts)}개 배정 해제")
        
        # ⭐ 4단계: 작업자 삭제
        db.delete(worker)
        db.commit()
        
        print(f"✅ [DELETE WORKER] 작업자 ID {worker_id} 삭제 완료")
        
        return {"message": "작업자가 삭제되었습니다. 관련 데이터도 정리되었습니다."}
        
    except Exception as e:
        db.rollback()
        print(f"❌ [DELETE WORKER] 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"삭제 중 오류 발생: {str(e)}")