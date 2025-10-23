from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from datetime import date, datetime  # date와 datetime 한 번에 import
from sqlalchemy import or_, func

from database import Base, engine, SessionLocal, User, PostSchedule, MarketingPost
from routers import auth, admin_users, product, marketing


app = FastAPI()

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
    
    if username and (can_manage_marketing or is_admin):
        db = SessionLocal()
        try:
            today = datetime.now().date()
            
            # 오늘의 스케줄 통계
            today_schedules = db.query(PostSchedule).filter(
                PostSchedule.scheduled_date == today
            ).all()
            
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
        "active_workers": active_workers
    })