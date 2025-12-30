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
        from quickstar_scraper import QuickstarScraper
        
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
        for order in all_orders:
            sales_channel = (order.sales_channel or '').lower()
            courier = (order.courier_company or '').lower()
            
            # 판매처: 카페24 또는 스마트스토어
            is_target_channel = ('카페24' in sales_channel or 'cafe24' in sales_channel or 
                                '스마트스토어' in sales_channel or 'smartstore' in sales_channel)
            
            # 택배사: 직접전달 또는 자체배송
            is_target_courier = ('직접전달' in courier or '자체배송' in courier)
            
            if is_target_channel and is_target_courier:
                target_orders.append(order)
        
        print(f"  📋 대상 주문: {len(target_orders)}건")
        
        ready_count = 0  # 반출신고 완료 건수
        checked_count = 0
        scraper = QuickstarScraper()
        
        for order in target_orders:
            try:
                tracking = clean_tracking_number(order.tracking_number)
                
                # 카페24 (자체배송 + 송장번호 있음)
                if tracking and len(tracking) >= 12:
                    # 송장번호로 바로 조회
                    pass
                
                # 네이버 (직접전달 + 송장번호 없음)
                else:
                    # quickstar에서 송장번호 조회
                    if not order.taobao_order_number:
                        continue
                    
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
    
    # ⭐ 네이버 송장 흐름 자동 체크: 매일 14시, 19시
    scheduler.add_job(
        check_naver_delivery_flow,
        trigger='cron',
        hour='14,19',
        minute=0,
        id='naver_delivery_check',
        name='네이버 송장 흐름 자동 체크',
        replace_existing=True
    )
    
    scheduler.start()
    print("✅ 스케줄러 시작됨")
    print("   - 미완료 업무 알림: 30분마다")
    print("   - 알림 정리: 매일 자정")
    print("   - 통관 절차 이상 체크: 매일 13시, 18시")
    print("   - 네이버 송장 흐름 체크: 매일 14시, 19시")


def stop_scheduler():
    """스케줄러 종료"""
    scheduler.shutdown()
    print("⏹️ 스케줄러 종료됨")