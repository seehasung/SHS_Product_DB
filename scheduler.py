# scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from sqlalchemy import and_
import asyncio

from database import SessionLocal, TaskAssignment, TaskNotification, User, Order, get_kst_now, KST
from websocket_manager import manager

# ⭐ 통관 절차 이상 캐시 (메모리)
customs_issue_cache = {
    'orders': [],
    'last_checked': None,
    'count': 0
}

# ⭐ 네이버 송장 흐름 캐시 (메모리)
naver_delivery_cache = {
    'count': 0,
    'last_checked': None
}

scheduler = AsyncIOScheduler()

async def send_pending_notifications():
    """미완료 업무에 대한 반복 알림 전송"""
    db = SessionLocal()
    try:
        now = get_kst_now()
        
        # ⭐ 퇴근 1시간 전인지 확인 (17시 기준 - 16시부터)
        work_end_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
        one_hour_before_end = work_end_time - timedelta(hours=1)
        is_near_work_end = now >= one_hour_before_end and now < work_end_time
        
        # ⭐ 미완료 업무 조회 (취소/완료 제외)
        pending_tasks = db.query(TaskAssignment).filter(
            TaskAssignment.status.in_(['new', 'confirmed', 'in_progress']),
            TaskAssignment.status.not_in(['completed', 'cancelled'])  # ⭐ 명시적 제외
        ).all()
        
        for task in pending_tasks:
            if not task.assignee_id:
                continue
            
            # 알림 전송 조건 확인
            should_notify = False
            notification_message = ""
            
            # 긴급 업무는 항상 알림
            if task.priority == 'urgent':
                should_notify = True
                notification_message = f"🔴 긴급 업무: {task.title}"
            
            # ⭐ 퇴근 1시간 전부터는 알림 (16:00 ~ 17:00)
            elif is_near_work_end:
                should_notify = True
                notification_message = f"⏰ 퇴근 전 미완료: {task.title}"
            
            # 마감 임박 (2시간 이내)
            elif task.deadline and task.deadline <= now + timedelta(hours=2):
                should_notify = True
                notification_message = f"⚠️ 마감 임박: {task.title}"
            
            if should_notify:
                # 알림 로그 생성
                notification = TaskNotification(
                    task_id=task.id,
                    user_id=task.assignee_id,
                    notification_type='deadline_warning',
                    message=notification_message,
                    auto_delete_at=get_kst_now() + timedelta(days=90)
                )
                db.add(notification)
                
                # WebSocket으로 실시간 알림 전송
                await manager.send_personal_message({
                    'type': 'task_notification',
                    'task_id': task.id,
                    'title': task.title,  # ⭐ 추가
                    'message': notification_message,
                    'priority': task.priority,
                    'status': task.status,  # ⭐ 추가
                    'creator_id': task.creator_id,  # ⭐ 추가
                    'creator_name': task.creator.username if task.creator else "알 수 없음",
                    'assignee_id': task.assignee_id,  # ⭐ 추가
                    'assignee_name': task.assignee.username if task.assignee else "알 수 없음",
                    'timestamp': get_kst_now().isoformat()
                }, task.assignee_id)
        
        db.commit()
        print(f"✅ 반복 알림 전송 완료: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ 알림 전송 오류: {e}")
        db.rollback()
    finally:
        db.close()


