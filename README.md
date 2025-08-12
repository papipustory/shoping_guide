# 🛒 가이드컴 가격비교 웹앱

가이드컴(GuidecoM) 사이트에서 컴퓨터 부품 및 IT 제품의 가격과 사양을 검색하고 비교할 수 있는 웹 크롤링 애플리케이션입니다.

## ✨ 주요 기능

- 🔍 **제품 검색**: 키워드를 통한 가이드컴 제품 검색
- 🏭 **브랜드 필터**: 24개 주요 브랜드별 제품 필터링
- 💰 **가격순 정렬**: 최저가부터 자동 정렬
- 📊 **스펙 정보**: 최대 8개 상세 스펙 정보 제공
- 📱 **반응형 디자인**: 모바일/태블릿/데스크톱 지원
- 🔄 **중복 제거**: 동일 제품 자동 중복 제거

## 🚀 Streamlit Cloud 배포

### 1. GitHub 저장소 생성
1. GitHub에 새 저장소 생성
2. 이 폴더의 모든 파일을 업로드

### 2. Streamlit Cloud 배포
1. [Streamlit Cloud](https://streamlit.io/cloud) 접속
2. GitHub 계정으로 로그인
3. "New app" 클릭
4. 저장소 선택 및 `app.py` 지정
5. Deploy 클릭

## 📁 파일 구조

```
가이드컴/
├── app.py              # Streamlit 웹앱 메인 파일
├── guidecom.py         # 가이드컴 크롤링 모듈
├── danawa.py           # 다나와 크롤링 모듈 (참조용)
├── requirements.txt    # 필요한 패키지 목록
├── dibugguid.txt      # 가이드컴 API 구조 분석
├── goods.txt          # HTML 구조 샘플
└── README.md          # 프로젝트 설명
```

## 🛠️ 로컬 실행

```bash
# 패키지 설치
pip install -r requirements.txt

# Streamlit 앱 실행
streamlit run app.py
```

## 📋 사용 방법

1. **검색어 입력**: 찾고자 하는 제품명 입력 (예: SSD, 그래픽카드)
2. **제조사 검색**: "제조사 검색" 버튼 클릭
3. **브랜드 선택**: 원하는 브랜드들을 체크박스로 선택
4. **제품 검색**: "선택한 제조사로 제품 검색" 버튼 클릭
5. **결과 확인**: 테이블에서 제품명, 가격, 사양 확인
6. **새로 검색**: "새로 검색하기" 버튼으로 초기화

## 🎯 지원 브랜드 (24개)

### 주요 하드웨어 브랜드
- **CPU/GPU**: 삼성전자, 인텔, AMD, NVIDIA
- **저장장치**: WD, 시게이트, Crucial, Kingston, ADATA
- **메모리**: G.SKILL, Corsair, Patriot, Team, GeIL
- **그래픽카드**: MSI, ASUS, 기가바이트, EVGA, Zotac, Sapphire, PowerColor, XFX
- **기타**: OCZ, PNY

## 🌐 API 구조

가이드컴 검색 API:
```
https://www.guidecom.co.kr/search/index.html?keyword={검색어}&order={정렬옵션}
```

### 정렬 옵션
- `event_goods`: 행사상품순
- `price_0`: 낮은가격순  
- `reco_goods`: 인기상품순

## 📊 데이터 파싱 구조

### HTML 구조 (goods.txt 기반)
```html
<ul class="product_list">
  <li>
    <div class="prod_info">
      <p class="prod_name">
        <a>상품명</a>
      </p>
    </div>
    <div class="prod_pricelist">
      <p class="price_sect">
        <strong>가격</strong>
      </p>
    </div>
    <div class="spec_list">
      <span class="highlight">스펙1</span>
      <span class="highlight">스펙2</span>
      <!-- 최대 8개 스펙 -->
    </div>
  </li>
</ul>
```

## 🔧 주요 클래스 및 메소드

### GuidecomParser 클래스
```python
class GuidecomParser:
    def get_search_options(keyword: str) -> List[Dict[str, str]]
    def search_products(keyword: str, sort_type: str, maker_codes: List[str], limit: int) -> List[Product]
    def get_unique_products(keyword: str, maker_codes: List[str]) -> List[Product]
```

### Product 데이터 구조
```python
@dataclass
class Product:
    name: str           # 제품명
    price: str          # 가격
    specifications: str # 상세 사양 (스펙1 ~ 스펙8)
```

## 🎨 주요 특징

- **danawa.py 호환**: 동일한 인터페이스로 쉬운 통합
- **실시간 검색**: 빠른 응답과 부드러운 UX
- **다중 브랜드 필터**: 여러 브랜드 동시 선택
- **자동 중복 제거**: 동일 제품명 자동 필터링
- **스펙 정보 구조화**: highlight 클래스 기반 스펙 파싱

## 🔧 기술 스택

- **Frontend**: Streamlit
- **Backend**: Python 3.7+
- **크롤링**: BeautifulSoup4, Requests
- **데이터 처리**: Pandas
- **배포**: Streamlit Cloud

## ⚠️ 주의사항

- 웹 크롤링 시 사이트의 robots.txt 및 이용약관을 준수하세요
- 과도한 요청으로 인한 서버 부하를 방지하기 위해 적절한 딜레이를 사용하세요
- 가이드컴 사이트 구조 변경 시 파싱 로직 업데이트가 필요할 수 있습니다

## 🚀 향후 계획

- danawa.py와 guidecom.py 통합
- 더 많은 브랜드 지원
- Excel 다운로드 기능 추가
- 가격 변동 추적 기능

## 📝 라이선스

이 프로젝트는 교육 목적으로 제작되었습니다.

## 🤝 기여

버그 리포트나 기능 개선 제안은 이슈를 통해 제출해주세요.

---

⭐ 도움이 되었다면 별표를 눌러주세요!