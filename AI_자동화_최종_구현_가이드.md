# 🤖 AI 자동화 시스템 최종 구현 가이드

**작성일:** 2026-01-06  
**상태:** 진행 중 (기초 완료, 상세 기능 구현 예정)

---

## ✅ 오늘까지 완성된 것 (2026-01-06)

### **1. 기본 자동화 시스템**
- ✅ PC 관리 (8대 Worker PC 연결 중)
- ✅ 계정 관리 (네이버 계정 관리)
- ✅ 카페 관리 (타겟 카페 관리)
- ✅ 프롬프트 관리 (기본 CRUD)
- ✅ 스케줄 관리 (기본 생성/삭제)
- ✅ 대시보드 (실시간 모니터링)

### **2. 댓글 시스템**
- ✅ CommentScript 모델 (database.py)
- ✅ 댓글 파싱 함수 (utils/comment_parser.py)
- ✅ 댓글 API (routers/automation.py)
  - `/api/comment-scripts/parse` - 파싱 및 저장
  - `/api/comment-scripts/list` - 목록 조회
  - `/api/comment-scripts/create-tasks` - Task 생성
- ✅ 댓글 모달 (automation_cafe_full.html)
- ✅ 댓글 JavaScript 함수
- ✅ 로컬 테스트 성공 (test_full_comment_flow.py)

### **3. Claude AI 통합**
- ✅ Claude Sonnet 4 연동
- ✅ API 키 환경변수 설정 (.env, Render)
- ✅ 로컬 콘텐츠 생성 테스트 성공

### **4. 캡챠 우회 로그인**
- ✅ undetected-chromedriver
- ✅ pyperclip 붙여넣기
- ✅ 로컬 테스트 성공

### **5. UI 개선**
- ✅ 네비게이션 바 정리
- ✅ 관리자 메뉴 → 사용자 드롭다운
- ✅ 자동화 탭 정리 (6개)
- ✅ 주문조회 페이지네이션

### **6. 마케팅 개선**
- ✅ 연동 관리 양방향 보기
- ✅ 활동정지/졸업 제외
- ✅ 10개 자동 졸업
- ✅ 상품 선택 스케줄링

### **7. 메모 시스템**
- ✅ 관리자 모드 (다른 직원 메모 관리)
- ✅ 자기 메모만 뱃지/현황 표시

---

## 🎯 다음 세션 구현 순서

### **Phase 1: 상품 세팅 (우선순위 1)**

#### **1-1. 테이블 생성**
```sql
-- Render Shell에서 실행
psql $DATABASE_URL

-- database.py에 모델이 이미 정의되어 있으므로
-- Python에서 테이블 생성
```

또는 `create_ai_automation_tables.sql` 실행

#### **1-2. 상품 세팅 탭 UI**

**파일:** `templates/automation_cafe_full.html`

**위치:** 탭 콘텐츠 섹션에 추가

```html
<!-- AI 상품 세팅 탭 -->
<div class="tab-pane fade" id="ai-product-setup">
    <div class="content-card">
        <div class="card-header-custom">
            <h4><i class="bi bi-stars"></i> AI 상품 세팅</h4>
            <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#selectMarketingProductModal">
                <i class="bi bi-plus-circle"></i> 상품 추가
            </button>
        </div>
        
        <div class="table-responsive">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>썸네일</th>
                        <th>상품명</th>
                        <th>카페</th>
                        <th>블로그</th>
                        <th>키워드</th>
                        <th>레퍼런스</th>
                        <th>관리</th>
                    </tr>
                </thead>
                <tbody id="aiProductsTableBody">
                    <tr><td colspan="7" class="text-center">로딩 중...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
```

#### **1-3. 상품 추가 모달**

```html
<!-- 마케팅 상품 선택 모달 -->
<div class="modal fade" id="selectMarketingProductModal">
    <div class="modal-dialog modal-xl">
        <div class="modal-content">
            <div class="modal-header">
                <h5>AI 자동화 상품 추가</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <!-- 마케팅 상품 목록 (썸네일 + 상품명) -->
                <div id="marketingProductsList"></div>
            </div>
        </div>
    </div>
</div>
```

#### **1-4. 상품 상세 정보 모달 (12개 필드)**

