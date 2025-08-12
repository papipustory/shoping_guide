import os
import re
import time
import random
from dataclasses import dataclass
from typing import List, Dict, Optional
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
    Guidecom 상품 검색/파싱 모듈

    - 요구사항: 낮은가격 3 + 인기상품 4 + 행사상품 3 = 총 10개, 중복 없이 반환
    - 검색 엔드포인트 2가지 모두 지원
      1) GET  https://www.guidecom.co.kr/search/index.html?keyword=...&order=...
      2) POST https://www.guidecom.co.kr/search/list.php (keyword/order/lpp/page)
    """

    def __init__(self) -> None:
        self.base_url = "https://www.guidecom.co.kr/search/index.html"
        self.list_url = "https://www.guidecom.co.kr/search/list.php"
        self.debug = str(os.getenv("GUIDECOM_DEBUG", "0")).lower() in {"1", "true", "yes"}
        self.session = requests.Session()
        self.last_request_time = 0.0
        self._setup_session()

    # ----------------------- Debug helper -----------------------
    def _dbg(self, msg: str) -> None:
        if self.debug:
            print(f"[GUIDECOM][DEBUG] {msg}", flush=True)

    # ----------------------- Session helpers -----------------------
    def _setup_session(self) -> None:
        # 세션 시작 시 하나를 고정 선택 (요청마다 바꾸면 봇 시그널이 될 수 있음)
        user_agents = [
            # 최신/일반적인 데스크톱 브라우저 UA 3종
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        ]
        fixed_ua = random.choice(user_agents)
        self.session.headers.update({
            "User-Agent": fixed_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        })

    def _update_headers(self) -> None:
        # UA는 고정, 가벼운 헤더만 갱신
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

    # ----------------------- HTTP helpers -----------------------
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

    def _prewarm_session(self, keyword: str, order: str = "reco_goods") -> str:
        """
        POST 호출 전에 실제 브라우저처럼 검색 페이지를 먼저 GET하여
        세션/쿠키를 확보한다.
        """
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
        """
        list.php로 직접 POST (AJAX 응답 HTML). 세션 예열 + AJAX 헤더 보강 포함.
        """
        try:
            referer = self._prewarm_session(keyword, order=order)
            self._update_headers()
            self._wait_between_requests()

            headers = {
                "Referer": referer,
                "Origin": "https://www.guidecom.co.kr",
                "X-Requested-With": "XMLHttpRequest",
            }
            data = {"keyword": keyword, "order": order, "lpp": lpp, "page": page, "y": 0}
            self._dbg(f"POST {self.list_url} data={data}")
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

    # ----------------------- Parsing helpers -----------------------
    def _find_goods_list(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """
        검색 페이지에서 상품 리스트 컨테이너를 찾아 반환.
        list.php 응답은 goods-row 묶음만 내려올 수 있으므로 soup 자체를 받게 될 수도 있음.
        """
        gl = soup.find(id="goods-list")
        if gl:
            return gl
        placeholder = soup.find(id="goods-placeholder")
        if placeholder:
            inner = placeholder.find(id="goods-list")
            if inner:
                return inner
        return soup

    def _extract_text(self, el) -> str:
        return el.get_text(" ", strip=True) if el else ""

    def _parse_price(self, text: str) -> str:
        digits = re.sub(r"[^\d]", "", text or "")
        if not digits:
            return ""
        return f"{int(digits):,}원"

    def _parse_product_item(self, row) -> Optional[Product]:
        """
        goods-row 하나에서 Product 추출
        """
        try:
            # 이름: goodsname1 우선, 없으면 타이틀 a
            name_el = row.select_one(".desc .goodsname1")
            if not name_el:
                name_el = row.select_one(".desc h4.title a") or row.select_one("h4.title a")
            name = self._extract_text(name_el)

            # 사양: .spec 또는 .desc > ul/li 텍스트 모음
            spec_el = row.select_one(".desc .spec")
            if spec_el:
                specs = self._extract_text(spec_el)
            else:
                li_texts = [self._extract_text(li) for li in row.select(".desc li")]
                specs = " / ".join([t for t in li_texts if t])[:200]

            # 가격: .price-large 내부 숫자
            price_el = row.select_one(".prices .price-large span") or row.select_one(".price-large span")
            price = self._parse_price(self._extract_text(price_el))

            if not name:
                return None
            return Product(name=name, price=price, specifications=specs)
        except Exception as e:
            self._dbg(f"_parse_product_item exception: {e}")
            return None

    # ----------------------- Manufacturer helpers -----------------------
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
        제품명에서 제조사처럼 보이는 토큰을 추출
        """
        if not product_name:
            return None

        # 대괄호 태그 제거
        text = re.sub(r"\[[^\]]+\]", " ", product_name)
        text = re.sub(r"\s+", " ", text).strip()

        tokens = re.split(r"[ /\-|]", text)
        candidates = []
        for tok in tokens:
            tt = tok.strip()
            if not tt or len(tt) < 2:
                continue
            # 흔한 접두/시리즈/규격은 제외
            if re.search(r"^(pro|ultra|max|mini|lite|plus|gaming|rog|tuf|strix|evo|neo|rgb|ddr|nvme|pcie|m\.2|sata|atx|matx|itx|oem|bulk|retail)$", tt, flags=re.I):
                continue
            candidates.append(tt)

        if not candidates:
            return None

        # 첫 1~2개 토큰에서 브랜드가 보통 나옴
        best = candidates[0]
        best_norm = self._normalize_brand(best)
        return best if best_norm == best else best_norm

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
        # 느슨한 포함 규칙 (보편적인 별칭)
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
        return False

    # ----------------------- Public APIs -----------------------
    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        """
        키워드로 검색된 결과에서 제조사 후보들을 추정하여
        [{"name":"삼성전자","code":"삼성전자"}, ...] 형태로 반환.

        1) POST list.php 시도(인기상품 기준)
        2) 실패 시 GET 페이지 파싱
        """
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

            for idx, row in enumerate(rows[:100]):
                name_el = row.select_one(".desc .goodsname1") or row.select_one(".desc h4.title a") or row.select_one("h4.title a")
                nm = self._extract_text(name_el)
                if self.debug and idx < 10 and nm:
                    sample_names.append(nm)
                maker = self._extract_manufacturer(nm)
                if maker and maker not in seen:
                    manufacturers.append(maker)
                    seen.add(maker)

            if self.debug and sample_names:
                self._dbg("sample product names → makers:")
                for s in sample_names:
                    self._dbg(f"  - {s[:80]} → {self._extract_manufacturer(s)}")

            # 정렬: 한글 우선, 동일 언어끼리는 정규화 이름으로 정렬
            def sort_key(x: str):
                xn = self._normalize_brand(x)
                has_kor = bool(re.search(r"[가-힣]", x))
                return (0 if has_kor else 1, xn)

            return [{"name": m, "code": self._normalize_brand(m).replace(" ", "_")} for m in sorted(manufacturers, key=sort_key)]
        except Exception as e:
            self._dbg(f"get_search_options exception: {e}")
            return []

    def _resolve_order_param(self, sort_type: str) -> str:
        mapping = {
            "price_0": "price_0", "낮은가격": "price_0", "priceasc": "price_0",
            "reco_goods": "reco_goods", "인기상품": "reco_goods", "opiniondesc": "reco_goods",
            "event_goods": "event_goods", "행사상품": "event_goods", "savedesc": "event_goods",
        }
        k = (sort_type or "").lower()
        return mapping.get(k, "reco_goods")

    def search_products(self, keyword: str, sort_type: str, maker_codes: List[str], limit: int = 50) -> List[Product]:
        """
        단일 정렬 기준으로 제품 최대 `limit`개 반환 (list.php 우선, 실패 시 GET 보조)
        """
        try:
            order = self._resolve_order_param(sort_type)

            soup = self._post_list(keyword, order=order, page=1, lpp=limit)
            rows = soup.find_all("div", class_="goods-row") if soup else []

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
        """
        낮은가격 3 + 인기상품 4 + 행사상품 3 = 총 10개, 이름으로 중복 제거
        """
        results: List[Product] = []
        seen_names = set()

        buckets = [("price_0", 3), ("reco_goods", 4), ("event_goods", 3)]
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
