import os
import requests
from bs4 import BeautifulSoup

# 디버그 모드 활성화
os.environ['GUIDECOM_DEBUG'] = '1'

from guidecom import GuidecomParser

def test_simple_request():
    """간단한 요청 테스트"""
    print("=== 간단한 요청 테스트 ===")
    
    parser = GuidecomParser()
    
    try:
        # 직접 요청
        url = "https://www.guidecom.co.kr/search/index.html"
        params = {"keyword": "SSD"}
        
        print(f"요청 URL: {url}")
        print(f"파라미터: {params}")
        
        response = parser.session.get(url, params=params, timeout=30)
        print(f"응답 상태: {response.status_code}")
        print(f"응답 길이: {len(response.text)}")
        print(f"인코딩: {response.encoding}")
        
        # HTML 내용 확인
        soup = BeautifulSoup(response.text, 'lxml')
        
        # goods-row 찾기
        goods_rows = soup.find_all("div", class_="goods-row")
        print(f"goods-row 개수: {len(goods_rows)}")
        
        # 다른 가능한 상품 컨테이너들 찾기
        possible_containers = [
            "product-item", "item", "goods-item", "product", 
            "list-item", "search-item", "result-item"
        ]
        
        for container_class in possible_containers:
            items = soup.find_all(class_=lambda x: x and container_class in str(x))
            if items:
                print(f"Found {len(items)} items with class containing '{container_class}'")
                print(f"첫 번째 아이템: {str(items[0])[:200]}")
        
        # 전체 body 내용의 일부 출력
        print("\n=== 페이지 내용 샘플 ===")
        print(response.text[:2000])
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_request()
