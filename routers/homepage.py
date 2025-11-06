from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from typing import List, Optional
from datetime import datetime, date, timedelta
import random
import math
import re
import os
import uuid
from pathlib import Path

# 기존 database.py에서 import
from database import (
    get_db, User, MarketingProduct, Product,
    HomepageWorker, HomepageAccount, HomepageProductKeyword, HomepagePost, HomepagePostImage,
    HomepageKeywordProgress, HomepageWorkTask, HomepagePostSchedule
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
        print(f"❌ [HOMEPAGE] 세션에 'user' 키 없음. 세션 내용: {dict(request.session)}")
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    
    # 사용자 조회
    user = db.query(User).filter(User.username == username).first()
    if not user:
        print(f"❌ [HOMEPAGE] 사용자 '{username}' DB에 없음")
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    print(f"✅ [HOMEPAGE] 사용자 인증 성공: {user.username} (ID: {user.id})")
    return user


def check_homepage_access(user: User, db: Session):
    """통페이지 접근 권한 체크"""
    # 전체 관리자는 항상 접근 가능
    if user.is_admin:
        # 통페이지 작업자 프로필 자동 생성
        homepage_worker = db.query(HomepageWorker).filter(
            HomepageWorker.user_id == user.id
        ).first()
        
        if not homepage_worker:
            homepage_worker = HomepageWorker(
                user_id=user.id,
                status='active',
                daily_quota=0,
                is_homepage_manager=True
            )
            db.add(homepage_worker)
            db.commit()
            db.refresh(homepage_worker)
        
        return True, homepage_worker
    
    # 마케팅 권한 체크
    if not user.can_manage_marketing:
        return False, "마케팅 권한이 필요합니다"
    
    # 통페이지 작업자 등록 여부 체크
    homepage_worker = db.query(HomepageWorker).filter(
        HomepageWorker.user_id == user.id,
        HomepageWorker.status == 'active'
    ).first()
    
    if not homepage_worker:
        return False, "통페이지 작업자로 등록되지 않았습니다"
    
    return True, homepage_worker

def check_is_homepage_manager(user: User, db: Session):
    """통페이지 관리자 여부 체크"""
    if user.is_admin:
        return True
    
    homepage_worker = db.query(HomepageWorker).filter(
        HomepageWorker.user_id == user.id
    ).first()
    
    return homepage_worker and homepage_worker.is_homepage_manager

def count_keyword_occurrences(text: str, keyword: str):
    """텍스트에서 키워드 출현 횟수 세기"""
    return text.lower().count(keyword.lower())

def count_chars_without_spaces(text: str):
    """공백과 특수문자를 제외한 순수 글자 수 세기 (한글, 영문, 숫자만)"""
    import re
    # 한글, 영문, 숫자만 남기고 나머지 모두 제거
    pure_text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
    return len(pure_text)


def update_worker_accounts(worker: HomepageWorker, db: Session):
    """작업자의 할당량에 따라 통페이지 계정 자동 배정/해제"""
    required = worker.required_accounts
    
    # 현재 배정된 계정 수
    current_accounts = db.query(HomepageAccount).filter(
        HomepageAccount.assigned_worker_id == worker.id
    ).order_by(HomepageAccount.assignment_order).all()
    
    current_count = len(current_accounts)
    
    # 계정 추가 필요
    if required > current_count:
        additional = required - current_count
        
        # 미배정 계정 찾기
        available = db.query(HomepageAccount).filter(
            HomepageAccount.assigned_worker_id == None,
            HomepageAccount.status == 'active'
        ).limit(additional).all()
        
        if len(available) < additional:
            raise HTTPException(
                status_code=400,
                detail=f"사용 가능한 통페이지 계정이 부족합니다. (필요: {additional}개, 사용 가능: {len(available)}개)"
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

@router.get("/marketing/homepage")  # ⭐ /homepage → /marketing/homepage 로 변경
def homepage_main_page(request: Request, db: Session = Depends(get_db)):
    """통페이지 메인 페이지"""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    
    user = get_current_user(request, db)
    has_access, homepage_worker_or_error = check_homepage_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=homepage_worker_or_error)
    
    homepage_worker = homepage_worker_or_error if not user.is_admin else db.query(HomepageWorker).filter(
        HomepageWorker.user_id == user.id
    ).first()
    
    is_manager = check_is_homepage_manager(user, db)
    
    print("=" * 80)
    print(f"🔍 [HOMEPAGE PAGE] 사용자: {user.username}")
    print(f"🔍 [HOMEPAGE PAGE] user.is_admin: {user.is_admin}")
    print(f"🔍 [HOMEPAGE PAGE] homepage_worker: {homepage_worker}")
    if homepage_worker:
        print(f"🔍 [HOMEPAGE PAGE] homepage_worker.id: {homepage_worker.id}")
        print(f"🔍 [HOMEPAGE PAGE] homepage_worker.is_homepage_manager: {homepage_worker.is_homepage_manager}")
        print(f"🔍 [HOMEPAGE PAGE] homepage_worker.status: {homepage_worker.status}")
    print(f"🔍 [HOMEPAGE PAGE] is_manager (템플릿 전달값): {is_manager}")
    print("=" * 80)
    
    return templates.TemplateResponse("marketing_homepage.html", {
        "request": request,
        "user": user,
        "homepage_worker": homepage_worker,
        "is_manager": is_manager
    })
    
# ============================================
# 전체 현황 API
# ============================================

@router.get("/marketing/homepage/api/dashboard")
def get_dashboard_stats(request: Request, db: Session = Depends(get_db)):
    """전체 현황 통계"""
    user = get_current_user(request, db)
    has_access, homepage_worker_or_error = check_homepage_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403, detail=homepage_worker_or_error)
    
    homepage_worker = homepage_worker_or_error if not user.is_admin else None
    is_manager = check_is_homepage_manager(user, db)
    
    today = date.today()
    
    # 오늘의 작업 통계
    if is_manager:
        # 관리자: 전체 통계
        total_tasks = db.query(HomepageWorkTask).filter(
            HomepageWorkTask.task_date == today
        ).count()
        
        completed_tasks = db.query(HomepageWorkTask).filter(
            HomepageWorkTask.task_date == today,
            HomepageWorkTask.status == 'completed'
        ).count()
    else:
        # 일반 작업자: 내 작업만
        total_tasks = db.query(HomepageWorkTask).filter(
            HomepageWorkTask.task_date == today,
            HomepageWorkTask.worker_id == homepage_worker.id
        ).count()
        
        completed_tasks = db.query(HomepageWorkTask).filter(
            HomepageWorkTask.task_date == today,
            HomepageWorkTask.worker_id == homepage_worker.id,
            HomepageWorkTask.status == 'completed'
        ).count()
    
    progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # 전체 글 수
    if is_manager:
        total_posts = db.query(HomepagePost).count()
        today_posts = db.query(HomepagePost).filter(
            func.date(HomepagePost.created_at) == today
        ).count()
    else:
        total_posts = db.query(HomepagePost).filter(
            HomepagePost.worker_id == homepage_worker.id
        ).count()
        today_posts = db.query(HomepagePost).filter(
            HomepagePost.worker_id == homepage_worker.id,
            func.date(HomepagePost.created_at) == today
        ).count()
    
    # 활성 작업자 수
    active_workers = db.query(HomepageWorker).filter(
        HomepageWorker.status == 'active'
    ).count()
    
    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "progress": round(progress, 1),
        "total_posts": total_posts,
        "today_posts": today_posts,
        "active_workers": active_workers
    }

