# -*- coding: utf-8 -*-
"""
배달의민족 크롤러 - 버전2 (엑셀 기반 검색)
엑셀 파일의 상호명(F열)으로 배민에서 검색하여 정보 수집
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
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading


class BaeminCrawlerV2:
    def __init__(self, log_callback=None):
        self.d = None
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
        """최근주문수, 전체리뷰수 추출"""
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

    def search_store(self, store_name):
        """배민에서 가게 검색"""
        # 검색 버튼 클릭
        search_btn = self.d(descriptionContains='검색')
        if search_btn.exists(timeout=3):
            search_btn.click()
            time.sleep(1.5)
        else:
            self.log('[WARN] 검색 버튼 못 찾음')
            return False

        # 검색어 입력
        search_input = self.d(className='android.widget.EditText')
        if search_input.exists(timeout=3):
            search_input.set_text(store_name)
            time.sleep(0.5)
            # 검색 실행 (엔터)
            self.d.press('enter')
            time.sleep(2)
            return True
        else:
            self.log('[WARN] 검색창 못 찾음')
            self.go_back()
            return False

    def click_first_store(self, search_name):
        """검색 결과에서 첫 번째 가게 클릭"""
        time.sleep(1)

        # 검색 결과에서 가게 찾기 (content-desc에 배달팁 또는 준비중 포함된 것)
        root = self.get_xml_root()

        stores = []
        def find_stores(node):
            desc = node.attrib.get('content-desc', '')
            bounds = node.attrib.get('bounds', '')
            # 배달팁 또는 준비중이 있으면 가게로 인식
            if desc.strip() and bounds and ('배달팁' in desc or '준비중' in desc):
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    y1 = int(match.group(2))
                    # 가게명 추출 (배달팁, 준비중 앞부분)
                    store_name = desc
                    if ', 배달팁' in desc:
                        store_name = desc.split(', 배달팁')[0]
                    elif ', 준비중' in desc:
                        store_name = desc.split(', 준비중')[0]
                    stores.append({'name': store_name, 'y': y1, 'desc': desc})
            for child in node:
                find_stores(child)
        find_stores(root)

        if stores:
            stores.sort(key=lambda x: x['y'])
            first_store = stores[0]
            # 전체 desc로 클릭 (준비중 포함되어도 찾을 수 있게)
            elem = self.d(descriptionContains=first_store['desc'][:30])
            if elem.exists(timeout=2):
                elem.click()
                self.log(f'      [OK] 가게 클릭: {first_store["name"]}')
                time.sleep(2)
                return True

        self.log('[WARN] 검색 결과에서 가게 못 찾음')
        return False

    def crawl_store_info(self):
        """현재 가게 페이지에서 정보 추출"""
        store_data = {
            '배달타입': '',
            '상호명': '',
            '주소': '',
            '전화번호': '',
            '최근주문수': '',
            '전체리뷰수': '',
            '크롤링시간': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        try:
            # 1. 배달타입 펼치기
            self.log(f'      [1] 배달타입 펼치기...')
            self.click_expand_delivery()
            time.sleep(1)

            # 2. 배달타입 추출
            self.log(f'      [2] 배달타입 추출...')
            delivery_types = self.extract_delivery_types()
            store_data['배달타입'] = ', '.join(delivery_types)
            self.log(f'          → {store_data["배달타입"]}')

            # 3. 가게정보·원산지 클릭
            self.log(f'      [3] 가게정보·원산지 클릭...')
            if self.find_and_click_image('templates/store_info_btn.png', threshold=0.6):
                time.sleep(2)

                # 4. 상호명, 주소, 전화번호 추출
                self.log(f'      [4] 가게정보 추출...')
                info = self.extract_store_info()
                store_data.update(info)
                self.log(f'          → 상호명: {info.get("상호명", "없음")}')

                # 5. 최근주문수, 전체리뷰수 추출
                self.log(f'      [5] 통계 추출...')
                for _ in range(5):
                    if self.d(textContains='최근 주문수').exists(timeout=1) and self.d(textContains='전체 리뷰수').exists(timeout=1):
                        break
                    self.scroll_down(1)
                stats = self.extract_stats()
                store_data.update(stats)
                self.log(f'          → 최근주문수: {stats.get("최근주문수", "없음")}')
                self.log(f'          → 전체리뷰수: {stats.get("전체리뷰수", "없음")}')

                # 뒤로가기 (가게정보 → 가게상세)
                self.go_back()

        except Exception as e:
            self.log(f'      [ERROR] {e}')

        # 뒤로가기 (가게상세 → 검색결과)
        self.go_back()
        time.sleep(1)
        # 뒤로가기 (검색결과 → 메인)
        self.go_back()
        time.sleep(1)

        return store_data

    def go_to_main(self):
        """배민 메인 화면으로 이동"""
        # 홈 버튼 여러번 눌러서 메인으로
        for _ in range(3):
            home_btn = self.d(descriptionContains='홈')
            if home_btn.exists(timeout=1):
                home_btn.click()
                time.sleep(1)
                break
            self.go_back()

    def run(self, excel_path, progress_callback=None):
        """크롤링 실행"""
        self.is_running = True
        self.should_stop = False

        self.log('=' * 50)
        self.log('  배달의민족 크롤러 V2 시작')
        self.log(f'  엑셀 파일: {excel_path}')
        self.log('=' * 50)

        # 엑셀 파일 읽기
        try:
            df = pd.read_excel(excel_path)
            self.log(f'[OK] 엑셀 로드 완료: {len(df)}개 행')
        except Exception as e:
            self.log(f'[ERROR] 엑셀 로드 실패: {e}')
            self.is_running = False
            return None

        # F열(상호명) 확인 - 0-indexed로 5번째
        if df.shape[1] < 6:
            self.log('[ERROR] 엑셀에 F열(상호명)이 없습니다')
            self.is_running = False
            return None

        # 컬럼명 확인
        col_names = df.columns.tolist()
        self.log(f'[INFO] 컬럼: {col_names}')

        # 상호명 컬럼 (F열 = index 5)
        store_col = col_names[5] if len(col_names) > 5 else None
        if not store_col:
            self.log('[ERROR] 상호명 컬럼을 찾을 수 없습니다')
            self.is_running = False
            return None

        self.log(f'[INFO] 상호명 컬럼: {store_col}')

        # I열부터 새 컬럼 추가 (없으면)
        new_cols = ['배달타입_배민', '상호명_배민', '주소_배민', '전화번호_배민', '최근주문수', '전체리뷰수', '크롤링시간']
        for col in new_cols:
            if col not in df.columns:
                df[col] = ''

        if not self.connect():
            self.is_running = False
            return None

        total = len(df)
        for idx, row in df.iterrows():
            if self.should_stop:
                self.log('[중지] 사용자 요청으로 중지됨')
                break

            store_name = str(row[store_col]).strip()
            if not store_name or store_name == 'nan':
                continue

            self.log(f'\n[{idx+1}/{total}] 검색: {store_name}')

            if progress_callback:
                progress_callback(idx + 1, total)

            # 메인화면으로
            self.go_to_main()
            time.sleep(1)

            # 검색
            if self.search_store(store_name):
                # 첫 번째 가게 클릭
                if self.click_first_store(store_name):
                    # 정보 추출
                    data = self.crawl_store_info()

                    # 엑셀에 저장
                    df.at[idx, '배달타입_배민'] = data.get('배달타입', '')
                    df.at[idx, '상호명_배민'] = data.get('상호명', '')
                    df.at[idx, '주소_배민'] = data.get('주소', '')
                    df.at[idx, '전화번호_배민'] = data.get('전화번호', '')
                    df.at[idx, '최근주문수'] = data.get('최근주문수', '')
                    df.at[idx, '전체리뷰수'] = data.get('전체리뷰수', '')
                    df.at[idx, '크롤링시간'] = data.get('크롤링시간', '')

                    self.log(f'      [완료] 상호명: {data.get("상호명", "")}')
                else:
                    self.log(f'      [SKIP] 가게 못 찾음')
                    self.go_back()
                    time.sleep(0.5)
                    self.go_back()
            else:
                self.log(f'      [SKIP] 검색 실패')

            time.sleep(1)

        # 엑셀 저장
        output_path = excel_path.replace('.xlsx', '_결과.xlsx')
        df.to_excel(output_path, index=False)
        self.log(f'\n[OK] 결과 저장: {output_path}')

        self.log('')
        self.log('=' * 50)
        self.log('  크롤링 완료!')
        self.log('=' * 50)

        self.is_running = False
        return output_path


class BaeminCrawlerV2GUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('배달의민족 크롤러 V2 - 엑셀 검색')
        self.root.geometry('700x750')
        self.root.resizable(True, True)

        self.crawler = None
        self.crawl_thread = None
        self.excel_path = None

        self.setup_ui()

    def setup_ui(self):
        """UI 구성"""
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 제목
        title_label = ttk.Label(main_frame, text='배달의민족 크롤러 V2', font=('맑은 고딕', 16, 'bold'))
        title_label.pack(pady=(0, 5))

        subtitle_label = ttk.Label(main_frame, text='엑셀 상호명으로 검색하여 정보 수집', font=('맑은 고딕', 10))
        subtitle_label.pack(pady=(0, 15))

        # 엑셀 파일 선택 프레임
        file_frame = ttk.LabelFrame(main_frame, text='엑셀 파일', padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        self.file_var = tk.StringVar(value='파일을 선택하세요...')
        file_entry = ttk.Entry(file_frame, textvariable=self.file_var, state='readonly')
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        file_btn = ttk.Button(file_frame, text='파일 선택', command=self.select_file)
        file_btn.pack(side=tk.RIGHT)

        # 안내 프레임
        info_frame = ttk.LabelFrame(main_frame, text='안내', padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        info_text = """• 엑셀 파일의 F열(상호명)을 기준으로 배민에서 검색합니다
• I열부터 배달타입, 상호명, 주소, 전화번호, 최근주문수, 전체리뷰수가 추가됩니다
• 결과는 원본파일명_결과.xlsx로 저장됩니다
• 배민 앱이 메인화면에 있어야 합니다"""

        info_label = ttk.Label(info_frame, text=info_text, font=('맑은 고딕', 9), justify=tk.LEFT)
        info_label.pack(anchor=tk.W)

        # 진행 상태 프레임
        progress_frame = ttk.LabelFrame(main_frame, text='진행 상태', padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)

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

    def select_file(self):
        """엑셀 파일 선택"""
        file_path = filedialog.askopenfilename(
            title='엑셀 파일 선택',
            filetypes=[('Excel files', '*.xlsx *.xls'), ('All files', '*.*')]
        )
        if file_path:
            self.excel_path = file_path
            self.file_var.set(file_path)

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
        if not self.excel_path:
            messagebox.showerror('오류', '엑셀 파일을 선택하세요.')
            return

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.progress_var.set(0)
        self.status_var.set('크롤링 시작...')

        self.crawler = BaeminCrawlerV2(log_callback=self.log)

        def crawl_task():
            try:
                result_path = self.crawler.run(
                    excel_path=self.excel_path,
                    progress_callback=self.update_progress
                )
                self.root.after(0, lambda: self.crawl_complete(result_path))
            except Exception as e:
                self.root.after(0, lambda: self.log(f'[ERROR] {e}'))
                self.root.after(0, lambda: self.crawl_complete(None))

        self.crawl_thread = threading.Thread(target=crawl_task, daemon=True)
        self.crawl_thread.start()

    def stop_crawl(self):
        """크롤링 중지"""
        if self.crawler:
            self.crawler.should_stop = True
            self.status_var.set('중지 중...')

    def crawl_complete(self, result_path):
        """크롤링 완료"""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        if result_path:
            self.status_var.set(f'완료! 저장: {result_path}')
            messagebox.showinfo('완료', f'크롤링 완료!\n\n결과 파일: {result_path}')
        else:
            self.status_var.set('완료')

    def run(self):
        """GUI 실행"""
        self.root.mainloop()


if __name__ == '__main__':
    app = BaeminCrawlerV2GUI()
    app.run()
