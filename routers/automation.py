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
    MarketingPost, User, CommentScript, WorkerVersion, AIGeneratedPost,
    DraftPost,
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
    
    # 2-A. 이 PC에 할당된 post/create_draft Task 우선 찾기 (오래된 순 → 밀린 것부터 처리)
    # ⭐ post 타입은 무조건 즉시 전송 가능하므로 comment보다 먼저 찾아야 함
    assigned_post_task = db.query(AutomationTask).filter(
        AutomationTask.assigned_pc_id.in_([pc.id, pc_number]),
        AutomationTask.status.in_(['pending', 'assigned']),
        AutomationTask.task_type.in_(['post', 'create_draft'])
    ).order_by(AutomationTask.id.asc()).first()

    # 2-B. post 없으면 comment/reply Task 찾기 (최신 순)
    assigned_comment_task = None
    if not assigned_post_task:
        assigned_comment_task = db.query(AutomationTask).filter(
            AutomationTask.assigned_pc_id.in_([pc.id, pc_number]),
            AutomationTask.status.in_(['pending', 'assigned']),
            AutomationTask.task_type.in_(['comment', 'reply'])
        ).order_by(AutomationTask.order_sequence.asc()).first()

    assigned_task = assigned_post_task or assigned_comment_task
    print(f"   할당된 Task (PC #{pc_number}): {'#' + str(assigned_task.id) + ' (' + assigned_task.task_type + ')' if assigned_task else '없음'}")
    
    # 3. 모든 pending/assigned Task 확인 (디버깅)
    all_pending = db.query(AutomationTask).filter(
        AutomationTask.status.in_(['pending', 'assigned'])
    ).all()
    if all_pending:
        print(f"   전체 대기 Task: {', '.join([f'#{t.id}(PC:{t.assigned_pc_id}, 상태:{t.status})' for t in all_pending])}")
    
    # ⚠️  댓글/대댓글 Task: 기본은 HTTP 완료 보고로만 다음 Task 전송! (순서 보장)
    # ✅  post / create_draft 타입 Task: 연결 즉시 전송 가능 (순서 무관)
    # ✅  comment / reply 타입 Task: 부모 post 완료 + 이전 순서 모두 완료 시 즉시 전송 (복구)
    if assigned_post_task:
        print(f"   📤 Post Task #{assigned_post_task.id} 즉시 전송 (Worker 재연결 감지)")
        try:
            await send_task_to_worker(pc_number, assigned_post_task, db)
        except Exception as _e:
            print(f"   ❌ Post Task 즉시 전송 실패: {_e}")
    elif assigned_comment_task:
        if _is_comment_ready(assigned_comment_task, db):
            print(f"   📤 Comment Task #{assigned_comment_task.id} 즉시 전송 (부모 완료 확인, 복구)")
            try:
                await send_task_to_worker(pc_number, assigned_comment_task, db)
            except Exception as _e:
                print(f"   ❌ Comment Task 즉시 전송 실패: {_e}")
        else:
            print(f"   ℹ️  순차 실행 중: HTTP 완료 보고로만 다음 Task 전송됨")
    elif pending_task and pending_task.task_type in ('post', 'create_draft'):
        # 미할당 post 태스크: 이 PC에 할당해서 즉시 전송
        pending_task.assigned_pc_id = pc.id
        db.commit()
        print(f"   📤 미할당 Post Task #{pending_task.id} → PC#{pc_number} 즉시 배정 후 전송")
        try:
            await send_task_to_worker(pc_number, pending_task, db)
        except Exception as _e:
            print(f"   ❌ 미할당 Post Task 즉시 전송 실패: {_e}")
    else:
        print(f"   ℹ️  대기 중인 Task 없음")
    
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
                    
                    # 작성된 글/댓글/신규발행 저장
                    if task.task_type == 'create_draft':
                        # 신규발행 인사글 URL을 DraftPost에 저장
                        draft_url = message.get('post_url')
                        if draft_url and task.cafe_id and task.assigned_account_id:
                            from database import CafeAccountLink, DraftPost
                            import re as _re
                            link = db.query(CafeAccountLink).filter(
                                CafeAccountLink.cafe_id == task.cafe_id,
                                CafeAccountLink.account_id == task.assigned_account_id,
                                CafeAccountLink.status == 'active'
                            ).first()
                            if link:
                                article_id = ''
                                m = _re.search(r'articleid=(\d+)', draft_url, _re.IGNORECASE)
                                if m:
                                    article_id = m.group(1)
                                draft_post = DraftPost(
                                    link_id=link.id,
                                    draft_url=draft_url,
                                    article_id=article_id,
                                    status='available'
                                )
                                db.add(draft_post)
                                link.draft_post_count = (link.draft_post_count or 0) + 1
                                db.commit()
                                print(f"   ✅ DraftPost 저장: {draft_url[:60]}...")
                            else:
                                print(f"   ⚠️  CafeAccountLink 없음 (cafe_id={task.cafe_id}, account_id={task.assigned_account_id})")
                    elif task.task_type == 'post':
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
                        # ★ DraftPost modified_url만 저장 (used 처리는 댓글 전체 완료 후)
                        post_url_ws = message.get('post_url')
                        if (task.error_message and 'MODIFY_URL:' in task.error_message and post_url_ws):
                            try:
                                from database import DraftPost as _DP_ws
                                draft_url_ws = task.error_message.split('MODIFY_URL:')[1].split('|')[0].strip()
                                dp_ws = db.query(_DP_ws).filter(_DP_ws.draft_url == draft_url_ws).first()
                                if dp_ws:
                                    dp_ws.modified_url = post_url_ws
                                    print(f"  📌 [WS] DraftPost #{dp_ws.id} modified_url 저장 (used 처리는 댓글 완료 후)")
                            except Exception as _dp_err:
                                print(f"  ⚠️ [WS] DraftPost modified_url 저장 실패: {_dp_err}")
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
                    _failed_task_type = task.task_type
                    _failed_task_id = task.id
                    _failed_pc_id = task.assigned_pc_id
                    task.status = 'failed'
                    task.error_message = message.get('error')
                    task.retry_count += 1
                    pc.status = 'online'
                    pc.current_task_id = None
                    db.commit()
                    _err_preview = (message.get('error') or '')[:80]
                    print(f"❌ Task #{_failed_task_id} 실패 처리 완료 (타입: {_failed_task_type}, 사유: {_err_preview})")

                    # ★ post 타입 실패 → 다음 AI 그룹 실행 (댓글 스킵, 다음 글로)
                    if _failed_task_type == 'post':
                        asyncio.create_task(
                            _dispatch_next_group_on_failure(_failed_task_id)
                        )
                    # ★ create_draft 실패 → 해당 PC 다음 대기 태스크 전송
                    elif _failed_task_type == 'create_draft' and _failed_pc_id:
                        asyncio.create_task(
                            _try_send_next_pending_task(_failed_pc_id)
                        )
                    
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
            extracted = task.error_message.split('MODIFY_URL:')[1].split('|')[0].strip()
            draft_url = extracted if extracted else None  # 빈 문자열도 None 처리
        
        # post 타입 태스크에서 draft_url이 없으면 오류 로그 출력
        if task.task_type == 'post' and not draft_url:
            print(f"⚠️  [경고] Task #{task.id} (post) → draft_url 없음!")
            print(f"   error_message: {repr(task.error_message)}")
            print(f"   MODIFY_URL이 error_message에 저장되지 않은 상태입니다.")
        
        # 부모 Task의 post_url 가져오기 (댓글/대댓글용만, post task는 불필요)
        post_url = None
        parent_comment_id = None

        if task.task_type in ['comment', 'reply'] and task.parent_task_id:
            parent_task = db.query(AutomationTask).get(task.parent_task_id)
            if parent_task:
                # post_url 가져오기
                if parent_task.task_type == 'post':
                    post_url = parent_task.post_url
                else:
                    # 부모가 댓글이면 루트 post까지 올라가서 post_url 사용
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
        
        # ★ 댓글/대댓글인데 post_url이 없으면 전송 차단 (잘못된 글에 댓글 방지)
        if task.task_type in ['comment', 'reply'] and not post_url:
            print(f"❌ [경고] Task #{task.id} ({task.task_type}) → post_url 없음! 전송 중단 (부모 post_url이 아직 없거나 parent_task_id 오류)")
            print(f"   parent_task_id: {task.parent_task_id}")
            return

        # 이미지 URL 파싱 (JSON 문자열 → 리스트)
        import json as _json
        image_urls = []
        if task.image_urls:
            try:
                image_urls = _json.loads(task.image_urls)
            except Exception:
                pass
        
        # Task 데이터 (전송 전 로그)
        _content_val = task.content or ''
        print(f"\n📤 [send_task] Task #{task.id} ({task.task_type}) → PC#{pc_number}")
        print(f"   제목       : {task.title or '없음'}")
        print(f"   content 길이: {len(_content_val)}자")
        if _content_val:
            print(f"   content 앞부분: {_content_val[:200]}{'...' if len(_content_val) > 200 else ''}")
        else:
            print(f"   ⚠️  content가 비어있음! (DB 값: {repr(task.content)})")
        print(f"   draft_url  : {draft_url or '없음'}")
        print(f"   keyword    : {task.keyword or '없음'}")
        print(f"   image_urls : {len(image_urls)}장")

        task_data = {
            'type': 'new_task',
            'task': {
                'id': task.id,
                'task_type': task.task_type,
                'title': task.title,
                'content': task.content,
                'cafe_url': cafe.url if cafe else None,
                'post_url': post_url,
                'draft_url': draft_url,
                'parent_comment_id': parent_comment_id,
                'account_id': account.account_id if account else None,
                'account_pw': account.account_pw if account else None,
                'target_board': cafe.target_board if cafe else None,
                'image_urls': image_urls,  # ⭐ 이미지 URL 목록
                'keyword': task.keyword or None,  # ⭐ 타겟 키워드 (태그용)
                # ⭐ create_draft 전용: 인사글 제목/본문 (error_message에 JSON으로 저장)
                'draft_title': (
                    _json.loads(task.error_message).get('draft_title', '안녕하세요')
                    if task.error_message and task.error_message.startswith('{')
                    else '안녕하세요'
                ) if task.task_type == 'create_draft' else None,
                'draft_body': (
                    _json.loads(task.error_message).get('draft_body', '')
                    if task.error_message and task.error_message.startswith('{')
                    else ''
                ) if task.task_type == 'create_draft' else None,
            }
        }
        
        await websocket.send_json(task_data)
        print(f"📤 Task #{task.id} 전송 → PC #{pc_number}")

        # ★ 전송 즉시 assigned로 상태 변경 (중복 전송 방지)
        # pending인 경우만 변경 (이미 assigned/in_progress/completed면 skip → 중복 전송 방지)
        try:
            db.refresh(task)  # 최신 상태 재조회 (타이밍 문제 방지)
            if task.status == 'pending':
                task.status = 'assigned'
                db.commit()
            elif task.status in ['completed', 'failed', 'cancelled']:
                print(f"⚠️  Task #{task.id} 이미 {task.status} 상태 → 전송했지만 상태 변경 없음 (중복 전송 의심!)")
        except Exception:
            db.rollback()
        
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

