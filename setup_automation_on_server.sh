#!/bin/bash
# 서버에서 자동화 시스템 설정 스크립트
# 실행: bash setup_automation_on_server.sh

echo "╔════════════════════════════════════════════════════════╗"
echo "║     자동화 시스템 서버 설정                            ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 현재 디렉토리 확인
if [ ! -f "main.py" ]; then
    echo "❌ 오류: 프로젝트 루트 디렉토리에서 실행하세요"
    echo "   현재 위치: $(pwd)"
    exit 1
fi

echo "✅ 프로젝트 디렉토리 확인: $(pwd)"
echo ""

# 1. Alembic 마이그레이션
echo "================================================"
echo "  1. 데이터베이스 마이그레이션"
echo "================================================"
echo ""

echo "🔄 Alembic 마이그레이션 실행 중..."
python -m alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ 마이그레이션 완료!"
else
    echo "❌ 마이그레이션 실패!"
    echo "   수동 실행: python -m alembic upgrade head"
    exit 1
fi

echo ""

# 2. 초기 데이터 설정 여부 확인
echo "================================================"
echo "  2. 초기 데이터 설정"
echo "================================================"
echo ""

echo "초기 데이터를 설정하시겠습니까? (y/n)"
echo "  - PC 8대 자동 등록"
echo "  - 계정 등록"
echo "  - 카페 등록"
echo "  - 프롬프트 등록"
echo ""

read -p "초기 데이터 설정 (y/n): " answer

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    echo ""
    echo "🔄 초기 데이터 설정 중..."
    python init_automation_data.py
else
    echo "⏭️  초기 데이터 설정 건너뜀 (나중에 웹에서 가능)"
fi

echo ""

# 3. 서비스 재시작 여부
echo "================================================"
echo "  3. 서비스 재시작"
echo "================================================"
echo ""

echo "서비스를 재시작하시겠습니까? (y/n)"
read -p "재시작 (y/n): " restart_answer

if [ "$restart_answer" = "y" ] || [ "$restart_answer" = "Y" ]; then
    echo ""
    echo "🔄 서비스 재시작 중..."
    
    # systemd 사용 시
    if systemctl is-active --quiet shs-product-db; then
        sudo systemctl restart shs-product-db
        echo "✅ systemd 서비스 재시작 완료"
    else
        # 수동 프로세스 재시작
        echo "⚠️  systemd 서비스를 찾을 수 없습니다"
        echo "   수동으로 재시작하세요"
    fi
fi

echo ""
echo "================================================"
echo "  설정 완료!"
echo "================================================"
echo ""
echo "✅ 자동화 시스템 서버 설정이 완료되었습니다!"
echo ""
echo "📝 다음 단계:"
echo "   1. 웹 접속: https://scorp274.com/automation/cafe"
echo "   2. 8대 PC에 Worker Agent 설치"
echo "   3. 테스트 작업 실행"
echo ""
echo "🎯 배포 성공을 기원합니다! 🚀"
echo ""

