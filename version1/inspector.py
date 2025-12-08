# -*- coding: utf-8 -*-
"""
UI Inspector - 클릭으로 요소 정보 확인
브라우저에서 화면 클릭하면 content-desc, text, bounds 등 표시
"""
import uiautomator2 as u2
import xml.etree.ElementTree as ET
import re
import http.server
import socketserver
import webbrowser
import base64
import json
import sys
import os
from io import BytesIO

PORT = 8888

class InspectorHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path == '/screenshot':
            self.send_screenshot()
        elif self.path == '/hierarchy':
            self.send_hierarchy()
        else:
            self.send_error(404)

    def send_screenshot(self):
        try:
            d = u2.connect()
            img = d.screenshot()
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_data = base64.b64encode(buffer.getvalue()).decode()

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'image': img_data}).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def send_hierarchy(self):
        try:
            d = u2.connect()
            xml_str = d.dump_hierarchy()
            root = ET.fromstring(xml_str)

            elements = []
            def parse(node):
                bounds = node.attrib.get('bounds', '')
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    elem = {
                        'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                        'content_desc': node.attrib.get('content-desc', ''),
                        'text': node.attrib.get('text', ''),
                        'class': node.attrib.get('class', '').split('.')[-1],
                        'clickable': node.attrib.get('clickable', 'false'),
                        'resource_id': node.attrib.get('resource-id', '')
                    }
                    if elem['content_desc'] or elem['text'] or elem['clickable'] == 'true':
                        elements.append(elem)
                for child in node:
                    parse(child)

            parse(root)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(elements).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        pass  # 로그 숨기기

