#main.py

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware  # ✅ CORS 미들웨어
from datetime import date, datetime  # date와 datetime 한 번에 import
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload  # ✅ 추가!
from websocket_manager import manager
from contextlib import asynccontextmanager
from scheduler import start_scheduler, stop_scheduler
from routers import tasks
import os
from dotenv import load_dotenv  # ✅ 환경변수 로드

# ✅ 환경변수 로드 (.env 파일에서)
load_dotenv()


from database import (
    Base, engine, SessionLocal, User, PostSchedule, MarketingPost,
    MarketingProduct, Product
)
from routers import auth, admin_users, product, marketing, tasks, blog, homepage, orders  

# ✅ Render Disk 경로 설정
STATIC_DIR = "/opt/render/project/src/static"
UPLOAD_DIR = f"{STATIC_DIR}/uploads"

# 📁 디렉토리 생성
os.makedirs(f"{UPLOAD_DIR}/homepage_images", exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/cafe_images", exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/blog_images", exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/task_images", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 이벤트"""
    # 시작 시
    start_scheduler()
    yield
    # 종료 시
    stop_scheduler()

app = FastAPI(lifespan=lifespan)

# ✅ 환경변수에서 설정값 가져오기
SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-dev-key-DO-NOT-USE-IN-PRODUCTION")
ENV = os.environ.get("ENV", "development")
DEBUG = os.environ.get("DEBUG", "True") == "True"
APP_DOMAIN = os.environ.get("APP_DOMAIN", "http://localhost:10000")

# ✅ CORS 설정 (Cross-Origin Resource Sharing)
# 개발 환경: localhost 허용, 운영 환경: 실제 도메인만 허용
if ENV == "development":
    # 개발 환경: 로컬호스트 모두 허용
    allowed_origins = [
        "http://localhost:10000",
        "http://127.0.0.1:10000",
        "http://localhost:8000",
    ]
else:
    # 운영 환경: 실제 도메인만 허용
    allowed_origins = [APP_DOMAIN] if APP_DOMAIN else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# ✅ 세션 미들웨어 설정 (보안 강화)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,  # ✅ 환경변수 사용
    max_age=None,
    https_only=(ENV == "production"),  # ✅ 운영 환경에서만 HTTPS 강제
    same_site='lax' if ENV == "development" else 'none'  # ✅ 개발/운영 분리
)

# ✅ 보안 헤더 미들웨어 (XSS, Clickjacking 방어)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """모든 응답에 보안 헤더 추가"""
    response = await call_next(request)
    
    # XSS 방어: 브라우저가 MIME 타입 추측하지 못하게 함
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Clickjacking 방어: iframe 삽입 차단
    response.headers["X-Frame-Options"] = "DENY"
    
    # XSS 필터 활성화 (구형 브라우저용)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # HTTPS 강제 (운영 환경만)
    if ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response

templates = Jinja2Templates(directory="templates")

# DB 초기화 (Alembic이 관리하므로 주석 처리)
# Base.metadata.create_all(bind=engine)

