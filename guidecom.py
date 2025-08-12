import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Product:
    name: str
    price: str
    specifications: str

class DanawaParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = "https://search.danawa.com/dsearch.php"

    def get_search_options(self, keyword: str) -> List[Dict[str, str]]:
        params = {'query': keyword}
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. 정확한 방법 시도
            options = self._get_options_strictly(soup)
            if options:
                return options

            # 2. 정확한 방법 실패 시, 넓은 범위의 대체 방법으로 전환
            return self._get_options_broadly(soup)

        except Exception as e:
            print(f"An error occurred while fetching search options: {e}")
            return []

    def _get_options_strictly(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """ "제조사/브랜드" 섹션을 정확히 찾아서 옵션을 추출합니다. """
        options = []
        option_area = soup.find('div', id='searchOptionListArea')
        if not option_area:
            return []

        title_tag = option_area.find('h4', class_='cate_tit', string=lambda t: t and t.strip() in ["제조사/브랜드", "제조자"])
        if title_tag:
            parent_container = title_tag.find_parent('div', class_=[_class for _class in ['search_option_item', 'basic_top_area'] if _class])
            if parent_container:
                cate_cont = parent_container.find('div', class_='cate_cont')
                if cate_cont:
                    maker_items = cate_cont.find_all('div', class_='basic_cate_item')
                    for item in maker_items:
                        checkbox = item.find('input', type='checkbox')
                        label = item.find('label')
                        if checkbox and label:
                            name_span = label.find('span', class_='name')
                            if name_span:
                                options.append({
                                    'name': name_span.text.strip(),
                                    'code': checkbox.get('value')
                                })
        return options

    def _get_options_broadly(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """ 넓은 범위로 모든 옵션을 찾되, 상위 24개로 제한합니다. """
        options = []
        option_area = soup.find('div', id='searchOptionListArea')
        if not option_area:
            return []

        maker_items = option_area.find_all('div', class_='basic_cate_item', limit=24)
        for item in maker_items:
            checkbox = item.find('input', type='checkbox')
            label = item.find('label')
            if checkbox and label:
                name_span = label.find('span', class_='name')
                if name_span:
                    options.append({
                        'name': name_span.text.strip(),
                        'code': checkbox.get('value')
                    })
        return options

    def search_products(self, keyword: str, sort_type: str, maker_codes: List[str], limit: int = 5) -> List[Product]:
        params = {
            'query': keyword,
            'sort': sort_type,
            'maker': ",".join(maker_codes)
        }
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            products = []
            
            product_list = soup.find('ul', class_='product_list')
            if not product_list:
                return []

            items = product_list.find_all('li', class_='prod_item')
            for item in items[:limit]:
                product = self._parse_product_item(item)
                if product:
                    products.append(product)
            return products
        except Exception as e:
            print(f"An error occurred while searching for products: {e}")
            return []

    def _parse_product_item(self, item) -> Optional[Product]:
        try:
            prod_info = item.find('div', class_='prod_info')
            if not prod_info:
                return None

            prod_name_tag = prod_info.find('p', class_='prod_name')
            name = prod_name_tag.a.text.strip() if prod_name_tag and prod_name_tag.a else "정보 없음"

            price_sect = item.find('p', class_='price_sect')
            price = price_sect.a.strong.text.strip() if price_sect and price_sect.a and price_sect.a.strong else "가격 문의"

            specifications = "사양 정보 없음"
            spec_list_div = item.find('div', class_='spec_list')
            if spec_list_div:
                # get_text()를 사용하여 모든 텍스트를 가져온 후, | 문자로 분리하고 정리합니다.
                full_text = spec_list_div.get_text(separator='|', strip=True)
                specs = [spec.strip() for spec in full_text.split('|')]
                
                # 불필요한 텍스트(빈 문자열, 특수문자 등)를 제거합니다.
                cleaned_specs = [
                    spec for spec in specs 
                    if spec and len(spec) > 1 and "상세 스펙 보기" not in spec
                ]
                
                if cleaned_specs:
                    specifications = " / ".join(cleaned_specs)

            return Product(name=name, price=price, specifications=specifications)
        except Exception as e:
            print(f"Error parsing product item: {e}")
            return None

    def get_unique_products(self, keyword: str, maker_codes: List[str]) -> List[Product]:
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