async def check_naver_delivery_flow():
    """네이버 송장 흐름 자동 체크 (카페24/스마트스토어 + 직접전달/자체배송)"""
    db = SessionLocal()
    try:
        from routers.orders import get_customs_info_auto, clean_tracking_number
        from quickstar_selenium_scraper import QuickstarSeleniumScraper
        
        now = get_kst_now()
        print(f"📦 네이버 송장 흐름 체크 시작: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # WebSocket 알림
        await manager.broadcast({
            'type': 'naver_delivery_check',
            'status': 'started',
            'message': '📦 네이버 송장 흐름 체크 시작...',
            'timestamp': now.isoformat()
        })
        
        # 카페24 또는 스마트스토어 주문
        all_orders = db.query(Order).all()
        
        target_orders = []
        cafe24_count = 0
        naver_count = 0
        
        for order in all_orders:
            sales_channel = str(order.sales_channel or '')
            courier = str(order.courier_company or '')
            
            # 판매처: 카페24 또는 스마트스토어
            is_cafe24 = ('카페24' in sales_channel or 'cafe24' in sales_channel.lower())
            is_naver = ('스마트스토어' in sales_channel or 'smartstore' in sales_channel.lower())
            is_target_channel = is_cafe24 or is_naver
            
            # 택배사: 직접전달 또는 자체배송
            is_target_courier = ('직접전달' in courier or '자체배송' in courier)
            
            if is_target_channel and is_target_courier:
                target_orders.append(order)
                
                if is_cafe24:
                    cafe24_count += 1
                elif is_naver:
                    naver_count += 1
        
        print(f"  📋 대상 주문: {len(target_orders)}건 (카페24: {cafe24_count}건, 네이버: {naver_count}건)")
        
        ready_count = 0  # 반출신고 완료 건수
        checked_count = 0
        scraper = QuickstarSeleniumScraper()  # ⭐ Selenium 사용
        
        for order in target_orders:
            try:
                tracking = clean_tracking_number(order.tracking_number)
                is_cafe24 = '카페24' in str(order.sales_channel or '')
                
                # 카페24 (자체배송 + 송장번호 있음)
                if is_cafe24 and tracking and len(tracking) >= 12:
                    print(f"  📦 카페24 주문: {order.order_number}, 송장: {tracking}")
                
                # 네이버 (직접전달 + 송장번호 없음)
                elif not tracking or len(tracking) < 12:
                    # quickstar에서 송장번호 조회
                    if not order.taobao_order_number:
                        continue
                    
                    print(f"  📦 네이버 주문: {order.order_number}, 타오바오: {order.taobao_order_number}")
                    
                    tracking = scraper.get_tracking_number(order.taobao_order_number)
                    if not tracking:
                        continue
                
                # 통관 API 조회
                customs_result = get_customs_info_auto(
                    tracking_number=tracking,
                    master_bl=order.master_bl,
                    house_bl=order.house_bl,
                    order_date=str(order.order_date) if order.order_date else None
                )
                
                if customs_result.get("success"):
                    history = customs_result.get("history", [])
                    
                    # 반출신고가 있으면 카운트
                    has_release = any("반출신고" in str(h.get("process_type", "")) for h in history)
                    
                    if has_release:
                        ready_count += 1
                        print(f"  ✅ 반출신고 완료: {order.order_number}")
                
                checked_count += 1
                
            except Exception as e:
                print(f"  ❌ 체크 오류: {order.order_number} - {e}")
                continue
        
        # 캐시 저장
        naver_delivery_cache['count'] = ready_count
        naver_delivery_cache['last_checked'] = now
        
        elapsed_time = (get_kst_now() - now).total_seconds()
        
        print(f"✅ 네이버 송장 흐름 체크 완료: {ready_count}건 (총 {checked_count}건 체크, 소요 시간: {elapsed_time:.1f}초)")
        
        # ⭐ Selenium 브라우저 종료
        scraper.close()
        
        # WebSocket 알림
        await manager.broadcast({
            'type': 'naver_delivery_check',
            'status': 'completed',
            'message': f'✅ 네이버 송장 흐름 체크 완료! 반출신고: {ready_count}건',
            'count': ready_count,
            'checked_count': checked_count,
            'elapsed_time': round(elapsed_time, 1),
            'timestamp': get_kst_now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ 네이버 송장 흐름 체크 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


async def cleanup_old_notifications():
    """3개월 지난 알림 자동 삭제"""
    db = SessionLocal()
    try:
        now = datetime.now()
        
        # auto_delete_at이 지난 알림 삭제
        deleted_count = db.query(TaskNotification).filter(
            TaskNotification.auto_delete_at <= now
        ).delete()
        
        db.commit()
        
        if deleted_count > 0:
            print(f"🗑️ 오래된 알림 {deleted_count}개 삭제됨")
        
    except Exception as e:
        print(f"❌ 알림 정리 오류: {e}")
        db.rollback()
    finally:
        db.close()


async def check_customs_issues():
    """통관 절차 이상 자동 체크 (10일 지난 배송중/반품 중 반출신고 없음)"""
    db = SessionLocal()
    try:
        from datetime import date, timedelta
        from routers.orders import normalize_order_status, clean_tracking_number, get_customs_info_auto
        
        now = get_kst_now()
        print(f"🔍 통관 절차 이상 자동 체크 시작: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # ⭐ WebSocket 알림: 체크 시작
        await manager.broadcast({
            'type': 'customs_check_progress',
            'status': 'started',
            'message': '🔍 통관 절차 체크 시작...',
            'timestamp': now.isoformat()
        })
        
        ten_days_ago = (date.today() - timedelta(days=10)).strftime('%Y-%m-%d')
        
        # 10일 지난 주문
        old_orders = db.query(Order).filter(
            Order.order_date < ten_days_ago
        ).all()
        
        issue_orders = []
        checked_count = 0
        
        for order in old_orders:
            # 배송중 또는 반품 상태만
            normalized_status = normalize_order_status(order.order_status, db)
            if normalized_status not in ['배송중', '반품']:
                continue
            
            # 송장번호 확인
            tracking = clean_tracking_number(order.tracking_number)
            if not tracking:
                continue
            
            # 통관 API 조회
            try:
                customs_result = get_customs_info_auto(
                    tracking_number=tracking,
                    master_bl=order.master_bl,
                    house_bl=order.house_bl,
                    order_date=str(order.order_date) if order.order_date else None
                )
                
                if customs_result.get("success"):
                    history = customs_result.get("history", [])
                    
                    # 반출신고가 없으면 이상
                    has_release = any("반출신고" in str(h.get("process_type", "")) for h in history)
                    
                    if not has_release:
                        issue_orders.append({
                            'order_id': order.id,
                            'order_number': order.order_number,
                            'tracking_number': tracking,
                            'order_status': order.order_status,
                            'order_date': str(order.order_date)
                        })
                
                checked_count += 1
                
                # ⭐ 제한 없이 모두 체크
                
            except Exception as e:
                print(f"  ❌ 통관 조회 오류: {order.order_number} - {e}")
                continue
        
        # 캐시에 저장
        customs_issue_cache['orders'] = issue_orders
        customs_issue_cache['last_checked'] = now
        customs_issue_cache['count'] = len(issue_orders)
        
        elapsed_time = (get_kst_now() - now).total_seconds()
        
        print(f"✅ 통관 절차 이상 체크 완료: {len(issue_orders)}건 발견 (총 {checked_count}건 체크, 소요 시간: {elapsed_time:.1f}초)")
        
        # ⭐ WebSocket 알림: 체크 완료
        await manager.broadcast({
            'type': 'customs_check_progress',
            'status': 'completed',
            'message': f'✅ 체크 완료! 발견: {len(issue_orders)}건',
            'count': len(issue_orders),
            'checked_count': checked_count,
            'elapsed_time': round(elapsed_time, 1),
            'timestamp': get_kst_now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ 통관 절차 이상 체크 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def start_scheduler():
    """스케줄러 시작"""
    
    # ⭐ 반복 알림: 30분마다 실행
    scheduler.add_job(
        send_pending_notifications,
        trigger=IntervalTrigger(minutes=30),
        id='pending_notifications',
        name='미완료 업무 알림',
        replace_existing=True
    )
    
    # 오래된 알림 정리: 매일 자정
    scheduler.add_job(
        cleanup_old_notifications,
        trigger='cron',
        hour=0,
        minute=0,
        id='cleanup_notifications',
        name='오래된 알림 정리',
        replace_existing=True
    )
    
    # ⭐ 통관 절차 이상 자동 체크: 매일 13시, 18시
    scheduler.add_job(
        check_customs_issues,
        trigger='cron',
        hour='13,18',
        minute=0,
        id='customs_issue_check',
        name='통관 절차 이상 자동 체크',
        replace_existing=True
    )
    
    # ⭐ 네이버 송장 흐름 자동 체크: 9시, 13시 30분, 16시 30분
    # 9시 (0분)
    scheduler.add_job(
        check_naver_delivery_flow,
        trigger='cron',
        hour=9,
        minute=0,
        id='naver_delivery_check_09',
        name='네이버 송장 흐름 체크 (09:00)',
        replace_existing=True
    )
    
    # 13시 30분
    scheduler.add_job(
        check_naver_delivery_flow,
        trigger='cron',
        hour=13,
        minute=30,
        id='naver_delivery_check_13',
        name='네이버 송장 흐름 체크 (13:30)',
        replace_existing=True
    )
    
    # 18시 30분 (오후 6시 반)
    scheduler.add_job(
        check_naver_delivery_flow,
        trigger='cron',
        hour=18,
        minute=30,
        id='naver_delivery_check_18',
        name='네이버 송장 흐름 체크 (18:30)',
        replace_existing=True
    )
    
    # ─── AI 자동화 스케줄 체크 (1분마다) ───
    scheduler.add_job(
        check_ai_schedules,
        trigger=IntervalTrigger(minutes=1),
        id='check_ai_schedules',
        name='AI 자동화 스케줄 체크',
        replace_existing=True,
        coalesce=True,        # 밀린 실행 하나로 합치기 (missed 누적 방지)
        max_instances=1,      # 동시 실행 1개만 허용
        misfire_grace_time=30 # 30초 이내 지연은 실행 허용
    )

    # ─── 고아 댓글 Task 복구 (3분마다) ───
    scheduler.add_job(
        recover_orphaned_comment_tasks,
        trigger=IntervalTrigger(minutes=3),
        id='recover_orphaned_comments',
        name='고아 댓글 Task 자동 복구',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60
    )

    scheduler.start()
    print("✅ 스케줄러 시작됨")
    print("   - 미완료 업무 알림: 30분마다")
    print("   - 알림 정리: 매일 자정")
    print("   - 통관 절차 이상 체크: 매일 13시, 18시")
    print("   - 네이버 송장 흐름 체크: 매일 9시, 13시 30분, 18시 30분")
    print("   - AI 자동화 스케줄 체크: 1분마다")
    print("   - 고아 댓글 Task 복구: 3분마다")


async def check_ai_schedules():
    """AI 자동화 스케줄 (신규발행 + 수정발행) 실행 체크 - 1분마다"""
    from database import AIMarketingSchedule, DraftCreationSchedule, AutomationTask
    from routers.ai_automation import _execute_ai_schedule, _execute_draft_schedule
    from datetime import timedelta

    db = SessionLocal()
    now = get_kst_now()
    try:
        # ── 고착 태스크 자동 복구 ─────────────────────────────────────
        # 10분 이상 in_progress/assigned 상태인 post 태스크 → pending 리셋
        # (워커 완료 보고 타임아웃으로 상태가 변경 안 된 경우 복구)
        stuck_threshold = now - timedelta(minutes=10)
        stuck_tasks = db.query(AutomationTask).filter(
            AutomationTask.status.in_(['in_progress', 'assigned']),
            AutomationTask.task_type.in_(['post', 'comment', 'reply', 'create_draft']),
            AutomationTask.updated_at <= stuck_threshold,
        ).all()
        for st in stuck_tasks:
            st.status = 'pending'
            print(f"🔄 고착 태스크 #{st.id} ({st.task_type}) → pending 리셋 (마지막 업데이트: {st.updated_at})")
        if stuck_tasks:
            db.commit()
            print(f"✅ 고착 태스크 {len(stuck_tasks)}개 복구 완료")
            # ⭐ 리셋 직후 복구 잡 즉시 실행 (3분 주기 기다리지 않고 바로 재전송)
            asyncio.create_task(recover_orphaned_comment_tasks())

        # ── 신규발행(인사글) 스케줄 ──
        draft_schedules = db.query(DraftCreationSchedule).filter(
            DraftCreationSchedule.is_active == True,
            DraftCreationSchedule.next_run_at != None,
            DraftCreationSchedule.next_run_at <= now,
        ).all()
        for s in draft_schedules:
            try:
                print(f"🚀 [신규발행 스케줄 #{s.id}] 자동 실행")
                await _execute_draft_schedule(s.id, db)
            except Exception as e:
                print(f"⚠️ 신규발행 스케줄 #{s.id} 실행 오류: {e}")

        # ── 수정발행(AI) 스케줄 ──
        ai_schedules = db.query(AIMarketingSchedule).filter(
            AIMarketingSchedule.is_active == True,
            AIMarketingSchedule.next_run_at != None,
            AIMarketingSchedule.next_run_at <= now,
        ).all()
        for s in ai_schedules:
            try:
                print(f"🚀 [AI 수정발행 스케줄 #{s.id}] 자동 실행")
                await _execute_ai_schedule(s.id, db)
            except Exception as e:
                print(f"⚠️ AI 수정발행 스케줄 #{s.id} 실행 오류: {e}")
    except Exception as e:
        print(f"⚠️ check_ai_schedules 오류: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


async def recover_orphaned_comment_tasks():
    """3분마다: pending 상태로 방치된 모든 task(post/comment/reply) 자동 복구 및 전송
    - post/create_draft: PC 연결 + idle이면 즉시 전송 (서버 재시작 후 리셋된 케이스 복구)
    - comment/reply: 부모 post 완료 + 순서 맞으면 즉시 전송 (체인 단절 복구)
    """
    from database import AutomationTask, AutomationWorkerPC
    from routers.automation import worker_connections, send_task_to_worker, _is_comment_ready

    db = SessionLocal()
    try:
        post_dispatched = 0
        comment_dispatched = 0
        skipped = 0

        # ── 1. pending post/create_draft task 복구 ─────────────────────────
        # (서버 재시작 or 스케줄러 리셋 후 PC가 이미 연결된 상태라 재연결 핸들러가 안 도는 케이스)
        pending_posts = db.query(AutomationTask).filter(
            AutomationTask.status.in_(['pending', 'assigned']),
            AutomationTask.task_type.in_(['post', 'create_draft']),
            AutomationTask.assigned_pc_id != None,
        ).order_by(AutomationTask.id.asc()).all()

        for task in pending_posts:
            # 할당된 PC의 pc_number 조회
            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == task.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == task.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else task.assigned_pc_id

            if pc_num not in worker_connections:
                skipped += 1
                continue  # PC 미연결 → 재연결 시 처리됨

            # 이 PC에 현재 in_progress인 task가 있으면 스킵 (작업 중)
            in_progress_check = db.query(AutomationTask).filter(
                AutomationTask.assigned_pc_id.in_([task.assigned_pc_id, pc_num]),
                AutomationTask.status == 'in_progress',
            ).first()
            if in_progress_check:
                skipped += 1
                continue

            try:
                print(f"   🔧 [복구-post] Task #{task.id} ({task.task_type}) → PC #{pc_num}")
                await send_task_to_worker(pc_num, task, db)
                post_dispatched += 1
            except Exception as _e:
                print(f"   ⚠️ [복구-post] Task #{task.id} 전송 실패: {_e}")

        # ── 2. pending comment/reply task 복구 ─────────────────────────────
        # (부모 post 완료됐는데 첫 댓글이 전송 안 된 케이스)
        stuck_comments = db.query(AutomationTask).filter(
            AutomationTask.status == 'pending',  # assigned는 이미 전송됨, in_progress는 작업중
            AutomationTask.task_type.in_(['comment', 'reply']),
            AutomationTask.assigned_pc_id != None,
        ).order_by(AutomationTask.order_sequence.asc()).all()

        # root post 기준으로 그룹핑 → 각 그룹에서 하나만 전송 (순서 보장)
        dispatched_roots = set()

        for task in stuck_comments:
            if not _is_comment_ready(task, db):
                skipped += 1
                continue

            # 루트 post id 찾기
            root = task
            for _ in range(10):
                if root.task_type == 'post':
                    break
                if not root.parent_task_id:
                    break
                root = db.query(AutomationTask).get(root.parent_task_id)
                if not root:
                    break

            root_id = root.id if root and root.task_type == 'post' else None
            if root_id in dispatched_roots:
                continue  # 같은 그룹은 하나만

            pc_rec = db.query(AutomationWorkerPC).filter(
                (AutomationWorkerPC.id == task.assigned_pc_id) |
                (AutomationWorkerPC.pc_number == task.assigned_pc_id)
            ).first()
            pc_num = pc_rec.pc_number if pc_rec else task.assigned_pc_id

            if pc_num not in worker_connections:
                skipped += 1
                continue

            # ★ 전송 직전 DB 상태 재확인 (race condition 방지)
            db.refresh(task)
            if task.status != 'pending':
                skipped += 1
                continue

            try:
                print(f"   🔧 [복구-comment] Task #{task.id} (순서:{task.order_sequence}) → PC #{pc_num}")
                await send_task_to_worker(pc_num, task, db)
                comment_dispatched += 1
                if root_id:
                    dispatched_roots.add(root_id)
            except Exception as _e:
                print(f"   ⚠️ [복구-comment] Task #{task.id} 전송 실패: {_e}")

        total = post_dispatched + comment_dispatched
        if total > 0 or skipped > 0:
            print(f"🔧 [Task 복구] post:{post_dispatched} comment:{comment_dispatched} 전송 / 스킵:{skipped}")

    except Exception as e:
        print(f"⚠️ recover_orphaned_comment_tasks 오류: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


def stop_scheduler():
    """스케줄러 종료"""
    scheduler.shutdown()
    print("⏹️ 스케줄러 종료됨")