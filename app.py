from flask import Flask, request, jsonify
import shioaji as sj
import logging
import os

app = Flask(__name__)

# 設置日誌，寫入 /tmp/shioaji.log
logger = logging.getLogger('shioaji')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('/tmp/shioaji.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.handlers = [handler]

# 全局變數，用於儲存 Shioaji API 實例
api = None

# 登入端點
@app.route('/login', methods=['POST'])
def login():
    global api
    try:
        data = request.get_json()
        if not data:
            logger.error("Request body is empty")
            return jsonify({"error": "Request body is empty"}), 400

        api_key = data.get("api_key")
        secret_key = data.get("secret_key")
        ca_path = data.get("ca_path", "/app/Sinopac.pfx")  # Zeabur 支援 /app 資料夾
        ca_passwd = data.get("ca_passwd")
        person_id = data.get("person_id")
        simulation_mode = data.get("simulation_mode", False)

        # 驗證參數
        missing_params = []
        if not api_key:
            missing_params.append("api_key")
        if not secret_key:
            missing_params.append("secret_key")
        if not simulation_mode:
            if not ca_passwd:
                missing_params.append("ca_passwd")
            if not person_id:
                missing_params.append("person_id")

        if missing_params:
            error_msg = f"Missing required parameters: {', '.join(missing_params)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400

        # 檢查憑證檔案（正式環境）
        if not simulation_mode:
            if not os.path.exists(ca_path):
                error_msg = f"CA file not found at {ca_path}"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 500
            logger.info(f"CA file found at {ca_path}")

        logger.info("Initializing Shioaji")
        api = sj.Shioaji(simulation=simulation_mode)

        if not simulation_mode:
            logger.info("Activating CA")
            result = api.activate_ca(ca_path=ca_path, ca_passwd=ca_passwd, person_id=person_id)
            if not result:
                error_msg = "Failed to activate CA"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 500
            logger.info("CA activated successfully")

        logger.info("Logging into Shioaji")
        accounts = api.login(api_key=api_key, secret_key=secret_key)
        logger.info("Login successful")

        logger.info("Fetching contracts data")
        api.fetch_contracts()
        logger.info("Contracts data fetched successfully")

        return jsonify({"message": "Login successful", "accounts": accounts}), 200

    except Exception as e:
        error_msg = f"Error in login: {str(e)}"
        logger.error(error_msg)
        api = None
        return jsonify({"error": error_msg}), 500

# 檢查是否已登入
def check_login():
    if api is None:
        logger.error("Shioaji API not initialized")
        return jsonify({"error": "Shioaji API not initialized. Please login first."}), 401
    return None

# 查詢報價端點（符合 Shioaji 官方參數）
@app.route('/quote', methods=['GET'])
def quote():
    # 檢查是否已登入
    login_error = check_login()
    if login_error:
        return login_error

    try:
        code = request.args.get("code")  # 使用官方參數 "code"
        type_ = request.args.get("type", "stock")  # 預設為 stock

        if not code:
            error_msg = "Missing required parameter: code"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400

        logger.info(f"Received quote request: code={code}, type={type_}")

        # 根據 type 選擇合約類型
        contract = None
        market = None

        if type_ == "stock":
            logger.info(f"Fetching stock contract for code={code} from TSE")
            contract = api.Contracts.Stocks.TSE[code]
            market = "TSE"

            if contract is None:
                logger.info(f"Contract not found in TSE, trying OTC for code={code}")
                contract = api.Contracts.Stocks.OTC[code]
                market = "OTC"

            if contract is None:
                error_msg = f"Contract not found for code={code} in TSE or OTC"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 404

        elif type_ == "futures":
            logger.info(f"Fetching futures contract for code={code}")
            contract = api.Contracts.Futures[code]
            market = "Futures"

            if contract is None:
                error_msg = f"Futures contract not found for code={code}"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 404

        elif type_ == "options":
            logger.info(f"Fetching options contract for code={code}")
            contract = api.Contracts.Options[code]
            market = "Options"

            if contract is None:
                error_msg = f"Options contract not found for code={code}"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 404

        elif type_ == "index":
            logger.info(f"Fetching index contract for code={code} from TSE")
            contract = api.Contracts.Indexs.TSE[code]
            market = "Index"

            if contract is None:
                error_msg = f"Index contract not found for code={code} in TSE"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 404

        else:
            error_msg = f"Unsupported type: {type_}. Supported types are: stock, futures, options, index"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400

        # 查詢快照資料
        logger.info(f"Fetching quote for code={code} (type={type_})")
        quote = api.snapshots([contract])[0]

        return jsonify({
            "message": "Quote fetched",
            "quote": {
                "code": quote.code,
                "exchange": quote.exchange,
                "close": quote.close,
                "high": quote.high,
                "low": quote.low,
                "volume": quote.volume,
                "datetime": str(quote.datetime)
            },
            "market": market,
            "type": type_
        }), 200

    except KeyError as ke:
        error_msg = f"Contract not found for code={code} (type={type_}, KeyError: {str(ke)})"
        logger.error(error_msg)
        return jsonify({"error": error_msg}), 404
    except Exception as e:
        error_msg = f"Error in quote: {str(e)} (type={type_})"
        logger.error(error_msg)
        return jsonify({"error": error_msg}), 500

# 查詢所有合約端點
@app.route('/contracts', methods=['GET'])
def get_contracts():
    # 檢查是否已登入
    login_error = check_login()
    if login_error:
        return login_error

    try:
        type_ = request.args.get("type", "stock")  # 預設為 stock

        contracts = None
        if type_ == "stock":
            logger.info("Fetching TSE and OTC contracts")
            tse_contracts = {k: v.__dict__ for k, v in api.Contracts.Stocks.TSE.items() if v is not None}
            otc_contracts = {k: v.__dict__ for k, v in api.Contracts.Stocks.OTC.items() if v is not None}
            contracts = {"TSE": tse_contracts, "OTC": otc_contracts}
        elif type_ == "futures":
            logger.info("Fetching Futures contracts")
            contracts = {k: v.__dict__ for k, v in api.Contracts.Futures.items() if v is not None}
        elif type_ == "options":
            logger.info("Fetching Options contracts")
            contracts = {k: v.__dict__ for k, v in api.Contracts.Options.items() if v is not None}
        elif type_ == "index":
            logger.info("Fetching Index contracts")
            contracts = {k: v.__dict__ for k, v in api.Contracts.Indexs.TSE.items() if v is not None}
        else:
            error_msg = f"Unsupported type: {type_}. Supported types are: stock, futures, options, index"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400

        return jsonify({
            "message": "Contracts fetched",
            "type": type_,
            "contracts": contracts
        }), 200

    except Exception as e:
        error_msg = f"Error in contracts: {str(e)}"
        logger.error(error_msg)
        return jsonify({"error": error_msg}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
