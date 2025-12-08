# 배달의민족 크롤링 프로젝트

## 프로젝트 컨텍스트
이 프로젝트는 배달의민족 앱에서 가게 정보를 크롤링합니다.
세션이 끊기면 `기존대화.txt`를 읽고 이어서 작업하세요.

## 기술 스택
- Python 3.13 + uiautomator2 3.5.0
- Android 에뮬레이터: emulator-5554
- ADB: `C:/Android/Sdk/platform-tools/adb.exe`

## 413 에러 방지 규칙 (필수)

### 원인
Claude API 요청 크기 제한 초과 (이미지/컨텍스트가 너무 큼)

### 예방 규칙
1. **스크린샷 읽기 금지**: Read 도구로 PNG 파일 직접 읽지 말 것
2. **대신 사용할 방법**:
   - UI 덤프 XML로 화면 분석
   - content-desc, text 속성 파싱
   - 필요시 스크린샷 파일 경로만 저장하고 사용자에게 직접 확인 요청

3. **코드 패턴**:
```python
# 화면 분석 (스크린샷 없이)
d = u2.connect()
xml = d.dump_hierarchy()
# XML 파싱으로 요소 찾기

# 스크린샷은 저장만 하고 읽지 않기
d.screenshot('screen.png')
print('[저장됨] screen.png - 직접 확인하세요')
```

4. **이미지 필요시**: 사용자에게 "screen.png 파일 확인해주세요" 요청

## 크롤링 워크플로우

### 요소 찾기 우선순위
1. `content-desc` (가장 안정적)
2. `text` 속성
3. 좌표 클릭 (최후의 수단)

### 핵심 코드 템플릿
```python
# -*- coding: utf-8 -*-
import uiautomator2 as u2
import sys
sys.stdout.reconfigure(encoding='utf-8')

d = u2.connect()

# content-desc로 찾기
elem = d(descriptionContains='펼쳐보기')
if elem.exists(timeout=3):
    elem.click()
```

### 주요 content-desc 매핑
| 동작 | content-desc |
|------|--------------|
| 더보기 | "음식배달에서 더보기" |
| 펼치기 | "배달유형별 배달팁 접혀있음, 펼쳐보기" |
| 접기 | "배달유형별 배달팁 펼쳐져있음, 접기" |
| 배달타입 | "가게배달", "알뜰배달", "한집배달" |

## 진행 상태
`기존대화.txt` 파일에서 최신 상태 확인
