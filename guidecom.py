import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Product:
    name: str
    price: str
    specifications: str

class GuidecomParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = "https://www.guidecom.co.kr/search/index.html"

    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        """
        가이드컴에서 제품을 검색하여 제조사 정보를 추출합니다.
        제품명의 첫 단어를 제조사로 사용 (공식인증, 병행수입 제외)
        최대 8개의 제조사를 중복 없이 반환합니다.
        """
        try:
            # 검색하여 제품 목록 가져오기
            params = {'keyword': keyword}
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            manufacturers = set()
            
            # div id="goods-list" 에서 제품 찾기
            goods_list = soup.find('div', id='goods-list')
            if not goods_list:
                return []
            
            # 모든 goods-row 찾기
            goods_rows = goods_list.find_all('div', class_='goods-row')
            
            for row in goods_rows:
                # span class="goodsname1"에서 제품명 추출
                goodsname_span = row.find('span', class_='goodsname1')
                if goodsname_span:
                    # highlight 태그 제거하고 텍스트만 추출
                    product_name = goodsname_span.get_text(strip=True)
                    manufacturer = self._extract_manufacturer(product_name)
                    if manufacturer:
                        manufacturers.add(manufacturer)
                        
                        # 최대 8개 제한
                        if len(manufacturers) >= 8:
                            break
            
            # 제조사 목록을 알파벳순으로 정렬하여 반환
            manufacturer_list = []
            for manufacturer in sorted(manufacturers):
                manufacturer_list.append({
                    'name': manufacturer,
                    'code': manufacturer.lower().replace(' ', '_')
                })
            
            return manufacturer_list
            
        except Exception as e:
            print(f"An error occurred while fetching search options: {e}")
            return []
    
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
        
        # 첫 단어가 '공식인증' 또는 '병행수입'인 경우
        if words[0] in ['공식인증', '병행수입'] and len(words) > 1:
            return words[1]
        else:
            return words[0]

    def search_products(self, keyword: str, sort_type: str, maker_codes: List[str], limit: int = 5) -> List[Product]:
        """
        가이드컴에서 제품을 검색합니다.
        dibugguid.txt 기반으로 API URL 구조 사용
        """
        # 정렬 타입 매핑 (danawa.py와 호환)
        order_map = {
            "saveDESC": "event_goods",  # 추천상품 -> 행사상품
            "opinionDESC": "reco_goods",  # 인기상품
            "priceDESC": "price_0",    # 가격 낮은 순
            "priceASC": "price_0"      # 가격 낮은 순
        }
        
        order = order_map.get(sort_type, "reco_goods")
        
        params = {
            'keyword': keyword,
            'order': order
        }
        
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            products = []
            
            # 새로운 구조: div id="goods-list"
            goods_list = soup.find('div', id='goods-list')
            if not goods_list:
                return []

            # 모든 goods-row 찾기
            items = goods_list.find_all('div', class_='goods-row')
            for item in items[:limit]:
                product = self._parse_product_item(item)
                if product and self._filter_by_maker(product, maker_codes):
                    products.append(product)
                    
            return products
            
        except Exception as e:
            print(f"An error occurred while searching for products: {e}")
            return []
    
    def _filter_by_maker(self, product: Product, maker_codes: List[str]) -> bool:
        """제조사 코드로 제품을 필터링합니다."""
        if not maker_codes:
            return True
            
        # 제품명에서 제조사 추출
        manufacturer = self._extract_manufacturer(product.name)
        if not manufacturer:
            return False
            
        # 제조사가 선택된 코드 목록에 있는지 확인
        manufacturer_code = manufacturer.lower().replace(' ', '_')
        return manufacturer_code in maker_codes

    def _parse_product_item(self, item) -> Optional[Product]:
        """
        새로운 구조에 따라 제품 정보를 추출합니다.
        - 상품명: span class="goodsname1"
        - 가격: div class="prices" > span
        - 스펙: div class="feature"
        """
        try:
            # 상품명 추출: div class="desc" > h4 class="title" > span class="goodsname1"
            desc_div = item.find('div', class_='desc')
            if not desc_div:
                return None
            
            goodsname_span = desc_div.find('span', class_='goodsname1')
            name = goodsname_span.get_text(strip=True) if goodsname_span else "정보 없음"

            # 가격 추출: div class="prices" > div class="price-large price" > span
            prices_div = item.find('div', class_='prices')
            price = "가격 문의"
            if prices_div:
                price_span = prices_div.find('span')
                if price_span:
                    price = price_span.get_text(strip=True) + "원"

            # 스펙 정보 추출: div class="feature"
            specifications = "사양 정보 없음"
            feature_div = desc_div.find('div', class_='feature')
            if feature_div:
                # 전체 텍스트를 가져와서 정리
                full_text = feature_div.get_text(separator=' / ', strip=True)
                if full_text:
                    specifications = full_text

            return Product(name=name, price=price, specifications=specifications)
            
        except Exception as e:
            print(f"Error parsing product item: {e}")
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