@router.get("/marketing/homepage/api/tasks/today")
def get_today_tasks(request: Request, db: Session = Depends(get_db)):
    """오늘의 작업 목록 조회"""
    user = get_current_user(request, db)
    
    today = date.today()
    
    # 기본 쿼리 (오늘 작업만)
    query = db.query(HomepageWorkTask).filter(HomepageWorkTask.task_date == today)
    
    # 관리자 체크
    is_manager = check_is_homepage_manager(user, db)
    
    # 일반 사용자는 자기 작업만 필터링
    if not is_manager:
        worker = db.query(HomepageWorker).filter(HomepageWorker.user_id == user.id).first()
        if worker:
            query = query.filter(HomepageWorkTask.worker_id == worker.id)
        else:
            # 작업자가 아니면 빈 결과 반환
            return []
    
    # 관리자는 모든 작업 표시
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
            worker_obj = db.query(HomepageWorker).filter(
                HomepageWorker.id == task.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        # 계정 ID 조회
        account_id = ""
        if task.homepage_account_id:
            account = db.query(HomepageAccount).filter(
                HomepageAccount.id == task.homepage_account_id
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

# ============================================
# 상품 관리 API
# ============================================

@router.get("/marketing/homepage/api/products")
def get_homepage_products(request: Request, db: Session = Depends(get_db)):
    """통페이지 상품 목록"""
    user = get_current_user(request, db)
    has_access, _ = check_homepage_access(user, db)
    
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
        
        # 통페이지용 키워드 설정 조회
        homepage_keywords = db.query(HomepageProductKeyword).filter(
            HomepageProductKeyword.marketing_product_id == mp.id
        ).order_by(HomepageProductKeyword.order_index).all()
        
        keywords_info = []
        for hk in homepage_keywords:
            keywords_info.append({
                "id": hk.id,
                "text": hk.keyword_text,
                "is_active": hk.is_active,
                "order_index": hk.order_index
            })
        
        result.append({
            "id": mp.id,
            "product_code": product.product_code if product else f"MP-{mp.id}",
            "name": product.name if product else f"마케팅 상품 #{mp.id}",
            "base_keywords": base_keywords,
            "homepage_keywords": keywords_info
        })
    
    return result

@router.post("/marketing/homepage/api/products/{product_id}/sync-keywords")
def sync_product_keywords(product_id: int, request: Request, db: Session = Depends(get_db)):
    """상품의 기본 키워드를 통페이지 키워드로 동기화"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    product = db.query(MarketingProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    # keywords 파싱
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
    
    # 기존 통페이지 키워드 삭제
    deleted_count = db.query(HomepageProductKeyword).filter(
        HomepageProductKeyword.marketing_product_id == product_id
    ).delete()
    print(f"🗑️ [SYNC] 기존 키워드 {deleted_count}개 삭제")
    
    # 새로 생성 (dict 또는 string 모두 처리)
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
            homepage_keyword = HomepageProductKeyword(
                marketing_product_id=product_id,
                keyword_text=keyword_text.strip(),
                is_active=is_active,
                order_index=i
            )
            db.add(homepage_keyword)
            added_count += 1
            print(f"➕ [SYNC] 키워드 추가: {keyword_text.strip()} (active={is_active})")
    
    db.commit()
    
    print(f"✅ [SYNC] 총 {added_count}개 키워드 동기화 완료")
    
    return {
        "message": f"키워드 동기화 완료 ({added_count}개)",
        "keyword_count": added_count
    }


@router.put("/marketing/homepage/api/keywords/{keyword_id}/toggle")
def toggle_keyword_active(keyword_id: int, request: Request, db: Session = Depends(get_db)):
    """통페이지 키워드 ON/OFF 토글"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    keyword = db.query(HomepageProductKeyword).get(keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다")
    
    keyword.is_active = not keyword.is_active
    db.commit()
    
    return {"is_active": keyword.is_active}


# ============================================
# 글 관리 API
# ============================================

@router.get("/marketing/homepage/api/posts")
def get_homepage_posts(request: Request, db: Session = Depends(get_db)):
    """통페이지 글 목록"""
    user = get_current_user(request, db)
    has_access, homepage_worker_or_error = check_homepage_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    homepage_worker = homepage_worker_or_error if not user.is_admin else None
    is_manager = check_is_homepage_manager(user, db)
    
    query = db.query(HomepagePost)
    
    # 일반 작업자는 자신의 글만
    if not is_manager and homepage_worker:
        query = query.filter(HomepagePost.worker_id == homepage_worker.id)
    
    posts = query.order_by(desc(HomepagePost.created_at)).all()
    
    result = []
    for post in posts:
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
            worker_obj = db.query(HomepageWorker).filter(
                HomepageWorker.id == post.worker_id
            ).first()
            if worker_obj and worker_obj.user:
                worker_name = worker_obj.user.username
        
        account_id = ""
        if post.homepage_account_id:
            account = db.query(HomepageAccount).filter(
                HomepageAccount.id == post.homepage_account_id
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
            "images": [{"path": img.image_path, "filename": img.image_filename} for img in post.images],
            "created_at": post.created_at.strftime("%Y-%m-%d %H:%M"),
            "post_url": post.post_url
        })
    
    return result


