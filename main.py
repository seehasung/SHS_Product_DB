from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from database import Base, engine, SessionLocal, User
from routers import auth
from routers import admin_users
from routers import product


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="서하성")

templates = Jinja2Templates(directory="templates")

# DB 초기화
Base.metadata.create_all(bind=engine)

# ✅ 최초 관리자 계정 생성 (main.py에서 호출)
# database.py에서 import 해 와서 사용합니다.
from database import create_super_admin
create_super_admin()

# 라우터 등록
app.include_router(auth.router)         # 로그인 등
app.include_router(admin_users.router, prefix="/admin")
app.include_router(product.router)

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    username = request.session.get("user")
    is_admin = False
    if username:
        db = SessionLocal()
        user = db.query(User).filter(User.username == username).first()
        db.close()
        if user:
            is_admin = user.is_admin

    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin
    })
