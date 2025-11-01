# scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from sqlalchemy import and_
import asyncio

from database import SessionLocal, TaskAssignment, TaskNotification, User, get_kst_now, KST
from websocket_manager import manager

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


def start_scheduler():
    """스케줄러 시작"""
    
    # ⭐ 반복 알림: 30분마다 실행 (중복 제거)
    scheduler.add_job(
        send_pending_notifications,
        trigger=IntervalTrigger(minutes=30),
        id='pending_notifications',
        name='미완료 업무 알림',
        replace_existing=True
    )
    
    # ⭐ 중복 스케줄 제거 (위에서 모두 처리)
    
    # 오래된 알림 정리: 매일 자정에 실행
    scheduler.add_job(
        cleanup_old_notifications,
        trigger='cron',
        hour=0,
        minute=0,
        id='cleanup_notifications',
        name='오래된 알림 정리',
        replace_existing=True
    )
    
    scheduler.start()
    print("✅ 스케줄러 시작됨 (30분 간격, 퇴근 시간 17:00)")


def stop_scheduler():
    """스케줄러 종료"""
    scheduler.shutdown()
    print("⏹️ 스케줄러 종료됨")