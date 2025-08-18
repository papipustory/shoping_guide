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
        self.ajax_url = "https://www.guidecom.co.kr/ajax/search.php"  # AJAX 엔드포인트
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
        # 더 다양한 User-Agent로 클라우드 환경 우회
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        
        # 클라우드 환경에서 더 안정적인 헤더 설정
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

    def _update_headers(self) -> None:
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
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
            # 가이드컴은 EUC-KR 사용, 명시적으로 설정
            if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "utf-8"):
                # Content-Type에서 charset 확인
                content_type = resp.headers.get('content-type', '').lower()
                if 'euc-kr' in content_type:
                    resp.encoding = 'euc-kr'
                elif 'charset=euc-kr' in resp.text[:1000].lower():
                    resp.encoding = 'euc-kr'
                else:
                    resp.encoding = resp.apparent_encoding or 'euc-kr'  # 기본값을 euc-kr로
            self._dbg(f"Final encoding set to: {resp.encoding}")
        except Exception as e:
            self._dbg(f"Encoding fix failed: {e}")
            resp.encoding = 'euc-kr'  # 안전한 기본값

    def _make_request(self, url: str, params: Optional[Dict[str, str]] = None, retries: int = 5) -> requests.Response:
        last_exc = None
        for attempt in range(retries):
            try:
                self._update_headers()
                self._wait_between_requests()
                
                # 재시도시 더 긴 대기
                if attempt > 0:
                    delay = self._get_random_delay(2.0 + attempt, 4.0 + attempt)
                    self._dbg(f"Retry {attempt+1}/{retries}, waiting {delay:.2f}s")
                    time.sleep(delay)
                
                # 클라우드 환경을 위한 추가 헤더
                extra_headers = {
                    "Referer": "https://www.google.com/",
                    "Origin": "https://www.guidecom.co.kr" if "guidecom.co.kr" in url else None
                }
                extra_headers = {k: v for k, v in extra_headers.items() if v}
                
                self._dbg(f"GET {url} params={params} extra_headers={extra_headers}")
                
                resp = self.session.get(
                    url, 
                    params=params, 
                    headers=extra_headers,
                    timeout=45,  # 더 긴 타임아웃
                    allow_redirects=True,
                    verify=True  # SSL 검증 활성화
                )
                
                self._fix_encoding(resp)
                self._dbg(f"GET status={resp.status_code} encoding={resp.encoding} len={len(resp.text)}")
                
                # 응답 상태 체크
                if resp.status_code == 200:
                    # 매우 관대한 조건으로 변경
                    if len(resp.text) > 50:  # 최소 50자만 있으면 통과
                        return resp
                    else:
                        self._dbg(f"Response too short: {len(resp.text)} chars")
                elif resp.status_code in [301, 302, 303, 307, 308]:
                    self._dbg(f"Redirect detected: {resp.status_code}")
                    return resp  # 리다이렉트도 허용
                else:
                    self._dbg(f"HTTP Error: {resp.status_code}")
                    self._dbg(f"Response Headers: {dict(resp.headers)}")
                    self._dbg(f"Response Text (first 300 chars): {resp.text[:300]}")
                    
            except requests.exceptions.Timeout:
                self._dbg(f"TIMEOUT on attempt {attempt+1}/{retries}")
                last_exc = RuntimeError(f"Timeout after {45}s")
            except requests.exceptions.ConnectionError as e:
                self._dbg(f"CONNECTION ERROR on attempt {attempt+1}/{retries}: {e}")
                last_exc = e
            except requests.RequestException as e:
                self._dbg(f"REQUEST ERROR on attempt {attempt+1}/{retries}: {e}")
                last_exc = e
                
        self._dbg(f"All {retries} attempts failed")
        raise last_exc if last_exc else RuntimeError("요청 실패")

    def _post_list(self, keyword: str, order: str, page: int = 1, lpp: int = 30, use_computer_parts_filter: bool = True) -> Optional[BeautifulSoup]:
        """list.php로 직접 POST하여 goods-row HTML 조각을 받는다."""
        try:
            self._update_headers()
            self._wait_between_requests()
            referer = f"https://www.guidecom.co.kr/search/?keyword={quote_plus(keyword)}&order={order}"
            headers = {"Referer": referer}
            data = {"keyword": keyword, "order": order, "lpp": lpp, "page": page, "y": 0}
            
            # 컴퓨터주요부품 카테고리 필터 적용
            if use_computer_parts_filter:
                # 키워드에 따라 관련성 높은 카테고리부터 시도
                keyword_lower = keyword.lower()
                
                # 카테고리 우선순위 매핑 (완벽한 키워드 매핑)
                
                # CPU 관련 키워드
                cpu_keywords = [
                    "cpu", "프로세서", "processor", "intel", "amd", "라이젠", "ryzen", "인텔", 
                    "셀러론", "celeron", "펜티엄", "pentium", "코어", "core", "i3", "i5", "i7", "i9",
                    "xeon", "제온", "athlon", "애슬론", "fx", "threadripper", "쓰레드리퍼",
                    # AMD 라이젠 최신 (9000, 8000, 7000, 5000 시리즈)
                    "9950x", "9900x", "9700x", "9600x", "8700g", "8600g", "8500g", "8300g",
                    "7950x3d", "7900x3d", "7800x3d", "7950x", "7900x", "7700x", "7600x", 
                    "5950x", "5900x", "5800x3d", "5800x", "5700x", "5600x",
                    # 인텔 최신 (15세대, 14세대, 13세대, 12세대)
                    "15900k", "15700k", "15600k", "15400", "285k", "265k", "245k", # 15세대 Ultra
                    "14900k", "14700k", "14600k", "14400", "14100", # 14세대
                    "13900k", "13700k", "13600k", "13500", "13400", "13100", # 13세대
                    "12900k", "12700k", "12600k", "12400", "12100", # 12세대
                    "ultra", "울트라" # 인텔 Ultra 시리즈
                ]
                
                # 메인보드 관련 키워드
                motherboard_keywords = [
                    "메인보드", "마더보드", "motherboard", "mainboard", "보드", "board", 
                    # AMD 최신 소켓 (AM5, AM4)
                    "x870", "x870e", "b850", "b840", "a820", # AM5 최신 칩셋
                    "x670", "x670e", "b650", "b650e", "a620", # AM5 이전 칩셋
                    "x570", "b550", "b450", "a520", # AM4 칩셋
                    # 인텔 최신 소켓 (LGA1700, LGA1200)
                    "z890", "h870", "b860", # LGA1851 (15세대 예상)
                    "z790", "z690", "h770", "h670", "b760", "b660", "h610", # LGA1700 (12-14세대)
                    "z590", "z490", "h570", "h470", "b560", "b460", "h410", # LGA1200 (10-11세대)
                    # 소켓 정보
                    "lga1851", "lga1700", "lga1200", "am5", "am4", "socket"
                ]
                
                # 메모리 관련 키워드
                memory_keywords = [
                    "메모리", "ram", "ddr", "ddr4", "ddr5", "ddr6", "dimm", "sodimm", "삼성램", "하이닉스",
                    "corsair", "gskill", "crucial", "kingston", "팀그룹", "teamgroup", "g.skill",
                    # DDR5 최신 속도 (고속)
                    "8000", "7800", "7600", "7200", "7000", "6800", "6400", "6200", "6000", "5600", "5200", "4800",
                    # DDR4 속도
                    "4000", "3800", "3600", "3466", "3200", "3000", "2933", "2666", "2400",
                    # 레이턴시
                    "cl36", "cl34", "cl32", "cl30", "cl28", "cl26", "cl24", "cl22", "cl20", "cl18", "cl16", "cl14",
                    # 브랜드 시리즈
                    "vengeance", "trident", "ripjaws", "ballistix", "fury", "dominator", "neo", "royal"
                ]
                
                # 그래픽카드 관련 키워드
                gpu_keywords = [
                    "그래픽", "그래픽카드", "gpu", "vga", "비디오카드", "video card", "graphics card",
                    "rtx", "gtx", "radeon", "rx", "nvidia", "엔비디아", "amd", "geforce", "지포스",
                    # NVIDIA RTX 최신 (50시리즈, 40시리즈, 30시리즈)
                    "5090", "5080", "5070", "5060", "rtx5090", "rtx5080", "rtx5070", "rtx5060", # 50시리즈 최신
                    "4090", "4080", "4070", "4060", "rtx4090", "rtx4080", "rtx4070", "rtx4060", # 40시리즈
                    "4070ti", "4060ti", "rtx4070ti", "rtx4060ti", "rtx4070super", "rtx4080super",
                    "3090", "3080", "3070", "3060", "rtx3090", "rtx3080", "rtx3070", "rtx3060", # 30시리즈
                    "3090ti", "3080ti", "3070ti", "3060ti", "rtx3090ti", "rtx3080ti", "rtx3070ti", "rtx3060ti",
                    # AMD Radeon 최신 (8000, 7000, 6000 시리즈)
                    "8800xt", "8700xt", "8600xt", "rx8800", "rx8700", "rx8600", # 8000시리즈 (예상)
                    "7900xt", "7900xtx", "7800xt", "7700xt", "7600xt", "7600", # 7000시리즈
                    "rx7900", "rx7800", "rx7700", "rx7600", "rx7900xt", "rx7900xtx", "rx7800xt", "rx7700xt",
                    "6950xt", "6900xt", "6800xt", "6700xt", "6600xt", "6600", "6500xt", "6400", # 6000시리즈
                    "rx6950", "rx6900", "rx6800", "rx6700", "rx6600", "rx6500", "rx6400",
                    # 기타
                    "gtx1660", "gtx1650", "arc", "인텔arc", "아크", "a770", "a750", "a580", "titan"
                ]
                
                # HDD 관련 키워드  
                hdd_keywords = [
                    "hdd", "하드디스크", "하드", "hard disk", "hard drive", "wd", "western digital",
                    "seagate", "시게이트", "toshiba", "도시바", "hitachi", "히타치", "barracuda", 
                    "blue", "black", "red", "purple", "gold", "ironwolf", "skyhawk"
                ]
                
                # SSD 관련 키워드
                ssd_keywords = [
                    "ssd", "solid state", "nvme", "m.2", "sata ssd", "2.5인치", 
                    "crucial", "mx", "bx", "samsung", "삼성", "kingston", "adata", "transcend",
                    # 삼성 최신 라인업
                    "990pro", "990evo", "980pro", "980", "970evo", "980evo", 
                    # WD 최신 라인업
                    "sn850x", "sn770", "sn580", "sn570", "black", "blue", "green",
                    # 크루셜 최신
                    "t700", "t500", "p5", "p3", "mx500", "bx500",
                    # 기타 브랜드 최신
                    "mp600", "mp510", "mp700", "fury", "kc3000", "kc2500",
                    # 규격 및 성능
                    "pcie", "gen3", "gen4", "gen5", "tlc", "qlc", "mlc", "slc", "dram", "dramless",
                    "7000mb", "5000mb", "3500mb" # 읽기 속도
                ]
                
                # 파워 관련 키워드
                power_keywords = [
                    "파워", "power", "psu", "파워서플라이", "power supply", "전원공급장치", "정격",
                    # 인증 등급
                    "80plus", "bronze", "silver", "gold", "platinum", "titanium", "cybenetics",
                    # 모듈러 타입
                    "모듈러", "modular", "풀모듈러", "세미모듈러", "논모듈러",
                    # 최신 규격
                    "atx3.0", "atx3.1", "pcie5.0", "12vhpwr", "16pin", "12+4pin",
                    # 용량별
                    "550w", "650w", "750w", "850w", "1000w", "1200w", "1600w",
                    # 브랜드
                    "seasonic", "시소닉", "corsair", "antec", "안텍", "fsp", "쿨러마스터", "silverstone",
                    "evga", "thermaltake", "be quiet", "fractal", "msi", "asus", "gigabyte"
                ]
                
                # 케이스 관련 키워드
                case_keywords = [
                    "케이스", "case", "컴퓨터케이스", "pc케이스", "타워", "tower", "미들타워", "풀타워",
                    "미니itx", "mini-itx", "micro-atx", "atx", "e-atx", "큐브", "슬림",
                    "fractal", "nzxt", "corsair", "쿨러마스터", "써마테이크", "thermaltake",
                    "define", "meshify", "h510", "4000d", "5000d", "view", "rgb", "tempered glass"
                ]
                
                # CPU 쿨러 관련 키워드
                cpu_cooler_keywords = [
                    "cpu쿨러", "cpu 쿨러", "cpucooler", "프로세서쿨러", "공랭쿨러", "공냉쿨러", 
                    "타워쿨러", "tower cooler", "top flow", "탑플로우", "사이드플로우", "side flow",
                    "noctua", "녹투아", "be quiet", "비콰이어트", "zalman", "잘만", "deepcool", "딥쿨"
                ]
                
                # 수랭쿨러 관련 키워드  
                liquid_cooler_keywords = [
                    "수랭쿨러", "수냉쿨러", "수랭", "수냉", "liquid cooler", "aio", "올인원", "라디에이터",
                    "240mm", "280mm", "360mm", "corsair", "nzxt", "써마테이크", "쿨러마스터",
                    "arctic", "아틱", "msi", "asus"
                ]
                
                # 모니터 관련 키워드
                monitor_keywords = [
                    "모니터", "monitor", "디스플레이", "display", "lcd", "led", "oled", "qled",
                    "24인치", "27인치", "32인치", "144hz", "165hz", "240hz", "360hz",
                    "4k", "2k", "1440p", "1080p", "울트라와이드", "ultrawide", "커브드",
                    "gaming", "게이밍", "ips", "va", "tn"
                ]
                
                # 키보드 관련 키워드
                keyboard_keywords = [
                    "키보드", "keyboard", "기계식", "mechanical", "멤브레인", "membrane",
                    "텐키리스", "tkl", "60%", "65%", "75%", "풀배열", "무선", "wireless",
                    "rgb", "백라이트", "청축", "갈축", "적축", "저소음", "게이밍"
                ]
                
                # 마우스 관련 키워드
                mouse_keywords = [
                    "마우스", "mouse", "게이밍마우스", "gaming mouse", "무선마우스", "wireless mouse",
                    "광마우스", "optical", "레이저", "laser", "dpi", "rgb", "매크로",
                    "로지텍", "logitech", "레이저", "razer", "스틸시리즈", "steelseries"
                ]
                
                # 키워드 우선순위 매칭
                if any(k in keyword_lower for k in cpu_keywords):
                    priority_categories = ["8800"]  # CPU
                elif any(k in keyword_lower for k in motherboard_keywords):
                    priority_categories = ["8801"]  # 메인보드
                elif any(k in keyword_lower for k in memory_keywords):
                    priority_categories = ["8802"]  # 메모리
                elif any(k in keyword_lower for k in gpu_keywords):
                    priority_categories = ["8803"]  # 그래픽카드
                elif any(k in keyword_lower for k in hdd_keywords):
                    priority_categories = ["8804"]  # HDD
                elif any(k in keyword_lower for k in ssd_keywords):
                    priority_categories = ["8855"]  # SSD
                elif any(k in keyword_lower for k in power_keywords):
                    priority_categories = ["8806"]  # 파워서플라이
                elif any(k in keyword_lower for k in case_keywords):
                    priority_categories = ["8807"]  # 케이스
                elif any(k in keyword_lower for k in cpu_cooler_keywords):
                    priority_categories = ["8805"]  # CPU쿨러
                elif any(k in keyword_lower for k in liquid_cooler_keywords):
                    priority_categories = ["8805"]  # CPU쿨러 (수랭도 동일 카테고리)
                elif any(k in keyword_lower for k in monitor_keywords):
                    priority_categories = ["8808"]  # 모니터
                elif any(k in keyword_lower for k in keyboard_keywords):
                    priority_categories = ["8809"]  # 키보드
                elif any(k in keyword_lower for k in mouse_keywords):
                    priority_categories = ["8810"]  # 마우스
                elif "디스크" in keyword_lower and not any(k in keyword_lower for k in hdd_keywords):
                    # "디스크"만 있고 HDD 관련 키워드가 없는 경우
                    priority_categories = ["8855", "8804"]  # SSD 먼저, 그다음 HDD
                else:
                    # 일반 검색: 주요 컴퓨터 부품 카테고리들 (사용 빈도 순)
                    priority_categories = ["8803", "8800", "8855", "8802", "8801", "8804", "8806", "8807", "8805", "8808", "8809", "8810"]
                
                self._dbg(f"Priority categories for '{keyword}': {priority_categories}")
                
                # 우선순위 카테고리부터 검색
                for cid in priority_categories:
                    try:
                        data_with_cid = data.copy()
                        data_with_cid["cid"] = cid
                        self._dbg(f"POST {self.list_url} with cid={cid}")
                        resp = self.session.post(self.list_url, data=data_with_cid, headers=headers, timeout=30)
                        self._fix_encoding(resp)
                        
                        if resp.status_code == 200 and len(resp.text) > 100:
                            soup = BeautifulSoup(resp.text, "lxml")
                            rows = soup.find_all("div", class_="goods-row")
                            self._dbg(f"Category {cid}: found {len(rows)} products")
                            
                            if len(rows) > 0:
                                # 검색 결과 품질 검증
                                if self._is_relevant_results(rows, keyword_lower):
                                    self._dbg(f"Using category {cid} with {len(rows)} relevant products")
                                    return soup
                                else:
                                    self._dbg(f"Category {cid} results not relevant, trying next category")
                                    continue
                                
                        # 카테고리별 요청 간격
                        self._wait_between_requests(0.1)
                        
                    except Exception as e:
                        self._dbg(f"Category {cid} failed: {e}")
                        continue
                
                self._dbg("No results found in priority categories, trying fallback")
            
            # 컴퓨터 부품 필터가 결과를 못 찾거나 비활성화된 경우 기본 검색
            self._dbg(f"POST {self.list_url} data={data} referer={referer}")
            resp = self.session.post(self.list_url, data=data, headers=headers, timeout=30)
            self._fix_encoding(resp)
            self._dbg(f"POST status={resp.status_code} encoding={resp.encoding} len={len(resp.text)}")
            if resp.status_code == 200 and len(resp.text) > 100:
                soup = BeautifulSoup(resp.text, "lxml")
                rows = soup.find_all("div", class_="goods-row")
                self._dbg(f"POST parsed goods-row={len(rows)}")
                
                # 디버그: 첫 번째 상품의 HTML 구조 확인
                if self.debug and rows:
                    self._dbg(f"=== FIRST PRODUCT HTML ===")
                    self._dbg(f"First row HTML: {str(rows[0])[:1000]}")
                    
                return soup
        except requests.RequestException as e:
            self._dbg(f"POST exception: {e}")
            return None
        return None
    
    def _is_relevant_results(self, rows, keyword_lower: str) -> bool:
        """검색 결과가 키워드와 관련성이 높은지 검증"""
        if not rows:
            return False
            
        relevant_count = 0
        total_checked = min(len(rows), 5)  # 상위 5개 제품만 검사
        
        for row in rows[:total_checked]:
            try:
                # 제품명 추출
                name_el = row.select_one(".desc .goodsname1") or row.select_one(".desc h4.title a") or row.select_one("h4.title a")
                product_name = self._extract_text(name_el).lower()
                
                # 스펙 정보 추출
                spec_el = row.select_one(".desc .feature")
                specs = self._extract_text(spec_el).lower() if spec_el else ""
                
                full_text = f"{product_name} {specs}"
                self._dbg(f"Checking relevance: '{product_name[:50]}...'")
                
                # 카테고리별 상세 관련성 검증
                
                # CPU 관련성 체크
                if any(k in keyword_lower for k in ["cpu", "프로세서", "intel", "amd", "라이젠", "ryzen", "ultra", "울트라"]):
                    cpu_check_keywords = [
                        "cpu", "프로세서", "processor", "intel", "amd", "ryzen", "라이젠", "코어", "core", 
                        "i3", "i5", "i7", "i9", "celeron", "pentium", "xeon", "athlon", "ultra", "울트라",
                        # 최신 모델명
                        "9950x", "9900x", "7800x3d", "7950x", "15900k", "14900k", "13900k", "285k", "265k"
                    ]
                    exclude_keywords = ["쿨러", "cooler", "케이스", "보드"]
                    
                    has_cpu_keyword = any(keyword in full_text for keyword in cpu_check_keywords)
                    has_exclude_keyword = any(keyword in full_text for keyword in exclude_keywords)
                    
                    if has_cpu_keyword and not has_exclude_keyword:
                        relevant_count += 1
                
                # 메인보드 관련성 체크
                elif any(k in keyword_lower for k in ["메인보드", "마더보드", "motherboard", "보드"]):
                    mb_check_keywords = ["메인보드", "마더보드", "motherboard", "mainboard", "보드", "b450", "b550", "x570", "z490", "z590", "lga", "am4", "am5"]
                    if any(keyword in full_text for keyword in mb_check_keywords):
                        relevant_count += 1
                
                # 메모리 관련성 체크
                elif any(k in keyword_lower for k in ["메모리", "ram", "ddr"]):
                    memory_check_keywords = ["메모리", "ram", "ddr", "ddr4", "ddr5", "dimm", "gb", "삼성", "하이닉스", "corsair", "gskill", "crucial"]
                    exclude_keywords = ["ssd", "hdd", "그래픽"]
                    
                    has_memory_keyword = any(keyword in full_text for keyword in memory_check_keywords)
                    has_exclude_keyword = any(keyword in full_text for keyword in exclude_keywords)
                    
                    if has_memory_keyword and not has_exclude_keyword:
                        relevant_count += 1
                
                # 그래픽카드 관련성 체크
                elif any(k in keyword_lower for k in ["그래픽", "gpu", "rtx", "gtx", "vga", "5090", "5080", "5070", "5060"]):
                    gpu_check_keywords = [
                        "그래픽", "gpu", "rtx", "gtx", "radeon", "rx", "nvidia", "amd", "geforce", "지포스", "vga", "비디오카드",
                        # 최신 모델명
                        "5090", "5080", "5070", "5060", "4090", "4080", "4070", "7900xt", "7800xt", "arc"
                    ]
                    if any(keyword in full_text for keyword in gpu_check_keywords):
                        relevant_count += 1
                
                # HDD 관련성 체크
                elif any(k in keyword_lower for k in ["hdd", "하드디스크", "하드"]):
                    hdd_check_keywords = ["hdd", "하드디스크", "하드", "hard disk", "wd", "western digital", "seagate", "toshiba", "barracuda", "blue", "red", "tb", "gb"]
                    exclude_keywords = ["케이스", "컨버터", "외장", "usb", "어댑터", "독", "dock", "ssd"]
                    
                    has_hdd_keyword = any(keyword in full_text for keyword in hdd_check_keywords)
                    has_exclude_keyword = any(keyword in full_text for keyword in exclude_keywords)
                    
                    if has_hdd_keyword and not has_exclude_keyword:
                        relevant_count += 1
                    elif has_hdd_keyword and has_exclude_keyword:
                        # 주변기기 키워드가 있어도 실제 HDD 용량이 명시되어 있으면 관련성 있음
                        if any(cap in full_text for cap in ["1tb", "2tb", "4tb", "8tb", "12tb", "16tb"]):
                            relevant_count += 1
                
                # SSD 관련성 체크
                elif any(k in keyword_lower for k in ["ssd", "nvme", "m.2"]):
                    ssd_check_keywords = ["ssd", "solid state", "nvme", "m.2", "sata ssd", "980", "970", "crucial", "mx", "bx", "samsung", "tb", "gb"]
                    exclude_keywords = ["hdd", "케이스"]
                    
                    has_ssd_keyword = any(keyword in full_text for keyword in ssd_check_keywords)
                    has_exclude_keyword = any(keyword in full_text for keyword in exclude_keywords)
                    
                    if has_ssd_keyword and not has_exclude_keyword:
                        relevant_count += 1
                
                # 파워서플라이 관련성 체크
                elif any(k in keyword_lower for k in ["파워", "power", "psu"]):
                    power_check_keywords = ["파워", "power", "psu", "파워서플라이", "전원공급", "80plus", "정격", "w", "watt", "모듈러", "seasonic", "corsair"]
                    exclude_keywords = ["그래픽", "케이스"]
                    
                    has_power_keyword = any(keyword in full_text for keyword in power_check_keywords)
                    has_exclude_keyword = any(keyword in full_text for keyword in exclude_keywords)
                    
                    if has_power_keyword and not has_exclude_keyword:
                        relevant_count += 1
                
                # 케이스 관련성 체크
                elif any(k in keyword_lower for k in ["케이스", "case"]):
                    case_check_keywords = ["케이스", "case", "컴퓨터케이스", "pc케이스", "타워", "tower", "atx", "mini-itx", "micro-atx"]
                    if any(keyword in full_text for keyword in case_check_keywords):
                        relevant_count += 1
                
                # 쿨러 관련성 체크
                elif any(k in keyword_lower for k in ["쿨러", "cooler", "수랭", "수냉"]):
                    cooler_check_keywords = ["쿨러", "cooler", "cpu쿨러", "수랭", "수냉", "공랭", "공냉", "라디에이터", "240mm", "280mm", "360mm", "noctua", "be quiet"]
                    if any(keyword in full_text for keyword in cooler_check_keywords):
                        relevant_count += 1
                        
                # 모니터 관련성 체크
                elif any(k in keyword_lower for k in ["모니터", "monitor", "디스플레이"]):
                    monitor_check_keywords = ["모니터", "monitor", "디스플레이", "display", "인치", "hz", "144hz", "4k", "1440p", "게이밍", "ips", "va"]
                    if any(keyword in full_text for keyword in monitor_check_keywords):
                        relevant_count += 1
                        
                # 키보드 관련성 체크
                elif any(k in keyword_lower for k in ["키보드", "keyboard"]):
                    keyboard_check_keywords = ["키보드", "keyboard", "기계식", "mechanical", "텐키리스", "무선", "rgb", "청축", "갈축", "적축"]
                    if any(keyword in full_text for keyword in keyboard_check_keywords):
                        relevant_count += 1
                        
                # 마우스 관련성 체크
                elif any(k in keyword_lower for k in ["마우스", "mouse"]):
                    mouse_check_keywords = ["마우스", "mouse", "게이밍", "gaming", "무선", "wireless", "dpi", "rgb", "로지텍", "razer"]
                    if any(keyword in full_text for keyword in mouse_check_keywords):
                        relevant_count += 1
                
                # 기타 일반적인 관련성 체크
                else:
                    # 키워드가 제품명이나 스펙에 포함되어 있으면 관련성 있음
                    search_terms = keyword_lower.split()
                    if any(term in full_text for term in search_terms if len(term) > 2):
                        relevant_count += 1
                        
            except Exception as e:
                self._dbg(f"Error checking relevance: {e}")
                continue
        
        relevance_ratio = relevant_count / total_checked if total_checked > 0 else 0
        self._dbg(f"Relevance check: {relevant_count}/{total_checked} = {relevance_ratio:.2f}")
        
        # 50% 이상이 관련성 있으면 적절한 결과로 판단
        return relevance_ratio >= 0.5
    
    def _try_alternative_methods(self, keyword: str, order: str) -> Optional[BeautifulSoup]:
        """다양한 방법으로 상품 데이터 가져오기 시도"""
        methods = [
            ("POST list.php with computer parts filter", lambda: self._post_list(keyword, order, use_computer_parts_filter=True)),
            ("POST list.php", lambda: self._post_list(keyword, order, use_computer_parts_filter=False)),
            ("GET with params", lambda: self._get_with_params(keyword, order)),
            ("Alternative URLs", lambda: self._try_alternative_urls(keyword, order))
        ]
        
        for method_name, method_func in methods:
            self._dbg(f"Trying method: {method_name}")
            try:
                result = method_func()
                if result and result.find_all("div", class_="goods-row"):
                    self._dbg(f"Success with method: {method_name}")
                    return result
            except Exception as e:
                self._dbg(f"Method {method_name} failed: {e}")
                
        return None
    
    def _get_with_params(self, keyword: str, order: str) -> Optional[BeautifulSoup]:
        """GET 요청으로 직접 가져오기"""
        try:
            params = {"keyword": keyword, "order": order}
            resp = self._make_request(self.base_url, params=params)
            soup = BeautifulSoup(resp.text, "lxml")
            return soup
        except Exception as e:
            self._dbg(f"GET with params failed: {e}")
            return None
    
    def _try_alternative_urls(self, keyword: str, order: str) -> Optional[BeautifulSoup]:
        """대체 URL들 시도"""
        for alt_url in self.alternative_urls:
            try:
                self._dbg(f"Trying alternative URL: {alt_url}")
                params = {"keyword": keyword, "order": order, "q": keyword}
                resp = self._make_request(alt_url, params=params)
                soup = BeautifulSoup(resp.text, "lxml")
                rows = soup.find_all("div", class_="goods-row")
                if rows:
                    self._dbg(f"Found {len(rows)} products in {alt_url}")
                    return soup
            except Exception as e:
                self._dbg(f"Alternative URL {alt_url} failed: {e}")
        return None

    # ----------------------- Parsing helpers -----------------------
    def _find_goods_list(self, soup: BeautifulSoup):
        # 1순위: 기본 goods-list
        gl = soup.find(id="goods-list")
        if gl and gl.find_all("div", class_="goods-row"):
            self._dbg("Found products in #goods-list")
            return gl
            
        # 2순위: placeholder 내부
        placeholder = soup.find(id="goods-placeholder")
        if placeholder:
            inner = placeholder.find(id="goods-list")
            if inner and inner.find_all("div", class_="goods-row"):
                self._dbg("Found products in #goods-placeholder > #goods-list")
                return inner
        
        # 3순위: 다양한 컨테이너 ID/클래스 시도
        containers = [
            soup.find(id="product-list"),
            soup.find(id="search-results"),
            soup.find(class_="product-list"),
            soup.find(class_="search-results"),
            soup.find(class_="goods-container"),
            soup.find(class_="product-container")
        ]
        
        for container in containers:
            if container and container.find_all("div", class_="goods-row"):
                self._dbg(f"Found products in alternative container: {container.get('id') or container.get('class')}")
                return container
        
        # 4순위: 전체 soup에서 goods-row가 있는지 확인
        if soup.find_all("div", class_="goods-row"):
            self._dbg("Found goods-row in root soup")
            return soup
        
        # 5순위: 다른 가능한 상품 컨테이너들 시도
        alternative_selectors = [
            "div[class*='product']",
            "div[class*='item']", 
            "div[class*='goods']",
            ".product-item",
            ".search-item",
            ".list-item"
        ]
        
        for selector in alternative_selectors:
            items = soup.select(selector)
            if items:
                self._dbg(f"Found {len(items)} items with selector: {selector}")
                # 가짜 goods-row 구조 생성
                fake_container = soup.new_tag("div")
                for item in items[:20]:  # 최대 20개
                    item['class'] = item.get('class', []) + ['goods-row']
                    fake_container.append(item)
                return fake_container
        
        self._dbg("No product containers found anywhere")
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
            # 디버그: 전체 row HTML 구조 출력
            if self.debug:
                self._dbg(f"=== ROW HTML DEBUG ===")
                self._dbg(f"Row classes: {row.get('class', [])}")
                self._dbg(f"Row HTML (first 500 chars): {str(row)[:500]}")
            
            # 이름: 여러 선택자 시도
            name_selectors = [
                ".desc .goodsname1",
                ".desc h4.title a", 
                "h4.title a",
                ".desc .title a",
                ".title a",
                ".desc a",
                "a"
            ]
            
            name_el = None
            for selector in name_selectors:
                name_el = row.select_one(selector)
                if name_el:
                    self._dbg(f"Found name with selector: {selector}")
                    break
                    
            name = self._extract_text(name_el)
            if not name:
                self._dbg("=== NAME NOT FOUND ===")
                self._dbg(f"Available elements: {[tag.name for tag in row.find_all()]}")
                self._dbg(f"All text in row: {row.get_text(' ', strip=True)}")
                return None
                
            self._dbg(f"Product name: {name}")
            
            # 스펙 추출: 더 광범위한 선택자
            spec_selectors = [
                ".desc .feature",
                ".feature", 
                ".desc .spec",
                ".spec",
                ".desc .description",
                ".description",
                ".desc .summary",
                ".summary",
                ".desc .info",
                ".info",
                ".desc ul",
                ".desc p",
                ".goodsinfo"
            ]
            
            specs = ""
            for selector in spec_selectors:
                spec_el = row.select_one(selector)
                if spec_el:
                    specs = self._extract_text(spec_el)
                    if specs and specs != name:
                        self._dbg(f"Found specs with selector {selector}: {specs[:100]}")
                        break
                        
            if not specs:
                # 마지막 시도: .desc 내 모든 텍스트 추출
                desc_el = row.select_one(".desc")
                if desc_el:
                    # 링크 텍스트 제거하고 나머지 텍스트 가져오기
                    desc_copy = desc_el.__copy__()
                    for a_tag in desc_copy.find_all('a'):
                        a_tag.decompose()
                    specs = self._extract_text(desc_copy).strip()
                    if specs:
                        self._dbg(f"Extracted specs from .desc (no links): {specs[:100]}")
                        
            if not specs:
                self._dbg("=== SPECS NOT FOUND ===")
                desc_el = row.select_one(".desc")
                if desc_el:
                    self._dbg(f"Desc HTML: {str(desc_el)[:300]}")
                else:
                    self._dbg("No .desc element found")
                    
            # 가격 추출: 더 다양한 선택자
            price_selectors = [
                ".prices .price-large span",
                ".price-large span",
                ".price-large",
                ".prices .price span",
                ".price span", 
                ".price",
                ".cost",
                "[class*='price']"
            ]
            
            price = ""
            for selector in price_selectors:
                price_el = row.select_one(selector)
                if price_el:
                    price = self._parse_price(self._extract_text(price_el))
                    if price:
                        self._dbg(f"Found price with selector {selector}: {price}")
                        break
                        
            if not price:
                self._dbg("=== PRICE NOT FOUND ===")
                self._dbg(f"Available elements with 'price' in class: {[str(el)[:100] for el in row.find_all(class_=lambda x: x and 'price' in str(x).lower())]}")
                
            return Product(name=name, price=price or "가격 정보 없음", specifications=specs or "사양 정보 없음")
        except Exception as e:
            self._dbg(f"_parse_product_item exception: {e}")
            import traceback
            self._dbg(f"Traceback: {traceback.format_exc()}")
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
        if not product_name:
            return None
        
        self._dbg(f"Extracting manufacturer from: '{product_name}'")
        
        # 대괄호 제거 및 정리
        text = re.sub(r"\[[^\]]+\]", " ", product_name)
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()
        
        if not words:
            self._dbg("No words found after cleaning")
            return None
            
        self._dbg(f"Words after cleaning: {words}")
        
        # 건너뛸 단어들 - 더 포괄적으로 확장
        skip = {
            "신제품", "신상품", "공식인증", "병행수입", "벌크", "정품", "스페셜", "한정판",
            "8월", "7월", "6월", "9월", "10월", "11월", "12월", "1월", "2월", "3월", "4월", "5월",
            "새상품", "리퍼", "중고", "전시", "개봉", "박스", "오픈박스", "리퍼비시",
            "할인", "특가", "세일", "이벤트", "프로모션", "한정", "무료배송", "당일발송"
        }
        
        i = 0
        while i < len(words):
            word = words[i]
            self._dbg(f"Checking word '{word}' (index {i})")
            
            # 정확한 매치 또는 부분 매치 확인
            should_skip = False
            for skip_word in skip:
                if word == skip_word or skip_word in word or word in skip_word:
                    should_skip = True
                    self._dbg(f"Skipping word '{word}' (matched with '{skip_word}')")
                    break
                    
            if not should_skip:
                break
            i += 1
            
        if i >= len(words):
            self._dbg("All words were skipped, no manufacturer found")
            return None
            
        manufacturer = words[i]
        self._dbg(f"Found manufacturer candidate: '{manufacturer}'")
        
        # 2단어 브랜드 결합(Western Digital, TP LINK 등)
        if i + 1 < len(words):
            pair = f"{manufacturer} {words[i+1]}"
            normalized_pair = self._normalize_brand(pair)
            if normalized_pair in {"western digital", "tp link", "g skill", "team group"}:
                manufacturer = pair
                self._dbg(f"Combined into 2-word brand: '{manufacturer}'")
                
        self._dbg(f"Final manufacturer: '{manufacturer}'")
        return manufacturer

    def _extract_manufacturer_from_row(self, row) -> Optional[str]:
        name_el = row.select_one(".desc .goodsname1")
        if not name_el:
            name_el = row.select_one(".desc h4.title a") or row.select_one("h4.title a")
        name = self._extract_text(name_el)
        maker = self._extract_manufacturer(name)
        if self.debug:
            self._dbg(f"NAME='{name[:80]}' -> MFR='{maker}'")
        return maker

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
            if man_norm == canonical and any(a == sel for sel in sel_norms for a in aliases):
                return True
            if man_norm in aliases and any(sel == canonical for sel in sel_norms):
                return True
        return False

    # ----------------------- Public API -----------------------
    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        """
        제조사 후보를 최대 8개까지 반환.
        1) list.php POST 결과에서 우선 추출
        2) 실패 시 검색 페이지(GET)에서 보조 추출
        디버깅 출력:
          - goods-row 개수
          - 샘플 제품명들, 제품명->제조사 매핑 몇 개
        """
        manufacturers: List[str] = []
        seen = set()
        try:
            # 1) 다양한 방법으로 상품 데이터 가져오기 시도
            soup = self._try_alternative_methods(keyword, "reco_goods")
            
            if not soup:
                self._dbg("All methods failed, trying fallback approaches")
                # 마지막 시도: 단순 GET 요청
                try:
                    params = {"keyword": keyword}
                    resp = self._make_request(self.base_url, params=params)
                    soup = BeautifulSoup(resp.text, "lxml")
                except Exception as e:
                    self._dbg(f"Fallback GET failed: {e}")
                    return []
                    
            container = self._find_goods_list(soup) if soup else None
            rows = container.find_all("div", class_="goods-row") if container else []

            self._dbg(f"get_search_options: goods-row count={len(rows)}")
            
            # 디버그: HTML 구조 확인
            if self.debug and soup:
                self._dbg(f"=== SOUP CONTENT SAMPLE ===")
                body_text = soup.get_text()[:1000] if soup.body else "No body found"
                self._dbg(f"Body text sample: {body_text}")
                
            sample_names: List[str] = []

            for idx, row in enumerate(rows[:80]):
                name_el = row.select_one(".desc .goodsname1") or row.select_one(".desc h4.title a") or row.select_one("h4.title a")
                nm = self._extract_text(name_el)
                if self.debug and idx < 10:
                    sample_names.append(nm)
                maker = self._extract_manufacturer(nm)
                if maker and maker not in seen:
                    manufacturers.append(maker)
                    seen.add(maker)
                if len(manufacturers) >= 8:
                    break

            if self.debug:
                self._dbg("sample names: " + " | ".join(sample_names))
                self._dbg("manufacturers: " + ", ".join(manufacturers))

            def sort_key(x: str):
                xn = self._normalize_brand(x)
                return (0 if re.search(r"[가-힣]", x) else 1, xn)

            return [{"name": m, "code": self._normalize_brand(m).replace(" ", "_")} for m in sorted(manufacturers, key=sort_key)]
        except Exception as e:
            self._dbg(f"get_search_options exception: {e}")
            return []

    def _resolve_order_param(self, sort_type: str) -> str:
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
        """단일 정렬 기준으로 제품 최대 `limit`개 반환 (list.php 우선)."""
        try:
            order = self._resolve_order_param(sort_type)
            # 1) 다양한 방법으로 시도
            soup = self._try_alternative_methods(keyword, order)
            
            if soup:
                container = self._find_goods_list(soup)
                rows = container.find_all("div", class_="goods-row") if container else []
            else:
                rows = []
                
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
            candidates = self.search_products(keyword, order, maker_codes, limit=50)
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
        
        # 결과가 없을 경우 더 유용한 안내 메시지 반환
        if not results:
            self._dbg("No products found, returning helpful guidance")
            return [
                Product(
                    name="🔍 검색 결과가 없습니다",
                    price="안내", 
                    specifications="다른 검색어로 시도해보세요. 예: SSD, 그래픽카드, 메모리, 메인보드 등"
                ),
                Product(
                    name="🌐 서버 연결 문제일 수 있습니다",
                    price="해결방법", 
                    specifications="1) 잠시 후 다시 시도 2) 검색어를 단순하게 입력 3) 브랜드명 대신 제품 종류로 검색"
                ),
                Product(
                    name="📝 검색 팁",
                    price="도움말", 
                    specifications="• '삼성 SSD' 대신 'SSD'로 검색 • 영문보다는 한글 검색어 권장 • 너무 구체적인 모델명보다는 일반적인 제품군으로 검색"
                )
            ]
            
        return results[:10]
