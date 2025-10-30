# routers/tasks.py

from fastapi import APIRouter, Request, Form, Depends, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from datetime import date, datetime, timedelta
from typing import List, Optional
import os
import uuid
from websocket_manager import manager
import asyncio



from database import (
    SessionLocal, User, TaskAssignment, TaskComment, 
    TaskFile, TaskNotification
)

router = APIRouter(prefix="/tasks")
templates = Jinja2Templates(directory="templates")

# 파일 업로드 디렉토리
UPLOAD_DIR = "static/task_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_session(request: Request):
    """세션 확인 및 사용자 정보 반환"""
    if request.session.get("login_date") != date.today().isoformat():
        request.session.clear()
    
    username = request.session.get("user")
    if not username:
        return None
    return username

# ============================================
# 업무 지시 목록 및 대시보드
# ============================================

@router.get("/", response_class=HTMLResponse)
async def task_list(request: Request, db: Session = Depends(get_db)):
    """업무 지시 목록 (담당자 기준)"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    is_admin = request.session.get("is_admin", False)
    
    # 담당자로서 받은 업무 조회 (관계 데이터 미리 로드)
    tasks_query = db.query(TaskAssignment).options(
        joinedload(TaskAssignment.creator),
        joinedload(TaskAssignment.assignee)
    )
    
    if not is_admin:
        tasks_query = tasks_query.filter(TaskAssignment.assignee_id == current_user.id)
    
    tasks = tasks_query.order_by(
        TaskAssignment.status.in_(['new', 'confirmed', 'in_progress']).desc(),
        TaskAssignment.deadline.asc()
    ).all()
    
    # 미읽은 알림 수
    unread_count = db.query(TaskNotification).filter(
        TaskNotification.user_id == current_user.id,
        TaskNotification.is_read == False
    ).count()
    
    return templates.TemplateResponse("tasks/task_list.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "tasks": tasks,
        "unread_count": unread_count,
        "current_user_id": current_user.id  # ⭐ 추가

    })


@router.get("/dashboard", response_class=HTMLResponse)
async def task_dashboard(request: Request, db: Session = Depends(get_db)):
    """업무 지시 대시보드 (대표 전용)"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    is_admin = request.session.get("is_admin", False)
    if not is_admin:
        return RedirectResponse("/tasks", status_code=302)
    
    # 전체 통계
    today = datetime.now().date()
    three_months_ago = today - timedelta(days=90)
    
    # 상태별 통계
    total_tasks = db.query(TaskAssignment).count()
    new_tasks = db.query(TaskAssignment).filter(TaskAssignment.status == 'new').count()
    in_progress = db.query(TaskAssignment).filter(TaskAssignment.status == 'in_progress').count()
    completed = db.query(TaskAssignment).filter(TaskAssignment.status == 'completed').count()
    
    # 오늘 마감 업무
    today_deadline = db.query(TaskAssignment).filter(
        func.date(TaskAssignment.deadline) == today,
        TaskAssignment.status.in_(['new', 'confirmed', 'in_progress'])
    ).count()
    
    # 지연 업무 (마감 지났는데 미완료)
    delayed_tasks = db.query(TaskAssignment).filter(
        TaskAssignment.deadline < datetime.now(),
        TaskAssignment.status.in_(['new', 'confirmed', 'in_progress'])
    ).count()
    
    # 직원별 통계 (최근 3개월)
    users = db.query(User).filter(User.is_admin == False).all()
    user_stats = []
    
    for user in users:
        total = db.query(TaskAssignment).filter(
            TaskAssignment.assignee_id == user.id,
            TaskAssignment.created_at >= three_months_ago
        ).count()
        
        completed_count = db.query(TaskAssignment).filter(
            TaskAssignment.assignee_id == user.id,
            TaskAssignment.status == 'completed',
            TaskAssignment.created_at >= three_months_ago
        ).count()
        
        delayed = db.query(TaskAssignment).filter(
            TaskAssignment.assignee_id == user.id,
            TaskAssignment.deadline < datetime.now(),
            TaskAssignment.status.in_(['new', 'confirmed', 'in_progress'])
        ).count()
        
        completion_rate = round((completed_count / total * 100), 1) if total > 0 else 0
        
        user_stats.append({
            'username': user.username,
            'total': total,
            'completed': completed_count,
            'delayed': delayed,
            'completion_rate': completion_rate
        })
    
    # 미처리 업무 목록 (최신순 20개)
    pending_tasks = db.query(TaskAssignment).options(
        joinedload(TaskAssignment.creator),
        joinedload(TaskAssignment.assignee)
    ).filter(
        TaskAssignment.status.in_(['new', 'confirmed', 'in_progress'])
    ).order_by(TaskAssignment.created_at.desc()).limit(20).all()
    
    return templates.TemplateResponse("tasks/dashboard.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "stats": {
            'total': total_tasks,
            'new': new_tasks,
            'in_progress': in_progress,
            'completed': completed,
            'today_deadline': today_deadline,
            'delayed': delayed_tasks
        },
        "user_stats": user_stats,
        "pending_tasks": pending_tasks
    })

