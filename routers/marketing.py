from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import json

from database import SessionLocal, TargetCafe, MarketingAccount, Product, MarketingProduct, CafeMembership

router = APIRouter(prefix="/marketing")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 카페 관리 메인 페이지 ---
@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get('tab', 'status')
    error = request.query_params.get('error')
    error_message = "이미 사용 중인 아이디입니다." if error == 'duplicate_account' else None
    
    selected_cafe_id = request.query_params.get('cafe_id')
    status_filter = request.query_params.get('status_filter', 'all')
    category_filter = request.query_params.get('category_filter', 'all')
    
    selected_cafe, memberships = None, []
    if selected_cafe_id:
        selected_cafe = db.query(TargetCafe).filter(TargetCafe.id == selected_cafe_id).first()
        query = db.query(CafeMembership).filter(CafeMembership.cafe_id == selected_cafe_id)
        if status_filter != 'all':
            query = query.filter(CafeMembership.status == status_filter)
        memberships = query.order_by(CafeMembership.account_id).all()
        
    cafes = db.query(TargetCafe).all()
    accounts_query = db.query(MarketingAccount)
    if category_filter != 'all':
        accounts_query = accounts_query.filter(MarketingAccount.category == category_filter)
    accounts = accounts_query.order_by(MarketingAccount.id).all()
    marketing_products = db.query(MarketingProduct).all()
    
    return templates.TemplateResponse("marketing_cafe.html", {
        "request": request, "cafes": cafes, "accounts": accounts,
        "marketing_products": marketing_products, "memberships": memberships,
        "selected_cafe": selected_cafe, "status_filter": status_filter,
        "category_filter": category_filter, "error": error_message,
        "active_tab": tab
    })

# --- 키워드 관리 ---
@router.get("/product/keywords/{mp_id}", response_class=HTMLResponse)
async def get_product_keywords(request: Request, mp_id: int, db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    keywords_list = []
    if marketing_product and marketing_product.keywords:
        try:
            keywords_list = json.loads(marketing_product.keywords)
        except json.JSONDecodeError:
            keywords_list = [{"keyword": kw.strip(), "active": True} for kw in marketing_product.keywords.splitlines() if kw.strip()]
    keywords_text = "\n".join([item['keyword'] for item in keywords_list])
    return templates.TemplateResponse("marketing_product_keywords.html", {
        "request": request,
        "marketing_product": marketing_product,
        "keywords_list": keywords_list,
        "keywords_text": keywords_text
    })

@router.post("/product/keywords/{mp_id}", response_class=RedirectResponse)
async def update_product_keywords(mp_id: int, keywords: str = Form(...), db: Session = Depends(get_db)):
    marketing_product = db.query(MarketingProduct).filter(MarketingProduct.id == mp_id).first()
    if marketing_product:
        old_keywords = {}
        if marketing_product.keywords:
            try:
                for item in json.loads(marketing_product.keywords):
                    old_keywords[item['keyword']] = item['active']
            except json.JSONDecodeError: pass
        new_keywords_list = []
        for line in keywords.splitlines():
            keyword_text = line.strip()
            if keyword_text:
                new_keywords_list.append({
                    "keyword": keyword_text,
                    "active": old_keywords.get(keyword_text, True)
                })
        marketing_product.keywords = json.dumps(new_keywords_list, ensure_ascii=False, indent=4)
        db.commit()
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

# --- 계정 관리 ---
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

# --- 카페-계정 연동 관리 ---
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
    if membership:
        membership.new_post_count = new_post_count
        membership.edited_post_count = edited_post_count
        if (new_post_count + edited_post_count) >= 10:
            membership.status = "graduated"
        else:
            membership.status = status
        db.commit()
        return RedirectResponse(url=f"/marketing/cafe?tab=memberships&cafe_id={membership.cafe_id}", status_code=303)
    return RedirectResponse(url="/marketing/cafe?tab=memberships", status_code=303)

# --- 타겟 카페 관리 ---
@router.post("/cafe/add", response_class=RedirectResponse)
async def add_target_cafe(name: str = Form(...), url: str = Form(...), db: Session = Depends(get_db)):
    new_cafe = TargetCafe(name=name, url=url)
    db.add(new_cafe)
    db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

@router.post("/cafe/delete/{cafe_id}", response_class=RedirectResponse)
async def delete_target_cafe(cafe_id: int, db: Session = Depends(get_db)):
    cafe_to_delete = db.query(TargetCafe).filter(TargetCafe.id == cafe_id).first()
    if cafe_to_delete:
        db.delete(cafe_to_delete)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=cafes", status_code=303)

# --- 마케팅 상품 관리 ---
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

# --- 다른 마케팅 페이지 (구조만 유지) ---
@router.get("/blog", response_class=HTMLResponse)
async def marketing_blog(request: Request):
    return templates.TemplateResponse("marketing_blog.html", {"request": request})

@router.get("/homepage", response_class=HTMLResponse)
async def marketing_homepage(request: Request):
    return templates.TemplateResponse("marketing_homepage.html", {"request": request})

@router.get("/kin", response_class=HTMLResponse)
async def marketing_kin(request: Request):
    return templates.TemplateResponse("marketing_kin.html", {"request": request})

