"""
이미지 다운로드 테스트
서버에서 이미지를 제대로 다운로드하는지 확인

실행: python test_image_download.py
"""

import requests
import tempfile
import os
from pathlib import Path
import urllib3

# SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_download():
    print("""
╔════════════════════════════════════════════════════════╗
║     이미지 다운로드 테스트                             ║
╚════════════════════════════════════════════════════════╝
    """)
    
    # 테스트용 이미지 URL
    test_urls = [
        "https://scorp274.com/static/uploads/blog_images/5b7aa101-6a6a-49c8-a1d1-cbd8e4bd26cd.png",
        "https://scorp274.com/static/uploads/blog_images/5e9eb055-3f51-4b2c-98be-83dfec0ba55b.png"
    ]
    
    # 또는 사용자 입력
    custom_url = input("이미지 URL (Enter=테스트 URL 사용): ").strip()
    
    urls = [custom_url] if custom_url else test_urls
    
    print("\n" + "="*60)
    print("다운로드 시작")
    print("="*60)
    
    for i, url in enumerate(urls, 1):
        print(f"\n이미지 {i}/{len(urls)}:")
        print(f"URL: {url}")
        
        try:
            # 다운로드
            print("다운로드 중...")
            response = requests.get(url, timeout=30, verify=False)
            
            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type')}")
            print(f"Content-Length: {len(response.content)} bytes")
            
            if response.status_code == 200:
                # 임시 폴더
                temp_dir = tempfile.gettempdir()
                print(f"\n임시 폴더: {temp_dir}")
                
                # 파일명 추출
                filename = url.split('/')[-1]
                print(f"파일명: {filename}")
                
                # 저장 경로
                temp_path = os.path.join(temp_dir, filename)
                print(f"저장 경로: {temp_path}")
                
                # 파일 저장
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"\n✅ 파일 저장 완료!")
                
                # 파일 확인
                if os.path.exists(temp_path):
                    file_size = os.path.getsize(temp_path)
                    print(f"✅ 파일 존재 확인!")
                    print(f"   크기: {file_size / 1024:.1f} KB")
                    print(f"   경로: {temp_path}")
                    
                    # 탐색기로 폴더 열기
                    open_folder = input("\n탐색기로 폴더를 열어볼까요? (y/n): ").lower()
                    if open_folder == 'y':
                        os.startfile(temp_dir)
                        print("✅ 탐색기 열림 - 파일을 직접 확인하세요!")
                else:
                    print("❌ 파일이 저장되지 않음!")
            else:
                print(f"❌ 다운로드 실패: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 오류: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)


if __name__ == "__main__":
    try:
        test_download()
    except KeyboardInterrupt:
        print("\n⏹️ 취소")




