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

# ⭐ 전역 락 (순차 실행 보장!)
task_completion_lock = asyncio.Lock()

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
    MarketingPost, User, CommentScript, WorkerVersion, AIGeneratedPost  # ⭐ AIGeneratedPost 추가!
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
    
    # 🔄 재연결 시 대기 중인 Task 재전송 (모든 연결에서 실행!)
    print(f"\n🔄 Worker PC #{pc_number} 연결 → Task 확인 중...")
    
    # 1. 미할당 Task 찾기
    pending_task = db.query(AutomationTask).filter(
        AutomationTask.status == 'pending',
        AutomationTask.assigned_pc_id == None
    ).order_by(
        AutomationTask.priority.desc(),
        AutomationTask.scheduled_time.asc()
    ).first()
    print(f"   미할당 Task: {'#' + str(pending_task.id) if pending_task else '없음'}")
    
    # 2. 이 PC에 할당된 Task 중 아직 시작 안 한 것 찾기 (최신 우선!)
    assigned_task = db.query(AutomationTask).filter(
        AutomationTask.assigned_pc_id == pc.id,
        AutomationTask.status.in_(['pending', 'assigned'])
    ).order_by(
        AutomationTask.priority.desc(),
        AutomationTask.id.desc()  # 최신 Task 우선!
    ).first()
    print(f"   할당된 Task (PC #{pc_number}): {'#' + str(assigned_task.id) if assigned_task else '없음'}")
    
    # 3. 모든 pending/assigned Task 확인 (디버깅)
    all_pending = db.query(AutomationTask).filter(
        AutomationTask.status.in_(['pending', 'assigned'])
    ).all()
    if all_pending:
        print(f"   전체 대기 Task: {', '.join([f'#{t.id}(PC:{t.assigned_pc_id}, 상태:{t.status})' for t in all_pending])}")
    
    # ⚠️  재연결 시 Task 재전송하지 않음! HTTP API에서만 순차 전송!
    print(f"   ℹ️  순차 실행 중: HTTP 완료 보고로만 다음 Task 전송됨")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message['type'] == 'heartbeat':
                # Heartbeat 처리
                pc.status = 'online'  # ⭐ Heartbeat 받으면 무조건 online!
                pc.cpu_usage = message.get('cpu_usage')
                pc.memory_usage = message.get('memory_usage')
                pc.ip_address = message.get('ip_address', pc.ip_address)
                pc.last_heartbeat = get_kst_now()  # KST 시간으로 저장
                db.commit()
                
                # Heartbeat 응답 전송 (중요!)
                await websocket.send_json({
                    'type': 'heartbeat_ack',
                    'timestamp': get_kst_now().isoformat()
                })
                
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
                    
                    # ⭐ 즉시 커밋 (재연결 시 중복 실행 방지!)
                    db.commit()
                    print(f"✅ Task #{task.id} 완료 처리 완료 (타입: {task.task_type}, post_url: {task.post_url})")
                    
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
                    
                    # ⚠️  WebSocket 완료는 백업용! HTTP API에서만 다음 Task 전송!
                    
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
    finally:
        # ⭐ DB 세션 정리 (연결 풀 고갈 방지!)
        try:
            db.close()
        except:
            pass


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
        
        # draft_url 추출 (error_message에서)
        draft_url = None
        if task.error_message and 'MODIFY_URL:' in task.error_message:
            draft_url = task.error_message.split('MODIFY_URL:')[1].strip()
        
        # 부모 Task의 post_url 가져오기 (댓글/대댓글용)
        post_url = None
        parent_comment_id = None
        
        if task.parent_task_id:
            parent_task = db.query(AutomationTask).get(task.parent_task_id)
            if parent_task:
                # post_url 가져오기
                if parent_task.task_type == 'post':
                    post_url = parent_task.post_url
                else:
                    # 부모가 댓글이면 그 댓글의 post_url 사용
                    root_task = parent_task
                    while root_task and root_task.task_type != 'post':
                        root_task = db.query(AutomationTask).get(root_task.parent_task_id) if root_task.parent_task_id else None
                    if root_task:
                        post_url = root_task.post_url
                
                # 대댓글이면 부모 댓글의 cafe_comment_id 가져오기
                if task.task_type == 'reply' and parent_task.task_type in ['comment', 'reply']:
                    if parent_task.error_message and 'cafe_comment_id:' in parent_task.error_message:
                        parent_comment_id = parent_task.error_message.split('cafe_comment_id:')[1].strip()
                        print(f"   부모 댓글 ID: {parent_comment_id}")
                
                print(f"   부모 Task #{parent_task.id} post_url: {post_url}")
        
        # Task 데이터
        task_data = {
            'type': 'new_task',
            'task': {
                'id': task.id,
                'task_type': task.task_type,
                'title': task.title,
                'content': task.content,
                'cafe_url': cafe.url if cafe else None,
                'post_url': post_url,  # 명시적으로 로드한 post_url
                'draft_url': draft_url,  # 수정 발행 URL 추가!
                'parent_comment_id': parent_comment_id,  # 부모 댓글 ID (대댓글용)
                'account_id': account.account_id if account else None,
                'account_pw': account.account_pw if account else None,
                'target_board': cafe.target_board if cafe else None  # ⭐ 게시판명 추가
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
        print(f"❌ PC #{pc_number} 정보 없음")
        return
    
    # 대기 중인 작업 찾기 (우선순위 높은 순, 예정 시간 빠른 순)
    pending_task = db.query(AutomationTask).filter(
        AutomationTask.status == 'pending',
        AutomationTask.assigned_pc_id == None
    ).order_by(
        AutomationTask.priority.desc(),
        AutomationTask.scheduled_time.asc()
    ).first()
    
    print(f"📋 Pending Task 검색 결과: {'Task #' + str(pending_task.id) if pending_task else '없음'}")
    
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
        
        # 부모 Task의 post_url 가져오기 (댓글/대댓글용)
        post_url = None
        if pending_task.parent_task_id:
            parent_task = db.query(AutomationTask).get(pending_task.parent_task_id)
            if parent_task:
                post_url = parent_task.post_url
                print(f"   부모 Task #{parent_task.id} post_url: {post_url}")
        
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
                'post_url': post_url,  # 명시적으로 로드한 post_url
                'account_id': available_account.account_id,
                'account_pw': available_account.account_pw
            }
        }
        
        await websocket.send_json(task_data)
        print(f"📤 작업 할당: Task #{pending_task.id} → PC #{pc_number} (post_url: {post_url})")


# ============================================
# 대시보드 페이지
# ============================================