# ============================================
# 업무 지시 생성/수정/삭제
# ============================================

@router.get("/create", response_class=HTMLResponse)
async def create_task_page(request: Request, db: Session = Depends(get_db)):
    """업무 지시 생성 페이지"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    is_admin = request.session.get("is_admin", False)
    
    # 담당자 목록 (대표는 제외하고, 지시자 본인도 제외)
    if is_admin:
        # 대표는 모든 직원에게 지시 가능
        assignees = db.query(User).filter(User.is_admin == False).all()
    else:
        # 일반 직원은 다른 직원에게만 지시 가능 (대표, 본인 제외)
        assignees = db.query(User).filter(
            User.is_admin == False,
            User.id != current_user.id
        ).all()
    
    return templates.TemplateResponse("tasks/create_task.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "assignees": assignees
    })


@router.post("/create", response_class=RedirectResponse)
async def create_task(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    assignee_ids: str = Form(...),  # 쉼표로 구분된 ID들
    priority: str = Form("normal"),
    deadline_type: str = Form(None),
    custom_deadline: str = Form(None),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """업무 지시 생성"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    
    # 담당자 ID 리스트 파싱
    assignee_id_list = [int(id.strip()) for id in assignee_ids.split(',') if id.strip()]
    
    # 마감 시간 계산
    deadline = None
    if deadline_type == "custom" and custom_deadline:
        deadline = datetime.fromisoformat(custom_deadline)
    elif deadline_type == "2hours":
        deadline = datetime.now() + timedelta(hours=2)
    elif deadline_type == "today":
        deadline = datetime.now().replace(hour=18, minute=0, second=0)
    elif deadline_type == "this_week":
        days_until_friday = (4 - datetime.now().weekday()) % 7
        deadline = (datetime.now() + timedelta(days=days_until_friday)).replace(hour=18, minute=0)
    
    # 일괄 지시 여부
    is_batch = len(assignee_id_list) > 1
    batch_group_id = str(uuid.uuid4()) if is_batch else None
    
    # 각 담당자에게 업무 생성
    for assignee_id in assignee_id_list:
        new_task = TaskAssignment(
            title=title,
            content=content,
            creator_id=current_user.id,
            assignee_id=assignee_id,
            priority=priority,
            deadline_type=deadline_type,
            deadline=deadline,
            status='new',
            is_batch=is_batch,
            batch_group_id=batch_group_id
        )
        db.add(new_task)
        db.flush()  # ID 생성
        
        # 파일 업로드 처리
        if files:
            for file in files:
                if file.filename:
                    # 파일명 중복 방지
                    file_ext = os.path.splitext(file.filename)[1]
                    unique_filename = f"{uuid.uuid4()}{file_ext}"
                    filepath = os.path.join(UPLOAD_DIR, unique_filename)
                    
                    # 파일 저장
                    with open(filepath, "wb") as f:
                        f.write(await file.read())
                    
                    task_file = TaskFile(
                        task_id=new_task.id,
                        filename=file.filename,
                        filepath=filepath,
                        filesize=os.path.getsize(filepath),
                        uploaded_by=current_user.id
                    )
                    db.add(task_file)
        
        # 알림 생성
        notification = TaskNotification(
            task_id=new_task.id,
            user_id=assignee_id,
            notification_type='new_task',
            message=f"새 업무: {title}",
            auto_delete_at=datetime.now() + timedelta(days=90)
        )
        db.add(notification)
    
    db.commit()
    
    for assignee_id in assignee_id_list:
        try:
            await manager.send_personal_message({
                'type': 'new_task',
                'task_id': new_task.id,
                'message': f"새 업무가 할당되었습니다: {title}",
                'priority': priority,
                'timestamp': datetime.now().isoformat()
            }, assignee_id)
        except Exception as e:
            print(f"WebSocket 전송 오류: {e}")
    
    return RedirectResponse("/tasks", status_code=303)

