#admin_users.py

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from datetime import date # 날짜 기반 세션 만료를 위해 추가

from database import SessionLocal, User, LoginLog

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

@router.post("/users/toggle-orders/{user_id}")
def toggle_orders_permission(
    request: Request, 
    user_id: int,
    db: Session = Depends(get_db)
):
    """CS 관리(주문조회) 권한 토글"""
    # 관리자 체크
    admin_username = request.session.get("user")
    admin_user = db.query(User).filter(User.username == admin_username).first()
    
    if not admin_user or not admin_user.is_admin:
        return RedirectResponse(url="/login", status_code=302)
    
    # 대상 사용자 조회
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=302)
    
    # CS 관리 권한 토글
    user.can_manage_orders = not user.can_manage_orders
    db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=302)

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

# ✅ 사용자 삭제 (외래 키 관계 처리 추가)
@router.post("/users/delete", response_class=RedirectResponse)
async def delete_user(user_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        # 최고 관리자(shsboss274)는 삭제 불가
        if not user or user.username == 'shsboss274':
            return RedirectResponse("/admin/users?error=cannot_delete_admin", status_code=303)
        
        # ✅ 1. LoginLog 먼저 삭제
        db.query(LoginLog).filter(LoginLog.user_id == user_id).delete()

        # ✅ 2. PersonalMemo 관련 삭제 (MemoFile은 DB CASCADE로 자동 삭제됨)
        try:
            from database import PersonalMemo
            db.query(PersonalMemo).filter(PersonalMemo.user_id == user_id).delete()
        except Exception:
            pass

        # ✅ 3. TaskAssignment 관련 처리 (creator/assignee)
        try:
            from database import TaskAssignment
            # 작성자인 경우 삭제, 담당자인 경우 null 처리 (nullable 컬럼)
            db.query(TaskAssignment).filter(TaskAssignment.creator_id == user_id).delete()
            db.query(TaskAssignment).filter(TaskAssignment.assignee_id == user_id).update(
                {TaskAssignment.assignee_id: None}
            )
        except Exception:
            pass

        # ✅ 4. TaskNotification 삭제
        try:
            from database import TaskNotification
            db.query(TaskNotification).filter(TaskNotification.user_id == user_id).delete()
        except Exception:
            pass

        # ✅ 5. WorkTask 삭제 (있다면)
        try:
            from database import WorkTask
            db.query(WorkTask).filter(WorkTask.worker_id == user_id).delete()
        except Exception:
            pass

        # ✅ 6. PostSchedule 삭제 (있다면)
        try:
            from database import PostSchedule
            db.query(PostSchedule).filter(PostSchedule.worker_id == user_id).delete()
        except Exception:
            pass

        # ✅ 7. 마지막으로 User 삭제
        db.delete(user)
        db.commit()
        
        return RedirectResponse("/admin/users?success=deleted", status_code=303)
        
    except Exception as e:
        db.rollback()
        print(f"❌ 사용자 삭제 오류: {e}")
        import traceback
        traceback.print_exc()
        return RedirectResponse("/admin/users?error=delete_failed", status_code=303)


# ✅ 로그인 기록 보기 (관리자 전용)
@router.get("/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request, 
    user_filter: str = "",
    db: Session = Depends(get_db)
):
    """로그인 기록 보기"""
    # 세션 만료 체크
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()
    
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_admin:
        return RedirectResponse("/", status_code=302)
    
    # ⭐ 권한 변수 추가
    is_admin = current_user.is_admin
    can_manage_products = current_user.can_manage_products or is_admin
    can_manage_marketing = current_user.can_manage_marketing or is_admin
    
    # 로그 조회 (최신 순)
    from sqlalchemy.orm import joinedload
    logs_query = db.query(LoginLog).options(joinedload(LoginLog.user))
    
    # 사용자 필터링
    if user_filter:
        logs_query = logs_query.join(User).filter(User.username.contains(user_filter))
    
    logs = logs_query.order_by(LoginLog.login_time.desc()).limit(500).all()
    
    # 통계 계산
    from datetime import datetime, timedelta
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    # 오늘 로그인
    today_logs = [log for log in logs if log.login_time.date() == today]
    # 이번 주 로그인
    week_logs = [log for log in logs if log.login_time.date() >= week_ago]
    # 실패한 로그인
    failed_logs = [log for log in logs if not log.success]
    
    stats = {
        'total': len(logs),
        'today': len(today_logs),
        'week': len(week_logs),
        'failed': len(failed_logs)
    }
    
    return templates.TemplateResponse("view_logs.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,  # ⭐ 추가
        "can_manage_products": can_manage_products,  # ⭐ 추가
        "can_manage_marketing": can_manage_marketing,  # ⭐ 추가
        "logs": logs,
        "user_filter": user_filter,
        "stats": stats
    })