from database import Base, engine

print("📦 데이터베이스 테이블 생성 중...")
Base.metadata.create_all(bind=engine)
print("✅ 완료: csdata.db 파일이 생성되었습니다.")