```html
<div class="modal fade" id="editAIProductModal">
    <div class="modal-dialog modal-xl">
        <div class="modal-content">
            <div class="modal-header">
                <h5>상품 상세 정보 입력</h5>
            </div>
            <form id="aiProductForm">
                <div class="modal-body">
                    <!-- 권한 체크박스 -->
                    <div class="mb-3">
                        <div class="form-check form-check-inline">
                            <input type="checkbox" name="is_cafe_enabled" checked>
                            <label>카페 사용</label>
                        </div>
                        <div class="form-check form-check-inline">
                            <input type="checkbox" name="is_blog_enabled">
                            <label>블로그 사용</label>
                        </div>
                    </div>
                    
                    <!-- 12개 필드 -->
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label>1. 우리 제품명 *</label>
                            <input type="text" name="product_name" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label>8. 우리 제품의 가격 *</label>
                            <input type="text" name="our_price" class="form-control" required>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label>2. 우리 제품의 핵심 *</label>
                        <textarea name="core_value" rows="4" class="form-control" required></textarea>
                    </div>
                    
                    <div class="mb-3">
                        <label>3. 우리 제품의 서브 핵심 *</label>
                        <textarea name="sub_core_value" rows="3" class="form-control" required></textarea>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label>4. 사이즈 & 무게 *</label>
                            <input type="text" name="size_weight" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label>9. 기존 시장 평균 가격 *</label>
                            <input type="text" name="market_avg_price" class="form-control" required>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label>5. 타사 제품과 차별점 *</label>
                        <textarea name="difference" rows="4" class="form-control" required></textarea>
                    </div>
                    
                    <div class="mb-3">
                        <label>6. 해당 제품의 유명 브랜드들 *</label>
                        <input type="text" name="famous_brands" class="form-control" required 
                               placeholder="예: A브랜드, B브랜드, C브랜드">
                    </div>
                    
                    <div class="mb-3">
                        <label>7. 기존 시장의 문제점 *</label>
                        <textarea name="market_problem" rows="4" class="form-control" required></textarea>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label>10. 고객 예상 연령대 *</label>
                            <input type="text" name="target_age" class="form-control" required
                                   placeholder="예: 20-40대">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label>11. 고객 예상 성별 *</label>
                            <select name="target_gender" class="form-select" required>
                                <option value="">선택</option>
                                <option value="남성">남성</option>
                                <option value="여성">여성</option>
                                <option value="무관">무관</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label>12. 기타 추가 특이사항 (선택)</label>
                        <textarea name="additional_notes" rows="3" class="form-control"></textarea>
                    </div>
                    
                    <div class="mb-3">
                        <label>마케팅 링크 *</label>
                        <input type="url" name="marketing_link" class="form-control" required
                               placeholder="https://...">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">취소</button>
                    <button type="submit" class="btn btn-primary">저장</button>
                </div>
            </form>
        </div>
    </div>
</div>
```

---

### **Phase 2: 키워드 관리**

**파일:** `templates/automation_cafe_full.html`

**API:** `routers/automation.py`
- `/api/ai/products/{product_id}/keywords` - 키워드 목록
- `/api/ai/keywords/{keyword_id}/classify` - 분류 변경
- `/api/ai/keywords/sync` - 마케팅에서 동기화

---

### **Phase 3: 레퍼런스 관리**

**파일:** `templates/automation_cafe_full.html`

**API:** `routers/automation.py`
- `/api/ai/products/{product_id}/references` - 레퍼런스 목록
- `/api/ai/references/{ref_id}/classify` - 분류 변경
- `/api/ai/references/sync` - 마케팅에서 동기화

---

### **Phase 4: 프롬프트 템플릿**

**변수 시스템:**
```
{PRODUCT_NAME}
{CORE_VALUE}
{SUB_CORE_VALUE}
{SIZE_WEIGHT}
{DIFFERENCE}
{FAMOUS_BRANDS}
{MARKET_PROBLEM}
{OUR_PRICE}
{MARKET_AVG_PRICE}
{TARGET_AGE}
{TARGET_GENDER}
{MARKETING_LINK}
```

**이미지 생성 프롬프트 자동 추가:**
```
위 내용을 정확하게 참조해서 
1. 제품 파손, 불량 등 부정적인 실제 사진같은 이미지 
2. 실제 한국사람이 고통스러워 하고있는 실제 사진같은 이미지 
3. 해당 제품의 실제 사용하는 것 같은 이미지 
이렇게 총 3장을 만들어줘
```

---

### **Phase 5: 프롬프트 관리**

**상품별 프롬프트:**
- 상품 선택 → 템플릿 선택 → 변수 자동 치환

---

### **Phase 6: 스케줄 관리 개선**

**추가 기능:**
- 상품 선택 → 키워드 수 표시
- 프롬프트 선택 (상품별 필터)
- 예상 발행 수 계산
- 페이지네이션 (20개)
- 상품명 검색
- 상태 필터

