"""
Worker Agent 버전 업데이트 도구
새 버전을 배포하면 모든 PC가 자동으로 업데이트됩니다

실행: python update_worker_version.py
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

def update_version():
    """버전 업데이트"""
    
    print("""
╔════════════════════════════════════════════════════════╗
║     Worker Agent 버전 업데이트 도구                    ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 현재 버전 파일 읽기
    version_file = Path('static/worker_version.json')
    
    if version_file.exists():
        with open(version_file, 'r', encoding='utf-8') as f:
            current_info = json.load(f)
        
        print(f"현재 버전: {current_info['version']}")
        print(f"배포일: {current_info['release_date']}\n")
    else:
        current_info = {
            'version': '0.0.0',
            'release_date': '',
            'changelog': []
        }
        print("현재 버전 파일이 없습니다\n")
    
    # 새 버전 입력
    print("새 버전 정보를 입력하세요:\n")
    
    new_version = input(f"버전 (예: 1.0.1): ").strip()
    if not new_version:
        print("❌ 버전을 입력하세요")
        return
    
    # 변경 사항 입력
    changelog = []
    print("\n변경 사항을 입력하세요 (빈 줄 입력 시 종료):")
    while True:
        change = input("  - ").strip()
        if not change:
            break
        changelog.append(change)
    
    # 새 버전 정보 생성
    new_info = {
        'version': new_version,
        'release_date': datetime.now().strftime('%Y-%m-%d'),
        'download_url': '/static/worker_files/worker_agent.py',
        'changelog': changelog,
        'required_packages': {
            'selenium': '4.15.2',
            'websockets': '12.0',
            'psutil': '5.9.6',
            'requests': '2.31.0',
            'webdriver-manager': '4.0.1'
        }
    }
    
    # 파일 저장
    with open(version_file, 'w', encoding='utf-8') as f:
        json.dump(new_info, f, indent=2, ensure_ascii=False)
    
    # worker_agent.py 복사
    worker_src = Path('worker_agent.py')
    worker_dst = Path('static/worker_files/worker_agent.py')
    
    worker_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(worker_src, worker_dst)
    
    # worker_agent.py의 버전 번호 업데이트
    with open(worker_src, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # VERSION 상수 찾아서 교체
    import re
    content = re.sub(
        r'VERSION = "[0-9.]+"',
        f'VERSION = "{new_version}"',
        content
    )
    
    with open(worker_src, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 다시 복사
    shutil.copy(worker_src, worker_dst)
    
    print("\n" + "="*60)
    print("✅ 버전 업데이트 완료!")
    print("="*60)
    print(f"\n📦 새 버전: v{new_version}")
    print(f"📅 배포일: {new_info['release_date']}")
    print(f"\n📝 변경 사항:")
    for change in changelog:
        print(f"   - {change}")
    
    print(f"\n📁 파일 위치:")
    print(f"   - {version_file}")
    print(f"   - {worker_dst}")
    
    print(f"\n🚀 다음 단계:")
    print(f"   1. Git 커밋 및 푸시")
    print(f"   2. 서버 자동 배포")
    print(f"   3. 각 PC에서 Worker 재시작")
    print(f"   4. 자동으로 v{new_version}으로 업데이트됨!")
    
    print(f"\n💡 각 PC는 다음 실행 시 자동으로 업데이트됩니다!")


if __name__ == "__main__":
    try:
        update_version()
    except KeyboardInterrupt:
        print("\n\n⏹️ 취소됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()