# 라우터 등록
app.include_router(auth.router)
app.include_router(admin_users.router)  # prefix 제거됨 (admin_users.py에서 처리)
app.include_router(product.router)
app.include_router(homepage.router, prefix="/marketing")
app.include_router(marketing.router)
app.include_router(tasks.router)
app.include_router(blog.router)
app.include_router(orders.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")



@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    
    # 일일 세션 만료 기능
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()

    username = request.session.get("user")
    is_admin = request.session.get("is_admin", False)
    can_manage_products = request.session.get("can_manage_products", False)
    can_manage_marketing = request.session.get("can_manage_marketing", False)
    can_manage_orders = request.session.get("can_manage_orders", False)  # ⭐ 추가

    # 관리자는 모든 권한 자동 부여
    if is_admin:
        can_manage_products = True
        can_manage_marketing = True
        can_manage_orders = True  # ⭐ 추가

    
    # --- 마케팅 통계 데이터 추가 (마케팅 권한이 있을 때만) ---
    today_stats = {}
    today_schedules = []
    
    # ⭐ 업무 지시 통계 초기화
    task_stats = {
        'new': 0,
        'confirmed': 0,
        'in_progress': 0,
        'on_hold': 0
    }
    
    my_pending_tasks = []
    
    if username and (can_manage_marketing or is_admin):
        db = SessionLocal()
        try:
            today = datetime.now().date()
            
            # 현재 로그인한 사용자 정보 가져오기
            current_user = db.query(User).filter(User.username == username).first()
            
            # ✅ 오늘의 스케줄 조회 (관계 데이터 미리 로드)
            if current_user:
                if is_admin:
                    # 관리자: 모든 작업자의 스케줄
                    today_schedules = db.query(PostSchedule).options(
                        joinedload(PostSchedule.worker),
                        joinedload(PostSchedule.account),
                        joinedload(PostSchedule.cafe),
                        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product)
                    ).filter(
                        PostSchedule.scheduled_date == today
                    ).limit(10).all()
                    
                    # 관리자: 전체 통계
                    today_stats = {
                        'today_pending': db.query(PostSchedule).filter(
                            PostSchedule.scheduled_date == today,
                            PostSchedule.status == 'pending'
                        ).count(),
                        'today_completed': db.query(PostSchedule).filter(
                            PostSchedule.scheduled_date == today,
                            PostSchedule.status == 'completed'
                        ).count(),
                        'all_pending': db.query(PostSchedule).filter(
                            PostSchedule.status == 'pending'
                        ).count(),
                        'all_in_progress': db.query(PostSchedule).filter(
                            PostSchedule.status == 'in_progress'
                        ).count()
                    }
                else:
                    # 일반 작업자: 본인 스케줄만
                    today_schedules = db.query(PostSchedule).options(
                        joinedload(PostSchedule.worker),
                        joinedload(PostSchedule.account),
                        joinedload(PostSchedule.cafe),
                        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product)
                    ).filter(
                        PostSchedule.scheduled_date == today,
                        PostSchedule.worker_id == current_user.id
                    ).all()
                    
                    # 일반 작업자: 본인 통계만
                    today_stats = {
                        'today_pending': db.query(PostSchedule).filter(
                            PostSchedule.scheduled_date == today,
                            PostSchedule.worker_id == current_user.id,
                            PostSchedule.status == 'pending'
                        ).count(),
                        'today_completed': db.query(PostSchedule).filter(
                            PostSchedule.scheduled_date == today,
                            PostSchedule.worker_id == current_user.id,
                            PostSchedule.status == 'completed'
                        ).count(),
                        'all_pending': db.query(PostSchedule).filter(
                            PostSchedule.worker_id == current_user.id,
                            PostSchedule.status == 'pending'
                        ).count(),
                        'all_in_progress': db.query(PostSchedule).filter(
                            PostSchedule.worker_id == current_user.id,
                            PostSchedule.status == 'in_progress'
                        ).count()
                    }
            else:
                today_schedules = []
                today_stats = {
                    'today_pending': 0,
                    'today_completed': 0,
                    'all_pending': 0,
                    'all_in_progress': 0
                }
                
        except Exception as e:
            print(f"통계 데이터 로드 중 오류: {e}")
            today_stats = {
                'today_pending': 0,
                'today_completed': 0,
                'all_pending': 0,
                'all_in_progress': 0
            }
            today_schedules = []
        finally:
            db.close()
    
    # ⭐ 업무 지시 통계 (로그인한 모든 사용자)
    if username:
        from database import TaskAssignment  # 여기서 import
        db = SessionLocal()
        try:
            current_user = db.query(User).filter(User.username == username).first()
            if current_user:
                # 내가 받은 업무 통계
                task_stats['new'] = db.query(TaskAssignment).filter(
                    TaskAssignment.assignee_id == current_user.id,
                    TaskAssignment.status == 'new'
                ).count()

                task_stats['confirmed'] = db.query(TaskAssignment).filter(
                    TaskAssignment.assignee_id == current_user.id,
                    TaskAssignment.status == 'confirmed'
                ).count()

                task_stats['in_progress'] = db.query(TaskAssignment).filter(
                    TaskAssignment.assignee_id == current_user.id,
                    TaskAssignment.status == 'in_progress'
                ).count()

                task_stats['on_hold'] = db.query(TaskAssignment).filter(
                    TaskAssignment.assignee_id == current_user.id,
                    TaskAssignment.status == 'on_hold'
                ).count()
                
                # 미완료 업무 목록 (최대 5개)
                my_pending_tasks = db.query(TaskAssignment).options(
                    joinedload(TaskAssignment.creator)
                ).filter(
                    TaskAssignment.assignee_id == current_user.id,
                    TaskAssignment.status.in_(['new', 'confirmed', 'in_progress'])
                ).order_by(TaskAssignment.deadline.asc()).limit(5).all()
        except Exception as e:
            print(f"업무 통계 로드 중 오류: {e}")
        finally:
            db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "can_manage_products": can_manage_products,
        "can_manage_marketing": can_manage_marketing,
        "can_manage_orders": can_manage_orders,  # ⭐ 추가
        "today": date.today().isoformat(),
        "today_stats": today_stats,
        "today_schedules": today_schedules,
        # ⭐ 업무 지시 데이터 추가
        "task_stats": task_stats,
        "my_pending_tasks": my_pending_tasks
    })
    
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """실시간 알림을 위한 WebSocket 연결"""
    await manager.connect(websocket, user_id)
    try:
        while True:
            # 클라이언트로부터 메시지 수신 (keep-alive)
            data = await websocket.receive_text()
            # ping 응답
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        print(f"WebSocket 오류: {e}")
        manager.disconnect(websocket, user_id)