---

### **Phase 7: 신규 발행 관리**

**카페별/계정별 신규발행 글 목록**

---

### **Phase 8: 연동 관리**

**마케팅과 별개 연동 관리**

---

## 🗂️ 현재 파일 구조

```
SHS_Product_DB/
├── database.py (✅ AI 모델 이미 정의됨!)
│   ├─ AIMarketingProduct
│   ├─ AIProductKeyword
│   ├─ AIProductReference
│   ├─ AIPromptTemplate
│   ├─ AIPrompt
│   ├─ AIMarketingSchedule
│   └─ AIGeneratedPost
│
├── routers/
│   ├── automation.py (✅ 기본 자동화 + 댓글 API)
│   ├── marketing.py (✅ 마케팅 시스템)
│   └── tasks.py (✅ 업무/메모)
│
├── templates/
│   ├── base.html (✅ 네비게이션 정리 완료)
│   └── automation_cafe_full.html (✅ 6개 탭 + AI 탭 구조 추가됨)
│
├── utils/
│   └── comment_parser.py (✅ 댓글 파싱)
│
├── test_full_comment_flow.py (✅ 댓글 전체 테스트)
├── test_full_post_flow.py (✅ 본문 전체 테스트)
└── create_ai_automation_tables.sql (✅ AI 테이블 생성 SQL)
```

---

## 🚀 다음 세션 시작 순서

### **Step 1: Render Shell 접속**

```bash
# Render Shell
cd /opt/render/project/src
psql $DATABASE_URL < create_ai_automation_tables.sql
```

또는:

```sql
psql $DATABASE_URL

-- AI 테이블이 있는지 확인
\dt ai_*

-- 없으면:
CREATE TABLE ai_marketing_products (...);
CREATE TABLE ai_product_keywords (...);
...
```

---

### **Step 2: 상품 세팅 UI 구현**

**파일:** `templates/automation_cafe_full.html`

**추가할 위치:** 스케줄 관리 탭 다음

**코드:**
```html
<!-- AI 상품 세팅 탭 -->
<div class="tab-pane fade" id="ai-product-setup">
    [위의 HTML 코드 복사]
</div>
```

---

### **Step 3: JavaScript 함수**

**파일:** `templates/automation_cafe_full.html` 하단 `<script>` 섹션

```javascript
// AI 상품 목록 로드
async function loadAIProducts() {
    const response = await fetch('/automation/api/ai/products/list');
    const data = await response.json();
    displayAIProducts(data.products);
}

// 상품 상세 정보 모달 열기
async function openAIProductDetail(productId) {
    if (productId) {
        // 기존 정보 로드
        const response = await fetch(`/automation/api/ai/products/${productId}`);
        const data = await response.json();
        // 폼에 채우기
    }
    const modal = new bootstrap.Modal(document.getElementById('editAIProductModal'));
    modal.show();
}

// 상품 정보 저장
async function saveAIProduct(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    
    const response = await fetch('/automation/api/ai/products/save', {
        method: 'POST',
        body: formData
    });
    
    if (response.ok) {
        alert('저장되었습니다');
        loadAIProducts();
    }
}
```

---

### **Step 4: API 엔드포인트**

**파일:** `routers/automation.py`

**추가할 위치:** 댓글 API 다음

