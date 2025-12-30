# routers/automation.py
# 네이버 카페 자동화 시스템

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func, and_
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
import json
import asyncio

# Claude API (선택적 import)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️  anthropic 모듈이 없습니다. AI 모드는 비활성화됩니다.")
    print("   설치: pip install anthropic")

from database import (
    get_db, get_kst_now,
    AutomationWorkerPC, AutomationAccount, AutomationCafe,
    AutomationPrompt, AutomationSchedule, AutomationTask,
    AutomationPost, AutomationComment, MarketingProduct, Product,
    MarketingPost, User
)

router = APIRouter(prefix="/automation", tags=["automation"])
templates = Jinja2Templates(directory="templates")

# ===== WebSocket 연결 관리 =====
worker_connections: Dict[int, WebSocket] = {}  # {pc_number: websocket}


# ============================================
# WebSocket 엔드포인트 (Worker PC 연결)
# ============================================

@router.websocket("/ws/worker/{pc_number}")
async def worker_websocket(websocket: WebSocket, pc_number: int, db: Session = Depends(get_db)):
    """Worker PC WebSocket 연결"""
    await websocket.accept()
    worker_connections[pc_number] = websocket
    
    print(f"✅ Worker PC #{pc_number} 연결됨")
    
    # PC 상태 업데이트
    pc = db.query(AutomationWorkerPC).filter(
        AutomationWorkerPC.pc_number == pc_number
    ).first()
    
    if pc:
        pc.status = 'online'
        pc.last_heartbeat = get_kst_now()
        db.commit()
    else:
        # PC 정보 자동 등록
        pc = AutomationWorkerPC(
            pc_number=pc_number,
            pc_name=f"Worker PC #{pc_number}",
            ip_address="Unknown",
            status='online'
        )
        db.add(pc)
        db.commit()
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message['type'] == 'heartbeat':
                # Heartbeat 처리
                pc.cpu_usage = message.get('cpu_usage')
                pc.memory_usage = message.get('memory_usage')
                pc.ip_address = message.get('ip_address', pc.ip_address)
                pc.last_heartbeat = get_kst_now()
                db.commit()
                
            elif message['type'] == 'task_started':
                # 작업 시작
                task = db.query(AutomationTask).get(message['task_id'])
                if task:
                    task.status = 'in_progress'
                    task.started_at = get_kst_now()
                    pc.status = 'busy'
                    pc.current_task_id = task.id
                    db.commit()
                    
            elif message['type'] == 'task_completed':
                # 작업 완료
                task = db.query(AutomationTask).get(message['task_id'])
                if task:
                    task.status = 'completed'
                    task.completed_at = get_kst_now()
                    task.post_url = message.get('post_url')
                    
                    # 작성된 글/댓글 저장
                    if task.task_type == 'post':
                        post = AutomationPost(
                            mode=task.mode,
                            title=task.title,
                            content=task.content,
                            post_url=task.post_url,
                            account_id=task.assigned_account_id,
                            cafe_id=task.cafe_id,
                            marketing_product_id=task.schedule.marketing_product_id if task.schedule else None,
                            keyword_text=task.schedule.keyword_text if task.schedule else None
                        )
                        db.add(post)
                    elif task.task_type in ['comment', 'reply']:
                        parent_post_id = None
                        if task.parent_task and task.parent_task.task_type == 'post':
                            # 본문 글에 대한 댓글
                            parent_post = db.query(AutomationPost).filter(
                                AutomationPost.post_url == task.parent_task.post_url
                            ).first()
                            if parent_post:
                                parent_post_id = parent_post.id
                        
                        if parent_post_id:
                            comment = AutomationComment(
                                mode=task.mode,
                                post_id=parent_post_id,
                                content=task.content,
                                account_id=task.assigned_account_id,
                                order_sequence=task.order_sequence
                            )
                            db.add(comment)
                    
                    pc.status = 'online'
                    pc.current_task_id = None
                    db.commit()
                    
                    # 다음 작업 할당
                    await assign_next_task(pc_number, db, websocket)
                    
            elif message['type'] == 'task_failed':
                # 작업 실패
                task = db.query(AutomationTask).get(message['task_id'])
                if task:
                    task.status = 'failed'
                    task.error_message = message.get('error')
                    task.retry_count += 1
                    pc.status = 'online'
                    pc.current_task_id = None
                    db.commit()
                    
    except WebSocketDisconnect:
        print(f"❌ Worker PC #{pc_number} 연결 해제")
        worker_connections.pop(pc_number, None)
        if pc:
            pc.status = 'offline'
            pc.current_task_id = None
            db.commit()