@router.post("/api/tasks/{task_id}/resume-comments")
async def resume_task_comments(task_id: int, db: Session = Depends(get_db)):
    """특정 post task의 대기 중인 댓글을 순서대로 재전송"""
    try:
        task = db.query(AutomationTask).get(task_id)
        if not task:
            return JSONResponse({'success': False, 'message': 'Task not found'}, status_code=404)
        if task.task_type not in ('post',):
            return JSONResponse({'success': False, 'message': 'post 타입 Task만 가능합니다.'}, status_code=400)
        if task.status != 'completed':
            return JSONResponse({'success': False, 'message': 'post가 completed 상태여야 합니다.'}, status_code=400)

        pending_children = db.query(AutomationTask).filter(
            AutomationTask.parent_task_id == task_id,
            AutomationTask.task_type.in_(['comment', 'reply']),
            AutomationTask.status.in_(['pending', 'assigned'])
        ).order_by(AutomationTask.order_sequence.asc()).all()

        if not pending_children:
            return JSONResponse({'success': True, 'message': '대기 중인 댓글이 없습니다.', 'sent': 0})

        first = pending_children[0]
        first.status = 'pending'
        db.commit()

        pc_rec = db.query(AutomationWorkerPC).filter(
            (AutomationWorkerPC.id == first.assigned_pc_id) |
            (AutomationWorkerPC.pc_number == first.assigned_pc_id)
        ).first()
        pc_num = pc_rec.pc_number if pc_rec else first.assigned_pc_id

        if pc_num and pc_num in worker_connections:
            await send_task_to_worker(pc_num, first, db)
            print(f"📤 [댓글재전송] Task #{first.id} → PC #{pc_num} (부모 #{task_id}, 대기 {len(pending_children)}개)")
            return JSONResponse({'success': True, 'message': f'댓글 Task #{first.id} 전송 완료 (대기 {len(pending_children)}개)', 'sent': 1})
        else:
            return JSONResponse({'success': True, 'message': f'댓글 Task #{first.id} pending 리셋 (PC 미연결 - 복구 시 자동 전송)', 'sent': 0})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


