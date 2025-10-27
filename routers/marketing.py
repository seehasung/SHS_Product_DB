from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func, distinct, select
from datetime import date, datetime, timedelta
from typing import Optional, List
import json
import math


# Reference, Comment, User 및 신규 MarketingPost 모델을 import
from database import (
    SessionLocal, TargetCafe, MarketingAccount, Product, MarketingProduct,
    CafeMembership, Reference, Comment, User, MarketingPost, WorkTask,
    PostSchedule, AccountCafeUsage, PostingRound
)


router = APIRouter(prefix="/marketing")
templates = Jinja2Templates(directory="templates")

# --- Helper Functions ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Main Marketing Cafe Page ---
@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get('tab', 'status')
    error = request.query_params.get('error')
    cafe_id = request.query_params.get('cafe_id', None)
    if cafe_id:
        cafe_id = int(cafe_id)
    
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
        'db_error': "데이터베이스 오류가 발생했습니다.",
        'keyword_needed': "키워드를 입력해주세요.",
        'duplicate_keyword': "이미 존재하는 키워드입니다."
    }
    
    error_message = error_messages.get(error, "")
    
    accounts = db.query(MarketingAccount).all()
    cafes = db.query(TargetCafe).all()
    
    all_products = db.query(Product).all()
    
    marketing_products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    
    # --- 참조 탭 관련 ---
    references = db.query(Reference).options(
        joinedload(Reference.comments)
    ).order_by(Reference.ref_type, Reference.title).all()
    
    # 타입별로 그룹화
    references_by_type = {"대안": [], "정보": [], "기타": []}
    
    for ref in references:
        ref_type_str = ref.ref_type or "기타"  # None이면 '기타'로 처리
        
        if ref_type_str in references_by_type:
            references_by_type[ref_type_str].append(ref)
        else:
            references_by_type["기타"].append(ref)
    
    # --- 멤버십 탭 관련 ---
    memberships = db.query(CafeMembership).options(
        joinedload(CafeMembership.account),
        joinedload(CafeMembership.cafe)
    ).all()
    
    # 선택된 카페와 필터 처리
    selected_cafe = None
    status_filter = request.query_params.get("status_filter", "all")
    reference_filter = request.query_params.get("ref_filter", "all")
    account_filter = request.query_params.get("account_filter", "all")
    
    if tab == "memberships" and cafe_id:
        selected_cafe = db.query(TargetCafe).filter(TargetCafe.id == cafe_id).first()
        if selected_cafe:
            # 선택된 카페의 멤버십만 필터링
            memberships_query = db.query(CafeMembership).options(
                joinedload(CafeMembership.account),
                joinedload(CafeMembership.cafe)
            ).filter(CafeMembership.cafe_id == cafe_id)
            
            if status_filter != "all":
                memberships_query = memberships_query.filter(CafeMembership.status == status_filter)
            
            memberships = memberships_query.all()
    
    # 레퍼런스 필터 처리
    if tab == "references" and reference_filter != "all":
        references = db.query(Reference).filter(Reference.ref_type == reference_filter).all()
        # references_by_type 재구성
        references_by_type = {}
        for ref in references:
            ref_type_str = ref.ref_type or "미지정"
            if ref_type_str not in references_by_type:
                references_by_type[ref_type_str] = []
            references_by_type[ref_type_str].append(ref)
    
    # 계정 필터 처리
    if tab == "accounts" and account_filter != "all":
        accounts = db.query(MarketingAccount).filter(MarketingAccount.category == account_filter).all()
    
    return templates.TemplateResponse("marketing_cafe.html", {
        "request": request,
        "accounts": accounts,
        "cafes": cafes,
        "memberships": memberships,
        "selected_cafe": selected_cafe,
        "status_filter": status_filter,
        "reference_filter": reference_filter,
        "account_filter": account_filter,
        "references": references,
        "references_by_type": references_by_type,
        "tab": tab,
        "error": error,
        "all_products": all_products,
        "marketing_products": marketing_products,
        "work_tasks": work_tasks,
        "completed_count": completed_count,
        "daily_quota": daily_quota,
        "remaining_tasks": remaining_tasks,
        "today": today,
        "today_schedules": today_schedules,
        "today_stats": today_stats,
        "workers": workers,
        "worker_quotas": worker_quotas
    })

