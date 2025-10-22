from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt # 비밀번호 해싱을 위해 추가
from datetime import date # 날짜 기반 세션 만료를 위해 추가

from database import SessionLocal, User

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ✅ 사용자 목록 보기 (세션 만료 기능 추가)
@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request, search: str = ""):
    # --- ▼ 일일 세션 만료 기능 추가 ▼ ---
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()
    # --- ▲ 일일 세션 만료 기능 추가 ▲ ---

    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)

    db: Session = SessionLocal()
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_admin:
        db.close()
        return RedirectResponse("/", status_code=302)

    users = db.query(User).order_by(User.id).all() # ID 순으로 정렬
    if search:
        users = [user for user in users if search.lower() in user.username.lower()]
    
    db.close()
    return templates.TemplateResponse("admin_users_bootstrap.html", {
        "request": request,
        "users": users,
        "username": username,
        "search": search
    })

# --- ▼▼▼ 비밀번호 초기화 기능 추가 ▼▼▼ ---
@router.post("/users/reset-password")
def reset_password(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274': # 최고 관리자 제외
        user.password = bcrypt.hash("1234") # '1234'로 비밀번호 초기화
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)
# --- ▲▲▲ 비밀번호 초기화 기능 추가 ▲▲▲ ---


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

# ✅ 최고 관리자 권한 토글
@router.post("/users/toggle-admin")
def toggle_admin(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_admin = not user.is_admin
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 상품 관리 권한 토글
@router.post("/users/toggle-products")
def toggle_products_permission(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.can_manage_products = not user.can_manage_products
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

# ✅ 마케팅 관리 권한 토글
@router.post("/users/toggle-marketing")
def toggle_marketing_permission(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.can_manage_marketing = not user.can_manage_marketing
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)


# ✅ 사용자 삭제
@router.post("/users/delete")
def delete_user(user_id: int = Form(...)):
    db: Session = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274':
        db.delete(user)
        db.commit()
    db.close()
    return RedirectResponse("/admin/users", status_code=302)

