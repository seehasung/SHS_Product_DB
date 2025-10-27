# admin.py - 최종 검증 완료 버전

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from datetime import date

from database import SessionLocal, User, LoginLog

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ✅ 사용자 목록 보기
@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, search: str = "", db: Session = Depends(get_db)):
    # 일일 세션 만료 기능
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()
    
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)

    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_admin:
        return RedirectResponse("/", status_code=302)

    users_query = db.query(User)
    if search:
        users_query = users_query.filter(User.username.contains(search))
    
    users = users_query.order_by(User.id).all()
    
    return templates.TemplateResponse("admin_users_bootstrap.html", {
        "request": request,
        "users": users,
        "username": username,
        "search": search
    })

# ✅ 비밀번호 초기화
@router.post("/users/reset-password", response_class=RedirectResponse)
async def reset_password(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274':
        user.password = bcrypt.hash("1234")
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 사용자 이름 수정
@router.post("/users/update", response_class=RedirectResponse)
async def update_user(user_id: int = Form(...), new_username: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.username = new_username
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 최고 관리자 권한 토글
@router.post("/users/toggle-admin/{user_id}", response_class=RedirectResponse)
async def toggle_admin(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274':
        user.is_admin = not user.is_admin
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 상품 관리 권한 토글
@router.post("/users/toggle-products/{user_id}", response_class=RedirectResponse)
async def toggle_products(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.can_manage_products = not user.can_manage_products
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 마케팅 관리 권한 토글
@router.post("/users/toggle-marketing/{user_id}", response_class=RedirectResponse)
async def toggle_marketing(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.can_manage_marketing = not user.can_manage_marketing
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 일일 할당량 설정
@router.post("/users/set-quota/{user_id}", response_class=RedirectResponse)
async def set_user_quota(
    user_id: int,
    request: Request,  # 기본값 없는 것을 앞으로
    daily_quota: int = Form(...),  # 기본값 있는 것을 뒤로
    db: Session = Depends(get_db)
):
    """일일 할당량 설정"""
    
    # 권한 체크
    current_username = request.session.get("user")
    if not current_username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == current_username).first()
    if not current_user or not current_user.is_admin:
        return RedirectResponse("/", status_code=302)
    
    # 대상 사용자 조회
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # 마케팅 권한 체크
        if user.can_manage_marketing:
            user.daily_quota = max(0, min(100, daily_quota))
        else:
            user.daily_quota = 0
        
        db.commit()
    
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 사용자 삭제
@router.post("/users/delete", response_class=RedirectResponse)
async def delete_user(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username != 'shsboss274':
        db.delete(user)
        db.commit()
    return RedirectResponse("/admin/users", status_code=303)

# ✅ 로그 보기 페이지
@router.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request, db: Session = Depends(get_db)):
    """로그인 로그 페이지"""
    
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_admin:
        return HTMLResponse("관리자 권한이 필요합니다", status_code=403)
    
    # LoginLog 모델이 있다면 조회, 없으면 빈 리스트
    try:
        logs = db.query(LoginLog).order_by(LoginLog.login_time.desc()).limit(100).all()
    except:
        logs = []
    
    return templates.TemplateResponse("login_logs.html", {
        "request": request,
        "logs": logs
    })