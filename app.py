from flask import Flask, render_template, request, jsonify
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import json
import os

app = Flask(__name__)

# ─────────────────────────────────────────────
# ✏️  여기에 메뉴 이름과 가격을 입력하세요
# ─────────────────────────────────────────────
MENU = {
    "닭꼬치 순한맛": 4000,   # ← 가격 (원)
    "닭꼬치 매운맛": 4000,   # ← 가격 (원)
    "소떡소떡":      3000,   # ← 가격 (원)
    "음료":          2000,   # ← 가격 (원)
}

# ─────────────────────────────────────────────
# ✏️  구글 스프레드시트 설정
# ─────────────────────────────────────────────
SPREADSHEET_ID = "1ScLyjPyRXBFuM-Osn1VwPJMPNpog6pNHWSc21xGq6VI"   # ← 스프레드시트 URL에서 복사
SHEET_NAME = "주문내역"                           # ← 시트 이름 (기본값 유지 가능)
CREDENTIALS_FILE = "credentials.json"             # ← 서비스 계정 키 파일명

# ─────────────────────────────────────────────
# Google Sheets 연결
# ─────────────────────────────────────────────
def get_sheets_service():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return build("sheets", "v4", credentials=creds)
def append_order(order: dict):
    """주문 1건을 스프레드시트에 추가"""
    service = get_sheets_service()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    menu_keys = list(MENU.keys())

    quantities = [order.get(menu, 0) for menu in menu_keys]
    total = sum(MENU[menu] * order.get(menu, 0) for menu in menu_keys)

    row = [timestamp] + quantities + [total]
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()

def get_summary():
    """메뉴별 누적 판매 수량 집계"""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A2:Z",
    ).execute()

    rows = result.get("values", [])
    menu_keys = list(MENU.keys())
    summary = {menu: 0 for menu in menu_keys}

    for row in rows:
        for i, menu in enumerate(menu_keys):
            col = i + 1  # A=타임스탬프, B부터 메뉴
            try:
                summary[menu] += int(row[col]) if len(row) > col else 0
            except (ValueError, IndexError):
                pass

    return summary

def init_sheet():
    """스프레드시트 헤더 초기화"""
    service = get_sheets_service()
    headers = ["타임스탬프"] + list(MENU.keys()) + ["합계금액"]
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()

# ─────────────────────────────────────────────
# 라우트
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", menu=MENU)

@app.route("/api/order", methods=["POST"])
def order():
    data = request.json
    order_items = {k: v for k, v in data.items() if k in MENU and v > 0}
    if not order_items:
        return jsonify({"success": False, "message": "주문 항목이 없습니다"}), 400
    try:
        append_order(order_items)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/summary")
def summary():
    try:
        data = get_summary()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/init", methods=["POST"])
def init():
    """헤더 초기화 (최초 1회 실행)"""
    try:
        init_sheet()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/menu")
def menu_info():
    return jsonify(MENU)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
