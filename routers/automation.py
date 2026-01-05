# routers/automation.py
# 네이버 카페 자동화 시스템

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, Form, HTTPException, Query
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
    MarketingPost, User  # CommentScript 임시 제거
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
    from database import get_kst_now  # ⭐ 맨 위로 이동!
    
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
            status='online',
            last_heartbeat=get_kst_now()
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
                pc.last_heartbeat = get_kst_now()  # KST 시간으로 저장
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
                        cafe_comment_id = message.get('cafe_comment_id')  # ⭐ 카페 댓글 ID
                        
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
                            db.flush()  # ID 생성
                            
                            # ⭐ 카페 댓글 ID 저장 (있으면)
                            if cafe_comment_id:
                                # AutomationComment에 cafe_comment_id 필드가 필요
                                # 임시로 task에 저장
                                task.error_message = f"cafe_comment_id:{cafe_comment_id}"
                                print(f"  📌 카페 댓글 ID 저장: {cafe_comment_id}")
                        
                        # 댓글 원고 완료 처리 (임시 비활성화)
                        # comment_script = db.query(CommentScript).filter(
                        #     CommentScript.generated_task_id == task.id
                        # ).first()
                        
                        comment_script = None  # 임시
                        if False and comment_script:
                            comment_script.status = 'completed'
                            comment_script.completed_at = get_kst_now()
                            
                            # 다음 댓글 스크립트 찾기 (순차 실행)
                            next_script = db.query(CommentScript).filter(
                                CommentScript.post_task_id == comment_script.post_task_id,
                                CommentScript.status == 'task_created'
                            ).order_by(
                                CommentScript.group_number,
                                CommentScript.sequence_number
                            ).first()
                            
                            if next_script and next_script.generated_task_id:
                                next_task = db.query(AutomationTask).get(next_script.generated_task_id)
                                if next_task and next_task.assigned_pc_id in worker_connections:
                                    # ⭐ 부모 댓글 ID 찾기
                                    parent_cafe_comment_id = None
                                    
                                    # 대댓글이면 부모 그룹의 첫 댓글 ID 찾기
                                    if not next_script.is_new_comment and next_script.parent_group:
                                        parent_script = db.query(CommentScript).filter(
                                            CommentScript.post_task_id == comment_script.post_task_id,
                                            CommentScript.group_number == next_script.parent_group,
                                            CommentScript.sequence_number == 1,
                                            CommentScript.status == 'completed'
                                        ).first()
                                        
                                        if parent_script and parent_script.generated_task_id:
                                            parent_task = db.query(AutomationTask).get(parent_script.generated_task_id)
                                            if parent_task and parent_task.error_message:
                                                # error_message에서 cafe_comment_id 추출
                                                if 'cafe_comment_id:' in parent_task.error_message:
                                                    parent_cafe_comment_id = parent_task.error_message.split('cafe_comment_id:')[1]
                                                    print(f"  📌 부모 댓글 ID 발견: {parent_cafe_comment_id}")
                                    
                                    # 다음 댓글 작성 PC에게 시작 신호
                                    try:
                                        await worker_connections[next_task.assigned_pc_id].send_json({
                                            'type': 'new_task',
                                            'task': {
                                                'id': next_task.id,
                                                'task_type': next_task.task_type,
                                                'content': next_task.content,
                                                'post_url': task.post_url,  # 같은 글
                                                'account_id': next_task.assigned_account.account_id if next_task.assigned_account else None,
                                                'account_pw': next_task.assigned_account.account_pw if next_task.assigned_account else None,
                                                'parent_comment_id': parent_cafe_comment_id  # ⭐ 카페 댓글 ID 전달
                                            }
                                        })
                                        print(f"✅ 다음 댓글 시작 신호 전송: 그룹 {next_script.group_number}-{next_script.sequence_number}")
                                    except Exception as e:
                                        print(f"❌ 다음 댓글 신호 전송 실패: {e}")
                    
                    pc.status = 'online'
                    pc.current_task_id = None
                    db.commit()
                    
                    # 다음 작업 할당 (댓글이 아닌 경우만)
                    if task.task_type not in ['comment', 'reply']:
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