@router.get("/cafe", response_class=HTMLResponse)
async def automation_cafe(request: Request, db: Session = Depends(get_db)):
    """AI 카페 자동화 (AI 전용)"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login")
    
    is_admin = request.session.get("is_admin", False)
    
    return templates.TemplateResponse("automation_cafe_full.html", {
        "request": request,
        "username": username,
        "is_admin": is_admin
    })


@router.get("/human", response_class=HTMLResponse)
async def automation_human(request: Request, db: Session = Depends(get_db)):
    """휴먼 카페 자동화 (휴먼 전용)"""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login")
    
    is_admin = request.session.get("is_admin", False)
    
    return templates.TemplateResponse("automation_human.html", {
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

@router.post("/api/tasks/{task_id}/complete")
async def complete_task(
    task_id: int,
    post_url: str = Form(None),
    cafe_comment_id: str = Form(None),  # 추가!
    db: Session = Depends(get_db)
):
    """Task 완료 보고 (HTTP API) - 순차 실행 보장!"""
    # ⭐ 전역 락 획득 (한 번에 하나씩만 처리!)
    async with task_completion_lock:
        try:
            task = db.query(AutomationTask).get(task_id)
            if not task:
                return JSONResponse({'success': False, 'error': 'Task not found'}, status_code=404)
            
            # 이전 sequence Task들이 모두 완료되었는지 확인
            if task.order_sequence is not None and task.order_sequence > 0:
                # 같은 본문의 이전 Task들 확인
                root_task = db.query(AutomationTask).get(task.parent_task_id)
                while root_task and root_task.task_type != 'post':
                    root_task = db.query(AutomationTask).get(root_task.parent_task_id) if root_task.parent_task_id else None
                
                if root_task:
                    prev_incomplete = db.query(AutomationTask).filter(
                        AutomationTask.parent_task_id == root_task.id,
                        AutomationTask.order_sequence < task.order_sequence,
                        AutomationTask.status != 'completed'
                    ).count()
                    
                    if prev_incomplete > 0:
                        print(f"⚠️ Task #{task_id}: 이전 {prev_incomplete}개 Task 미완료, 완료만 처리하고 전송 보류")
                        task.status = 'completed'
                        task.completed_at = get_kst_now()
                        if post_url:
                            task.post_url = post_url
                        if cafe_comment_id:
                            task.error_message = f"cafe_comment_id:{cafe_comment_id}"
                            print(f"  📌 카페 댓글 ID 저장: {cafe_comment_id}")
                        db.commit()
                        return JSONResponse({'success': True, 'message': 'pending'})
            
            task.status = 'completed'
            task.completed_at = get_kst_now()
            if post_url:
                task.post_url = post_url
            if cafe_comment_id:
                task.error_message = f"cafe_comment_id:{cafe_comment_id}"
                print(f"  📌 카페 댓글 ID 저장: {cafe_comment_id}")
            
            db.commit()
            print(f"✅ Task #{task_id} 완료 (HTTP, sequence:{task.order_sequence}, post_url: {task.post_url})")
        
        except Exception as e:
            return JSONResponse({'success': False, 'error': str(e)}, status_code=500)
    
    # ⭐ 락 해제 후 대기 및 전송 (다른 요청 차단 안 함!)
    
    # 랜덤 대기 (2-5초)
    import random
    wait_time = random.randint(2, 5)
    print(f"⏳ 다음 작업 대기 중... ({wait_time}초)")
    await asyncio.sleep(wait_time)
    
    # 다음 Task 전송
    task = db.query(AutomationTask).get(task_id)  # 다시 조회
    if task and task.task_type == 'post' and task.parent_task_id is None:
        # 본문 완료: 첫 댓글 전송
        first_comment = db.query(AutomationTask).filter(
            AutomationTask.parent_task_id == task_id,
            AutomationTask.status.in_(['pending', 'assigned'])
        ).order_by(
            AutomationTask.order_sequence.asc()
        ).first()
        
        if first_comment and first_comment.assigned_pc_id:
            # PC 연결될 때까지 대기 (최대 90초)
            if first_comment.assigned_pc_id not in worker_connections:
                print(f"   ⏳ PC #{first_comment.assigned_pc_id} 연결 대기 중... (최대 90초)")
                for i in range(90):
                    await asyncio.sleep(1)
                    if first_comment.assigned_pc_id in worker_connections:
                        print(f"   ✅ PC #{first_comment.assigned_pc_id} 연결됨! ({i+1}초)")
                        break
                else:
                    print(f"   ⚠️  타임아웃: PC #{first_comment.assigned_pc_id} 연결 안 됨")
                    return JSONResponse({'success': True, 'message': 'timeout'})
            
            print(f"   📨 첫 댓글 Task #{first_comment.id} → PC #{first_comment.assigned_pc_id} 전송...")
            await send_task_to_worker(first_comment.assigned_pc_id, first_comment, db)
    
    elif task and task.task_type in ['comment', 'reply']:
        # 댓글/대댓글 완료: 같은 본문의 다음 댓글 전송
        root_task = db.query(AutomationTask).get(task.parent_task_id)
        while root_task and root_task.task_type != 'post':
            root_task = db.query(AutomationTask).get(root_task.parent_task_id) if root_task.parent_task_id else None
        
        if root_task:
            # 같은 본문의 모든 댓글/대댓글 중 다음 것 찾기
            all_comments = db.query(AutomationTask).filter(
                AutomationTask.task_type.in_(['comment', 'reply']),
                AutomationTask.status.in_(['pending', 'assigned', 'completed']),
                AutomationTask.cafe_id == root_task.cafe_id,
                AutomationTask.id >= root_task.id
            ).all()
            
            # 이 본문과 관련된 댓글들만 필터링 (부모 추적)
            related_tasks = []
            for t in all_comments:
                temp = t
                while temp and temp.task_type != 'post':
                    temp = db.query(AutomationTask).get(temp.parent_task_id) if temp.parent_task_id else None
                if temp and temp.id == root_task.id:
                    related_tasks.append(t)
            
            # pending/assigned 중 다음 순서 것 찾기
            next_comment = None
            for t in sorted(related_tasks, key=lambda x: x.order_sequence):
                if t.order_sequence > task.order_sequence and t.status in ['pending', 'assigned']:
                    next_comment = t
                    break
            
            if next_comment and next_comment.assigned_pc_id:
                # PC 연결될 때까지 대기 (최대 90초)
                if next_comment.assigned_pc_id not in worker_connections:
                    print(f"   ⏳ PC #{next_comment.assigned_pc_id} 연결 대기 중... (최대 90초)")
                    for i in range(90):
                        await asyncio.sleep(1)
                        if next_comment.assigned_pc_id in worker_connections:
                            print(f"   ✅ PC #{next_comment.assigned_pc_id} 연결됨! ({i+1}초)")
                            break
                    else:
                        print(f"   ⚠️  타임아웃: PC #{next_comment.assigned_pc_id} 연결 안 됨")
                        return JSONResponse({'success': True, 'message': 'timeout'})
                
                print(f"   📨 다음 댓글 Task #{next_comment.id} (순서:{next_comment.order_sequence}, 타입:{next_comment.task_type}) → PC #{next_comment.assigned_pc_id} 전송...")
                await send_task_to_worker(next_comment.assigned_pc_id, next_comment, db)
    
    return JSONResponse({'success': True})


@router.get("/api/worker/version")
async def get_worker_version():
    """Worker 버전 정보 제공"""
    return JSONResponse({
        "version": "1.0.6",
        "release_date": "2026-02-19",
        "download_url": "/automation/api/worker/download",
        "changelog": [
            "계정명 기반 PC 고정 할당",
            "대댓글 ID 반환 (부모 추적)",
            "카페 계정 수 자동 조정",
            "순차 실행 + 랜덤 대기"
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


@router.get("/api/pcs/{pc_number}/account")
async def get_pc_account(pc_number: int, db: Session = Depends(get_db)):
    """PC에 할당된 계정 정보 조회"""
    try:
        # PC 정보 조회
        pc = db.query(AutomationWorkerPC).filter(
            AutomationWorkerPC.pc_number == pc_number
        ).first()
        
        if not pc:
            return JSONResponse({
                'success': False,
                'error': f'PC #{pc_number}를 찾을 수 없습니다'
            }, status_code=404)
        
        # 해당 PC에 할당된 계정 조회
        account = db.query(AutomationAccount).filter(
            AutomationAccount.assigned_pc_id == pc.id
        ).first()
        
        if not account:
            return JSONResponse({
                'success': False,
                'error': f'PC #{pc_number}에 할당된 계정이 없습니다'
            }, status_code=404)
        
        return JSONResponse({
            'success': True,
            'account': {
                'id': account.id,
                'account_id': account.account_id,
                'account_pw': account.account_pw,
                'status': account.status
            },
            'pc': {
                'id': pc.id,
                'pc_number': pc.pc_number,
                'pc_name': pc.pc_name
            }
        })
        
    except Exception as e:
        print(f"❌ 계정 조회 오류: {e}")
        return JSONResponse({
            'success': False,
            'error': str(e)
        }, status_code=500)


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
            'characteristics': cafe.characteristics if hasattr(cafe, 'characteristics') else None,
            'target_board': cafe.target_board if hasattr(cafe, 'target_board') else None,
            'status': cafe.status,
            'created_at': cafe.created_at.strftime('%Y-%m-%d') if cafe.created_at else None
        } for cafe in cafes]
    })


@router.get("/api/cafes/by-url")
async def get_cafe_by_url(
    url: str,
    db: Session = Depends(get_db)
):
    """URL로 카페 정보 조회 (Worker용)"""
    try:
        # URL에서 카페 도메인 추출
        from urllib.parse import urlparse
        parsed = urlparse(url)
        cafe_domain = f"{parsed.scheme}://{parsed.netloc}"
        
        # cafe_domain으로 카페 찾기
        cafe = db.query(AutomationCafe).filter(
            AutomationCafe.url.like(f"{cafe_domain}%")
        ).first()
        
        if not cafe:
            return JSONResponse({
                'success': False,
                'message': '등록되지 않은 카페입니다'
            }, status_code=404)
        
        return JSONResponse({
            'success': True,
            'cafe': {
                'id': cafe.id,
                'name': cafe.name,
                'url': cafe.url,
                'target_board': cafe.target_board,
                'characteristics': cafe.characteristics
            }
        })
    except Exception as e:
        return JSONResponse({
            'success': False,
            'error': str(e)
        }, status_code=500)


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


@router.post("/api/accounts/update/{account_id}")
async def update_account(
    account_id: int,
    account_pw: Optional[str] = Form(None),
    assigned_pc_id: Optional[str] = Form(None),
    status: str = Form('active'),
    db: Session = Depends(get_db)
):
    """계정 수정"""
    account = db.query(AutomationAccount).filter(AutomationAccount.id == account_id).first()
    
    if not account:
        return JSONResponse({'success': False, 'message': '계정을 찾을 수 없습니다'}, status_code=404)
    
    # 비밀번호 변경 (입력했을 때만)
    if account_pw and account_pw.strip():
        account.account_pw = account_pw
    
    # PC 할당 변경
    if assigned_pc_id and assigned_pc_id.strip():
        try:
            account.assigned_pc_id = int(assigned_pc_id)
        except ValueError:
            pass
    else:
        account.assigned_pc_id = None
    
    # 상태 변경
    account.status = status
    
    db.commit()
    
    return JSONResponse({'success': True, 'message': '계정이 수정되었습니다'})


@router.post("/api/cafes/add")
async def add_cafe(
    cafe_name: str = Form(...),
    cafe_url: str = Form(...),
    characteristics: Optional[str] = Form(None),
    target_board: Optional[str] = Form(None),
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
        status='active',
        characteristics=characteristics,
        target_board=target_board
    )
    db.add(cafe)
    db.commit()
    
    return JSONResponse({'success': True, 'message': '카페가 등록되었습니다'})


@router.post("/api/cafes/update/{cafe_id}")
async def update_cafe(
    cafe_id: int,
    cafe_name: str = Form(...),
    cafe_url: str = Form(...),
    characteristics: Optional[str] = Form(None),
    target_board: Optional[str] = Form(None),
    status: str = Form('active'),
    db: Session = Depends(get_db)
):
    """카페 수정"""
    cafe = db.query(AutomationCafe).filter(AutomationCafe.id == cafe_id).first()
    
    if not cafe:
        return JSONResponse({'success': False, 'message': '카페를 찾을 수 없습니다'}, status_code=404)
    
    cafe.name = cafe_name
    cafe.url = cafe_url
    cafe.characteristics = characteristics
    cafe.target_board = target_board
    cafe.status = status
    
    db.commit()
    
    return JSONResponse({'success': True, 'message': '카페가 수정되었습니다'})


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


@router.post("/api/prompts/{prompt_id}/update")
async def update_prompt(
    prompt_id: int,
    name: str = Form(...),
    prompt_type: str = Form(...),
    temperature: float = Form(...),
    max_tokens: int = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 수정"""
    prompt = db.query(AutomationPrompt).get(prompt_id)
    if not prompt:
        return JSONResponse({'success': False, 'message': '프롬프트를 찾을 수 없습니다'})
    
    # 기본 정보만 수정 (보안상 시스템/사용자 프롬프트는 수정 불가)
    prompt.name = name
    prompt.prompt_type = prompt_type
    prompt.temperature = temperature
    prompt.max_tokens = max_tokens
    
    db.commit()
    
    return JSONResponse({'success': True, 'message': '프롬프트가 수정되었습니다'})


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


