"""
Worker Agent 버전 업데이트 도구 v2
routers/automation.py의 API도 자동 업데이트!

실행: python update_worker_version_v2.py
"""

import sys
import re
from pathlib import Path
from datetime import datetime

def update_version():
    """버전 업데이트"""
    
    print("""
╔════════════════════════════════════════════════════════╗
║     Worker Agent 버전 업데이트 도구 v2                ║
║     모든 파일을 자동으로 업데이트합니다!               ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 1. 현재 버전 읽기
    worker_file = Path('worker_agent.py')
    
    with open(worker_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # VERSION 찾기
    version_match = re.search(r'VERSION = "([0-9.]+)"', content)
    if version_match:
        current_version = version_match.group(1)
        print(f"현재 버전: v{current_version}\n")
    else:
        current_version = "1.0.0"
        print("현재 버전을 찾을 수 없습니다\n")
    
    # 2. 새 버전 입력
    new_version = input(f"새 버전 (예: 1.0.2): ").strip()
    if not new_version:
        print("❌ 버전을 입력하세요")
        return
    
    # 버전 형식 검증
    if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', new_version):
        print("❌ 버전 형식이 올바르지 않습니다 (예: 1.0.2)")
        return
    
    # 3. 변경 사항 입력
    changelog = []
    print("\n변경 사항을 입력하세요 (빈 줄 입력 시 종료):")
    while True:
        change = input("  - ").strip()
        if not change:
            break
        changelog.append(change)
    
    if not changelog:
        changelog = ["버전 업데이트"]
    
    # 4. worker_agent.py VERSION 업데이트
    print("\n📝 파일 업데이트 중...\n")
    
    new_content = re.sub(
        r'VERSION = "[0-9.]+"',
        f'VERSION = "{new_version}"',
        content
    )
    
    with open(worker_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ worker_agent.py VERSION → v{new_version}")
    
    # 5. routers/automation.py API 업데이트
    automation_file = Path('routers/automation.py')
    
    with open(automation_file, 'r', encoding='utf-8') as f:
        automation_content = f.read()
    
    # 버전 정보 패턴 찾기
    pattern = r'@router\.get\("/api/worker/version"\)\s+async def get_worker_version\(\):[^}]+\{[^}]+\}'
    
    # 새 버전 정보 생성
    changelog_str = ",\n            ".join([f'"{c}"' for c in changelog])
    
    new_api_function = f'''@router.get("/api/worker/version")
async def get_worker_version():
    """Worker 버전 정보 제공"""
    return JSONResponse({{
        "version": "{new_version}",
        "release_date": "{datetime.now().strftime('%Y-%m-%d')}",
        "download_url": "/automation/api/worker/download",
        "changelog": [
            {changelog_str}
        ],
        "required_packages": {{
            "selenium": "4.15.2",
            "websockets": "12.0",
            "psutil": "5.9.6",
            "requests": "2.31.0",
            "webdriver-manager": "4.0.1"
        }}
    }})'''
    
    # 기존 함수를 새로운 것으로 교체
    if '@router.get("/api/worker/version")' in automation_content:
        # 함수 전체를 찾아서 교체 (더 안전한 방법)
        lines = automation_content.split('\n')
        new_lines = []
        skip_until_next_def = False
        
        for i, line in enumerate(lines):
            if '@router.get("/api/worker/version")' in line:
                # 새 함수 추가
                new_lines.append(new_api_function)
                skip_until_next_def = True
            elif skip_until_next_def:
                # 다음 @router 또는 class, def를 만날 때까지 건너뛰기
                if (line.strip().startswith('@router.') or 
                    line.strip().startswith('class ') or 
                    (line.strip().startswith('def ') and not line.strip().startswith('def get_worker_version'))):
                    skip_until_next_def = False
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        new_automation_content = '\n'.join(new_lines)
        
        with open(automation_file, 'w', encoding='utf-8') as f:
            f.write(new_automation_content)
        
        print(f"✅ routers/automation.py API 버전 → v{new_version}")
    else:
        print(f"⚠️  routers/automation.py에서 버전 API를 찾을 수 없습니다")
    
    # 완료
    print("\n" + "="*60)
    print("✅ 버전 업데이트 완료!")
    print("="*60)
    print(f"\n📦 새 버전: v{new_version}")
    print(f"📅 배포일: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"\n📝 변경 사항:")
    for change in changelog:
        print(f"   - {change}")
    
    print(f"\n🚀 다음 단계:")
    print(f"   1. git add .")
    print(f"   2. git commit -m 'Worker v{new_version} 업데이트'")
    print(f"   3. git push origin main")
    print(f"   4. 각 PC에서 Worker 재시작")
    print(f"\n💡 각 PC는 자동으로 v{new_version}으로 업데이트됩니다!")


if __name__ == "__main__":
    try:
        update_version()
    except KeyboardInterrupt:
        print("\n\n⏹️ 취소됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()