@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail(task_id: int, request: Request, db: Session = Depends(get_db)):
    """업무 지시 상세보기"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    is_admin = request.session.get("is_admin", False)
    
    task = db.query(TaskAssignment).options(
        joinedload(TaskAssignment.creator),
        joinedload(TaskAssignment.assignee),
        joinedload(TaskAssignment.comments).joinedload(TaskComment.user),
        joinedload(TaskAssignment.files)
    ).filter(TaskAssignment.id == task_id).first()
    
    if not task:
        return RedirectResponse("/tasks", status_code=302)
    
    # 권한 확인 (담당자, 지시자, 관리자만 볼 수 있음)
    if not is_admin and task.assignee_id != current_user.id and task.creator_id != current_user.id:
        return RedirectResponse("/tasks", status_code=302)
    
    # 읽음 처리 (담당자가 처음 열었을 때)
    if not task.is_read and task.assignee_id == current_user.id:
        task.is_read = True
        task.read_at = datetime.now()
        db.commit()
    
    return templates.TemplateResponse("tasks/task_detail.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "task": task,
        "current_user_id": current_user.id
    })


# ============================================
# 상태 변경
# ============================================

@router.post("/{task_id}/status", response_class=RedirectResponse)
async def update_task_status(
    task_id: int,
    request: Request,
    status: str = Form(...),
    estimated_time: str = Form(None),
    completion_note: str = Form(None),
    hold_reason: str = Form(None),
    hold_resume_date: str = Form(None),
    db: Session = Depends(get_db)
):
    """업무 상태 변경"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    task = db.query(TaskAssignment).filter(TaskAssignment.id == task_id).first()
    
    if not task or task.assignee_id != current_user.id:
        return RedirectResponse("/tasks", status_code=302)
    
    # 상태 변경
    task.status = status
    task.updated_at = datetime.now()
    
    if status == 'confirmed':
        pass  # 확인함
    elif status == 'in_progress':
        if estimated_time:
            task.estimated_completion_time = datetime.fromisoformat(estimated_time)
    elif status == 'completed':
        if completion_note:
            task.completion_note = completion_note
        task.completed_at = datetime.now()
    elif status == 'on_hold':
        if hold_reason:
            task.hold_reason = hold_reason
        if hold_resume_date:
            task.hold_resume_date = datetime.fromisoformat(hold_resume_date).date()
    
    # 지시자에게 알림 생성
    if task.creator_id:
        notification = TaskNotification(
            task_id=task.id,
            user_id=task.creator_id,
            notification_type='status_change',
            message=f"업무 상태 변경: {task.title} → {status}",
            auto_delete_at=datetime.now() + timedelta(days=90)
        )
        db.add(notification)
    
    db.commit()
    
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/cancel", response_class=RedirectResponse)
async def cancel_task(
    task_id: int,
    request: Request,
    cancel_reason: str = Form(...),
    db: Session = Depends(get_db)
):
    """업무 취소 (지시자 또는 관리자만)"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    is_admin = request.session.get("is_admin", False)
    task = db.query(TaskAssignment).filter(TaskAssignment.id == task_id).first()
    
    if not task:
        return RedirectResponse("/tasks", status_code=302)
    
    # 권한 확인 (지시자 또는 관리자만)
    if not is_admin and task.creator_id != current_user.id:
        return RedirectResponse(f"/tasks/{task_id}", status_code=302)
    
    task.status = 'cancelled'
    task.cancel_reason = cancel_reason
    task.updated_at = datetime.now()
    
    # 담당자에게 알림
    if task.assignee_id:
        notification = TaskNotification(
            task_id=task.id,
            user_id=task.assignee_id,
            notification_type='status_change',
            message=f"업무 취소: {task.title}",
            auto_delete_at=datetime.now() + timedelta(days=90)
        )
        db.add(notification)
    
    db.commit()
    
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


# ============================================
# 댓글 시스템
# ============================================

@router.post("/{task_id}/comment", response_class=RedirectResponse)
async def add_comment(
    task_id: int,
    request: Request,
    content: str = Form(...),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """댓글 추가"""
    username = check_session(request)
    if not username:
        return RedirectResponse("/login", status_code=302)
    
    current_user = db.query(User).filter(User.username == username).first()
    task = db.query(TaskAssignment).filter(TaskAssignment.id == task_id).first()
    
    if not task:
        return RedirectResponse("/tasks", status_code=302)
    
    # 댓글 추가
    comment = TaskComment(
        task_id=task_id,
        user_id=current_user.id,
        content=content
    )
    db.add(comment)
    db.flush()
    
    # 파일 첨부 처리
    if files:
        for file in files:
            if file.filename:
                file_ext = os.path.splitext(file.filename)[1]
                unique_filename = f"{uuid.uuid4()}{file_ext}"
                filepath = os.path.join(UPLOAD_DIR, unique_filename)
                
                with open(filepath, "wb") as f:
                    f.write(await file.read())
                
                task_file = TaskFile(
                    comment_id=comment.id,
                    filename=file.filename,
                    filepath=filepath,
                    filesize=os.path.getsize(filepath),
                    uploaded_by=current_user.id
                )
                db.add(task_file)
    
    # 상대방에게 알림 (담당자가 댓글 → 지시자에게, 지시자가 댓글 → 담당자에게)
    recipient_id = None
    if current_user.id == task.assignee_id:
        recipient_id = task.creator_id  # 담당자가 댓글 → 지시자에게
    elif current_user.id == task.creator_id:
        recipient_id = task.assignee_id  # 지시자가 댓글 → 담당자에게
    
    if recipient_id:
        notification = TaskNotification(
            task_id=task.id,
            user_id=recipient_id,
            notification_type='comment',
            message=f"새 댓글: {task.title}",
            auto_delete_at=datetime.now() + timedelta(days=90)
        )
        db.add(notification)
    
    db.commit()
    
    if recipient_id:
        try:
            await manager.send_personal_message({
                'type': 'new_comment',
                'task_id': task.id,
                'message': f"새 댓글이 달렸습니다: {task.title}",
                'timestamp': datetime.now().isoformat()
            }, recipient_id)
        except Exception as e:
            print(f"WebSocket 전송 오류: {e}")
    
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


# ============================================
# 알림 관련
# ============================================

@router.get("/notifications/unread")
def get_unread_notifications(request: Request, db: Session = Depends(get_db)):
    """읽지 않은 알림 목록 조회"""
    username = request.session.get("user")
    if not username:
        return []
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user:
        return []
    
    # 읽지 않은 알림 조회
    notifications = db.query(TaskNotification).options(
        joinedload(TaskNotification.task)
    ).filter(
        TaskNotification.user_id == current_user.id,
        TaskNotification.is_read == False
    ).order_by(
        TaskNotification.created_at.desc()
    ).all()
    
    # JSON 직렬화 가능한 형태로 변환
    result = []
    for notif in notifications:
        # 업무 우선순위 가져오기
        priority = 'normal'
        if notif.task:
            priority = notif.task.priority
        
        result.append({
            "id": notif.id,
            "task_id": notif.task_id,
            "notification_type": notif.notification_type,
            "message": notif.message,
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat(),
            "priority": priority  # ⭐ 우선순위 추가
        })
    
    return result

@router.post("/notifications/{notif_id}/read", response_class=JSONResponse)
async def mark_notification_read(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """알림 읽음 처리 (API)"""
    username = check_session(request)
    if not username:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    current_user = db.query(User).filter(User.username == username).first()
    
    notification = db.query(TaskNotification).filter(
        TaskNotification.id == notif_id,
        TaskNotification.user_id == current_user.id
    ).first()
    
    if notification:
        notification.is_read = True
        notification.read_at = datetime.now()
        db.commit()
        return JSONResponse({"success": True})
    
    return JSONResponse({"error": "Not found"}, status_code=404)

@router.get("/get-current-user-id")
def get_current_user_id(request: Request, db: Session = Depends(get_db)):
    """현재 로그인한 사용자 ID 반환 (WebSocket 연결용)"""
    username = request.session.get("user")
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    return {"user_id": current_user.id}


@router.post("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """알림을 읽음 처리"""
    username = request.session.get("user")
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    # 알림 조회
    notification = db.query(TaskNotification).filter(
        TaskNotification.id == notification_id,
        TaskNotification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
    
    # 읽음 처리
    notification.is_read = True
    notification.read_at = datetime.now()
    
    db.commit()
    
    return {"success": True, "message": "알림을 읽음 처리했습니다"}


@router.get("/notifications/all")
def get_all_notifications(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 50
):
    """모든 알림 조회 (읽은 알림 포함)"""
    username = request.session.get("user")
    if not username:
        return []
    
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user:
        return []
    
    notifications = db.query(TaskNotification).options(
        joinedload(TaskNotification.task)
    ).filter(
        TaskNotification.user_id == current_user.id
    ).order_by(
        TaskNotification.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for notif in notifications:
        # 업무 우선순위 가져오기
        priority = 'normal'
        if notif.task:
            priority = notif.task.priority
        
        result.append({
            "id": notif.id,
            "task_id": notif.task_id,
            "notification_type": notif.notification_type,
            "message": notif.message,
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat(),
            "read_at": notif.read_at.isoformat() if notif.read_at else None,
            "priority": priority
        })
    
    return result