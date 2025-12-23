# routers/auth.py - 완전한 예시 코드

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import bcrypt
from database import SessionLocal, User, LoginLog
import random
import string
import datetime

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 기존 로그인/회원가입 라우트 ==========

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """로그인 페이지 표시"""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """로그인 처리"""
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    
    # IP 주소 추출
    client_host = request.client.host if request.client else "Unknown"
    user_agent = request.headers.get("user-agent", "Unknown")
    
    if user and bcrypt.verify(password, user.password):
        # 세션 닫기 전에 필요한 속성을 모두 변수에 저장
        user_id = user.id
        is_admin = user.is_admin
        can_manage_products = user.can_manage_products
        can_manage_marketing = user.can_manage_marketing
        can_manage_orders = user.can_manage_orders  # ⭐ 추가!

        
        # 로그인 성공 - 기록 저장
        login_log = LoginLog(
            user_id=user_id,
            login_time=datetime.datetime.utcnow(),
            ip_address=client_host,
            user_agent=user_agent,
            success=True
        )
        db.add(login_log)
        db.commit()
        db.close()
        
        # 세션 설정 (DB 세션 닫은 후)
        from datetime import date
        request.session["user"] = username
        request.session["is_admin"] = is_admin
        request.session["can_manage_products"] = can_manage_products
        request.session["can_manage_marketing"] = can_manage_marketing
        request.session["can_manage_orders"] = can_manage_orders  # ⭐ 변수 사용
        request.session["login_date"] = date.today().isoformat()
        return RedirectResponse("/", status_code=303)
    else:
        # 로그인 실패 - 실패 기록 저장 (user가 존재하는 경우만)
        if user:
            login_log = LoginLog(
                user_id=user.id,
                login_time=datetime.datetime.utcnow(),
                ip_address=client_host,
                user_agent=user_agent,
                success=False
            )
            db.add(login_log)
            db.commit()
        
        db.close()
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "아이디 또는 비밀번호가 올바르지 않습니다."
        })

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    """회원가입 페이지 표시"""
    # ⭐ username 등 추가 (로그인 전이므로 None이나 빈 값)
    return templates.TemplateResponse("register.html", {
        "request": request,
        "username": None,  # ⭐ 추가
        "is_admin": False,  # ⭐ 추가
        "can_manage_products": False,  # ⭐ 추가
        "can_manage_marketing": False  # ⭐ 추가
    })

@router.post("/register", response_class=HTMLResponse)
def register(request: Request, username: str = Form(...), password: str = Form(...)):
    """회원가입 처리"""
    db = SessionLocal()
    
    # 중복 체크
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        db.close()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "username": None,  # ⭐ 추가
            "is_admin": False,  # ⭐ 추가
            "can_manage_products": False,  # ⭐ 추가
            "can_manage_marketing": False,  # ⭐ 추가
            "error": "이미 존재하는 아이디입니다."
        })
    
    # 신규 사용자 생성
    hashed_password = bcrypt.hash(password)
    new_user = User(
        username=username,
        password=hashed_password,
        is_admin=False,
        can_manage_products=False,
        can_manage_marketing=False
    )
    
    db.add(new_user)
    db.commit()
    db.close()
    
    return RedirectResponse("/login?registered=true", status_code=303)

@router.get("/logout")
def logout(request: Request):
    """로그아웃 처리"""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@router.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request):
    """비밀번호 변경 페이지"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=303)
    
    # ⭐ 세션에서 권한 정보 가져오기
    is_admin = request.session.get("is_admin", False)
    can_manage_products = request.session.get("can_manage_products", False)
    can_manage_marketing = request.session.get("can_manage_marketing", False)
    
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "username": username,  # ⭐ 추가
        "is_admin": is_admin,  # ⭐ 추가
        "can_manage_products": can_manage_products,  # ⭐ 추가
        "can_manage_marketing": can_manage_marketing  # ⭐ 추가
    })

@router.post("/change-password", response_class=HTMLResponse)
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...)
):
    """비밀번호 변경 처리"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=303)
    
    # ⭐ 세션에서 권한 정보 가져오기
    is_admin = request.session.get("is_admin", False)
    can_manage_products = request.session.get("can_manage_products", False)
    can_manage_marketing = request.session.get("can_manage_marketing", False)
    
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    
    if not user or not bcrypt.verify(current_password, user.password):
        db.close()
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "username": username,  # ⭐ 추가
            "is_admin": is_admin,  # ⭐ 추가
            "can_manage_products": can_manage_products,  # ⭐ 추가
            "can_manage_marketing": can_manage_marketing,  # ⭐ 추가
            "error": "현재 비밀번호가 올바르지 않습니다."
        })
    
    # 새 비밀번호 설정
    user.password = bcrypt.hash(new_password)
    db.commit()
    db.close()
    
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "username": username,  # ⭐ 추가
        "is_admin": is_admin,  # ⭐ 추가
        "can_manage_products": can_manage_products,  # ⭐ 추가
        "can_manage_marketing": can_manage_marketing,  # ⭐ 추가
        "success": True
    })
# ========== 새로 추가: 비밀번호 찾기 기능 ==========

def generate_temp_password(length=12):
    """임시 비밀번호 생성"""
    # 각 문자 유형별로 최소 1개씩 포함
    lowercase = random.choice(string.ascii_lowercase)
    uppercase = random.choice(string.ascii_uppercase)
    digit = random.choice(string.digits)
    special = random.choice('!@#$%^&*')
    
    # 나머지 문자들
    all_chars = string.ascii_letters + string.digits + '!@#$%^&*'
    remaining_length = length - 4
    remaining_chars = [random.choice(all_chars) for _ in range(remaining_length)]
    
    # 모든 문자 섞기
    password_list = [lowercase, uppercase, digit, special] + remaining_chars
    random.shuffle(password_list)
    
    return ''.join(password_list)

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    """비밀번호 찾기 페이지 표시"""
    return templates.TemplateResponse("forgot-password.html", {
        "request": request
    })

@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(
    request: Request,
    username: str = Form(...),
    email: str = Form(None)  # 이메일은 선택사항
):
    """임시 비밀번호 발급"""
    db = SessionLocal()
    
    try:
        # 사용자 조회
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            return templates.TemplateResponse("forgot-password.html", {
                "request": request,
                "error": "등록되지 않은 아이디입니다."
            })
        
        # 임시 비밀번호 생성
        temp_password = generate_temp_password()
        
        # 비밀번호 해시화하여 저장
        hashed_password = bcrypt.hash(temp_password)
        user.password = hashed_password
        
        # 변경사항 저장
        db.commit()
        
        # 성공 페이지 표시 (임시 비밀번호 표시)
        return templates.TemplateResponse("forgot-password.html", {
            "request": request,
            "temp_password": temp_password,
            "username": username
        })
        
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("forgot-password.html", {
            "request": request,
            "error": "임시 비밀번호 발급 중 오류가 발생했습니다."
        })
    finally:
        db.close()