import os
import io
import streamlit as st
import pandas as pd
from guidecom import GuidecomParser, Product

# (선택) 클라우드에서 Secrets로 디버그 제어
try:
    dbg = st.secrets.get("GUIDECOM_DEBUG", None)
    if dbg is not None:
        os.environ["GUIDECOM_DEBUG"] = str(dbg)
except Exception:
    pass

st.set_page_config(page_title="가이드컴 상품 검색", layout="wide")
st.title("🛒 가이드컴 상품 검색기")

# --- Session State 초기화 (기존 키/흐름 유지) ---
if 'parser' not in st.session_state:
    st.session_state.parser = GuidecomParser()
if 'keyword' not in st.session_state:
    st.session_state.keyword = ""
if 'manufacturers' not in st.session_state:
    st.session_state.manufacturers = []
if 'selected_manufacturers' not in st.session_state:
    st.session_state.selected_manufacturers = {}
if 'products' not in st.session_state:
    st.session_state.products = []

# --- 1) 키워드 입력 (기존 form + 버튼) ---
with st.form(key="search_form"):
    keyword_input = st.text_input(
        "검색어를 입력하세요:",
        placeholder="예: 그래픽카드, SSD",
        value=st.session_state.get("keyword", "")
    )
    search_button = st.form_submit_button(label="제조사 검색")

if search_button:
    st.session_state.keyword = keyword_input.strip()
    st.session_state.products = []  # 새로운 검색 시 이전 결과 초기화
    if st.session_state.keyword:
        with st.spinner("제조사 정보를 가져오는 중..."):
            st.session_state.manufacturers = st.session_state.parser.get_search_options(st.session_state.keyword)
            # 기존 형태 유지: dict[name] = bool
            st.session_state.selected_manufacturers = {m['name']: False for m in st.session_state.manufacturers}
            if not st.session_state.manufacturers:
                st.warning("해당 검색어에 대한 제조사 정보를 찾을 수 없습니다.")
    else:
        st.warning("검색어를 입력해주세요.")

# --- 2) 제조사 선택 (기존 체크박스 + 제출 버튼) ---
if st.session_state.manufacturers:
    st.subheader("제조사를 선택하세요 (중복 가능)")
    with st.form(key="manufacturer_form"):
        cols = st.columns(4)
        for i, manufacturer in enumerate(st.session_state.manufacturers):
            with cols[i % 4]:
                st.checkbox(manufacturer['name'], key=f"mfr_{i}")  # 기존 키 유지
        product_search_button = st.form_submit_button("선택한 제조사로 제품 검색")

    if product_search_button:
        # 체크박스 상태 회수 → code 리스트
        selected_codes = []
        for i, manufacturer in enumerate(st.session_state.manufacturers):
            if st.session_state.get(f"mfr_{i}", False):
                selected_codes.append(manufacturer['code'])
                # 호환성: 기존 dict도 함께 갱신
                st.session_state.selected_manufacturers[manufacturer['name']] = True

        if not selected_codes:
            st.warning("하나 이상의 제조사를 선택해주세요.")
        else:
            with st.spinner('제품 정보를 검색 중입니다...'):
                st.session_state.products = st.session_state.parser.get_unique_products(
                    st.session_state.keyword, selected_codes
                )
                if not st.session_state.products:
                    st.info("선택된 제조사의 제품을 찾을 수 없습니다.")
                st.rerun()  # 기존 흐름 유지

# --- 3) 결과 표시 ---
if st.session_state.products:
    st.subheader(f"'{st.session_state.keyword}'에 대한 검색 결과")

    # 가격 오름차순 정렬 (기존 로직 유지)
    def extract_price(product: Product):
        try:
            price_str = product.price.replace('원', '').replace(',', '')
            return int(price_str)
        except (ValueError, AttributeError):
            return float('inf')

    sorted_products = sorted(st.session_state.products, key=extract_price)
    data = [{
        "제품명": p.name,
        "가격": p.price,
        "주요 사양": p.specifications
    } for p in sorted_products]

    df = pd.DataFrame(data)
    st.dataframe(df, height=35 * (len(df) + 1), use_container_width=True)

    # (수정) 안전한 다운로드: BytesIO 사용 → TypeError 방지
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ CSV 다운로드", data=csv_bytes, file_name="guidecom_search.csv", mime="text/csv")

    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="검색결과")
    xlsx_buffer.seek(0)
    st.download_button(
        "⬇️ 엑셀 다운로드",
        data=xlsx_buffer,
        file_name="guidecom_search.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Reset
    if st.button("새로 검색하기"):
        st.session_state.keyword = ""
        st.session_state.manufacturers = []
        st.session_state.selected_manufacturers = {}
        st.session_state.products = []
        st.rerun()