@router.post("/api/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    태스크 재시도:
    - failed 태스크: status를 pending으로 리셋 후 해당 PC로 즉시 재전송
    - pending/assigned 태스크: 해당 PC로 즉시 재전송 (막힌 경우)
    """
    try:
        task = db.query(AutomationTask).get(task_id)
        if not task:
            return JSONResponse({'success': False, 'message': f'Task #{task_id} 없음'}, status_code=404)

        if task.status not in ('failed', 'pending', 'assigned'):
            return JSONResponse({'success': False, 'message': f'재시도 불가 상태: {task.status}'}, status_code=400)

        # PC 번호 확인
        pc_num = None
        if task.assigned_pc_id:
            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == task.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == task.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else task.assigned_pc_id

        # failed이면 pending으로 리셋
        if task.status == 'failed':
            task.status = 'pending'
            task.error_message = None
            task.retry_count = (task.retry_count or 0) + 1
            db.commit()
            print(f"🔄 [재시도] Task #{task_id} failed → pending 리셋")

        # PC가 연결되어 있으면 즉시 전송
        if pc_num and pc_num in worker_connections:
            try:
                await send_task_to_worker(pc_num, task, db)
                print(f"📤 [재시도] Task #{task_id} → PC #{pc_num} 즉시 전송")
                return JSONResponse({'success': True, 'message': f'Task #{task_id} PC #{pc_num}으로 재전송 완료'})
            except Exception as _e:
                return JSONResponse({'success': True, 'message': f'Task #{task_id} pending 리셋 완료 (PC 전송 실패: {_e})'})
        else:
            pc_str = f"PC #{pc_num}" if pc_num else "미할당"
            return JSONResponse({'success': True, 'message': f'Task #{task_id} pending 리셋 완료 ({pc_str} 미연결 - 재연결 시 자동 실행)'})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


@router.post("/api/tasks/recover-stuck")
async def recover_stuck_tasks(
    db: Session = Depends(get_db)
):
    """
    막힌 태스크 강제 복구:
    1. assigned 태스크 즉시 pending 리셋 (강제 모드)
    2. in_progress 태스크 → pending 리셋
    3. PC:None 미할당 태스크 → 연결된 PC에 자동 배정 후 전송
    4. pending post/create_draft → 연결된 PC에 즉시 전송
    5. pending comment/reply 중 부모 완료된 것 → 즉시 전송
    """
    try:
        from datetime import datetime as _dt, timedelta as _td
        now = datetime.now()
        sent = 0
        reset = 0
        assigned_new = 0

        # 1. assigned 상태 즉시 리셋 (강제 복구이므로 시간 조건 없음)
        stuck_assigned = db.query(AutomationTask).filter(
            AutomationTask.status == 'assigned',
        ).all()
        for task in stuck_assigned:
            task.status = 'pending'
            reset += 1
            print(f"⚠️ [강제복구] Task #{task.id} assigned → pending 리셋")
        if stuck_assigned:
            db.commit()

        # 2. 10분 이상 in_progress 상태인 태스크 → pending 리셋
        stuck_cutoff = now - _td(minutes=10)
        stuck_inprogress = db.query(AutomationTask).filter(
            AutomationTask.status == 'in_progress',
            AutomationTask.updated_at < stuck_cutoff
        ).all()
        for task in stuck_inprogress:
            task.status = 'pending'
            reset += 1
            print(f"⚠️ [강제복구] Task #{task.id} in_progress → pending 리셋")
        if stuck_inprogress:
            db.commit()

        # 3. PC:None 미할당 post/create_draft 태스크 → 연결된 PC에 배정
        unassigned_posts = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.assigned_pc_id == None,
            AutomationTask.task_type.in_(['post', 'create_draft'])
        ).all()
        for task in unassigned_posts:
            if worker_connections:
                pc_num = next(iter(worker_connections))
                pc_rec = db.query(AutomationWorkerPC).filter(
                    AutomationWorkerPC.pc_number == pc_num
                ).first()
                if pc_rec:
                    task.assigned_pc_id = pc_rec.id
                    db.commit()
                    try:
                        await send_task_to_worker(pc_num, task, db)
                        sent += 1
                        assigned_new += 1
                    except Exception:
                        pass

        # 4. PC 할당된 pending post/create_draft → 즉시 전송
        pending_posts = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.assigned_pc_id != None,
            AutomationTask.task_type.in_(['post', 'create_draft'])
        ).order_by(AutomationTask.id.asc()).all()
        for task in pending_posts:
            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == task.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == task.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else task.assigned_pc_id
            if pc_num not in worker_connections:
                continue
            db.refresh(task)
            if task.status != 'pending':
                continue
            try:
                await send_task_to_worker(pc_num, task, db)
                sent += 1
                print(f"🔧 [강제복구] post Task #{task.id} → PC #{pc_num} 전송")
            except Exception:
                pass

        # 5. pending comment/reply 중 즉시 전송 가능한 것
        stuck_comments = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.task_type.in_(['comment', 'reply']),
        ).order_by(AutomationTask.order_sequence.asc()).all()

        dispatched_parents = set()
        for task in stuck_comments:
            if not _is_comment_ready(task, db):
                continue
            parent_id = task.parent_task_id
            if parent_id in dispatched_parents:
                continue

            if not task.assigned_pc_id:
                sibling = db.query(AutomationTask).filter(
                    AutomationTask.parent_task_id == task.parent_task_id,
                    AutomationTask.assigned_pc_id != None
                ).first()
                if sibling:
                    task.assigned_pc_id = sibling.assigned_pc_id
                elif worker_connections:
                    fallback_pc_num = next(iter(worker_connections))
                    fallback_pc = db.query(AutomationWorkerPC).filter(
                        AutomationWorkerPC.pc_number == fallback_pc_num
                    ).first()
                    if fallback_pc:
                        task.assigned_pc_id = fallback_pc.id
                db.commit()
                assigned_new += 1
                print(f"🔧 [강제복구] PC:None comment Task #{task.id} → PC 배정 완료")

            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == task.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == task.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else task.assigned_pc_id
            if pc_num not in worker_connections:
                continue
            db.refresh(task)
            if task.status != 'pending':
                continue
            try:
                await send_task_to_worker(pc_num, task, db)
                sent += 1
                if parent_id:
                    dispatched_parents.add(parent_id)
            except Exception:
                pass

        msg = f"복구 완료: {sent}개 전송, {reset}개 리셋, {assigned_new}개 새 배정"
        print(f"🔧 [강제복구] {msg}")
        return JSONResponse({'success': True, 'message': msg, 'sent': sent, 'reset': reset, 'assigned': assigned_new})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


@router.post("/api/tasks/force-resume-comments")
async def force_resume_comments(db: Session = Depends(get_db)):
    """
    강제 댓글 체인 복구:
    - 부모 post가 completed인데 pending/assigned 댓글이 있는 경우
    - 순서에 관계없이 각 그룹의 첫 번째 미완료 댓글을 강제 전송
    - 워커의 중복 방지 세트에 걸리는 경우를 위해 task ID를 변경하는 옵션 포함
    """
    try:
        sent = 0
        skipped = 0

        completed_posts = db.query(AutomationTask).filter(
            AutomationTask.task_type == 'post',
            AutomationTask.status == 'completed',
        ).all()

        for post in completed_posts:
            all_children = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id == post.id,
                AutomationTask.task_type.in_(['comment', 'reply']),
                AutomationTask.status.in_(['pending', 'assigned'])
            ).order_by(AutomationTask.order_sequence.asc()).all()

            if not all_children:
                continue

            first_pending = all_children[0]
            first_pending.status = 'pending'

            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == first_pending.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == first_pending.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else first_pending.assigned_pc_id

            if pc_num not in worker_connections:
                skipped += 1
                continue

            try:
                await send_task_to_worker(pc_num, first_pending, db)
                sent += 1
                print(f"🔧 [강제댓글복구] Task #{first_pending.id} (순서:{first_pending.order_sequence}) → PC #{pc_num} (부모 post #{post.id})")
            except Exception as e:
                print(f"⚠️ [강제댓글복구] Task #{first_pending.id} 전송 실패: {e}")
                skipped += 1

        # 대댓글(reply)도 복구: 부모 comment가 completed인데 reply가 pending인 경우
        completed_comments = db.query(AutomationTask).filter(
            AutomationTask.task_type == 'comment',
            AutomationTask.status == 'completed',
        ).all()

        for comment in completed_comments:
            pending_replies = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id == comment.id,
                AutomationTask.task_type == 'reply',
                AutomationTask.status.in_(['pending', 'assigned'])
            ).order_by(AutomationTask.order_sequence.asc()).all()

            if not pending_replies:
                continue

            first_reply = pending_replies[0]
            first_reply.status = 'pending'

            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == first_reply.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == first_reply.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else first_reply.assigned_pc_id

            if pc_num not in worker_connections:
                skipped += 1
                continue

            try:
                await send_task_to_worker(pc_num, first_reply, db)
                sent += 1
                print(f"🔧 [강제댓글복구] Reply Task #{first_reply.id} → PC #{pc_num} (부모 comment #{comment.id})")
            except Exception as e:
                skipped += 1

        db.commit()
        msg = f"강제 댓글 복구: {sent}개 전송, {skipped}개 건너뜀 (PC 미연결)"
        print(f"🔧 {msg}")
        return JSONResponse({'success': True, 'message': msg, 'sent': sent, 'skipped': skipped})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


@router.post("/api/tasks/cancel-old-pending")
async def cancel_old_pending_tasks(
    db: Session = Depends(get_db)
):
    """
    오래된 pending 태스크 일괄 취소:
    - 부모 post가 failed/cancelled 인 comment/reply → cancelled
    - 부모가 없는 고아 comment/reply → cancelled
    - 7일 이상 된 pending 태스크 → cancelled
    """
    try:
        from datetime import datetime as _dt, timedelta as _td
        cancelled = 0
        now = datetime.now()
        cutoff_7d = now - _td(days=7)

        # 1. 부모 post가 failed/cancelled인 comment/reply 취소
        orphan_comments = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.task_type.in_(['comment', 'reply']),
            AutomationTask.parent_task_id != None
        ).all()
        for task in orphan_comments:
            # 루트 post 찾기
            root = task
            for _ in range(10):
                if root.task_type == 'post':
                    break
                if not root.parent_task_id:
                    root = None
                    break
                root = db.query(AutomationTask).get(root.parent_task_id)
                if not root:
                    break
            if root is None or (root.status in ('failed', 'cancelled')):
                task.status = 'cancelled'
                cancelled += 1

        # 2. 7일 이상 된 pending 태스크 취소
        old_tasks = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.created_at < cutoff_7d
        ).all()
        for task in old_tasks:
            task.status = 'cancelled'
            cancelled += 1

        db.commit()
        msg = f"{cancelled}개 오래된/고아 태스크 취소 완료"
        print(f"🧹 [정리] {msg}")
        return JSONResponse({'success': True, 'message': msg, 'cancelled': cancelled})

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


@router.get("/api/tasks/diagnose")
async def diagnose_tasks(
    db: Session = Depends(get_db)
):
    """
    태스크 상태 진단 - PC:None 태스크 및 막힌 태스크 현황 반환
    """
    try:
        # PC:None pending 태스크
        unassigned = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',
            AutomationTask.assigned_pc_id == None
        ).order_by(AutomationTask.id.asc()).all()

        unassigned_list = []
        for t in unassigned:
            root_status = None
            if t.parent_task_id:
                root = t
                for _ in range(10):
                    if root.task_type == 'post': break
                    if not root.parent_task_id: root = None; break
                    root = db.query(AutomationTask).get(root.parent_task_id)
                    if not root: break
                root_status = root.status if root else 'unknown'
            unassigned_list.append({
                'id': t.id,
                'type': t.task_type,
                'status': t.status,
                'root_status': root_status,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else None,
            })

        # 상태별 카운트
        from sqlalchemy import func as _func
        status_counts = db.query(AutomationTask.status, _func.count(AutomationTask.id)).group_by(AutomationTask.status).all()

        return JSONResponse({
            'success': True,
            'unassigned_tasks': unassigned_list,
            'status_counts': {s: c for s, c in status_counts},
            'connected_pcs': list(worker_connections.keys()),
        })
    except Exception as e:
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)

@router.get("/api/tasks/completed")
async def list_completed_tasks(
    date_from: Optional[str] = Query(None),    # 'YYYY-MM-DD'
    date_to: Optional[str] = Query(None),      # 'YYYY-MM-DD'
    product_name: Optional[str] = Query(None), # 상품명 부분 검색
    cafe_name: Optional[str] = Query(None),    # 카페명 부분 검색
    account_name: Optional[str] = Query(None), # 계정 부분 검색
    result_filter: Optional[str] = Query(None), # 'success' | 'partial' | 'failed'
    sort_order: str = Query('desc'),           # 'desc' | 'asc'
    page: int = Query(1),
    page_size: int = Query(20),
    db: Session = Depends(get_db)
):
    """완료 탭 전용 API - 서버사이드 필터/페이지네이션"""
    try:
        from datetime import datetime as _dt, timedelta as _td
        from sqlalchemy import desc as _desc, asc as _asc

        # root post task만 조회 (parent_task_id IS NULL)
        query = db.query(AutomationTask).filter(
            AutomationTask.parent_task_id == None,
            AutomationTask.task_type.in_(['post', 'create_draft']),
        )

        # result_filter에 따른 상태 필터
        if result_filter == 'failed':
            query = query.filter(AutomationTask.status == 'failed')
        elif result_filter in ('success', 'partial'):
            query = query.filter(AutomationTask.status == 'completed')
        else:
            query = query.filter(AutomationTask.status.in_(['completed', 'failed']))

        if date_from:
            _df = _dt.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AutomationTask.completed_at >= _df)
        if date_to:
            _dt2_end = _dt.strptime(date_to, '%Y-%m-%d') + _td(days=1)
            query = query.filter(AutomationTask.completed_at < _dt2_end)

        # product_name 필터 (task.product_name 컬럼)
        if product_name:
            query = query.filter(AutomationTask.product_name.ilike(f'%{product_name}%'))

        # success/partial 필터는 자식 상태를 봐야 하므로 전체 조회 후 파이썬 필터
        need_child_filter = result_filter in ('success', 'partial')

        if need_child_filter:
            if sort_order == 'asc':
                all_tasks = query.order_by(_asc(AutomationTask.completed_at)).all()
            else:
                all_tasks = query.order_by(_desc(AutomationTask.completed_at)).all()

            filtered_tasks = []
            for t in all_tasks:
                children = db.query(AutomationTask).filter(
                    AutomationTask.parent_task_id == t.id,
                    AutomationTask.task_type.in_(['comment', 'reply'])
                ).all()
                all_children_completed = all(c.status == 'completed' for c in children) if children else True
                if result_filter == 'success' and all_children_completed:
                    filtered_tasks.append(t)
                elif result_filter == 'partial' and not all_children_completed:
                    filtered_tasks.append(t)

            total = len(filtered_tasks)
            tasks = filtered_tasks[(page - 1) * page_size: page * page_size]
        else:
            total = query.count()
            if sort_order == 'asc':
                tasks = query.order_by(_asc(AutomationTask.completed_at)).offset((page - 1) * page_size).limit(page_size).all()
            else:
                tasks = query.order_by(_desc(AutomationTask.completed_at)).offset((page - 1) * page_size).limit(page_size).all()

        import json as _json
        task_list = []
        for task in tasks:
            try:
                cafe_obj = db.query(AutomationCafe).get(task.cafe_id) if task.cafe_id else None
                c_name = cafe_obj.name if cafe_obj else None

                # 카페명 필터 (DB에서 못 거른 경우 파이썬에서)
                if cafe_name and (not c_name or cafe_name.lower() not in c_name.lower()):
                    total -= 1
                    continue

                acc_obj = db.query(AutomationAccount).get(task.assigned_account_id) if task.assigned_account_id else None
                acc_str = acc_obj.account_id if acc_obj else None

                # 계정명 필터
                if account_name and (not acc_str or account_name.lower() not in acc_str.lower()):
                    total -= 1
                    continue

                pc_rec = db.query(AutomationWorkerPC).filter(
                    (AutomationWorkerPC.id == task.assigned_pc_id) |
                    (AutomationWorkerPC.pc_number == task.assigned_pc_id)
                ).first() if task.assigned_pc_id else None
                pc_num = pc_rec.pc_number if pc_rec else task.assigned_pc_id

                image_urls_list = []
                if task.image_urls:
                    try:
                        image_urls_list = _json.loads(task.image_urls)
                    except Exception:
                        pass

                # 자식 task 수 및 상태 요약
                children = db.query(AutomationTask).filter(
                    AutomationTask.parent_task_id == task.id
                ).order_by(AutomationTask.order_sequence.asc()).all()

                children_data = []
                for ch in children:
                    ch_acc = db.query(AutomationAccount).get(ch.assigned_account_id) if ch.assigned_account_id else None
                    ch_pc_rec = db.query(AutomationWorkerPC).filter(
                        (AutomationWorkerPC.id == ch.assigned_pc_id) |
                        (AutomationWorkerPC.pc_number == ch.assigned_pc_id)
                    ).first() if ch.assigned_pc_id else None
                    children_data.append({
                        'id': ch.id,
                        'task_type': ch.task_type,
                        'status': ch.status,
                        'content': (ch.content or '')[:80],
                        'assigned_pc': ch_pc_rec.pc_number if ch_pc_rec else ch.assigned_pc_id,
                        'assigned_account': ch_acc.account_id if ch_acc else None,
                        'order_sequence': ch.order_sequence,
                        'post_url': ch.post_url,
                        'completed_at': ch.completed_at.strftime('%Y-%m-%d %H:%M:%S') if ch.completed_at else None,
                    })

                # result_status 계산: 전체성공/일부성공/실패
                if task.status == 'failed':
                    _result_status = 'failed'
                else:
                    _comment_children = [ch for ch in children if ch.task_type in ('comment', 'reply')]
                    _all_done = all(ch.status == 'completed' for ch in _comment_children) if _comment_children else True
                    _result_status = 'success' if _all_done else 'partial'

                task_list.append({
                    'id': task.id,
                    'task_type': task.task_type,
                    'mode': task.mode,
                    'title': task.title,
                    'content': (task.content or '')[:500],
                    'cafe_name': c_name,
                    'product_name': task.product_name or '',
                    'keyword_text': task.keyword or '',
                    'status': task.status,
                    'result_status': _result_status,
                    'assigned_pc': pc_num,
                    'assigned_account': acc_str,
                    'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M:%S') if task.completed_at else None,
                    'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S') if task.updated_at else None,
                    'post_url': task.post_url,
                    'parent_task_id': None,
                    'order_sequence': task.order_sequence,
                    'image_urls': image_urls_list,
                    'error_message': (task.error_message if task.status == 'failed' and task.error_message and not task.error_message.startswith('MODIFY_URL:') else None),
                    '_children': children_data,
                })
            except Exception as _e:
                print(f"완료 Task {task.id} 파싱 오류: {_e}")
                continue

        return JSONResponse({
            'success': True,
            'tasks': task_list,
            'total': total,
            'page': page,
            'page_size': page_size,
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'message': str(e)}, status_code=500)


@router.get("/api/tasks/list")
async def list_tasks(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Task 목록 조회"""
    try:
        query = db.query(AutomationTask)

        # pending/assigned/in_progress 태스크는 반드시 전부 포함
        # completed/failed/cancelled는 최근 200개만
        from sqlalchemy import or_ as _or
        active_tasks = db.query(AutomationTask).filter(
            AutomationTask.status.in_(['pending', 'assigned', 'in_progress'])
        ).order_by(AutomationTask.id.asc()).all()

        recent_done = db.query(AutomationTask).filter(
            AutomationTask.status.in_(['completed', 'failed', 'cancelled'])
        ).order_by(AutomationTask.id.desc()).limit(200).all()

        tasks = active_tasks + recent_done
        
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

                # 1) task 자체에 product_name 저장된 경우 (AI 스케줄 태스크)
                if hasattr(task, 'product_name') and task.product_name:
                    product_name = task.product_name

                # 2) schedule_id 있는 경우 → schedule → marketing_product
                if task.schedule_id:
                    schedule = db.query(AutomationSchedule).get(task.schedule_id)
                    if schedule:
                        keyword_text = schedule.keyword_text
                        if not product_name and schedule.marketing_product_id:
                            mp = db.query(MarketingProduct).options(
                                joinedload(MarketingProduct.product)
                            ).get(schedule.marketing_product_id)
                            if mp and mp.product:
                                product_name = mp.product.name

                # 3) keyword_text 폴백: task.keyword
                if not keyword_text and task.keyword:
                    keyword_text = task.keyword

                assigned_pc_num = None
                if task.assigned_pc_id:
                    # pc_id는 DB ID 또는 pc_number 둘 다 가능 → 양쪽 조회
                    pc = db.query(AutomationWorkerPC).filter(
                        (AutomationWorkerPC.id == task.assigned_pc_id) |
                        (AutomationWorkerPC.pc_number == task.assigned_pc_id)
                    ).first()
                    assigned_pc_num = pc.pc_number if pc else task.assigned_pc_id

                assigned_account_str = None
                if task.assigned_account_id:
                    acc = db.query(AutomationAccount).get(task.assigned_account_id)
                    assigned_account_str = acc.account_id if acc else None

                # 이미지 URL 파싱
                import json as _json
                image_urls_list = []
                if task.image_urls:
                    try:
                        image_urls_list = _json.loads(task.image_urls)
                    except Exception:
                        pass

                task_list.append({
                    'id': task.id,
                    'task_type': task.task_type,
                    'mode': task.mode,
                    'title': task.title,
                    'content': (task.content or '')[:500],  # 미리보기용 500자
                    'cafe_name': cafe_name,
                    'product_name': product_name,
                    'keyword_text': keyword_text,
                    'status': task.status,
                    'assigned_pc': assigned_pc_num,
                    'assigned_account': assigned_account_str,
                    'scheduled_time': task.scheduled_time.strftime('%Y-%m-%d %H:%M') if task.scheduled_time else None,
                    'started_at': task.started_at.strftime('%Y-%m-%d %H:%M:%S') if task.started_at else None,
                    'completed_at': task.completed_at.strftime('%Y-%m-%d %H:%M:%S') if task.completed_at else None,
                    'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S') if task.updated_at else None,
                    'post_url': task.post_url,
                    'parent_task_id': task.parent_task_id,
                    'order_sequence': task.order_sequence,
                    'image_urls': image_urls_list,
                    'error_message': (task.error_message if task.status == 'failed' and task.error_message and not task.error_message.startswith('MODIFY_URL:') else None),
                })
            except Exception as e:
                print(f"Task {task.id} 파싱 오류: {e}")
                continue

        # ── 2nd pass: 자식 task에 부모의 product_name/keyword_text 상속 ──
        # (댓글/대댓글 task 자체에는 이 값이 없어서 대시보드에 "-" 표시)
        by_id = {t['id']: t for t in task_list}
        for t in task_list:
            if t['parent_task_id'] and (not t['product_name'] or not t['keyword_text']):
                parent = by_id.get(t['parent_task_id'])
                if parent:
                    if not t['product_name']:
                        t['product_name'] = parent.get('product_name')
                    if not t['keyword_text']:
                        t['keyword_text'] = parent.get('keyword_text')

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

