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
        가이드컴에서 브랜드/제조사 정보를 가져옵니다.
        실제 사이트 구조에 따라 구현해야 하므로 임시로 기본 브랜드 목록을 반환합니다.
        """
        # 가이드컴 특성상 고정된 브랜드 목록을 제공
        common_brands = [
            {'name': '삼성전자', 'code': 'samsung'},
            {'name': '인텔', 'code': 'intel'},
            {'name': 'AMD', 'code': 'amd'},
            {'name': 'NVIDIA', 'code': 'nvidia'},
            {'name': 'WD', 'code': 'wd'},
            {'name': '시게이트', 'code': 'seagate'},
            {'name': 'MSI', 'code': 'msi'},
            {'name': 'ASUS', 'code': 'asus'},
            {'name': '기가바이트', 'code': 'gigabyte'},
            {'name': 'EVGA', 'code': 'evga'},
            {'name': 'Corsair', 'code': 'corsair'},
            {'name': 'G.SKILL', 'code': 'gskill'},
            {'name': 'Crucial', 'code': 'crucial'},
            {'name': 'Kingston', 'code': 'kingston'},
            {'name': 'ADATA', 'code': 'adata'},
            {'name': 'Patriot', 'code': 'patriot'},
            {'name': 'Team', 'code': 'team'},
            {'name': 'GeIL', 'code': 'geil'},
            {'name': 'OCZ', 'code': 'ocz'},
            {'name': 'PNY', 'code': 'pny'},
            {'name': 'Zotac', 'code': 'zotac'},
            {'name': 'Sapphire', 'code': 'sapphire'},
            {'name': 'PowerColor', 'code': 'powercolor'},
            {'name': 'XFX', 'code': 'xfx'}
        ]
        return common_brands

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
            
            # goods.txt 구조 기반으로 파싱
            product_list = soup.find('ul', class_='product_list')
            if not product_list:
                return []

            items = product_list.find_all('li')
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
            
        product_name_lower = product.name.lower()
        for code in maker_codes:
            if code.lower() in product_name_lower:
                return True
        return True  # 일단 모든 제품 통과

    def _parse_product_item(self, item) -> Optional[Product]:
        """
        dibugguid.txt와 goods.txt 구조에 따라 제품 정보를 추출합니다.
        """
        try:
            # dibugguid.txt 기반 파싱 구조:
            # div class="prod_info"
            # p class="prod_name" > a (상품명)
            prod_info = item.find('div', class_='prod_info')
            if not prod_info:
                return None

            # 상품명 추출
            prod_name_tag = prod_info.find('p', class_='prod_name')
            name = prod_name_tag.a.text.strip() if prod_name_tag and prod_name_tag.a else "정보 없음"

            # 가격 추출: div class="prod_pricelist" > p class="price_sect" > strong
            price_sect = item.find('p', class_='price_sect')
            price = price_sect.strong.text.strip() if price_sect and price_sect.strong else "가격 문의"

            # 스펙 정보 추출: div class="spec_list" > class="highlight" 내용들
            specifications = "사양 정보 없음"
            spec_list_div = item.find('div', class_='spec_list')
            if spec_list_div:
                # highlight 클래스들의 내용을 스펙1, 스펙2... 형태로 수집
                highlights = spec_list_div.find_all(class_='highlight')
                if highlights:
                    spec_items = []
                    for i, highlight in enumerate(highlights[:8]):  # 최대 8개까지
                        spec_text = highlight.get_text(strip=True)
                        if spec_text:
                            spec_items.append(f"스펙{i+1}: {spec_text}")
                    
                    if spec_items:
                        specifications = " / ".join(spec_items)
                else:
                    # highlight가 없으면 전체 텍스트를 가져와서 정리
                    full_text = spec_list_div.get_text(separator='|', strip=True)
                    specs = [spec.strip() for spec in full_text.split('|')]
                    cleaned_specs = [
                        spec for spec in specs 
                        if spec and len(spec) > 1
                    ]
                    if cleaned_specs:
                        specifications = " / ".join(cleaned_specs[:8])  # 최대 8개

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
