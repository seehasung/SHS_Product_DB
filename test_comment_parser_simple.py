"""
댓글 원고 파싱 간단 테스트
"""

from utils.comment_parser import parse_comment_scripts, validate_comment_scripts

# 테스트 데이터
test_script = """
1-1: PC1 도와주세요
1-2: PC2 저도 궁금하네요
1-3: PC1 오 대박

2-1: PC3 다들 고민이네요
2-2: PC1 맞아요
"""

print("="*60)
print("댓글 원고 파싱 테스트")
print("="*60)

# 파싱
scripts = parse_comment_scripts(test_script)

print(f"\n파싱된 댓글: {len(scripts)}개")
for script in scripts:
    comment_type = "새 댓글" if script['is_new'] else "대댓글"
    print(f"  [{script['group']}-{script['sequence']}] PC{script['pc']}: {script['content'][:20]}... ({comment_type})")

# 유효성 검증
print("\n" + "="*60)
print("유효성 검증")
print("="*60)

validation = validate_comment_scripts(scripts)
if validation['valid']:
    print("OK - 유효성 검증 통과!")
else:
    print("ERROR - 유효성 검증 실패:")
    for error in validation['errors']:
        print(f"  - {error}")

print("\n" + "="*60)
print("테스트 완료!")
print("="*60)