def _is_comment_ready(task, db) -> bool:
    """comment/reply Task가 지금 즉시 실행 가능한지 확인
    
    조건:
    0. task 자신이 pending 상태여야 함 (assigned/in_progress는 이미 전송됨)
    1. 루트 post task가 completed 상태
    2. 이 task보다 낮은 order_sequence 중 아직 완료되지 않은 task가 없어야 함
    3. 현재 in_progress 또는 assigned인 sibling task가 없어야 함
    """
    try:
        # ★ 자신이 이미 전송된 상태라면 복구 불필요
        if task.status in ('in_progress', 'completed', 'failed', 'cancelled'):
            return False

        # 루트 post task 찾기 (최대 10단계)
        root = task
        for _ in range(10):
            if root.task_type == 'post':
                break
            if not root.parent_task_id:
                return False
            root = db.query(AutomationTask).get(root.parent_task_id)
            if not root:
                return False

        if root.task_type != 'post':
            return False

        # 루트 post가 실패한 경우 댓글은 실행 불가 (cancelled 처리되어야 함)
        if root.status == 'failed':
            return False

        # 루트 post가 완료여야 댓글 실행 가능
        if root.status not in ('completed',):
            return False

        # reply 태스크인 경우: 직계 부모(comment)가 completed 상태여야 함
        if task.task_type == 'reply':
            parent = db.query(AutomationTask).get(task.parent_task_id) if task.parent_task_id else None
            if not parent:
                return False
            if parent.status != 'completed':
                return False
            # 같은 부모를 가진 reply 중 자신보다 낮은 order_sequence가 미완료이면 아직 차례 아님
            earlier_reply = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id == task.parent_task_id,
                AutomationTask.order_sequence < (task.order_sequence or 0),
                AutomationTask.status.in_(['pending', 'assigned', 'in_progress'])
            ).first()
            if earlier_reply:
                return False
            # 같은 부모 아래 in_progress/assigned reply가 있으면 대기
            sibling_active = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id == task.parent_task_id,
                AutomationTask.id != task.id,
                AutomationTask.status.in_(['in_progress', 'assigned'])
            ).first()
            if sibling_active:
                return False
            return True

        # comment 태스크인 경우: root post 직계 자식 기준으로 체크
        # 이 task보다 낮은 order_sequence를 가진 미완료 task가 있으면 아직 차례 아님
        earlier_incomplete = db.query(AutomationTask).filter(
            AutomationTask.parent_task_id == root.id,
            AutomationTask.order_sequence < (task.order_sequence or 0),
            AutomationTask.status.in_(['pending', 'assigned', 'in_progress'])
        ).first()
        if earlier_incomplete:
            return False

        # 현재 in_progress 또는 assigned인 다른 댓글이 있으면 대기 (중복 전송 방지)
        in_progress = db.query(AutomationTask).filter(
            AutomationTask.parent_task_id == root.id,
            AutomationTask.id != task.id,
            AutomationTask.status.in_(['in_progress', 'assigned'])
        ).first()
        if in_progress:
            return False

        return True
    except Exception:
        return False


