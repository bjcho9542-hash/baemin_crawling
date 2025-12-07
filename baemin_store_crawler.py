"""
배달의민족 가게 정보 크롤러
=============================
목표: 가게배달 가능한 업체 정보 수집 (가게명, 주소, 전화번호)
방법: uiautomator2를 사용한 UI 자동화

사용법:
    python baemin_store_crawler.py              # 현재 열린 가게 정보 추출
    python baemin_store_crawler.py category 치킨 5  # 치킨 카테고리에서 5개 가게 크롤링
"""
import uiautomator2 as u2
import time
import json
import re
import os
from datetime import datetime

os.environ['ANDROID_HOME'] = r"C:\Android\Sdk"


class BaeminStoreCrawler:
    def __init__(self):
        self.device = None
        self.stores = []
        self.output_file = "crawled_stores.json"

    def connect(self):
        """에뮬레이터/디바이스 연결"""
        try:
            self.device = u2.connect()
            info = self.device.info
            print(f"[OK] 연결됨: {info.get('productName', 'Unknown')}")
            print(f"     화면: {info.get('displayWidth')}x{info.get('displayHeight')}")
            return True
        except Exception as e:
            print(f"[ERROR] 연결 실패: {e}")
            print("  - Android 에뮬레이터가 실행 중인지 확인하세요")
            print("  - ADB가 연결되어 있는지 확인하세요: adb devices")
            return False

    def wait(self, seconds=1):
        time.sleep(seconds)

    def screenshot(self, name="screen"):
        """스크린샷 저장"""
        path = f"{name}.png"
        self.device.screenshot(path)
        return path

    def go_back(self):
        """뒤로가기"""
        self.device.press("back")
        self.wait(1.5)

    def scroll_down(self):
        """화면 스크롤 다운"""
        self.device.swipe(540, 1600, 540, 800, duration=0.3)
        self.wait(1)

    def scroll_up(self):
        """화면 스크롤 업"""
        self.device.swipe(540, 800, 540, 1600, duration=0.3)
        self.wait(1)

    def click_category(self, category_name):
        """
        카테고리 클릭 (치킨, 피자, 한식 등)
        메인 화면에서 사용
        """
        try:
            # content-desc로 찾기 (배민 앱의 카테고리 버튼)
            elem = self.device(description=category_name)
            if elem.exists(timeout=3):
                elem.click()
                print(f"[OK] '{category_name}' 카테고리 클릭")
                self.wait(3)
                return True

            # 텍스트로 찾기
            elem = self.device(text=category_name)
            if elem.exists(timeout=2):
                elem.click()
                print(f"[OK] '{category_name}' 텍스트 클릭")
                self.wait(3)
                return True

            print(f"[WARN] '{category_name}' 카테고리를 찾을 수 없음")
            return False
        except Exception as e:
            print(f"[ERROR] 카테고리 클릭 실패: {e}")
            return False

    def click_first_store(self):
        """가게 목록에서 첫 번째 가게 클릭"""
        try:
            # 클릭 가능한 요소 중 가게처럼 보이는 것 찾기
            elements = self.device.xpath('//*[@clickable="true"]').all()
            stores = []

            for elem in elements:
                bounds = elem.attrib.get('bounds', '')
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    height = y2 - y1
                    # 가게 리스트 영역 (화면 중앙~하단, 적당한 높이)
                    if 400 < y1 < 1800 and height > 150:
                        stores.append({'bounds': bounds, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})

            stores.sort(key=lambda x: x['y1'])

            if stores:
                s = stores[0]
                cx, cy = (s['x1'] + s['x2']) // 2, (s['y1'] + s['y2']) // 2
                self.device.click(cx, cy)
                print(f"[OK] 가게 클릭 at ({cx}, {cy})")
                self.wait(3)
                return True

            print("[WARN] 가게를 찾을 수 없음")
            return False
        except Exception as e:
            print(f"[ERROR] 가게 클릭 실패: {e}")
            return False

    def click_store_info_button(self):
        """가게정보·원산지 버튼 클릭"""
        try:
            # 다양한 방법으로 찾기
            selectors = [
                ("textContains", "정보"),
                ("textContains", "원산지"),
                ("text", "정보·원산지"),
                ("descriptionContains", "정보"),
            ]

            for method, value in selectors:
                if method == "text":
                    elem = self.device(text=value)
                elif method == "textContains":
                    elem = self.device(textContains=value)
                elif method == "descriptionContains":
                    elem = self.device(descriptionContains=value)

                if elem.exists(timeout=2):
                    elem.click()
                    print(f"[OK] 가게정보 버튼 클릭")
                    self.wait(2)
                    return True

            print("[WARN] 가게정보 버튼을 찾을 수 없음")
            return False
        except Exception as e:
            print(f"[ERROR] 가게정보 버튼 클릭 실패: {e}")
            return False

    def extract_store_info(self):
        """
        현재 화면(가게정보·원산지 페이지)에서 정보 추출
        """
        info = {
            "store_name": None,
            "business_name": None,
            "address": None,
            "phone": None,
            "hours": None,
            "closed_days": None,
            "crawled_at": datetime.now().isoformat()
        }

        try:
            # UI 덤프에서 텍스트 추출
            xml = self.device.dump_hierarchy()
            texts = re.findall(r'text="([^"]+)"', xml)
            texts = [t.strip() for t in texts if t.strip() and len(t) > 1]

            print(f"[INFO] {len(texts)}개 텍스트 요소 발견")

            # 패턴 매칭으로 정보 추출
            for i, t in enumerate(texts):
                # 상호명
                if t == '상호명' and i + 1 < len(texts):
                    info['business_name'] = texts[i + 1]

                # 주소
                if t == '주소' and i + 1 < len(texts):
                    info['address'] = texts[i + 1]

                # 전화번호
                if t == '전화번호' and i + 1 < len(texts):
                    info['phone'] = texts[i + 1]

                # 운영시간
                if t == '운영시간' and i + 1 < len(texts):
                    info['hours'] = texts[i + 1]

                # 휴무일
                if t == '휴무일' and i + 1 < len(texts):
                    info['closed_days'] = texts[i + 1]

            # 가게명은 상단에 있음 (첫 번째 의미있는 텍스트)
            for t in texts[1:10]:
                if len(t) > 3 and len(t) < 30:
                    if not any(x in t for x in ['상호명', '주소', '전화', '운영', '휴무', ':']):
                        info['store_name'] = t
                        break

            return info

        except Exception as e:
            print(f"[ERROR] 정보 추출 실패: {e}")
            return info

    def crawl_current_store(self):
        """현재 열린 가게의 정보 크롤링 (가게 상세 페이지에서 시작)"""
        print("\n" + "=" * 50)
        print("현재 가게 정보 크롤링")
        print("=" * 50)

        # 1. 가게정보 버튼 클릭
        print("\n[1] 가게정보 버튼 찾기...")
        if not self.click_store_info_button():
            print("[WARN] 가게정보 버튼을 찾지 못함. 현재 화면에서 정보 추출 시도...")

        # 2. 정보 추출
        print("\n[2] 정보 추출 중...")
        info = self.extract_store_info()

        # 3. 결과 출력
        print("\n[결과] 추출된 가게 정보:")
        print("-" * 40)
        for key, value in info.items():
            if value and key != 'crawled_at':
                print(f"  {key}: {value}")
        print("-" * 40)

        return info

    def crawl_category(self, category_name, max_stores=5):
        """
        특정 카테고리의 여러 가게 크롤링
        메인 화면에서 시작해야 함
        """
        print("\n" + "=" * 50)
        print(f"카테고리 '{category_name}' 크롤링 시작 (최대 {max_stores}개)")
        print("=" * 50)

        # 1. 카테고리 클릭
        if not self.click_category(category_name):
            return []

        crawled = []
        for i in range(max_stores):
            print(f"\n--- 가게 {i + 1}/{max_stores} ---")

            # 2. 가게 클릭
            if not self.click_first_store():
                print("[WARN] 더 이상 가게를 찾을 수 없음")
                self.scroll_down()
                continue

            # 3. 정보 추출
            info = self.crawl_current_store()
            if info.get('address') or info.get('phone'):
                crawled.append(info)
                self.stores.append(info)
                print(f"[OK] 가게 정보 저장 완료")
            else:
                print("[WARN] 정보 추출 실패")

            # 4. 뒤로가기 (가게 목록으로)
            self.go_back()  # 가게정보 → 가게상세
            self.go_back()  # 가게상세 → 가게목록
            self.wait(1)

            # 5. 다음 가게를 위해 스크롤
            self.scroll_down()

        return crawled

    def save_results(self):
        """크롤링 결과 저장"""
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.stores, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] 결과 저장됨: {self.output_file}")
        print(f"     총 {len(self.stores)}개 가게 정보")


def main():
    import sys

    crawler = BaeminStoreCrawler()

    if not crawler.connect():
        return

    if len(sys.argv) >= 2:
        if sys.argv[1] == "category":
            # 카테고리 크롤링 모드
            category = sys.argv[2] if len(sys.argv) > 2 else "치킨"
            count = int(sys.argv[3]) if len(sys.argv) > 3 else 5
            crawler.crawl_category(category, count)
            crawler.save_results()
        else:
            print(f"알 수 없는 명령: {sys.argv[1]}")
            print("사용법:")
            print("  python baemin_store_crawler.py              # 현재 가게 정보 추출")
            print("  python baemin_store_crawler.py category 치킨 5  # 치킨 카테고리 5개")
    else:
        # 현재 가게 정보 추출
        info = crawler.crawl_current_store()
        crawler.stores.append(info)
        crawler.save_results()


if __name__ == "__main__":
    main()
