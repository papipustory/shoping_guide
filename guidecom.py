import os
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus
import re
import time
import random

"""
Guidecom 상품 검색/파싱 모듈 (app.py 수정 없이 사용)
- 요구사항: 낮은가격 3 + 인기상품 4 + 행사상품 3 = 총 10개, 중복 없이 반환
- 검색 엔드포인트 2가지 모두 지원
  1) GET  https://www.guidecom.co.kr/search/index.html?keyword=...&order=...
  2) POST https://www.guidecom.co.kr/search/list.php (keyword/order/lpp/page)
- 디버깅: 환경변수 GUIDECOM_DEBUG=1 이면 상세 로그를 콘솔(스트림릿 로그)로 출력
"""

@dataclass
class Product:
    name: str
    price: str
    specifications: str

class GuidecomParser:
    def __init__(self) -> None:
        self.base_url = "https://www.guidecom.co.kr/search/index.html"
        self.list_url = "https://www.guidecom.co.kr/search/list.php"
        self.alternative_urls = [
            "https://www.guidecom.co.kr/search/",
            "https://www.guidecom.co.kr/shop/search.html",
            "https://www.guidecom.co.kr/shop/",
        ]
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
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        ]
        # 세션 시작 시 데스크톱 UA 부여
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        })

    def _update_headers(self) -> None:
        # 기존 로직 유지(최소 수정): 가벼운 헤더 갱신
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

    # --- 추가: 세션 예열(최소 수정) ---
    def _prewarm_session(self, keyword: str, order: str = "reco_goods") -> str:
        """
        POST 전에 실제 브라우저처럼 검색 페이지를 먼저 GET하여
        서버가 주는 쿠키/세션을 확보한다.
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
        """list.php로 직접 POST하여 goods-row HTML 조