async def _try_send_next_pending_task(pc_id: int, db=None):
    """create_draft 실패 후 해당 PC에 다음 대기 태스크 전송"""
    from database import SessionLocal, AutomationTask, AutomationPC
    _own_db = db is None
    if _own_db:
        db = SessionLocal()
    try:
        await asyncio.sleep(2)
        pc = db.query(AutomationPC).get(pc_id)
        if not pc:
            return
        pc_number = pc.pc_number
        # 해당 PC에 할당된 pending 태스크 찾기
        next_task = db.query(AutomationTask).filter(
            AutomationTask.assigned_pc_id == pc_id,
            AutomationTask.status == 'pending'
        ).order_by(AutomationTask.id.asc()).first()
        if next_task and pc_number in worker_connections:
            await send_task_to_worker(pc_number, next_task, db)
            print(f"📤 [create_draft 실패 후] 다음 Task #{next_task.id} → PC #{pc_number}")
    except Exception as e:
        print(f"⚠️  _try_send_next_pending_task 오류: {e}")
    finally:
        if _own_db:
            db.close()


def _mark_draft_post_used(post_task, db):
    """post task에 연결된 DraftPost를 'used'로 변경 + used_post_count 증가
    
    전체 댓글이 completed인 경우에만 호출해야 함.
    """
    from database import CafeAccountLink as _CAL, DraftPost as _DP
    if not (post_task.error_message and 'MODIFY_URL:' in post_task.error_message):
        return
    if not post_task.post_url:
        return
    try:
        draft_url_val = post_task.error_message.split('MODIFY_URL:')[1].split('|')[0].strip()
        draft_post = db.query(_DP).filter(_DP.draft_url == draft_url_val).first()
        if draft_post and draft_post.status != 'used':
            draft_post.status = 'used'
            draft_post.used_at = get_kst_now()
            if not draft_post.modified_url:
                draft_post.modified_url = post_task.post_url
            if draft_post.link_id:
                link = db.query(_CAL).get(draft_post.link_id)
                if link:
                    link.used_post_count = (link.used_post_count or 0) + 1
                    print(f"  ✅ DraftPost #{draft_post.id} → used, used_post_count → {link.used_post_count}")
            else:
                print(f"  ✅ DraftPost #{draft_post.id} → used")
            db.commit()
    except Exception as dp_err:
        print(f"  ⚠️ DraftPost used 처리 실패: {dp_err}")


