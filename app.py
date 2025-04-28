from flask import Flask, request, jsonify
import shioaji as sj
import os

app = Flask(__name__)

# 儲存 Shioaji API 實例，避免重複登入
api = None

# 登入端點
@app.route('/login', methods=['POST'])
def login():
    global api
    # 從標頭中獲取金鑰
    api_key = request.headers.get('X-API-Key')
    secret_key = request.headers.get('X-Secret-Key')

    if not api_key or not secret_key:
        return jsonify({"error": "缺少必要的標頭: X-API-Key 和 X-Secret-Key"}), 401

    # 從請求主體中獲取憑證參數
    data = request.get_json() or {}
    ca_path = data.get('ca_path')
    ca_passwd = data.get('ca_passwd')
    person_id = data.get('person_id')
    simulation_mode = data.get('simulation_mode', False)  # 預設為 False（正式環境）

    # 驗證憑證參數（正式環境需要）
    if not simulation_mode and (not ca_path or not ca_passwd or not person_id):
        return jsonify({"error": "正式環境需要提供 ca_path, ca_passwd 和 person_id"}), 400

    try:
        # 初始化 Shioaji API
        api = sj.Shioaji(simulation=simulation_mode)
        api.login(
            api_key=api_key,
            secret_key=secret_key,
            contracts_timeout=10000
        )
        print("Shioaji 登入成功")

        # 如果是正式環境，啟用憑證
        if not simulation_mode:
            # 檢查憑證檔案是否存在
            if not os.path.exists(ca_path):
                return jsonify({"error": f"憑證檔案 {ca_path} 不存在"}), 400

            result = api.activate_ca(
                ca_path=ca_path,
                ca_passwd=ca_passwd,
                person_id=person_id
            )
            if not result:
                return jsonify({"error": "憑證啟用失敗"}), 400
            print("Shioaji 憑證啟用成功")

        return jsonify({"message": "登入成功"}), 200
    except Exception as e:
        print(f"Shioaji 登入或憑證啟用失敗: {str(e)}")
        api = None  # 確保失敗時清除 api 物件
        return jsonify({"error": f"登入或憑證啟用失敗: {str(e)}"}), 401

# 檢查是否已登入
def check_login():
    if api is None:
        return jsonify({"error": "尚未登入，請先調用 /login 端點"}), 401
    return None

# 查詢股票報價端點
@app.route('/quote', methods=['GET'])
def get_quote():
    # 檢查是否已登入
    login_error = check_login()
    if login_error:
        return login_error

    # 獲取股票代碼（使用官方的 "code" 命名）
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "缺少必要的參數: code"}), 400

    try:
        # 查詢商品檔（遵循 Shioaji 官方用法）
        contract = api.Contracts.Stocks[code]
        if not contract:
            return jsonify({"error": f"股票代碼 {code} 無效"}), 400

        # 查詢即時報價（使用 api.snapshots）
        snapshot = api.snapshots([contract])[0]

        # 格式化回應，包含官方欄位
        response = {
            "code": snapshot.code,
            "exchange": snapshot.exchange,
            "name": contract.name,
            "close": snapshot.close,
            "high": snapshot.high,
            "low": snapshot.low,
            "volume": snapshot.volume,
            "datetime": snapshot.datetime
        }
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": f"查詢失敗: {str(e)}"}), 500

# 商品檔端點
@app.route('/contract', methods=['GET'])
def get_contract():
    # 檢查是否已登入
    login_error = check_login()
    if login_error:
        return login_error

    code = request.args.get('code')
    if not code:
        return jsonify({"error": "缺少必要的參數: code"}), 400

    try:
        contract = api.Contracts.Stocks[code]
        if not contract:
            return jsonify({"error": f"股票代碼 {code} 無效"}), 400

        response = {
            "exchange": contract.exchange.value,
            "code": contract.code,
            "symbol": contract.symbol,
            "name": contract.name,
            "category": contract.category,
            "unit": contract.unit,
            "limit_up": contract.limit_up,
            "limit_down": contract.limit_down,
            "reference": contract.reference,
            "update_date": contract.update_date,
            "day_trade": contract.day_trade.value
        }
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": f"查詢失敗: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
