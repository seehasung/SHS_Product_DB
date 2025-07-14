from fastapi import APIRouter, Request, Form
from sqlalchemy.exc import IntegrityError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import math
from fastapi import Query
from database import SessionLocal, User, Product

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ✅ 사용자 목록 보기 (검색 포함)
@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, search: str = ""):
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)

    db: Session = SessionLocal()
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_admin:
        db.close()
        return RedirectResponse("/", status_code=302)

    users = db.query(User).filter(User.username.contains(search)).all() if search else db.query(User).all()
    db.close()
    return templates.TemplateResponse("admin_users_bootstrap.html", {
        "request": request,
        "users": users,
        "username": username,
        "search": search
    })

# ✅ 사용자 이름 수정
@router.post("/users/update")
def update_user(user_id: int = Form(...), new_username: str = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.username = new_username
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 관리자 권한 토글
@router.post("/users/toggle-admin")
def toggle_admin(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_admin = not user.is_admin
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 사용자 삭제
@router.post("/users/delete")
def delete_user(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'admin':
        db.delete(user)
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 상품 목록 보기
@router.get("/products", response_class=HTMLResponse)
def product_list(
    request: Request,
    keyword: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1)
):
    db = SessionLocal()
    
    # 정렬 키 함수: '1-10' 같은 문자열을 (1, 10) 같은 숫자 튜플로 변환
    def custom_sort_key(product):
        try:
            parts = product.product_code.split('-')
            # 파트가 2개 이상이고 모두 숫자로 변환 가능할 때만 처리
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return (int(parts[0]), int(parts[1]))
            # 형식이 맞지 않는 경우, 맨 뒤로 보내기 위해 큰 값을 반환
            return (float('inf'),)
        except (ValueError, IndexError):
            # 그 외 예외 발생 시에도 맨 뒤로 보냄
            return (float('inf'),)

    # 검색 쿼리
    query = db.query(Product)
    if keyword:
        query = query.filter(Product.name.contains(keyword))
    
    # --- ▼▼▼ 정렬 로직 변경 ▼▼▼ ---
    # 1. DB에서 모든 검색 결과를 가져옴
    all_filtered_products = query.all()

    # 2. Python에서 직접 정렬
    sorted_products = sorted(all_filtered_products, key=custom_sort_key)
    
    # 3. 전체 아이템 수 및 페이지 수 계산
    total_products = len(sorted_products)
    total_pages = math.ceil(total_products / size)

    # 4. 현재 페이지에 해당하는 부분만 잘라내기
    offset = (page - 1) * size
    paginated_products = sorted_products[offset : offset + size]
    # --- ▲▲▲ 정렬 로직 변경 ▲▲▲ ---

    db.close()
    
    return templates.TemplateResponse("admin_products.html", {
        "request": request,
        "products": paginated_products, # 정렬 및 페이징된 최종 목록 전달
        "keyword": keyword,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": size,
        "total_products": total_products
    })
# ✅ 상품 등록 폼
@router.get("/products/create", response_class=HTMLResponse)
def product_create_form(request: Request):
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": None,
        "coupang_options": [],
        "taobao_options": []
    })
    
# ✅ 상품 등록 처리 (수정된 최종 버전)
@router.post("/products/create")
def product_create(
    request: Request,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: Optional[str] = Form(None),
    customs_paid: Optional[str] = Form(None),
    coupang_link: Optional[str] = Form(""),
    taobao_link: Optional[str] = Form(""),
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
    ])

    db = SessionLocal()
    
    try:
        new_product = Product(
            product_code=product_code,
            name=name,
            price=price,
            kd_paid=(kd_paid == "on"),
            customs_paid=(customs_paid == "on"),
            coupang_link=coupang_link,
            taobao_link=taobao_link,
            coupang_options=coupang_options,
            taobao_options=taobao_options,
            thumbnail=thumbnail,
            details=details
        )
        db.add(new_product)
        db.commit()
        db.close()
        return RedirectResponse("/products?success=create", status_code=302)
    except IntegrityError:
        db.rollback()
        db.close()
        form_data = {
            "product_code": product_code, "name": name, "price": price,
            "kd_paid": (kd_paid == "on"), "customs_paid": (customs_paid == "on"),
            "coupang_link": coupang_link, "taobao_link": taobao_link,
            "thumbnail": thumbnail, "details": details
        }
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]")
        })


# ✅ 상품 상세 보기
@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    db.close()
    if not product:
        return RedirectResponse("/products", status_code=302)
    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "product": product,
        "coupang_options": json.loads(product.coupang_options or "[]"),
        "taobao_options": json.loads(product.taobao_options or "[]")
    })

# ✅ 상품 수정 폼
@router.get("/products/edit/{product_id}", response_class=HTMLResponse)
def edit_product_form(request: Request, product_id: int):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    db.close()
    return templates.TemplateResponse("product_form.html", {
        "request": request,
        "product": product,
        "coupang_options": json.loads(product.coupang_options or "[]"),
        "taobao_options": json.loads(product.taobao_options or "[]")
    })

# ✅ 상품 수정 처리 (수정된 최종 버전)
@router.post("/products/edit/{product_id}")
def edit_product(
    request: Request, # request 파라미터 추가
    product_id: int,
    product_code: str = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    kd_paid: Optional[str] = Form(None),
    customs_paid: Optional[str] = Form(None),
    coupang_link: Optional[str] = Form(""),
    taobao_link: Optional[str] = Form(""),
    coupang_option_names: Optional[List[str]] = Form([]),
    coupang_option_prices: Optional[List[int]] = Form([]),
    taobao_option_names: Optional[List[str]] = Form([]),
    taobao_option_prices: Optional[List[int]] = Form([]),
    thumbnail: Optional[str] = Form(""),
    details: Optional[str] = Form("")
):
    coupang_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(coupang_option_names, coupang_option_prices)
    ])
    taobao_options = json.dumps([
        {"name": n, "price": p} for n, p in zip(taobao_option_names, taobao_option_prices)
    ])

    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    
    try:
        if product:
            product.product_code = product_code
            product.name = name
            product.price = price
            product.kd_paid = (kd_paid == "on")
            product.customs_paid = (customs_paid == "on")
            product.coupang_link = coupang_link
            product.taobao_link = taobao_link
            product.coupang_options = coupang_options
            product.taobao_options = taobao_options
            product.thumbnail = thumbnail
            product.details = details
            db.commit()
        db.close()
        return RedirectResponse("/products?success=edit", status_code=302) # create -> edit 으로 수정
    except IntegrityError:
        db.rollback()
        db.close()
        # 에러 발생 시, 현재 product 객체에 입력된 값을 덮어써서 form에 전달
        form_data_from_product = product.__dict__
        form_data_from_product.update({
             "product_code": product_code, "name": name, "price": price,
            "kd_paid": (kd_paid == "on"), "customs_paid": (customs_paid == "on"),
            "coupang_link": coupang_link, "taobao_link": taobao_link,
            "thumbnail": thumbnail, "details": details
        })
        return templates.TemplateResponse("product_form.html", {
            "request": request,
            "error": "이미 사용 중인 상품 ID입니다.",
            "product": form_data_from_product,
            "coupang_options": json.loads(coupang_options or "[]"),
            "taobao_options": json.loads(taobao_options or "[]")
        })
        
        
# ✅ 상품 삭제
@router.post("/products/delete")
def product_delete(product_id: int = Form(...)):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    db.close()
    return RedirectResponse("/products", status_code=302)
