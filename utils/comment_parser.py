"""
댓글 원고 파싱 유틸리티
형식: "1-1: PC1 도와주세요ㅠㅜㅠㅠㅠ"
"""

import re
from typing import List, Dict, Optional

def parse_comment_script(text: str) -> Optional[Dict]:
    """
    댓글 원고 한 줄 파싱
    
    입력 예시:
        "1-1: PC1 도와주세요ㅠㅜㅠㅠㅠ"
        "1-2: PC2 저도 궁금하네요"
        "2-1: PC3 다들 고민이..." (새 댓글)
        "2-2: PC1 와 헐 대박..." (2-1에 대한 대댓글)
    
    출력 예시:
        {
            'group': 1,
            'sequence': 1,
            'pc': 1,
            'content': '도와주세요ㅠㅜㅠㅠㅠ',
            'is_new': True
        }
    
    Args:
        text: 댓글 원고 한 줄
        
    Returns:
        파싱 결과 딕셔너리 또는 None (파싱 실패 시)
    """
    # 공백 제거
    text = text.strip()
    
    if not text:
        return None
    
    # 정규식 패턴: "1-1: PC1 내용"
    # 그룹1: 그룹 번호, 그룹2: 순서 번호, 그룹3: PC 번호, 그룹4: 내용
    pattern = r'^(\d+)-(\d+):\s*PC(\d+)\s+(.+)$'
    
    match = re.match(pattern, text)
    
    if not match:
        return None
    
    group_num = int(match.group(1))
    seq_num = int(match.group(2))
    pc_num = int(match.group(3))
    content = match.group(4).strip()
    
    # 새 댓글인지 대댓글인지 판단
    # 같은 그룹의 첫 번째(순서 1)는 새 댓글
    is_new_comment = (seq_num == 1)
    
    return {
        'group': group_num,
        'sequence': seq_num,
        'pc': pc_num,
        'content': content,
        'is_new': is_new_comment,
        'parent_group': group_num if not is_new_comment else None
    }


def parse_comment_scripts(text: str) -> List[Dict]:
    """
    여러 줄의 댓글 원고 파싱
    
    입력 예시:
        '''
        1-1: PC1 도와주세요ㅠㅜㅠㅠㅠ
        1-2: PC2 저도 궁금하네요
        1-3: PC1 오 대박...
        
        2-1: PC3 다들 고민이...
        2-2: PC1 와 헐 대박...
        '''
    
    Returns:
        파싱된 댓글 리스트
    """
    lines = text.split('\n')
    results = []
    
    for line in lines:
        parsed = parse_comment_script(line)
        if parsed:
            results.append(parsed)
    
    return results


def validate_comment_scripts(scripts: List[Dict]) -> Dict[str, List[str]]:
    """
    댓글 원고 유효성 검증
    
    검증 항목:
    - 그룹-순서 연속성 확인
    - PC 번호 유효성 확인
    - 빈 내용 확인
    
    Returns:
        {
            'valid': True/False,
            'errors': ['오류 메시지1', '오류 메시지2', ...]
        }
    """
    errors = []
    
    if not scripts:
        errors.append("댓글 원고가 비어있습니다.")
        return {'valid': False, 'errors': errors}
    
    # 그룹별로 정리
    groups = {}
    for script in scripts:
        group_num = script['group']
        if group_num not in groups:
            groups[group_num] = []
        groups[group_num].append(script)
    
    # 각 그룹별 검증
    for group_num, group_scripts in groups.items():
        # 순서대로 정렬
        group_scripts.sort(key=lambda x: x['sequence'])
        
        # 순서 연속성 확인
        for i, script in enumerate(group_scripts, 1):
            if script['sequence'] != i:
                errors.append(
                    f"그룹 {group_num}: 순서가 연속적이지 않습니다. "
                    f"예상 순서 {i}, 실제 순서 {script['sequence']}"
                )
        
        # 첫 번째는 반드시 새 댓글이어야 함
        if group_scripts[0]['sequence'] == 1 and not group_scripts[0]['is_new']:
            errors.append(f"그룹 {group_num}-1: 첫 번째는 새 댓글이어야 합니다.")
    
    # PC 번호 확인
    for script in scripts:
        if script['pc'] <= 0:
            errors.append(
                f"그룹 {script['group']}-{script['sequence']}: "
                f"PC 번호가 유효하지 않습니다. (PC{script['pc']})"
            )
    
    # 내용 확인
    for script in scripts:
        if not script['content']:
            errors.append(
                f"그룹 {script['group']}-{script['sequence']}: "
                f"댓글 내용이 비어있습니다."
            )
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }


def group_comment_scripts(scripts: List[Dict]) -> Dict[int, List[Dict]]:
    """
    댓글 원고를 그룹별로 정리
    
    Returns:
        {
            1: [script1, script2, script3],
            2: [script4, script5],
            ...
        }
    """
    groups = {}
    
    for script in scripts:
        group_num = script['group']
        if group_num not in groups:
            groups[group_num] = []
        groups[group_num].append(script)
    
    # 각 그룹 내에서 순서대로 정렬
    for group_num in groups:
        groups[group_num].sort(key=lambda x: x['sequence'])
    
    return groups


def get_next_script(scripts: List[Dict], current_group: int, current_sequence: int) -> Optional[Dict]:
    """
    다음 실행할 댓글 스크립트 가져오기
    
    Args:
        scripts: 전체 댓글 스크립트 리스트
        current_group: 현재 그룹 번호
        current_sequence: 현재 순서 번호
        
    Returns:
        다음 스크립트 또는 None (마지막인 경우)
    """
    for script in scripts:
        # 현재 그룹의 다음 순서
        if script['group'] == current_group and script['sequence'] == current_sequence + 1:
            return script
        
        # 다음 그룹의 첫 번째
        if script['group'] == current_group + 1 and script['sequence'] == 1:
            return script
    
    return None


# ============================================
# 테스트/예시 코드
# ============================================

if __name__ == "__main__":
    # 테스트 데이터
    test_script = """
1-1: PC1 도와주세요ㅠㅜㅠㅠㅠ
1-2: PC2 저도 궁금하네요
1-3: PC1 오 대박...

2-1: PC3 다들 고민이...
2-2: PC1 와 헐 대박...
2-3: PC3 개인 채팅줘라

3-1: PC4 저도 작년에...
3-2: PC2 혹시 어떤거...
    """
    
    print("=" * 60)
    print("댓글 원고 파싱 테스트")
    print("=" * 60)
    
    # 파싱
    scripts = parse_comment_scripts(test_script)
    
    print(f"\n✅ 파싱 결과: {len(scripts)}개 댓글")
    for script in scripts:
        comment_type = "새 댓글" if script['is_new'] else f"대댓글 (→ {script['parent_group']}-1)"
        print(f"  [{script['group']}-{script['sequence']}] PC{script['pc']}: {script['content'][:20]}... ({comment_type})")
    
    # 유효성 검증
    print("\n" + "=" * 60)
    print("유효성 검증")
    print("=" * 60)
    
    validation = validate_comment_scripts(scripts)
    if validation['valid']:
        print("✅ 유효성 검증 통과!")
    else:
        print("❌ 유효성 검증 실패:")
        for error in validation['errors']:
            print(f"  - {error}")
    
    # 그룹별 정리
    print("\n" + "=" * 60)
    print("그룹별 정리")
    print("=" * 60)
    
    groups = group_comment_scripts(scripts)
    for group_num, group_scripts in groups.items():
        print(f"\n그룹 {group_num}: {len(group_scripts)}개 댓글")
        for script in group_scripts:
            print(f"  {script['group']}-{script['sequence']}: PC{script['pc']} - {script['content'][:30]}...")
    
    # 다음 스크립트 가져오기
    print("\n" + "=" * 60)
    print("순차 실행 시뮬레이션")
    print("=" * 60)
    
    current_group = 1
    current_seq = 1
    
    while True:
        next_script = get_next_script(scripts, current_group, current_seq)
        if not next_script:
            print(f"\n✅ 마지막 댓글 (그룹 {current_group}-{current_seq})")
            break
        
        print(f"현재: {current_group}-{current_seq} → 다음: {next_script['group']}-{next_script['sequence']}")
        current_group = next_script['group']
        current_seq = next_script['sequence']