# --- Account CRUD ---
@router.get("/accounts/add", response_class=HTMLResponse)
async def add_account_page(request: Request):
    """계정 추가 페이지"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    return templates.TemplateResponse("marketing_account_add.html", {
        "request": request,
        "platforms": ["Naver", "Daum", "Google", "Facebook"],
        "categories": ["최적화", "일반", "프리미엄"]
    })

@router.post("/accounts/add", response_class=RedirectResponse)
async def add_account(
    request: Request,
    platform: str = Form("Naver"),
    account_id: str = Form(...),
    account_pw: str = Form(...),
    ip_address: str = Form(None),
    category: str = Form('최적화'),
    db: Session = Depends(get_db)
):
    try:
        new_account = MarketingAccount(
            platform=platform,
            account_id=account_id,
            account_pw=account_pw,
            ip_address=ip_address,
            category=category
        )
        db.add(new_account)
        db.commit()
        return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)
    except IntegrityError:
        return RedirectResponse(url="/marketing/cafe?tab=accounts&error=duplicate_account", status_code=303)

@router.post("/account/add", response_class=RedirectResponse)
async def add_account_alias(
    request: Request,
    platform: str = Form("Naver"),
    account_id: str = Form(...),
    account_pw: str = Form(...),
    ip_address: str = Form(None),
    category: str = Form('최적화'),
    db: Session = Depends(get_db)
):
    """계정 추가 (별칭 라우트)"""
    return await add_account(request, platform, account_id, account_pw, ip_address, category, db)

@router.post("/accounts/edit/{account_id}", response_class=RedirectResponse)
async def edit_account(
    account_id: int,
    request: Request,
    new_account_id: str = Form(...),
    new_account_pw: str = Form(...),
    new_ip_address: str = Form(None),
    new_category: str = Form('최적화'),
    db: Session = Depends(get_db)
):
    account = db.query(MarketingAccount).filter(MarketingAccount.id == account_id).first()
    if account:
        account.account_id = new_account_id
        account.account_pw = new_account_pw
        account.ip_address = new_ip_address
        account.category = new_category
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

@router.post("/account/update/{account_id}", response_class=RedirectResponse)
async def update_account(
    account_id: int,
    request: Request,
    edit_account_id: str = Form(None),
    edit_account_pw: str = Form(None),
    edit_ip_address: str = Form(None),
    edit_category: str = Form(None),
    # 기존 파라미터 이름도 지원 (하위 호환성)
    new_account_id: str = Form(None),
    new_account_pw: str = Form(None),
    new_ip_address: str = Form(None),
    new_category: str = Form(None),
    db: Session = Depends(get_db)
):
    """계정 업데이트 (별칭 라우트)"""
    # edit_ 파라미터가 있으면 우선 사용, 없으면 new_ 파라미터 사용
    final_account_id = edit_account_id or new_account_id
    final_account_pw = edit_account_pw or new_account_pw
    final_ip_address = edit_ip_address or new_ip_address
    final_category = edit_category or new_category or '최적화'
    
    if not final_account_id or not final_account_pw:
        return RedirectResponse(url="/marketing/cafe?tab=accounts&error=missing_fields", status_code=303)
    
    return await edit_account(account_id, request, final_account_id, final_account_pw, final_ip_address, final_category, db)

@router.post("/accounts/delete/{account_id}", response_class=RedirectResponse)
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(MarketingAccount).filter(MarketingAccount.id == account_id).first()
    if account:
        db.delete(account)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

@router.post("/account/delete/{account_id}", response_class=RedirectResponse)
async def delete_account_alias(account_id: int, db: Session = Depends(get_db)):
    """계정 삭제 (별칭 라우트)"""
    return await delete_account(account_id, db)

# --- Cafe CRUD ---
@router.get("/cafes/add", response_class=HTMLResponse)
async def add_cafe_page(request: Request):
    """카페 추가 페이지"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    return templates.TemplateResponse("marketing_cafe_add.html", {
        "request": request
    })

@router.post("/cafes/add", response_class=RedirectResponse)
async def add_cafe(
    request: Request,
    cafe_name: str = Form(...),
    cafe_url: str = Form(...),
    db: Session = Depends(get_db)
):
    new_cafe = TargetCafe(name=cafe_name, url=cafe_url)
    db.add(new_cafe)
    db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

@router.post("/cafe/add", response_class=RedirectResponse)
async def add_cafe_alias(
    request: Request,
    db: Session = Depends(get_db)
):
    """카페 추가 (별칭 라우트)"""
    form_data = await request.form()
    cafe_name = form_data.get("cafe_name")
    cafe_url = form_data.get("cafe_url")
    
    # 필드 검증
    if not cafe_name or not cafe_url:
        return RedirectResponse(url="/marketing/cafe?tab=cafes&error=missing_fields", status_code=303)
    
    return await add_cafe(request, cafe_name, cafe_url, db)

@router.post("/cafes/edit/{cafe_id}", response_class=RedirectResponse)
async def edit_cafe(
    cafe_id: int,
    new_cafe_name: str = Form(...),
    new_cafe_url: str = Form(...),
    db: Session = Depends(get_db)
):
    cafe = db.query(TargetCafe).filter(TargetCafe.id == cafe_id).first()
    if cafe:
        cafe.name = new_cafe_name
        cafe.url = new_cafe_url
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

@router.post("/cafes/delete/{cafe_id}", response_class=RedirectResponse)
async def delete_cafe(cafe_id: int, db: Session = Depends(get_db)):
    cafe = db.query(TargetCafe).filter(TargetCafe.id == cafe_id).first()
    if cafe:
        db.delete(cafe)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

@router.post("/cafe/delete/{cafe_id}", response_class=RedirectResponse)
async def delete_cafe_alias(cafe_id: int, db: Session = Depends(get_db)):
    """카페 삭제 (별칭 라우트)"""
    return await delete_cafe(cafe_id, db)

# --- Membership CRUD ---
@router.post("/memberships/add", response_class=RedirectResponse)
async def add_membership(
    request: Request,
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    status: str = Form("active"),
    db: Session = Depends(get_db)
):
    # 중복 연동 체크
    existing = db.query(CafeMembership).filter(
        CafeMembership.account_id == account_id,
        CafeMembership.cafe_id == cafe_id
    ).first()
    
    if existing:
        # 이미 연동된 경우 에러 메시지와 함께 리다이렉트
        return RedirectResponse(url=f"/marketing/cafe?tab=memberships&cafe_id={cafe_id}&error=duplicate_membership", status_code=303)
    
    new_membership = CafeMembership(account_id=account_id, cafe_id=cafe_id, status=status)
    db.add(new_membership)
    db.commit()
    return RedirectResponse(url=f"/marketing/cafe?tab=memberships&cafe_id={cafe_id}", status_code=303)

@router.post("/membership/add", response_class=RedirectResponse)
async def add_membership_alias(
    request: Request,
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    status: str = Form("active"),
    db: Session = Depends(get_db)
):
    """멤버십 추가 (별칭 라우트)"""
    return await add_membership(request, account_id, cafe_id, status, db)

@router.post("/memberships/delete/{membership_id}", response_class=RedirectResponse)
async def delete_membership(membership_id: int, db: Session = Depends(get_db)):
    membership = db.query(CafeMembership).filter(CafeMembership.id == membership_id).first()
    if membership:
        db.delete(membership)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=memberships", status_code=303)