async def _dispatch_next_group_on_failure(failed_task_id: int):
    """post 타입 Task 실패 시 → 해당 그룹의 댓글들을 모두 cancelled 처리하고 다음 AI 그룹 실행"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        import random
        await asyncio.sleep(random.randint(1, 3))

        # 실패한 post task에 연결된 댓글/대댓글을 재귀적으로 모두 cancelled 처리
        def _collect_descendants(parent_id):
            children = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id == parent_id,
                AutomationTask.status.in_(['pending', 'assigned'])
            ).all()
            result = list(children)
            for ch in children:
                result.extend(_collect_descendants(ch.id))
            return result

        child_tasks = _collect_descendants(failed_task_id)
        for ct in child_tasks:
            ct.status = 'cancelled'
            print(f"   🚫 [BG] Task #{ct.id} ({ct.task_type}) → cancelled (부모 실패)")
        if child_tasks:
            db.commit()
            print(f"   ✅ [BG] {len(child_tasks)}개 하위 Task cancelled 처리 완료 (댓글+대댓글)")

        # 다음 AI 그룹 실행
        try:
            from routers.ai_automation import _execute_next_ai_group, _ai_task_schedule_map
            schedule_id = _ai_task_schedule_map.get(failed_task_id)
            if schedule_id is None:
                # 서버 재시작 등으로 in-memory 맵 소실 → DB task error_message에서 SCHED_ID 복구
                _failed_task = db.query(AutomationTask).get(failed_task_id)
                if _failed_task and _failed_task.error_message and 'SCHED_ID:' in _failed_task.error_message:
                    try:
                        for _part in _failed_task.error_message.split('|'):
                            if _part.startswith('SCHED_ID:'):
                                schedule_id = int(_part.split(':')[1].strip())
                                print(f"   🔄 [BG] schedule_id error_message 복구: {schedule_id} (task#{failed_task_id})")
                                break
                    except Exception:
                        pass
            if schedule_id is not None:
                print(f"   🔗 [BG] post 실패 → 다음 AI 그룹 실행 (schedule#{schedule_id})")
                await _execute_next_ai_group(schedule_id, db)
            else:
                print(f"   ℹ️  [BG] schedule 매핑 없음 (task#{failed_task_id}) → 다음 그룹 없음")
        except Exception as _nge:
            print(f"   ⚠️ [BG] 다음 AI 그룹 실행 오류: {_nge}")

    except Exception as e:
        import traceback
        print(f"❌ [BG] 실패 후 다음 그룹 처리 오류: {e}")
        traceback.print_exc()
    finally:
        db.close()


async def _dispatch_next_task_bg(task_id: int, task_type: str, parent_task_id, order_sequence, cafe_id):
    """다음 Task 비동기 전송 (백그라운드) - complete_task 즉시 응답 후 실행"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        import random
        wait_time = random.randint(20, 40)
        print(f"⏳ [BG] 다음 작업 대기 중... ({wait_time}초)")
        await asyncio.sleep(wait_time)

        if task_type == 'post':
            # 본문 완료 → 첫 댓글 전송 (task_type 필터로 post 체인 제외)
            first_comment = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id == task_id,
                AutomationTask.task_type.in_(['comment', 'reply']),
                AutomationTask.status.in_(['pending', 'assigned'])
            ).order_by(AutomationTask.order_sequence.asc()).first()

            if first_comment:
                print(f"   📋 [BG] 첫 댓글 Task #{first_comment.id} (PC:{first_comment.assigned_pc_id})")
            else:
                total = db.query(AutomationTask).filter(AutomationTask.parent_task_id == task_id).count()
                print(f"   ⚠️  [BG] 댓글 없음 (총 {total}개) → 다음 AI 그룹 확인")

            if first_comment and first_comment.assigned_pc_id:
                # DB ID → pc_number 변환
                _pc_rec = db.query(AutomationWorkerPC).filter(
                    (AutomationWorkerPC.id == first_comment.assigned_pc_id) |
                    (AutomationWorkerPC.pc_number == first_comment.assigned_pc_id)
                ).first()
                _pc_num = _pc_rec.pc_number if _pc_rec else first_comment.assigned_pc_id

                if _pc_num not in worker_connections:
                    print(f"   ⏳ [BG] PC #{_pc_num} 연결 대기 중... (최대 120초)")
                    for i in range(120):
                        await asyncio.sleep(1)
                        if _pc_num in worker_connections:
                            print(f"   ✅ [BG] PC #{_pc_num} 연결됨! ({i+1}초)")
                            break
                    else:
                        print(f"   ⚠️  [BG] 타임아웃: PC #{_pc_num} 미연결 → Task #{first_comment.id} pending 유지 (recover-stuck에서 재시도)")
                        return

                # ★ 전송 직전 상태 재확인 (중복 전송 방지)
                db.refresh(first_comment)
                if first_comment.status != 'pending':
                    print(f"   ⚠️  [BG] 첫 댓글 Task #{first_comment.id} 이미 {first_comment.status} → 전송 건너뜀")
                    return

                print(f"   📨 [BG] 첫 댓글 Task #{first_comment.id} → PC #{_pc_num}")
                _post_task_for_log = db.query(AutomationTask).get(task_id)
                print(f"   📌 [BG] 댓글 대상 글: {_post_task_for_log.post_url[:80] if _post_task_for_log and _post_task_for_log.post_url else 'N/A'}...")
                await send_task_to_worker(_pc_num, first_comment, db)
            else:
                # 댓글 없는 경우 → DraftPost used 처리 후 다음 AI 그룹 즉시 실행
                _post_task_for_used = db.query(AutomationTask).get(task_id)
                if _post_task_for_used:
                    _mark_draft_post_used(_post_task_for_used, db)
                try:
                    from routers.ai_automation import _execute_next_ai_group, _ai_task_schedule_map
                    schedule_id = _ai_task_schedule_map.get(task_id)
                    if schedule_id is None:
                        _post_task = db.query(AutomationTask).get(task_id)
                        if _post_task and _post_task.error_message and 'SCHED_ID:' in _post_task.error_message:
                            try:
                                for _part in _post_task.error_message.split('|'):
                                    if _part.startswith('SCHED_ID:'):
                                        schedule_id = int(_part.split(':')[1].strip())
                                        print(f"   🔄 [BG] schedule_id error_message 복구: {schedule_id}")
                                        break
                            except Exception:
                                pass
                    if schedule_id is not None:
                        print(f"   🔗 [BG] 댓글 없음 → 다음 AI 그룹 실행 (schedule#{schedule_id})")
                        await _execute_next_ai_group(schedule_id, db)
                except Exception as _nge:
                    print(f"   ⚠️ [BG] 다음 AI 그룹 실행 오류: {_nge}")

        elif task_type in ['comment', 'reply']:
            # 댓글/대댓글 완료 → 다음 댓글 전송
            task = db.query(AutomationTask).get(task_id)
            if not task:
                return

            # ★ root_task(post task) 찾기: parent_task_id를 따라 올라감
            root_task = db.query(AutomationTask).get(task.parent_task_id)
            while root_task and root_task.task_type != 'post':
                root_task = db.query(AutomationTask).get(root_task.parent_task_id) if root_task.parent_task_id else None

            if root_task:
                # ★ 핵심 수정: cafe_id 기반 범위 쿼리 대신 parent_task_id로 직접 추적
                # 이전 방식: cafe_id == root_task.cafe_id → 같은 카페의 다른 글 댓글까지 포함되어 오염됨
                # 새 방식: root_task에 직접 연결된 comment만, 그리고 reply는 parent comment에 연결된 것만
                def get_all_children_recursive(parent_id, collected=None):
                    """parent_task_id를 재귀적으로 탐색해서 관련 task 모두 수집"""
                    if collected is None:
                        collected = []
                    children = db.query(AutomationTask).filter(
                        AutomationTask.parent_task_id == parent_id,
                        AutomationTask.task_type.in_(['comment', 'reply'])
                    ).all()
                    for child in children:
                        collected.append(child)
                        get_all_children_recursive(child.id, collected)
                    return collected

                related_tasks = get_all_children_recursive(root_task.id)
                print(f"   🔍 [BG] root_task #{root_task.id} 하위 댓글 {len(related_tasks)}개 탐색")

                next_comment = None
                for t in sorted(related_tasks, key=lambda x: x.order_sequence):
                    # ★ 중복 전송 방지: pending 상태만 선택 (assigned/completed는 이미 처리됨)
                    if t.order_sequence > order_sequence and t.status == 'pending':
                        next_comment = t
                        break

                if next_comment and next_comment.assigned_pc_id:
                    # DB ID → pc_number 변환
                    _pc_rec2 = db.query(AutomationWorkerPC).filter(
                        (AutomationWorkerPC.id == next_comment.assigned_pc_id) |
                        (AutomationWorkerPC.pc_number == next_comment.assigned_pc_id)
                    ).first()
                    _pc_num2 = _pc_rec2.pc_number if _pc_rec2 else next_comment.assigned_pc_id

                    if _pc_num2 not in worker_connections:
                        print(f"   ⏳ [BG] PC #{_pc_num2} 연결 대기 중... (최대 120초)")
                        for i in range(120):
                            await asyncio.sleep(1)
                            if _pc_num2 in worker_connections:
                                print(f"   ✅ [BG] PC #{_pc_num2} 연결됨! ({i+1}초)")
                                break
                        else:
                            print(f"   ⚠️  [BG] 타임아웃: PC #{_pc_num2} 미연결 → Task #{next_comment.id} pending 유지 (recover-stuck에서 재시도)")
                            return

                    # ★ 전송 직전 상태 재확인 (타이밍으로 인한 중복 전송 방지)
                    db.refresh(next_comment)
                    if next_comment.status != 'pending':
                        print(f"   ⚠️  [BG] Task #{next_comment.id} 이미 {next_comment.status} → 전송 건너뜀 (중복 방지)")
                        return

                    # ★ post_url 검증: 부모 post_task의 post_url이 있어야 댓글 전송 가능
                    _parent_of_next = db.query(AutomationTask).get(next_comment.parent_task_id)
                    _root_of_next = _parent_of_next
                    while _root_of_next and _root_of_next.task_type != 'post':
                        _root_of_next = db.query(AutomationTask).get(_root_of_next.parent_task_id) if _root_of_next.parent_task_id else None
                    if _root_of_next and not _root_of_next.post_url:
                        print(f"   ⚠️  [BG] Task #{next_comment.id} 부모 post_task #{_root_of_next.id}의 post_url 없음 → 전송 대기 (수정발행 미완료)")
                        return

                    print(f"   📨 [BG] 다음 댓글 Task #{next_comment.id} (순서:{next_comment.order_sequence}) → PC #{_pc_num2}")
                    print(f"   📌 [BG] 댓글 대상 글: {_root_of_next.post_url[:80] if _root_of_next else 'N/A'}...")
                    await send_task_to_worker(_pc_num2, next_comment, db)

                else:
                    # ★ 마지막 댓글 완료 → 1개라도 성공이면 DraftPost used 처리
                    if root_task:
                        all_comments = get_all_children_recursive(root_task.id)
                        completed_count = sum(1 for t in all_comments if t.status == 'completed')
                        if completed_count > 0:
                            _mark_draft_post_used(root_task, db)
                            print(f"   ✅ [BG] 댓글 {completed_count}/{len(all_comments)}개 성공 → DraftPost used 처리")
                        else:
                            print(f"   ⚠️  [BG] 댓글 전체 실패 ({len(all_comments)}개) → DraftPost used 처리 안 함 (재사용 가능)")

                    # 다음 AI 그룹 실행 (순차)
                    try:
                        from routers.ai_automation import _execute_next_ai_group, _ai_task_schedule_map
                        if root_task:
                            schedule_id = _ai_task_schedule_map.get(root_task.id)
                            if schedule_id is None:
                                # 서버 재시작 등으로 in-memory 맵 소실 → root_task error_message에서 복구
                                if root_task.error_message and 'SCHED_ID:' in root_task.error_message:
                                    try:
                                        for _part in root_task.error_message.split('|'):
                                            if _part.startswith('SCHED_ID:'):
                                                schedule_id = int(_part.split(':')[1].strip())
                                                print(f"   🔄 [BG] schedule_id error_message 복구: {schedule_id} (root#{root_task.id})")
                                                break
                                    except Exception:
                                        pass
                            if schedule_id is not None:
                                print(f"   🔗 [BG] 마지막 댓글 완료 → 다음 AI 그룹 실행 (schedule#{schedule_id})")
                                await _execute_next_ai_group(schedule_id, db)
                            else:
                                print(f"   ✅ [BG] 모든 그룹 처리 완료 (root_task #{root_task.id})")
                    except Exception as _nge:
                        print(f"   ⚠️ [BG] 다음 AI 그룹 실행 오류: {_nge}")

    except Exception as e:
        import traceback
        print(f"❌ [BG] 다음 Task 전송 오류: {e}")
        traceback.print_exc()
    finally:
        db.close()


