"""
자동화 시스템 초기 데이터 설정
계정, 카페, 프롬프트를 한 번에 등록

실행: python init_automation_data.py
"""

import sys
from database import (
    SessionLocal, AutomationWorkerPC, AutomationAccount,
    AutomationCafe, AutomationPrompt
)
from datetime import datetime


class AutomationDataInitializer:
    """자동화 초기 데이터 설정"""
    
    def __init__(self):
        self.db = SessionLocal()
        
    def print_header(self, text):
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}\n")
        
    def register_pcs(self, count=8):
        """PC 등록 (8대)"""
        self.print_header("1. PC 등록")
        
        registered = 0
        skipped = 0
        
        for i in range(1, count + 1):
            existing = self.db.query(AutomationWorkerPC).filter(
                AutomationWorkerPC.pc_number == i
            ).first()
            
            if existing:
                print(f"⏭️  PC #{i} (이미 존재)")
                skipped += 1
                continue
            
            pc = AutomationWorkerPC(
                pc_number=i,
                pc_name=f"Worker PC #{i}",
                ip_address=f"192.168.1.{100 + i}",
                status='offline'
            )
            self.db.add(pc)
            registered += 1
            print(f"✅ PC #{i} 등록: IP 192.168.1.{100 + i}")
        
        self.db.commit()
        print(f"\n📊 결과: 등록 {registered}개, 건너뜀 {skipped}개")
        
    def register_accounts_interactive(self):
        """계정 등록 (대화형)"""
        self.print_header("2. 네이버 계정 등록")
        
        print("등록할 네이버 계정 정보를 입력하세요")
        print("(종료하려면 빈 ID 입력)\n")
        
        registered = 0
        
        while True:
            account_id = input(f"\n계정 ID #{registered + 1} (종료: Enter): ").strip()
            if not account_id:
                break
            
            # 중복 확인
            existing = self.db.query(AutomationAccount).filter(
                AutomationAccount.account_id == account_id
            ).first()
            
            if existing:
                print(f"⚠️  {account_id}는 이미 등록되어 있습니다")
                continue
            
            account_pw = input(f"비밀번호: ").strip()
            if not account_pw:
                print("❌ 비밀번호를 입력하세요")
                continue
            
            # PC 할당
            print("\nPC 할당 (1-8, 0=나중에):")
            pc_number = input("PC 번호: ").strip()
            
            assigned_pc_id = None
            if pc_number.isdigit() and 1 <= int(pc_number) <= 8:
                pc = self.db.query(AutomationWorkerPC).filter(
                    AutomationWorkerPC.pc_number == int(pc_number)
                ).first()
                if pc:
                    assigned_pc_id = pc.id
                    print(f"✅ PC #{pc_number}에 할당")
            
            # 계정 생성
            account = AutomationAccount(
                account_id=account_id,
                account_pw=account_pw,
                assigned_pc_id=assigned_pc_id,
                status='active'
            )
            self.db.add(account)
            self.db.commit()
            
            registered += 1
            print(f"✅ {account_id} 등록 완료!")
        
        print(f"\n📊 총 {registered}개 계정 등록됨")
        
    def register_accounts_from_file(self, filename="accounts.txt"):
        """파일에서 계정 일괄 등록"""
        self.print_header("2. 네이버 계정 일괄 등록")
        
        if not Path(filename).exists():
            print(f"⚠️  {filename} 파일이 없습니다")
            print(f"\n파일 형식 (accounts.txt):")
            print("account_id1,password1,pc_number")
            print("account_id2,password2,pc_number")
            print("...")
            return 0
        
        registered = 0
        skipped = 0
        
        with open(filename, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                try:
                    parts = line.split(',')
                    if len(parts) < 2:
                        print(f"⚠️  라인 {line_num}: 형식 오류")
                        continue
                    
                    account_id = parts[0].strip()
                    account_pw = parts[1].strip()
                    pc_number = int(parts[2].strip()) if len(parts) > 2 else None
                    
                    # 중복 확인
                    existing = self.db.query(AutomationAccount).filter(
                        AutomationAccount.account_id == account_id
                    ).first()
                    
                    if existing:
                        print(f"⏭️  {account_id} (이미 존재)")
                        skipped += 1
                        continue
                    
                    # PC 찾기
                    assigned_pc_id = None
                    if pc_number:
                        pc = self.db.query(AutomationWorkerPC).filter(
                            AutomationWorkerPC.pc_number == pc_number
                        ).first()
                        if pc:
                            assigned_pc_id = pc.id
                    
                    # 계정 생성
                    account = AutomationAccount(
                        account_id=account_id,
                        account_pw=account_pw,
                        assigned_pc_id=assigned_pc_id,
                        status='active'
                    )
                    self.db.add(account)
                    registered += 1
                    
                    pc_info = f" → PC #{pc_number}" if pc_number else ""
                    print(f"✅ {account_id}{pc_info}")
                    
                except Exception as e:
                    print(f"❌ 라인 {line_num} 오류: {e}")
        
        self.db.commit()
        print(f"\n📊 결과: 등록 {registered}개, 건너뜀 {skipped}개")
        return registered
        
    def register_cafes(self):
        """카페 등록 (대화형)"""
        self.print_header("3. 타겟 카페 등록")
        
        print("등록할 카페 정보를 입력하세요")
        print("(종료하려면 빈 URL 입력)\n")
        
        registered = 0
        
        while True:
            cafe_url = input(f"\n카페 URL #{registered + 1} (종료: Enter): ").strip()
            if not cafe_url:
                break
            
            # 중복 확인
            existing = self.db.query(AutomationCafe).filter(
                AutomationCafe.url == cafe_url
            ).first()
            
            if existing:
                print(f"⚠️  이미 등록된 카페입니다")
                continue
            
            cafe_name = input("카페 이름: ").strip()
            if not cafe_name:
                # URL에서 카페 이름 추출 시도
                if 'cafe.naver.com/' in cafe_url:
                    cafe_id = cafe_url.split('cafe.naver.com/')[-1].split('/')[0]
                    cafe_name = cafe_id
                else:
                    cafe_name = f"카페 {registered + 1}"
            
            # 카페 생성
            cafe = AutomationCafe(
                name=cafe_name,
                url=cafe_url,
                status='active'
            )
            self.db.add(cafe)
            self.db.commit()
            
            registered += 1
            print(f"✅ {cafe_name} 등록 완료!")
        
        print(f"\n📊 총 {registered}개 카페 등록됨")
        
    def register_default_prompts(self):
        """기본 프롬프트 등록"""
        self.print_header("4. 기본 프롬프트 등록")
        
        prompts = [
            {
                'name': '카페 글 작성 - 일반',
                'prompt_type': 'post',
                'system_prompt': """당신은 네이버 카페 글 작성 전문가입니다.
자연스럽고 진정성 있는 글을 작성하며, 광고처럼 보이지 않습니다.
실제 사용 경험을 공유하는 듯한 느낌을 줍니다.""",
                'user_prompt_template': """다음 상품에 대해 네이버 카페 글을 작성해주세요.

상품명: {product_name}
키워드: {keyword}

요구사항:
1. 제목: 20~35자, {keyword} 포함
2. 본문: 400~600자
3. 자연스럽고 진정성 있는 문체
4. 광고 티 나지 않게
5. 실제 사용 경험처럼

형식:
제목: [여기에 제목]
---
[여기에 본문]""",
                'temperature': 0.7,
                'max_tokens': 1000
            },
            {
                'name': '카페 글 작성 - 후기',
                'prompt_type': 'post',
                'system_prompt': """당신은 솔직한 제품 후기 작성자입니다.
실제 사용 경험을 바탕으로 장점과 단점을 모두 언급합니다.
과장하지 않고 정직하게 평가합니다.""",
                'user_prompt_template': """다음 상품에 대해 사용 후기를 작성해주세요.

상품명: {product_name}
키워드: {keyword}

요구사항:
1. 제목: "{keyword}" 포함, 후기 느낌
2. 본문: 500~700자
3. 장점 3가지, 단점 1가지 언급
4. 구체적인 사용 상황 설명
5. 다른 사용자들을 위한 팁

형식:
제목: [여기에 제목]
---
[여기에 본문 - 장점/단점/사용팁 포함]""",
                'temperature': 0.75,
                'max_tokens': 1200
            },
            {
                'name': '댓글 작성 - 공감',
                'prompt_type': 'comment',
                'system_prompt': """당신은 카페 활동을 활발히 하는 회원입니다.
다른 사람의 글에 공감하고 추가 정보를 제공합니다.""",
                'user_prompt_template': """다음 글에 댓글을 작성해주세요.

글 제목: {post_title}
키워드: {keyword}

요구사항:
1. 50~100자
2. 공감 표현
3. 추가 정보나 팁 제공
4. 자연스러운 대화체

예시: "저도 이거 써봤는데 정말 좋더라고요! 특히 ~할 때 유용했어요 😊" """,
                'temperature': 0.8,
                'max_tokens': 200
            }
        ]
        
        registered = 0
        skipped = 0
        
        for prompt_data in prompts:
            existing = self.db.query(AutomationPrompt).filter(
                AutomationPrompt.name == prompt_data['name']
            ).first()
            
            if existing:
                print(f"⏭️  {prompt_data['name']} (이미 존재)")
                skipped += 1
                continue
            
            prompt = AutomationPrompt(**prompt_data, is_active=True)
            self.db.add(prompt)
            registered += 1
            print(f"✅ {prompt_data['name']}")
        
        self.db.commit()
        print(f"\n📊 결과: 등록 {registered}개, 건너뜀 {skipped}개")
        
    def show_summary(self):
        """현재 등록된 데이터 요약"""
        self.print_header("현재 등록 상태")
        
        pc_count = self.db.query(AutomationWorkerPC).count()
        account_count = self.db.query(AutomationAccount).count()
        cafe_count = self.db.query(AutomationCafe).count()
        prompt_count = self.db.query(AutomationPrompt).count()
        
        print(f"PC:      {pc_count}개")
        print(f"계정:    {account_count}개")
        print(f"카페:    {cafe_count}개")
        print(f"프롬프트: {prompt_count}개")
        
        # PC 상세
        if pc_count > 0:
            print("\n📌 등록된 PC:")
            pcs = self.db.query(AutomationWorkerPC).order_by(AutomationWorkerPC.pc_number).all()
            for pc in pcs:
                status_icon = "🟢" if pc.status == 'online' else "🔴"
                print(f"   {status_icon} PC #{pc.pc_number}: {pc.pc_name} ({pc.ip_address})")
        
        # 계정 상세
        if account_count > 0:
            print("\n📌 등록된 계정:")
            accounts = self.db.query(AutomationAccount).all()
            for acc in accounts:
                pc_info = f"→ PC #{acc.assigned_pc.pc_number}" if acc.assigned_pc else "할당 안됨"
                print(f"   👤 {acc.account_id} {pc_info}")
        
        # 카페 상세
        if cafe_count > 0:
            print("\n📌 등록된 카페:")
            cafes = self.db.query(AutomationCafe).all()
            for cafe in cafes:
                print(f"   ☕ {cafe.name}: {cafe.url}")
        
        # 프롬프트 상세
        if prompt_count > 0:
            print("\n📌 등록된 프롬프트:")
            prompts = self.db.query(AutomationPrompt).all()
            for prompt in prompts:
                active = "🟢" if prompt.is_active else "🔴"
                print(f"   {active} {prompt.name} ({prompt.prompt_type})")
        
    def run(self):
        """초기화 실행"""
        print("""
╔════════════════════════════════════════════════════════╗
║     자동화 시스템 초기 데이터 설정                     ║
╚════════════════════════════════════════════════════════╝
        """)
        
        try:
            # 1. PC 등록 (8대 자동)
            self.register_pcs(count=8)
            
            # 2. 계정 등록
            print("\n계정 등록 방법:")
            print("1. 대화형으로 입력")
            print("2. accounts.txt 파일에서 일괄 등록")
            print("3. 건너뛰기")
            
            choice = input("\n선택 (1-3): ").strip()
            
            if choice == '1':
                self.register_accounts_interactive()
            elif choice == '2':
                registered = self.register_accounts_from_file()
                if registered == 0:
                    print("\n💡 accounts.txt 파일 형식:")
                    print("account1,password1,1")
                    print("account2,password2,2")
                    print("...")
            
            # 3. 카페 등록
            print("\n카페를 등록하시겠습니까? (y/n): ", end='')
            if input().strip().lower() == 'y':
                self.register_cafes()
            else:
                print("⏭️  카페 등록 건너뜀 (나중에 웹에서 등록 가능)")
            
            # 4. 기본 프롬프트 등록
            print("\n기본 프롬프트를 등록하시겠습니까? (y/n): ", end='')
            if input().strip().lower() == 'y':
                self.register_default_prompts()
            else:
                print("⏭️  프롬프트 등록 건너뜀")
            
            # 5. 요약
            self.show_summary()
            
            self.print_header("초기 설정 완료!")
            
            print("✅ 자동화 시스템 초기 데이터가 설정되었습니다!")
            print("\n📝 다음 단계:")
            print("   1. 각 PC에 Worker Agent 설치 및 실행")
            print("   2. 웹 대시보드 접속: https://scorp274.com/automation/cafe")
            print("   3. PC 연결 상태 확인")
            print("   4. 테스트 스케줄 생성\n")
            
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            self.db.rollback()
            import traceback
            traceback.print_exc()
        finally:
            self.db.close()


if __name__ == "__main__":
    initializer = AutomationDataInitializer()
    
    try:
        initializer.run()
    except KeyboardInterrupt:
        print("\n\n⏹️ 취소됨")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()