async def assign_next_task(pc_number: int, db: Session, websocket: WebSocket):
    """다음 작업 할당"""
    # PC 정보
    pc = db.query(AutomationWorkerPC).filter(
        AutomationWorkerPC.pc_number == pc_number
    ).first()
    
    if not pc:
        return
    
    # 대기 중인 작업 찾기 (우선순위 높은 순, 예정 시간 빠른 순)
    pending_task = db.query(AutomationTask).filter(
        AutomationTask.status == 'pending',
        AutomationTask.assigned_pc_id == None
    ).order_by(
        AutomationTask.priority.desc(),
        AutomationTask.scheduled_time.asc()
    ).first()
    
    if pending_task:
        # 계정 할당 (PC에 할당된 계정 중 사용 가능한 것)
        available_account = db.query(AutomationAccount).filter(
            AutomationAccount.assigned_pc_id == pc.id,
            AutomationAccount.status == 'active'
        ).first()
        
        if not available_account:
            print(f"⚠️ PC #{pc_number}에 사용 가능한 계정이 없습니다")
            return
        
        # 카페 정보
        cafe = db.query(AutomationCafe).get(pending_task.cafe_id)
        
        # 작업 할당
        pending_task.assigned_pc_id = pc.id
        pending_task.assigned_account_id = available_account.id
        pending_task.status = 'assigned'
        db.commit()
        
        # Worker에게 작업 전송
        task_data = {
            'type': 'new_task',
            'task': {
                'id': pending_task.id,
                'task_type': pending_task.task_type,
                'title': pending_task.title,
                'content': pending_task.content,
                'cafe_url': cafe.url if cafe else None,
                'post_url': pending_task.parent_task.post_url if pending_task.parent_task_id else None,
                'account_id': available_account.account_id,
                'account_pw': available_account.account_pw
            }
        }
        
        await websocket.send_json(task_data)
        print(f"📤 작업 할당: Task #{pending_task.id} → PC #{pc_number}")


# ============================================
# 대시보드 페이지
# ============================================

@router.get("/cafe", response_class=HTMLResponse)
async def automation_dashboard(request: Request, db: Session = Depends(get_db)):
    """자동화 대시보드"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login")
    
    is_admin = request.session.get("is_admin", False)


@router.get("/stats", response_class=HTMLResponse)
async def automation_stats(request: Request):
    """통계 분석 페이지"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login")
    
    is_admin = request.session.get("is_admin", False)
    
    return templates.TemplateResponse("automation_stats.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin
    })
    
    # PC 상태
    pcs = db.query(AutomationWorkerPC).all()
    
    # 작업 대기 목록
    pending_tasks = db.query(AutomationTask).filter(
        AutomationTask.status.in_(['pending', 'assigned'])
    ).order_by(AutomationTask.priority.desc(), AutomationTask.scheduled_time.asc()).limit(20).all()
    
    # 진행 중인 작업
    in_progress_tasks = db.query(AutomationTask).filter(
        AutomationTask.status == 'in_progress'
    ).all()
    
    # 완료된 작업 (오늘)
    completed_tasks_today = db.query(AutomationTask).filter(
        AutomationTask.status == 'completed',
        func.date(AutomationTask.completed_at) == date.today()
    ).all()
    
    # 통계
    stats = {
        'total_pcs': len(pcs),
        'online_pcs': len([pc for pc in pcs if pc.status == 'online']),
        'busy_pcs': len([pc for pc in pcs if pc.status == 'busy']),
        'pending_tasks': len(pending_tasks),
        'in_progress_tasks': len(in_progress_tasks),
        'completed_today': len(completed_tasks_today),
        'failed_today': db.query(AutomationTask).filter(
            AutomationTask.status == 'failed',
            func.date(AutomationTask.updated_at) == date.today()
        ).count()
    }
    
    return templates.TemplateResponse("automation_dashboard.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin,
        "pcs": pcs,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "completed_tasks_today": completed_tasks_today,
        "stats": stats
    })


# ============================================
# AI 콘텐츠 생성 (Claude API)
# ============================================