# ============================================
# 댓글 원고 관리 API
# ============================================

@router.post("/api/comment-scripts/parse")
async def parse_comment_scripts(
    post_task_id: int = Form(...),
    script_text: str = Form(...),
    db: Session = Depends(get_db)
):
    # 댓글 원고 파싱 및 저장
    from utils.comment_parser import parse_comment_scripts, validate_comment_scripts
    
    try:
        post_task = db.query(AutomationTask).get(post_task_id)
        if not post_task or post_task.task_type != 'post':
            return JSONResponse({'success': False, 'message': '본문 Task를 찾을 수 없습니다.'}, status_code=404)
        
        scripts = parse_comment_scripts(script_text)
        if not scripts:
            return JSONResponse({'success': False, 'message': '파싱할 댓글 원고가 없습니다.'}, status_code=400)
        
        validation = validate_comment_scripts(scripts)
        if not validation['valid']:
            return JSONResponse({'success': False, 'message': '유효성 검증 실패', 'errors': validation['errors']}, status_code=400)
        
        db.query(CommentScript).filter(CommentScript.post_task_id == post_task_id).delete()
        db.commit()
        
        saved_scripts = []
        for script in scripts:
            comment_script = CommentScript(
                post_task_id=post_task_id,
                group_number=script['group'],
                sequence_number=script['sequence'],
                pc_number=script['pc'],
                content=script['content'],
                is_new_comment=script['is_new'],
                parent_group=script['parent_group'],
                status='pending'
            )
            db.add(comment_script)
            saved_scripts.append(comment_script)
        
        db.commit()
        
        return JSONResponse({
            'success': True,
            'message': f'{len(saved_scripts)}개 댓글 원고 저장 완료',
            'total_scripts': len(saved_scripts),
            'groups': max([s['group'] for s in scripts])
        })
        
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'message': f'오류 발생: {str(e)}'}, status_code=500)