async def auto_assign_tasks(db: Session):
    """대기 중인 Task들을 자동 할당"""
    try:
        # 대기 중인 Task들
        pending_tasks = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.assigned_pc_id == None
        ).order_by(AutomationTask.priority.desc(), AutomationTask.scheduled_time.asc()).all()
        
        if not pending_tasks:
            return
        
        # 온라인 PC 찾기
        online_pcs = db.query(AutomationWorkerPC).filter(
            AutomationWorkerPC.status == 'online'
        ).all()
        
        if not online_pcs:
            print("⚠️ 온라인 PC가 없습니다")
            return
        
        assigned_count = 0
        
        for task in pending_tasks:
            # 사용 가능한 PC 찾기 (현재 작업이 없는 PC)
            for pc in online_pcs:
                if pc.current_task_id:
                    continue  # 이미 작업 중
                
                # 해당 PC의 계정 찾기
                available_account = db.query(AutomationAccount).filter(
                    AutomationAccount.assigned_pc_id == pc.id,
                    AutomationAccount.status == 'active'
                ).first()
                
                if not available_account:
                    continue  # 사용 가능한 계정 없음
                
                # Task 할당
                task.assigned_pc_id = pc.id
                task.assigned_account_id = available_account.id
                task.status = 'assigned'
                pc.current_task_id = task.id
                
                assigned_count += 1
                print(f"✅ Task #{task.id} → PC #{pc.pc_number} (계정: {available_account.account_id})")
                
                # 해당 PC의 WebSocket으로 작업 전송
                if pc.pc_number in worker_connections:
                    await send_task_to_worker(pc.pc_number, task, db)
                
                break  # 다음 Task로
        
        db.commit()
        print(f"📊 {assigned_count}개 Task 할당 완료")
        
    except Exception as e:
        print(f"❌ 자동 할당 오류: {e}")
        import traceback
        traceback.print_exc()


async def send_task_to_worker(pc_number: int, task: AutomationTask, db: Session):
    """Worker에게 Task 전송"""
    try:
        websocket = worker_connections.get(pc_number)
        if not websocket:
            return
        
        # 카페 정보
        cafe = db.query(AutomationCafe).get(task.cafe_id) if task.cafe_id else None
        
        # 계정 정보
        account = db.query(AutomationAccount).get(task.assigned_account_id) if task.assigned_account_id else None
        
        # Task 데이터
        task_data = {
            'type': 'new_task',
            'task': {
                'id': task.id,
                'task_type': task.task_type,
                'title': task.title,
                'content': task.content,
                'cafe_url': cafe.url if cafe else None,
                'post_url': task.parent_task.post_url if task.parent_task_id else None,
                'account_id': account.account_id if account else None,
                'account_pw': account.account_pw if account else None
            }
        }
        
        await websocket.send_json(task_data)
        print(f"📤 Task #{task.id} 전송 → PC #{pc_number}")
        
    except Exception as e:
        print(f"❌ Task 전송 오류: {e}")


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
async def automation_cafe(request: Request, db: Session = Depends(get_db)):
    """자동화 카페 관리 (통합)"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login")
    
    is_admin = request.session.get("is_admin", False)
    
    return templates.TemplateResponse("automation_cafe_full.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin
    })


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

@router.get("/api/tasks/list")
async def list_tasks(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Task 목록 조회"""
    try:
        query = db.query(AutomationTask)
        
        if status:
            query = query.filter(AutomationTask.status == status)
        
        tasks = query.order_by(AutomationTask.id.desc()).limit(50).all()
        
        task_list = []
        for task in tasks:
            try:
                # 안전하게 데이터 추출
                cafe_name = None
                if task.cafe_id:
                    cafe = db.query(AutomationCafe).get(task.cafe_id)
                    cafe_name = cafe.name if cafe else None
                
                product_name = None
                keyword_text = None
                if task.schedule_id:
                    schedule = db.query(AutomationSchedule).get(task.schedule_id)
                    if schedule:
                        keyword_text = schedule.keyword_text
                        if schedule.marketing_product_id:
                            mp = db.query(MarketingProduct).options(
                                joinedload(MarketingProduct.product)
                            ).get(schedule.marketing_product_id)
                            if mp and mp.product:
                                product_name = mp.product.name
                
                assigned_pc_num = None
                if task.assigned_pc_id:
                    pc = db.query(AutomationWorkerPC).get(task.assigned_pc_id)
                    assigned_pc_num = pc.pc_number if pc else None
                
                assigned_account_id = None
                if task.assigned_account_id:
                    acc = db.query(AutomationAccount).get(task.assigned_account_id)
                    assigned_account_id = acc.account_id if acc else None
                
                task_list.append({
                    'id': task.id,
                    'task_type': task.task_type,
                    'mode': task.mode,
                    'title': task.title,
                    'cafe_name': cafe_name,
                    'product_name': product_name,
                    'keyword_text': keyword_text,
                    'status': task.status,
                    'assigned_pc': assigned_pc_num,
                    'assigned_account': assigned_account_id,
                    'scheduled_time': task.scheduled_time.strftime('%Y-%m-%d %H:%M') if task.scheduled_time else None,
                    'started_at': task.started_at.strftime('%Y-%m-%d %H:%M:%S') if task.started_at else None,
                    'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M:%S') if task.completed_at else None,
                    'post_url': task.post_url
                })
            except Exception as e:
                print(f"Task {task.id} 파싱 오류: {e}")
                continue
        
        return JSONResponse({
            'success': True,
            'tasks': task_list
        })
        
    except Exception as e:
        print(f"Task 목록 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            'success': False,
            'message': str(e)
        }, status_code=500)