HTML_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>UI Inspector</title>
    <style>
        body { margin: 0; padding: 20px; font-family: 'Malgun Gothic', sans-serif; background: #1e1e1e; color: #fff; }
        h1 { color: #4fc3f7; margin-bottom: 10px; }
        .container { display: flex; gap: 20px; }
        .screen-wrap { position: relative; border: 2px solid #333; }
        #screenshot { max-height: 800px; cursor: crosshair; }
        #coords { position: fixed; top: 10px; right: 10px; background: #ff5722; color: #fff; padding: 10px 15px; border-radius: 4px; font-size: 16px; font-weight: bold; z-index: 1000; }
        .highlight { position: absolute; border: 2px solid #ff5722; background: rgba(255,87,34,0.2); pointer-events: none; }
        .info-panel { width: 500px; background: #2d2d2d; padding: 15px; border-radius: 8px; }
        .info-panel h3 { color: #4fc3f7; margin-top: 0; }
        .info-item { margin: 10px 0; padding: 10px; background: #3d3d3d; border-radius: 4px; }
        .info-item label { color: #aaa; font-size: 12px; display: block; }
        .info-item .value { color: #fff; font-size: 14px; word-break: break-all; margin-top: 5px; }
        .info-item .value.highlight-text { color: #ffeb3b; font-weight: bold; }
        button { background: #4fc3f7; color: #000; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-size: 14px; margin-right: 10px; }
        button:hover { background: #29b6f6; }
        .copy-btn { background: #ff9800; font-size: 12px; padding: 5px 10px; margin-top: 5px; }
        #status { color: #aaa; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>UI Inspector</h1>
    <p id="status">로딩 중...</p>
    <button onclick="refresh()">새로고침 (F5)</button>
    <button onclick="copyCode()">선택된 요소 코드 복사</button>
    <div class="container">
        <div id="coords">X: 0, Y: 0</div>
        <div class="screen-wrap" id="screen-wrap">
            <img id="screenshot" onclick="handleClick(event)" onmousemove="showCoords(event)">
            <div class="highlight" id="highlight"></div>
        </div>
        <div class="info-panel">
            <h3>선택된 요소 정보</h3>
            <div class="info-item">
                <label>content-desc</label>
                <div class="value highlight-text" id="info-desc">-</div>
            </div>
            <div class="info-item">
                <label>text</label>
                <div class="value highlight-text" id="info-text">-</div>
            </div>
            <div class="info-item">
                <label>bounds</label>
                <div class="value" id="info-bounds">-</div>
            </div>
            <div class="info-item">
                <label>class</label>
                <div class="value" id="info-class">-</div>
            </div>
            <div class="info-item">
                <label>clickable</label>
                <div class="value" id="info-clickable">-</div>
            </div>
            <div class="info-item">
                <label>resource-id</label>
                <div class="value" id="info-resid">-</div>
            </div>
            <div class="info-item">
                <label>Python 코드</label>
                <div class="value" id="info-code" style="font-family: monospace; color: #4fc3f7;">-</div>
                <button class="copy-btn" onclick="copyCode()">복사</button>
            </div>
        </div>
    </div>
    <script>
        let elements = [];
        let selectedElem = null;
        let scale = 1;

        async function refresh() {
            document.getElementById('status').textContent = '로딩 중...';
            try {
                const [imgRes, hierRes] = await Promise.all([
                    fetch('/screenshot'),
                    fetch('/hierarchy')
                ]);
                const imgData = await imgRes.json();
                elements = await hierRes.json();

                const img = document.getElementById('screenshot');
                img.src = 'data:image/png;base64,' + imgData.image;
                img.onload = () => {
                    scale = img.naturalWidth / img.clientWidth;
                    document.getElementById('status').textContent = `로드 완료! 요소 ${elements.length}개 (클릭하여 확인)`;
                };
            } catch(e) {
                document.getElementById('status').textContent = '오류: ' + e;
            }
        }

        function handleClick(e) {
            const img = document.getElementById('screenshot');
            const rect = img.getBoundingClientRect();
            const x = (e.clientX - rect.left) * scale;
            const y = (e.clientY - rect.top) * scale;

            // 가장 작은 영역 찾기 (클릭 위치 포함)
            let best = null;
            let bestArea = Infinity;
            for (const elem of elements) {
                if (x >= elem.x1 && x <= elem.x2 && y >= elem.y1 && y <= elem.y2) {
                    const area = (elem.x2 - elem.x1) * (elem.y2 - elem.y1);
                    if (area < bestArea) {
                        bestArea = area;
                        best = elem;
                    }
                }
            }

            if (best) {
                selectedElem = best;
                showInfo(best);
                showHighlight(best);
            }
        }

        function showInfo(elem) {
            document.getElementById('info-desc').textContent = elem.content_desc || '-';
            document.getElementById('info-text').textContent = elem.text || '-';
            document.getElementById('info-bounds').textContent = `[${elem.x1},${elem.y1}][${elem.x2},${elem.y2}]`;
            document.getElementById('info-class').textContent = elem.class || '-';
            document.getElementById('info-clickable').textContent = elem.clickable;
            document.getElementById('info-resid').textContent = elem.resource_id || '-';

            // Python 코드 생성
            let code = '';
            if (elem.content_desc) {
                code = `d(descriptionContains='${elem.content_desc.substring(0,30)}')`;
            } else if (elem.text) {
                code = `d(textContains='${elem.text.substring(0,30)}')`;
            } else if (elem.resource_id) {
                code = `d(resourceId='${elem.resource_id}')`;
            } else {
                code = `d.click(${Math.round((elem.x1+elem.x2)/2)}, ${Math.round((elem.y1+elem.y2)/2)})`;
            }
            document.getElementById('info-code').textContent = code;
        }

        function showHighlight(elem) {
            const img = document.getElementById('screenshot');
            const hl = document.getElementById('highlight');
            hl.style.left = (elem.x1 / scale) + 'px';
            hl.style.top = (elem.y1 / scale) + 'px';
            hl.style.width = ((elem.x2 - elem.x1) / scale) + 'px';
            hl.style.height = ((elem.y2 - elem.y1) / scale) + 'px';
            hl.style.display = 'block';
        }

        function copyCode() {
            const code = document.getElementById('info-code').textContent;
            if (code && code !== '-') {
                navigator.clipboard.writeText(code);
                alert('복사됨: ' + code);
            }
        }

        function showCoords(e) {
            const img = document.getElementById('screenshot');
            const rect = img.getBoundingClientRect();
            const x = Math.round((e.clientX - rect.left) * scale);
            const y = Math.round((e.clientY - rect.top) * scale);
            document.getElementById('coords').textContent = 'X: ' + x + ', Y: ' + y;
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'F5') {
                e.preventDefault();
                refresh();
            }
        });

        refresh();
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print('=' * 50)
    print('  UI Inspector 시작')
    print('=' * 50)
    print()
    print(f'브라우저에서 http://localhost:{PORT} 열기...')
    print()
    print('- 화면 클릭: 해당 요소 정보 표시')
    print('- F5: 새로고침')
    print('- Ctrl+C: 종료')
    print()

    webbrowser.open(f'http://localhost:{PORT}')

    with socketserver.TCPServer(("", PORT), InspectorHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n종료')
