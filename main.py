from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from datetime import date # date 추가

from database import Base, engine, SessionLocal, User
from routers import auth, admin_users, product, marketing


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="서하성", max_age=None) # max_age=None으로 설정

templates = Jinja2Templates(directory="templates")

# DB 초기화 (Alembic이 관리하므로 주석 처리 또는 삭제)
# Base.metadata.create_all(bind=engine)

# 라우터 등록
app.include_router(auth.router)
app.include_router(admin_users.router, prefix="/admin")
app.include_router(product.router)
app.include_router(marketing.router)

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    # --- ▼ 일일 세션 만료 기능 추가 ▼ ---
    # 페이지에 접근할 때마다 로그인한 날짜가 오늘과 같은지 확인
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear() # 날짜가 다르면 세션 초기화
    # --- ▲ 일일 세션 만료 기능 추가 ▲ ---

    username = request.session.get("user")
    is_admin = request.session.get("is_admin", False)
    can_manage_products = request.session.get("can_manage_products", False)
    can_manage_marketing = request.session.get("can_manage_marketing", False)

    if is_admin:
        can_manage_products = True
        can_manage_marketing = True

    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "can_manage_products": can_manage_products,
        "can_manage_marketing": can_manage_marketing
    })
