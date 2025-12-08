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
        """최근주문수, 전체리뷰수 추출 - 라벨 오른쪽 같은 행에서 값 찾기"""
        root = self.get_xml_root()
        stats = {}

        # 모든 텍스트 요소와 bounds 수집
        elements = []
        def collect(node):
            text = node.attrib.get('text', '').strip()
            bounds = node.attrib.get('bounds', '')
            if text and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    elements.append({
                        'text': text,
                        'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                        'cy': (y1 + y2) // 2
                    })
            for child in node:
                collect(child)
        collect(root)

        # 라벨 찾고 같은 행(y좌표 유사)에서 오른쪽에 있는 값 찾기
        for elem in elements:
            if elem['text'] == '최근 주문수':
                for other in elements:
                    if other['x1'] >= elem['x2'] and abs(other['cy'] - elem['cy']) < 40:
                        stats['최근주문수'] = other['text']
                        break

            if elem['text'] == '전체 리뷰수':
                for other in elements:
                    if other['x1'] >= elem['x2'] and abs(other['cy'] - elem['cy']) < 40:
                        stats['전체리뷰수'] = other['text']
                        break

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

    def click_sort_option(self, sort_type='기본순'):
        """정렬 옵션 선택 (기본순/주문 많은 순/별점 높은 순/가까운 순/찜 많은 순)"""
        # 1. 정렬 버튼 클릭 (기본순 텍스트 위쪽 버튼 클릭)
        # 기본순 텍스트 좌표를 찾고, 그 위쪽(약 130px)을 클릭
        sort_btn = self.d(textContains='기본순')
        if sort_btn.exists(timeout=3):
            # 기본순 텍스트의 bounds에서 좌표 추출
            info = sort_btn.info
            bounds = info.get('bounds', {})
            x = (bounds.get('left', 0) + bounds.get('right', 0)) // 2
            y = bounds.get('top', 0) - 130  # 텍스트 위쪽 130px
            self.d.click(x, y)
            print(f'      [OK] 정렬 버튼 클릭 ({x}, {y})')
            time.sleep(1)
        else:
            print(f'      [WARN] 정렬 버튼 못 찾음')
            return False

        # 2. 원하는 정렬 옵션 선택
        sort_elem = self.d(descriptionContains=sort_type)
        if sort_elem.exists(timeout=3):
            sort_elem.click()
            print(f'      [OK] 정렬 선택: {sort_type}')
            time.sleep(1)
            return True
        else:
            print(f'      [WARN] 정렬 옵션 못 찾음: {sort_type}')
            # 팝업 닫기 (뒤로가기)
            self.d.press('back')
            return False

    def find_기본순_y(self):
        """기본순 또는 기본순 외 텍스트의 y좌표 찾기"""
        root = self.get_xml_root()

        def find(node):
            text = node.attrib.get('text', '')
            bounds = node.attrib.get('bounds', '')
            # '기본순' 또는 '기본순 외' 둘 다 찾기
            if text == '기본순' or text.startswith('기본순 외'):
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
        """기본순 또는 기본순 외 아래에 있는 가게 이름들 추출"""
        root = self.get_xml_root()

        # 1. 기본순 또는 기본순 외 y좌표 찾기
        기본순_y = None
        def find_기본순(node):
            nonlocal 기본순_y
            text = node.attrib.get('text', '')
            bounds = node.attrib.get('bounds', '')
            # '기본순' 또는 '기본순 외' 둘 다 찾기
            if text == '기본순' or text.startswith('기본순 외'):
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
                        # 가게명 추출: "가게명, 배달팁 X원" → "가게명"
                        store_name = desc
                        if ', 배달팁' in desc:
                            store_name = desc.split(', 배달팁')[0]

                        # 제외: 배달타입, 거리, 가격, 별점, 리뷰수, 메뉴설명, UI요소 등
                        exclude = (
                            # 배달타입/UI
                            store_name in ['가게배달', '알뜰배달', '한집배달', '음식배달'] or
                            '음식' in store_name or
                            # 거리/가격
                            'km' in store_name or
                            '원,' in store_name or
                            '원)' in store_name or
                            '거리' in store_name or
                            # 별점/리뷰
                            '별점' in store_name or
                            re.match(r'^\d+개$', store_name) or
                            re.match(r'^[\d.,]+개$', store_name) or
                            re.match(r'^[\d.]+$', store_name) or
                            # 광고/프로모션
                            '추천' in store_name or
                            '광고' in store_name or
                            '받기' in store_name or
                            '하기' in store_name or
                            '빽보이' in store_name or
                            '카카오' in store_name or
                            '브랜드' in store_name or
                            '쿠폰' in store_name or
                            '할인' in store_name or
                            '혜택' in store_name or
                            '모아보기' in store_name or
                            '푸드페스타' in store_name or
                            '혼자 사는 어르신에게' in store_name or
                            # UI 요소
                            '탭바' in store_name or
                            '탭' in store_name or
                            '홈' in store_name or
                            '뒤로' in store_name or
                            '검색' in store_name or
                            '장바구니' in store_name or
                            '스토어' in store_name or
                            '버튼' in store_name or
                            '알림' in store_name or
                            '도움말' in store_name or
                            '배민클럽' in store_name or
                            # 상태바 요소
                            '오후' in store_name or
                            '오전' in store_name or
                            'Mobile' in store_name or
                            '신호' in store_name or
                            '막대' in store_name or
                            '배터리' in store_name or
                            '퍼센트' in store_name or
                            '5G' in store_name or
                            '4G' in store_name or
                            'LTE' in store_name or
                            'Wi-Fi' in store_name or
                            # 기타
                            '번째' in store_name or
                            '총' in store_name or
                            '방금' in store_name or
                            '비슷' in store_name or
                            '최소' in store_name or
                            '최대' in store_name or
                            '메뉴' in store_name or
                            '전체' in store_name or
                            # 특수문자로 시작
                            store_name.startswith(',') or
                            store_name.startswith('.') or
                            store_name.replace('.', '').replace(',', '').isdigit()
                        )
                        # 가게명: 2글자 이상, 30글자 이하
                        if not exclude and 2 <= len(store_name) <= 30:
                            stores.append({'name': store_name, 'y': y1})
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
                        # 가게명 추출: "가게명, 배달팁 X원" → "가게명"
                        store_name = desc
                        if ', 배달팁' in desc:
                            store_name = desc.split(', 배달팁')[0]

                        # 가게명 필터 (간단하게)
                        exclude = (
                            'km' in store_name or '음식' in store_name or
                            '별점' in store_name or '개' in store_name or '탭' in store_name or
                            '홈' in store_name or '검색' in store_name or '버튼' in store_name or
                            '오후' in store_name or '오전' in store_name or '방금' in store_name or
                            '비슷' in store_name or '배민클럽' in store_name or
                            '푸드페스타' in store_name or '추천' in store_name or '광고' in store_name or
                            '혼자 사는 어르신에게' in store_name or
                            store_name in ['가게배달', '알뜰배달', '한집배달', '음식배달'] or
                            len(store_name) < 2 or len(store_name) > 30
                        )
                        if not exclude:
                            stores.append({'name': store_name, 'y': y1})
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

                # 5. 최근주문수, 전체리뷰수 추출 (둘 다 보일 때까지 스크롤)
                print(f'      [5] 통계 추출...')
                for _ in range(5):
                    if self.d(textContains='최근 주문수').exists(timeout=1) and self.d(textContains='전체 리뷰수').exists(timeout=1):
                        break
                    self.scroll_down(1)
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

    def run(self, max_stores=5, sort_type='기본순'):
        """크롤링 실행 - 화면에 보이는 가게 바로 크롤링

        Args:
            max_stores: 크롤링할 최대 가게 수
            sort_type: 정렬 방식 ('기본순', '주문 많은 순', '별점 높은 순', '가까운 순', '찜 많은 순')
        """
        print('=' * 60)
        print('  배달의민족 크롤러')
        print(f'  정렬: {sort_type}')
        print('=' * 60)
        print()

        if not self.connect():
            return

        # 메인화면에서 가게 목록으로 이동
        if not self.go_to_store_list():
            print('[ERROR] 가게 목록으로 이동 실패')
            return

        # 정렬 옵션 선택 (기본순이 아닐 경우)
        if sort_type != '기본순':
            print(f'[STEP 3] 정렬 변경: {sort_type}')
            if not self.click_sort_option(sort_type):
                print('[WARN] 정렬 변경 실패, 기본순으로 진행')
            time.sleep(1)

        skip_names = []  # 스킵할 가게명 목록 (방문한 가게 + 방금본가게 광고)
        collected_count = 0
        retry_count = 0
        max_retry = 10

        while collected_count < max_stores and retry_count < max_retry:
            # 현재 화면에서 모든 가게 찾기
            all_stores = self.get_stores_below_기본순(passed_기본순=collected_count > 0)

            # 스킵 목록에 없는 가게만 필터링
            available_stores = [s for s in all_stores if s['name'] not in skip_names]

            if available_stores:
                new_store = available_stores[0]
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
                    skip_names.append(new_store['name'])  # 방문한 가게 스킵 목록에 추가
                    print(f'      [완료] 상호명: {store_data.get("상호명", "")}')

                    # 뒤로가기 직후: 먼저 방금 방문한 가게를 화면에서 찾기 (위로 스크롤)
                    time.sleep(0.5)

                    # 1단계: 방금 방문한 가게가 화면에 보이는지 확인, 없으면 위로 스크롤
                    for scroll_up_try in range(5):
                        elem_check = self.d(descriptionContains=new_store['name'])
                        if elem_check.exists(timeout=1):
                            break
                        else:
                            # 위로 스크롤
                            self.d.swipe(540, 800, 540, 1500, duration=0.3)
                            time.sleep(0.5)

                    # 2단계: 스크롤해서 "방금 본 가게와 비슷해요!" 찾기
                    방금본_found = False
                    for scroll_try in range(5):
                        # "방금 본 가게" 있는지 확인
                        root = self.get_xml_root()
                        def check_방금본가게(node):
                            desc = node.attrib.get('content-desc', '')
                            if '방금 본 가게' in desc:
                                return True
                            for child in node:
                                if check_방금본가게(child):
                                    return True
                            return False

                        if check_방금본가게(root):
                            방금본_found = True
                            print(f'      [발견] "방금 본 가게와 비슷해요!"')
                            break
                        else:
                            self.scroll_down(1)

                    # 4개 매장 스킵 목록에 추가 (4개 찾을 때까지 스크롤)
                    if 방금본_found:
                        방금본_stores = []
                        방금본_stores = self.get_방금본가게_아래_4개()
                        print(f'      [DEBUG] 첫 시도: {len(방금본_stores)}개 발견 - {방금본_stores}')
                        if len(방금본_stores) < 4:
                            self.d.swipe(540, 1200, 540, 900, duration=0.2)  # 짧은 스크롤
                            time.sleep(0.3)
                            방금본_stores = self.get_방금본가게_아래_4개()
                            print(f'      [DEBUG] 스크롤 후: {len(방금본_stores)}개 발견 - {방금본_stores}')
                        for s in 방금본_stores:
                            if s not in skip_names:
                                skip_names.append(s)
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
    print('=' * 60)
    print('  배달의민족 크롤러')
    print('=' * 60)
    print()

    # 정렬 옵션 선택
    print('정렬 방식을 선택하세요:')
    print('  1. 기본순')
    print('  2. 주문 많은 순')
    print('  3. 별점 높은 순')
    print('  4. 가까운 순')
    print('  5. 찜 많은 순')
    print()

    sort_options = {
        '1': '기본순',
        '2': '주문 많은 순',
        '3': '별점 높은 순',
        '4': '가까운 순',
        '5': '찜 많은 순'
    }

    choice = input('번호 입력 (기본값: 1): ').strip() or '1'
    sort_type = sort_options.get(choice, '기본순')
    print(f'→ 선택: {sort_type}')
    print()

    # 크롤링 개수 입력
    max_input = input('크롤링할 가게 수 (기본값: 10): ').strip() or '10'
    max_stores = int(max_input)
    print(f'→ {max_stores}개 가게 크롤링')
    print()

    crawler = BaeminCrawler()
    crawler.run(max_stores=max_stores, sort_type=sort_type)