```python
# ============================================
# AI 자동화 상품 세팅 API
# ============================================

@router.get("/api/ai/products/list")
async def list_ai_products(db: Session = Depends(get_db)):
    """AI 상품 목록 조회"""
    from database import AIMarketingProduct
    
    products = db.query(AIMarketingProduct).options(
        joinedload(AIMarketingProduct.marketing_product).joinedload(MarketingProduct.product)
    ).all()
    
    result = []
    for p in products:
        # 키워드 수
        keyword_count = db.query(AIProductKeyword).filter(
            AIProductKeyword.ai_product_id == p.id
        ).count()
        
        # 레퍼런스 수
        ref_count = db.query(AIProductReference).filter(
            AIProductReference.ai_product_id == p.id
        ).count()
        
        result.append({
            'id': p.id,
            'product_name': p.product_name,
            'thumbnail': p.marketing_product.product.thumbnail if p.marketing_product and p.marketing_product.product else None,
            'is_cafe_enabled': p.is_cafe_enabled,
            'is_blog_enabled': p.is_blog_enabled,
            'keyword_count': keyword_count,
            'reference_count': ref_count
        })
    
    return JSONResponse({'success': True, 'products': result})


@router.post("/api/ai/products/save")
async def save_ai_product(
    marketing_product_id: int = Form(...),
    is_cafe_enabled: bool = Form(False),
    is_blog_enabled: bool = Form(False),
    product_name: str = Form(...),
    core_value: str = Form(...),
    sub_core_value: str = Form(...),
    size_weight: str = Form(...),
    difference: str = Form(...),
    famous_brands: str = Form(...),
    market_problem: str = Form(...),
    our_price: str = Form(...),
    market_avg_price: str = Form(...),
    target_age: str = Form(...),
    target_gender: str = Form(...),
    additional_notes: str = Form(""),
    marketing_link: str = Form(...),
    db: Session = Depends(get_db)
):
    """AI 상품 정보 저장"""
    from database import AIMarketingProduct
    
    # 기존 체크
    existing = db.query(AIMarketingProduct).filter(
        AIMarketingProduct.marketing_product_id == marketing_product_id
    ).first()
    
    if existing:
        # 수정
        existing.is_cafe_enabled = is_cafe_enabled
        existing.is_blog_enabled = is_blog_enabled
        existing.product_name = product_name
        existing.core_value = core_value
        existing.sub_core_value = sub_core_value
        existing.size_weight = size_weight
        existing.difference = difference
        existing.famous_brands = famous_brands
        existing.market_problem = market_problem
        existing.our_price = our_price
        existing.market_avg_price = market_avg_price
        existing.target_age = target_age
        existing.target_gender = target_gender
        existing.additional_notes = additional_notes
        existing.marketing_link = marketing_link
        existing.updated_at = get_kst_now()
        
        ai_product = existing
    else:
        # 신규
        ai_product = AIMarketingProduct(
            marketing_product_id=marketing_product_id,
            is_cafe_enabled=is_cafe_enabled,
            is_blog_enabled=is_blog_enabled,
            product_name=product_name,
            core_value=core_value,
            sub_core_value=sub_core_value,
            size_weight=size_weight,
            difference=difference,
            famous_brands=famous_brands,
            market_problem=market_problem,
            our_price=our_price,
            market_avg_price=market_avg_price,
            target_age=target_age,
            target_gender=target_gender,
            additional_notes=additional_notes,
            marketing_link=marketing_link
        )
        db.add(ai_product)
    
    db.commit()
    
    return JSONResponse({'success': True, 'message': '상품 정보가 저장되었습니다'})
```

---

## 📝 변수 시스템 구현 가이드

### **변수 정의**

```python
PRODUCT_VARIABLES = {
    'PRODUCT_NAME': '우리 제품명',
    'CORE_VALUE': '우리 제품의 핵심',
    'SUB_CORE_VALUE': '서브 핵심',
    'SIZE_WEIGHT': '사이즈 & 무게',
    'DIFFERENCE': '타사 차별점',
    'FAMOUS_BRANDS': '유명 브랜드들',
    'MARKET_PROBLEM': '시장 문제점',
    'OUR_PRICE': '우리 가격',
    'MARKET_AVG_PRICE': '시장 평균 가격',
    'TARGET_AGE': '예상 연령대',
    'TARGET_GENDER': '예상 성별',
    'MARKETING_LINK': '마케팅 링크'
}
```

### **변수 치환 함수**

```python
def replace_variables(template: str, ai_product: AIMarketingProduct) -> str:
    """템플릿의 변수를 실제 값으로 치환"""
    result = template
    
    result = result.replace('{PRODUCT_NAME}', ai_product.product_name)
    result = result.replace('{CORE_VALUE}', ai_product.core_value)
    result = result.replace('{SUB_CORE_VALUE}', ai_product.sub_core_value)
    result = result.replace('{SIZE_WEIGHT}', ai_product.size_weight)
    result = result.replace('{DIFFERENCE}', ai_product.difference)
    result = result.replace('{FAMOUS_BRANDS}', ai_product.famous_brands)
    result = result.replace('{MARKET_PROBLEM}', ai_product.market_problem)
    result = result.replace('{OUR_PRICE}', ai_product.our_price)
    result = result.replace('{MARKET_AVG_PRICE}', ai_product.market_avg_price)
    result = result.replace('{TARGET_AGE}', ai_product.target_age)
    result = result.replace('{TARGET_GENDER}', ai_product.target_gender)
    result = result.replace('{MARKETING_LINK}', ai_product.marketing_link)
    
    return result
```

---

## 🔑 중요 포인트

### **1. 마케팅과 분리**

- AI 자동화 키워드/레퍼런스는 마케팅과 **별개**
- 처음 한 번만 동기화 (sync 버튼)
- 이후 수정사항은 서로 영향 없음

