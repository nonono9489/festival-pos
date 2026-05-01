from flask import Flask, render_template, request, jsonify
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import json
import os

app = Flask(__name__)

# ─────────────────────────────────────────────
# ✏️  기본 메뉴 (최초 init 시에만 사용됨)
# 이후에는 구글 시트 '메뉴설정' 탭에서 관리
# ─────────────────────────────────────────────
DEFAULT_MENU = {
    "닭꼬치 순한맛": 4000,
    "닭꼬치 매운맛": 4000,
    "소떡소떡":      3000,
    "음료":          1500,
}

# ─────────────────────────────────────────────
# ✏️  관리자 비밀번호
# ─────────────────────────────────────────────
ADMIN_PASSWORD = "3927"   # ← 원하는 비밀번호로 변경

# ─────────────────────────────────────────────
# ✏️  구글 스프레드시트 설정
# ─────────────────────────────────────────────
SPREADSHEET_ID   = "1ScLyjPyRXBFuM-Osn1VwPJMPNpog6pNHWSc21xGq6VI"
SHEET_ORDER      = "주문내역"
SHEET_MENU       = "메뉴설정"
CREDENTIALS_FILE = "credentials.json"

# ─────────────────────────────────────────────
# Google Sheets 연결
# ─────────────────────────────────────────────
def get_sheets_service():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return build("sheets", "v4", credentials=creds)

# ─────────────────────────────────────────────
# 메뉴 관련
# ─────────────────────────────────────────────
def get_menu_from_sheet():
    """'메뉴설정' 시트에서 메뉴 목록 읽기"""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_MENU}!A2:C",
    ).execute()
    rows = result.get("values", [])
    menus = []
    for row in rows:
        if len(row) < 2:
            continue
        name     = row[0]
        price    = int(row[1]) if row[1].isdigit() else 0
        soldout  = row[2].strip() == "Y" if len(row) > 2 else False
        menus.append({"name": name, "price": price, "soldout": soldout})
    return menus

def save_menu_to_sheet(menus: list):
    """메뉴 목록 전체를 '메뉴설정' 시트에 저장"""
    service = get_sheets_service()
    rows = [[m["name"], m["price"], "Y" if m.get("soldout") else "N"] for m in menus]
    # 기존 데이터 지우고 다시 쓰기
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_MENU}!A2:C",
    ).execute()
    if rows:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_MENU}!A2",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()

# ─────────────────────────────────────────────
# 주문 관련
# ─────────────────────────────────────────────
def get_menu_keys():
    """현재 시트의 메뉴 이름 목록만 반환"""
    return [m["name"] for m in get_menu_from_sheet()]

def col_total(menu_keys):
    return 2 + len(menu_keys)

def col_status(menu_keys):
    return 2 + len(menu_keys) + 1

def get_all_order_rows():
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_ORDER}!A2:Z",
    ).execute()
    return result.get("values", [])

def get_next_order_number(rows):
    today = datetime.now().strftime("%Y-%m-%d")
    today_orders = [r for r in rows if len(r) > 1 and r[1].startswith(today)]
    return len(today_orders) + 1

def append_order(order: dict, menu_keys: list, price_map: dict):
    service = get_sheets_service()
    rows = get_all_order_rows()
    order_no_str = f"{get_next_order_number(rows):03d}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quantities = [order.get(menu, 0) for menu in menu_keys]
    total = sum(price_map.get(menu, 0) * order.get(menu, 0) for menu in menu_keys)
    row = [order_no_str, timestamp] + quantities + [total, "대기중"]
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_ORDER}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()
    return order_no_str

def get_summary(menu_keys):
    rows = get_all_order_rows()
    summary = {menu: 0 for menu in menu_keys}
    orders = []
    ct = col_total(menu_keys)
    cs = col_status(menu_keys)

    for row in rows:
        if not row:
            continue
        order_no  = row[0] if len(row) > 0 else "?"
        timestamp = row[1] if len(row) > 1 else ""
        status    = row[cs] if len(row) > cs else "대기중"
        items = {}
        for i, menu in enumerate(menu_keys):
            col = 2 + i
            try:
                qty = int(row[col]) if len(row) > col else 0
            except (ValueError, IndexError):
                qty = 0
            if qty > 0:
                summary[menu] += qty
                items[menu] = qty
        try:
            total = int(row[ct]) if len(row) > ct else 0
        except ValueError:
            total = 0
        orders.append({"order_no": order_no, "timestamp": timestamp,
                       "items": items, "total": total, "status": status})
    return summary, list(reversed(orders))

