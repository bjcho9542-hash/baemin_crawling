# -*- coding: utf-8 -*-
"""
이미지 템플릿 매칭으로 버튼 찾아서 클릭
"""
import uiautomator2 as u2
import cv2
import numpy as np
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def find_and_click(template_path, threshold=0.8):
    """
    화면에서 템플릿 이미지를 찾아서 클릭

    Args:
        template_path: 찾을 이미지 파일 경로
        threshold: 매칭 정확도 (0~1, 기본 0.8)

    Returns:
        (x, y) 클릭한 좌표 또는 None
    """
    d = u2.connect()

    # 현재 화면 캡처
    screen = d.screenshot(format='opencv')

    # 템플릿 이미지 로드
    template = cv2.imread(template_path)
    if template is None:
        print(f'[ERROR] 템플릿 이미지 없음: {template_path}')
        return None

    # 그레이스케일 변환
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    # 템플릿 매칭
    result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    print(f'[INFO] 매칭 정확도: {max_val:.2%}')

    if max_val >= threshold:
        # 템플릿 중심 좌표 계산
        h, w = template_gray.shape
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2

        print(f'[OK] 발견! 위치: ({center_x}, {center_y})')

        # 클릭
        d.click(center_x, center_y)
        print(f'[OK] 클릭 완료!')

        return (center_x, center_y)
    else:
        print(f'[WARN] 못 찾음 (정확도 {max_val:.2%} < {threshold:.0%})')
        return None


def capture_template(save_path, x1, y1, x2, y2):
    """
    화면의 특정 영역을 템플릿으로 저장

    Args:
        save_path: 저장할 파일 경로
        x1, y1, x2, y2: 영역 좌표
    """
    d = u2.connect()
    screen = d.screenshot(format='opencv')

    # 영역 크롭
    template = screen[y1:y2, x1:x2]

    # 저장
    cv2.imwrite(save_path, template)
    print(f'[OK] 템플릿 저장: {save_path}')
    print(f'     크기: {x2-x1}x{y2-y1}')


def find_all(template_path, threshold=0.8):
    """
    화면에서 템플릿 이미지를 모두 찾기 (여러 개일 때)

    Returns:
        [(x, y), ...] 발견된 모든 위치
    """
    d = u2.connect()
    screen = d.screenshot(format='opencv')
    template = cv2.imread(template_path)

    if template is None:
        print(f'[ERROR] 템플릿 이미지 없음: {template_path}')
        return []

    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    h, w = template_gray.shape

    result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)

    points = []
    for pt in zip(*locations[::-1]):
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2
        # 중복 제거 (근접한 점들)
        is_dup = False
        for px, py in points:
            if abs(px - center_x) < 20 and abs(py - center_y) < 20:
                is_dup = True
                break
        if not is_dup:
            points.append((center_x, center_y))

    print(f'[INFO] {len(points)}개 발견')
    for i, (x, y) in enumerate(points):
        print(f'  {i+1}. ({x}, {y})')

    return points


if __name__ == '__main__':
    print('=' * 50)
    print('  이미지 템플릿 매칭 테스트')
    print('=' * 50)
    print()
    print('사용법:')
    print('  1. capture_template("btn.png", x1, y1, x2, y2) - 버튼 이미지 저장')
    print('  2. find_and_click("btn.png") - 이미지 찾아서 클릭')
    print()
