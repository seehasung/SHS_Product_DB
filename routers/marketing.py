from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func, distinct
from datetime import date, datetime, timedelta
from typing import Optional, List
import json
import math



# Reference, Comment, User 및 신규 MarketingPost 모델을 import (PostSchedule 등 추가)
from database import (
    SessionLocal, TargetCafe, MarketingAccount, Product, MarketingProduct,
    CafeMembership, Reference, Comment, User, MarketingPost, WorkTask,
    PostSchedule, AccountCafeUsage, PostingRound  # 새로 추가된 모델들
)


router = APIRouter(prefix="/marketing")
templates = Jinja2Templates(directory="templates")

# --- Helper Functions ---

def sort_product_code(product_code):
    """
    상품 코드를 정렬하기 위한 키 생성 함수
    예: "1-1" → (1, 1), "10-2" → (10, 2)
    """
    if not product_code or '-' not in product_code:
        return (999999, 999999)  # 형식이 맞지 않으면 맨 뒤로
    
    try:
        parts = product_code.split('-')
        main = int(parts[0])
        sub = int(parts[1]) if len(parts) > 1 else 0
        return (main, sub)
    except (ValueError, IndexError):
        return (999999, 999999)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Main Marketing Cafe Page (수정됨) ---
@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get('tab', 'status')
    error = request.query_params.get('error')
    
    # --- 기존 전체 현황 탭 데이터 ---
    username = request.session.get("user")
    current_user = db.query(User).filter(User.username == username).first()
    
    today = date.today()
    work_tasks = []
    completed_count = 0
    daily_quota = 0
    
    if current_user:
        daily_quota = current_user.daily_quota or 0
        
        # 오늘 날짜로, 현재 사용자에게 할당된 모든 작업(WorkTask)을 조회
        work_tasks_query = db.query(WorkTask).options(
            joinedload(WorkTask.account),
            joinedload(WorkTask.cafe),
            joinedload(WorkTask.marketing_product).joinedload(MarketingProduct.product)
        ).filter(
            WorkTask.worker_id == current_user.id,
            func.date(WorkTask.task_date) == today
        )
        
        work_tasks = work_tasks_query.order_by(WorkTask.status.desc(), WorkTask.id).all()
        
        # 오늘 완료한 작업 수 계산
        completed_count = sum(1 for task in work_tasks if task.status == 'done')
    
    remaining_tasks = daily_quota - completed_count
    
    # --- 스케줄 관련 데이터 추가 ---
    
    # 오늘의 스케줄 (PostSchedule 사용)
    today_schedules = db.query(PostSchedule).filter(
        PostSchedule.scheduled_date == today
    ).options(
        joinedload(PostSchedule.worker),
        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product),
        joinedload(PostSchedule.cafe)
    ).all()
    
    # 오늘의 통계
    today_stats = {
        'total': len(today_schedules),
        'completed': sum(1 for s in today_schedules if s.status == 'completed'),
        'in_progress': sum(1 for s in today_schedules if s.status == 'in_progress'),
        'pending': sum(1 for s in today_schedules if s.status == 'pending')
    }
    
    # 작업자 목록 (마케팅 권한 있는 사용자)
    workers = db.query(User).filter(
        or_(User.can_manage_marketing == True, User.is_admin == True)
    ).all()
    
    # 작업자별 할당량 (User 모델의 daily_quota 사용)
    worker_quotas = {}
    for worker in workers:
        worker_quotas[worker.id] = worker.daily_quota or 6  # 기본값 6
    
    # --- 기존 탭들 데이터 ---
    error_messages = {
        'duplicate_account': "이미 사용 중인 아이디입니다.",
        'duplicate_reference': "이미 사용 중인 레퍼런스 제목입니다.",
        'no_workers': "작업자를 선택해주세요.",
        'no_keywords': "키워드가 없습니다.",
        'invalid_keywords': "키워드 형식이 잘못되었습니다.",
        'no_memberships': "활성 연동이 없습니다."
    }
    error_message = error_messages.get(error)
    selected_cafe_id = request.query_params.get('cafe_id')
    status_filter = request.query_params.get('status_filter', 'all')
    category_filter = request.query_params.get('category_filter', 'all')
    reference_filter = request.query_params.get('ref_filter', 'all')
    selected_cafe, memberships = None, []
    if selected_cafe_id:
        selected_cafe = db.query(TargetCafe).filter(TargetCafe.id == selected_cafe_id).first()
        query = db.query(CafeMembership).options(joinedload(CafeMembership.account))
        query = query.filter(CafeMembership.cafe_id == selected_cafe_id)
        if status_filter != 'all':
            query = query.filter(CafeMembership.status == status_filter)
        memberships = query.order_by(CafeMembership.account_id).all()
    
    # 카페 목록 조회 및 정렬 (1, 2, 10, 11 순서로)
    cafes_raw = db.query(TargetCafe).all()
    cafes = sorted(cafes_raw, key=lambda c: sort_product_code(c.name))
    
    accounts_query = db.query(MarketingAccount)
    if category_filter != 'all':
        accounts_query = accounts_query.filter(MarketingAccount.category == category_filter)
    accounts = accounts_query.order_by(MarketingAccount.id).all()
    
    # 마케팅 상품 목록 조회 및 정렬 (1-1, 1-2, 10-1 순서로)
    marketing_products_raw = db.query(MarketingProduct).options(joinedload(MarketingProduct.product)).all()
    marketing_products = sorted(marketing_products_raw, key=lambda mp: sort_product_code(mp.product.product_code if mp.product else ""))
    
    # 상품별 키워드 통계 추가
    for mp in marketing_products:
        if mp.keywords:
            try:
                keywords_data = json.loads(mp.keywords)
                mp.keyword_count = len([k for k in keywords_data if k.get('active', True)])
                
                # 라운드 정보 계산 (간단한 버전)
                usage = db.query(AccountCafeUsage).filter(
                    AccountCafeUsage.marketing_product_id == mp.id
                ).all()
                mp.round1_complete = len([u for u in usage if u.usage_count >= 1])
                mp.round2_progress = len([u for u in usage if u.usage_count >= 2])
                mp.remaining_tasks = (mp.keyword_count * 3 * 2) - sum(u.usage_count for u in usage)
            except:
                mp.keyword_count = 0
                mp.round1_complete = 0
                mp.round2_progress = 0
                mp.remaining_tasks = 0
        else:
            mp.keyword_count = 0
            mp.round1_complete = 0
            mp.round2_progress = 0
            mp.remaining_tasks = 0
    
    references_query = db.query(Reference).options(joinedload(Reference.last_modified_by))
    if reference_filter != 'all':
        references_query = references_query.filter(Reference.ref_type == reference_filter)
    references_raw = references_query.order_by(Reference.id.desc()).all()
    
    # SQLAlchemy 객체를 JSON 직렬화 가능한 딕셔너리로 변환
    references = []
    for ref in references_raw:
        ref_dict = {
            'id': ref.id,
            'title': ref.title,
            'ref_type': ref.ref_type,
            'content': ref.content,
            'last_modified_by_name': ref.last_modified_by.username if ref.last_modified_by else None
        }
        references.append(ref_dict)
    
    all_workers = db.query(User).filter(or_(User.can_manage_marketing == True, User.is_admin == True)).all()

    return templates.TemplateResponse("marketing_cafe.html", {
        "request": request, "cafes": cafes, "accounts": accounts,
        "marketing_products": marketing_products, "memberships": memberships,
        "selected_cafe": selected_cafe, "status_filter": status_filter,
        "category_filter": category_filter, "error": error_message,
        "references": references, "reference_filter": reference_filter,
        "active_tab": tab,
        
        "work_tasks": work_tasks,
        "daily_quota": daily_quota,
        "completed_count": completed_count,
        "remaining_tasks": remaining_tasks,
        "all_workers": all_workers,
        
        # 스케줄 관련 데이터 추가
        "today_schedules": today_schedules[:10],  # 최근 10개만
        "today_stats": today_stats,
        "workers": workers,
        "worker_quotas": worker_quotas
    })

# --- 스케줄 관리 라우터 추가 ---

@router.get("/schedules", response_class=HTMLResponse)
async def get_schedules(
    request: Request,
    selected_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """전체 현황 관리 페이지"""
    
    # 로그인 체크
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    # 날짜 파싱 (없으면 오늘)
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()
    
    # 해당 날짜의 스케줄 가져오기
    schedules = db.query(PostSchedule).options(
        joinedload(PostSchedule.worker),
        joinedload(PostSchedule.account),
        joinedload(PostSchedule.cafe),
        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product),
        joinedload(PostSchedule.marketing_post)
    ).filter(
        PostSchedule.scheduled_date == target_date
    ).order_by(PostSchedule.worker_id, PostSchedule.cafe_id).all()
    
    # 오늘의 통계
    today = datetime.now().date()
    today_schedules = db.query(PostSchedule).filter(
        PostSchedule.scheduled_date == today
    ).all()
    
    today_stats = {
        'total': len(today_schedules),
        'completed': sum(1 for s in today_schedules if s.status == 'completed'),
        'in_progress': sum(1 for s in today_schedules if s.status == 'in_progress'),
        'pending': sum(1 for s in today_schedules if s.status == 'pending')
    }
    
    # 작업자 목록
    workers = db.query(User).filter(
        or_(User.can_manage_marketing == True, User.is_admin == True)
    ).all()
    
    # 계정 목록
    accounts = db.query(MarketingAccount).all()
    
    # 카페 목록
    cafes = db.query(TargetCafe).all()
    
    # 상품 목록
    marketing_products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    
    # 계정별 카페 매핑
    all_memberships = db.query(CafeMembership).options(
        joinedload(CafeMembership.cafe)
    ).filter(CafeMembership.status == 'active').all()
    
    membership_map = {}
    for membership in all_memberships:
        if membership.account_id not in membership_map:
            membership_map[membership.account_id] = []
        if membership.cafe:
            membership_map[membership.account_id].append({
                "id": membership.cafe.id,
                "name": membership.cafe.name
            })
    
    # 상품별 키워드 맵
    product_keywords_map = {}
    for mp in marketing_products:
        if mp.keywords:
            try:
                keywords_list = json.loads(mp.keywords)
                active_keywords = [item['keyword'] for item in keywords_list if item.get('active', True)]
                product_keywords_map[mp.id] = active_keywords
            except json.JSONDecodeError:
                product_keywords_map[mp.id] = []
    
    # 연결되지 않은 글 목록
    linked_post_ids = db.query(PostSchedule.marketing_post_id).filter(
        PostSchedule.marketing_post_id != None
    ).subquery()
    
    unlinked_posts = db.query(MarketingPost).options(
        joinedload(MarketingPost.worker),
        joinedload(MarketingPost.marketing_product).joinedload(MarketingProduct.product)
    ).filter(
        MarketingPost.is_registration_complete == True,
        ~MarketingPost.id.in_(linked_post_ids)
    ).all()
    
    return templates.TemplateResponse("marketing_schedules.html", {
        "request": request,
        "username": username,
        "selected_date": target_date,
        "schedules": schedules,
        "today_stats": today_stats,
        "workers": workers,
        "accounts": accounts,
        "cafes": cafes,
        "marketing_products": marketing_products,
        "membership_map": membership_map,
        "product_keywords_map": product_keywords_map,
        "unlinked_posts": unlinked_posts
    })

@router.post("/schedule/add", response_class=RedirectResponse)
async def add_schedule(
    request: Request,
    scheduled_date: date = Form(...),
    worker_id: int = Form(...),
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    marketing_product_id: int = Form(...),
    keyword_text: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db)
):
    """새 스케줄 추가"""
    
    new_schedule = PostSchedule(
        scheduled_date=scheduled_date,
        worker_id=worker_id,
        account_id=account_id,
        cafe_id=cafe_id,
        marketing_product_id=marketing_product_id,
        keyword_text=keyword_text,
        notes=notes,
        status="pending"
    )
    
    db.add(new_schedule)
    db.commit()
    
    return RedirectResponse(
        url=f"/marketing/schedules?selected_date={scheduled_date}",
        status_code=303
    )

@router.post("/schedule/{schedule_id}/toggle-complete")
async def toggle_schedule_complete(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """스케줄 완료 상태 토글"""
    
    body = await request.json()
    is_completed = body.get('is_completed', False)
    
    schedule = db.query(PostSchedule).filter(
        PostSchedule.id == schedule_id
    ).first()
    
    if schedule:
        schedule.is_completed = is_completed
        if is_completed:
            schedule.status = "completed"
            schedule.completed_at = datetime.utcnow()
        else:
            schedule.status = "pending"
            schedule.completed_at = None
        
        db.commit()
    
    return {"success": True}

@router.post("/schedule/{schedule_id}/link-post", response_class=RedirectResponse)
async def link_post_to_schedule(
    schedule_id: int,
    marketing_post_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """스케줄에 작성된 글 연결"""
    
    schedule = db.query(PostSchedule).filter(
        PostSchedule.id == schedule_id
    ).first()
    
    if schedule:
        schedule.marketing_post_id = marketing_post_id
        schedule.status = "completed"
        schedule.is_completed = True
        schedule.completed_at = datetime.utcnow()
        db.commit()
    
    return RedirectResponse(
        url=f"/marketing/schedules?selected_date={schedule.scheduled_date if schedule else ''}",
        status_code=303
    )

@router.post("/schedule/{schedule_id}/delete")
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    """스케줄 삭제"""
    
    schedule = db.query(PostSchedule).filter(
        PostSchedule.id == schedule_id
    ).first()
    
    if schedule:
        db.delete(schedule)
        db.commit()
    
    return {"success": True}

@router.post("/user/quota/update", response_class=RedirectResponse)
async def update_user_quota(
    user_id: int = Form(...),
    daily_post_count: int = Form(...),
    db: Session = Depends(get_db)
):
    """유저 일일 할당량 업데이트"""
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if user:
        user.daily_quota = daily_post_count
        db.commit()
    
    return RedirectResponse(
        url="/marketing/cafe?tab=schedule",
        status_code=303
    )

@router.post("/schedule/generate", response_class=RedirectResponse)
async def generate_schedules(
    request: Request,
    start_date: date = Form(...),
    end_date: date = Form(...),
    marketing_product_id: int = Form(...),
    worker_ids: str = Form(""),
    db: Session = Depends(get_db)
):
    """스케줄 자동 생성"""
    
    if not worker_ids:
        return RedirectResponse(url="/marketing/cafe?tab=schedule&error=no_workers", status_code=303)
    
    worker_id_list = [int(id.strip()) for id in worker_ids.split(',') if id.strip()]
    
    # 상품의 키워드 가져오기
    marketing_product = db.query(MarketingProduct).filter(
        MarketingProduct.id == marketing_product_id
    ).first()
    
    if not marketing_product or not marketing_product.keywords:
        return RedirectResponse(url="/marketing/cafe?tab=schedule&error=no_keywords", status_code=303)
    
    try:
        keywords_data = json.loads(marketing_product.keywords)
        active_keywords = [k['keyword'] for k in keywords_data if k.get('active', True)]
    except:
        return RedirectResponse(url="/marketing/cafe?tab=schedule&error=invalid_keywords", status_code=303)
    
    # 계정-카페 매핑
    memberships = db.query(CafeMembership).filter(
        CafeMembership.status == 'active'
    ).all()
    
    if not memberships:
        return RedirectResponse(url="/marketing/cafe?tab=schedule&error=no_memberships", status_code=303)
    
    # 날짜 범위 내에서 스케줄 생성
    current_date = start_date
    keyword_index = 0
    
    while current_date <= end_date:
        # 주말 제외 (월-금만)
        if current_date.weekday() < 5:
            # 각 작업자에게 할당
            for worker_id in worker_id_list:
                user = db.query(User).filter(User.id == worker_id).first()
                if not user:
                    continue
                
                daily_quota = user.daily_quota or 6
                
                # 일일 할당량만큼 스케줄 생성
                for _ in range(daily_quota):
                    if keyword_index >= len(active_keywords):
                        keyword_index = 0  # 키워드 순환
                    
                    keyword = active_keywords[keyword_index]
                    
                    # 카페 선택 (키워드당 3개 카페)
                    posts_per_keyword = 3
                    for i in range(posts_per_keyword):
                        membership_index = (keyword_index * posts_per_keyword + i) % len(memberships)
                        membership = memberships[membership_index]
                        
                        # 사용 횟수 체크
                        usage = db.query(AccountCafeUsage).filter(
                            AccountCafeUsage.account_id == membership.account_id,
                            AccountCafeUsage.cafe_id == membership.cafe_id,
                            AccountCafeUsage.keyword_text == keyword,
                            AccountCafeUsage.marketing_product_id == marketing_product_id
                        ).first()
                        
                        if usage and usage.usage_count >= 2:
                            continue  # 최대 2회 제한
                        
                        new_schedule = PostSchedule(
                            scheduled_date=current_date,
                            worker_id=worker_id,
                            account_id=membership.account_id,
                            cafe_id=membership.cafe_id,
                            marketing_product_id=marketing_product_id,
                            keyword_text=keyword,
                            status="pending"
                        )
                        db.add(new_schedule)
                        
                        # 사용 횟수 업데이트
                        if usage:
                            usage.usage_count += 1
                            usage.last_used_date = current_date
                        else:
                            usage = AccountCafeUsage(
                                account_id=membership.account_id,
                                cafe_id=membership.cafe_id,
                                keyword_text=keyword,
                                marketing_product_id=marketing_product_id,
                                usage_count=1,
                                last_used_date=current_date
                            )
                            db.add(usage)
                    
                    keyword_index += 1
        
        current_date += timedelta(days=1)
    
    db.commit()
    
    return RedirectResponse(
        url=f"/marketing/schedules?selected_date={start_date}",
        status_code=303
    )

# --- 기존 WorkTask 관련 라우터 유지 ---
@router.post("/task/assign-next", response_class=RedirectResponse)
async def assign_next_task(request: Request, db: Session = Depends(get_db)):
    """현재 사용자에게 '다음 작업'을 할당하는 로직"""
    username = request.session.get("user")
    current_user = db.query(User).filter(User.username == username).first()
    
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    
    today = date.today()
    
    # 1. 오늘 이미 완료한 작업 수 확인
    completed_count = db.query(WorkTask).filter(
        WorkTask.worker_id == current_user.id,
        func.date(WorkTask.task_date) == today,
        WorkTask.status == 'done'
    ).count()
    
    # 2. 할당량이 남았는지 확인
    if completed_count < (current_user.daily_quota or 0):
        # 3. 이미 진행중('todo')인 작업이 있는지 확인
        existing_todo = db.query(WorkTask).filter(
            WorkTask.worker_id == current_user.id,
            WorkTask.status == 'todo'
        ).first()
        
        # 4. 진행중인 작업이 없다면, 새로운 작업 할당
        if not existing_todo:
            # --- (임시 로직: 첫 번째 상품의 첫 번째 키워드와 첫 번째 연동 정보를 할당) ---
            mp = db.query(MarketingProduct).first()
            membership = db.query(CafeMembership).filter(CafeMembership.status == 'active').first()
            
            if mp and membership and mp.keywords:
                keyword = json.loads(mp.keywords)[0].get('keyword', 'N/A')
                
                new_task = WorkTask(
                    task_date=today,
                    worker_id=current_user.id,
                    marketing_product_id=mp.id,
                    keyword_text=keyword,
                    account_id=membership.account_id,
                    cafe_id=membership.cafe_id,
                    status="todo"
                )
                db.add(new_task)
                db.commit()

    return RedirectResponse(url="/marketing/cafe?tab=status", status_code=303)

# --- Reference & Comment Management (기존 유지) ---
@router.post("/reference/add", response_class=RedirectResponse)
async def add_reference(
    request: Request,
    title: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """새 레퍼런스 생성"""
    username = request.session.get("user")
    user = None
    if username:
        user = db.query(User).filter(User.username == username).first()
    
    # 유니크한 제목 생성
    if not title or title.strip() == '':
        now = datetime.now()
        title = f"새 레퍼런스 {now.strftime('%Y%m%d_%H%M%S')}"
    
    try:
        # 새 레퍼런스 생성
        new_ref = Reference(
            title=title,
            ref_type='기타',
            content='',
            last_modified_by_id=user.id if user else None
        )
        db.add(new_ref)
        db.commit()
        db.refresh(new_ref)
        
        print(f"✅ 레퍼런스 생성 완료: ID={new_ref.id}, 제목={new_ref.title}")
        
        # 상세 페이지로 리다이렉트
        return RedirectResponse(
            url=f"/marketing/reference/{new_ref.id}",
            status_code=303
        )
        
    except Exception as e:
        db.rollback()
        print(f"❌ 레퍼런스 생성 실패: {e}")
        return RedirectResponse(
            url="/marketing/cafe?tab=references&error=create_failed",
            status_code=303
        )

@router.post("/reference/delete/{ref_id}", response_class=RedirectResponse)
async def delete_reference(ref_id: int, db: Session = Depends(get_db)):
    ref_to_delete = db.query(Reference).filter(Reference.id == ref_id).first()
    if ref_to_delete:
        db.delete(ref_to_delete)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=references", status_code=303)

@router.get("/reference/{ref_id}", response_class=HTMLResponse)
async def get_reference_detail(request: Request, ref_id: int, db: Session = Depends(get_db)):
    # Reference 조회 (product 관계 포함)
    reference = db.query(Reference).options(
        joinedload(Reference.last_modified_by)
    ).filter(Reference.id == ref_id).first()
    
    # product 가져오기 (Reference에 product/marketing_product 관계가 있으면)
    product = None
    try:
        if reference:
            # Reference에 product 관계가 있는 경우
            if hasattr(reference, 'product'):
                product = reference.product
            # Reference에 marketing_product 관계가 있는 경우
            elif hasattr(reference, 'marketing_product') and reference.marketing_product:
                product = reference.marketing_product.product if hasattr(reference.marketing_product, 'product') else None
            # Reference에 product_id 필드가 있는 경우
            elif hasattr(reference, 'product_id') and reference.product_id:
                product = db.query(Product).filter(Product.id == reference.product_id).first()
            # Reference에 marketing_product_id 필드가 있는 경우
            elif hasattr(reference, 'marketing_product_id') and reference.marketing_product_id:
                mp = db.query(MarketingProduct).options(
                    joinedload(MarketingProduct.product)
                ).filter(MarketingProduct.id == reference.marketing_product_id).first()
                if mp:
                    product = mp.product
    except Exception as e:
        print(f"⚠️ product 가져오기 실패: {e}")
        product = None
    
    all_comments = db.query(Comment).filter(Comment.reference_id == ref_id).order_by(Comment.created_at).all()
    comment_map = {c.id: c for c in all_comments}
    top_level_comments = []
    for comment in all_comments:
        comment.structured_replies = []
        if comment.parent_id:
            parent = comment_map.get(comment.parent_id)
            if parent:
                if not hasattr(parent, 'structured_replies'):
                    parent.structured_replies = []
                parent.structured_replies.append(comment)
        else:
            top_level_comments.append(comment)
            
    return templates.TemplateResponse("reference_detail.html", {
        "request": request,
        "reference": reference,
        "comments": top_level_comments,
        "product": product  # ✅ product 추가!
    })
@router.post("/reference/update/{ref_id}", response_class=RedirectResponse)
async def update_reference(request: Request, ref_id: int, title: str = Form(...), content: str = Form(""), ref_type: str = Form(...), db: Session = Depends(get_db)):
    username = request.session.get("user")
    user = None
    if username:
        user = db.query(User).filter(User.username == username).first()
    reference = db.query(Reference).filter(Reference.id == ref_id).first()
    if reference:
        reference.title = title
        reference.content = content
        reference.ref_type = ref_type
        reference.last_modified_by_id = user.id if user else None
        db.commit()
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

@router.post("/comment/add/{ref_id}", response_class=RedirectResponse)
async def add_comment(ref_id: int, account_sequence: int = Form(...), text: str = Form(...), parent_id: int = Form(None), db: Session = Depends(get_db)):
    new_comment = Comment(
        account_sequence=account_sequence,
        text=text,
        reference_id=ref_id,
        parent_id=parent_id
    )
    db.add(new_comment)
    db.commit()
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

@router.post("/comment/edit/{ref_id}/{comment_id}", response_class=RedirectResponse)
async def edit_comment(ref_id: int, comment_id: int, account_sequence: int = Form(...), text: str = Form(...), db: Session = Depends(get_db)):
    comment_to_edit = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment_to_edit:
        comment_to_edit.account_sequence = account_sequence
        comment_to_edit.text = text
        db.commit()
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

@router.post("/comment/delete/{ref_id}/{comment_id}", response_class=RedirectResponse)
async def delete_comment(ref_id: int, comment_id: int, db: Session = Depends(get_db)):
    comment_to_delete = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment_to_delete:
        db.delete(comment_to_delete)
        db.commit()
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

# --- Keyword Management (기존 유지) ---
@router.get("/product/keywords/{mp_id}", response_class=HTMLResponse)
async def get_product_keywords(
    request: Request, 
    mp_id: int, 
    db: Session = Depends(get_db),
    total: int = Query(None),
    success: int = Query(None),
    dups: int = Query(None)
):
    """키워드 관리 페이지"""
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    
    keywords_list = []
    if marketing_product and marketing_product.keywords:
        try:
            keywords_list = json.loads(marketing_product.keywords)
        except json.JSONDecodeError:
            keywords_list = [{"keyword": kw.strip(), "active": True} for kw in marketing_product.keywords.splitlines() if kw.strip()]

    keywords_text = "\n".join([item['keyword'] for item in keywords_list])
    total_keywords_count = len(keywords_list)

    return templates.TemplateResponse("marketing_product_keywords.html", {
        "request": request, 
        "marketing_product": marketing_product,
        "keywords_list": keywords_list, 
        "keywords_text": keywords_text,
        "total_keywords_count": total_keywords_count,
        "result_total": total,
        "result_success": success,
        "result_dups": dups
    })

@router.post("/product/keywords/{mp_id}", response_class=RedirectResponse)
async def update_product_keywords(mp_id: int, keywords: str = Form(...), db: Session = Depends(get_db)):
    """텍스트 영역의 키워드를 저장/업데이트"""
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    
    total_attempted = 0
    duplicate_in_batch = 0
    newly_added_count = 0
    
    if marketing_product:
        old_keywords_map = {}
        if marketing_product.keywords:
            try:
                for item in json.loads(marketing_product.keywords):
                    old_keywords_map[item['keyword']] = item['active']
            except json.JSONDecodeError: pass

        new_keywords_from_textarea = []
        seen_in_this_batch = set()
        
        for line in keywords.splitlines():
            kw = line.strip()
            if not kw:
                continue
            
            total_attempted += 1
            
            if kw in seen_in_this_batch:
                duplicate_in_batch += 1
            else:
                seen_in_this_batch.add(kw)
                new_keywords_from_textarea.append(kw)

        final_keywords_map = old_keywords_map.copy()
        for kw in new_keywords_from_textarea:
            if kw not in final_keywords_map:
                final_keywords_map[kw] = True
                newly_added_count += 1
        
        final_keywords_list = [{"keyword": k, "active": v} for k, v in final_keywords_map.items()]
        marketing_product.keywords = json.dumps(final_keywords_list, ensure_ascii=False, indent=4)
        db.commit()

        total_duplicates = duplicate_in_batch + (len(new_keywords_from_textarea) - newly_added_count)
        
        return RedirectResponse(
            url=f"/marketing/product/keywords/{mp_id}?total={total_attempted}&success={newly_added_count}&dups={total_duplicates}", 
            status_code=303
        )
        
    return RedirectResponse(url=f"/marketing/product/keywords/{mp_id}", status_code=303)

@router.post("/product/keywords/toggle/{mp_id}", response_class=RedirectResponse)
async def toggle_keyword_status(mp_id: int, keyword: str = Form(...), db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if marketing_product and marketing_product.keywords:
        keywords_list = json.loads(marketing_product.keywords)
        for item in keywords_list:
            if item['keyword'] == keyword:
                item['active'] = not item['active']
                break
        marketing_product.keywords = json.dumps(keywords_list, ensure_ascii=False, indent=4)
        db.commit()
    return RedirectResponse(url=f"/marketing/product/keywords/{mp_id}", status_code=303)

@router.post("/product/keywords/edit/{mp_id}", response_class=RedirectResponse)
async def edit_keyword(mp_id: int, old_keyword: str = Form(...), new_keyword: str = Form(...), db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if marketing_product and marketing_product.keywords:
        try:
            keywords_list = json.loads(marketing_product.keywords)
            for item in keywords_list:
                if item['keyword'] == old_keyword:
                    item['keyword'] = new_keyword.strip()
                    break
            marketing_product.keywords = json.dumps(keywords_list, ensure_ascii=False, indent=4)
            db.commit()
        except json.JSONDecodeError: pass
    return RedirectResponse(url=f"/marketing/product/keywords/{mp_id}", status_code=303)

@router.post("/product/keywords/delete/{mp_id}", response_class=RedirectResponse)
async def delete_keyword(mp_id: int, keyword: str = Form(...), db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if marketing_product and marketing_product.keywords:
        try:
            keywords_list = json.loads(marketing_product.keywords)
            keywords_list = [item for item in keywords_list if item['keyword'] != keyword]
            marketing_product.keywords = json.dumps(keywords_list, ensure_ascii=False, indent=4)
            db.commit()
        except json.JSONDecodeError: pass
    return RedirectResponse(url=f"/marketing/product/keywords/{mp_id}", status_code=303)

# --- Account Management (기존 유지) ---
@router.post("/account/add", response_class=RedirectResponse)
async def add_marketing_account(account_id: str = Form(...), account_pw: str = Form(...), category: str = Form(...), ip_address: str = Form(None), db: Session = Depends(get_db)):
    try:
        new_account = MarketingAccount(account_id=account_id, account_pw=account_pw, category=category, ip_address=ip_address)
        db.add(new_account)
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url="/marketing/cafe?tab=accounts&error=duplicate_account", status_code=303)
    finally:
        db.close()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

@router.post("/account/update/{account_id}", response_class=RedirectResponse)
async def update_marketing_account(account_id: int, edit_account_id: str = Form(...), edit_account_pw: str = Form(...), edit_category: str = Form(...), edit_ip_address: str = Form(None), db: Session = Depends(get_db)):
    account_to_update = db.query(MarketingAccount).filter(MarketingAccount.id == account_id).first()
    if account_to_update:
        account_to_update.account_id = edit_account_id
        account_to_update.account_pw = edit_account_pw
        account_to_update.category = edit_category
        account_to_update.ip_address = edit_ip_address
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

@router.post("/account/delete/{account_id}", response_class=RedirectResponse)
async def delete_marketing_account(account_id: int, db: Session = Depends(get_db)):
    account_to_delete = db.query(MarketingAccount).filter(MarketingAccount.id == account_id).first()
    if account_to_delete:
        db.delete(account_to_delete)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

# --- Cafe Membership Management (기존 유지) ---
@router.post("/membership/add", response_class=RedirectResponse)
async def add_cafe_membership(
    request: Request,
    account_id: int = Form(...), 
    cafe_id: int = Form(...), 
    new_post_count: int = Form(0), 
    edited_post_count: int = Form(0), 
    db: Session = Depends(get_db)
):
    # 중복 체크
    existing = db.query(CafeMembership).filter_by(
        account_id=account_id, 
        cafe_id=cafe_id
    ).first()
    
    if existing:
        # 중복일 경우 오류와 함께 리다이렉트
        return RedirectResponse(
            url=f"/marketing/cafe?tab=memberships&cafe_id={cafe_id}&error=duplicate", 
            status_code=303
        )
    
    # 신규 연동 생성
    status = "graduated" if (new_post_count + edited_post_count) >= 10 else "active"
    new_membership = CafeMembership(
        account_id=account_id, 
        cafe_id=cafe_id, 
        new_post_count=new_post_count, 
        edited_post_count=edited_post_count, 
        status=status
    )
    db.add(new_membership)
    db.commit()
    
    return RedirectResponse(
        url=f"/marketing/cafe?tab=memberships&cafe_id={cafe_id}", 
        status_code=303
    )

@router.post("/membership/update/{membership_id}", response_class=RedirectResponse)
async def update_membership(membership_id: int, status: str = Form(...), new_post_count: int = Form(...), edited_post_count: int = Form(...), db: Session = Depends(get_db)):
    membership = db.query(CafeMembership).filter(CafeMembership.id == membership_id).first()
    cafe_id_redirect = None
    if membership:
        cafe_id_redirect = membership.cafe_id
        membership.new_post_count = new_post_count
        membership.edited_post_count = edited_post_count
        if (new_post_count + edited_post_count) >= 10:
            membership.status = "graduated"
        else:
            membership.status = status
        db.commit()
    redirect_url = f"/marketing/cafe?tab=memberships&cafe_id={cafe_id_redirect}" if cafe_id_redirect else "/marketing/cafe?tab=memberships"
    return RedirectResponse(url=redirect_url, status_code=303)

# 연동 삭제 라우트 추가
@router.post("/membership/delete/{membership_id}", response_class=RedirectResponse)
async def delete_membership(membership_id: int, db: Session = Depends(get_db)):
    membership = db.query(CafeMembership).filter(CafeMembership.id == membership_id).first()
    cafe_id_redirect = None
    if membership:
        cafe_id_redirect = membership.cafe_id
        db.delete(membership)
        db.commit()
    redirect_url = f"/marketing/cafe?tab=memberships&cafe_id={cafe_id_redirect}" if cafe_id_redirect else "/marketing/cafe?tab=memberships"
    return RedirectResponse(url=redirect_url, status_code=303)

# --- Target Cafe Management (기존 유지) ---
@router.post("/cafe/add", response_class=RedirectResponse)
async def add_target_cafe(name: str = Form(...), url: str = Form(...), db: Session = Depends(get_db)):
    # 카페명 중복 체크
    existing_name = db.query(TargetCafe).filter(TargetCafe.name == name).first()
    if existing_name:
        return RedirectResponse(url="/marketing/cafe?tab=cafes&error=duplicate_name", status_code=303)
    
    # URL 중복 체크
    existing_url = db.query(TargetCafe).filter(TargetCafe.url == url).first()
    if existing_url:
        return RedirectResponse(url="/marketing/cafe?tab=cafes&error=duplicate_url", status_code=303)
    
    try:
        new_cafe = TargetCafe(name=name, url=url)
        db.add(new_cafe)
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

@router.post("/cafe/delete/{cafe_id}", response_class=RedirectResponse)
async def delete_target_cafe(cafe_id: int, db: Session = Depends(get_db)):
    cafe_to_delete = db.query(TargetCafe).filter(TargetCafe.id == cafe_id).first()
    if cafe_to_delete:
        db.delete(cafe_to_delete)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

# --- Marketing Product Management (기존 유지) ---
@router.get("/product-selection", response_class=HTMLResponse)
async def select_marketing_product(request: Request, db: Session = Depends(get_db)):
    existing_ids = [mp.product_id for mp in db.query(MarketingProduct.product_id).all()]
    available_products_raw = db.query(Product).filter(Product.id.notin_(existing_ids)).all()
    # 상품 코드 순으로 정렬 (1-1, 1-2, 10-1 순서)
    available_products = sorted(available_products_raw, key=lambda p: sort_product_code(p.product_code))
    return templates.TemplateResponse("marketing_product_selection.html", {
        "request": request,
        "products": available_products
    })

@router.post("/product/add/{product_id}", response_class=RedirectResponse)
async def add_marketing_product(product_id: int, db: Session = Depends(get_db)):
    existing = db.query(MarketingProduct).filter(MarketingProduct.product_id == product_id).first()
    if not existing:
        new_marketing_product = MarketingProduct(product_id=product_id, keywords="")
        db.add(new_marketing_product)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=products", status_code=303)

# --- '글 관리' 라우트 (기존 유지) ---
@router.get("/product/posts/{mp_id}", response_class=HTMLResponse)
async def get_product_posts(
    request: Request, 
    mp_id: int, 
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    keyword_search: str = Query(""),
    error: str = Query(None)
):
    PAGE_SIZE = 40
    
    marketing_product = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).filter(MarketingProduct.id == mp_id).first()
    
    error_message = None
    if error == 'url_required':
        error_message = "오류: '등록 완료'를 체크한 경우, 글 URL을 반드시 입력해야 합니다."

    keywords_list = []
    if marketing_product and marketing_product.keywords:
        try:
            keywords_list = [item['keyword'] for item in json.loads(marketing_product.keywords) if item['active']]
        except json.JSONDecodeError:
            pass

    filtered_keywords = []
    if keyword_search:
        search_term = keyword_search.replace(" ", "").lower()
        for kw in keywords_list:
            if search_term in kw.replace(" ", "").lower():
                filtered_keywords.append(kw)
    else:
        filtered_keywords = keywords_list

    total_keywords = len(filtered_keywords)
    total_pages = math.ceil(total_keywords / PAGE_SIZE)
    offset = (page - 1) * PAGE_SIZE
    keywords_for_page = filtered_keywords[offset : offset + PAGE_SIZE]

    posts = db.query(MarketingPost).options(
        joinedload(MarketingPost.worker),
        joinedload(MarketingPost.account),
        joinedload(MarketingPost.cafe)
    ).filter(
        MarketingPost.marketing_product_id == mp_id,
        MarketingPost.keyword_text.in_(keywords_for_page)
    ).order_by(MarketingPost.keyword_text, MarketingPost.id).all()

    other_posts = []
    if page == 1 and not keyword_search:
        all_post_keywords = [p.keyword_text for p in posts]
        db_posts_for_product = db.query(MarketingPost).options(
            joinedload(MarketingPost.worker),
            joinedload(MarketingPost.account),
            joinedload(MarketingPost.cafe)
        ).filter(MarketingPost.marketing_product_id == mp_id).all()
        for p in db_posts_for_product:
            if p.keyword_text not in keywords_list and p.keyword_text not in all_post_keywords:
                other_posts.append(p)

    # 전체 통계 계산
    all_posts = db.query(MarketingPost).filter(
        MarketingPost.marketing_product_id == mp_id
    ).all()
    
    post_stats = {
        'total': len(all_posts),
        'live': sum(1 for p in all_posts if p.is_live),
        'deleted': sum(1 for p in all_posts if p.is_registration_complete and not p.is_live),
        'draft': sum(1 for p in all_posts if not p.is_registration_complete)
    }

    posts_by_keyword = {}
    for kw in keywords_for_page:
        posts_by_keyword[kw] = []
    for post in posts:
        if post.keyword_text in posts_by_keyword:
            posts_by_keyword[post.keyword_text].append(post)
    if other_posts:
        posts_by_keyword["[삭제/미지정 키워드]"] = other_posts

    all_accounts = db.query(MarketingAccount).all()
    all_cafes = db.query(TargetCafe).all()
    all_workers = db.query(User).filter(or_(User.can_manage_marketing == True, User.is_admin == True)).all()
    
    all_references = db.query(Reference).options(joinedload(Reference.comments)).order_by(Reference.ref_type, Reference.title).all()
    references_by_type = {"대안": [], "정보": [], "기타": []}
    
    # JavaScript에서 사용할 수 있도록 references를 딕셔너리로 변환
    references_json = []
    for ref in all_references:
        ref_type_str = ref.ref_type or "기타"
        if ref_type_str in references_by_type:
            references_by_type[ref_type_str].append(ref)
        else:
            references_by_type["기타"].append(ref)
        
        # 댓글 변환
        comments_list = []
        for comment in ref.comments:
            comments_list.append({
                "id": comment.id,
                "account_sequence": comment.account_sequence,
                "text": comment.text,
                "parent_id": comment.parent_id
            })
        
        # 레퍼런스 변환
        references_json.append({
            "id": ref.id,
            "title": ref.title,
            "content": ref.content,
            "ref_type": ref.ref_type,
            "comments": comments_list
        })
    
    all_memberships = db.query(CafeMembership).options(joinedload(CafeMembership.cafe)).all()
    membership_map = {}
    for membership in all_memberships:
        if membership.status == 'active':
            account_key = str(membership.account_id)  # 문자열로 변환
            if account_key not in membership_map:
                membership_map[account_key] = []
            if membership.cafe:
                membership_map[account_key].append({"id": membership.cafe.id, "name": membership.cafe.name})
    
    return templates.TemplateResponse("marketing_product_posts.html", {
        "request": request,
        "marketing_product": marketing_product,
        "posts_by_keyword": posts_by_keyword,
        "keywords_list": keywords_list,
        "all_accounts": all_accounts,
        "all_cafes": all_cafes,
        "all_workers": all_workers,
        "all_references": all_references,
        "references_by_type": references_by_type,
        "references_json": references_json,
        "membership_map": membership_map,
        "total_pages": total_pages,
        "current_page": page,
        "keyword_search": keyword_search,
        "error": error_message,
        "post_stats": post_stats
    })

@router.post("/post/add", response_class=RedirectResponse)
async def add_marketing_post(
    request: Request,
    mp_id: int = Form(...),
    keyword_text: str = Form(...),
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    worker_id: int = Form(...),
    reference_id: int = Form(None),
    post_title: str = Form(""),
    post_body: str = Form(""),
    post_comments: str = Form(""),
    is_registration_complete: bool = Form(False),
    is_live: bool = Form(False),
    post_url: str = Form(None),
    db: Session = Depends(get_db)
):
    if is_registration_complete and not post_url:
        return RedirectResponse(url=f"/marketing/product/posts/{mp_id}?error=url_required", status_code=303)

    if reference_id:
        ref = db.query(Reference).options(joinedload(Reference.comments)).filter(Reference.id == reference_id).first()
        if ref:
            if not post_title:
                post_title = ref.title
            if not post_body:
                post_body = ref.content
            if not post_comments:
                comment_map = {c.id: c for c in ref.comments}
                top_level_comments = []
                for c in ref.comments:
                    c.structured_replies = []
                for c in ref.comments:
                    if c.parent_id and c.parent_id in comment_map:
                        comment_map[c.parent_id].structured_replies.append(c)
                    elif not c.parent_id:
                        top_level_comments.append(c)
                
                def format_comments(comments, indent = ""):
                    text = ""
                    for c in comments:
                        prefix = "작성자" if c.account_sequence == 0 else f"계정 {c.account_sequence}"
                        commentLines = "\n".join([f"{indent}  {line}" for line in c.text.split('\n')])
                        text += f"{indent}{prefix}:\n{commentLines}\n\n"
                        if hasattr(c, 'structured_replies') and c.structured_replies:
                            text += format_comments(c.structured_replies, indent + "    (답글) ")
                    return text
                
                post_comments = format_comments(top_level_comments).strip()

    new_post = MarketingPost(
        marketing_product_id=mp_id,
        keyword_text=keyword_text,
        account_id=account_id,
        cafe_id=cafe_id,
        worker_id=worker_id,
        post_title=post_title,
        post_body=post_body,
        post_comments=post_comments,
        is_registration_complete=is_registration_complete,
        post_url=post_url if is_registration_complete else None,
        is_live=is_live
    )
    db.add(new_post)
    db.commit()
    return RedirectResponse(url=f"/marketing/product/posts/{mp_id}", status_code=303)

@router.post("/post/update/{post_id}", response_class=RedirectResponse)
async def update_marketing_post(
    post_id: int,
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    worker_id: int = Form(...),
    post_title: str = Form(""),
    post_body: str = Form(""),
    post_comments: str = Form(""),
    is_registration_complete: bool = Form(False),
    post_url: str = Form(None),
    is_live: bool = Form(False),
    db: Session = Depends(get_db)
):
    post = db.query(MarketingPost).filter(MarketingPost.id == post_id).first()
    mp_id = None
    if post:
        mp_id = post.marketing_product_id
        
        if is_registration_complete and not post_url:
            return RedirectResponse(url=f"/marketing/product/posts/{mp_id}?error=url_required", status_code=303)
        
        post.account_id = account_id
        post.cafe_id = cafe_id
        post.worker_id = worker_id
        post.post_title = post_title
        post.post_body = post_body
        post.post_comments = post_comments
        post.is_registration_complete = is_registration_complete
        post.post_url = post_url if is_registration_complete else None
        post.is_live = is_live
        db.commit()
    
    redirect_url = f"/marketing/product/posts/{mp_id}" if mp_id else "/marketing/cafe?tab=products"
    return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/post/delete/{post_id}", response_class=RedirectResponse)
async def delete_marketing_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(MarketingPost).filter(MarketingPost.id == post_id).first()
    mp_id = None
    if post:
        mp_id = post.marketing_product_id
        db.delete(post)
        db.commit()
    
    redirect_url = f"/marketing/product/posts/{mp_id}" if mp_id else "/marketing/cafe?tab=products"
    return RedirectResponse(url=redirect_url, status_code=303)

# --- Other Marketing Pages (기존 유지) ---
@router.get("/blog", response_class=HTMLResponse)
async def marketing_blog(request: Request):
    return templates.TemplateResponse("marketing_blog.html", {"request": request})

@router.get("/homepage", response_class=HTMLResponse)
async def marketing_homepage(request: Request):
    return templates.TemplateResponse("marketing_homepage.html", {"request": request})

@router.get("/kin", response_class=HTMLResponse)
async def marketing_kin(request: Request):
    return templates.TemplateResponse("marketing_kin.html", {"request": request})

@router.get("/marketing/schedules/create", response_class=HTMLResponse)
async def create_schedule(request: Request):
    """스케줄 생성 페이지"""
    return templates.TemplateResponse("create_schedule.html", {
        "request": request
    })