@router.get("/api/schedules/list")
async def list_schedules(db: Session = Depends(get_db)):
    """스케줄 목록 조회"""
    schedules = db.query(AutomationSchedule).options(
        joinedload(AutomationSchedule.marketing_product).joinedload(MarketingProduct.product),
        joinedload(AutomationSchedule.prompt)
    ).order_by(AutomationSchedule.scheduled_date.desc()).limit(100).all()
    
    schedule_list = []
    for schedule in schedules:
        # 연관된 작업 개수
        task_count = db.query(AutomationTask).filter(
            AutomationTask.schedule_id == schedule.id
        ).count()
        
        schedule_list.append({
            'id': schedule.id,
            'scheduled_date': schedule.scheduled_date.strftime('%Y-%m-%d'),
            'mode': schedule.mode,
            'product_name': schedule.marketing_product.product.name if schedule.marketing_product and schedule.marketing_product.product else None,
            'keyword_text': schedule.keyword_text,
            'prompt_name': schedule.prompt.name if schedule.prompt else None,
            'status': schedule.status,
            'task_count': task_count
        })
    
    return JSONResponse({
        'success': True,
        'schedules': schedule_list
    })


@router.post("/api/tasks/{task_id}/reassign")
async def reassign_task(task_id: int, db: Session = Depends(get_db)):
    """Task 재할당 및 재전송"""
    task = db.query(AutomationTask).get(task_id)
    if not task:
        return JSONResponse({'success': False, 'message': 'Task를 찾을 수 없습니다'})
    
    # 상태 초기화
    task.assigned_pc_id = None
    task.assigned_account_id = None
    task.status = 'pending'
    db.commit()
    
    # 재할당
    await auto_assign_tasks(db)
    
    return JSONResponse({'success': True, 'message': 'Task가 재할당되었습니다'})


@router.post("/api/schedules/{schedule_id}/delete")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """스케줄 삭제"""
    schedule = db.query(AutomationSchedule).get(schedule_id)
    if not schedule:
        return JSONResponse({'success': False, 'message': '스케줄을 찾을 수 없습니다'})
    
    # 연관된 작업도 삭제
    db.query(AutomationTask).filter(AutomationTask.schedule_id == schedule_id).delete()
    
    db.delete(schedule)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '스케줄이 삭제되었습니다'})


