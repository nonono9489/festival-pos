# 🍢 축제 POS 시스템 — 세팅 가이드

## 전체 흐름
```
핸드폰 브라우저 → Flask 서버 (Render 무료) → Google Sheets API → 스프레드시트
```

---

## STEP 1 — 구글 스프레드시트 준비

1. [Google Sheets](https://sheets.google.com) 에서 새 스프레드시트 생성
2. 시트 이름을 **`주문내역`** 으로 변경 (하단 탭 더블클릭)
3. URL에서 스프레드시트 ID 복사
   ```
   https://docs.google.com/spreadsheets/d/【여기가 ID】/edit
   ```
4. 이 ID를 `app.py`의 `SPREADSHEET_ID` 변수에 붙여넣기

---

## STEP 2 — Google 서비스 계정 키 발급

1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 새 프로젝트 생성 (이름 자유)
3. **API 및 서비스 → 라이브러리** → `Google Sheets API` 검색 → 사용 설정
4. **API 및 서비스 → 사용자 인증 정보** → `+ 사용자 인증 정보 만들기` → `서비스 계정`
5. 서비스 계정 이름 입력 후 완료
6. 생성된 서비스 계정 클릭 → **키** 탭 → `키 추가` → `JSON` 선택 → 다운로드
7. 다운로드된 JSON 파일을 **`credentials.json`** 으로 이름 변경 후 프로젝트 폴더에 넣기

8. **스프레드시트에 서비스 계정 권한 부여**
   - `credentials.json` 열어서 `"client_email"` 값 복사 (예: `xxx@xxx.iam.gserviceaccount.com`)
   - 스프레드시트 → 우상단 `공유` 버튼 → 복사한 이메일 붙여넣기 → **편집자** 권한으로 공유

---

## STEP 3 — 메뉴 & 가격 설정

`app.py` 상단에서 수정:

```python
MENU = {
    "닭꼬치 순한맛": 3000,   # ← 원하는 가격으로 변경
    "닭꼬치 매운맛": 3000,
    "소떡소떡":      3000,
    "음료":          1500,
}
```

---

## STEP 4 — Render 무료 배포 (도메인 자동 발급)

### Render 선택 이유
- 완전 무료 (신용카드 불필요)
- `https://앱이름.onrender.com` 도메인 자동 발급
- GitHub 연동으로 쉬운 배포

### 배포 방법

1. [GitHub](https://github.com) 에 프로젝트 올리기
   ```bash
   git init
   git add .
   git commit -m "init"
   # GitHub에 새 repo 만들고:
   git remote add origin https://github.com/너의계정/pos-system.git
   git push -u origin main
   ```

2. ⚠️ **`credentials.json`은 절대 GitHub에 올리지 마세요!**
   `.gitignore` 파일 생성 후 아래 내용 추가:
   ```
   credentials.json
   __pycache__/
   *.pyc
   ```

3. [Render.com](https://render.com) 가입 → `New Web Service` → GitHub repo 연결
4. 설정:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Environment Variables**: 아래 STEP 5 참고

---

## STEP 5 — credentials.json 환경변수로 처리 (보안)

Render에 JSON 파일을 직접 올릴 수 없으므로, 환경변수로 처리합니다.

1. `credentials.json` 내용을 통째로 복사
2. Render → Environment → `Add Environment Variable`
   - Key: `GOOGLE_CREDENTIALS_JSON`
   - Value: 복사한 JSON 전체 내용 붙여넣기

3. `app.py`의 `get_sheets_service()` 함수를 아래로 교체:

```python
import json, tempfile

def get_sheets_service():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        # 환경변수에서 읽기 (배포 환경)
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # 로컬에서 파일로 읽기
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return build("sheets", "v4", credentials=creds)
```

---

## STEP 6 — 스프레드시트 헤더 초기화 (최초 1회)

배포 후, 브라우저에서 아래 URL 한 번 접속:
```
https://앱이름.onrender.com/api/init
```
→ 스프레드시트에 헤더 행이 자동 생성됩니다.

---

## 사용 방법

| 화면 | 용도 |
|------|------|
| 🛒 주문 입력 | + / − 버튼으로 수량 조절 → 주문 확정 |
| 📊 판매 현황 | 메뉴별 누적 판매량 + 총 매출 확인 |

- 여러 명이 동시에 같은 URL 접속해서 주문 입력 가능
- 주문 확정 시 구글 스프레드시트에 실시간 저장

---

## 로컬 테스트 방법

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5000 접속
```