@router.post("/api/tasks/{task_id}/complete")
async def complete_task(
    task_id: int,
    post_url: str = Form(None),
    cafe_comment_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Task 완료 보고 (HTTP API) - DB 저장 즉시 완료 후 백그라운드로 다음 Task 처리"""
    # ⚠️ task_completion_lock 범위를 최소화 → DB 저장만 직렬화, 나머지는 락 밖에서 처리
    # 기존: 락 내부에서 모든 처리 → 다수 PC 동시 완료 시 30초+ 대기 → Read timed out 발생
    _task_type = _parent_id = _order_seq = _cafe_id = None
    try:
        # ── 1단계: 락 없이 DB 조회 (읽기는 동시성 문제 없음) ──
        task = db.query(AutomationTask).get(task_id)
        if not task:
            return JSONResponse({'success': False, 'error': 'Task not found'}, status_code=404)

        # ── 2단계: 최소 범위 락으로 DB 업데이트만 직렬화 ──
        async with task_completion_lock:
            # 재조회 (락 획득 후 최신 상태 반영)
            db.refresh(task)

            task.status = 'completed'
            task.completed_at = get_kst_now()
            if post_url:
                task.post_url = post_url
            if cafe_comment_id:
                task.error_message = f"cafe_comment_id:{cafe_comment_id}"
                print(f"  📌 카페 댓글 ID 저장: {cafe_comment_id}")

            # ★ create_draft 완료 시 DraftPost 생성
            if task.task_type == 'create_draft' and post_url:
                try:
                    import re as _re
                    from database import CafeAccountLink
                    link = db.query(CafeAccountLink).filter(
                        CafeAccountLink.cafe_id == task.cafe_id,
                        CafeAccountLink.account_id == task.assigned_account_id,
                        CafeAccountLink.status == 'active'
                    ).first()
                    if link:
                        article_id = ''
                        m = _re.search(r'articleid=(\d+)', post_url, _re.IGNORECASE)
                        if m:
                            article_id = m.group(1)
                        existing = db.query(DraftPost).filter(DraftPost.draft_url == post_url).first()
                        if not existing:
                            draft_post_new = DraftPost(
                                link_id=link.id, draft_url=post_url,
                                article_id=article_id, status='available'
                            )
                            db.add(draft_post_new)
                            link.draft_post_count = (link.draft_post_count or 0) + 1
                            print(f"  ✅ DraftPost 저장 (HTTP): {post_url[:60]}...")
                        else:
                            print(f"  ℹ️  DraftPost 이미 존재: {post_url[:60]}...")
                    else:
                        print(f"  ⚠️  CafeAccountLink 없음 (cafe_id={task.cafe_id})")
                except Exception as dp_err:
                    print(f"  ⚠️ DraftPost 저장 실패: {dp_err}")

            # ★ post 완료 시 DraftPost modified_url만 저장 (used 처리는 댓글 전체 완료 후)
            if (task.task_type == 'post'
                    and task.error_message
                    and 'MODIFY_URL:' in task.error_message
                    and post_url):
                try:
                    draft_url_val = task.error_message.split('MODIFY_URL:')[1].split('|')[0].strip()
                    draft_post = db.query(DraftPost).filter(DraftPost.draft_url == draft_url_val).first()
                    if draft_post:
                        draft_post.modified_url = post_url
                        print(f"  📌 DraftPost #{draft_post.id} modified_url 저장 (used 처리는 댓글 완료 후)")
                except Exception as dp_err:
                    print(f"  ⚠️ DraftPost modified_url 저장 실패: {dp_err}")

            db.commit()
            print(f"✅ Task #{task_id} 완료 (HTTP, type:{task.task_type}, seq:{task.order_sequence})")

            # 락 해제 전 필요한 정보만 추출
            _task_type = task.task_type
            _parent_id = task.parent_task_id
            _order_seq = task.order_sequence
            _cafe_id = task.cafe_id

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)

    # ── 3단계: 즉시 응답 (락 완전 해제 후) ──
    # 백그라운드 Task 생성은 응답 반환 뒤에 처리되므로 Worker 절대 타임아웃 없음
    if _task_type:
        asyncio.create_task(
            _dispatch_next_task_bg(
                task_id=task_id,
                task_type=_task_type,
                parent_task_id=_parent_id,
                order_sequence=_order_seq,
                cafe_id=_cafe_id
            )
        )

    return JSONResponse({'success': True})


@router.post("/api/tasks/{task_id}/fail")
async def fail_task(
    task_id: int,
    error: str = Form(None),
    db: Session = Depends(get_db)
):
    """Task 실패 보고 (HTTP API) - WebSocket이 끊겼을 때 백업용"""
    try:
        task = db.query(AutomationTask).get(task_id)
        if not task:
            return JSONResponse({'success': False, 'error': 'Task not found'}, status_code=404)

        if task.status in ('completed', 'failed', 'cancelled'):
            return JSONResponse({'success': True, 'message': f'이미 {task.status} 상태'})

        _failed_task_type = task.task_type
        task.status = 'failed'
        task.error_message = error or '작업 실패'
        task.retry_count = (task.retry_count or 0) + 1
        db.commit()
        print(f"❌ Task #{task_id} 실패 처리 완료 (HTTP, type:{_failed_task_type}, 사유: {(error or '')[:80]})")

        # post 실패 → 다음 AI 그룹
        if _failed_task_type == 'post':
            asyncio.create_task(_dispatch_next_group_on_failure(task_id))
        # create_draft 실패 → 해당 PC에 다음 대기 태스크 전송
        elif _failed_task_type == 'create_draft':
            _pc_id = task.assigned_pc_id
            if _pc_id:
                asyncio.create_task(_try_send_next_pending_task(_pc_id, db))

        return JSONResponse({'success': True})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.delete("/api/tasks/failed/all")
async def delete_all_failed_tasks(db: Session = Depends(get_db)):
    """실패한 Task 전체 삭제"""
    try:
        failed_root_ids = [t.id for t in db.query(AutomationTask).filter(
            AutomationTask.status == 'failed',
            AutomationTask.parent_task_id == None,
            AutomationTask.task_type.in_(['post', 'create_draft'])
        ).all()]

        total_deleted = 0
        for root_id in failed_root_ids:
            children = db.query(AutomationTask).filter(AutomationTask.parent_task_id == root_id).all()
            child_ids = [c.id for c in children]
            for cid in child_ids:
                grandchildren = db.query(AutomationTask).filter(AutomationTask.parent_task_id == cid).all()
                gc_ids = [gc.id for gc in grandchildren]
                if gc_ids:
                    db.query(AutomationTask).filter(AutomationTask.id.in_(gc_ids)).delete(synchronize_session=False)
                    total_deleted += len(gc_ids)
            if child_ids:
                db.query(AutomationTask).filter(AutomationTask.id.in_(child_ids)).delete(synchronize_session=False)
                total_deleted += len(child_ids)
            db.query(AutomationTask).filter(AutomationTask.id == root_id).delete(synchronize_session=False)
            total_deleted += 1

        db.commit()
        print(f"🗑️ 실패 작업 전체 삭제: {total_deleted}개 (root {len(failed_root_ids)}개)")
        return JSONResponse({'success': True, 'message': f'실패 작업 {total_deleted}개 삭제 완료', 'deleted': total_deleted})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """실패/완료된 Task 단건 삭제 (하위 댓글 포함)"""
    try:
        task = db.query(AutomationTask).get(task_id)
        if not task:
            return JSONResponse({'success': False, 'error': 'Task not found'}, status_code=404)
        if task.status in ('pending', 'assigned', 'in_progress'):
            return JSONResponse({'success': False, 'error': '진행 중인 작업은 삭제할 수 없습니다.'}, status_code=400)

        def _collect_children(parent_id):
            children = db.query(AutomationTask).filter(AutomationTask.parent_task_id == parent_id).all()
            ids = []
            for c in children:
                ids.append(c.id)
                ids.extend(_collect_children(c.id))
            return ids

        child_ids = _collect_children(task_id)
        if child_ids:
            db.query(AutomationTask).filter(AutomationTask.id.in_(child_ids)).delete(synchronize_session=False)
        db.delete(task)
        db.commit()
        total = 1 + len(child_ids)
        print(f"🗑️ Task #{task_id} 삭제 완료 (하위 {len(child_ids)}개 포함, 총 {total}개)")
        return JSONResponse({'success': True, 'message': f'Task #{task_id} 외 {len(child_ids)}개 삭제', 'deleted': total})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


@router.get("/api/worker/version")
async def get_worker_version():
    """Worker 버전 정보 제공"""
    return JSONResponse({
        "version": "2.6.0",
        "release_date": "2026-01-24",
        "download_url": "/automation/api/worker/download",
        "changelog": [
            "중복 Task 실행 방지 (이미 처리된 task_id 재수신 시 건너뜀)",
            "서버: 다음 댓글 전송 전 pending 상태 재확인으로 중복 전송 방지",
            "완료 신호 5분 재시도 + 큐 보관",
            "게시판 자동 변경 기능 추가",
            "FLUX 이미지 자동 다운로드 + 에디터 업로드 기능 추가",
            "draft_url 없을 때 즉시 실패 처리",
            "NoSuchWindowException 발생 시 브라우저 자동 재시작",
            "undetected-chromedriver + pyperclip 자동 설치",
            "등록 버튼 클릭 전후 alert 팝업 자동 처리",
            "글쓰기 버튼 클릭 후 활동정지 팝업 5초 감지 → 실패 사유 대시보드 표시",
            "create_draft 실패 시 HTTP 실패 보고 + 다음 태스크 자동 전송",
            "에디터 진입 후 네이버 HTML 모달 팝업 감지 → 탭 닫기 + 실패 사유 보고"
        ],
        "required_packages": {
            "selenium": "4.15.2",
            "websockets": "12.0",
            "psutil": "5.9.6",
            "requests": "2.31.0",
            "webdriver-manager": "4.0.1"
        }
    })


@router.get("/api/tasks/{task_id}/detail")
async def get_task_detail(task_id: int, db: Session = Depends(get_db)):
    """Task 상세 조회 (자식 태스크 전체 포함) - 내용 미리보기 모달용"""
    import json as _json

    def _serialize(t):
        image_urls_list = []
        if t.image_urls:
            try:
                image_urls_list = _json.loads(t.image_urls)
            except Exception:
                pass
        return {
            'id': t.id,
            'task_type': t.task_type,
            'mode': t.mode,
            'status': t.status,
            'title': t.title,
            'content': t.content or '',
            'parent_task_id': t.parent_task_id,
            'order_sequence': t.order_sequence or 0,
            'post_url': t.post_url,
            'keyword': t.keyword,
            'product_name': t.product_name,
            'image_urls': image_urls_list,
            'completed_at': t.completed_at.strftime('%Y-%m-%d %H:%M:%S') if t.completed_at else None,
        }

    try:
        root = db.query(AutomationTask).get(task_id)
        if not root:
            return JSONResponse({'success': False, 'error': 'Task not found'}, status_code=404)

        # 직접 자식 (댓글)
        direct_children = db.query(AutomationTask).filter(
            AutomationTask.parent_task_id == task_id
        ).order_by(AutomationTask.order_sequence.asc(), AutomationTask.id.asc()).all()

        # 댓글의 자식 (대댓글)
        child_ids = [c.id for c in direct_children]
        grandchildren = []
        if child_ids:
            grandchildren = db.query(AutomationTask).filter(
                AutomationTask.parent_task_id.in_(child_ids)
            ).order_by(AutomationTask.order_sequence.asc(), AutomationTask.id.asc()).all()

        return JSONResponse({
            'success': True,
            'root': _serialize(root),
            'children': [_serialize(c) for c in direct_children],
            'grandchildren': [_serialize(g) for g in grandchildren],
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({'success': False, 'error': str(e)}, status_code=500)


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
    try:
        cafe = db.query(AutomationCafe).filter(AutomationCafe.id == cafe_id).first()
        
        if not cafe:
            return JSONResponse({'success': False, 'message': '카페를 찾을 수 없습니다'}, status_code=404)
        
        # URL 중복 확인 (자기 자신 제외)
        existing = db.query(AutomationCafe).filter(
            AutomationCafe.url == cafe_url,
            AutomationCafe.id != cafe_id
        ).first()
        if existing:
            return JSONResponse({'success': False, 'message': f'이미 등록된 URL입니다: {existing.name}'})
        
        cafe.name = cafe_name
        cafe.url = cafe_url
        cafe.characteristics = characteristics
        cafe.target_board = target_board
        cafe.status = status
        
        db.commit()
        
        return JSONResponse({'success': True, 'message': '카페가 수정되었습니다'})
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        return JSONResponse({'success': False, 'message': f'수정 오류: {str(e)}'}, status_code=500)


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

@router.get("/api/worker/version/db")
async def get_worker_version_db(db: Session = Depends(get_db)):
    """Worker 최신 버전 정보 (DB 기반, 관리자용)"""
    try:
        latest = db.query(WorkerVersion).filter(
            WorkerVersion.is_active == True
        ).first()
        
        if not latest:
            return {
                "version": "1.2.0",
                "changelog": []
            }
        
        changelog = latest.changelog.split('\n') if latest.changelog else []
        
        return {
            "version": latest.version,
            "changelog": [line for line in changelog if line.strip()]
        }
    except Exception as e:
        return {
            "version": "1.2.0",
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

