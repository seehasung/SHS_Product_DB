from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

# Product와 MarketingProduct 모델을 추가로 import 합니다.
from database import SessionLocal, TargetCafe, MarketingAccount, Product, MarketingProduct

router = APIRouter(prefix="/marketing")
templates = Jinja2Templates(directory="templates")

# 데이터베이스 세션을 가져오는 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 카페 관리 페이지 (메인) ---
@router.get("/cafe", response_class=HTMLResponse)
async def marketing_cafe(request: Request, db: Session = Depends(get_db)):
    tab = request.query_params.get('tab', 'status')
    cafes = db.query(TargetCafe).all()
    accounts = db.query(MarketingAccount).all()
    # 마케팅 상품 목록을 DB에서 가져옵니다.
    marketing_products = db.query(MarketingProduct).all()
    
    return templates.TemplateResponse("marketing_cafe.html", {
        "request": request,
        "cafes": cafes,
        "accounts": accounts,
        "marketing_products": marketing_products, # 템플릿으로 전달
        "active_tab": tab
    })

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

# --- 계정 관리 ---
@router.post("/account/add", response_class=RedirectResponse)
async def add_marketing_account(account_id: str = Form(...), account_pw: str = Form(...), ip_address: str = Form(None), db: Session = Depends(get_db)):
    hashed_pw = bcrypt.hash(account_pw)
    new_account = MarketingAccount(account_id=account_id, account_pw=hashed_pw, ip_address=ip_address)
    db.add(new_account)
    db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

@router.post("/account/delete/{account_id}", response_class=RedirectResponse)
async def delete_marketing_account(account_id: int, db: Session = Depends(get_db)):
    account_to_delete = db.query(MarketingAccount).filter(MarketingAccount.id == account_id).first()
    if account_to_delete:
        db.delete(account_to_delete)
        db.commit()
    return RedirectResponse(url="/marketing/cafe?tab=accounts", status_code=303)

# --- 마케팅 상품 관리 ---
@router.get("/product-selection", response_class=HTMLResponse)
async def select_marketing_product(request: Request, db: Session = Depends(get_db)):
    # 이미 마케팅 상품으로 등록된 ID들을 가져옵니다.
    existing_ids = [mp.product_id for mp in db.query(MarketingProduct.product_id).all()]
    # 등록되지 않은 상품들만 목록에 보여줍니다.
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

