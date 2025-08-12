import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Optional
import re

@dataclass
class Product:
    name: str
    price: str
    specifications: str

class GuidecomParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        # 모바일 버전 URL 사용
        self.base_url = "https://m.guidecom.co.kr/shop/"

    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        """
        가이드컴에서 실제 제품을 검색하여 제조사 정보를 추출합니다.
        dibugguid.txt와 goods.txt 구조에 최적화
        """
        try:
            # 모바일 버전: https://m.guidecom.co.kr/shop/?mode=search&keyword=검색어
            params = {
                'mode': 'search',
                'keyword': keyword
            }
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            manufacturers = set()
            
            # goods.txt 구조 분석:
            # <div id="goods-placeholder">
            #   <div id="goods-list">
            #     <div class="goods-row">
            #       <div class="desc">
            #         <h4 class="title">
            #           <span class="goodsname1">제품명</span>
            
            # 1단계: goods-list 찾기
            goods_list = self._find_goods_list(soup)
            if not goods_list:
                return []
            
            # 2단계: goods-row들에서 제품명 추출
            goods_rows = goods_list.find_all('div', class_='goods-row')
            if not goods_rows:
                return []
            
            # 3단계: 각 제품에서 제조사 추출 (최대 20개 제품 확인)
            for row in goods_rows[:20]:
                manufacturer = self._extract_manufacturer_from_row(row)
                if manufacturer:
                    manufacturers.add(manufacturer)
                    # 최대 8개 제조사로 제한
                    if len(manufacturers) >= 8:
                        break
            
            # 4단계: 제조사 목록을 정렬하여 반환
            return self._format_manufacturer_list(manufacturers)
            
        except Exception as e:
            print(f"검색 옵션 가져오기 오류: {e}")
            return []
    
    def _find_goods_list(self, soup):
        """모바일 버전에서 제품 리스트를 찾습니다"""
        print(f"DEBUG: HTML 구조 분석 중...")
        
        # 1. 기존 데스크톱 구조 시도
        goods_list = soup.find('div', id='goods-list')
        if goods_list:
            print(f"DEBUG: 데스크톱 구조 goods-list 찾음")
            return goods_list
        
        # 2. goods-placeholder 내부에서 찾기
        goods_placeholder = soup.find('div', id='goods-placeholder')
        if goods_placeholder:
            goods_list = goods_placeholder.find('div', id='goods-list')
            if goods_list:
                print(f"DEBUG: goods-placeholder 내 goods-list 찾음")
                return goods_list
        
        # 3. 모바일 버전 가능한 구조들 찾기
        possible_containers = [
            soup.find('div', class_='goods-list'),
            soup.find('ul', class_='goods-list'),
            soup.find('div', class_='product-list'),
            soup.find('ul', class_='product-list'),
            soup.find('div', class_='item-list'),
            soup.find('div', class_='search-result'),
            soup.find('div', class_='list-wrap'),
            soup.find('section', class_='goods')
        ]
        
        for container in possible_containers:
            if container:
                print(f"DEBUG: 모바일 구조 찾음: {container.name}.{container.get('class')}")
                return container
        
        # 4. 모든 div들 중 제품이 있을 만한 것들 찾기
        all_divs = soup.find_all('div')
        print(f"DEBUG: 총 div 개수: {len(all_divs)}")
        
        for div in all_divs:
            if div.get('class'):
                class_name = ' '.join(div.get('class'))
                if any(keyword in class_name.lower() for keyword in ['goods', 'product', 'item', 'list']):
                    print(f"DEBUG: 가능한 컨테이너: div.{class_name}")
        
        return None
    
    def _extract_manufacturer_from_row(self, row):
        """goods-row에서 제조사를 추출합니다"""
        try:
            # goods.txt 구조: div.desc > h4.title > span.goodsname1
            desc_div = row.find('div', class_='desc')
            if not desc_div:
                return None
            
            title_h4 = desc_div.find('h4', class_='title')
            if not title_h4:
                return None
            
            goodsname_span = title_h4.find('span', class_='goodsname1')
            if not goodsname_span:
                return None
            
            # 제품명에서 제조사 추출
            product_name = goodsname_span.get_text(strip=True)
            return self._extract_manufacturer(product_name)
            
        except Exception:
            return None
    
    
    def _format_manufacturer_list(self, manufacturers: set) -> List[Dict[str, str]]:
        """제조사 set을 정렬된 리스트로 변환합니다"""
        manufacturer_list = []
        for manufacturer in sorted(manufacturers):
            manufacturer_list.append({
                'name': manufacturer,
                'code': manufacturer.lower().replace(' ', '_').replace('.', '')
            })
        return manufacturer_list
    
    def _extract_manufacturer(self, product_name: str) -> Optional[str]:
        """
        제품명에서 제조사를 추출합니다.
        '공식인증', '병행수입'이 첫 단어면 다음 단어를 제조사로 사용
        """
        if not product_name:
            return None
            
        words = product_name.strip().split()
        if not words:
            return None
        
        print(f"DEBUG 제조사추출: 제품명='{product_name}', 분할된단어={words[:3]}")
        
        # 첫 단어가 '공식인증' 또는 '병행수입'인 경우
        if words[0] in ['공식인증', '병행수입'] and len(words) > 1:
            manufacturer = words[1]
            print(f"DEBUG: 공식인증/병행수입 제외 → 제조사='{manufacturer}'")
            return manufacturer
        else:
            manufacturer = words[0]
            print(f"DEBUG: 첫 단어 → 제조사='{manufacturer}'")
            return manufacturer

    def search_products(self, keyword: str, sort_type: str, maker_codes: List[str], limit: int = 5) -> List[Product]:
        """
        가이드컴에서 제품을 검색합니다.
        가이드컴은 제조사별 API 필터링이 없으므로 클라이언트 사이드에서 필터링
        """
        try:
            # 모바일 버전 정렬 매핑
            order_map = {
                "saveDESC": "reco_goods",     # 추천상품 -> 인기상품
                "opinionDESC": "reco_goods",  # 인기상품 -> 인기상품
                "priceDESC": "price_0",       # 가격 높은순 -> 낮은가격순
                "priceASC": "price_0"         # 가격 낮은순 -> 낮은가격순
            }
            
            order = order_map.get(sort_type, "reco_goods")
            
            # 모바일 버전 파라미터
            params = {
                'mode': 'search',
                'keyword': keyword,
                'order': order
            }
            
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            products = []
            
            # goods.txt 구조에 따른 파싱
            goods_list = self._find_goods_list(soup)
            if not goods_list:
                return []

            # 더 많은 제품을 가져와서 필터링할 여지를 늘림 (최대 50개)
            goods_rows = goods_list.find_all('div', class_='goods-row')
            
            filtered_count = 0
            total_processed = 0
            
            print(f"DEBUG: 선택된 제조사 코드: {maker_codes}")
            print(f"DEBUG: 총 제품 수: {len(goods_rows)}")
            
            for row in goods_rows:
                if filtered_count >= limit:
                    break
                    
                product = self._parse_product_item(row)
                if product:
                    total_processed += 1
                    extracted_manufacturer = self._extract_manufacturer(product.name)
                    
                    # 제조사 필터링 적용
                    is_match = self._filter_by_maker(product, maker_codes)
                    
                    if total_processed <= 5:  # 처음 5개만 디버깅
                        print(f"DEBUG: 제품 {total_processed}: {product.name[:50]}...")
                        print(f"DEBUG: 추출된 제조사: {extracted_manufacturer}")
                        print(f"DEBUG: 필터링 결과: {is_match}")
                    
                    if is_match:
                        products.append(product)
                        filtered_count += 1
            
            print(f"DEBUG: 처리된 제품 수: {total_processed}")
            print(f"DEBUG: 필터링된 제품 수: {filtered_count}")
                    
            return products
            
        except Exception as e:
            print(f"제품 검색 오류: {e}")
            return []
    
    def _filter_by_maker(self, product: Product, maker_codes: List[str]) -> bool:
        """
        제조사 코드로 제품을 필터링합니다.
        가이드컴 특성: 제품명의 첫 단어와 선택된 제조사를 매칭
        """
        # 제조사가 선택되지 않았으면 모든 제품 통과
        if not maker_codes:
            return True
            
        # 제품명에서 제조사 추출
        manufacturer = self._extract_manufacturer(product.name)
        if not manufacturer:
            return False
        
        print(f"DEBUG 필터링: 제품명='{product.name[:30]}...', 추출제조사='{manufacturer}', 선택코드={maker_codes}")
        
        # 간단한 매칭: 제조사명이 선택된 제조사 목록에 있는지 확인
        manufacturer_lower = manufacturer.lower()
        
        for selected_code in maker_codes:
            # 코드에서 제조사명 추출 (code는 name.lower().replace(' ', '_') 형태)
            selected_name = selected_code.replace('_', ' ').lower()
            
            print(f"DEBUG: '{manufacturer_lower}' vs '{selected_name}' 비교")
            
            # 직접 매칭
            if manufacturer_lower == selected_name:
                print(f"DEBUG: 직접 매칭 성공!")
                return True
            
            # 부분 매칭 (제조사명이 포함되어 있는지)
            if manufacturer_lower in selected_name or selected_name in manufacturer_lower:
                print(f"DEBUG: 부분 매칭 성공!")
                return True
        
        print(f"DEBUG: 매칭 실패")
        return False
    
    def _check_brand_alias(self, manufacturer: str, selected_code: str) -> bool:
        """브랜드 별칭을 확인합니다"""
        manufacturer_lower = manufacturer.lower()
        selected_lower = selected_code.lower()
        
        # 한글-영문 매칭
        brand_mapping = {
            '삼성전자': ['samsung', 'samsung전자'],
            '인텔': ['intel'],
            'amd': ['amd'],
            'nvidia': ['nvidia', '엔비디아'],
            'msi': ['msi'],
            'asus': ['asus', '에이수스'],
            '기가바이트': ['gigabyte', 'gb'],
            'evga': ['evga'],
            'zotac': ['zotac', '조택'],
            'sapphire': ['sapphire', '사파이어'],
            'wd': ['wd', 'western', 'digital'],
            'crucial': ['crucial', '크루셜'],
            'kingston': ['kingston', '킹스톤'],
            'corsair': ['corsair', '커세어'],
            'g.skill': ['gskill', 'g_skill']
        }
        
        # 제조사가 매핑에 있는지 확인
        for brand, aliases in brand_mapping.items():
            if brand in manufacturer_lower:
                if any(alias in selected_lower for alias in aliases):
                    return True
            if brand in selected_lower:
                if any(alias in manufacturer_lower for alias in aliases):
                    return True
        
        return False

    def _parse_product_item(self, goods_row) -> Optional[Product]:
        """
        goods.txt 구조에 최적화된 제품 정보 추출
        dibugguid.txt 기준:
        - 상품명: div.desc > h4.title > span.goodsname1  
        - 가격: div.prices > div.price-large.price > span
        - 스펙: div.desc > div.feature
        """
        try:
            # 1. 상품명 추출 (goods.txt 라인 6, 25, 44 기준)
            desc_div = goods_row.find('div', class_='desc')
            if not desc_div:
                return None
            
            title_h4 = desc_div.find('h4', class_='title')
            if not title_h4:
                return None
                
            goodsname_span = title_h4.find('span', class_='goodsname1')
            if not goodsname_span:
                return None
                
            # highlight 태그 포함한 전체 텍스트 추출
            name = goodsname_span.get_text(strip=True)
            
            # 2. 가격 추출 (goods.txt 라인 12, 31, 50 기준)
            prices_div = goods_row.find('div', class_='prices')
            price = "가격 문의"
            if prices_div:
                price_large_div = prices_div.find('div', class_='price-large')
                if price_large_div:
                    price_span = price_large_div.find('span')
                    if price_span and price_span.get_text(strip=True):
                        raw_price = price_span.get_text(strip=True)
                        # 숫자만 있는 경우 '원' 추가
                        if raw_price.isdigit() or ',' in raw_price:
                            price = raw_price + "원"
                        else:
                            price = raw_price

            # 3. 스펙 정보 추출 (goods.txt 라인 7, 26, 45 기준)
            specifications = "사양 정보 없음"
            feature_div = desc_div.find('div', class_='feature')
            if feature_div:
                # dibugguid.txt: 스펙 정보를 ' / '로 구분
                full_text = feature_div.get_text(separator=' / ', strip=True)
                if full_text and len(full_text) > 10:  # 의미있는 스펙 정보만
                    specifications = full_text
            
            return Product(name=name, price=price, specifications=specifications)
            
        except Exception as e:
            print(f"제품 파싱 오류: {e}")
            return None

    def get_unique_products(self, keyword: str, maker_codes: List[str]) -> List[Product]:
        """danawa.py와 동일한 인터페이스를 제공합니다."""
        recommended_products = self.search_products(keyword, "saveDESC", maker_codes, limit=5)
        top_rated_products = self.search_products(keyword, "opinionDESC", maker_codes, limit=5)

        all_products = recommended_products + top_rated_products
        
        unique_products = []
        seen_names = set()
        for product in all_products:
            if product.name not in seen_names:
                unique_products.append(product)
                seen_names.add(product.name)
        
        return unique_products