@router.get("/api/comment-scripts/list")
async def get_comment_scripts(
    post_task_id: int = Query(...),
    db: Session = Depends(get_db)
):
    # 특정 본문 Task의 댓글 원고 목록
    scripts = db.query(CommentScript).filter(
        CommentScript.post_task_id == post_task_id
    ).order_by(
        CommentScript.group_number,
        CommentScript.sequence_number
    ).all()
    
    groups = {}
    for script in scripts:
        group_num = script.group_number
        if group_num not in groups:
            groups[group_num] = []
        
        groups[group_num].append({
            'id': script.id,
            'group': script.group_number,
            'sequence': script.sequence_number,
            'pc_number': script.pc_number,
            'content': script.content,
            'is_new_comment': script.is_new_comment,
            'parent_group': script.parent_group,
            'status': script.status,
            'completed_at': script.completed_at.strftime('%Y-%m-%d %H:%M:%S') if script.completed_at else None
        })
    
    return JSONResponse({
        'success': True,
        'scripts': [s for s in scripts],
        'groups': groups,
        'total_count': len(scripts),
        'total_groups': len(groups)
    })


@router.post("/api/comment-scripts/create-tasks")
async def create_comment_tasks(
    post_task_id: int = Form(...),
    db: Session = Depends(get_db)
):
    # 댓글 원고에서 AutomationTask 생성
    try:
        post_task = db.query(AutomationTask).get(post_task_id)
        if not post_task or post_task.status != 'completed' or not post_task.post_url:
            return JSONResponse({'success': False, 'message': '본문 글이 완료되어야 합니다.'}, status_code=400)
        
        scripts = db.query(CommentScript).filter(
            CommentScript.post_task_id == post_task_id,
            CommentScript.status == 'pending'
        ).order_by(CommentScript.group_number, CommentScript.sequence_number).all()
        
        if not scripts:
            return JSONResponse({'success': False, 'message': '생성할 댓글 원고가 없습니다.'}, status_code=404)
        
        created_tasks = []
        for script in scripts:
            pc = db.query(AutomationWorkerPC).filter(AutomationWorkerPC.pc_number == script.pc_number).first()
            if not pc:
                continue
            
            account = db.query(AutomationAccount).filter(
                AutomationAccount.assigned_pc_id == pc.id,
                AutomationAccount.status == 'active'
            ).first()
            if not account:
                continue
            
            task = AutomationTask(
                task_type='comment' if script.is_new_comment else 'reply',
                mode=post_task.mode,
                schedule_id=post_task.schedule_id,
                scheduled_time=get_kst_now(),
                content=script.content,
                parent_task_id=None,
                order_sequence=script.group_number * 100 + script.sequence_number,
                assigned_pc_id=pc.id,
                assigned_account_id=account.id,
                cafe_id=post_task.cafe_id,
                status='pending',
                priority=0
            )
            db.add(task)
            db.flush()
            
            script.generated_task_id = task.id
            script.status = 'task_created'
            created_tasks.append(task)
        
        db.commit()
        
        for task in created_tasks:
            if task.assigned_pc_id in worker_connections:
                try:
                    await worker_connections[task.assigned_pc_id].send_json({
                        'type': 'new_task',
                        'task_id': task.id,
                        'task_type': task.task_type,
                        'content': task.content[:50] + '...' if len(task.content) > 50 else task.content
                    })
                except:
                    pass
        
        return JSONResponse({'success': True, 'message': f'{len(created_tasks)}개 댓글 Task 생성 완료', 'total_tasks': len(created_tasks)})
        
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'message': f'오류 발생: {str(e)}'}, status_code=500)


# ============================================
# AI 자동화 마케팅 API
# ============================================

from database import (
    AIMarketingProduct, AIProductKeyword, AIProductReference,
    AIPromptTemplate, AIPrompt, AIMarketingSchedule, AIGeneratedPost
)

