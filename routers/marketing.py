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

def generate_post_title(worker_username: str, scheduled_date: date, worker_id: int, db: Session) -> str:
    """
    글 제목 생성: {작업자명}/{날짜}-{순번}
    예: "오승아/2025-01-05-3"
    """
    # 해당 날짜에 해당 작업자의 기존 글 개수 조회
    existing_count = db.query(MarketingPost).join(
        PostSchedule, MarketingPost.id == PostSchedule.marketing_post_id
    ).filter(
        PostSchedule.worker_id == worker_id,
        PostSchedule.scheduled_date == scheduled_date
    ).count()
    
    # 다음 순번
    sequence = existing_count + 1
    
    # 날짜 포맷
    date_str = scheduled_date.strftime('%Y-%m-%d')
    
    # 제목 생성
    title = f"{worker_username}/{date_str}-{sequence}"
    
    return title

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
    
    # ✅ 1. 날짜 파라미터 처리
    date_param = request.query_params.get('date')
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    # ✅ 2. 자동 졸업 체크
    graduation_messages = []
    
    all_memberships_for_grad = db.query(CafeMembership).options(
        joinedload(CafeMembership.account),
        joinedload(CafeMembership.cafe)
    ).filter(
        CafeMembership.status.in_(['active', 'suspended'])
    ).all()
    
    for membership in all_memberships_for_grad:
        total_posts_count = db.query(PostSchedule).filter(
            PostSchedule.account_id == membership.account_id,
            PostSchedule.cafe_id == membership.cafe_id,
            PostSchedule.status.in_(['pending', 'in_progress', 'completed'])
        ).count()
        
        if total_posts_count >= 10:
            membership.status = 'graduated'
            graduation_message = f"🎓 <strong>{membership.account.account_id}</strong>님이 <strong>{membership.cafe.name}</strong> 카페를 졸업했습니다! (총 {total_posts_count}개 글)"
            graduation_messages.append(graduation_message)
    
    if graduation_messages:
        db.commit()
    
    # ✅ 3. 현재 사용자 스케줄 조회
    username = request.session.get("user")
    current_user = db.query(User).filter(User.username == username).first()
    
    today_schedules = []
    completed_count = 0
    daily_quota = 0
    
    if current_user:
        daily_quota = current_user.daily_quota or 0
        
        today_schedules_query = db.query(PostSchedule).options(
            joinedload(PostSchedule.account),
            joinedload(PostSchedule.cafe),
            joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product),
            joinedload(PostSchedule.marketing_post),
            joinedload(PostSchedule.worker)
        ).filter(
            PostSchedule.worker_id == current_user.id,
            PostSchedule.scheduled_date == selected_date
        )
        
        today_schedules = today_schedules_query.order_by(PostSchedule.status.desc(), PostSchedule.id).all()
        completed_count = sum(1 for s in today_schedules if s.status == 'completed')
    
    remaining_tasks = daily_quota - len(today_schedules)
    
    # ✅ 4. 오류 메시지
    error_messages = {
        'duplicate_account': "이미 사용 중인 아이디입니다.",
        'duplicate_reference': "이미 사용 중인 레퍼런스 제목입니다.",
        'no_workers': "작업자를 선택해주세요.",
        'no_keywords': "키워드가 없습니다.",
        'invalid_keywords': "키워드 형식이 잘못되었습니다.",
        'no_memberships': "활성 연동이 없습니다.",
        'no_data': "활성 상품이나 연동이 없습니다."
    }
    error_message = error_messages.get(error)
    
    # ✅ 5. 연동 관리 탭 데이터
    selected_cafe_id = request.query_params.get('cafe_id')
    status_filter = request.query_params.get('status_filter', 'all')
    selected_cafe = None
    memberships = []
    
    if selected_cafe_id:
        selected_cafe = db.query(TargetCafe).filter(TargetCafe.id == selected_cafe_id).first()
        query = db.query(CafeMembership).options(joinedload(CafeMembership.account))
        query = query.filter(CafeMembership.cafe_id == selected_cafe_id)
        if status_filter != 'all':
            query = query.filter(CafeMembership.status == status_filter)
        memberships = query.order_by(CafeMembership.account_id).all()
    
    # ✅ 6. 카페 목록
    cafes_raw = db.query(TargetCafe).all()
    cafes = sorted(cafes_raw, key=lambda c: sort_product_code(c.name))
    
    # ✅ 7. 계정 목록
    category_filter = request.query_params.get('category_filter', 'all')
    accounts_query = db.query(MarketingAccount)
    if category_filter != 'all':
        accounts_query = accounts_query.filter(MarketingAccount.category == category_filter)
    accounts = accounts_query.order_by(MarketingAccount.id).all()
    
    # ✅ 8. 마케팅 상품 목록
    marketing_products_raw = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    marketing_products = sorted(
        marketing_products_raw, 
        key=lambda mp: sort_product_code(mp.product.product_code if mp.product else "")
    )
    
    # 상품별 키워드 수 계산
    for mp in marketing_products:
        if mp.keywords:
            try:
                keywords_data = json.loads(mp.keywords)
                mp.keyword_count = len([k for k in keywords_data if k.get('active', True)])
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
    
    # ✅ 9. 레퍼런스 목록
    reference_filter = request.query_params.get('ref_filter', 'all')
    references_query = db.query(Reference).options(joinedload(Reference.last_modified_by))
    if reference_filter != 'all':
        references_query = references_query.filter(Reference.ref_type == reference_filter)
    references_raw = references_query.order_by(Reference.id.desc()).all()
    
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
    
    # ✅ 10. 작업자 목록
    all_workers = db.query(User).filter(
        or_(User.can_manage_marketing == True, User.is_admin == True)
    ).all()
    
    workers = all_workers  # 동일
    
    worker_quotas = {}
    for worker in workers:
        worker_quotas[worker.id] = worker.daily_quota or 6
    
    # ✅ 11. 전체 통계 (selected_date 기준)
    all_today_schedules = db.query(PostSchedule).filter(
        PostSchedule.scheduled_date == selected_date
    ).all()
    
    today_stats = {
        'total': len(all_today_schedules),
        'completed': sum(1 for s in all_today_schedules if s.status == 'completed'),
        'in_progress': sum(1 for s in all_today_schedules if s.status == 'in_progress'),
        'pending': sum(1 for s in all_today_schedules if s.status == 'pending')
    }
    
    # ✅ 12. 계정-카페 매핑 (membership_map)
    all_memberships_map = db.query(CafeMembership).options(
        joinedload(CafeMembership.cafe)
    ).all()
    
    membership_map = {}
    for membership in all_memberships_map:
        if membership.status == 'active':
            account_key = str(membership.account_id)
            if account_key not in membership_map:
                membership_map[account_key] = []
            if membership.cafe:
                membership_map[account_key].append({
                    "id": membership.cafe.id, 
                    "name": membership.cafe.name
                })
    
    # ✅ 13. 상품별 키워드 매핑
    product_keywords_map = {}
    for mp in marketing_products:
        if mp.keywords:
            try:
                keywords_list = json.loads(mp.keywords)
                active_keywords = [
                    item['keyword'] 
                    for item in keywords_list 
                    if item.get('active', True)
                ]
                product_keywords_map[mp.id] = active_keywords
            except json.JSONDecodeError:
                product_keywords_map[mp.id] = []
        else:
            product_keywords_map[mp.id] = []
    
    # ✅ 14. 레퍼런스 데이터 (타입별)
    all_references = db.query(Reference).options(
        joinedload(Reference.comments)
    ).order_by(Reference.ref_type, Reference.title).all()

    # ✅ JSON 직렬화 가능한 형태로 변환
    references_json = []
    for ref in all_references:
        ref_dict = {
            'id': ref.id,
            'title': ref.title,
            'ref_type': ref.ref_type,
            'content': ref.content,
            'comments': [
                {
                    'id': c.id,
                    'account_sequence': c.account_sequence,
                    'text': c.text,
                    'parent_id': c.parent_id
                }
                for c in (ref.comments or [])
            ]
        }
        references_json.append(ref_dict)

    references_by_type = {}
    for ref in all_references:
        ref_type = ref.ref_type or "기타"
        if ref_type not in references_by_type:
            references_by_type[ref_type] = []
        references_by_type[ref_type].append(ref)

    # ✅ 15. 템플릿 렌더링
    return templates.TemplateResponse("marketing_cafe.html", {
        "request": request,
        "cafes": cafes,
        "accounts": accounts,
        "marketing_products": marketing_products,
        "memberships": memberships,
        "selected_cafe": selected_cafe,
        "status_filter": status_filter,
        "category_filter": category_filter,
        "error": error_message,
        "references": references,
        "reference_filter": reference_filter,
        "active_tab": tab,
        
        # 스케줄 관련
        "today_schedules": today_schedules,
        "daily_quota": daily_quota,
        "completed_count": completed_count,
        "remaining_tasks": remaining_tasks,
        "all_workers": all_workers,
        
        # 통계
        "today_stats": today_stats,
        "workers": workers,
        "worker_quotas": worker_quotas,
        "graduation_messages": graduation_messages,
        
        # 매핑 데이터
        "membership_map": membership_map,
        "product_keywords_map": product_keywords_map,
        "all_references": all_references,
        "references_by_type": references_by_type,
        "references_json": references_json,  # ✅ 추가!
        
        # 날짜
        "selected_date": selected_date,
        "today": date.today()
    })

# --- 스케줄 관리 라우터 추가 ---

@router.get("/schedules", response_class=HTMLResponse)
async def get_schedules(
    request: Request,
    selected_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """전체 현황 관리 페이지 (관리자 전용)"""
    
    # 로그인 체크
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    # 관리자 권한 체크
    is_admin = request.session.get("is_admin", False)
    if not is_admin:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>접근 거부</title>
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 40px;
                    border-radius: 15px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }
                h1 {
                    color: #e74c3c;
                    margin-bottom: 20px;
                }
                p {
                    color: #555;
                    font-size: 18px;
                    margin-bottom: 30px;
                }
                .btn {
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 25px;
                    transition: transform 0.2s;
                }
                .btn:hover {
                    transform: translateY(-2px);
                }
                .icon {
                    font-size: 80px;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">🚫</div>
                <h1>접근 불가</h1>
                <p>이 페이지는 관리자만 접근할 수 있습니다.<br>관리자에게 문의하세요.</p>
                <a href="/" class="btn">홈으로 돌아가기</a>
            </div>
        </body>
        </html>
        """, status_code=403)
    
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
    ).scalar_subquery()
    
    unlinked_posts = db.query(MarketingPost).options(
        joinedload(MarketingPost.worker),
        joinedload(MarketingPost.marketing_product).joinedload(MarketingProduct.product)
    ).filter(
        MarketingPost.is_registration_complete == True,
        ~MarketingPost.id.in_(linked_post_ids)
    ).all()
    
    # 레퍼런스 데이터 추가 (모달용)
    all_references = db.query(Reference).options(
        joinedload(Reference.comments)
    ).order_by(Reference.ref_type, Reference.title).all()
    
    references_by_type = {}
    for ref in all_references:
        if ref.ref_type not in references_by_type:
            references_by_type[ref.ref_type] = []
        references_by_type[ref.ref_type].append(ref)
    
    return templates.TemplateResponse("marketing_schedules.html", {
        "request": request,
        "username": username,
        "selected_date": target_date,
        "today": today,  # ✅ today 추가!
        "schedules": schedules,
        "today_stats": today_stats,
        "workers": workers,
        "accounts": accounts,
        "cafes": cafes,
        "marketing_products": marketing_products,
        "membership_map": membership_map,
        "product_keywords_map": product_keywords_map,
        "unlinked_posts": unlinked_posts,
        "all_references": all_references,
        "references_by_type": references_by_type
    })

# ... (나머지 모든 라우터 함수들은 동일하게 유지) ...

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
    """새 스케줄 추가 + 글 자동 생성"""
    
    # 작업자 정보 조회
    worker = db.query(User).filter(User.id == worker_id).first()
    if not worker:
        return RedirectResponse(url="/marketing/schedules", status_code=303)
    
    # 제목 생성
    post_title = generate_post_title(worker.username, scheduled_date, worker_id, db)
    
    # MarketingPost 생성
    new_post = MarketingPost(
        marketing_product_id=marketing_product_id,
        keyword_text=keyword_text,
        post_title=post_title,
        post_body="",
        post_url="",
        worker_id=worker_id,
        account_id=account_id,
        cafe_id=cafe_id
    )
    db.add(new_post)
    db.flush()  # ID 생성
    
    # PostSchedule 생성 (글과 연결)
    new_schedule = PostSchedule(
        scheduled_date=scheduled_date,
        worker_id=worker_id,
        account_id=account_id,
        cafe_id=cafe_id,
        marketing_product_id=marketing_product_id,
        keyword_text=keyword_text,
        notes=notes,
        status="pending",
        marketing_post_id=new_post.id  # 연결!
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
    """스케줄 및 연결된 글 삭제"""
    
    schedule = db.query(PostSchedule).filter(
        PostSchedule.id == schedule_id
    ).first()
    
    if schedule:
        # 연결된 MarketingPost 먼저 삭제
        if schedule.marketing_post_id:
            post = db.query(MarketingPost).filter(
                MarketingPost.id == schedule.marketing_post_id
            ).first()
            if post:
                db.delete(post)
        
        # 스케줄 삭제
        db.delete(schedule)
        db.commit()
    
    return {"success": True}

@router.post("/schedule/{schedule_id}/change-status")
async def change_schedule_status(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """스케줄 상태 변경 (MarketingPost와 동기화)"""
    
    body = await request.json()
    new_status = body.get('status')
    
    if new_status not in ['pending', 'in_progress', 'completed', 'skipped', 'deleted']:
        return {"success": False, "error": "Invalid status"}
    
    schedule = db.query(PostSchedule).filter(
        PostSchedule.id == schedule_id
    ).first()
    
    if schedule:
        schedule.status = new_status
        
        # 상태에 따른 추가 처리
        if new_status == 'completed':
            schedule.is_completed = True
            if not schedule.completed_at:
                schedule.completed_at = datetime.utcnow()
        elif new_status == 'pending':
            schedule.is_completed = False
            schedule.completed_at = None
        
        # 연결된 MarketingPost도 동기화
        # MarketingPost는 status 필드가 없으므로 is_registration_complete만 사용
        if schedule.marketing_post_id:
            post = db.query(MarketingPost).filter(
                MarketingPost.id == schedule.marketing_post_id
            ).first()
            if post:
                if new_status == 'completed':
                    post.is_registration_complete = True
                elif new_status == 'pending':
                    post.is_registration_complete = False
        
        db.commit()
        return {"success": True}
    
    return {"success": False, "error": "Schedule not found"}

@router.get("/schedule/{schedule_id}/info")
async def get_schedule_info(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    """스케줄 정보 가져오기 (모달용)"""
    
    schedule = db.query(PostSchedule).options(
        joinedload(PostSchedule.worker),
        joinedload(PostSchedule.account),
        joinedload(PostSchedule.cafe),
        joinedload(PostSchedule.marketing_product)
    ).filter(PostSchedule.id == schedule_id).first()
    
    if not schedule:
        return {"success": False, "error": "Schedule not found"}
    
    # 스케줄 정보
    schedule_data = {
        "worker_id": schedule.worker_id,
        "account_id": schedule.account_id,
        "cafe_id": schedule.cafe_id,
        "keyword_text": schedule.keyword_text  # ✅ 키워드 추가!

    }
    
    # 연결된 글 정보
    post_data = None
    if schedule.marketing_post_id:
        post = db.query(MarketingPost).filter(
            MarketingPost.id == schedule.marketing_post_id
        ).first()
        if post:
            post_data = {
                "id": post.id,
                "post_title": post.post_title,
                "post_body": post.post_body,
                "post_comments": post.post_comments,
                "post_url": post.post_url,
                "is_live": post.is_live,
                "is_registration_complete": post.is_registration_complete,
                "worker_id": post.worker_id,
                "account_id": post.account_id,
                "cafe_id": post.cafe_id,
                "keyword_text": post.keyword_text  # ✅ 키워드 추가!

            }
    
    return {
        "success": True,
        "schedule_id": schedule.id,
        "marketing_post_id": schedule.marketing_post_id,
        "status": schedule.status,
        "schedule": schedule_data,
        "post": post_data
    }

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
    """스케줄 자동 생성 (개선된 로직)"""
    
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
    
    # 활성 계정-카페 매핑
    memberships = db.query(CafeMembership).filter(
        CafeMembership.status == 'active'
    ).all()
    
    if not memberships:
        return RedirectResponse(url="/marketing/cafe?tab=schedule&error=no_memberships", status_code=303)
    
    # ✅ ========================================
    # 헬퍼 함수들
    # ========================================
    
    def get_active_post_count(keyword):
        """키워드의 활성 글 수 (completed + pending + in_progress)"""
        return db.query(PostSchedule).filter(
            PostSchedule.keyword_text == keyword,
            PostSchedule.marketing_product_id == marketing_product_id,
            PostSchedule.status.in_(['completed', 'pending', 'in_progress'])  # ✅ in_progress 추가!
        ).count()
    
    def get_total_account_cafe_posts(account_id, cafe_id):
        """계정+카페 조합의 전체 글 수 (모든 상품/키워드)"""
        return db.query(PostSchedule).filter(
            PostSchedule.account_id == account_id,
            PostSchedule.cafe_id == cafe_id,
            PostSchedule.status.in_(['pending', 'in_progress', 'completed'])
        ).count()
    
    def get_existing_cafes_for_keyword(keyword):
        """키워드에 이미 사용된 카페들"""
        existing_posts = db.query(PostSchedule).filter(
            PostSchedule.keyword_text == keyword,
            PostSchedule.marketing_product_id == marketing_product_id,
            PostSchedule.status != 'deleted'
        ).all()
        
        cafe_ids = list(set([post.cafe_id for post in existing_posts]))
        return cafe_ids[:3]  # 최대 3개만
    
    def get_alternative_account_cafe(keyword, unavailable_cafe_id):
        """연동 해제 시 대체 계정+카페 조합 찾기 (순환)"""
        
        # 이 키워드로 작성된 다른 글들 (연동 해제된 카페 제외)
        other_posts = db.query(PostSchedule).filter(
            PostSchedule.keyword_text == keyword,
            PostSchedule.marketing_product_id == marketing_product_id,
            PostSchedule.cafe_id != unavailable_cafe_id,
            PostSchedule.status != 'deleted'
        ).order_by(PostSchedule.id).all()
        
        if not other_posts:
            return None, None
        
        # 순환 인덱스 계산 (해당 카페에 대체로 생성된 글 수)
        replacement_count = db.query(PostSchedule).filter(
            PostSchedule.keyword_text == keyword,
            PostSchedule.marketing_product_id == marketing_product_id,
            PostSchedule.cafe_id == unavailable_cafe_id,
            PostSchedule.status != 'deleted'
        ).count() - 3  # 원래 3개를 제외
        
        if replacement_count < 0:
            replacement_count = 0
        
        rotation_index = replacement_count % len(other_posts)
        
        # 10개 제한 체크하며 순환
        attempts = 0
        while attempts < len(other_posts):
            selected_post = other_posts[rotation_index]
            
            # 10개 제한 체크
            total_posts = get_total_account_cafe_posts(
                selected_post.account_id, 
                selected_post.cafe_id
            )
            
            if total_posts < 10:
                return selected_post.account_id, selected_post.cafe_id
            
            # 다음 인덱스로 순환
            rotation_index = (rotation_index + 1) % len(other_posts)
            attempts += 1
        
        # 모든 조합이 10개 제한에 걸림
        return None, None
    
    # ✅ ========================================
    # 날짜 범위 내에서 스케줄 생성
    # ========================================
    
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
                
                # 일일 할당량만큼 스케줄 생성 시도
                posts_created_today = 0
                
                while posts_created_today < daily_quota:
                    if keyword_index >= len(active_keywords):
                        keyword_index = 0  # 키워드 순환
                    
                    keyword = active_keywords[keyword_index]
                    
                    # ✅ 1단계: 키워드당 6개 제한 체크
                    active_count = get_active_post_count(keyword)
                    if active_count >= 6:
                        keyword_index += 1
                        continue  # 이 키워드 스킵
                    
                    available_slots = 6 - active_count
                    
                    # ✅ 2단계: 기존 카페 조회 (고정)
                    existing_cafe_ids = get_existing_cafes_for_keyword(keyword)
                    
                    if len(existing_cafe_ids) == 0:
                        # 첫 생성: 3개 카페 선택
                        target_cafe_ids = []
                        for i in range(3):
                            membership_index = (keyword_index * 3 + i) % len(memberships)
                            target_cafe_ids.append(memberships[membership_index].cafe_id)
                    else:
                        # 기존 카페 사용 (고정)
                        target_cafe_ids = existing_cafe_ids
                    
                    # ✅ 3단계: 각 카페별로 글 생성
                    for cafe_id in target_cafe_ids:
                        if posts_created_today >= daily_quota:
                            break
                        
                        if active_count >= 6:
                            break  # 6개 제한 도달
                        
                        # 이전에 사용된 계정 찾기
                        previous_post = db.query(PostSchedule).filter(
                            PostSchedule.keyword_text == keyword,
                            PostSchedule.marketing_product_id == marketing_product_id,
                            PostSchedule.cafe_id == cafe_id,
                            PostSchedule.status != 'deleted'
                        ).order_by(PostSchedule.id).first()
                        
                        if previous_post:
                            # 기존 계정 재사용
                            use_account_id = previous_post.account_id
                            use_cafe_id = cafe_id
                            
                            # 연동 상태 체크
                            membership = db.query(CafeMembership).filter(
                                CafeMembership.account_id == use_account_id,
                                CafeMembership.cafe_id == use_cafe_id,
                                CafeMembership.status == 'active'
                            ).first()
                            
                            if not membership:
                                # ✅ 연동 해제됨 → 대체 계정 찾기 (순환)
                                alt_account_id, alt_cafe_id = get_alternative_account_cafe(
                                    keyword, 
                                    cafe_id
                                )
                                
                                if not alt_account_id:
                                    # 대체 불가능 → 이 키워드 스킵
                                    break
                                
                                use_account_id = alt_account_id
                                use_cafe_id = alt_cafe_id
                            
                            # 10개 제한 체크
                            total_posts = get_total_account_cafe_posts(
                                use_account_id, 
                                use_cafe_id
                            )
                            
                            if total_posts >= 10:
                                # 10개 제한 → 대체 계정 찾기
                                alt_account_id, alt_cafe_id = get_alternative_account_cafe(
                                    keyword, 
                                    cafe_id
                                )
                                
                                if not alt_account_id:
                                    # 대체 불가능 → 이 키워드 스킵
                                    break
                                
                                use_account_id = alt_account_id
                                use_cafe_id = alt_cafe_id
                        else:
                            # 완전히 새로운 카페 → 새 계정 선택
                            membership_index = (keyword_index * 3) % len(memberships)
                            membership = memberships[membership_index]
                            use_account_id = membership.account_id
                            use_cafe_id = cafe_id
                            
                            # 10개 제한 체크
                            total_posts = get_total_account_cafe_posts(
                                use_account_id, 
                                use_cafe_id
                            )
                            
                            if total_posts >= 10:
                                # 다른 계정 찾기
                                found = False
                                for mb in memberships:
                                    if mb.cafe_id == cafe_id:
                                        total = get_total_account_cafe_posts(
                                            mb.account_id, 
                                            cafe_id
                                        )
                                        if total < 10:
                                            use_account_id = mb.account_id
                                            found = True
                                            break
                                
                                if not found:
                                    continue  # 사용 가능한 계정 없음
                        
                        # ✅ 제목 생성
                        post_title = generate_post_title(
                            user.username, 
                            current_date, 
                            worker_id, 
                            db
                        )
                        
                        # ✅ MarketingPost 생성
                        new_post = MarketingPost(
                            marketing_product_id=marketing_product_id,
                            keyword_text=keyword,
                            post_title=post_title,
                            post_body="",
                            post_url="",
                            worker_id=worker_id,
                            account_id=use_account_id,
                            cafe_id=use_cafe_id
                        )
                        db.add(new_post)
                        db.flush()  # ID 생성
                        
                        # ✅ PostSchedule 생성 (글과 연결)
                        new_schedule = PostSchedule(
                            scheduled_date=current_date,
                            worker_id=worker_id,
                            account_id=use_account_id,
                            cafe_id=use_cafe_id,
                            marketing_product_id=marketing_product_id,
                            keyword_text=keyword,
                            status="pending",
                            marketing_post_id=new_post.id
                        )
                        db.add(new_schedule)
                        
                        posts_created_today += 1
                        active_count += 1
                        
                        print(f"✅ 생성: {keyword} | {use_account_id} + {use_cafe_id} | {current_date}")
                    
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
    """현재 사용자에게 선택된 날짜의 할당량만큼 작업을 한번에 생성"""
    username = request.session.get("user")
    current_user = db.query(User).filter(User.username == username).first()
    
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    
    # ✅ 폼에서 날짜 받기
    form_data = await request.form()
    target_date_str = form_data.get('target_date')
    
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except:
            target_date = date.today()
    else:
        target_date = date.today()
    
    daily_quota = current_user.daily_quota or 6
    
    # ✅ 선택된 날짜의 기존 작업 수 확인
    existing_count = db.query(PostSchedule).filter(
        PostSchedule.worker_id == current_user.id,
        PostSchedule.scheduled_date == target_date
    ).count()
    
    # 생성해야 할 작업 수
    to_create = daily_quota - existing_count
    
    if to_create <= 0:
        return RedirectResponse(url=f"/marketing/cafe?tab=status&date={target_date}", status_code=303)
    
    # ✅ 활성 마케팅 상품과 연동 가져오기
    marketing_products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    
    active_memberships = db.query(CafeMembership).filter(
        CafeMembership.status == 'active'
    ).all()
    
    if not marketing_products or not active_memberships:
        return RedirectResponse(url=f"/marketing/cafe?tab=status&date={target_date}&error=no_data", status_code=303)
    
    # ✅ 각 상품의 키워드 수집
    all_keywords = []
    for mp in marketing_products:
        if mp.keywords:
            try:
                keywords_data = json.loads(mp.keywords)
                for kw_item in keywords_data:
                    if kw_item.get('active', True):
                        all_keywords.append({
                            'keyword': kw_item['keyword'],
                            'product_id': mp.id,
                            'product': mp
                        })
            except:
                continue
    
    if not all_keywords:
        return RedirectResponse(url=f"/marketing/cafe?tab=status&date={target_date}&error=no_keywords", status_code=303)
    
    # ✅ 작업 생성 (선택된 날짜로)
    created_count = 0
    keyword_index = 0
    
    while created_count < to_create and keyword_index < len(all_keywords) * 10:
        kw_data = all_keywords[keyword_index % len(all_keywords)]
        keyword = kw_data['keyword']
        mp = kw_data['product']
        
        # 이 키워드의 활성 글 수 체크 (6개 제한)
        active_count = db.query(PostSchedule).filter(
            PostSchedule.keyword_text == keyword,
            PostSchedule.marketing_product_id == mp.id,
            PostSchedule.status.in_(['completed', 'pending', 'in_progress'])
        ).count()
        
        if active_count >= 6:
            keyword_index += 1
            continue
        
        # 카페 선택 (순환)
        membership = active_memberships[created_count % len(active_memberships)]
        
        # 10개 제한 체크
        total_posts = db.query(PostSchedule).filter(
            PostSchedule.account_id == membership.account_id,
            PostSchedule.cafe_id == membership.cafe_id,
            PostSchedule.status.in_(['pending', 'in_progress', 'completed'])
        ).count()
        
        if total_posts >= 10:
            keyword_index += 1
            continue
        
        # 제목 생성
        post_title = generate_post_title(current_user.username, target_date, current_user.id, db)
        
        # MarketingPost 생성
        new_post = MarketingPost(
            marketing_product_id=mp.id,
            keyword_text=keyword,
            post_title=post_title,
            post_body="",
            post_url="",
            worker_id=current_user.id,
            account_id=membership.account_id,
            cafe_id=membership.cafe_id
        )
        db.add(new_post)
        db.flush()
        
        # PostSchedule 생성 (선택된 날짜로)
        new_schedule = PostSchedule(
            scheduled_date=target_date,  # ✅ 선택된 날짜
            worker_id=current_user.id,
            account_id=membership.account_id,
            cafe_id=membership.cafe_id,
            marketing_product_id=mp.id,
            keyword_text=keyword,
            status="pending",
            marketing_post_id=new_post.id
        )
        db.add(new_schedule)
        
        created_count += 1
        keyword_index += 1
    
    db.commit()
    print(f"✅ {current_user.username}님에게 {target_date} 날짜로 {created_count}개 작업 할당 완료")
    
    # ✅ 생성된 날짜로 리다이렉트
    return RedirectResponse(url=f"/marketing/cafe?tab=status&date={target_date}", status_code=303)

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

@router.get("/reference/{ref_id}/content")
async def get_reference_content(ref_id: int, db: Session = Depends(get_db)):
    """레퍼런스 내용 가져오기 (JSON)"""
    reference = db.query(Reference).options(
        joinedload(Reference.comments)
    ).filter(Reference.id == ref_id).first()
    
    if not reference:
        return {"success": False, "error": "Reference not found"}
    
    # 댓글 정보 구성
    comments_data = []
    for comment in reference.comments:
        if not comment.parent_id:  # 최상위 댓글만
            comments_data.append({
                "commenter_name": f"계정{comment.account_sequence}",
                "comment_text": comment.text
            })
    
    return {
        "success": True,
        "title": reference.title,
        "body": reference.content or "",
        "comments": comments_data
    }

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
    status_filter: str = Query("all"),  # ✅ 상태 필터 추가
    error: str = Query(None)
):
    PAGE_SIZE = 10
    
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

    # ✅ 상태 필터에 따라 쿼리 수정
    posts_query = db.query(MarketingPost).options(
        joinedload(MarketingPost.worker),
        joinedload(MarketingPost.account),
        joinedload(MarketingPost.cafe),
        joinedload(MarketingPost.schedules)
    ).filter(
        MarketingPost.marketing_product_id == mp_id,
        MarketingPost.keyword_text.in_(keywords_for_page)
    )
    
    # ✅ 상태 필터 적용
    if status_filter != 'all':
        # schedules를 통해 status 필터링
        posts_query = posts_query.join(
            PostSchedule, 
            MarketingPost.id == PostSchedule.marketing_post_id
        ).filter(
            PostSchedule.status == status_filter
        )
    
    posts = posts_query.order_by(MarketingPost.keyword_text, MarketingPost.id).all()

    other_posts = []
    if page == 1 and not keyword_search:
        all_post_keywords = [p.keyword_text for p in posts]
        db_posts_for_product_query = db.query(MarketingPost).options(
            joinedload(MarketingPost.worker),
            joinedload(MarketingPost.account),
            joinedload(MarketingPost.cafe),
            joinedload(MarketingPost.schedules)
        ).filter(MarketingPost.marketing_product_id == mp_id)
        
        # ✅ other_posts도 필터 적용
        if status_filter != 'all':
            db_posts_for_product_query = db_posts_for_product_query.join(
                PostSchedule,
                MarketingPost.id == PostSchedule.marketing_post_id
            ).filter(
                PostSchedule.status == status_filter
            )
        
        db_posts_for_product = db_posts_for_product_query.all()
        for p in db_posts_for_product:
            if p.keyword_text not in keywords_list and p.keyword_text not in all_post_keywords:
                other_posts.append(p)

    # 전체 통계 계산 (PostSchedule의 status 기반)
    all_posts = db.query(MarketingPost).options(
        joinedload(MarketingPost.schedules)
    ).filter(
        MarketingPost.marketing_product_id == mp_id
    ).all()
    
    # PostSchedule의 status 기반으로 통계 계산
    def get_post_status(post):
        """Post의 연결된 schedule의 status를 반환"""
        if post.schedules:
            # 가장 최근 schedule의 status 사용
            return post.schedules[0].status
        return 'pending'  # schedule이 없으면 pending
    
    post_stats = {
        'total': len(all_posts),
        'pending': sum(1 for p in all_posts if get_post_status(p) == 'pending'),
        'in_progress': sum(1 for p in all_posts if get_post_status(p) == 'in_progress'),
        'completed': sum(1 for p in all_posts if get_post_status(p) == 'completed'),
        'skipped': sum(1 for p in all_posts if get_post_status(p) == 'skipped'),
        'deleted': sum(1 for p in all_posts if get_post_status(p) == 'deleted')
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
    
    # today_stats 추가 (HTML 템플릿에서 사용 중)
    today_stats = {
        'total': 0,
        'pending': 0,
        'in_progress': 0,
        'completed': 0
    }
    
    # selected_date 추가 (HTML 템플릿에서 사용될 수 있음)
    from datetime import date
    selected_date = date.today()
    
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
        "post_stats": post_stats,
        "today_stats": today_stats,
        "selected_date": selected_date,
        "status_filter": status_filter  # ✅ 템플릿에 전달

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
        
        # Option C: URL 입력 시 자동 완료
        # MarketingPost는 is_registration_complete만 사용
        if post_url and post_url.strip():
            post.is_registration_complete = True
        
        # 연결된 PostSchedule 동기화
        schedule = db.query(PostSchedule).filter(
            PostSchedule.marketing_post_id == post_id
        ).first()
        
        if schedule:
            schedule.account_id = account_id
            schedule.cafe_id = cafe_id
            schedule.worker_id = worker_id
            
            # URL 입력 시 스케줄도 완료로 변경
            if post_url and post_url.strip():
                schedule.status = "completed"
                schedule.is_completed = True
                schedule.completed_at = datetime.utcnow()
        
        db.commit()
    
    redirect_url = f"/marketing/product/posts/{mp_id}" if mp_id else "/marketing/cafe?tab=products"
    return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/post/delete/{post_id}", response_class=RedirectResponse)
async def delete_marketing_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(MarketingPost).filter(MarketingPost.id == post_id).first()
    mp_id = None
    if post:
        mp_id = post.marketing_product_id
        
        # 연결된 PostSchedule 먼저 삭제
        schedule = db.query(PostSchedule).filter(
            PostSchedule.marketing_post_id == post_id
        ).first()
        if schedule:
            db.delete(schedule)
        
        # 글 삭제
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