### **2. 데이터베이스 관계**

```
MarketingProduct (기존)
    ↓ (1:1)
AIMarketingProduct
    ├─ AIProductKeyword (1:N)
    ├─ AIProductReference (1:N)
    └─ AIPrompt (1:N)
        └─ AIMarketingSchedule (1:N)
            └─ AIGeneratedPost (1:N)
```

### **3. 키워드 분류 워크플로우**

```
1. 마케팅에서 동기화 → 모두 'unclassified'
2. 작업자가 하나씩 분류:
   - alternative (대안성)
   - informational (정보성)
3. 프롬프트 생성 시 분류별로 다른 템플릿 사용
```

---

## 🧪 테스트 시나리오

### **1. 상품 세팅**

```
1. AI 상품 세팅 탭 클릭
2. 상품 추가 버튼
3. 마케팅 상품 선택
4. 12개 필드 + 마케팅 링크 입력
5. 저장
6. 목록에 표시 확인
```

### **2. 키워드 관리**

```
1. 상품 목록에서 "키워드" 버튼 클릭
2. 키워드 동기화 버튼 (마케팅에서)
3. 각 키워드를 대안성/정보성으로 분류
4. 저장
```

### **3. 레퍼런스 관리**

```
1. 상품 목록에서 "레퍼런스" 버튼 클릭
2. 레퍼런스 동기화 버튼
3. 각 레퍼런스를 대안성/정보성으로 분류
4. 저장
```

---

## 📦 로컬 테스트 파일들

**이미 작동하는 것:**
- ✅ `test_naver_comment.py` - 댓글/대댓글 작성
- ✅ `test_full_post_flow.py` - 본문 생성 + 발행
- ✅ `test_full_comment_flow.py` - 댓글 생성 + 순차 작성
- ✅ `test_claude_auto.py` - Claude 콘텐츠 생성

---

## 💾 중요 환경 설정

### **Render 환경변수:**
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx...
DATABASE_URL=postgresql://...
```

### **로컬 .env:**
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx...
DATABASE_URL=postgresql://...
```

---

## 🎯 다음 세션 첫 작업

**1. 테이블 생성 확인:**
```sql
psql $DATABASE_URL
\dt ai_*
```

**2. 상품 세팅 탭 UI 추가:**
- automation_cafe_full.html 수정

**3. API 추가:**
- routers/automation.py 수정

**4. 테스트:**
- 상품 추가
- 상세 정보 입력
- 저장 확인

---

## 📋 체크리스트 (다음 세션)

### **상품 세팅:**
- [ ] 테이블 생성 확인
- [ ] 상품 목록 UI
- [ ] 상품 추가 모달
- [ ] 상품 상세 정보 모달 (12개 필드)
- [ ] 마케팅 링크 필드
- [ ] 권한 체크박스 (카페/블로그)
- [ ] API 엔드포인트
- [ ] 테스트

### **키워드 관리:**
- [ ] 키워드 목록 UI
- [ ] 동기화 버튼
- [ ] 분류 선택 (대안성/정보성/미분류)
- [ ] 추가/삭제 기능
- [ ] API
- [ ] 테스트

### **레퍼런스 관리:**
- [ ] 레퍼런스 목록 UI
- [ ] 동기화 버튼
- [ ] 분류 선택
- [ ] 상세 보기 (마케팅과 동일)
- [ ] API
- [ ] 테스트

### **프롬프트 템플릿:**
- [ ] 템플릿 목록 UI
- [ ] 템플릿 추가 모달
- [ ] 변수 드롭다운
- [ ] 변수 버튼 표시
- [ ] 이미지 생성 버튼
- [ ] API
- [ ] 테스트

---

## 🎊 현재 배포 상태

**서버:**
- ✅ https://scorp274.com
- ✅ Worker PC 8대 연결
- ✅ 기본 자동화 정상 작동
- ✅ 댓글 API 활성화
- ✅ Claude API 설정 완료

**다음 세션:**
- 🚀 AI 자동화 시스템 본격 구현

---

## 📞 다음 세션 시작 시

**이 파일을 열어주세요:**
- `AI_자동화_최종_구현_가이드.md`

**그리고 말씀해주세요:**
> "AI 자동화 시스템 구현을 계속하겠습니다"

**제가 이 가이드를 보고 정확히 이어서 작업하겠습니다!**

---

**오늘 수고하셨습니다!** 🎉

많은 것을 완성했습니다! 다음 세션에서 AI 시스템을 완성하겠습니다! 💪🚀
