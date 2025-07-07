# create_user.py

from database import SessionLocal, User
from passlib.hash import bcrypt

def create_user(username: str, password: str):
    db = SessionLocal()
    hashed_password = bcrypt.hash(password)

    user = User(username=username, password=hashed_password)
    db.add(user)
    try:
        db.commit()
        print(f"✅ 사용자 '{username}' 생성 완료")
    except Exception as e:
        db.rollback()
        print(f"❌ 사용자 생성 실패: {e}")
    finally:
        db.close()

# 실행
create_user("admin", "admin123")
