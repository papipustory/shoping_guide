import os
import re
import time
import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


@dataclass
class Product:
    name: str
    price: str
    specifications: str


class GuidecomParser:
    """
    Guidecom 상품 검색/파싱 모듈 (원본 인터페이스 유지)
    - 낮은가격 3 + 인기상품 4 + 행사상품 3 = 총 10개, 중복 없이 반환
    - 검색 엔드포인트:
        1) GET  https://www.guidecom.co.kr/search/index.html?keyword=...&order=...
        2) POST https://www.guidecom.co.kr/search/list.php (keyword/order/lpp/page)
    - 디버그: GUIDECOM_DEBUG=1 → 로그 출력
    """

    def __init__(self) -> None:
        self.base_url = "https://www.guidecom.co.kr/search/index.html"
        self.list_url = "https://www.guidecom.co.kr/search/list.php"
        self.debug = str(os.getenv("GUIDECOM_DEBUG", "0")).lower() in {"1", "true", "yes"}
        self.session = requests.Session()
        self.last_request_time = 0.0
        self._setup_session()

    # ---------------- Debug helper ----------------
    def _dbg(self, msg: str) -> None:
        if self.debug:
            print(f"[GUIDECOM][DEBUG] {msg}", flush=True)

    # ---------------- Session helpers ----------------
    def _setup_session(self) -> None:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        ]
        self.session.headers.update({
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        })

    def _update_headers(self) -> None:
        # 최소 변경: 캐시 헤더만 갱신
        self.session.headers.update({
            "Cache-Control": random.choice(["no-cache", "max-age=0"]),
        })

    def _get_random_delay(self, a: float = 0.35, b: float = 0.9) -> float:
        return random.uniform(a, b)

    def _wait_between_requests(self, min_gap: float = 0.25) -> None:
        now = time.time()
        delta = now - self.last_request_time
        if delta < min_gap:
            time.sleep(min_gap - delta)
        self.last_request_time = time.time()

    def _fix_encoding(self, resp: requests.Response) -> None:
        try:
            if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "utf-8"):
                resp.encoding = resp.apparent_encoding or resp.encoding
        except Exception:
            pass

    # ---------------- HTTP helpers ----------------
    def _make_request(self, url: str, params: Optional[Dict[str, str]] = None, retries: int = 3) -> requests.Response:
        last_exc = None
        for attempt in range(retries):
            try:
                self._update_headers()
                self._wait_between_requests()
                if attempt > 0:
                    time.sleep(self._get_random_delay(1.2, 2.2))
                self._dbg(f"GET {url} params={params}")
                resp = self.session.get(url, params=params, timeout=20, allow_redirects=True)
                self._fix_encoding(resp)
                self._dbg(f"GET status={resp.status_code} encoding={resp.encoding} len={len(resp.text)}")
                if resp.status_code != 200:
                    self._dbg(f"!!! FAILED REQUEST !!! status_code={resp.status_code}")
                    self._dbg(f"Response Text (first 500 chars): {resp.text[:500]}")
                if resp.status_code == 200 and len(resp.text) > 300:
                    return resp
            except requests.RequestException as e:
                last_exc = e
                self._dbg(f"GET exception: {e}")
        raise last_exc if last_exc else RuntimeError("요청 실패")

    # --- 세션 예열: POST 전에 검색 페이지 먼저 방문해 쿠키/세션 확보 ---
    def _prewarm_session(self, keyword: str, order: str = "reco_goods") -> str:
        pre_url = f"https://www.guidecom.co.kr/search/?keyword={quote_plus(keyword)}&order={order}"
        self._dbg(f"PRE GET {pre_url}")
        try:
            self._update_headers()
            self._wait_between_requests()
            pre = self.session.get(pre_url, timeout=20, allow_redirects=True)
            self._fix_encoding(pre)
            self._dbg(f"PRE status={pre.status_code} len={len(pre.text)}")
        except requests.RequestException as e:
            self._dbg(f"PRE exception: {e}")
        time.sleep(self._get_random_delay(0.6, 1.2))
        return pre_url

    def _post_list(self, keyword: str, order: str, page: int = 1, lpp: int = 30) -> Optional[BeautifulSoup]:
        """list.php로 직접 POST하여 goods-row HTML 조각을 받는다."""
        try:
            # 최소 변경: 세션 예열 + AJAX성 헤더
            referer = self._prewarm_session(keyword, order=order)
            self._update_headers()
            self._wait_between_requests()

            headers = {
                "Referer": referer,
                "Origin": "https://www.guidecom.co.kr",
                "X-Requested-With": "XMLHttpRequest",
            }
            data = {"keyword": keyword, "order": order, "lpp": lpp, "page": page, "y": 0}
            self._dbg(f"POST {self.list_url} data={data} referer={referer}")
            resp = self.session.post(self.list_url, data=data, headers=headers, timeout=20)
            self._fix_encoding(resp)
            self._dbg(f"POST status={resp.status_code} encoding={resp.encoding} len={len(resp.text)}")
            if resp.status_code == 200 and len(resp.text) > 100:
                soup = BeautifulSoup(resp.text, "lxml")
                rows = soup.find_all("div", class_="goods-row")
                self._dbg(f"POST parsed goods-row={len(rows)}")
                return soup
        except requests.RequestException as e:
            self._dbg(f"POST exception: {e}")
            return None
        return None

    # ---------------- Parsing helpers ----------------
    def _find_goods_list(self, soup: BeautifulSoup):
        gl = soup.find(id="goods-list")
        if gl:
            return gl
        placeholder = soup.find(id="goods-placeholder")
        if placeholder:
            inner = placeholder.find(id="goods-list")
            if inner:
                return inner
        # list.php 응답은 래퍼 없이 goods-row만 내려올 수 있으므로 soup 자체를 반환
        return soup

    def _extract_text(self, el) -> str:
        return el.get_text(" ", strip=True) if el else ""

    def _parse_price(self, text: str) -> str:
        digits = re.sub(r"[^\d]", "", text or "")
        if not digits:
            return ""
        return f"{int(digits):,}원"

    def _parse_product_item(self, row) -> Optional[Product]:
        try:
            # 이름
            name_el = row.select_one(".desc .goodsname1")
            if not name_el:
                name_el = row.select_one(".desc h4.title a") or row.select_one("h4.title a")
            name = self._extract_text(name_el)
            if not name:
                self._dbg("name not found; row snippet=" + (row.decode()[:200] if hasattr(row, 'decode') else str(row)[:200]))
                return None

            # (원본 유지) 주요 사양: .desc .feature만 사용
            spec_el = row.select_one(".desc .feature")
            specs = self._extract_text(spec_el)

            # 가격
            price_el = row.select_one(".prices .price-large span") or row.select_one(".price-large span")
            price = self._parse_price(self._extract_text(price_el))

            return Product(name=name, price=price, specifications=specs)
        except Exception as e:
            self._dbg(f"_parse_product_item exception: {e}")
            return None

    # ---------------- Manufacturer helpers ----------------
    def _normalize_brand(self, text: str) -> str:
        t = (text or "").lower()
        t = re.sub(r"[\s._/-]+", " ", t).strip()
        aliases = {
            "wd": "western digital",
            "웨스턴 디지털": "western digital",
            "에이수스": "asus",
            "기가바이트": "gigabyte",
            "조텍": "zotac",
            "엔비디아": "nvidia",
            "삼성": "삼성전자",
            "samsung": "삼성전자",
            "g skill": "gskill",
            "tp-link": "tp link",
        }
        return aliases.get(t, t)

    def _extract_manufacturer(self, product_name: str) -> Optional[str]:
        """
        제품명에서 제조사처럼 보이는 토큰을 추출.
        선행 수식어/상태어(신제품/병행/벌크/품절/월표기 등)는 건너뜀.
        """
        if not product_name:
            return None
        text = re.sub(r"\[[^\]]+\]", " ", product_name)
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()
        if not words:
            return None

        skip = {"신제품", "공식인증", "병행수입", "병행", "벌크", "정품", "스페셜", "한정판", "품절"}
        month_pat = re.compile(r"^(?:[0-9Oo]{1,2})월")  # 9월, 10월, o월 등

        i = 0
        while i < len(words) and (words[i] in skip or month_pat.match(words[i])):
            i += 1
        if i >= len(words):
            return None

        manufacturer = words[i]
        # 2단어 브랜드 결합 (Western Digital, TP LINK 등)
        if i + 1 < len(words):
            pair = f"{manufacturer} {words[i+1]}"
            if self._normalize_brand(pair) in {"western digital", "tp link"}:
                manufacturer = pair
        return manufacturer

    def _filter_by_maker(self, product: Product, maker_codes: List[str]) -> bool:
        if not maker_codes:
            return True
        manufacturer = self._extract_manufacturer(product.name)
        if not manufacturer:
            return False
        man_norm = self._normalize_brand(manufacturer)
        sel_norms = [self._normalize_brand(code.replace("_", " ")) for code in maker_codes]
        for sel in sel_norms:
            if man_norm == sel or man_norm in sel or sel in man_norm:
                return True
        # 느슨한 별칭 매칭
        brand_pairs = [
            ("western digital", ["wd", "western", "digital"]),
            ("삼성전자", ["samsung", "삼성"]),
            ("asus", ["에이수스"]),
            ("gigabyte", ["기가바이트"]),
            ("zotac", ["조텍"]),
            ("nvidia", ["엔비디아"]),
            ("tp link", ["tp-link"]),
        ]
        for canonical, aliases in brand_pairs:
            if man_norm == canonical and any(a in sel_norms for a in aliases):
                return True
            if man_norm in aliases and any(sel == canonical for sel in sel_norms):
                return True
        return False

    # ---------------- Public API ----------------
    def _resolve_order_param(self, sort_type: str) -> str:
        mapping = {
            "price_0": "price_0", "낮은가격": "price_0", "priceasc": "price_0",
            "reco_goods": "reco_goods", "인기상품": "reco_goods", "opiniondesc": "reco_goods",
            "event_goods": "event_goods", "행사상품": "event_goods", "savedesc": "event_goods",
        }
        k = (sort_type or "").lower()
        return mapping.get(k, "reco_goods")

    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        """키워드 검색 결과에서 제조사 후보 최대 8개 반환 (POST 우선, GET 보조)."""
        manufacturers: List[str] = []
        seen = set()
        try:
            soup = self._post_list(keyword, order="reco_goods", page=1, lpp=30)
            rows = soup.find_all("div", class_="goods-row") if soup else []
            if not rows:
                params = {"keyword": keyword}
                resp = self._make_request(self.base_url, params=params)
                soup2 = BeautifulSoup(resp.text, "lxml")
                container = self._find_goods_list(soup2)
                rows = container.find_all("div", class_="goods-row") if container else []

            self._dbg(f"get_search_options: goods-row count={len(rows)}")
            sample_names: List[str] = []

            for idx, row in enumerate(rows[:80]):
                name_el = row.select_one(".desc .goodsname1") or row.select_one(".desc h4.title a") or row.select_one("h4.title a")
                nm = self._extract_text(name_el)
                if self.debug and idx < 10 and nm:
                    sample_names.append(nm)
                maker = self._extract_manufacturer(nm)
                if maker and maker not in seen:
                    manufacturers.append(maker)
                    seen.add(maker)
                if len(manufacturers) >= 8:
                    break

            if self.debug and sample_names:
                self._dbg("sample names: " + " | ".join(sample_names))
                self._dbg("manufacturers: " + ", ".join(manufacturers))

            def sort_key(x: str):
                xn = self._normalize_brand(x)
                return (0 if re.search(r"[가-힣]", x) else 1, xn)

            return [{"name": m, "code": self._normalize_brand(m).replace(" ", "_")} for m in sorted(manufacturers, key=sort_key)]
        except Exception as e:
            self._dbg(f"get_search_options exception: {e}")
            return []

    def search_products(self, keyword: str, sort_type: str, maker_codes: List[str], limit: int = 50) -> List[Product]:
        """
        단일 정렬 기준으로 제품 최대 `limit`개 반환 (POST 우선, GET 보조).
        - POST 응답에 .feature가 전혀 없으면 GET 페이지로 폴백(사양 공란 방지)
        """
        try:
            order = self._resolve_order_param(sort_type)

            # 1) POST 우선
            soup = self._post_list(keyword, order=order, page=1, lpp=40)
            rows = soup.find_all("div", class_="goods-row") if soup else []

            # ★ POST 응답에서 .feature 가 하나도 없으면 GET으로 폴백
            if rows:
                feat_cnt = sum(1 for r in rows[:20] if r.select_one(".desc .feature"))
                if feat_cnt == 0:
                    self._dbg("POST rows have no .feature; fallback to GET page.")
                    rows = []

            # 2) GET 보조
            if not rows:
                params = {"keyword": keyword, "order": order}
                resp = self._make_request(self.base_url, params=params)
                soup2 = BeautifulSoup(resp.text, "lxml")
                container = self._find_goods_list(soup2)
                rows = container.find_all("div", class_="goods-row") if container else []

            self._dbg(f"search_products: order={order} rows={len(rows)}")

            out: List[Product] = []
            for row in rows:
                p = self._parse_product_item(row)
                if not p:
                    continue
                if not self._filter_by_maker(p, maker_codes):
                    continue
                out.append(p)
                if len(out) >= limit:
                    break

            self._dbg(f"search_products: returned={len(out)}")
            return out
        except Exception as e:
            self._dbg(f"search_products exception: {e}")
            return []

    def get_unique_products(self, keyword: str, maker_codes: List[str]) -> List[Product]:
        """낮은가격 3 + 인기상품 4 + 행사상품 3 = 총 10개(중복 제거)."""
        buckets: List[Tuple[str, int]] = [
            ("price_0", 3),     # 낮은가격
            ("reco_goods", 4),  # 인기상품
            ("event_goods", 3), # 행사상품
        ]
        results: List[Product] = []
        seen_names = set()

        for order, want in buckets:
            candidates = self.search_products(keyword, order, maker_codes, limit=60)
            took = 0
            for p in candidates:
                if p.name in seen_names:
                    continue
                results.append(p)
                seen_names.add(p.name)
                took += 1
                if took >= want:
                    break

        self._dbg(f"get_unique_products: total={len(results)} unique names={len(seen_names)}")
        return results[:10]
