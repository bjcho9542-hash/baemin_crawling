# -*- coding: utf-8 -*-
"""
배달의민족 크롤러 - 최종 버전
가게배달 업체 정보 수집: 배달타입, 상호명, 주소, 전화번호, 최근주문수, 전체리뷰수
"""
import uiautomator2 as u2
import time
import re
import sys
import os
import pandas as pd
from datetime import datetime
import xml.etree.ElementTree as ET
import cv2
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')


class BaeminCrawler:
    def __init__(self):
        self.d = None
        self.stores = []

    def connect(self):
        """디바이스 연결"""
        self.d = u2.connect()
        print('[OK] 디바이스 연결됨')
        return True

    def get_xml_root(self):
        """XML 루트 가져오기"""
        xml = self.d.dump_hierarchy()
        return ET.fromstring(xml)

    def get_all_texts(self):
        """현재 화면의 모든 텍스트 추출"""
        root = self.get_xml_root()
        texts = []

        def extract(node):
            text = node.attrib.get('text', '')
            if text.strip():
                texts.append(text.strip())
            for child in node:
                extract(child)

        extract(root)
        return texts

    def get_content_descs(self):
        """현재 화면의 모든 content-desc 추출"""
        root = self.get_xml_root()
        descs = []

        def extract(node):
            desc = node.attrib.get('content-desc', '')
            if desc.strip():
                descs.append(desc.strip())
            for child in node:
                extract(child)

        extract(root)
        return descs

    def find_and_click_image(self, template_path, threshold=0.7):
        """이미지 템플릿 매칭으로 클릭"""
        screen = self.d.screenshot(format='opencv')
        template = cv2.imread(template_path)

        if template is None:
            print(f'[ERROR] 템플릿 없음: {template_path}')
            return False

        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template_gray.shape
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            self.d.click(cx, cy)
            print(f'      [이미지매칭] 클릭 ({cx}, {cy}) - {max_val:.0%}')
            return True
        else:
            print(f'      [WARN] 이미지 못 찾음 - {max_val:.0%}')
            return False

    def extract_delivery_types(self):
        """배달타입 추출 (가게배달/알뜰배달/한집배달)"""
        descs = self.get_content_descs()
        types = []
        for desc in descs:
            if desc in ['가게배달', '알뜰배달', '한집배달']:
                if desc not in types:
                    types.append(desc)
        return types

    def extract_store_info(self):
        """가게정보 페이지에서 상호명, 주소, 전화번호 추출"""
        texts = self.get_all_texts()
        info = {}

        for i, t in enumerate(texts):
            if t == '상호명' and i+1 < len(texts):
                info['상호명'] = texts[i+1]
            if t == '주소' and i+1 < len(texts):
                info['주소'] = texts[i+1]
            if t == '전화번호' and i+1 < len(texts):
                info['전화번호'] = texts[i+1]

        return info

    def extract_stats(self):
        """최근주문수, 전체리뷰수 추출"""
        texts = self.get_all_texts()
        stats = {}

        for i, t in enumerate(texts):
            if t == '최근 주문수' and i+1 < len(texts):
                stats['최근주문수'] = texts[i+1]
            if t == '전체 리뷰수' and i+1 < len(texts):
                stats['전체리뷰수'] = texts[i+1]

        return stats

    def scroll_down(self, times=1):
        """아래로 스크롤"""
        for _ in range(times):
            self.d.swipe(540, 1500, 540, 700, duration=0.3)
            time.sleep(0.8)

    def scroll_up(self, times=1):
        """위로 스크롤"""
        for _ in range(times):
            self.d.swipe(540, 700, 540, 1500, duration=0.3)
            time.sleep(0.8)

    def go_back(self):
        """뒤로가기"""
        self.d.press('back')
        time.sleep(1.5)

    def click_expand_delivery(self):
        """배달타입 펼치기 클릭"""
        elem = self.d(descriptionContains='펼쳐보기')
        if elem.exists(timeout=2):
            elem.click()
            time.sleep(1)
            return True
        return False

    def find_기본순_y(self):
        """기본순 텍스트의 y좌표 찾기"""
        root = self.get_xml_root()

        def find(node):
            text = node.attrib.get('text', '')
            bounds = node.attrib.get('bounds', '')
            if text == '기본순':
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    return int(match.group(4))  # y2 반환
            for child in node:
                result = find(child)
                if result:
                    return result
            return None

        return find(root)

    def get_stores_below_기본순(self, passed_기본순=False, last_store_name=None):
        """기본순 아래에 있는 가게 이름들 추출"""
        root = self.get_xml_root()

        # 1. 기본순 y좌표 찾기
        기본순_y = None
        def find_기본순(node):
            nonlocal 기본순_y
            text = node.attrib.get('text', '')
            bounds = node.attrib.get('bounds', '')
            if text == '기본순':
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    기본순_y = int(match.group(4))
            for child in node:
                find_기본순(child)
        find_기본순(root)

        # 기본순 화면에 없고, 이미 지나갔다면 y=0으로 설정 (전체 화면에서 찾기)
        if 기본순_y is None:
            if passed_기본순:
                기본순_y = 0  # 화면 상단부터 찾기
            else:
                return []

        # 2. 마지막 방문 가게 y좌표 찾기 (있으면)
        last_store_y = None
        if last_store_name:
            def find_last_store(node):
                nonlocal last_store_y
                desc = node.attrib.get('content-desc', '')
                bounds = node.attrib.get('bounds', '')
                if last_store_name in desc and bounds:
                    match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        last_store_y = int(match.group(4))  # 하단 y좌표
                for child in node:
                    find_last_store(child)
            find_last_store(root)

        # 3. "방금 본 가게와 비슷해요!" y좌표 찾기
        방금본가게_y = None
        def find_방금본가게(node):
            nonlocal 방금본가게_y
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')
            if '방금 본 가게' in desc and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    방금본가게_y = int(match.group(4))  # 하단 y좌표
            for child in node:
                find_방금본가게(child)
        find_방금본가게(root)

        # 3. 기본순 아래 가게들 찾기
        stores = []
        def find_stores(node):
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')

            if desc.strip() and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    y1 = int(match.group(2))
                    # 기본순 아래
                    if y1 > 기본순_y:
                        # 제외: 배달타입, 거리, 가격, 별점, 리뷰수, 메뉴설명, UI요소 등
                        exclude = (
                            # 배달타입
                            desc in ['가게배달', '알뜰배달', '한집배달'] or
                            '배달' in desc or
                            # 거리/가격
                            'km' in desc or
                            '원,' in desc or
                            '원)' in desc or
                            '거리' in desc or
                            # 별점/리뷰
                            '별점' in desc or
                            re.match(r'^\d+개$', desc) or
                            re.match(r'^[\d.,]+개$', desc) or
                            re.match(r'^[\d.]+$', desc) or
                            # 광고/프로모션
                            '추천' in desc or
                            '광고' in desc or
                            '받기' in desc or
                            '하기' in desc or
                            '빽보이' in desc or
                            '카카오' in desc or
                            '브랜드' in desc or
                            '쿠폰' in desc or
                            '할인' in desc or
                            '혜택' in desc or
                            '모아보기' in desc or
                            # UI 요소
                            '탭바' in desc or
                            '탭' in desc or
                            '홈' in desc or
                            '뒤로' in desc or
                            '검색' in desc or
                            '장바구니' in desc or
                            '스토어' in desc or
                            '버튼' in desc or
                            '알림' in desc or
                            '도움말' in desc or
                            '배민클럽' in desc or
                            # 상태바 요소
                            '오후' in desc or
                            '오전' in desc or
                            'Mobile' in desc or
                            '신호' in desc or
                            '막대' in desc or
                            '배터리' in desc or
                            '퍼센트' in desc or
                            '5G' in desc or
                            '4G' in desc or
                            'LTE' in desc or
                            'Wi-Fi' in desc or
                            # 기타
                            '번째' in desc or
                            '총' in desc or
                            '방금' in desc or
                            '비슷' in desc or
                            '최소' in desc or
                            '최대' in desc or
                            '메뉴' in desc or
                            '전체' in desc or
                            # 특수문자로 시작
                            desc.startswith(',') or
                            desc.startswith('.') or
                            desc.replace('.', '').replace(',', '').isdigit()
                        )
                        # 가게명: 2글자 이상, 30글자 이하
                        if not exclude and 2 <= len(desc) <= 30:
                            stores.append({'name': desc, 'y': y1})
            for child in node:
                find_stores(child)
        find_stores(root)

        # y좌표로 정렬 (위에서 아래로)
        stores.sort(key=lambda x: x['y'])

        # 중복 제거 (y좌표 근처 50px 이내)
        unique = []
        for s in stores:
            is_dup = False
            for u in unique:
                if abs(u['y'] - s['y']) < 50:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(s)

        # 마지막 방문 가게 아래 + "방금 본 가게와 비슷해요!" 아래 2개 건너뛰기
        if last_store_y and 방금본가게_y:
            # last_store_y 아래에서, 방금본가게_y 아래 2개 제외
            skip_count = 0
            filtered = []
            for s in unique:
                # 마지막 방문 가게 아래만 대상
                if s['y'] > last_store_y:
                    # "방금 본 가게" 아래면 4개 건너뛰기
                    if s['y'] > 방금본가게_y:
                        skip_count += 1
                        if skip_count <= 4:
                            continue
                    filtered.append(s)
            return filtered
        elif 방금본가게_y:
            # 방금본가게_y 바로 아래 4개 제외
            skip_count = 0
            filtered = []
            for s in unique:
                if s['y'] > 방금본가게_y:
                    skip_count += 1
                    if skip_count <= 4:
                        continue  # 처음 4개 건너뛰기
                filtered.append(s)
            return filtered

        return unique

    def get_방금본가게_아래_4개(self):
        """'방금 본 가게와 비슷해요!' 아래 4개 매장 이름 반환"""
        root = self.get_xml_root()

        # 방금 본 가게 y좌표 찾기
        방금본가게_y = None
        def find_방금본가게(node):
            nonlocal 방금본가게_y
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')
            if '방금 본 가게' in desc and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    방금본가게_y = int(match.group(4))
            for child in node:
                find_방금본가게(child)
        find_방금본가게(root)

        if not 방금본가게_y:
            return []

        # 방금본가게_y 아래 가게들 찾기
        stores = []
        def find_stores(node):
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')
            if desc.strip() and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    y1 = int(match.group(2))
                    if y1 > 방금본가게_y:
                        # 가게명 필터 (간단하게)
                        exclude = (
                            '배달' in desc or 'km' in desc or '원' in desc or
                            '별점' in desc or '개' in desc or '탭' in desc or
                            '홈' in desc or '검색' in desc or '버튼' in desc or
                            '오후' in desc or '오전' in desc or '방금' in desc or
                            '비슷' in desc or len(desc) < 2 or len(desc) > 30
                        )
                        if not exclude:
                            stores.append({'name': desc, 'y': y1})
            for child in node:
                find_stores(child)
        find_stores(root)

        # y좌표로 정렬해서 상위 4개 반환
        stores.sort(key=lambda x: x['y'])
        return [s['name'] for s in stores[:4]]

    def click_store_by_index(self, index):
        """가게 목록에서 N번째 가게 클릭 (기본순 아래)"""
        stores = self.get_stores_below_기본순()

        if index <= len(stores):
            store_name = stores[index - 1]['name']
            elem = self.d(descriptionContains=store_name)
            if elem.exists(timeout=3):
                elem.click()
                print(f'      [OK] {index}번째 가게 클릭: {store_name}')
                time.sleep(2)
                return True

        print(f'      [WARN] {index}번째 가게 못 찾음')
        return False

    def get_store_name_from_list(self):
        """가게 상세 페이지에서 가게명 추출"""
        texts = self.get_all_texts()
        # 첫 번째 줄이 보통 가게명
        for t in texts:
            if len(t) > 2 and len(t) < 30 and '배달' not in t and '리뷰' not in t:
                return t
        return ''

    def crawl_single_store(self, store_index):
        """단일 가게 크롤링 (가게 상세 페이지에서 시작)"""
        store_data = {
            '순번': store_index,
            '가게명': '',
            '배달타입': '',
            '상호명': '',
            '주소': '',
            '전화번호': '',
            '최근주문수': '',
            '전체리뷰수': '',
            '크롤링시간': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        try:
            # 0. 가게명 추출
            store_data['가게명'] = self.get_store_name_from_list()
            print(f'      가게명: {store_data["가게명"]}')

            # 1. 배달타입 펼치기
            print(f'      [1] 배달타입 펼치기...')
            self.click_expand_delivery()
            time.sleep(1)

            # 2. 배달타입 추출
            print(f'      [2] 배달타입 추출...')
            delivery_types = self.extract_delivery_types()
            store_data['배달타입'] = ', '.join(delivery_types)
            print(f'          → {store_data["배달타입"]}')

            # 3. 가게정보·원산지 클릭 (이미지 매칭)
            print(f'      [3] 가게정보·원산지 클릭...')
            if self.find_and_click_image('templates/store_info_btn.png', threshold=0.6):
                time.sleep(2)

                # 4. 상호명, 주소, 전화번호 추출
                print(f'      [4] 가게정보 추출...')
                info = self.extract_store_info()
                store_data.update(info)
                print(f'          → 상호명: {info.get("상호명", "없음")}')

                # 5. 스크롤해서 최근주문수, 전체리뷰수 추출
                print(f'      [5] 통계 추출...')
                self.scroll_down(3)
                stats = self.extract_stats()
                store_data.update(stats)
                print(f'          → 최근주문수: {stats.get("최근주문수", "없음")}')
                print(f'          → 전체리뷰수: {stats.get("전체리뷰수", "없음")}')

                # 뒤로가기 (가게정보 → 가게상세)
                self.go_back()

        except Exception as e:
            print(f'      [ERROR] {e}')

        # 뒤로가기 (가게상세 → 가게목록) - 항상 1번만
        self.go_back()

        return store_data

    def save_to_excel(self, filename=None):
        """엑셀 저장"""
        if not self.stores:
            print('[WARN] 저장할 데이터 없음')
            return

        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'baemin_stores_{timestamp}.xlsx'

        df = pd.DataFrame(self.stores)
        df.to_excel(filename, index=False)
        print(f'[OK] 엑셀 저장 완료: {filename}')
        print(f'     총 {len(self.stores)}개 가게')

    def go_to_store_list(self):
        """메인화면에서 음식배달 더보기 클릭 → 기본순 아래 가게 찾기"""
        print('[STEP 1] 음식배달에서 더보기 클릭')
        elem = self.d(descriptionContains='음식배달에서 더보기')
        if elem.exists(timeout=3):
            elem.click()
            time.sleep(2)
            print('      [OK] 더보기 클릭 완료')
        else:
            print('      [WARN] 더보기 버튼 못 찾음')
            return False

        print('[STEP 2] 기본순 아래 가게목록 찾기')
        for i in range(10):
            # 기본순 아래 가게가 있는지 확인
            stores = self.get_stores_below_기본순()
            if stores:
                print(f'      [OK] 기본순 아래 가게 {len(stores)}개 발견! (스크롤 {i}회)')
                for j, s in enumerate(stores[:3]):
                    print(f'          {j+1}. {s["name"]}')
                return True

            self.scroll_down(1)
            print(f'      스크롤 {i+1}회...')

        print('      [WARN] 기본순 아래 가게 못 찾음')
        return False

    def collect_all_store_names(self, max_stores=50):
        """스크롤하면서 가게 이름 모두 수집 (1단계)"""
        print('[PHASE 1] 가게 이름 수집 시작')
        print('-' * 40)

        all_names = []
        no_new_count = 0
        max_no_new = 5  # 5번 연속 새 가게 없으면 종료

        while len(all_names) < max_stores and no_new_count < max_no_new:
            stores = self.get_stores_below_기본순(passed_기본순=len(all_names) > 0)

            new_count = 0
            for s in stores:
                if s['name'] not in all_names:
                    all_names.append(s['name'])
                    new_count += 1
                    print(f'      {len(all_names)}. {s["name"]}')

                    if len(all_names) >= max_stores:
                        break

            if new_count == 0:
                no_new_count += 1
            else:
                no_new_count = 0

            # 스크롤
            if len(all_names) < max_stores:
                self.scroll_down(1)
                time.sleep(0.5)

        print(f'\n[OK] 총 {len(all_names)}개 가게 이름 수집 완료')
        return all_names

    def run(self, max_stores=5):
        """크롤링 실행 - 화면에 보이는 가게 바로 크롤링"""
        print('=' * 60)
        print('  배달의민족 크롤러')
        print('=' * 60)
        print()

        if not self.connect():
            return

        # 메인화면에서 가게 목록으로 이동
        if not self.go_to_store_list():
            print('[ERROR] 가게 목록으로 이동 실패')
            return

        collected_names = []  # 이미 수집한 가게명
        collected_count = 0
        retry_count = 0
        max_retry = 10
        last_store = None  # 마지막 방문 가게

        while collected_count < max_stores and retry_count < max_retry:
            # 현재 화면에서 가게 찾기 (마지막 방문 가게 기준)
            stores = self.get_stores_below_기본순(
                passed_기본순=collected_count > 0,
                last_store_name=last_store
            )

            # 아직 수집 안 한 가게 찾기
            new_store = None
            for s in stores:
                if s['name'] not in collected_names:
                    new_store = s
                    break

            if new_store:
                collected_count += 1
                print(f'\n[{collected_count}/{max_stores}] {new_store["name"]}')

                # 가게 클릭
                elem = self.d(descriptionContains=new_store['name'])
                if elem.exists(timeout=3):
                    elem.click()
                    print(f'      [OK] 클릭')
                    time.sleep(2)

                    # 크롤링
                    store_data = self.crawl_single_store(collected_count)
                    store_data['가게명'] = new_store['name']
                    self.stores.append(store_data)
                    collected_names.append(new_store['name'])
                    last_store = new_store['name']  # 마지막 방문 가게 업데이트
                    print(f'      [완료] 상호명: {store_data.get("상호명", "")}')

                    # 뒤로가기 직후 "방금 본 가게와 비슷해요!" 아래 4개 매장 이름 수집해서 제외 목록에 추가
                    time.sleep(0.5)
                    방금본_stores = self.get_방금본가게_아래_4개()
                    for s in 방금본_stores:
                        if s not in collected_names:
                            collected_names.append(s)
                            print(f'      [SKIP] 방금본가게 광고: {s}')
                else:
                    print(f'      [WARN] 클릭 실패')
                    collected_count -= 1

                retry_count = 0
                time.sleep(1)
            else:
                # 새 가게 없으면 스크롤
                print(f'      스크롤... ({retry_count+1})')
                self.scroll_down(1)
                retry_count += 1
                time.sleep(1)

        # 엑셀 저장
        self.save_to_excel()

        print()
        print('=' * 60)
        print('  크롤링 완료!')
        print('=' * 60)


if __name__ == '__main__':
    crawler = BaeminCrawler()
    crawler.run(max_stores=10)  # 테스트: 10개