# --- Reference CRUD ---
@router.post("/references/add", response_class=RedirectResponse)
async def add_reference(
    request: Request,
    ref_title: str = Form(None),
    title: str = Form(None),  # 별칭 지원
    ref_content: str = Form(""),
    ref_type: str = Form("기타"),
    comments: str = Form(""),
    db: Session = Depends(get_db)
):
    # ref_title 또는 title 중 하나 사용
    final_title = ref_title or title
    if not final_title:
        return RedirectResponse(url="/marketing/cafe?tab=references&error=missing_title", status_code=303)
    
    try:
        username = request.session.get("user")
        user = db.query(User).filter(User.username == username).first()
        user_id = user.id if user else None
        
        new_ref = Reference(
            title=final_title, 
            content=ref_content, 
            ref_type=ref_type,
            last_modified_by_id=user_id
        )
        db.add(new_ref)
        db.flush()
        
        if comments:
            try:
                comments_data = json.loads(comments)
                for comment_data in comments_data:
                    if comment_data.get('text') and comment_data['text'].strip():
                        new_comment = Comment(
                            reference_id=new_ref.id,
                            text=comment_data['text'],
                            account_sequence=comment_data.get('account_sequence', 0)
                        )
                        db.add(new_comment)
            except (json.JSONDecodeError, KeyError):
                pass
        
        db.commit()
        return RedirectResponse(url=f"/marketing/reference/{new_ref.id}", status_code=303)
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url="/marketing/cafe?tab=references&error=duplicate_reference", status_code=303)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url="/marketing/cafe?tab=references&error=db_error", status_code=303)

@router.post("/references/edit/{ref_id}", response_class=RedirectResponse)
async def edit_reference(
    request: Request,
    ref_id: int,
    new_ref_title: str = Form(...),
    new_ref_content: str = Form(""),
    new_ref_type: str = Form("기타"),
    comments: str = Form(""),
    db: Session = Depends(get_db)
):
    username = request.session.get("user")
    user = db.query(User).filter(User.username == username).first()
    user_id = user.id if user else None
    
    reference = db.query(Reference).filter(Reference.id == ref_id).first()
    if reference:
        reference.title = new_ref_title
        reference.content = new_ref_content
        reference.ref_type = new_ref_type
        reference.last_modified_by_id = user_id
        
        db.query(Comment).filter(Comment.reference_id == ref_id).delete()
        
        if comments:
            try:
                comments_data = json.loads(comments)
                for comment_data in comments_data:
                    if comment_data.get('text') and comment_data['text'].strip():
                        new_comment = Comment(
                            reference_id=ref_id,
                            text=comment_data['text'],
                            account_sequence=comment_data.get('account_sequence', 0)
                        )
                        db.add(new_comment)
            except (json.JSONDecodeError, KeyError):
                pass
        
        db.commit()
        # 생성된 레퍼런스의 상세 페이지로 이동
        return RedirectResponse(url=f"/marketing/reference/{new_ref.id}", status_code=303)
    return RedirectResponse(url="/marketing/cafe?tab=references", status_code=303)

@router.post("/reference/add", response_class=RedirectResponse)
async def add_reference_alias(
    request: Request,
    ref_title: str = Form(None),
    title: str = Form(None),  # 별칭 지원
    ref_content: str = Form(""),
    ref_type: str = Form("기타"),
    comments: str = Form(""),
    db: Session = Depends(get_db)
):
    """레퍼런스 추가 (별칭 라우트)"""
    return await add_reference(request, ref_title, title, ref_content, ref_type, comments, db)

@router.post("/references/delete/{ref_id}", response_class=RedirectResponse)
async def delete_reference(ref_id: int, db: Session = Depends(get_db)):
    reference = db.query(Reference).filter(Reference.id == ref_id).first()
    if reference:
        db.delete(reference)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=references", status_code=303)

@router.post("/reference/update/{ref_id}", response_class=RedirectResponse)
async def update_reference(
    ref_id: int,
    request: Request,
    ref_title: str = Form(None),
    ref_content: str = Form(""),
    ref_type: str = Form("기타"),
    db: Session = Depends(get_db)
):
    """레퍼런스 업데이트"""
    reference = db.query(Reference).filter(Reference.id == ref_id).first()
    if reference:
        if ref_title:
            reference.title = ref_title
        reference.content = ref_content
        reference.ref_type = ref_type
        db.commit()
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

@router.get("/reference/{ref_id}", response_class=HTMLResponse)
async def reference_detail(request: Request, ref_id: int, db: Session = Depends(get_db)):
    """레퍼런스 상세 보기"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not (current_user.can_manage_marketing or current_user.is_admin):
        return RedirectResponse("/", status_code=302)
    
    reference = db.query(Reference).options(
        joinedload(Reference.comments)
    ).filter(Reference.id == ref_id).first()
    
    if not reference:
        return RedirectResponse("/marketing/cafe?tab=references", status_code=302)
    
    # 댓글을 계층 구조로 정렬
    def organize_comments(comments):
        comment_dict = {comment.id: comment for comment in comments}
        root_comments = []
        
        for comment in comments:
            if comment.parent_id is None:
                root_comments.append(comment)
            else:
                parent = comment_dict.get(comment.parent_id)
                if parent:
                    if not hasattr(parent, 'replies'):
                        parent.replies = []
                    parent.replies.append(comment)
        
        return root_comments
    
    organized_comments = organize_comments(reference.comments)
    
    return templates.TemplateResponse("reference_detail.html", {
        "request": request,
        "reference": reference,
        "organized_comments": organized_comments
    })

@router.post("/comment/add/{ref_id}", response_class=RedirectResponse)
async def add_comment(
    ref_id: int,
    request: Request,
    text: str = Form(...),
    account_sequence: int = Form(0),
    parent_id: int = Form(None),
    db: Session = Depends(get_db)
):
    """레퍼런스에 댓글 추가"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not (current_user.can_manage_marketing or current_user.is_admin):
        return RedirectResponse("/", status_code=302)
    
    new_comment = Comment(
        reference_id=ref_id,
        text=text,
        account_sequence=account_sequence,
        parent_id=parent_id if parent_id and parent_id > 0 else None
    )
    
    db.add(new_comment)
    db.commit()
    
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

