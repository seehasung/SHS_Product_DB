from fastapi import APIRouter, Request, Form, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func # func를 import합니다.
import json
import math
import datetime # datetime을 import합니다.


# Reference, Comment, User 및 신규 MarketingPost 모델을 import
from database import (
    SessionLocal, TargetCafe, MarketingAccount, Product, MarketingProduct,
    CafeMembership, Reference, Comment, User, MarketingPost, WorkTask
)

router = APIRouter(prefix="/marketing")
templates = Jinja2Templates(directory="templates")

# --- Helper Functions ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() # get_db가 모든 요청이 끝난 후 여기서 세션을 닫습니다.

# --- Main Marketing Cafe Page ---
@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get('tab', 'status')
    error = request.query_params.get('error')
    
    username = request.session.get("user")
    current_user = db.query(User).filter(User.username == username).first()
    
    today = datetime.date.today()
    work_tasks = []
    completed_count = 0
    daily_quota = 0
    
    if current_user:
        daily_quota = current_user.daily_quota
        
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

    error_messages = {
        'duplicate_account': "이미 사용 중인 아이디입니다.",
        'duplicate_reference': "이미 사용 중인 레퍼런스 제목입니다."
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

    cafes = db.query(TargetCafe).order_by(TargetCafe.name).all()
    accounts_query = db.query(MarketingAccount)
    if category_filter != 'all':
        accounts_query = accounts_query.filter(MarketingAccount.category == category_filter)
    accounts = accounts_query.order_by(MarketingAccount.id).all()
    marketing_products = db.query(MarketingProduct).options(joinedload(MarketingProduct.product)).order_by(MarketingProduct.id).all()
    references_query = db.query(Reference).options(joinedload(Reference.last_modified_by))
    if reference_filter != 'all':
        references_query = references_query.filter(Reference.ref_type == reference_filter)
    references = references_query.order_by(Reference.id.desc()).all()

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
        "remaining_tasks": remaining_tasks
        
    })
    
@router.post("/task/assign-next", response_class=RedirectResponse)
async def assign_next_task(request: Request, db: Session = Depends(get_db)):
    """현재 사용자에게 '다음 작업'을 할당하는 로직"""
    username = request.session.get("user")
    current_user = db.query(User).filter(User.username == username).first()
    
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    
    today = datetime.date.today()
    
    # 1. 오늘 이미 완료한 작업 수 확인
    completed_count = db.query(WorkTask).filter(
        WorkTask.worker_id == current_user.id,
        func.date(WorkTask.task_date) == today,
        WorkTask.status == 'done'
    ).count()
    
    # 2. 할당량이 남았는지 확인
    if completed_count < current_user.daily_quota:
        # 3. 이미 진행중('todo')인 작업이 있는지 확인
        existing_todo = db.query(WorkTask).filter(
            WorkTask.worker_id == current_user.id,
            WorkTask.status == 'todo'
        ).first()
        
        # 4. 진행중인 작업이 없다면, 새로운 작업 할당 (TODO: 여기에 복잡한 할당 로직 구현)
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
                    status="todo" # '할 일' 상태로 생성
                )
                db.add(new_task)
                db.commit()
            # --- (임시 로직 끝) ---

    return RedirectResponse(url="/marketing/cafe?tab=status", status_code=303)

# --- Reference & Comment Management ---
@router.post("/reference/add", response_class=RedirectResponse)
async def add_reference(request: Request, title: str = Form(...), db: Session = Depends(get_db)):
    username = request.session.get("user")
    user = None
    if username:
        user = db.query(User).filter(User.username == username).first()
    try:
        new_ref = Reference(title=title, ref_type='기타', last_modified_by_id=user.id if user else None)
        db.add(new_ref)
        db.commit()
        db.refresh(new_ref)
        return RedirectResponse(url=f"/marketing/reference/{new_ref.id}", status_code=303)
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url="/marketing/cafe?tab=references&error=duplicate_reference", status_code=303)

@router.post("/reference/delete/{ref_id}", response_class=RedirectResponse)
async def delete_reference(ref_id: int, db: Session = Depends(get_db)):
    ref_to_delete = db.query(Reference).filter(Reference.id == ref_id).first()
    if ref_to_delete:
        db.delete(ref_to_delete)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=references", status_code=303)

@router.get("/reference/{ref_id}", response_class=HTMLResponse)
async def get_reference_detail(request: Request, ref_id: int, db: Session = Depends(get_db)):
    reference = db.query(Reference).options(
        joinedload(Reference.last_modified_by)
    ).filter(Reference.id == ref_id).first()
    
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
        "comments": top_level_comments
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