@router.post("/marketing/homepage/api/posts")
async def create_homepage_post(
    request: Request,
    task_id: int = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    post_url: str = Form(None),
    images: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """통페이지 글 작성"""
    user = get_current_user(request, db)
    has_access, homepage_worker_or_error = check_homepage_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    homepage_worker = homepage_worker_or_error if not user.is_admin else db.query(HomepageWorker).filter(
        HomepageWorker.user_id == user.id
    ).first()
    
    # 작업 조회
    task = db.query(HomepageWorkTask).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다")
    
    # 권한 체크 (일반 작업자는 자신의 작업만)
    if not check_is_homepage_manager(user, db) and task.worker_id != homepage_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 통계 계산
    char_count = count_chars_without_spaces(body)
    keyword_count = count_keyword_occurrences(title + " " + body, task.keyword_text)
    
    # 통페이지 글 생성
    homepage_post = HomepagePost(
        post_title=title,
        post_body=body,
        keyword_text=task.keyword_text,
        post_url=post_url,
        char_count=char_count,
        image_count=0,
        keyword_count=keyword_count,
        marketing_product_id=task.marketing_product_id,
        worker_id=task.worker_id,
        homepage_account_id=task.homepage_account_id,
        is_registration_complete=True
    )
    db.add(homepage_post)
    db.flush()
    
    # 이미지 저장
    if images:
        upload_dir = Path("static/uploads/homepage_images")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        for i, image in enumerate(images):
            if image.filename:
                ext = os.path.splitext(image.filename)[1]
                filename = f"{uuid.uuid4()}{ext}"
                filepath = upload_dir / filename
                
                with open(filepath, "wb") as f:
                    content = await image.read()
                    f.write(content)
                
                homepage_image = HomepagePostImage(
                    homepage_post_id=homepage_post.id,
                    image_path=str(filepath),
                    image_filename=filename,
                    image_order=i
                )
                db.add(homepage_image)
        
        homepage_post.image_count = len(images)
    
    # 작업 완료 처리
    task.status = 'completed'
    task.completed_post_id = homepage_post.id
    task.completed_at = datetime.now()
    
    # 진행 상황 업데이트
    progress = db.query(HomepageKeywordProgress).filter(
        HomepageKeywordProgress.worker_id == task.worker_id,
        HomepageKeywordProgress.marketing_product_id == task.marketing_product_id,
        HomepageKeywordProgress.keyword_text == task.keyword_text
    ).first()
    
    if progress:
        progress.is_completed = True
        progress.completed_post_id = homepage_post.id
        progress.completed_at = datetime.now()
    
    db.commit()
    
    return {"message": "글 작성 완료", "post_id": homepage_post.id}


@router.get("/marketing/homepage/api/posts/{post_id}")
def get_homepage_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """통페이지 글 상세"""
    user = get_current_user(request, db)
    has_access, homepage_worker_or_error = check_homepage_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    post = db.query(HomepagePost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 권한 체크
    homepage_worker = homepage_worker_or_error if not user.is_admin else None
    if not check_is_homepage_manager(user, db) and homepage_worker and post.worker_id != homepage_worker.id:
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
        worker_obj = db.query(HomepageWorker).filter(
            HomepageWorker.id == post.worker_id
        ).first()
        if worker_obj and worker_obj.user:
            worker_name = worker_obj.user.username
    
    account_id = ""
    if post.homepage_account_id:
        account = db.query(HomepageAccount).filter(
            HomepageAccount.id == post.homepage_account_id
        ).first()
        if account:
            account_id = account.account_id
    
    # task_id 찾기
    task_id = None
    task = db.query(HomepageWorkTask).filter(
        HomepageWorkTask.completed_post_id == post_id
    ).first()
    if task:
        task_id = task.id
    
    return {
        "id": post.id,
        "task_id": task_id,
        "title": post.post_title,
        "body": post.post_body,
        "keyword": post.keyword_text,
        "post_url": post.post_url,
        "char_count": post.char_count,
        "image_count": post.image_count,
        "keyword_count": post.keyword_count,
        "images": [{"path": img.image_path, "filename": img.image_filename} for img in post.images],
        "product_name": product_name,
        "worker_name": worker_name,
        "account_id": account_id,
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M")
    }

@router.put("/marketing/homepage/api/posts/{post_id}")
async def update_homepage_post(
    post_id: int,
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    post_url: str = Form(None),
    images: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """통페이지 글 수정"""
    user = get_current_user(request, db)
    has_access, homepage_worker_or_error = check_homepage_access(user, db)
    
    if not has_access:
        raise HTTPException(status_code=403)
    
    post = db.query(HomepagePost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    # 권한 체크
    homepage_worker = homepage_worker_or_error if not user.is_admin else None
    if not check_is_homepage_manager(user, db) and homepage_worker and post.worker_id != homepage_worker.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    # 글 수정
    post.post_title = title
    post.post_body = body
    post.post_url = post_url
    
    # 통계 재계산
    post.char_count = count_chars_without_spaces(body)
    post.keyword_count = count_keyword_occurrences(title + " " + body, post.keyword_text)
      
    # 새 이미지 추가
    if images:
        upload_dir = Path("static/uploads/homepage_images")
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
                
                homepage_image = HomepagePostImage(
                    homepage_post_id=post.id,
                    image_path=str(filepath),
                    image_filename=filename,
                    image_order=existing_count + i
                )
                db.add(homepage_image)
        
        post.image_count = existing_count + len(images)
    
    db.commit()
    
    return {"message": "글 수정 완료", "post_id": post.id}

@router.delete("/marketing/homepage/api/posts/{post_id}")
def delete_homepage_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    """통페이지 글 삭제"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    post = db.query(HomepagePost).get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="글을 찾을 수 없습니다")
    
    try:
        # 1단계: HomepageWorkTask에서 참조 제거
        related_tasks = db.query(HomepageWorkTask).filter(
            HomepageWorkTask.completed_post_id == post_id
        ).all()
        
        print(f"🔍 [DELETE] 관련 작업 {len(related_tasks)}개 발견")
        
        for task in related_tasks:
            print(f"   - 작업 ID {task.id}: completed_post_id 제거")
            task.completed_post_id = None
            task.status = 'pending'
            task.completed_at = None
            db.add(task)
        
        # 2단계: HomepageKeywordProgress에서 참조 제거
        related_progress = db.query(HomepageKeywordProgress).filter(
            HomepageKeywordProgress.completed_post_id == post_id
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


# ============================================
# 계정 관리 API
# ============================================

@router.get("/marketing/homepage/api/accounts")
def get_homepage_accounts(request: Request, db: Session = Depends(get_db)):
    """통페이지 계정 목록"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    accounts = db.query(HomepageAccount).order_by(HomepageAccount.id).all()
    
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


@router.post("/marketing/homepage/api/accounts")
def create_homepage_account(
    account_id: str = Form(...),
    account_pw: str = Form(...),
    blog_url: str = Form(None),
    ip_address: str = Form(None),
    category: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """통페이지 계정 추가"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 중복 체크
    existing = db.query(HomepageAccount).filter(
        HomepageAccount.account_id == account_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="이미 존재하는 계정입니다")
    
    account = HomepageAccount(
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


@router.put("/marketing/homepage/api/accounts/{account_id}")
def update_homepage_account(
    account_id: int,
    account_pw: str = Form(None),
    blog_url: str = Form(None),
    ip_address: str = Form(None),
    category: str = Form(None),
    status: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """통페이지 계정 수정"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    account = db.query(HomepageAccount).get(account_id)
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


@router.delete("/marketing/homepage/api/accounts/{account_id}")
def delete_homepage_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    """통페이지 계정 삭제"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    account = db.query(HomepageAccount).get(account_id)
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

@router.get("/marketing/homepage/api/workers")
def get_homepage_workers(request: Request, db: Session = Depends(get_db)):
    """통페이지 작업자 목록"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    workers = db.query(HomepageWorker).order_by(HomepageWorker.id).all()
    
    result = []
    for worker in workers:
        # 안전하게 상품 이름 가져오기
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
            total_keywords = db.query(HomepageProductKeyword).filter(
                HomepageProductKeyword.marketing_product_id == worker.current_product_id,
                HomepageProductKeyword.is_active == True
            ).count()
            
            completed_keywords = db.query(HomepageKeywordProgress).filter(
                HomepageKeywordProgress.worker_id == worker.id,
                HomepageKeywordProgress.marketing_product_id == worker.current_product_id,
                HomepageKeywordProgress.is_completed == True
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
            "accounts": [acc.account_id for acc in worker.homepage_accounts],
            "current_product": current_product_name,
            "progress": progress,
            "progress_percent": progress_percent,
            "daily_quota": worker.daily_quota,
            "status": worker.status,
            "is_homepage_manager": worker.is_homepage_manager
        })
    
    return result


@router.get("/marketing/homepage/api/available-users")
def get_available_users(request: Request, db: Session = Depends(get_db)):
    """통페이지 작업자로 추가 가능한 사용자 목록"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 마케팅 권한이 있고, 아직 통페이지 작업자가 아닌 사용자
    existing_worker_ids = db.query(HomepageWorker.user_id).all()
    existing_worker_ids = [w[0] for w in existing_worker_ids]
    
    users = db.query(User).filter(
        User.can_manage_marketing == True,
        User.id.notin_(existing_worker_ids)
    ).all()
    
    return [{"id": u.id, "username": u.username} for u in users]


@router.post("/marketing/homepage/api/workers")
def create_homepage_worker(
    user_id: int = Form(...),
    daily_quota: int = Form(...),
    product_id: int = Form(...),
    is_homepage_manager: bool = Form(False),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """통페이지 작업자 추가"""
    admin_user = get_current_user(request, db)
    
    if not check_is_homepage_manager(admin_user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 사용자 존재 확인
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    # 이미 작업자인지 확인
    existing = db.query(HomepageWorker).filter(
        HomepageWorker.user_id == user_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="이미 통페이지 작업자입니다")
    
    # 작업자 생성
    worker = HomepageWorker(
        user_id=user_id,
        daily_quota=daily_quota,
        current_product_id=product_id,
        is_homepage_manager=is_homepage_manager,
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


@router.put("/marketing/homepage/api/workers/{worker_id}/quota")
def update_worker_quota(
    worker_id: int,
    daily_quota: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """작업자 할당량 변경"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(HomepageWorker).get(worker_id)
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


@router.put("/marketing/homepage/api/workers/{worker_id}/status")
def update_worker_status(
    worker_id: int,
    status: str = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """작업자 상태 변경"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(HomepageWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    worker.status = status
    db.commit()
    
    return {"message": "상태 변경 완료"}


@router.put("/marketing/homepage/api/workers/{worker_id}/product")
def update_worker_product(
    worker_id: int,
    product_id: int = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    
    """작업자 현재 상품 변경"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(HomepageWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    worker.current_product_id = product_id
    db.commit()
    
    return {"message": "상품 변경 완료"}


@router.put("/marketing/homepage/api/workers/{worker_id}/homepage-manager")
def update_worker_homepage_manager(
    worker_id: int,
    is_homepage_manager: bool = Form(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """작업자 통페이지 관리자 권한 변경"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(HomepageWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    # 자기 자신의 관리자 권한은 해제할 수 없음
    if worker.user_id == user.id and not is_homepage_manager:
        raise HTTPException(
            status_code=400, 
            detail="자신의 관리자 권한은 해제할 수 없습니다"
        )
    
    worker.is_homepage_manager = is_homepage_manager
    db.commit()
    
    status_text = "관리자로 지정" if is_homepage_manager else "일반 작업자로 변경"
    print(f"✅ [WORKER] {worker.user.username}: {status_text}")
    
    return {"message": f"{status_text}되었습니다"}


# ============================================
# 스케줄 자동 배정 (Cron Job용)
# ============================================

@router.post("/marketing/homepage/api/schedule/auto-assign")
def auto_assign_daily_tasks(
    target_date: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """일일 작업 자동 배정"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    # 날짜 설정
    if target_date:
        task_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        task_date = date.today()
    
    print("=" * 80)
    print(f"🔍 [AUTO-ASSIGN] 작업 배정 시작: {task_date}")
    print("=" * 80)
    
    # 이미 배정된 작업이 있는지 확인
    existing = db.query(HomepageWorkTask).filter(
        HomepageWorkTask.task_date == task_date
    ).first()
    
    if existing:
        print(f"⚠️ [AUTO-ASSIGN] 이미 배정된 작업 있음")
        raise HTTPException(status_code=400, detail=f"{task_date} 날짜에 이미 배정된 작업이 있습니다")
    
    # 활성 작업자 조회
    active_workers = db.query(HomepageWorker).filter(
        HomepageWorker.status == 'active'
    ).all()
    
    print(f"🔍 [AUTO-ASSIGN] 활성 작업자 수: {len(active_workers)}")
    
    if not active_workers:
        print(f"⚠️ [AUTO-ASSIGN] 활성 작업자 없음!")
        raise HTTPException(status_code=400, detail="활성 작업자가 없습니다")
    
    # 오늘 배정된 키워드 (중복 방지)
    today_assigned_keywords = set()
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
        
        # 이 작업자가 아직 안 쓴 키워드 조회
        completed = db.query(HomepageKeywordProgress.keyword_text).filter(
            HomepageKeywordProgress.worker_id == worker.id,
            HomepageKeywordProgress.marketing_product_id == worker.current_product_id,
            HomepageKeywordProgress.is_completed == True
        ).all()
        completed_keywords = {k[0] for k in completed}
        print(f"   - 완료한 키워드: {len(completed_keywords)}개")
        
        # 이 상품의 활성 키워드
        active_kws = db.query(HomepageProductKeyword.keyword_text).filter(
            HomepageProductKeyword.marketing_product_id == worker.current_product_id,
            HomepageProductKeyword.is_active == True
        ).all()
        active_keywords = {k[0] for k in active_kws}
        print(f"   - 활성 키워드: {len(active_keywords)}개")
        
        if len(active_keywords) == 0:
            print(f"   ⚠️ 활성 키워드 없음 → 스킵")
            continue
        
        # 아직 안 쓴 키워드
        unused = active_keywords - completed_keywords
        print(f"   - 미사용 키워드: {len(unused)}개")
        
        # 오늘 다른 작업자가 배정받은 키워드 제외
        available = unused - today_assigned_keywords
        print(f"   - 배정 가능 키워드: {len(available)}개")
        
        if not available:
            print(f"   ⚠️ 배정 가능한 키워드 없음 → 스킵")
            continue
        
        # 할당량만큼 랜덤 선택
        quota = min(worker.daily_quota, len(available))
        selected = random.sample(list(available), quota)
        print(f"   ✅ 선택된 키워드: {quota}개 - {selected[:3]}{'...' if len(selected) > 3 else ''}")
        
        # 작업자의 통페이지 계정들
        accounts = db.query(HomepageAccount).filter(
            HomepageAccount.assigned_worker_id == worker.id
        ).order_by(HomepageAccount.assignment_order).all()
        
        print(f"   - 배정된 계정: {len(accounts)}개")
        
        if not accounts:
            print(f"   ⚠️ 배정된 계정 없음 → 스킵")
            continue
        
        # 계정별 작업 분배 (계정당 최대 3개)
        account_idx = 0
        account_post_count = {}
        assigned_for_worker = 0
        
        for keyword in selected:
            # 현재 계정이 3개 다 찼으면 다음 계정으로
            if account_post_count.get(account_idx, 0) >= 3:
                account_idx += 1
                if account_idx >= len(accounts):
                    print(f"   ⚠️ 모든 계정이 가득 참 (배정: {assigned_for_worker}개)")
                    break
            
            task = HomepageWorkTask(
                task_date=task_date,
                status='pending',
                keyword_text=keyword,
                worker_id=worker.id,
                marketing_product_id=worker.current_product_id,
                homepage_account_id=accounts[account_idx].id
            )
            db.add(task)
            assigned_for_worker += 1
            
            # 진행 상황에도 기록 (아직 없다면)
            progress = db.query(HomepageKeywordProgress).filter(
                HomepageKeywordProgress.worker_id == worker.id,
                HomepageKeywordProgress.marketing_product_id == worker.current_product_id,
                HomepageKeywordProgress.keyword_text == keyword
            ).first()
            
            if not progress:
                progress = HomepageKeywordProgress(
                    worker_id=worker.id,
                    marketing_product_id=worker.current_product_id,
                    keyword_text=keyword,
                    is_completed=False
                )
                db.add(progress)
            
            today_assigned_keywords.add(keyword)
            account_post_count[account_idx] = account_post_count.get(account_idx, 0) + 1
        
        print(f"   ✅ 이 작업자에게 {assigned_for_worker}개 작업 배정")
        total_assigned += assigned_for_worker
    
    db.commit()
    
    print("=" * 80)
    print(f"✅ [AUTO-ASSIGN] 총 {total_assigned}개 작업 배정 완료")
    print("=" * 80)
    
    return {
        "message": f"{task_date} 작업 배정 완료 (총 {total_assigned}개)",
        "assigned_count": total_assigned,
        "workers_count": len(active_workers)
    }
    
@router.delete("/marketing/homepage/api/workers/{worker_id}")
def delete_homepage_worker(worker_id: int, request: Request, db: Session = Depends(get_db)):
    """통페이지 작업자 삭제"""
    user = get_current_user(request, db)
    
    if not check_is_homepage_manager(user, db):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    
    worker = db.query(HomepageWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다")
    
    # 배정된 계정 모두 해제
    accounts = db.query(HomepageAccount).filter(
        HomepageAccount.assigned_worker_id == worker_id
    ).all()
    
    
    for account in accounts:
        account.assigned_worker_id = None
        account.assignment_order = None
        db.add(account)
    
    # 작업자 삭제
    db.delete(worker)
    db.commit()
    
    return {"message": "작업자 삭제 완료"}