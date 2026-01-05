"""
automation.py 파일 수정 스크립트
1471줄까지만 남기고 나머지 삭제
"""

# 파일 읽기
with open('routers/automation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1471줄까지만 유지
clean_lines = lines[:1471]

# 파일 쓰기
with open('routers/automation.py', 'w', encoding='utf-8') as f:
    f.writelines(clean_lines)

print(f"✅ 완료! {len(clean_lines)}줄로 정리됨")
print(f"삭제된 줄: {len(lines) - len(clean_lines)}줄")