@router.post("/comment/delete/{ref_id}/{comment_id}", response_class=RedirectResponse)
async def delete_comment(
    ref_id: int,
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """댓글 삭제"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not (current_user.can_manage_marketing or current_user.is_admin):
        return RedirectResponse("/", status_code=302)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment:
        db.delete(comment)
        db.commit()
    
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

@router.post("/comment/edit/{ref_id}/{comment_id}", response_class=RedirectResponse)
async def edit_comment(
    ref_id: int,
    comment_id: int,
    request: Request,
    text: str = Form(...),
    account_sequence: int = Form(0),
    db: Session = Depends(get_db)
):
    """댓글 수정"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not (current_user.can_manage_marketing or current_user.is_admin):
        return RedirectResponse("/", status_code=302)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment:
        comment.text = text
        comment.account_sequence = account_sequence
        db.commit()
    return RedirectResponse(url=f"/marketing/reference/{ref_id}", status_code=303)

# --- 전체 현황 탭 처리 ---
@router.post("/tasks/complete/{task_id}", response_class=RedirectResponse)
async def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(WorkTask).filter(WorkTask.id == task_id).first()
    if task:
        task.status = 'done'
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=status", status_code=303)

@router.post("/tasks/uncomplete/{task_id}", response_class=RedirectResponse)
async def uncomplete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(WorkTask).filter(WorkTask.id == task_id).first()
    if task:
        task.status = 'todo'
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=status", status_code=303)

# --- Product Selection Page ---
@router.get("/product-selection", response_class=HTMLResponse)
async def product_selection(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("user")
    
    # 이미 마케팅 상품으로 등록된 상품 ID들 조회
    existing_marketing_product_ids = db.query(MarketingProduct.product_id).all()
    existing_ids = [row[0] for row in existing_marketing_product_ids]
    
    # 등록되지 않은 상품들만 조회
    all_products = db.query(Product).filter(
        Product.id.notin_(existing_ids)
    ).all()
    
    # ⭐ 템플릿 이름 수정: product_selection.html → marketing_product_selection.html
    return templates.TemplateResponse("marketing_product_selection.html", {
        "request": request,
        "username": username,
        "products": all_products
    })

@router.post("/product/add/{product_id}", response_class=RedirectResponse)
async def add_marketing_product_single(
    product_id: int,
    db: Session = Depends(get_db)
):
    """단일 상품을 마케팅 상품으로 추가"""
    existing = db.query(MarketingProduct).filter(
        MarketingProduct.product_id == product_id
    ).first()
    
    if not existing:
        new_marketing_product = MarketingProduct(product_id=product_id, keywords=None)
        db.add(new_marketing_product)
        db.commit()
    
    return RedirectResponse(url="/marketing/cafe?tab=products", status_code=303)

# --- 마케팅 상품 API 라우트들 ---
@router.post("/product/keywords/{product_id}", response_class=JSONResponse)
async def add_marketing_product(
    product_id: int,
    keywords: List[str] = Form(...),
    db: Session = Depends(get_db)
):
    """상품에 키워드를 추가하여 마케팅 상품으로 등록"""
    existing = db.query(MarketingProduct).filter(
        MarketingProduct.product_id == product_id
    ).first()
    
    if existing:
        return JSONResponse({"success": False, "message": "이미 마케팅 상품으로 등록되었습니다."})
    
    keyword_data = [{"keyword": kw, "active": True} for kw in keywords if kw.strip()]
    
    new_marketing_product = MarketingProduct(
        product_id=product_id,
        keywords=json.dumps(keyword_data, ensure_ascii=False) if keyword_data else None
    )
    
    db.add(new_marketing_product)
    db.commit()
    
    return JSONResponse({"success": True, "marketing_product_id": new_marketing_product.id})

# --- 마케팅 상품 표시를 위한 API ---
@router.get("/product/keywords/{product_id}", response_class=JSONResponse)
async def get_product_keywords(product_id: int, db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(
        MarketingProduct.product_id == product_id
    ).first()
    
    if marketing_product and marketing_product.keywords:
        try:
            keywords_data = json.loads(marketing_product.keywords)
            keywords = [item['keyword'] for item in keywords_data if item.get('active', True)]
            return JSONResponse({"keywords": keywords})
        except json.JSONDecodeError:
            return JSONResponse({"keywords": []})
    
    return JSONResponse({"keywords": []})

@router.get("/product/keywords/manage/{mp_id}", response_class=HTMLResponse)
async def manage_keywords_page(mp_id: int, request: Request, db: Session = Depends(get_db)):
    """키워드 관리 페이지"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not (current_user.can_manage_marketing or current_user.is_admin):
        return RedirectResponse("/", status_code=302)
    
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if not marketing_product:
        return RedirectResponse("/marketing/cafe?tab=products", status_code=302)
    
    # 키워드 데이터 파싱
    keywords_data = []
    keywords_text = ""
    keywords_list = []
    total_keywords_count = 0
    
    if marketing_product.keywords:
        try:
            keywords_data = json.loads(marketing_product.keywords)
            # 텍스트 형태로 변환
            keywords_text = "\n".join([item.get("keyword", "") for item in keywords_data if item.get("keyword")])
            # 리스트 형태로 변환
            keywords_list = keywords_data
            total_keywords_count = len(keywords_data)
        except json.JSONDecodeError:
            keywords_data = []
    
    return templates.TemplateResponse("marketing_product_keywords.html", {
        "request": request,
        "marketing_product": marketing_product,
        "keywords_data": keywords_data,
        "keywords_text": keywords_text,
        "keywords_list": keywords_list,
        "total_keywords_count": total_keywords_count
    })

# --- 키워드 관리 라우트 ---
@router.post("/product/keywords/update/{mp_id}", response_class=RedirectResponse)
async def update_keywords(
    mp_id: int,
    keywords: str = Form(""),
    db: Session = Depends(get_db)
):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if marketing_product:
        existing_data = []
        if marketing_product.keywords:
            try:
                existing_data = json.loads(marketing_product.keywords)
            except json.JSONDecodeError:
                pass
        
        existing_dict = {item['keyword']: item for item in existing_data}
        
        new_keywords = [kw.strip() for kw in keywords.split('\n') if kw.strip()]
        
        updated_data = []
        for kw in new_keywords:
            if kw in existing_dict:
                updated_data.append(existing_dict[kw])
            else:
                updated_data.append({"keyword": kw, "active": True})
        
        marketing_product.keywords = json.dumps(updated_data, ensure_ascii=False) if updated_data else None
        db.commit()
    
    return RedirectResponse(url="/marketing/cafe?tab=products", status_code=303)

# --- 키워드 토글 라우트 ---
@router.post("/product/keyword/toggle/{mp_id}", response_class=JSONResponse)
async def toggle_keyword_status(
    mp_id: int,
    keyword: str = Form(...),
    db: Session = Depends(get_db)
):
    """특정 키워드의 활성/비활성 상태를 토글"""
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    
    if marketing_product and marketing_product.keywords:
        try:
            keywords_data = json.loads(marketing_product.keywords)
            
            for item in keywords_data:
                if item['keyword'] == keyword:
                    item['active'] = not item.get('active', True)
                    break
            
            marketing_product.keywords = json.dumps(keywords_data, ensure_ascii=False)
            db.commit()
            
            return JSONResponse({"success": True})
        except json.JSONDecodeError:
            pass
    
    return JSONResponse({"success": False})

@router.post("/product/delete/{mp_id}", response_class=RedirectResponse)
async def delete_marketing_product(mp_id: int, db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if marketing_product:
        db.delete(marketing_product)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=products", status_code=303)

# --- '마케팅 상품 추가' 폼 처리 ---
@router.post("/product/add-from-selection", response_class=RedirectResponse)
async def add_marketing_product_from_selection(
    product_ids: List[int] = Form(...),
    db: Session = Depends(get_db)
):
    for product_id in product_ids:
        existing = db.query(MarketingProduct).filter(
            MarketingProduct.product_id == product_id
        ).first()
        if not existing:
            new_marketing_product = MarketingProduct(product_id=product_id, keywords=None)
            db.add(new_marketing_product)
    db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=products", status_code=303)

@router.post("/marketing/products/add-simple", response_class=RedirectResponse)
async def add_marketing_product_simple(
    product_id: int = Form(...),
    db: Session = Depends(get_db)
):
    existing = db.query(MarketingProduct).filter(
        MarketingProduct.product_id == product_id
    ).first()
    if not existing:
        new_marketing_product = MarketingProduct(product_id=product_id, keywords=None)
        db.add(new_marketing_product)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=products", status_code=303)

# --- '글 관리' 라우트 ---
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
    for ref in all_references:
        ref_type_str = ref.ref_type or "기타"
        if ref_type_str in references_by_type:
            references_by_type[ref_type_str].append(ref)
        else:
            references_by_type["기타"].append(ref)
    
    all_memberships = db.query(CafeMembership).options(joinedload(CafeMembership.cafe)).all()
    
    # 계정-카페 연동 맵 생성
    membership_map = {}
    for membership in all_memberships:
        if membership.account_id not in membership_map:
            membership_map[membership.account_id] = []
        membership_map[membership.account_id].append({
            "id": membership.cafe.id,
            "name": membership.cafe.name
        })
    
    # 키워드 리스트 생성
    keywords_list = []
    if marketing_product.keywords:
        try:
            keywords_data = json.loads(marketing_product.keywords)
            keywords_list = [kw.get('keyword', '') for kw in keywords_data if kw.get('keyword', '').strip()]
        except:
            keywords_list = []

    # ⭐ 템플릿 이름 수정: marketing_posts.html → marketing_product_posts.html
    return templates.TemplateResponse("marketing_product_posts.html", {
        "request": request,
        "marketing_product": marketing_product,
        "posts_by_keyword": posts_by_keyword,
        "all_accounts": all_accounts,
        "all_cafes": all_cafes,
        "all_workers": all_workers,
        "all_references": all_references,
        "references_by_type": references_by_type,
        "all_memberships": all_memberships,
        "membership_map": membership_map,  # 추가
        "keywords_list": keywords_list,  # 추가
        "page": page,
        "current_page": page,  # 추가
        "total_pages": total_pages,
        "keyword_search": keyword_search,
        "post_stats": post_stats,
        "error_message": error_message
    })

@router.post("/post/add", response_class=RedirectResponse)
async def add_marketing_post_form(
    request: Request,
    mp_id: int = Form(...),
    keyword_text: str = Form(...),
    worker_id: int = Form(...),
    account_id: int = Form(...),
    cafe_id: int = Form(...),
    post_title: str = Form(""),
    post_body: str = Form(""),
    post_comments: str = Form(""),
    is_registration_complete: bool = Form(False),
    post_url: str = Form(""),
    is_live: bool = Form(True),
    reference_id: int = Form(None),
    db: Session = Depends(get_db)
):
    """마케팅 포스트 추가 (폼에서)"""
    new_post = MarketingPost(
        marketing_product_id=mp_id,
        keyword_text=keyword_text,
        worker_id=worker_id,
        account_id=account_id,
        cafe_id=cafe_id,
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

@router.post("/post/add/{mp_id}/{keyword}", response_class=RedirectResponse)
async def add_marketing_post(
    mp_id: int, 
    keyword: str, 
    count: int = Form(1),
    db: Session = Depends(get_db)
):
    for i in range(count):
        new_post = MarketingPost(
            marketing_product_id=mp_id,
            keyword_text=keyword,
            post_title="",
            post_body="",
            post_comments=""
        )
        db.add(new_post)
    db.commit()
    return RedirectResponse(url=f"/marketing/product/posts/{mp_id}", status_code=303)

@router.post("/post/update/{post_id}", response_class=RedirectResponse)
async def update_marketing_post(
    post_id: int,
    account_id: int = Form(None),
    cafe_id: int = Form(None),
    worker_id: int = Form(None),
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
        post.is_live = is_live if is_registration_complete else False
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

# --- Other Marketing Pages ---
@router.get("/blog", response_class=HTMLResponse)
async def marketing_blog(request: Request):
    return templates.TemplateResponse("marketing_blog.html", {"request": request})

@router.get("/homepage", response_class=HTMLResponse)
async def marketing_homepage(request: Request):
    return templates.TemplateResponse("marketing_homepage.html", {"request": request})

@router.get("/kin", response_class=HTMLResponse)
async def marketing_kin(request: Request):
    return templates.TemplateResponse("marketing_kin.html", {"request": request})

# ========== 스케줄 관리 ==========

# 스케줄 페이지
@router.get("/schedules", response_class=HTMLResponse)
async def view_schedules(
    request: Request,
    selected_date: str = Query(None),
    worker_filter: int = Query(None),
    status_filter: str = Query(None),
    db: Session = Depends(get_db)
):
    """전체 스케줄 관리 페이지"""
    
    # 날짜 처리
    if selected_date:
        target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        target_date = date.today()
    
    # 쿼리 빌드
    query = db.query(PostSchedule).filter(
        PostSchedule.scheduled_date == target_date
    ).options(
        joinedload(PostSchedule.worker),
        joinedload(PostSchedule.account),
        joinedload(PostSchedule.cafe),
        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product),
        joinedload(PostSchedule.marketing_post)
    )
    
    # 필터 적용
    if worker_filter:
        query = query.filter(PostSchedule.worker_id == worker_filter)
    if status_filter:
        query = query.filter(PostSchedule.status == status_filter)
    
    schedules = query.order_by(PostSchedule.id).all()
    
    # 작업자 목록
    workers = db.query(User).filter(
        or_(User.can_manage_marketing == True, User.is_admin == True)
    ).all()
    
    # 마케팅 상품 목록
    marketing_products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    
    # 계정 목록
    accounts = db.query(MarketingAccount).all()
    
    # 카페 목록
    cafes = db.query(TargetCafe).all()
    
    # 멤버십 조회
    memberships = db.query(CafeMembership).options(
        joinedload(CafeMembership.account),
        joinedload(CafeMembership.cafe)
    ).all()
    
    # membership_map 생성
    membership_map = {}
    for membership in memberships:
        if membership.account_id not in membership_map:
            membership_map[membership.account_id] = []
        membership_map[membership.account_id].append({
            'cafe_id': membership.cafe_id,
            'cafe_name': membership.cafe.name if membership.cafe else ''
        })
    
    # product_keywords_map 생성
    product_keywords_map = {}
    for mp in marketing_products:
        keywords = []
        if mp.keywords:
            try:
                keywords_data = json.loads(mp.keywords)
                keywords = [item['keyword'] for item in keywords_data if item.get('active', True)]
            except:
                keywords = []
        product_keywords_map[mp.id] = keywords
    
    # 통계 계산
    total_schedules = len(schedules)
    completed_schedules = sum(1 for s in schedules if s.status == "completed")
    in_progress_schedules = sum(1 for s in schedules if s.status == "in_progress")
    pending_schedules = sum(1 for s in schedules if s.status == "pending")
    skipped_schedules = sum(1 for s in schedules if s.status == "skipped")
    
    # today_stats 생성
    today_stats = {
        'total': total_schedules,
        'completed': completed_schedules,
        'in_progress': in_progress_schedules,
        'pending': pending_schedules,
        'skipped': skipped_schedules
    }
    
    # 작성되지 않은 글 목록
    unlinked_posts = db.query(MarketingPost).filter(
        MarketingPost.id.notin_(
            db.query(PostSchedule.marketing_post_id).filter(
                PostSchedule.marketing_post_id.isnot(None)
            ).scalar_subquery()
        )
    ).options(
        joinedload(MarketingPost.marketing_product).joinedload(MarketingProduct.product)
    ).all()
    
    return templates.TemplateResponse("marketing_schedules.html", {
        "request": request,
        "schedules": schedules,
        "workers": workers,
        "marketing_products": marketing_products,
        "product_keywords_map": product_keywords_map,
        "accounts": accounts,
        "cafes": cafes,
        "memberships": memberships,
        "membership_map": membership_map,
        "unlinked_posts": unlinked_posts,
        "selected_date": target_date,
        "today": date.today(),
        "today_stats": today_stats,
        "worker_filter": worker_filter,
        "status_filter": status_filter,
        "total_schedules": total_schedules,
        "completed_schedules": completed_schedules,
        "in_progress_schedules": in_progress_schedules,
        "pending_schedules": pending_schedules,
        "skipped_schedules": skipped_schedules
    })

@router.get("/schedules/create", response_class=HTMLResponse)
async def create_schedule_page(request: Request, db: Session = Depends(get_db)):
    """스케줄 생성 페이지"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not (current_user.can_manage_marketing or current_user.is_admin):
        return RedirectResponse("/", status_code=302)
    
    # 필요한 데이터 조회
    marketing_products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    
    workers = db.query(User).filter(
        or_(User.can_manage_marketing == True, User.is_admin == True)
    ).all()
    
    accounts = db.query(MarketingAccount).all()
    cafes = db.query(TargetCafe).all()
    
    return templates.TemplateResponse("marketing_schedule_create.html", {
        "request": request,
        "marketing_products": marketing_products,
        "workers": workers,
        "accounts": accounts,
        "cafes": cafes,
        "today": date.today()
    })

# ========== 새로운 자동 생성 로직 ==========

@router.post("/api/generate-schedule")
async def generate_schedule(
    request: Request,
    product_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db)
):
    """자동 스케줄 생성 - 중복 체크 및 할당량 적용"""
    try:
        # 날짜 변환
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        # 마케팅 상품 정보
        marketing_product = db.query(MarketingProduct).filter(
            MarketingProduct.id == product_id
        ).first()
        
        if not marketing_product:
            return {"success": False, "message": "마케팅 상품을 찾을 수 없습니다"}
        
        # 키워드 파싱
        keywords = []
        if marketing_product.keywords:
            try:
                keywords_data = json.loads(marketing_product.keywords)
                keywords = [item['keyword'] for item in keywords_data if item.get('active', True)]
            except:
                keywords = []
        
        if not keywords:
            return {"success": False, "message": "활성화된 키워드가 없습니다"}
        
        # 각 키워드별 이미 작성된 글 수 계산
        keyword_post_counts = {}
        for keyword in keywords:
            # 완료된 글 수
            completed_posts = db.query(MarketingPost).filter(
                MarketingPost.marketing_product_id == product_id,
                MarketingPost.keyword_text == keyword,
                MarketingPost.is_registration_complete == True
            ).count()
            
            # 예약된 스케줄 수 (완료되지 않은 것)
            scheduled_posts = db.query(PostSchedule).filter(
                PostSchedule.marketing_product_id == product_id,
                PostSchedule.keyword_text == keyword,
                PostSchedule.status != "completed",
                PostSchedule.scheduled_date >= start
            ).count()
            
            keyword_post_counts[keyword] = {
                'completed': completed_posts,
                'scheduled': scheduled_posts,
                'total': completed_posts + scheduled_posts
            }
        
        # 작성 가능한 키워드만 필터링 (3개 미만)
        available_keywords = [k for k in keywords if keyword_post_counts[k]['total'] < 3]
        
        if not available_keywords:
            return {"success": False, "message": "모든 키워드가 이미 3회 작성 완료/예약되었습니다"}
        
        # 할당 가능한 사용자 조회
        users = db.query(User).filter(
            User.can_manage_marketing == True,
            User.daily_quota > 0
        ).all()
        
        if not users:
            return {"success": False, "message": "할당 가능한 사용자가 없습니다 (할당량 설정 필요)"}
        
        created_count = 0
        current_date = start
        keyword_index = 0
        
        while current_date <= end:
            # 해당 날짜의 기존 스케줄 확인
            existing_schedules = db.query(PostSchedule).filter(
                PostSchedule.scheduled_date == current_date
            ).all()
            
            # 각 사용자별 현재 할당된 작업 수 계산
            user_daily_assignments = {}
            for schedule in existing_schedules:
                if schedule.worker_id:
                    user_daily_assignments[schedule.worker_id] = \
                        user_daily_assignments.get(schedule.worker_id, 0) + 1
            
            # 각 사용자별로 할당
            for user in users:
                current_count = user_daily_assignments.get(user.id, 0)
                remaining_quota = user.daily_quota - current_count
                
                # 남은 할당량만큼만 스케줄 생성
                for _ in range(remaining_quota):
                    # 작성 가능한 키워드 찾기
                    selected_keyword = None
                    attempts = 0
                    
                    # 모든 키워드를 순회하며 작성 가능한 것 찾기
                    while attempts < len(keywords):
                        test_keyword = available_keywords[keyword_index % len(available_keywords)] if available_keywords else None
                        if test_keyword and keyword_post_counts[test_keyword]['total'] < 3:
                            selected_keyword = test_keyword
                            keyword_index += 1
                            break
                        keyword_index += 1
                        attempts += 1
                    
                    if not selected_keyword:
                        continue  # 더 이상 할당할 키워드 없음
                    
                    # 중복 체크
                    exists = db.query(PostSchedule).filter(
                        PostSchedule.scheduled_date == current_date,
                        PostSchedule.worker_id == user.id,
                        PostSchedule.keyword_text == selected_keyword,
                        PostSchedule.marketing_product_id == product_id
                    ).first()
                    
                    if exists:
                        continue
                    
                    # 계정과 카페 자동 할당
                    account = None
                    cafe = None
                    
                    # 사용 가능한 계정 찾기
                    accounts = db.query(MarketingAccount).all()
                    cafes = db.query(TargetCafe).all()
                    
                    if accounts and cafes:
                        # 가장 적게 사용된 조합 찾기
                        for acc in accounts:
                            for cf in cafes:
                                # 해당 계정-카페-키워드 사용 횟수 확인
                                usage = db.query(AccountCafeUsage).filter(
                                    AccountCafeUsage.account_id == acc.id,
                                    AccountCafeUsage.cafe_id == cf.id,
                                    AccountCafeUsage.keyword_text == selected_keyword,
                                    AccountCafeUsage.marketing_product_id == product_id
                                ).first()
                                
                                if not usage or usage.usage_count < 2:
                                    account = acc
                                    cafe = cf
                                    break
                            if account and cafe:
                                break
                    
                    if account and cafe:
                        # 새 스케줄 생성
                        new_schedule = PostSchedule(
                            scheduled_date=current_date,
                            worker_id=user.id,
                            account_id=account.id,
                            cafe_id=cafe.id,
                            marketing_product_id=product_id,
                            keyword_text=selected_keyword,
                            status="pending"
                        )
                        db.add(new_schedule)
                        created_count += 1
                        
                        # 카운트 업데이트
                        keyword_post_counts[selected_keyword]['scheduled'] += 1
                        keyword_post_counts[selected_keyword]['total'] += 1
                        
                        # 사용 횟수 업데이트
                        usage = db.query(AccountCafeUsage).filter(
                            AccountCafeUsage.account_id == account.id,
                            AccountCafeUsage.cafe_id == cafe.id,
                            AccountCafeUsage.keyword_text == selected_keyword,
                            AccountCafeUsage.marketing_product_id == product_id
                        ).first()
                        
                        if usage:
                            usage.usage_count += 1
                            usage.last_used_date = current_date
                        else:
                            new_usage = AccountCafeUsage(
                                account_id=account.id,
                                cafe_id=cafe.id,
                                keyword_text=selected_keyword,
                                marketing_product_id=product_id,
                                usage_count=1,
                                last_used_date=current_date
                            )
                            db.add(new_usage)
            
            current_date += timedelta(days=1)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{created_count}개의 스케줄이 생성되었습니다"
        }
        
    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"오류 발생: {str(e)}"}

