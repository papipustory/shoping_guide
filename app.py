import os
import streamlit as st
import pandas as pd
from typing import List, Dict
from guidecom import GuidecomParser, Product

# --- Read debug flag from Secrets (optional) ---
try:
    dbg = st.secrets.get("GUIDECOM_DEBUG", None)
    if dbg is not None:
        os.environ["GUIDECOM_DEBUG"] = str(dbg)
except Exception:
    pass

st.set_page_config(page_title="가이드컴 상품 검색", layout="wide")
st.title("🛒 가이드컴 상품 검색기")

# --- Session init ---
if "parser" not in st.session_state:
    st.session_state.parser = GuidecomParser()
if "keyword" not in st.session_state:
    st.session_state.keyword = ""
if "manufacturers" not in st.session_state:
    st.session_state.manufacturers = []   # [{"name": "...", "code":"..."}]
if "selected_codes" not in st.session_state:
    st.session_state.selected_codes = []  # ["asus","gigabyte",...]

parser: GuidecomParser = st.session_state.parser

with st.sidebar:
    st.subheader("검색 설정")
    keyword = st.text_input("키워드", value=st.session_state.keyword, placeholder="예) SSD, 4060, 라이젠 7 등")
    if st.button("🔎 제조사 불러오기", use_container_width=True):
        st.session_state.keyword = keyword.strip()
        if not st.session_state.keyword:
            st.warning("키워드를 입력해주세요.")
        else:
            with st.spinner("제조사 목록을 가져오는 중..."):
                st.session_state.manufacturers = parser.get_search_options(st.session_state.keyword)
                # 기존 선택값은 유지하되, 목록에 없는 건 제거
                codes = {m["code"] for m in st.session_state.manufacturers}
                st.session_state.selected_codes = [c for c in st.session_state.selected_codes if c in codes]

    if st.session_state.manufacturers:
        st.caption("제조사 필터(선택사항)")
        # 멀티셀렉트로 깔끔하게
        display_to_code = {m["name"]: m["code"] for m in st.session_state.manufacturers}
        selected_display = st.multiselect(
            "제조사 선택 (미선택 시 전체)",
            options=list(display_to_code.keys()),
            default=[name for name, code in display_to_code.items() if code in st.session_state.selected_codes],
        )
        st.session_state.selected_codes = [display_to_code[name] for name in selected_display]

    run_search = st.button("📦 제품 불러오기", type="primary", use_container_width=True)

# --- Main area ---
if run_search:
    if not st.session_state.keyword:
        st.error("키워드를 먼저 입력한 뒤, [제품 불러오기]를 클릭하세요.")
    else:
        with st.spinner("제품을 수집/정리하는 중..."):
            products: List[Product] = parser.get_unique_products(
                keyword=st.session_state.keyword,
                maker_codes=st.session_state.selected_codes
            )

        if not products:
            st.info("조건에 맞는 제품이 없거나, 사이트에서 차단되어 데이터를 받지 못했습니다. (사이드바에서 GUIDECOM_DEBUG=1을 켜고 로그를 확인해 주세요.)")
        else:
            # 표 데이터 구성
            data: List[Dict[str, str]] = [{
                "제품명": p.name,
                "가격": p.price,
                "주요 사양": p.specifications,
            } for p in products]

            df = pd.DataFrame(data)
            st.subheader("검색 결과 (최대 10개, 중복 제거)")
            st.dataframe(df, use_container_width=True, height=38 * (len(df) + 1))

            # 다운로드
            col1, col2 = st.columns(2)
            with col1:
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇️ CSV 다운로드", data=csv, file_name="guidecom_search.csv", mime="text/csv")
            with col2:
                xlsx = df.to_excel(index=False, engine="openpyxl")
                # streamlit은 in-memory로 처리하기 어려우니, 임시 파일로 저장
                tmp_path = "/tmp/guidecom_search.xlsx"
                df.to_excel(tmp_path, index=False)
                with open(tmp_path, "rb") as f:
                    st.download_button("⬇️ 엑셀 다운로드", data=f, file_name="guidecom_search.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.divider()
with st.expander("디버그 안내"):
    st.markdown(
        """
        - Streamlit Cloud에서 **Settings → Secrets**에 `GUIDECOM_DEBUG="1"` 추가 시, 서버 로그에 상태코드/본문 길이/샘플명이 출력됩니다.
        - 403/503 또는 본문에 "Cloudflare/Just a moment" 등이 보이면 WAF/봇차단 가능성이 큽니다.
        """
    )
