#main.py

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from datetime import date, datetime  # date와 datetime 한 번에 import
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload  # ✅ 추가!
from websocket_manager import manager
from contextlib import asynccontextmanager
from scheduler import start_scheduler, stop_scheduler

from database import (
    Base, engine, SessionLocal, User, PostSchedule, MarketingPost,
    MarketingProduct  # ✅ 추가!
)
from routers import auth, admin_users, product, marketing, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 이벤트"""
    # 시작 시
    start_scheduler()
    yield
    # 종료 시
    stop_scheduler()

app = FastAPI(lifespan=lifespan)

# 세션 미들웨어 설정
app.add_middleware(
    SessionMiddleware,
    secret_key="서하성",
    max_age=None,
    https_only=True,  # HTTPS에서만 쿠키 사용
    same_site='none'  # Cross-site 쿠키 허용
)

templates = Jinja2Templates(directory="templates")

# DB 초기화 (Alembic이 관리하므로 주석 처리)
# Base.metadata.create_all(bind=engine)

# 라우터 등록
app.include_router(auth.router)
app.include_router(admin_users.router)  # prefix 제거됨 (admin_users.py에서 처리)
app.include_router(product.router)
app.include_router(marketing.router)
app.include_router(tasks.router)


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    # 일일 세션 만료 기능
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()

    username = request.session.get("user")
    is_admin = request.session.get("is_admin", False)
    can_manage_products = request.session.get("can_manage_products", False)
    can_manage_marketing = request.session.get("can_manage_marketing", False)

    # 관리자는 모든 권한 자동 부여
    if is_admin:
        can_manage_products = True
        can_manage_marketing = True
    
    # --- 마케팅 통계 데이터 추가 (마케팅 권한이 있을 때만) ---
    today_stats = {}
    total_posts = 0
    new_posts_today = 0
    active_workers = 0
    today_schedules = []  # 초기화 추가!
    
    if username and (can_manage_marketing or is_admin):
        db = SessionLocal()
        try:
            today = datetime.now().date()
            
            # 현재 로그인한 사용자 정보 가져오기
            current_user = db.query(User).filter(User.username == username).first()
            
            # ✅ 오늘의 스케줄 통계 (관계 데이터 미리 로드)
            if current_user:
                if is_admin:
                    # 관리자는 모든 스케줄 보기 (joinedload 추가!)
                    today_schedules = db.query(PostSchedule).options(
                        joinedload(PostSchedule.worker),
                        joinedload(PostSchedule.account),
                        joinedload(PostSchedule.cafe),
                        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product)
                    ).filter(
                        PostSchedule.scheduled_date == today
                    ).limit(10).all()  # 성능을 위해 최근 10개만
                else:
                    # 일반 사용자는 자신의 스케줄만 보기 (joinedload 추가!)
                    today_schedules = db.query(PostSchedule).options(
                        joinedload(PostSchedule.worker),
                        joinedload(PostSchedule.account),
                        joinedload(PostSchedule.cafe),
                        joinedload(PostSchedule.marketing_product).joinedload(MarketingProduct.product)
                    ).filter(
                        PostSchedule.scheduled_date == today,
                        PostSchedule.worker_id == current_user.id
                    ).all()
            else:
                today_schedules = []
            
            today_stats = {
                'total': len(today_schedules),
                'completed': sum(1 for s in today_schedules if s.status == 'completed'),
                'in_progress': sum(1 for s in today_schedules if s.status == 'in_progress'),
                'pending': sum(1 for s in today_schedules if s.status == 'pending')
            }
            
            # 완료율 계산
            if today_stats['total'] > 0:
                today_stats['percentage'] = round((today_stats['completed'] / today_stats['total']) * 100, 1)
            else:
                today_stats['percentage'] = 0
            
            # 전체 게시글 수
            total_posts = db.query(MarketingPost).filter(
                MarketingPost.is_live == True
            ).count()
            
            # 오늘 추가된 게시글 (created_at 필드가 없을 수도 있으므로 처리)
            try:
                new_posts_today = db.query(MarketingPost).filter(
                    func.date(MarketingPost.created_at) == today,
                    MarketingPost.is_live == True
                ).count()
            except:
                new_posts_today = 0  # created_at 필드가 없으면 0
            
            # 활성 작업자 수 (마케팅 권한이 있는 사용자)
            active_workers = db.query(User).filter(
                or_(User.can_manage_marketing == True, User.is_admin == True)
            ).count()
            
        except Exception as e:
            print(f"통계 데이터 로드 중 오류: {e}")
            # 오류 발생 시 기본값 사용
            today_stats = {'total': 0, 'completed': 0, 'in_progress': 0, 'pending': 0, 'percentage': 0}
            total_posts = 0
            new_posts_today = 0
            active_workers = 0
            today_schedules = []  # ✅ 오류 시에도 빈 리스트로 초기화
        finally:
            db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "can_manage_products": can_manage_products,
        "can_manage_marketing": can_manage_marketing,
        "today": date.today().isoformat(),  # 오늘 날짜 추가
        # 마케팅 통계 데이터 (권한이 있을 때만 전달)
        "today_stats": today_stats,
        "total_posts": total_posts,
        "new_posts_today": new_posts_today,
        "active_workers": active_workers,
        "today_schedules": today_schedules
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