@router.get("/api/ai/products")
async def get_ai_products(db: Session = Depends(get_db)):
    """AI 상품 목록 조회"""
    try:
        products = db.query(AIMarketingProduct).options(
            joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
        ).all()
        
        products_data = []
        for p in products:
            if p.marketing_product and p.marketing_product.product:
                products_data.append({
                    'id': p.id,
                    'product_name': p.product_name,
                    'product_code': p.marketing_product.product.product_code,
                    'thumbnail': p.marketing_product.product.thumbnail,
                    'use_for_cafe': p.use_for_cafe,
                    'use_for_blog': p.use_for_blog,
                    'marketing_link': p.marketing_link
                })
        
        return JSONResponse({'success': True, 'products': products_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/prompt-templates")
async def get_prompt_templates(db: Session = Depends(get_db)):
    """프롬프트 템플릿 목록 조회"""
    try:
        templates = db.query(AIPromptTemplate).filter(
            AIPromptTemplate.is_template == True
        ).all()
        
        templates_data = [{
            'id': t.id,
            'template_name': t.template_name,
            'template_type': t.template_type,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in templates]
        
        return JSONResponse({'success': True, 'templates': templates_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/prompts")
async def get_prompts(
    product: Optional[int] = Query(None),
    type: str = Query('all'),
    db: Session = Depends(get_db)
):
    """프롬프트 목록 조회"""
    try:
        query = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
        )
        
        if product:
            query = query.filter(AIPrompt.ai_product_id == product)
        
        if type != 'all':
            query = query.filter(AIPrompt.keyword_classification == type)
        
        prompts = query.all()
        
        prompts_data = []
        for p in prompts:
            if p.ai_product and p.ai_product.marketing_product and p.ai_product.marketing_product.product:
                prompts_data.append({
                    'id': p.id,
                    'product_name': p.ai_product.product_name,
                    'keyword_classification': p.keyword_classification,
                    'temperature': p.temperature,
                    'max_tokens': p.max_tokens,
                    'generate_images': p.generate_images
                })
        
        return JSONResponse({'success': True, 'prompts': prompts_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/schedules")
async def get_schedules(
    page: int = Query(1, ge=1),
    search: str = Query(''),
    status: str = Query('all'),
    db: Session = Depends(get_db)
):
    """스케줄 목록 조회 (페이지네이션)"""
    try:
        PAGE_SIZE = 20
        
        query = db.query(AIMarketingSchedule).options(
            joinedload(AIMarketingSchedule.ai_product).joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product),
            joinedload(AIMarketingSchedule.prompt)
        )
        
        # 검색 필터
        if search:
            query = query.join(
                AIMarketingProduct,
                AIMarketingSchedule.ai_product_id == AIMarketingProduct.id
            ).filter(AIMarketingProduct.product_name.like(f'%{search}%'))
        
        # 상태 필터
        if status != 'all':
            query = query.filter(AIMarketingSchedule.status == status)
        
        # 전체 개수
        total_count = query.count()
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        
        # 페이지네이션
        offset = (page - 1) * PAGE_SIZE
        schedules = query.order_by(AIMarketingSchedule.created_at.desc()).offset(offset).limit(PAGE_SIZE).all()
        
        schedules_data = []
        for s in schedules:
            if s.ai_product and s.ai_product.marketing_product and s.ai_product.marketing_product.product and s.prompt:
                schedules_data.append({
                    'id': s.id,
                    'product_name': s.ai_product.product_name,
                    'keyword_classification': s.prompt.keyword_classification,
                    'start_date': s.start_date.isoformat() if s.start_date else None,
                    'end_date': s.end_date.isoformat() if s.end_date else None,
                    'daily_post_count': s.daily_post_count,
                    'expected_total_posts': s.expected_total_posts,
                    'status': s.status
                })
        
        return JSONResponse({
            'success': True,
            'schedules': schedules_data,
            'total_pages': total_pages,
            'current_page': page
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/generated-posts")
async def get_generated_posts(
    account: Optional[int] = Query(None),
    cafe: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """신규 발행 글 목록 조회"""
    try:
        query = db.query(AIGeneratedPost).options(
            joinedload(AIGeneratedPost.ai_product),
            joinedload(AIGeneratedPost.account),
            joinedload(AIGeneratedPost.cafe)
        )
        
        if account:
            query = query.filter(AIGeneratedPost.account_id == account)
        
        if cafe:
            query = query.filter(AIGeneratedPost.cafe_id == cafe)
        
        posts = query.order_by(AIGeneratedPost.created_at.desc()).all()
        
        posts_data = [{
            'id': p.id,
            'product_name': p.ai_product.product_name if p.ai_product else '',
            'account_name': p.account.account_id if p.account else '',
            'cafe_name': p.cafe.name if p.cafe else '',
            'post_title': p.post_title,
            'post_url': p.post_url,
            'status': p.status,
            'created_at': p.created_at.isoformat() if p.created_at else None
        } for p in posts]
        
        return JSONResponse({'success': True, 'posts': posts_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/connections")
async def get_connections(db: Session = Depends(get_db)):
    """연동 관리 목록 조회"""
    try:
        from database import CafeAccountLink
        
        connections = db.query(CafeAccountLink).options(
            joinedload(CafeAccountLink.cafe),
            joinedload(CafeAccountLink.account)
        ).all()
        
        connections_data = [{
            'id': c.id,
            'cafe_name': c.cafe.name if c.cafe else '',
            'account_name': c.account.account_id if c.account else '',
            'status': c.status,
            'draft_post_count': c.draft_post_count,
            'used_post_count': c.used_post_count
        } for c in connections]
        
        return JSONResponse({'success': True, 'connections': connections_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# AI 상품 관리 API
# ============================================

@router.get("/api/ai/available-products")
async def get_available_products(db: Session = Depends(get_db)):
    """추가 가능한 상품 목록"""
    try:
        # 이미 AI 자동화에 추가된 상품 ID들
        existing_ids = [p.marketing_product_id for p in db.query(AIMarketingProduct).all()]
        
        # 추가 가능한 상품들
        available = db.query(MarketingProduct).options(
            joinedload(MarketingProduct.product)
        ).filter(MarketingProduct.id.notin_(existing_ids) if existing_ids else True).all()
        
        products_data = []
        for mp in available:
            if mp.product:
                products_data.append({
                    'id': mp.id,
                    'name': mp.product.name,
                    'product_code': mp.product.product_code,
                    'thumbnail': mp.product.thumbnail
                })
        
        return JSONResponse({'success': True, 'products': products_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/products/add/{marketing_product_id}")
async def add_ai_product(marketing_product_id: int, db: Session = Depends(get_db)):
    """AI 상품 추가"""
    try:
        # 중복 체크
        existing = db.query(AIMarketingProduct).filter(
            AIMarketingProduct.marketing_product_id == marketing_product_id
        ).first()
        
        if existing:
            return JSONResponse({'success': False, 'error': '이미 추가된 상품입니다'}, status_code=400)
        
        # 마케팅 상품 정보 조회
        mp = db.query(MarketingProduct).options(
            joinedload(MarketingProduct.product)
        ).filter(MarketingProduct.id == marketing_product_id).first()
        
        if not mp or not mp.product:
            return JSONResponse({'success': False, 'error': '상품을 찾을 수 없습니다'}, status_code=404)
        
        # AI 상품 생성
        ai_product = AIMarketingProduct(
            marketing_product_id=marketing_product_id,
            use_for_cafe=True,
            use_for_blog=False,
            product_name=mp.product.name,
            core_value='',
            sub_core_value='',
            size_weight='',
            difference='',
            famous_brands='',
            market_problem='',
            our_price='',
            market_avg_price='',
            target_age='',
            target_gender='',
            marketing_link=''
        )
        
        db.add(ai_product)
        db.commit()
        db.refresh(ai_product)
        
        return JSONResponse({'success': True, 'id': ai_product.id})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/products/{product_id}")
async def get_ai_product(product_id: int, db: Session = Depends(get_db)):
    """AI 상품 정보 조회"""
    try:
        product = db.query(AIMarketingProduct).filter(AIMarketingProduct.id == product_id).first()
        
        if not product:
            return JSONResponse({'success': False, 'error': '상품을 찾을 수 없습니다'}, status_code=404)
        
        return JSONResponse({
            'success': True,
            'product': {
                'id': product.id,
                'use_for_cafe': product.use_for_cafe,
                'use_for_blog': product.use_for_blog,
                'product_name': product.product_name,
                'core_value': product.core_value,
                'sub_core_value': product.sub_core_value,
                'size_weight': product.size_weight,
                'difference': product.difference,
                'famous_brands': product.famous_brands,
                'market_problem': product.market_problem,
                'our_price': product.our_price,
                'market_avg_price': product.market_avg_price,
                'target_age': product.target_age,
                'target_gender': product.target_gender,
                'additional_info': product.additional_info,
                'marketing_link': product.marketing_link
            }
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/products/update/{product_id}")
async def update_ai_product(
    product_id: int,
    use_for_cafe: bool = Form(False),
    use_for_blog: bool = Form(False),
    product_name: str = Form(...),
    core_value: str = Form(...),
    sub_core_value: str = Form(...),
    size_weight: str = Form(...),
    difference: str = Form(...),
    famous_brands: str = Form(...),
    market_problem: str = Form(...),
    our_price: str = Form(...),
    market_avg_price: str = Form(...),
    target_age: str = Form(...),
    target_gender: str = Form(...),
    marketing_link: str = Form(...),
    additional_info: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """AI 상품 정보 업데이트"""
    try:
        product = db.query(AIMarketingProduct).filter(AIMarketingProduct.id == product_id).first()
        
        if not product:
            return JSONResponse({'success': False, 'error': '상품을 찾을 수 없습니다'}, status_code=404)
        
        # 업데이트
        product.use_for_cafe = use_for_cafe
        product.use_for_blog = use_for_blog
        product.product_name = product_name
        product.core_value = core_value
        product.sub_core_value = sub_core_value
        product.size_weight = size_weight
        product.difference = difference
        product.famous_brands = famous_brands
        product.market_problem = market_problem
        product.our_price = our_price
        product.market_avg_price = market_avg_price
        product.target_age = target_age
        product.target_gender = target_gender
        product.additional_info = additional_info
        product.marketing_link = marketing_link
        
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/products/{product_id}/keywords")
async def get_product_keyword_count(product_id: int, db: Session = Depends(get_db)):
    """상품의 활성 키워드 개수 조회"""
    try:
        count = db.query(AIProductKeyword).filter(
            AIProductKeyword.ai_product_id == product_id,
            AIProductKeyword.is_active == True
        ).count()
        
        return JSONResponse({'success': True, 'count': count})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 프롬프트 템플릿 관리 API
# ============================================

@router.get("/api/ai/prompt-templates")
async def get_prompt_templates_filtered(type: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """프롬프트 템플릿 목록 (분류별 필터)"""
    try:
        query = db.query(AIPromptTemplate).filter(AIPromptTemplate.is_template == True)
        
        if type:
            query = query.filter(AIPromptTemplate.template_type == type)
        
        templates = query.all()
        
        templates_data = [{
            'id': t.id,
            'template_name': t.template_name,
            'template_type': t.template_type,
            'user_prompt_template': t.user_prompt_template,
            'created_at': t.created_at.isoformat() if t.created_at else None
        } for t in templates]
        
        return JSONResponse({'success': True, 'templates': templates_data})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/prompt-templates/add")
async def add_prompt_template(
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 추가"""
    try:
        if template_type not in ['alternative', 'informational']:
            return JSONResponse({'success': False, 'error': '잘못된 분류입니다'}, status_code=400)
        
        template = AIPromptTemplate(
            template_name=template_name,
            template_type=template_type,
            user_prompt_template=user_prompt_template,
            is_template=True
        )
        
        db.add(template)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/ai/prompt-templates/{template_id}")
async def get_prompt_template(template_id: int, db: Session = Depends(get_db)):
    """프롬프트 템플릿 정보 조회"""
    try:
        template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if not template:
            return JSONResponse({'success': False, 'error': '템플릿을 찾을 수 없습니다'}, status_code=404)
        
        return JSONResponse({
            'success': True,
            'template': {
                'id': template.id,
                'template_name': template.template_name,
                'template_type': template.template_type,
                'user_prompt_template': template.user_prompt_template
            }
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/prompt-templates/update/{template_id}")
async def update_prompt_template(
    template_id: int,
    template_name: str = Form(...),
    template_type: str = Form(...),
    user_prompt_template: str = Form(...),
    db: Session = Depends(get_db)
):
    """프롬프트 템플릿 수정"""
    try:
        template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if not template:
            return JSONResponse({'success': False, 'error': '템플릿을 찾을 수 없습니다'}, status_code=404)
        
        template.template_name = template_name
        template.template_type = template_type
        template.user_prompt_template = user_prompt_template
        
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/prompt-templates/duplicate/{template_id}")
async def duplicate_prompt_template(template_id: int, db: Session = Depends(get_db)):
    """프롬프트 템플릿 복제"""
    try:
        original = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if not original:
            return JSONResponse({'success': False, 'error': '템플릿을 찾을 수 없습니다'}, status_code=404)
        
        duplicate = AIPromptTemplate(
            template_name=f"{original.template_name} (복사본)",
            template_type=original.template_type,
            user_prompt_template=original.user_prompt_template,
            is_template=True
        )
        
        db.add(duplicate)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/prompt-templates/delete/{template_id}")
async def delete_prompt_template(template_id: int, db: Session = Depends(get_db)):
    """프롬프트 템플릿 삭제"""
    try:
        template = db.query(AIPromptTemplate).filter(AIPromptTemplate.id == template_id).first()
        
        if template:
            db.delete(template)
            db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 프롬프트 관리 API
# ============================================

@router.post("/api/ai/prompts/add")
async def add_prompt(
    ai_product_id: int = Form(...),
    keyword_classification: str = Form(...),
    system_prompt: str = Form(...),
    user_prompt: str = Form(...),
    temperature: float = Form(0.7),
    max_tokens: int = Form(2000),
    generate_images: bool = Form(False),
    db: Session = Depends(get_db)
):
    """프롬프트 추가"""
    try:
        if keyword_classification not in ['alternative', 'informational']:
            return JSONResponse({'success': False, 'error': '잘못된 분류입니다'}, status_code=400)
        
        prompt = AIPrompt(
            ai_product_id=ai_product_id,
            keyword_classification=keyword_classification,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            generate_images=generate_images
        )
        
        db.add(prompt)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/prompts/delete/{prompt_id}")
async def delete_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """프롬프트 삭제"""
    try:
        prompt = db.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()
        
        if prompt:
            db.delete(prompt)
            db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 스케줄 관리 API
# ============================================

@router.post("/api/ai/schedules/add")
async def add_schedule(
    ai_product_id: int = Form(...),
    prompt_id: int = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    daily_post_count: int = Form(...),
    db: Session = Depends(get_db)
):
    """스케줄 추가"""
    try:
        # 예상 총 글 발행 수 계산
        current = start_date
        work_days = 0
        while current <= end_date:
            if current.weekday() < 5:  # 월~금
                work_days += 1
            current += timedelta(days=1)
        
        expected_total = work_days * daily_post_count
        
        schedule = AIMarketingSchedule(
            ai_product_id=ai_product_id,
            prompt_id=prompt_id,
            start_date=start_date,
            end_date=end_date,
            daily_post_count=daily_post_count,
            expected_total_posts=expected_total,
            status='scheduled'
        )
        
        db.add(schedule)
        db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/schedules/delete/{schedule_id}")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """스케줄 삭제"""
    try:
        schedule = db.query(AIMarketingSchedule).filter(AIMarketingSchedule.id == schedule_id).first()
        
        if schedule:
            db.delete(schedule)
            db.commit()
        
        return JSONResponse({'success': True})
    except Exception as e:
        db.rollback()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# Claude API 연동 - 글 생성
# ============================================

@router.post("/api/ai/generate-content")
async def generate_content(request: Request, db: Session = Depends(get_db)):
    """Claude API를 사용하여 컨텐츠 생성"""
    try:
        data = await request.json()
        prompt_id = data.get('prompt_id')
        keyword = data.get('keyword', '')
        
        if not prompt_id:
            return JSONResponse({'success': False, 'error': '프롬프트 ID가 필요합니다'}, status_code=400)
        
        # 프롬프트 정보 조회
        prompt = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product)
        ).filter(AIPrompt.id == prompt_id).first()
        
        if not prompt or not prompt.ai_product:
            return JSONResponse({'success': False, 'error': '프롬프트를 찾을 수 없습니다'}, status_code=404)
        
        # 변수 치환
        user_prompt = prompt.user_prompt
        product = prompt.ai_product
        
        replacements = {
            '{product_name}': product.product_name,
            '{core_value}': product.core_value,
            '{sub_core_value}': product.sub_core_value,
            '{size_weight}': product.size_weight,
            '{difference}': product.difference,
            '{famous_brands}': product.famous_brands,
            '{market_problem}': product.market_problem,
            '{our_price}': product.our_price,
            '{market_avg_price}': product.market_avg_price,
            '{target_age}': product.target_age,
            '{target_gender}': product.target_gender,
            '{additional_info}': product.additional_info or '',
            '{marketing_link}': product.marketing_link,
            '{keyword}': keyword
        }
        
        for var, value in replacements.items():
            user_prompt = user_prompt.replace(var, str(value))
        
        # Claude API 호출
        if not ANTHROPIC_AVAILABLE:
            return JSONResponse({'success': False, 'error': 'Anthropic 모듈이 설치되지 않았습니다'}, status_code=500)
        
        import os
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return JSONResponse({'success': False, 'error': 'ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다'}, status_code=500)
        
        client = anthropic.Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=prompt.max_tokens,
            temperature=prompt.temperature,
            system=prompt.system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        generated_content = response.content[0].text
        
        return JSONResponse({
            'success': True,
            'content': generated_content,
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# 이미지 생성 기능
# ============================================

@router.post("/api/ai/generate-images")
async def generate_images(request: Request, db: Session = Depends(get_db)):
    """Claude API를 사용하여 이미지 생성 프롬프트 작성"""
    try:
        data = await request.json()
        prompt_id = data.get('prompt_id')
        keyword = data.get('keyword', '')
        generated_content = data.get('generated_content', '')
        
        if not prompt_id:
            return JSONResponse({'success': False, 'error': '프롬프트 ID가 필요합니다'}, status_code=400)
        
        # 프롬프트 정보 조회
        prompt = db.query(AIPrompt).options(
            joinedload(AIPrompt.ai_product)
        ).filter(AIPrompt.id == prompt_id).first()
        
        if not prompt or not prompt.ai_product:
            return JSONResponse({'success': False, 'error': '프롬프트를 찾을 수 없습니다'}, status_code=404)
        
        product = prompt.ai_product
        
        # 이미지 생성 프롬프트 작성
        image_generation_prompt = f"""
위 내용을 정확하게 참조해서 다음 3가지 이미지를 생성해주세요:

상품 정보:
- 상품명: {product.product_name}
- 핵심 가치: {product.core_value}
- 타겟 고객: {product.target_age}, {product.target_gender}

생성할 이미지:
1. 제품 파손, 불량 등 부정적인 실제 사진같은 이미지
2. 실제 한국사람이 고통스러워 하고있는 실제 사진같은 이미지  
3. 해당 제품의 실제 사용하는 것 같은 이미지

각 이미지에 대한 상세한 설명을 제공해주세요.
"""
        
        # Claude API 호출
        if not ANTHROPIC_AVAILABLE:
            return JSONResponse({'success': False, 'error': 'Anthropic 모듈이 설치되지 않았습니다'}, status_code=500)
        
        import os
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return JSONResponse({'success': False, 'error': 'ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다'}, status_code=500)
        
        client = anthropic.Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            temperature=0.7,
            system="당신은 이미지 생성 전문가입니다. 주어진 컨텐츠를 바탕으로 효과적인 이미지 설명을 작성합니다.",
            messages=[
                {
                    "role": "user", 
                    "content": f"생성된 글 내용:\n\n{generated_content}\n\n{image_generation_prompt}"
                }
            ]
        )
        
        image_descriptions = response.content[0].text
        
        return JSONResponse({
            'success': True,
            'image_descriptions': image_descriptions,
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.post("/api/ai/test-generation")
async def test_generation(request: Request, db: Session = Depends(get_db)):
    """테스트: 전체 프로세스 (글 생성 + 이미지 설명 생성)"""
    try:
        data = await request.json()
        prompt_id = data.get('prompt_id')
        keyword = data.get('keyword', '')
        
        if not prompt_id:
            return JSONResponse({'success': False, 'error': '프롬프트 ID가 필요합니다'}, status_code=400)
        
        # 1단계: 글 생성
        content_response = await generate_content(request, db)
        if not content_response.body:
            return JSONResponse({'success': False, 'error': '글 생성 실패'}, status_code=500)
        
        content_data = json.loads(content_response.body)
        if not content_data.get('success'):
            return content_data
        
        generated_content = content_data['content']
        
        # 2단계: 이미지 생성 여부 확인
        prompt = db.query(AIPrompt).filter(AIPrompt.id == prompt_id).first()
        
        image_descriptions = None
        if prompt and prompt.generate_images:
            # 이미지 설명 생성
            image_request = Request(
                scope={
                    'type': 'http',
                    'method': 'POST',
                    'headers': [],
                    'query_string': b'',
                }
            )
            image_request._json = {
                'prompt_id': prompt_id,
                'keyword': keyword,
                'generated_content': generated_content
            }
            
            image_response = await generate_images(image_request, db)
            if image_response.body:
                image_data = json.loads(image_response.body)
                if image_data.get('success'):
                    image_descriptions = image_data['image_descriptions']
        
        return JSONResponse({
            'success': True,
            'content': generated_content,
            'images': image_descriptions,
            'images_generated': prompt.generate_images if prompt else False
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


# ============================================
# Worker Agent 버전 관리 API
# ============================================

@router.get("/api/worker/version")
async def get_worker_version(db: Session = Depends(get_db)):
    """Worker 최신 버전 정보"""
    try:
        latest = db.query(WorkerVersion).filter(
            WorkerVersion.is_active == True
        ).first()
        
        if not latest:
            return {
                "version": "1.0.0",
                "changelog": []
            }
        
        changelog = latest.changelog.split('\n') if latest.changelog else []
        
        return {
            "version": latest.version,
            "changelog": [line for line in changelog if line.strip()]
        }
    except Exception as e:
        return {
            "version": "1.0.0",
            "changelog": []
        }


@router.get("/api/worker/download")
async def download_worker():
    """Worker 파일 다운로드"""
    try:
        from fastapi.responses import FileResponse
        import os
        
        file_path = "worker_agent.py"
        
        if not os.path.exists(file_path):
            return JSONResponse(
                {'success': False, 'error': 'Worker 파일을 찾을 수 없습니다'},
                status_code=404
            )
        
        return FileResponse(
            path=file_path,
            media_type='text/plain',
            filename='worker_agent.py'
        )
    except Exception as e:
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )


@router.post("/api/worker/version/update")
async def update_worker_version(
    version_type: str = Form(...),  # "major", "minor", "patch"
    changelog: str = Form(...),
    db: Session = Depends(get_db)
):
    """새 버전 생성 (관리자용)"""
    try:
        # 현재 최신 버전 가져오기
        current = db.query(WorkerVersion).filter(
            WorkerVersion.is_active == True
        ).first()
        
        if current:
            # 현재 버전 비활성화
            current.is_active = False
            
            # 버전 번호 자동 증가
            parts = current.version.split('.')
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            
            if version_type == "major":
                major += 1
                minor = 0
                patch = 0
            elif version_type == "minor":
                minor += 1
                patch = 0
            else:  # patch
                patch += 1
            
            new_version = f"{major}.{minor}.{patch}"
        else:
            new_version = "1.0.0"
        
        # 새 버전 생성
        new_version_record = WorkerVersion(
            version=new_version,
            changelog=changelog,
            is_active=True,
            created_by="admin"
        )
        
        db.add(new_version_record)
        db.commit()
        
        return JSONResponse({
            'success': True,
            'version': new_version,
            'message': f'Worker 버전이 {new_version}으로 업데이트되었습니다'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )


@router.get("/api/worker/version/history")
async def get_worker_version_history(db: Session = Depends(get_db)):
    """Worker 버전 히스토리"""
    try:
        versions = db.query(WorkerVersion).order_by(
            WorkerVersion.created_at.desc()
        ).limit(10).all()
        
        return JSONResponse({
            'success': True,
            'versions': [{
                'id': v.id,
                'version': v.version,
                'changelog': v.changelog,
                'is_active': v.is_active,
                'created_at': v.created_at.strftime('%Y-%m-%d %H:%M:%S') if v.created_at else None,
                'created_by': v.created_by
            } for v in versions]
        })
    except Exception as e:
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )


# ============================================
# AI 신규발행 글 API (기존 AIGeneratedPost 사용)
# ============================================

@router.get("/api/ai-posts/list")
async def list_ai_generated_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    status: str = Query('all'),
    search: str = Query(''),
    db: Session = Depends(get_db)
):
    """AI 신규발행 글 목록 조회"""
    try:
        query = db.query(AIGeneratedPost)
        
        # 상태 필터
        if status != 'all':
            query = query.filter(AIGeneratedPost.status == status)
        
        # 검색
        if search:
            search_pattern = f'%{search}%'
            query = query.filter(
                AIGeneratedPost.post_title.like(search_pattern)
            )
        
        # 총 개수
        total = query.count()
        
        # 페이징
        posts = query.order_by(
            AIGeneratedPost.created_at.desc()
        ).offset((page - 1) * per_page).limit(per_page).all()
        
        return JSONResponse({
            'success': True,
            'posts': [{
                'id': p.id,
                'title': p.post_title,
                'url': p.post_url,
                'status': p.status,
                'created_at': p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else None,
                'published_at': p.published_at.strftime('%Y-%m-%d %H:%M:%S') if p.published_at else None
            } for p in posts],
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )


@router.post("/api/ai-posts/update-status/{post_id}")
async def update_ai_post_status(
    post_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    """AI 신규발행 글 상태 변경"""
    try:
        post = db.query(AIGeneratedPost).filter(AIGeneratedPost.id == post_id).first()
        
        if not post:
            return JSONResponse(
                {'success': False, 'error': '글을 찾을 수 없습니다'},
                status_code=404
            )
        
        post.status = status
        db.commit()
        
        return JSONResponse({
            'success': True,
            'message': f'상태가 {status}(으)로 변경되었습니다'
        })
        
    except Exception as e:
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )

