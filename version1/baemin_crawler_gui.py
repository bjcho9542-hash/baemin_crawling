# -*- coding: utf-8 -*-
"""
배달의민족 크롤러 - GUI 버전
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
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading


class BaeminCrawler:
    def __init__(self, log_callback=None):
        self.d = None
        self.stores = []
        self.log_callback = log_callback
        self.is_running = False
        self.should_stop = False

    def log(self, msg):
        """로그 출력"""
        if self.log_callback:
            self.log_callback(msg)
        print(msg)

    def connect(self):
        """디바이스 연결"""
        self.d = u2.connect()
        self.log('[OK] 디바이스 연결됨')
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
            self.log(f'[ERROR] 템플릿 없음: {template_path}')
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
            self.log(f'      [이미지매칭] 클릭 ({cx}, {cy}) - {max_val:.0%}')
            return True
        else:
            self.log(f'      [WARN] 이미지 못 찾음 - {max_val:.0%}')
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
        """정렬 옵션 선택"""
        sort_btn = self.d(textContains='기본순')
        if sort_btn.exists(timeout=3):
            info = sort_btn.info
            bounds = info.get('bounds', {})
            x = (bounds.get('left', 0) + bounds.get('right', 0)) // 2
            y = bounds.get('top', 0) - 130
            self.d.click(x, y)
            self.log(f'      [OK] 정렬 버튼 클릭 ({x}, {y})')
            time.sleep(1)
        else:
            self.log(f'      [WARN] 정렬 버튼 못 찾음')
            return False

        sort_elem = self.d(descriptionContains=sort_type)
        if sort_elem.exists(timeout=3):
            sort_elem.click()
            self.log(f'      [OK] 정렬 선택: {sort_type}')
            time.sleep(1)
            return True
        else:
            self.log(f'      [WARN] 정렬 옵션 못 찾음: {sort_type}')
            self.d.press('back')
            return False

    def get_stores_below_기본순(self, passed_기본순=False, last_store_name=None):
        """기본순 아래에 있는 가게 이름들 추출"""
        root = self.get_xml_root()

        기본순_y = None
        def find_기본순(node):
            nonlocal 기본순_y
            text = node.attrib.get('text', '')
            bounds = node.attrib.get('bounds', '')
            if text == '기본순' or text.startswith('기본순 외'):
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    기본순_y = int(match.group(4))
            for child in node:
                find_기본순(child)
        find_기본순(root)

        if 기본순_y is None:
            if passed_기본순:
                기본순_y = 0
            else:
                return []

        last_store_y = None
        if last_store_name:
            def find_last_store(node):
                nonlocal last_store_y
                desc = node.attrib.get('content-desc', '')
                bounds = node.attrib.get('bounds', '')
                if last_store_name in desc and bounds:
                    match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        last_store_y = int(match.group(4))
                for child in node:
                    find_last_store(child)
            find_last_store(root)

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

        stores = []
        def find_stores(node):
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')

            if desc.strip() and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    y1 = int(match.group(2))
                    if y1 > 기본순_y:
                        store_name = desc
                        if ', 배달팁' in desc:
                            store_name = desc.split(', 배달팁')[0]

                        exclude = (
                            store_name in ['가게배달', '알뜰배달', '한집배달', '음식배달'] or
                            '음식' in store_name or
                            'km' in store_name or
                            '원,' in store_name or
                            '원)' in store_name or
                            '거리' in store_name or
                            '별점' in store_name or
                            re.match(r'^\d+개$', store_name) or
                            re.match(r'^[\d.,]+개$', store_name) or
                            re.match(r'^[\d.]+$', store_name) or
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
                            '번째' in store_name or
                            '총' in store_name or
                            '방금' in store_name or
                            '비슷' in store_name or
                            '최소' in store_name or
                            '최대' in store_name or
                            '메뉴' in store_name or
                            '전체' in store_name or
                            store_name.startswith(',') or
                            store_name.startswith('.') or
                            store_name.replace('.', '').replace(',', '').isdigit()
                        )
                        if not exclude and 2 <= len(store_name) <= 30:
                            stores.append({'name': store_name, 'y': y1})
            for child in node:
                find_stores(child)
        find_stores(root)

        stores.sort(key=lambda x: x['y'])

        unique = []
        for s in stores:
            is_dup = False
            for u in unique:
                if abs(u['y'] - s['y']) < 50:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(s)

        if last_store_y and 방금본가게_y:
            skip_count = 0
            filtered = []
            for s in unique:
                if s['y'] > last_store_y:
                    if s['y'] > 방금본가게_y:
                        skip_count += 1
                        if skip_count <= 4:
                            continue
                    filtered.append(s)
            return filtered
        elif 방금본가게_y:
            skip_count = 0
            filtered = []
            for s in unique:
                if s['y'] > 방금본가게_y:
                    skip_count += 1
                    if skip_count <= 4:
                        continue
                filtered.append(s)
            return filtered

        return unique

    def get_방금본가게_아래_4개(self):
        """'방금 본 가게와 비슷해요!' 아래 4개 매장 이름 반환"""
        root = self.get_xml_root()

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

        stores = []
        def find_stores(node):
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')
            if desc.strip() and bounds:
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    y1 = int(match.group(2))
                    if y1 > 방금본가게_y:
                        store_name = desc
                        if ', 배달팁' in desc:
                            store_name = desc.split(', 배달팁')[0]

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

        stores.sort(key=lambda x: x['y'])
        return [s['name'] for s in stores[:4]]

    def crawl_single_store(self, store_index):
        """단일 가게 크롤링"""
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
            self.log(f'      [1] 배달타입 펼치기...')
            self.click_expand_delivery()
            time.sleep(1)

            self.log(f'      [2] 배달타입 추출...')
            delivery_types = self.extract_delivery_types()
            store_data['배달타입'] = ', '.join(delivery_types)
            self.log(f'          → {store_data["배달타입"]}')

            self.log(f'      [3] 가게정보·원산지 클릭...')
            if self.find_and_click_image('templates/store_info_btn.png', threshold=0.6):
                time.sleep(2)

                self.log(f'      [4] 가게정보 추출...')
                info = self.extract_store_info()
                store_data.update(info)
                self.log(f'          → 상호명: {info.get("상호명", "없음")}')

                self.log(f'      [5] 통계 추출...')
                for _ in range(5):
                    if self.d(textContains='최근 주문수').exists(timeout=1) and self.d(textContains='전체 리뷰수').exists(timeout=1):
                        break
                    self.scroll_down(1)
                stats = self.extract_stats()
                store_data.update(stats)
                self.log(f'          → 최근주문수: {stats.get("최근주문수", "없음")}')
                self.log(f'          → 전체리뷰수: {stats.get("전체리뷰수", "없음")}')

                self.go_back()

        except Exception as e:
            self.log(f'      [ERROR] {e}')

        self.go_back()

        return store_data

    def save_to_excel(self, filename=None):
        """엑셀 저장"""
        if not self.stores:
            self.log('[WARN] 저장할 데이터 없음')
            return None

        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'baemin_stores_{timestamp}.xlsx'

        df = pd.DataFrame(self.stores)
        df.to_excel(filename, index=False)
        self.log(f'[OK] 엑셀 저장 완료: {filename}')
        self.log(f'     총 {len(self.stores)}개 가게')
        return filename

    def go_to_store_list(self):
        """메인화면에서 음식배달 더보기 클릭"""
        self.log('[STEP 1] 음식배달에서 더보기 클릭')
        elem = self.d(descriptionContains='음식배달에서 더보기')
        if elem.exists(timeout=3):
            elem.click()
            time.sleep(2)
            self.log('      [OK] 더보기 클릭 완료')
        else:
            self.log('      [WARN] 더보기 버튼 못 찾음')
            return False

        self.log('[STEP 2] 기본순 아래 가게목록 찾기')
        for i in range(10):
            stores = self.get_stores_below_기본순()
            if stores:
                self.log(f'      [OK] 기본순 아래 가게 {len(stores)}개 발견! (스크롤 {i}회)')
                for j, s in enumerate(stores[:3]):
                    self.log(f'          {j+1}. {s["name"]}')
                return True

            self.scroll_down(1)
            self.log(f'      스크롤 {i+1}회...')

        self.log('      [WARN] 기본순 아래 가게 못 찾음')
        return False

    def run(self, max_stores=5, sort_type='기본순', progress_callback=None):
        """크롤링 실행"""
        self.is_running = True
        self.should_stop = False
        self.stores = []

        self.log('=' * 50)
        self.log('  배달의민족 크롤러 시작')
        self.log(f'  정렬: {sort_type}')
        self.log(f'  목표: {max_stores}개')
        self.log('=' * 50)

        if not self.connect():
            self.is_running = False
            return

        if not self.go_to_store_list():
            self.log('[ERROR] 가게 목록으로 이동 실패')
            self.is_running = False
            return

        if sort_type != '기본순':
            self.log(f'[STEP 3] 정렬 변경: {sort_type}')
            if not self.click_sort_option(sort_type):
                self.log('[WARN] 정렬 변경 실패, 기본순으로 진행')
            time.sleep(1)

        skip_names = []
        collected_count = 0
        retry_count = 0
        max_retry = 10

        while collected_count < max_stores and retry_count < max_retry:
            if self.should_stop:
                self.log('[중지] 사용자 요청으로 중지됨')
                break

            all_stores = self.get_stores_below_기본순(passed_기본순=collected_count > 0)
            available_stores = [s for s in all_stores if s['name'] not in skip_names]

            if available_stores:
                new_store = available_stores[0]
                collected_count += 1

                if progress_callback:
                    progress_callback(collected_count, max_stores)

                self.log(f'\n[{collected_count}/{max_stores}] {new_store["name"]}')

                elem = self.d(descriptionContains=new_store['name'])
                if elem.exists(timeout=3):
                    elem.click()
                    self.log(f'      [OK] 클릭')
                    time.sleep(2)

                    store_data = self.crawl_single_store(collected_count)
                    store_data['가게명'] = new_store['name']
                    self.stores.append(store_data)
                    skip_names.append(new_store['name'])
                    self.log(f'      [완료] 상호명: {store_data.get("상호명", "")}')

                    time.sleep(0.5)

                    for scroll_up_try in range(5):
                        elem_check = self.d(descriptionContains=new_store['name'])
                        if elem_check.exists(timeout=1):
                            break
                        else:
                            self.d.swipe(540, 800, 540, 1500, duration=0.3)
                            time.sleep(0.5)

                    방금본_found = False
                    for scroll_try in range(5):
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
                            self.log(f'      [발견] "방금 본 가게와 비슷해요!"')
                            break
                        else:
                            self.scroll_down(1)

                    if 방금본_found:
                        방금본_stores = self.get_방금본가게_아래_4개()
                        if len(방금본_stores) < 4:
                            self.d.swipe(540, 1200, 540, 900, duration=0.2)
                            time.sleep(0.3)
                            방금본_stores = self.get_방금본가게_아래_4개()
                        for s in 방금본_stores:
                            if s not in skip_names:
                                skip_names.append(s)
                                self.log(f'      [SKIP] 방금본가게 광고: {s}')
                else:
                    self.log(f'      [WARN] 클릭 실패')
                    collected_count -= 1

                retry_count = 0
                time.sleep(1)
            else:
                self.log(f'      스크롤... ({retry_count+1})')
                self.scroll_down(1)
                retry_count += 1
                time.sleep(1)

        filename = self.save_to_excel()

        self.log('')
        self.log('=' * 50)
        self.log('  크롤링 완료!')
        self.log('=' * 50)

        self.is_running = False
        return filename


class BaeminCrawlerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('배달의민족 크롤러')
        self.root.geometry('600x700')
        self.root.resizable(True, True)

        self.crawler = None
        self.crawl_thread = None

        self.setup_ui()

    def setup_ui(self):
        """UI 구성"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 제목
        title_label = ttk.Label(main_frame, text='배달의민족 크롤러', font=('맑은 고딕', 16, 'bold'))
        title_label.pack(pady=(0, 15))

        # 설정 프레임
        settings_frame = ttk.LabelFrame(main_frame, text='설정', padding=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # 정렬 옵션
        sort_frame = ttk.Frame(settings_frame)
        sort_frame.pack(fill=tk.X, pady=5)

        ttk.Label(sort_frame, text='정렬 방식:', font=('맑은 고딕', 10)).pack(side=tk.LEFT)

        self.sort_var = tk.StringVar(value='기본순')
        sort_options = ['기본순', '주문 많은 순', '별점 높은 순', '가까운 순', '찜 많은 순']

        for option in sort_options:
            ttk.Radiobutton(sort_frame, text=option, variable=self.sort_var, value=option).pack(side=tk.LEFT, padx=5)

        # 수집 개수
        count_frame = ttk.Frame(settings_frame)
        count_frame.pack(fill=tk.X, pady=5)

        ttk.Label(count_frame, text='수집 개수:', font=('맑은 고딕', 10)).pack(side=tk.LEFT)

        self.count_var = tk.StringVar(value='10')
        count_entry = ttk.Entry(count_frame, textvariable=self.count_var, width=10)
        count_entry.pack(side=tk.LEFT, padx=10)

        ttk.Label(count_frame, text='개', font=('맑은 고딕', 10)).pack(side=tk.LEFT)

        # 진행 상태 프레임
        progress_frame = ttk.LabelFrame(main_frame, text='진행 상태', padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        # 진행바
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)

        # 진행 상태 텍스트
        self.status_var = tk.StringVar(value='대기 중...')
        status_label = ttk.Label(progress_frame, textvariable=self.status_var, font=('맑은 고딕', 10))
        status_label.pack()

        # 버튼 프레임
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(btn_frame, text='시작', command=self.start_crawl, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text='중지', command=self.stop_crawl, width=15, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 로그 프레임
        log_frame = ttk.LabelFrame(main_frame, text='로그', padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        """로그 출력"""
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def update_progress(self, current, total):
        """진행 상태 업데이트"""
        percent = (current / total) * 100
        self.progress_var.set(percent)
        self.status_var.set(f'{current}/{total} 완료 ({percent:.0f}%)')
        self.root.update_idletasks()

    def start_crawl(self):
        """크롤링 시작"""
        try:
            max_stores = int(self.count_var.get())
        except ValueError:
            messagebox.showerror('오류', '수집 개수를 숫자로 입력하세요.')
            return

        if max_stores < 1:
            messagebox.showerror('오류', '수집 개수는 1 이상이어야 합니다.')
            return

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.progress_var.set(0)
        self.status_var.set('크롤링 시작...')

        sort_type = self.sort_var.get()

        self.crawler = BaeminCrawler(log_callback=self.log)

        def crawl_task():
            try:
                filename = self.crawler.run(
                    max_stores=max_stores,
                    sort_type=sort_type,
                    progress_callback=self.update_progress
                )

                self.root.after(0, lambda: self.crawl_complete(filename))
            except Exception as e:
                self.root.after(0, lambda: self.log(f'[ERROR] {e}'))
                self.root.after(0, self.crawl_complete)

        self.crawl_thread = threading.Thread(target=crawl_task, daemon=True)
        self.crawl_thread.start()

    def stop_crawl(self):
        """크롤링 중지"""
        if self.crawler:
            self.crawler.should_stop = True
            self.status_var.set('중지 중...')

    def crawl_complete(self, filename=None):
        """크롤링 완료"""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        if filename:
            self.status_var.set(f'완료! 저장: {filename}')
            messagebox.showinfo('완료', f'크롤링 완료!\n\n저장 파일: {filename}')
        else:
            self.status_var.set('완료')

    def run(self):
        """GUI 실행"""
        self.root.mainloop()


if __name__ == '__main__':
    app = BaeminCrawlerGUI()
    app.run()
