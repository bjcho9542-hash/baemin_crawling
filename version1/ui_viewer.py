# -*- coding: utf-8 -*-
"""
UI 뷰어 - 현재 화면의 모든 content-desc와 text 실시간 확인
"""
import uiautomator2 as u2
import xml.etree.ElementTree as ET
import re
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
os.system('cls' if os.name == 'nt' else 'clear')

d = u2.connect()
print('=' * 60)
print('  UI 뷰어 - 현재 화면 요소 확인')
print('=' * 60)
print()

xml = d.dump_hierarchy()
root = ET.fromstring(xml)

print('[content-desc 목록]')
print('-' * 60)
def find_desc(node):
    desc = node.attrib.get('content-desc', '')
    bounds = node.attrib.get('bounds', '')
    clickable = node.attrib.get('clickable', '')
    if desc.strip():
        click_mark = ' [클릭가능]' if clickable == 'true' else ''
        print(f'{bounds}{click_mark}')
        print(f'  → {desc[:70]}')
        print()
    for child in node:
        find_desc(child)

find_desc(root)

print()
print('[text 목록]')
print('-' * 60)
def find_text(node):
    text = node.attrib.get('text', '')
    bounds = node.attrib.get('bounds', '')
    clickable = node.attrib.get('clickable', '')
    if text.strip():
        click_mark = ' [클릭가능]' if clickable == 'true' else ''
        print(f'{bounds}{click_mark}')
        print(f'  → {text[:70]}')
        print()
    for child in node:
        find_text(child)

find_text(root)

print('=' * 60)
print('다시 확인하려면 이 스크립트를 다시 실행하세요')
print('=' * 60)
