# routers/auth.py - 완전히 정비된 버전

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from datetime import date, datetime
from database import SessionLocal, User, LoginLog  # LoginLog 추가
import random
import string

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# 데이터베이스 세션 관리
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ========== 로그인/로그아웃 ==========

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """로그인 페이지 표시"""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """로그인 처리 (IP 로그 기록 포함)"""
    
    # IP 주소 가져오기
    client_ip = request.client.host
    forwarded_ip = request.headers.get("X-Forwarded-For")
    if forwarded_ip:
        client_ip = forwarded_ip.split(',')[0]
    
    # 사용자 조회
    user = db.query(User).filter(User.username == username).first()
    login_success = user and bcrypt.verify(password, user.password)
    
    # 로그인 로그 기록 (LoginLog 테이블이 있는 경우)
    try:
        log = LoginLog(
            username=username,
            ip_address=client_ip,
            login_time=datetime.now(),
            success=login_success,
            user_agent=request.headers.get("User-Agent", "")[:500]
        )
        db.add(log)
        db.commit()
    except:
        pass  # LoginLog 테이블이 없으면 패스
    
    if login_success:
        request.session["user"] = username
        request.session["is_admin"] = user.is_admin  # 추가
        request.session["can_manage_products"] = user.can_manage_products  # 추가
        request.session["can_manage_marketing"] = user.can_manage_marketing  # 추가
        request.session["login_date"] = date.today().isoformat()
        return RedirectResponse("/", status_code=303)
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "아이디 또는 비밀번호가 올바르지 않습니다."
        })

@router.get("/logout")
async def logout(request: Request):
    """로그아웃 처리"""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# ========== 회원가입 ==========

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """회원가입 페이지 표시"""
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """회원가입 처리"""
    
    # 중복 체크
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "이미 존재하는 아이디입니다."
        })
    
    # 신규 사용자 생성
    new_user = User(
        username=username,
        password=bcrypt.hash(password),
        is_admin=False,
        can_manage_products=False,
        can_manage_marketing=False,
        daily_quota=0  # 기본값
    )
    
    db.add(new_user)
    db.commit()
    
    return RedirectResponse("/login?registered=true", status_code=303)

# ========== 비밀번호 변경 ==========

@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    """비밀번호 변경 페이지"""
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("change_password.html", {"request": request})

@router.post("/change-password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """비밀번호 변경 처리"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=303)
    
    user = db.query(User).filter(User.username == username).first()
    
    if not user or not bcrypt.verify(current_password, user.password):
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "error": "현재 비밀번호가 올바르지 않습니다."
        })
    
    # 새 비밀번호 설정
    user.password = bcrypt.hash(new_password)
    db.commit()
    
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "success": True
    })

# ========== 비밀번호 찾기 ==========

def generate_temp_password(length=12):
    """임시 비밀번호 생성"""
    lowercase = random.choice(string.ascii_lowercase)
    uppercase = random.choice(string.ascii_uppercase)
    digit = random.choice(string.digits)
    special = random.choice('!@#$%^&*')
    
    all_chars = string.ascii_letters + string.digits + '!@#$%^&*'
    remaining_length = length - 4
    remaining_chars = [random.choice(all_chars) for _ in range(remaining_length)]
    
    password_list = [lowercase, uppercase, digit, special] + remaining_chars
    random.shuffle(password_list)
    
    return ''.join(password_list)

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """비밀번호 찾기 페이지"""
    return templates.TemplateResponse("forgot_password.html", {
        "request": request
    })

@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password(
    request: Request,
    username: str = Form(...),
    email: str = Form(None),
    db: Session = Depends(get_db)
):
    """임시 비밀번호 발급"""
    
    # 사용자 조회
    user = db.query(User).filter(User.username == username).first()
    
    if not user:
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "등록되지 않은 아이디입니다."
        })
    
    try:
        # 임시 비밀번호 생성 및 저장
        temp_password = generate_temp_password()
        user.password = bcrypt.hash(temp_password)
        db.commit()
        
        # IP 로그 기록
        try:
            client_ip = request.client.host
            forwarded_ip = request.headers.get("X-Forwarded-For")
            if forwarded_ip:
                client_ip = forwarded_ip.split(',')[0]
                
            log = LoginLog(
                username=username,
                ip_address=client_ip,
                login_time=datetime.now(),
                success=False,  # 비밀번호 재설정으로 표시
                user_agent="Password Reset"
            )
            db.add(log)
            db.commit()
        except:
            pass
        
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "temp_password": temp_password,
            "username": username
        })
        
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "임시 비밀번호 발급 중 오류가 발생했습니다."
        })