@router.post("/api/schedules/create-auto")
async def create_auto_schedules(
    product_id: int = Form(...),
    cafe_id: int = Form(...),  # 카페 선택 추가!
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
        
        # 키워드 파싱
        try:
            if isinstance(product.keywords, str):
                keywords = json.loads(product.keywords)
            else:
                keywords = product.keywords or []
        except:
            keywords = []
        
        if not keywords:
            return JSONResponse({'success': False, 'message': '키워드가 없습니다'})
        
        # 키워드가 dict 리스트인 경우 처리 (예: [{"text": "키워드"}])
        keyword_list = []
        for kw in keywords:
            if isinstance(kw, dict):
                keyword_list.append(kw.get('text', '') or kw.get('keyword', ''))
            else:
                keyword_list.append(str(kw))
        
        if not keyword_list:
            return JSONResponse({'success': False, 'message': '유효한 키워드가 없습니다'})
        
        current_date = start
        keyword_index = 0
        created_count = 0
        
        while current_date <= end:
            # 주말 포함 (AI, 휴먼 모두)
            include_day = True
            
            if include_day:
                for _ in range(daily_count):
                    if keyword_index >= len(keyword_list):
                        keyword_index = 0
                    
                    schedule = AutomationSchedule(
                        mode=mode,
                        scheduled_date=current_date,
                        marketing_product_id=product_id,
                        keyword_text=keyword_list[keyword_index],
                        prompt_id=prompt_id if mode == 'ai' else None,
                        status='pending'
                    )
                    db.add(schedule)
                    db.flush()  # ID 생성
                    
                    # Task 생성 (본문 글)
                    task = AutomationTask(
                        task_type='post',
                        mode=mode,
                        schedule_id=schedule.id,
                        scheduled_time=datetime.combine(current_date, datetime.min.time()),
                        title=f"{product.product.name if product.product else '상품'} - {keyword_list[keyword_index]}",
                        content="AI가 자동 생성" if mode == 'ai' else "휴먼 모드",
                        cafe_id=cafe_id,
                        status='pending',
                        priority=0
                    )
                    db.add(task)
                    
                    created_count += 1
                    keyword_index += 1
            
            current_date += timedelta(days=1)
        
        db.commit()
        
        # ⭐ Task 생성 후 즉시 할당 시도
        await auto_assign_tasks(db)
        
        return JSONResponse({
            'success': True,
            'message': f'스케줄 {created_count}개가 생성되었습니다',
            'count': created_count
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
# Worker 업데이트 API
# ============================================

@router.get("/api/worker/version")
async def get_worker_version():
    """Worker 버전 정보 제공"""
    return JSONResponse({
        "version": "1.0.1",
        "release_date": "2025-12-31",
        "download_url": "/automation/api/worker/download",
        "changelog": [
            "VPN IP 자동 감지",
            "SSL 인증서 우회",
            "한국 시간 정확 표시",
            "자동 업데이트 기능"
        ],
        "required_packages": {
            "selenium": "4.15.2",
            "websockets": "12.0",
            "psutil": "5.9.6",
            "requests": "2.31.0",
            "webdriver-manager": "4.0.1"
        }
    })


@router.get("/api/worker/download")
async def download_worker():
    """Worker Agent 파일 다운로드"""
    from pathlib import Path
    from fastapi.responses import FileResponse
    
    worker_file = Path("worker_agent.py")
    
    if not worker_file.exists():
        return JSONResponse({
            'success': False,
            'message': 'Worker 파일을 찾을 수 없습니다'
        }, status_code=404)
    
    return FileResponse(
        worker_file,
        media_type='text/plain',
        filename='worker_agent.py'
    )


# ============================================
# 데이터 조회 API (목록)
# ============================================

@router.get("/api/pcs/list")
async def list_pcs(db: Session = Depends(get_db)):
    """PC 목록 조회"""
    pcs = db.query(AutomationWorkerPC).order_by(AutomationWorkerPC.pc_number).all()
    
    pc_list = []
    for pc in pcs:
        # 마지막 통신 시간 (이미 KST로 저장되어 있음)
        last_heartbeat_str = None
        if pc.last_heartbeat:
            last_heartbeat_str = pc.last_heartbeat.strftime('%Y-%m-%d %H:%M:%S')
        
        pc_list.append({
            'id': pc.id,
            'pc_number': pc.pc_number,
            'pc_name': pc.pc_name,
            'ip_address': pc.ip_address,
            'status': pc.status,
            'cpu_usage': pc.cpu_usage,
            'memory_usage': pc.memory_usage,
            'last_heartbeat': last_heartbeat_str,
            'current_task_id': pc.current_task_id
        })
    
    return JSONResponse({
        'success': True,
        'pcs': pc_list
    })


@router.get("/api/accounts/list")
async def list_accounts(db: Session = Depends(get_db)):
    """계정 목록 조회"""
    accounts = db.query(AutomationAccount).options(
        joinedload(AutomationAccount.assigned_pc)
    ).all()
    
    account_list = []
    for acc in accounts:
        # 마지막 사용 시간
        last_used_str = None
        if acc.last_used_at:
            last_used_str = acc.last_used_at.strftime('%Y-%m-%d %H:%M:%S')
        
        account_list.append({
            'id': acc.id,
            'account_id': acc.account_id,
            'assigned_pc': {
                'id': acc.assigned_pc.id,
                'pc_number': acc.assigned_pc.pc_number
            } if acc.assigned_pc else None,
            'status': acc.status,
            'login_status': acc.login_status,
            'total_posts': acc.total_posts,
            'total_comments': acc.total_comments,
            'last_used_at': last_used_str
        })
    
    return JSONResponse({
        'success': True,
        'accounts': account_list
    })


@router.get("/api/cafes/list")
async def list_cafes(db: Session = Depends(get_db)):
    """카페 목록 조회"""
    cafes = db.query(AutomationCafe).all()
    
    return JSONResponse({
        'success': True,
        'cafes': [{
            'id': cafe.id,
            'name': cafe.name,
            'url': cafe.url,
            'status': cafe.status,
            'created_at': cafe.created_at.strftime('%Y-%m-%d') if cafe.created_at else None
        } for cafe in cafes]
    })


@router.get("/api/prompts/list")
async def list_prompts(db: Session = Depends(get_db)):
    """프롬프트 목록 조회"""
    prompts = db.query(AutomationPrompt).all()
    
    return JSONResponse({
        'success': True,
        'prompts': [{
            'id': prompt.id,
            'name': prompt.name,
            'prompt_type': prompt.prompt_type,
            'temperature': prompt.temperature,
            'max_tokens': prompt.max_tokens,
            'is_active': prompt.is_active,
            'created_at': prompt.created_at.strftime('%Y-%m-%d') if prompt.created_at else None
        } for prompt in prompts]
    })


@router.get("/api/products/list")
async def list_products(db: Session = Depends(get_db)):
    """마케팅 상품 목록 조회"""
    products = db.query(MarketingProduct).options(
        joinedload(MarketingProduct.product)
    ).all()
    
    return JSONResponse({
        'success': True,
        'products': [{
            'id': product.id,
            'name': product.product.name if product.product else '상품명 없음',
            'keywords': product.keywords
        } for product in products]
    })


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


@router.post("/api/accounts/add")
async def add_account(
    account_id: str = Form(...),
    account_pw: str = Form(...),
    assigned_pc_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """계정 추가"""
    # 중복 확인
    existing = db.query(AutomationAccount).filter(
        AutomationAccount.account_id == account_id
    ).first()
    
    if existing:
        return JSONResponse({'success': False, 'message': '이미 등록된 계정입니다'})
    
    # PC ID 처리 (빈 문자열이면 None)
    pc_id = None
    if assigned_pc_id and assigned_pc_id.strip():
        try:
            pc_id = int(assigned_pc_id)
        except ValueError:
            pass
    
    account = AutomationAccount(
        account_id=account_id,
        account_pw=account_pw,
        assigned_pc_id=pc_id,
        status='active'
    )
    db.add(account)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '계정이 등록되었습니다'})


@router.post("/api/cafes/add")
async def add_cafe(
    cafe_name: str = Form(...),
    cafe_url: str = Form(...),
    db: Session = Depends(get_db)
):
    """카페 추가"""
    # 중복 확인
    existing = db.query(AutomationCafe).filter(
        AutomationCafe.url == cafe_url
    ).first()
    
    if existing:
        return JSONResponse({'success': False, 'message': '이미 등록된 카페입니다'})
    
    cafe = AutomationCafe(
        name=cafe_name,
        url=cafe_url,
        status='active'
    )
    db.add(cafe)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '카페가 등록되었습니다'})


