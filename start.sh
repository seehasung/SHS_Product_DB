#!/bin/bash

# 데이터베이스를 최신 상태로 마이그레이션 (테이블 생성)
alembic upgrade head

# Uvicorn 서버 실행
uvicorn main:app --host 0.0.0.0 --port 10000