@router.post("/api/generate-content")
async def generate_ai_content(
    prompt_id: int = Form(...),
    product_id: int = Form(...),
    keyword: str = Form(...),
    db: Session = Depends(get_db)
):
    """Claude API로 글/댓글 생성"""
    
    # anthropic 모듈 확인
    if not ANTHROPIC_AVAILABLE:
        return JSONResponse({
            'success': False,
            'message': 'anthropic 모듈이 설치되지 않았습니다. pip install anthropic'
        }, status_code=500)
    
    prompt = db.query(AutomationPrompt).get(prompt_id)
    product = db.query(MarketingProduct).options(joinedload(MarketingProduct.product)).get(product_id)
    
    if not prompt or not product:
        return JSONResponse({'success': False, 'message': '데이터를 찾을 수 없습니다'}, status_code=404)
    
    try:
        # Claude API 호출
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return JSONResponse({
                'success': False,
                'message': 'ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다'
            }, status_code=500)
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # 프롬프트 템플릿에 데이터 삽입
        user_prompt = prompt.user_prompt_template.format(
            product_name=product.product.name if product.product else "상품명",
            keyword=keyword
        )
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
            system=prompt.system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        generated_content = message.content[0].text
        
        return JSONResponse({
            'success': True,
            'content': generated_content
        })
        
    except Exception as e:
        return JSONResponse({
            'success': False,
            'message': f'AI 생성 오류: {str(e)}'
        }, status_code=500)


# ============================================
# 스케줄 관리 API
# ============================================

@router.post("/api/schedules/create-auto")
async def create_auto_schedules(
    product_id: int = Form(...),
    daily_count: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    mode: str = Form(...),  # human or ai
    prompt_id: Optional[int] = Form(None),  # AI 모드용
    db: Session = Depends(get_db)
):
    """스케줄 자동 생성"""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        product = db.query(MarketingProduct).get(product_id)
        if not product:
            return JSONResponse({'success': False, 'message': '상품을 찾을 수 없습니다'})
        
        keywords = json.loads(product.keywords) if product.keywords else []
        if not keywords:
            return JSONResponse({'success': False, 'message': '키워드가 없습니다'})
        
        current_date = start
        keyword_index = 0
        created_count = 0
        
        while current_date <= end:
            # AI 모드는 주말도 포함, 휴먼 모드는 평일만
            include_day = (mode == 'ai') or (current_date.weekday() < 5)
            
            if include_day:
                for _ in range(daily_count):
                    if keyword_index >= len(keywords):
                        keyword_index = 0
                    
                    schedule = AutomationSchedule(
                        mode=mode,
                        scheduled_date=current_date,
                        marketing_product_id=product_id,
                        keyword_text=keywords[keyword_index],
                        prompt_id=prompt_id if mode == 'ai' else None,
                        status='pending'
                    )
                    db.add(schedule)
                    created_count += 1
                    keyword_index += 1
            
            current_date += timedelta(days=1)
        
        db.commit()
        
        return JSONResponse({
            'success': True,
            'message': f'스케줄 {created_count}개가 생성되었습니다'
        })
        
    except Exception as e:
        db.rollback()
        return JSONResponse({
            'success': False,
            'message': f'오류: {str(e)}'
        }, status_code=500)


# ============================================
# 작업 생성 (휴먼 모드)
# ============================================

