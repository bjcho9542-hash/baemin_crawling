# 배달의민족 크롤러

## 설치 방법

### 1. Python 설치
- Python 3.8 이상 필요
- https://www.python.org/downloads/

### 2. 필수 패키지 설치
```bash
pip install uiautomator2
pip install opencv-python
pip install openpyxl
```

### 3. Android 환경 설정

#### ADB 설치 (방법 1: Android Studio)
1. Android Studio 다운로드 및 설치
   - https://developer.android.com/studio
2. 설치 시 "Android SDK" 체크
3. 설치 완료 후 SDK 경로 확인
   - 보통 `C:\Users\{사용자명}\AppData\Local\Android\Sdk\platform-tools`
4. 환경변수 PATH에 위 경로 추가

#### ADB 설치 (방법 2: Platform-Tools만)
- Android SDK Platform-Tools 다운로드
- https://developer.android.com/tools/releases/platform-tools
- 압축 해제 후 환경변수 PATH에 추가

#### 핸드폰 설정
1. 개발자 옵션 활성화
   - 설정 → 휴대전화 정보 → 소프트웨어 정보 → 빌드번호 7번 터치
2. USB 디버깅 켜기
   - 설정 → 개발자 옵션 → USB 디버깅 ON
3. USB 연결 후 "USB 디버깅 허용" 팝업에서 확인

#### 연결 확인
```bash
adb devices
```
디바이스가 `device` 상태로 보이면 OK

### 4. uiautomator2 초기화 (최초 1회)
```bash
python -m uiautomator2 init
```
핸드폰에 ATX-Agent 앱 설치됨

## 실행 방법

### 크롤러 실행
```bash
python baemin_crawler_final.py
```
- 배민 앱 홈 화면에서 실행
- 10개 매장 기본 수집 (코드에서 max_stores 변경 가능)

### UI Inspector (디버깅용)
```bash
python inspector.py
```
- 브라우저에서 http://localhost:8080 접속
- 현재 화면 UI 요소 확인 가능

## 파일 구조
```
baemin_crawling/
├── baemin_crawler_final.py  # 메인 크롤러
├── inspector.py              # UI Inspector
├── templates/
│   └── store_info_btn.png   # 가게정보 버튼 템플릿
└── baemin_stores_*.xlsx     # 결과 엑셀 파일
```

## 수집 항목
- 가게명
- 배달타입 (가게배달/알뜰배달/한집배달)
- 상호명
- 주소
- 전화번호
- 최근주문수
- 전체리뷰수

## 주의사항
- 배민 앱 홈 화면 (음식배달 더보기가 보이는 상태)에서 시작
- 화면 해상도에 따라 스크롤 좌표 조정 필요할 수 있음 (기본: 1080x2400)
- "방금 본 가게와 비슷해요!" 광고 섹션 아래 4개 매장은 자동 스킵
