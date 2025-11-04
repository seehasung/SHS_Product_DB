from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from typing import List, Optional
from datetime import datetime, date, timedelta
import random
import math
import os
import uuid
from pathlib import Path

# 기존 database.py에서 import
from database import (
    get_db, User, MarketingProduct,
    BlogWorker, BlogAccount, BlogProductKeyword, BlogPost, BlogPostImage,
    BlogKeywordProgress, BlogWorkTask, BlogPostSchedule
)

router = APIRouter()

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

def is_blog_manager(user: User, db: Session):
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
    
    is_manager = is_blog_manager(user, db)
    
    return templates.TemplateResponse("marketing_blog.html", {
        "request": request,
        "user": user,
        "blog_worker": blog_worker,
        "is_manager": is_manager
    })


# ============================================
# 전체 현황 API
# ============================================

@router.get("/blog/api/dashboard")
def get_dashboard_stats(request: Request, db: Session = Depends(get_db)):
    """전체 현황 통계"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=blog_worker_or_error)
    
    blog_worker = blog_worker_or_error if not user.is_admin else None
    is_manager = is_blog_manager(user, db)
    
    today = date.today()
    
    # 오늘의 작업 통계
    if is_manager:
        # 관리자: 전체 통계
        total_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == today
        ).count()
        
        completed_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == today,
            BlogWorkTask.status == 'completed'
        ).count()
    else:
        # 일반 작업자: 내 작업만
        total_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == today,
            BlogWorkTask.worker_id == blog_worker.id
        ).count()
        
        completed_tasks = db.query(BlogWorkTask).filter(
            BlogWorkTask.task_date == today,
            BlogWorkTask.worker_id == blog_worker.id,
            BlogWorkTask.status == 'completed'
        ).count()
    
    progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # 전체 글 수
    if is_manager:
        total_posts = db.query(BlogPost).count()
        today_posts = db.query(BlogPost).filter(
            func.date(BlogPost.created_at) == today
        ).count()
    else:
        total_posts = db.query(BlogPost).filter(
            BlogPost.worker_id == blog_worker.id
        ).count()
        today_posts = db.query(BlogPost).filter(
            BlogPost.worker_id == blog_worker.id,
            func.date(BlogPost.created_at) == today
        ).count()
    
    # 활성 작업자 수
    active_workers = db.query(BlogWorker).filter(
        BlogWorker.status == 'active'
    ).count()
    
    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "progress": round(progress, 1),
        "total_posts": total_posts,
        "today_posts": today_posts,
        "active_workers": active_workers
    }


@router.get("/blog/api/tasks/today")
def get_today_tasks(request: Request, db: Session = Depends(get_db)):
    """오늘의 작업 목록"""
    user = get_current_user(request, db)
    has_access, blog_worker_or_error = check_blog_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=blog_worker_or_error)
    
    blog_worker = blog_worker_or_error if not user.is_admin else None
    is_manager = is_blog_manager(user, db)
    
    today = date.today()
    
    # 작업 목록 조회
    query = db.query(BlogWorkTask).filter(
        BlogWorkTask.task_date == today
    )
    
    # 일반 작업자는 자신의 작업만
    if not is_manager and blog_worker:
        query = query.filter(BlogWorkTask.worker_id == blog_worker.id)
    
    tasks = query.order_by(BlogWorkTask.id).all()
    
    result = []
    for task in tasks:
        result.append({
            "id": task.id,
            "keyword": task.keyword_text,
            "product_name": task.marketing_product.name if task.marketing_product else "",
            "worker_name": task.worker.user.username if task.worker else "",
            "account_id": task.blog_account.account_id if task.blog_account else "",
            "status": task.status,
            "post_id": task.completed_post_id
        })
    
    return result


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
        # ⭐ product_id로 Product 조회
        product = None
        if hasattr(mp, 'product_id') and mp.product_id:
            product = db.query(Product).filter(Product.id == mp.product_id).first()
        
        # MarketingProduct의 기본 키워드
        base_keywords = mp.keywords if isinstance(mp.keywords, list) else []
        
        # 블로그용 키워드 설정 조회
        blog_keywords = db.query(BlogProductKeyword).filter(
            BlogProductKeyword.marketing_product_id == mp.id
        ).order_by(BlogProductKeyword.order_index).all()
        
        keywords_info = []
        for bk in blog_keywords:
            keywords_info.append({
                "id": bk.id,
                "text": bk.keyword_text,
                "is_active": bk.is_active,
                "order_index": bk.order_index
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
    
    if not is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    product = db.query(MarketingProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    # 기존 블로그 키워드 삭제
    db.query(BlogProductKeyword).filter(
        BlogProductKeyword.marketing_product_id == product_id
    ).delete()
    
    # 새로 생성
    keywords = product.keywords if isinstance(product.keywords, list) else []
    for i, keyword in enumerate(keywords):
        blog_keyword = BlogProductKeyword(
            marketing_product_id=product_id,
            keyword_text=keyword,
            is_active=True,
            order_index=i
        )
        db.add(blog_keyword)
    
    db.commit()
    
    return {"message": "키워드 동기화 완료"}


@router.put("/blog/api/keywords/{keyword_id}/toggle")
def toggle_keyword_active(keyword_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 키워드 ON/OFF 토글"""
    user = get_current_user(request, db)
    
    if not is_blog_manager(user, db):
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
    is_manager = is_blog_manager(user, db)
    
    query = db.query(BlogPost)
    
    # 일반 작업자는 자신의 글만
    if not is_manager and blog_worker:
        query = query.filter(BlogPost.worker_id == blog_worker.id)
    
    posts = query.order_by(desc(BlogPost.created_at)).all()
    
    result = []
    for post in posts:
        result.append({
            "id": post.id,
            "title": post.post_title,
            "keyword": post.keyword_text,
            "product_name": post.marketing_product.name if post.marketing_product else "",
            "worker_name": post.worker.user.username if post.worker else "",
            "account_id": post.blog_account.account_id if post.blog_account else "",
            "char_count": post.char_count,
            "image_count": post.image_count,
            "keyword_count": post.keyword_count,
            "images": [{"path": img.image_path, "filename": img.image_filename} for img in post.images],
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
    
    # 권한 체크 (일반 작업자는 자신의 작업만)
    if not is_blog_manager(user, db) and task.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 통계 계산
    char_count = len(body)
    keyword_count = count_keyword_occurrences(title + " " + body, task.keyword_text)
    
    # 블로그 글 생성
    blog_post = BlogPost(
        post_title=title,
        post_body=body,
        keyword_text=task.keyword_text,
        post_url=post_url,
        char_count=char_count,
        image_count=0,  # 이미지 저장 후 업데이트
        keyword_count=keyword_count,
        marketing_product_id=task.marketing_product_id,
        worker_id=task.worker_id,
        blog_account_id=task.blog_account_id,
        is_registration_complete=True
    )
    db.add(blog_post)
    db.flush()  # ID 생성
    
    # 이미지 저장
    if images:
        # 이미지 저장 디렉토리
        upload_dir = Path("static/uploads/blog_images")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        for i, image in enumerate(images):
            if image.filename:
                # 고유 파일명 생성
                ext = os.path.splitext(image.filename)[1]
                filename = f"{uuid.uuid4()}{ext}"
                filepath = upload_dir / filename
                
                # 파일 저장
                with open(filepath, "wb") as f:
                    content = await image.read()
                    f.write(content)
                
                # DB에 기록
                blog_image = BlogPostImage(
                    blog_post_id=blog_post.id,
                    image_path=str(filepath),
                    image_filename=filename,
                    image_order=i
                )
                db.add(blog_image)
        
        # 이미지 개수 업데이트
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
    if not is_blog_manager(user, db) and blog_worker and post.worker_id != blog_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    return {
        "id": post.id,
        "title": post.post_title,
        "body": post.post_body,
        "keyword": post.keyword_text,
        "post_url": post.post_url,
        "char_count": post.char_count,
        "image_count": post.image_count,
        "keyword_count": post.keyword_count,
        "images": [{"path": img.image_path, "filename": img.image_filename} for img in post.images],
        "product_name": post.marketing_product.name,
        "worker_name": post.worker.user.username,
        "account_id": post.blog_account.account_id,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M")
    }


@router.delete("/blog/api/posts/{post_id}")
def delete_blog_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 글 삭제"""
    user = get_current_user(request, db)
    
    if not is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    post = db.query(BlogPost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 이미지 파일 삭제
    for image in post.images:
        try:
            os.remove(image.image_path)
        except:
            pass
    
    db.delete(post)
    db.commit()
    
    return {"message": "글 삭제 완료"}


# ============================================
# 계정 관리 API
# ============================================

@router.get("/blog/api/accounts")
def get_blog_accounts(request: Request, db: Session = Depends(get_db)):
    """블로그 계정 목록"""
    user = get_current_user(request, db)
    
    if not is_blog_manager(user, db):
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
    
    if not is_blog_manager(user, db):
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
    
    if not is_blog_manager(user, db):
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


@router.delete("/blog/api/accounts/{account_id}")
def delete_blog_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    """블로그 계정 삭제"""
    user = get_current_user(request, db)
    
    if not is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    account = db.query(BlogAccount).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    
    # 배정된 작업자가 있으면 삭제 불가
    if account.assigned_worker_id:
        raise HTTPException(status_code=400, detail="작업자가 배정된 계정은 삭제할 수 없습니다")
    
    db.delete(account)
    db.commit()
    
    return {"message": "계정 삭제 완료"}


# ============================================
# 작업자 관리 API
# ============================================

@router.get("/blog/api/workers")
def get_blog_workers(request: Request, db: Session = Depends(get_db)):
    """블로그 작업자 목록"""
    user = get_current_user(request, db)
    
    if not is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    workers = db.query(BlogWorker).order_by(BlogWorker.id).all()
    
    result = []
    for worker in workers:
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
            "username": worker.user.username,
            "user_id": worker.user_id,
            "accounts": [acc.account_id for acc in worker.blog_accounts],
            "current_product": worker.current_product.name if worker.current_product else None,
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
    
    if not is_blog_manager(user, db):
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
    
    if not is_blog_manager(admin_user, db):
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
    
    if not is_blog_manager(user, db):
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
    
    if not is_blog_manager(user, db):
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
    
    if not is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(BlogWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    worker.current_product_id = product_id
    db.commit()
    
    return {"message": "상품 변경 완료"}


# ============================================
# 스케줄 자동 배정 (Cron Job용)
# ============================================

@router.post("/blog/api/schedule/auto-assign")
def auto_assign_daily_tasks(
    target_date: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """일일 작업 자동 배정"""
    user = get_current_user(request, db)
    
    if not is_blog_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 날짜 설정
    if target_date:
        task_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        task_date = date.today()
    
    # 이미 배정된 작업이 있는지 확인
    existing = db.query(BlogWorkTask).filter(
        BlogWorkTask.task_date == task_date
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="이미 배정된 작업이 있습니다")
    
    # 활성 작업자 조회
    active_workers = db.query(BlogWorker).filter(
        BlogWorker.status == 'active'
    ).all()
    
    if not active_workers:
        raise HTTPException(status_code=400, detail="활성 작업자가 없습니다")
    
    # 오늘 배정된 키워드 (중복 방지)
    today_assigned_keywords = set()
    
    for worker in active_workers:
        if not worker.current_product_id:
            continue
        
        # 이 작업자가 아직 안 쓴 키워드 조회
        completed = db.query(BlogKeywordProgress.keyword_text).filter(
            BlogKeywordProgress.worker_id == worker.id,
            BlogKeywordProgress.marketing_product_id == worker.current_product_id,
            BlogKeywordProgress.is_completed == True
        ).all()
        completed_keywords = {k[0] for k in completed}
        
        # 이 상품의 활성 키워드
        active_kws = db.query(BlogProductKeyword.keyword_text).filter(
            BlogProductKeyword.marketing_product_id == worker.current_product_id,
            BlogProductKeyword.is_active == True
        ).all()
        active_keywords = {k[0] for k in active_kws}
        
        # 아직 안 쓴 키워드
        unused = active_keywords - completed_keywords
        
        # 오늘 다른 작업자가 배정받은 키워드 제외
        available = unused - today_assigned_keywords
        
        if not available:
            # 사용 가능한 키워드 없음 → 다음 상품으로 이동
            continue
        
        # 할당량만큼 랜덤 선택
        quota = min(worker.daily_quota, len(available))
        selected = random.sample(list(available), quota)
        
        # 작업자의 블로그 계정들
        accounts = db.query(BlogAccount).filter(
            BlogAccount.assigned_worker_id == worker.id
        ).order_by(BlogAccount.assignment_order).all()
        
        if not accounts:
            continue
        
        # 계정별 작업 분배 (계정당 최대 3개)
        account_idx = 0
        account_post_count = {}
        
        for keyword in selected:
            # 현재 계정이 3개 다 찼으면 다음 계정으로
            if account_post_count.get(account_idx, 0) >= 3:
                account_idx += 1
                if account_idx >= len(accounts):
                    break
            
            task = BlogWorkTask(
                task_date=task_date,
                status='pending',
                keyword_text=keyword,
                worker_id=worker.id,
                marketing_product_id=worker.current_product_id,
                blog_account_id=accounts[account_idx].id
            )
            db.add(task)
            
            # 진행 상황에도 기록 (아직 없다면)
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
            
            today_assigned_keywords.add(keyword)
            account_post_count[account_idx] = account_post_count.get(account_idx, 0) + 1
        
        # 이 상품의 모든 키워드 완료 체크
        if len(unused) <= worker.daily_quota:
            # TODO: 다음 상품으로 자동 이동 로직
            pass
    
    db.commit()
    
    return {"message": f"{task_date} 작업 배정 완료", "assigned_count": len(today_assigned_keywords)}