@router.post("/api/tasks/create-from-post")
async def create_tasks_from_post(
    schedule_id: int = Form(...),
    post_id: int = Form(...),  # MarketingPost ID
    cafe_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """휴먼 모드: 기존 작성된 글을 자동화 작업으로 전환"""
    try:
        schedule = db.query(AutomationSchedule).get(schedule_id)
        post = db.query(MarketingPost).get(post_id)
        cafe = db.query(AutomationCafe).get(cafe_id)
        
        if not all([schedule, post, cafe]):
            return JSONResponse({'success': False, 'message': '데이터를 찾을 수 없습니다'})
        
        # 본문 글 작업 생성
        post_task = AutomationTask(
            task_type='post',
            mode='human',
            schedule_id=schedule_id,
            scheduled_time=datetime.combine(schedule.scheduled_date, datetime.min.time()),
            title=post.post_title,
            content=post.post_body,
            cafe_id=cafe_id,
            status='pending',
            priority=0
        )
        db.add(post_task)
        db.flush()  # ID 생성
        
        # 댓글 작업 생성
        if post.post_comments:
            comments = json.loads(post.post_comments) if isinstance(post.post_comments, str) else post.post_comments
            
            for idx, comment in enumerate(comments):
                comment_task = AutomationTask(
                    task_type='comment',
                    mode='human',
                    schedule_id=schedule_id,
                    scheduled_time=datetime.combine(schedule.scheduled_date, datetime.min.time()) + timedelta(minutes=idx*2),
                    content=comment['text'],
                    parent_task_id=post_task.id,
                    order_sequence=idx,
                    cafe_id=cafe_id,
                    status='pending',
                    priority=0
                )
                db.add(comment_task)
        
        schedule.status = 'processing'
        db.commit()
        
        return JSONResponse({
            'success': True,
            'message': '작업이 생성되었습니다'
        })
        
    except Exception as e:
        db.rollback()
        return JSONResponse({
            'success': False,
            'message': f'오류: {str(e)}'
        }, status_code=500)


# ============================================
# PC 관리 API
# ============================================

@router.post("/api/pcs/register")
async def register_pc(
    pc_number: int = Form(...),
    pc_name: str = Form(...),
    ip_address: str = Form(...),
    db: Session = Depends(get_db)
):
    """PC 등록"""
    existing = db.query(AutomationWorkerPC).filter(
        AutomationWorkerPC.pc_number == pc_number
    ).first()
    
    if existing:
        return JSONResponse({'success': False, 'message': '이미 등록된 PC 번호입니다'})
    
    pc = AutomationWorkerPC(
        pc_number=pc_number,
        pc_name=pc_name,
        ip_address=ip_address,
        status='offline'
    )
    db.add(pc)
    db.commit()
    
    return JSONResponse({'success': True, 'message': 'PC가 등록되었습니다'})


@router.post("/api/accounts/assign-to-pc")
async def assign_account_to_pc(
    account_id: int = Form(...),
    pc_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """계정을 PC에 할당"""
    account = db.query(AutomationAccount).get(account_id)
    if not account:
        return JSONResponse({'success': False, 'message': '계정을 찾을 수 없습니다'})
    
    account.assigned_pc_id = pc_id
    db.commit()
    
    return JSONResponse({'success': True, 'message': '계정이 할당되었습니다'})


# ============================================
# 통계 및 분석 API
# ============================================

@router.get("/api/stats/overview")
async def get_stats_overview(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """전체 통계 개요"""
    from datetime import datetime, timedelta
    
    # 기간 설정
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
    else:
        start = datetime.now() - timedelta(days=30)  # 최근 30일
    
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end = datetime.now()
    
    # 1. PC 통계
    total_pcs = db.query(AutomationWorkerPC).count()
    online_pcs = db.query(AutomationWorkerPC).filter(
        AutomationWorkerPC.status == 'online'
    ).count()
    
    # 2. 작업 통계
    total_tasks = db.query(AutomationTask).filter(
        AutomationTask.created_at.between(start, end)
    ).count()
    
    completed_tasks = db.query(AutomationTask).filter(
        AutomationTask.status == 'completed',
        AutomationTask.completed_at.between(start, end)
    ).count()
    
    failed_tasks = db.query(AutomationTask).filter(
        AutomationTask.status == 'failed',
        AutomationTask.updated_at.between(start, end)
    ).count()
    
    # 3. 모드별 통계
    human_tasks = db.query(AutomationTask).filter(
        AutomationTask.mode == 'human',
        AutomationTask.status == 'completed',
        AutomationTask.completed_at.between(start, end)
    ).count()
    
    ai_tasks = db.query(AutomationTask).filter(
        AutomationTask.mode == 'ai',
        AutomationTask.status == 'completed',
        AutomationTask.completed_at.between(start, end)
    ).count()
    
    # 4. 작업 유형별 통계
    post_count = db.query(AutomationTask).filter(
        AutomationTask.task_type == 'post',
        AutomationTask.status == 'completed',
        AutomationTask.completed_at.between(start, end)
    ).count()
    
    comment_count = db.query(AutomationTask).filter(
        AutomationTask.task_type.in_(['comment', 'reply']),
        AutomationTask.status == 'completed',
        AutomationTask.completed_at.between(start, end)
    ).count()
    
    # 5. 성공률
    success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # 6. 평균 처리 시간
    avg_processing_time = db.query(
        func.avg(
            func.extract('epoch', AutomationTask.completed_at - AutomationTask.started_at)
        )
    ).filter(
        AutomationTask.status == 'completed',
        AutomationTask.completed_at.between(start, end)
    ).scalar() or 0
    
    return JSONResponse({
        'success': True,
        'period': {
            'start': start.strftime('%Y-%m-%d'),
            'end': end.strftime('%Y-%m-%d')
        },
        'pc_stats': {
            'total': total_pcs,
            'online': online_pcs,
            'online_rate': (online_pcs / total_pcs * 100) if total_pcs > 0 else 0
        },
        'task_stats': {
            'total': total_tasks,
            'completed': completed_tasks,
            'failed': failed_tasks,
            'pending': total_tasks - completed_tasks - failed_tasks,
            'success_rate': round(success_rate, 2)
        },
        'mode_stats': {
            'human': human_tasks,
            'ai': ai_tasks
        },
        'type_stats': {
            'posts': post_count,
            'comments': comment_count
        },
        'performance': {
            'avg_processing_time_seconds': round(avg_processing_time, 2)
        }
    })


@router.get("/api/stats/daily")
async def get_daily_stats(
    days: int = Query(7, description="최근 N일"),
    db: Session = Depends(get_db)
):
    """일별 통계"""
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    daily_data = []
    
    for i in range(days):
        day = start_date + timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        completed = db.query(AutomationTask).filter(
            AutomationTask.status == 'completed',
            AutomationTask.completed_at.between(day_start, day_end)
        ).count()
        
        failed = db.query(AutomationTask).filter(
            AutomationTask.status == 'failed',
            AutomationTask.updated_at.between(day_start, day_end)
        ).count()
        
        daily_data.append({
            'date': day.strftime('%Y-%m-%d'),
            'completed': completed,
            'failed': failed,
            'total': completed + failed
        })
    
    return JSONResponse({
        'success': True,
        'daily_stats': daily_data
    })


@router.get("/api/stats/pc-performance")
async def get_pc_performance(db: Session = Depends(get_db)):
    """PC별 성능 통계"""
    from datetime import datetime, timedelta
    
    pcs = db.query(AutomationWorkerPC).all()
    
    pc_stats = []
    
    for pc in pcs:
        # 최근 24시간 작업 통계
        yesterday = datetime.now() - timedelta(hours=24)
        
        completed = db.query(AutomationTask).filter(
            AutomationTask.assigned_pc_id == pc.id,
            AutomationTask.status == 'completed',
            AutomationTask.completed_at >= yesterday
        ).count()
        
        failed = db.query(AutomationTask).filter(
            AutomationTask.assigned_pc_id == pc.id,
            AutomationTask.status == 'failed',
            AutomationTask.updated_at >= yesterday
        ).count()
        
        # 평균 처리 시간
        avg_time = db.query(
            func.avg(
                func.extract('epoch', AutomationTask.completed_at - AutomationTask.started_at)
            )
        ).filter(
            AutomationTask.assigned_pc_id == pc.id,
            AutomationTask.status == 'completed',
            AutomationTask.completed_at >= yesterday
        ).scalar() or 0
        
        pc_stats.append({
            'pc_number': pc.pc_number,
            'pc_name': pc.pc_name,
            'status': pc.status,
            'ip_address': pc.ip_address,
            'completed_24h': completed,
            'failed_24h': failed,
            'success_rate': (completed / (completed + failed) * 100) if (completed + failed) > 0 else 0,
            'avg_processing_time': round(avg_time, 2),
            'cpu_usage': pc.cpu_usage,
            'memory_usage': pc.memory_usage
        })
    
    return JSONResponse({
        'success': True,
        'pc_performance': pc_stats
    })


@router.get("/api/stats/account-usage")
async def get_account_usage(db: Session = Depends(get_db)):
    """계정별 사용 통계"""
    from datetime import datetime, timedelta
    
    accounts = db.query(AutomationAccount).all()
    
    account_stats = []
    
    for account in accounts:
        # 최근 30일 작업
        month_ago = datetime.now() - timedelta(days=30)
        
        posts = db.query(AutomationTask).filter(
            AutomationTask.assigned_account_id == account.id,
            AutomationTask.task_type == 'post',
            AutomationTask.status == 'completed',
            AutomationTask.completed_at >= month_ago
        ).count()
        
        comments = db.query(AutomationTask).filter(
            AutomationTask.assigned_account_id == account.id,
            AutomationTask.task_type.in_(['comment', 'reply']),
            AutomationTask.status == 'completed',
            AutomationTask.completed_at >= month_ago
        ).count()
        
        account_stats.append({
            'account_id': account.account_id,
            'status': account.status,
            'assigned_pc': account.assigned_pc.pc_name if account.assigned_pc else None,
            'posts_30d': posts,
            'comments_30d': comments,
            'total_posts': account.total_posts,
            'total_comments': account.total_comments,
            'last_used': account.last_used_at.strftime('%Y-%m-%d %H:%M') if account.last_used_at else None
        })
    
    return JSONResponse({
        'success': True,
        'account_usage': account_stats
    })

