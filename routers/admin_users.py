from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import SessionLocal, User

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

    if search:
        users = db.query(User).filter(User.username.contains(search)).all()
    else:
        users = db.query(User).all()
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