def get_pending_orders(menu_keys):
    rows = get_all_order_rows()
    cs = col_status(menu_keys)
    pending = []
    for i, row in enumerate(rows):
        if not row:
            continue
        status = row[cs] if len(row) > cs else "대기중"
        if status == "완료":
            continue
        order_no  = row[0] if len(row) > 0 else "?"
        timestamp = row[1] if len(row) > 1 else ""
        items = {}
        for j, menu in enumerate(menu_keys):
            col = 2 + j
            try:
                qty = int(row[col]) if len(row) > col else 0
            except (ValueError, IndexError):
                qty = 0
            if qty > 0:
                items[menu] = qty
        pending.append({"order_no": order_no, "timestamp": timestamp,
                        "items": items, "sheet_row": i + 2})
    return pending

def complete_order(sheet_row: int, menu_keys: list):
    service = get_sheets_service()
    cs = col_status(menu_keys)
    col_letter = ""
    n = cs
    while True:
        col_letter = chr(ord('A') + n % 26) + col_letter
        n = n // 26 - 1
        if n < 0:
            break
    cell = f"{SHEET_ORDER}!{col_letter}{sheet_row}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell,
        valueInputOption="USER_ENTERED",
        body={"values": [["완료"]]},
    ).execute()

def init_sheets():
    """주문내역 + 메뉴설정 시트 초기화"""
    service = get_sheets_service()
    menus = list(DEFAULT_MENU.items())
    menu_names = [m[0] for m in menus]

    # 주문내역 헤더
    order_headers = ["주문번호", "타임스탬프"] + menu_names + ["합계금액", "완료여부"]
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_ORDER}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [order_headers]},
    ).execute()

    # 메뉴설정 헤더 + 기본 메뉴
    menu_header = [["메뉴명", "가격", "솔드아웃(Y/N)"]]
    menu_rows   = [[name, price, "N"] for name, price in menus]
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_MENU}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": menu_header + menu_rows},
    ).execute()

# ─────────────────────────────────────────────
# 라우트
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/kitchen")
def kitchen():
    return render_template("kitchen.html")

@app.route("/api/menu")
def api_menu():
    try:
        menus = get_menu_from_sheet()
        return jsonify({"success": True, "menus": menus})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/order", methods=["POST"])
def api_order():
    data = request.json
    try:
        menus = get_menu_from_sheet()
        menu_keys  = [m["name"] for m in menus]
        price_map  = {m["name"]: m["price"] for m in menus}
        soldout    = {m["name"] for m in menus if m["soldout"]}
        order_items = {k: v for k, v in data.items()
                       if k in menu_keys and v > 0 and k not in soldout}
        if not order_items:
            return jsonify({"success": False, "message": "주문 항목이 없습니다"}), 400
        order_no = append_order(order_items, menu_keys, price_map)
        return jsonify({"success": True, "order_no": order_no})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/summary")
def api_summary():
    try:
        menus = get_menu_from_sheet()
        menu_keys = [m["name"] for m in menus]
        totals, orders = get_summary(menu_keys)
        return jsonify({"success": True, "data": totals, "orders": orders, "menus": menus})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/kitchen")
def api_kitchen():
    try:
        menus = get_menu_from_sheet()
        menu_keys = [m["name"] for m in menus]
        pending = get_pending_orders(menu_keys)
        return jsonify({"success": True, "orders": pending})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/complete", methods=["POST"])
def api_complete():
    data = request.json
    sheet_row = data.get("sheet_row")
    if not sheet_row:
        return jsonify({"success": False, "message": "sheet_row 없음"}), 400
    try:
        menus = get_menu_from_sheet()
        menu_keys = [m["name"] for m in menus]
        complete_order(int(sheet_row), menu_keys)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "비밀번호가 틀렸습니다"}), 401

@app.route("/api/admin/soldout", methods=["POST"])
def api_admin_soldout():
    data = request.json
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "인증 실패"}), 401
    try:
        menus = get_menu_from_sheet()
        name    = data.get("name")
        soldout = data.get("soldout", False)
        for m in menus:
            if m["name"] == name:
                m["soldout"] = soldout
                break
        save_menu_to_sheet(menus)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/menu/add", methods=["POST"])
def api_admin_menu_add():
    data = request.json
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "인증 실패"}), 401
    try:
        name  = data.get("name", "").strip()
        price = int(data.get("price", 0))
        if not name or price <= 0:
            return jsonify({"success": False, "message": "메뉴명과 가격을 확인해주세요"}), 400
        menus = get_menu_from_sheet()
        if any(m["name"] == name for m in menus):
            return jsonify({"success": False, "message": "이미 존재하는 메뉴입니다"}), 400
        menus.append({"name": name, "price": price, "soldout": False})
        save_menu_to_sheet(menus)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/init", methods=["POST"])
def api_init():
    try:
        init_sheets()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)