# ========== 스케줄 관리 API 엔드포인트들 ==========

@router.post("/api/schedule/complete/{schedule_id}")
async def complete_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """스케줄 완료 처리"""
    try:
        schedule = db.query(PostSchedule).filter(PostSchedule.id == schedule_id).first()
        if schedule:
            schedule.status = "completed"
            schedule.is_completed = True
            schedule.completed_at = datetime.utcnow()
            db.commit()
            return {"success": True, "message": "완료 처리되었습니다"}
        return {"success": False, "message": "스케줄을 찾을 수 없습니다"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}

@router.post("/api/schedule/status/{schedule_id}")
async def update_schedule_status(
    schedule_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    """스케줄 상태 변경 (진행중/건너뛰기)"""
    try:
        schedule = db.query(PostSchedule).filter(PostSchedule.id == schedule_id).first()
        if schedule:
            schedule.status = status  # "in_progress" or "skipped"
            if status == "skipped":
                schedule.is_completed = True
                schedule.completed_at = datetime.utcnow()
            db.commit()
            
            status_text = "진행 중" if status == "in_progress" else "건너뛰기"
            return {"success": True, "message": f"{status_text}으로 변경되었습니다"}
        return {"success": False, "message": "스케줄을 찾을 수 없습니다"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}

@router.delete("/api/schedule/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    """스케줄 삭제"""
    try:
        schedule = db.query(PostSchedule).filter(PostSchedule.id == schedule_id).first()
        if schedule:
            db.delete(schedule)
            db.commit()
            return {"success": True, "message": "삭제되었습니다"}
        return {"success": False, "message": "스케줄을 찾을 수 없습니다"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}

@router.get("/api/schedule/edit/{schedule_id}")
async def get_schedule_edit(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    """스케줄 수정 정보 조회"""
    try:
        schedule = db.query(PostSchedule).filter(PostSchedule.id == schedule_id).first()
        if schedule:
            # 작업자 목록
            workers = db.query(User).filter(
                or_(User.can_manage_marketing == True, User.is_admin == True)
            ).all()
            
            # 계정 목록
            accounts = db.query(MarketingAccount).all()
            
            # 카페 목록
            cafes = db.query(TargetCafe).all()
            
            return {
                "success": True,
                "data": {
                    "id": schedule.id,
                    "worker_id": schedule.worker_id,
                    "account_id": schedule.account_id,
                    "cafe_id": schedule.cafe_id,
                    "keyword_text": schedule.keyword_text,
                    "notes": schedule.notes
                },
                "workers": [{"id": w.id, "name": w.username} for w in workers],
                "accounts": [{"id": a.id, "name": a.account_id} for a in accounts],
                "cafes": [{"id": c.id, "name": c.name} for c in cafes]
            }
        return {"success": False, "message": "스케줄을 찾을 수 없습니다"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.post("/api/schedule/edit/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    worker_id: int = Form(None),
    account_id: int = Form(None),
    cafe_id: int = Form(None),
    keyword_text: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """스케줄 수정"""
    try:
        schedule = db.query(PostSchedule).filter(PostSchedule.id == schedule_id).first()
        if schedule:
            if worker_id is not None:
                schedule.worker_id = worker_id
            if account_id is not None:
                schedule.account_id = account_id
            if cafe_id is not None:
                schedule.cafe_id = cafe_id
            if keyword_text:
                schedule.keyword_text = keyword_text
            if notes is not None:
                schedule.notes = notes
            
            schedule.updated_at = datetime.utcnow()
            db.commit()
            return {"success": True, "message": "수정되었습니다"}
        return {"success": False, "message": "스케줄을 찾을 수 없습니다"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}

@router.post("/api/schedule/link-post/{schedule_id}")
async def link_post_to_schedule(
    schedule_id: int,
    post_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """작성된 글 연결"""
    try:
        schedule = db.query(PostSchedule).filter(PostSchedule.id == schedule_id).first()
        post = db.query(MarketingPost).filter(MarketingPost.id == post_id).first()
        
        if schedule and post:
            schedule.marketing_post_id = post_id
            schedule.status = "completed"
            schedule.is_completed = True
            schedule.completed_at = datetime.utcnow()
            db.commit()
            return {"success": True, "message": "글이 연결되었습니다"}
        return {"success": False, "message": "스케줄 또는 글을 찾을 수 없습니다"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}