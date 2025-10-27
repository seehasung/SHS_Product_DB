from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from datetime import date # 날짜 기반 세션 만료를 위해 추가

from database import SessionLocal, User

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

# --- ▼▼▼ 데이터베이스 세션을 가져오는 함수 (수정됨) ▼▼▼ ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# --- ▲▲▲ 데이터베이스 세션을 가져오는 함수 (수정됨) ▲▲▲ ---

# ✅ 사용자 목록 보기 (세션 만료 기능 및 get_db 적용)
@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, search: str = "", db: Session = Depends(get_db)):
    # --- ▼ 일일 세션 만료 기능 추가 ▼ ---
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()
    # --- ▲ 일일 세션 만료 기능 추가 ▲ ---

    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)

    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_admin:
        return RedirectResponse("/", status_code=302)

    users_query = db.query(User)
    if search:
        # DB에서 직접 필터링 (더 효율적)
        users_query = users_query.filter(User.username.contains(search))
    
    users = users_query.order_by(User.id).all()
    
    # db.close() # <--- get_db가 자동으로 처리하므로 삭제
    return templates.TemplateResponse("admin_users_bootstrap.html", {
        "request": request,
        "users": users,
        "username": username,
        "search": search
    })

# --- ▼▼▼ 비밀번호 초기화 기능 (get_db 적용) ▼▼▼ ---
@router.post("/users/reset-password", response_class=RedirectResponse)
async def reset_password(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274': # 최고 관리자 제외
        user.password = bcrypt.hash("1234") # '1234'로 비밀번호 초기화
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303) # 302 -> 303으로 변경

# ✅ 사용자 이름 수정 (get_db 적용)
@router.post("/users/update", response_class=RedirectResponse)
async def update_user(user_id: int = Form(...), new_username: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.username = new_username
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303) # 302 -> 303으로 변경

# ✅ 최고 관리자 권한 토글 (get_db 적용)
@router.post("/users/toggle-admin/{user_id}", response_class=RedirectResponse)
async def toggle_admin(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274':
        user.is_admin = not user.is_admin
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 상품 관리 권한 토글 (get_db 적용)
@router.post("/users/toggle-products/{user_id}", response_class=RedirectResponse)
async def toggle_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.can_manage_products = not user.can_manage_products
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 마케팅 관리 권한 토글 (get_db 적용)
@router.post("/users/toggle-marketing/{user_id}", response_class=RedirectResponse)
async def toggle_marketing(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.can_manage_marketing = not user.can_manage_marketing
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303)

# --- ▼▼▼ 신규 할당량 관리 라우트 (get_db 적용) ▼▼▼ ---
@router.post("/users/set-quota/{user_id}", response_class=RedirectResponse)
async def set_user_quota(
    user_id: int, 
    daily_quota: int = Form(...),
    db: Session = Depends(get_db)
):
    """사용자의 일일 작업 할당량을 설정하는 라우트"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.daily_quota = daily_quota
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303)
# --- ▲▲▲ 신규 할당량 관리 라우트 ▲▲▲ ---

# ✅ 사용자 삭제 (get_db 적용)
@router.post("/users/delete", response_class=RedirectResponse)
async def delete_user(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274':
        db.delete(user)
        db.commit()
    # db.close() # <--- 삭제
    return RedirectResponse("/admin/users", status_code=303) # 302 -> 303으로 변경