@router.post("/api/prompts/add")
async def add_prompt(
    name: str = Form(...),
    prompt_type: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt_template: str = Form(...),
    temperature: float = Form(0.7),
    max_tokens: int = Form(1000),
    db: Session = Depends(get_db)
):
    """프롬프트 추가"""
    # 중복 확인
    existing = db.query(AutomationPrompt).filter(
        AutomationPrompt.name == name
    ).first()
    
    if existing:
        return JSONResponse({'success': False, 'message': '이미 등록된 프롬프트입니다'})
    
    prompt = AutomationPrompt(
        name=name,
        prompt_type=prompt_type,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        temperature=temperature,
        max_tokens=max_tokens,
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '프롬프트가 등록되었습니다'})


@router.post("/api/pcs/{pc_id}/delete")
async def delete_pc(pc_id: int, db: Session = Depends(get_db)):
    """PC 삭제"""
    pc = db.query(AutomationWorkerPC).get(pc_id)
    if not pc:
        return JSONResponse({'success': False, 'message': 'PC를 찾을 수 없습니다'})
    
    db.delete(pc)
    db.commit()
    
    return JSONResponse({'success': True, 'message': 'PC가 삭제되었습니다'})


@router.post("/api/accounts/{account_id}/delete")
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    """계정 삭제"""
    account = db.query(AutomationAccount).get(account_id)
    if not account:
        return JSONResponse({'success': False, 'message': '계정을 찾을 수 없습니다'})
    
    db.delete(account)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '계정이 삭제되었습니다'})


@router.post("/api/cafes/{cafe_id}/delete")
async def delete_cafe(cafe_id: int, db: Session = Depends(get_db)):
    """카페 삭제"""
    cafe = db.query(AutomationCafe).get(cafe_id)
    if not cafe:
        return JSONResponse({'success': False, 'message': '카페를 찾을 수 없습니다'})
    
    db.delete(cafe)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '카페가 삭제되었습니다'})


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

