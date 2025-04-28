from flask import Flask, request, jsonify
import shioaji as sj

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

    try:
        api = sj.Shioaji(simulation=False)  # 正式環境，設為 True 可使用模擬模式
        api.login(
            api_key=api_key,
            secret_key=secret_key,
            contracts_timeout=10000
        )
        print("Shioaji 登入成功")
        return jsonify({"message": "登入成功"}), 200
    except Exception as e:
        print(f"Shioaji 登入失敗: {str(e)}")
        api = None  # 確保失敗時清除 api 物件
        return jsonify({"error": f"登入失敗: {str(e)}"}), 401

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