# --- Keyword Management (원본 JSON 형식 유지) ---
@router.get("/product/keywords/{mp_id}", response_class=HTMLResponse)
async def get_product_keywords(
    request: Request, 
    mp_id: int, 
    db: Session = Depends(get_db),
    total: int = Query(None),
    success: int = Query(None),
    dups: int = Query(None)
):
    """키워드 관리 페이지 (결과 팝업을 위한 파라미터 추가)"""
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    
    keywords_list = []
    if marketing_product and marketing_product.keywords:
        try:
            keywords_list = json.loads(marketing_product.keywords)
        except json.JSONDecodeError:
            keywords_list = [{"keyword": kw.strip(), "active": True} for kw in marketing_product.keywords.splitlines() if kw.strip()]

    keywords_text = "\n".join([item['keyword'] for item in keywords_list])
    
    # 총 키워드 개수
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
    """텍스트 영역의 키워드를 저장/업데이트 (중복 제거 로직 추가)"""
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    
    total_attempted = 0
    duplicate_in_batch = 0
    newly_added_count = 0
    
    if marketing_product:
        # 1. DB에 이미 저장된 키워드 맵 (상태 유지를 위해)
        old_keywords_map = {}
        if marketing_product.keywords:
            try:
                for item in json.loads(marketing_product.keywords):
                    old_keywords_map[item['keyword']] = item['active']
            except json.JSONDecodeError: pass

        # 2. 텍스트 영역의 키워드 처리 (입력 자체의 중복 제거)
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

        # 3. 기존 맵에 새로운 키워드만 추가
        final_keywords_map = old_keywords_map.copy()
        for kw in new_keywords_from_textarea:
            if kw not in final_keywords_map:
                final_keywords_map[kw] = True # 새 키워드는 항상 active: True로 시작
                newly_added_count += 1
        
        # 4. 최종 리스트로 변환하여 저장
        final_keywords_list = [{"keyword": k, "active": v} for k, v in final_keywords_map.items()]
        marketing_product.keywords = json.dumps(final_keywords_list, ensure_ascii=False, indent=4)
        db.commit()

        # 5. 총 중복 개수 계산 (배치 내 중복 + DB 중복)
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

# --- Account Management ---
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

# --- Cafe Membership Management ---
@router.post("/membership/add", response_class=RedirectResponse)
async def add_cafe_membership(account_id: int = Form(...), cafe_id: int = Form(...), new_post_count: int = Form(0), edited_post_count: int = Form(0), db: Session = Depends(get_db)):
    existing = db.query(CafeMembership).filter_by(account_id=account_id, cafe_id=cafe_id).first()
    if not existing:
        status = "graduated" if (new_post_count + edited_post_count) >= 10 else "active"
        new_membership = CafeMembership(account_id=account_id, cafe_id=cafe_id, new_post_count=new_post_count, edited_post_count=edited_post_count, status=status)
        db.add(new_membership)
        db.commit()
    return RedirectResponse(url=f"/marketing/cafe?tab=memberships&cafe_id={cafe_id}", status_code=303)

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

# --- Target Cafe Management ---
@router.post("/cafe/add", response_class=RedirectResponse)
async def add_target_cafe(name: str = Form(...), url: str = Form(...), db: Session = Depends(get_db)):
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

# --- Marketing Product Management ---
@router.get("/product-selection", response_class=HTMLResponse)
async def select_marketing_product(request: Request, db: Session = Depends(get_db)):
    existing_ids = [mp.product_id for mp in db.query(MarketingProduct.product_id).all()]
    available_products = db.query(Product).filter(Product.id.notin_(existing_ids)).all()
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

# --- '글 관리' 라우트 (원본 그대로 유지, 댓글 포맷팅만 개선) ---
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

    # 전체 통계 계산 (모든 키워드의 글 포함)
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
    membership_map = {}
    for membership in all_memberships:
        if membership.status == 'active':
            if membership.account_id not in membership_map:
                membership_map[membership.account_id] = []
            if membership.cafe:
                membership_map[membership.account_id].append({"id": membership.cafe.id, "name": membership.cafe.name})
    
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
        "membership_map": membership_map,
        "total_pages": total_pages,
        "current_page": page,
        "keyword_search": keyword_search,
        "error": error_message,
        "post_stats": post_stats  # 통계 데이터 추가
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
                # 댓글을 계층 구조 텍스트로 변환 (개선된 포맷)
                comment_map = {c.id: c for c in ref.comments}
                top_level_comments = []
                for c in ref.comments:
                    c.structured_replies = []
                for c in ref.comments:
                    if c.parent_id and c.parent_id in comment_map:
                        comment_map[c.parent_id].structured_replies.append(c)
                    elif not c.parent_id:
                        top_level_comments.append(c)
                
                # 개선된 댓글 포맷팅 함수
                def format_comments(comments, indent = ""):
                    text = ""
                    for c in comments:
                        # Python의 3항 연산자
                        prefix = "작성자" if c.account_sequence == 0 else f"계정 {c.account_sequence}"
                        # Python의 리스트 컴프리헨션
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
        is_live=True if is_registration_complete else False
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