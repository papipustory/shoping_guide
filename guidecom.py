import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import re
import time
import random

@dataclass
class Product:
    name: str
    price: str
    specifications: str

class GuidecomParser:
    """
    Guidecom 상품 검색 파서
    - 검색 페이지: https://www.guidecom.co.kr/search/index.html
    - 정렬 파라미터:
        * 낮은가격  -> order=price_0
        * 인기상품  -> order=reco_goods
        * 행사상품  -> order=event_goods
    """
    def __init__(self) -> None:
        self.base_url = "https://www.guidecom.co.kr/search/index.html"
        self.alternative_urls = [
            "https://www.guidecom.co.kr/search/",
            "https://www.guidecom.co.kr/shop/search.html",
            "https://www.guidecom.co.kr/shop/"
        ]
        self.session = requests.Session()
        self.last_request_time = 0.0
        self._setup_session()

    # ----------------------- Session helpers -----------------------
    def _setup_session(self) -> None:
        # 베이직 헤더
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        ]
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        })

    def _update_headers(self) -> None:
        # 가벼운 헤더 변조로 간단한 방어 우회
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Cache-Control": random.choice(["no-cache", "max-age=0"]),
        })

    def _get_random_delay(self, a: float = 0.4, b: float = 1.1) -> float:
        return random.uniform(a, b)

    def _wait_between_requests(self, min_gap: float = 0.25) -> None:
        now = time.time()
        delta = now - self.last_request_time
        if delta < min_gap:
            time.sleep(min_gap - delta)
        self.last_request_time = time.time()

    def _make_request(self, url: str, params: Optional[Dict[str, str]] = None, retries: int = 3) -> requests.Response:
        last_exc = None
        for attempt in range(retries):
            try:
                self._update_headers()
                self._wait_between_requests()
                if attempt > 0:
                    time.sleep(self._get_random_delay(1.5, 3.0))
                resp = self.session.get(url, params=params, timeout=20, allow_redirects=True)
                # 인코딩 보정(EUC-KR/ISO-8859-1 등)
                try:
                    if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "utf-8"):
                        resp.encoding = resp.apparent_encoding or resp.encoding
                except Exception:
                    pass
                if resp.status_code == 200 and len(resp.text) > 500:
                    return resp
            except requests.RequestException as e:
                last_exc = e
        raise last_exc if last_exc else RuntimeError("요청 실패")

    # ----------------------- Parsing helpers -----------------------
    def _find_goods_list(self, soup: BeautifulSoup):
        gl = soup.find(id="goods-list")
        if gl:
            return gl
        # 일부 페이지에서 placeholder만 먼저 노출되기도 함
        placeholder = soup.find(id="goods-placeholder")
        if placeholder:
            inner = placeholder.find(id="goods-list")
            if inner:
                return inner
        # 마지막으로 클래스 기반 탐색
        return soup.find("div", {"id": re.compile(r"^goods-list$")})

    def _extract_text(self, el) -> str:
        return el.get_text(" ", strip=True) if el else ""

    def _parse_price(self, text: str) -> str:
        # "46,010원" 혹은 "46,010" 형태 처리
        t = re.sub(r"[^\d]", "", text or "")
        if not t:
            return ""
        # 천단위 콤마 + 원
        return f"{int(t):,}원"

    def _parse_product_item(self, row) -> Optional[Product]:
        try:
            # 이름
            name_el = row.select_one(".desc h4.title a") or row.select_one("h4.title a")
            name = self._extract_text(name_el)
            if not name:
                return None
            # 스펙
            spec_el = row.select_one(".desc .feature")
            specs = self._extract_text(spec_el)
            # 가격
            price_el = row.select_one(".prices .price-large span") or row.select_one(".price-large span")
            price = self._parse_price(self._extract_text(price_el))
            return Product(name=name, price=price, specifications=specs)
        except Exception:
            return None

    # ----------------------- Manufacturer helpers -----------------------
    def _normalize_brand(self, text: str) -> str:
        t = (text or "").lower()
        t = re.sub(r"[\\s._/-]+", " ", t).strip()
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
        }
        return aliases.get(t, t)

    def _extract_manufacturer(self, product_name: str) -> Optional[str]:
        if not product_name:
            return None
        # [307842] 같은 코드 제거
        text = re.sub(r"\[[^\]]+\]", " ", product_name)
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()
        if not words:
            return None
        skip = {"신제품", "공식인증", "병행수입", "벌크", "정품", "스페셜", "한정판"}
        i = 0
        while i < len(words) and words[i] in skip:
            i += 1
        if i >= len(words):
            return None
        manufacturer = words[i]
        # Western Digital 두 단어 결합
        if i + 1 < len(words):
            pair = f"{manufacturer} {words[i+1]}"
            if self._normalize_brand(pair) == "western digital":
                manufacturer = pair
        return manufacturer

    def _extract_manufacturer_from_row(self, row) -> Optional[str]:
        name_el = row.select_one(".desc h4.title a") or row.select_one("h4.title a")
        name = self._extract_text(name_el)
        return self._extract_manufacturer(name)

    def _filter_by_maker(self, product: Product, maker_codes: List[str]) -> bool:
        if not maker_codes:
            return True
        manufacturer = self._extract_manufacturer(product.name)
        if not manufacturer:
            return False
        man_norm = self._normalize_brand(manufacturer)
        sel_norms = [self._normalize_brand(code.replace("_", " ")) for code in maker_codes]
        # 직접 일치 또는 포함
        for sel in sel_norms:
            if man_norm == sel or man_norm in sel or sel in man_norm:
                return True
        # 추가 별칭 쌍
        brand_pairs = [
            ("western digital", ["wd", "western", "digital"]),
            ("삼성전자", ["samsung", "삼성"]),
            ("asus", ["에이수스"]),
            ("gigabyte", ["기가바이트"]),
            ("zotac", ["조텍"]),
            ("nvidia", ["엔비디아"]),
        ]
        for canonical, aliases in brand_pairs:
            if man_norm == canonical and any(a == sel for sel in sel_norms for a in aliases):
                return True
            if man_norm in aliases and any(sel == canonical for sel in sel_norms):
                return True
        return False

    # ----------------------- Public API -----------------------
    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        """
        검색 키워드로 1페이지를 스캔하여 제조사 후보를 최대 8개까지 반환합니다.
        반환: [{"name": "...", "code": "..."}, ...]
        """
        try:
            params = {"keyword": keyword}
            resp = self._make_request(self.base_url, params=params)
            soup = BeautifulSoup(resp.text, "lxml")
            goods_list = self._find_goods_list(soup)
            if not goods_list:
                # 대체 URL 시도
                for alt in self.alternative_urls:
                    try:
                        resp2 = self._make_request(alt, params=params)
                        soup2 = BeautifulSoup(resp2.text, "lxml")
                        goods_list = self._find_goods_list(soup2)
                        if goods_list:
                            break
                    except Exception:
                        continue
            if not goods_list:
                return []
            manufacturers = []
            seen = set()
            rows = goods_list.find_all("div", class_="goods-row")
            for row in rows[:60]:
                maker = self._extract_manufacturer_from_row(row)
                if maker:
                    if maker not in seen:
                        manufacturers.append(maker)
                        seen.add(maker)
                if len(manufacturers) >= 8:
                    break
            # 보기 좋게 정렬(한글 우선)
            def sort_key(x: str):
                xn = self._normalize_brand(x)
                return (0 if re.search(r"[가-힣]", x) else 1, xn)
            result = [{"name": m, "code": self._normalize_brand(m).replace(" ", "_")} for m in sorted(manufacturers, key=sort_key)]
            return result
        except Exception:
            return []

    def _resolve_order_param(self, sort_type: str) -> str:
        """
        들어온 sort_type을 guidecom의 order 파라미터로 변환합니다.
        허용 입력 예:
          - 'price_0' / '낮은가격' / 'priceASC'
          - 'reco_goods' / '인기상품' / 'opinionDESC'
          - 'event_goods' / '행사상품' / 'saveDESC'
        """
        mapping = {
            "price_0": "price_0",
            "낮은가격": "price_0",
            "priceasc": "price_0",
            "reco_goods": "reco_goods",
            "인기상품": "reco_goods",
            "opiniondesc": "reco_goods",
            "event_goods": "event_goods",
            "행사상품": "event_goods",
            "savedesc": "event_goods",
        }
        k = (sort_type or "").lower()
        return mapping.get(k, "reco_goods")

    def search_products(self, keyword: str, sort_type: str, maker_codes: List[str], limit: int = 5) -> List[Product]:
        """
        단일 정렬 기준으로 상품을 최대 `limit`개까지 반환합니다.
        """
        try:
            order = self._resolve_order_param(sort_type)
            params = {"keyword": keyword, "order": order}
            resp = self._make_request(self.base_url, params=params)
            soup = BeautifulSoup(resp.text, "lxml")
            goods_list = self._find_goods_list(soup)
            if not goods_list:
                return []
            rows = goods_list.find_all("div", class_="goods-row")
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
            return out
        except Exception:
            return []

    def get_unique_products(self, keyword: str, maker_codes: List[str]) -> List[Product]:
        """
        요구사항:
        - 낮은가격 3개 + 인기상품 4개 + 행사상품 3개 = 총 10개
        - 전부 중복 없이
        """
        buckets: List[Tuple[str, int]] = [
            ("price_0", 3),     # 낮은가격
            ("reco_goods", 4),  # 인기상품
            ("event_goods", 3), # 행사상품
        ]
        results: List[Product] = []
        seen_names = set()

        for order, want in buckets:
            # 충분히 많이 가져와서 중복 제외 후 quota를 맞춘다
            candidates = self.search_products(keyword, order, maker_codes, limit=30)
            taken = 0
            for p in candidates:
                if p.name in seen_names:
                    continue
                results.append(p)
                seen_names.add(p.name)
                taken += 1
                if taken >= want:
                    break

        # 최종 10개(부족하면 있는 만큼 반환)
        return results[:10]
