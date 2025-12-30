"""
기존 레퍼런스를 AI 프롬프트로 변환
실행: python convert_references_to_prompts.py
"""

import sys
from database import SessionLocal, Reference, AutomationPrompt

def convert_references_to_prompts():
    """기존 레퍼런스를 AutomationPrompt로 변환"""
    db = SessionLocal()
    
    try:
        print("="*60)
        print("  레퍼런스 → 프롬프트 변환 도구")
        print("="*60)
        
        # 기존 레퍼런스 조회
        references = db.query(Reference).all()
        
        if not references:
            print("\n❌ 레퍼런스가 없습니다")
            return
        
        print(f"\n📚 발견된 레퍼런스: {len(references)}개\n")
        
        # 레퍼런스 목록 출력
        for idx, ref in enumerate(references, 1):
            print(f"{idx}. {ref.title} ({ref.ref_type})")
        
        print("\n" + "="*60)
        print("변환 옵션:")
        print("1. 전체 변환 (모든 레퍼런스)")
        print("2. 선택 변환 (특정 레퍼런스만)")
        print("3. 취소")
        
        choice = input("\n선택 (1-3): ").strip()
        
        if choice == '3':
            print("취소됨")
            return
        
        refs_to_convert = []
        
        if choice == '1':
            # 전체 변환
            refs_to_convert = references
        elif choice == '2':
            # 선택 변환
            selected = input("\n변환할 레퍼런스 번호 (쉼표로 구분, 예: 1,3,5): ").strip()
            indices = [int(x.strip()) - 1 for x in selected.split(',')]
            refs_to_convert = [references[i] for i in indices if 0 <= i < len(references)]
        else:
            print("잘못된 선택")
            return
        
        print(f"\n📝 {len(refs_to_convert)}개 레퍼런스 변환 중...\n")
        
        converted_count = 0
        skipped_count = 0
        
        for ref in refs_to_convert:
            # 이미 같은 이름의 프롬프트가 있는지 확인
            existing = db.query(AutomationPrompt).filter(
                AutomationPrompt.name == ref.title
            ).first()
            
            if existing:
                print(f"⏭️  건너뜀: {ref.title} (이미 존재)")
                skipped_count += 1
                continue
            
            # 프롬프트 생성
            prompt = AutomationPrompt(
                name=ref.title,
                prompt_type='post',  # 기본값: 글 작성용
                system_prompt=create_system_prompt(ref),
                user_prompt_template=create_user_prompt_template(ref),
                temperature=0.7,
                max_tokens=1000,
                is_active=True
            )
            
            db.add(prompt)
            converted_count += 1
            print(f"✅ 변환: {ref.title}")
        
        db.commit()
        
        print("\n" + "="*60)
        print(f"✅ 변환 완료!")
        print(f"   - 성공: {converted_count}개")
        print(f"   - 건너뜀: {skipped_count}개")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def create_system_prompt(reference):
    """레퍼런스로부터 시스템 프롬프트 생성"""
    
    # 레퍼런스 타입에 따라 다른 시스템 프롬프트
    type_prompts = {
        "카페글": """당신은 네이버 카페 글 작성 전문가입니다.
다음 특성을 갖춘 글을 작성합니다:
- 자연스럽고 진정성 있는 문체
- 유용한 정보 제공
- 광고처럼 보이지 않는 자연스러운 소개
- 독자에게 도움이 되는 내용
- 실제 사용 경험을 공유하는 느낌""",
        
        "후기": """당신은 솔직한 제품 후기 작성자입니다.
다음 특성을 갖춘 후기를 작성합니다:
- 실제 사용 경험을 바탕으로 한 듯한 문체
- 장점과 함께 사소한 단점도 언급 (신뢰도 향상)
- 구체적인 사용 상황 설명
- 다른 사용자들에게 도움이 되는 팁
- 과장하지 않는 솔직한 평가""",
        
        "정보": """당신은 유용한 정보를 제공하는 카페 활동가입니다.
다음 특성을 갖춘 정보글을 작성합니다:
- 정확하고 검증된 정보
- 쉽게 이해할 수 있는 설명
- 실생활에 바로 적용 가능한 팁
- 단계별 가이드 제공
- 추가 정보 소스 제시""",
        
        "질문": """당신은 궁금한 것을 질문하는 카페 회원입니다.
다음 특성을 갖춘 질문글을 작성합니다:
- 구체적이고 명확한 질문
- 이미 시도해본 것들 언급
- 왜 궁금한지 배경 설명
- 다른 회원들이 답변하기 쉽게 구성
- 감사 인사 포함""",
    }
    
    # 레퍼런스 타입으로 시스템 프롬프트 선택
    return type_prompts.get(reference.ref_type, type_prompts["카페글"])


def create_user_prompt_template(reference):
    """레퍼런스로부터 사용자 프롬프트 템플릿 생성"""
    
    # 레퍼런스 내용을 템플릿에 포함
    content_preview = reference.content[:200] if reference.content else ""
    
    template = f"""다음 상품에 대해 네이버 카페 글을 작성해주세요.

📦 상품명: {{product_name}}
🔑 키워드: {{keyword}}

📝 참고 자료:
{reference.title}
---
{content_preview}{"..." if len(reference.content or "") > 200 else ""}

✍️ 작성 요구사항:
1. 제목: 20~40자, {{keyword}} 키워드 포함
2. 본문: 400~600자
3. 자연스럽고 진정성 있는 문체
4. 광고 티 나지 않게
5. 독자에게 실질적 도움이 되는 내용
6. 위 참고 자료의 스타일과 구조 참고

📤 출력 형식:
제목: [여기에 제목]
---
[여기에 본문 내용]

참고: 이모지는 자연스럽게 사용하되 과하지 않게"""
    
    return template


def show_prompts():
    """현재 등록된 프롬프트 목록 표시"""
    db = SessionLocal()
    
    try:
        prompts = db.query(AutomationPrompt).all()
        
        if not prompts:
            print("\n등록된 프롬프트가 없습니다\n")
            return
        
        print("\n" + "="*60)
        print(f"  등록된 프롬프트: {len(prompts)}개")
        print("="*60 + "\n")
        
        for idx, prompt in enumerate(prompts, 1):
            status = "🟢 활성" if prompt.is_active else "🔴 비활성"
            print(f"{idx}. {prompt.name} ({prompt.prompt_type}) {status}")
            print(f"   Temperature: {prompt.temperature}, Max Tokens: {prompt.max_tokens}")
            print(f"   생성: {prompt.created_at.strftime('%Y-%m-%d %H:%M')}\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════╗
║     레퍼런스 → AI 프롬프트 변환 도구                   ║
║     네이버 카페 자동화 시스템                           ║
╚════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--list':
            # 현재 프롬프트 목록 표시
            show_prompts()
        elif sys.argv[1] == '--help':
            print("""
사용법:
    python convert_references_to_prompts.py          # 변환 실행
    python convert_references_to_prompts.py --list   # 프롬프트 목록
    python convert_references_to_prompts.py --help   # 도움말
            """)
        else:
            print("알 수 없는 옵션. --help 참고")
    else:
        # 변환 실행
        convert_references_to_prompts()

