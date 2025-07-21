# database.py

import os # os 모듈을 임포트합니다.
from dotenv import load_dotenv # .env 파일을 읽기 위한 load_dotenv 함수를 임포트합니다.

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from passlib.hash import bcrypt

# --- 변경 시작 ---

# 1. .env 파일에서 환경 변수를 로드합니다.
# 이 코드가 있어야 .env 파일에 설정된 DATABASE_URL 값을 읽어올 수 있습니다.
load_dotenv()

# 2. 환경 변수에서 데이터베이스 URL을 가져옵니다.
# Render에서 복사한 PostgreSQL 연결 URL이 DATABASE_URL이라는 환경 변수로 설정되어 있을 것입니다.
# 만약 환경 변수가 설정되지 않았다면, 프로그램을 시작할 수 없도록 오류를 발생시킵니다.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 3. 데이터베이스 엔진 생성
# 이제 환경 변수에서 가져온 URL을 사용하여 PostgreSQL 데이터베이스에 연결합니다.
# SQLite 전용 설정인 connect_args={"check_same_thread": False}는 PostgreSQL에서 필요 없으므로 제거합니다.
engine = create_engine(DATABASE_URL)

# --- 변경 끝 ---

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# 사용자 테이블 정의 (기존과 동일)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False) # 권한 필드 추가

# 상품 테이블 정의 (기존과 동일)
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String, unique=True, index=True, nullable=False) # 사용자 정의 상품 ID
    name = Column(String(255), nullable=False) # 상품명
    price = Column(Integer)
    kd_paid = Column(Boolean, default=False) # 경동 대납 여부
    customs_paid = Column(Boolean, default=False) # 관세 대납 여부
    customs_cost = Column(Integer, default=0)     # 관세 신고단가
    coupang_link = Column(String(2083)) # 쿠팡 상품 페이지 URL
    taobao_link = Column(String(2083)) # 타오바오 상품 페이지 URL
    coupang_options = Column(Text) # 쿠팡 옵션 목록 (이름과 가격 JSON 등으로 저장)
    taobao_options = Column(Text) # 타오바오 옵션 목록 (JSON 문자열 등)
    thumbnail = Column(String(2083)) # 썸네일 이미지 URL
    details = Column(Text) # 제품 상세 정보 (예상 CS 답변 등)

__all__ = ["User", "Product", "SessionLocal", "Base"]

# ✅ 최초 관리자 계정 생성 (한 번만 실행되도록)
# 이 함수는 데이터베이스가 비어있을 때만 실행됩니다.
# 새로운 PostgreSQL DB는 비어있을 테니, 웹 서버를 처음 실행할 때 이 관리자 계정이 생성될 거예요.
def create_super_admin():
    db = SessionLocal()
    try: # 예외 처리를 추가하여 데이터베이스 커밋 실패 시 롤백하도록 합니다.
        if db.query(User).count() == 0:
            super_admin = User(
                username="shsboss274", # 원하는 아이디
                password=bcrypt.hash("shsboss274"), # 원하는 비밀번호
                is_admin=True
            )
            db.add(super_admin)
            db.commit()
            print("✅ 최초 관리자 계정이 생성되었습니다. (shsboss274 / shsboss274)")
    except Exception as e:
        db.rollback() # 오류 발생 시 변경사항 되돌리기
        print(f"관리자 계정 생성 중 오류 발생: {e}")
    finally:
        db.close()

# DB 테이블 생성 및 최초 관리자 등록
# 이 두 줄은 main.py에서 Base.metadata.create_all(bind=engine)를 이미 호출하고 있으므로
# 여기서는 주석 처리하거나 제거하는 것이 좋습니다.
# main.py에서 한 번만 호출되면 됩니다.
#Base.metadata.create_all(bind=engine)
#create_super_admin() # 이 함수는 main.py에서 호출하거나, 초기 실행 스크립트에서 호출하는 것이 좋습니다.