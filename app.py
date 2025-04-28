from flask import Flask, request
import shioaji as sj
import json
import logging
import os
import socket
import sys

app = Flask(__name__)

# 設置日誌，寫入 /tmp/shioaji.log
logger = logging.getLogger('shioaji')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('/tmp/shioaji.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.handlers = [handler]

# 記錄服務的 IP 位址
try:
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    logger.info(f"Service running on host: {hostname}, IP: {ip_address}")
except Exception as e:
    logger.error(f"Failed to get IP address: {str(e)}")

# 全局變數，用於儲存 Shioaji API 實例
api = None

@app.route('/login', methods=['POST'])
def login():
    global api
    try:
        data = request.get_json()
        if not data:
            error_msg = "Request body is empty"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

        api_key = data.get("api_key")
        secret_key = data.get("secret_key")
        ca_path = data.get("ca_path", "/app/Sinopac.pfx")
        ca_password = data.get("ca_password")
        person_id = data.get("person_id")
        simulation_mode = data.get("simulation_mode", False)

        missing_params = []
        if not api_key:
            missing_params.append("api_key")
        if not secret_key:
            missing_params.append("secret_key")
        if not simulation_mode:
            if not ca_password:
                missing_params.append("ca_password")
            if not person_id:
                missing_params.append("person_id")

        if missing_params:
            error_msg = f"Missing required parameters: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

        if not simulation_mode:
            if not os.path.exists(ca_path):
                error_msg = f"CA file not found at {ca_path}"
                logger.error(error_msg)
                return {"statusCode": 500, "body": json.dumps({"error": error_msg})}
            logger.info(f"CA file found at {ca_path}")

        logger.info(f"Received login request: api_key={api_key[:4]}****, secret_key={secret_key[:4]}****")
        logger.info(f"Initializing Shioaji with simulation={simulation_mode}")
        api = sj.Shioaji(simulation=simulation_mode)

        if not simulation_mode:
            logger.info(f"Activating CA with ca_path={ca_path}, person_id={person_id}")
            result = api.activate_ca(ca_path=ca_path, ca_passwd=ca_password, person_id=person_id)
            if not result:
                error_msg = "Failed to activate CA"
                logger.error(error_msg)
                return {"statusCode": 500, "body": json.dumps({"error": error_msg})}
            logger.info("CA activated successfully")

        logger.info("Logging into Shioaji")
        accounts = api.login(api_key=api_key, secret_key=secret_key)
        logger.info(f"Login successful, accounts: {json.dumps(accounts, default=str)}")

        logger.info("Fetching contracts data")
        api.fetch_contracts()
        logger.info("Contracts data fetched successfully")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Login successful", "accounts": accounts}, default=str)
        }

    except Exception as e:
        error_msg = f"Error in login: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception traceback: {sys.exc_info()}")
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

@app.route('/quote', methods=['POST'])
def quote():
    global api
    try:
        data = request.get_json()
        if not data:
            error_msg = "Request body is empty"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

        code = data.get("code")  # 改為官方參數 "code"
        type_ = data.get("type", "stock")  # 預設為 stock

        if not code:
            error_msg = "Missing required parameter: code"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

        if api is None:
            error_msg = "Shioaji API not initialized. Please login first."
            logger.error(error_msg)
            return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

        logger.info(f"Received quote request: code={code}, type={type_}")

        # 根據 type 選擇合約類型
        contract = None
        market = None

        if type_ == "stock":
            # 嘗試從 TSE 查詢股票合約
            logger.info(f"Fetching contract for code={code} from TSE")
            contract = api.Contracts.Stocks.TSE[code]
            market = "TSE"

            # 如果 TSE 中找不到，嘗試從 OTC 查詢
            if contract is None:
                logger.info(f"Contract not found in TSE, trying OTC for code={code}")
                contract = api.Contracts.Stocks.OTC[code]
                market = "OTC"

            if contract is None:
                error_msg = f"Contract not found for code={code} in TSE or OTC"
                logger.error(error_msg)
                return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

        elif type_ == "futures":
            # 查詢期貨合約
            logger.info(f"Fetching futures contract for code={code}")
            contract = api.Contracts.Futures[code]
            market = "Futures"

            if contract is None:
                error_msg = f"Futures contract not found for code={code}"
                logger.error(error_msg)
                return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

        elif type_ == "options":
            # 查詢選擇權合約
            logger.info(f"Fetching options contract for code={code}")
            contract = api.Contracts.Options[code]
            market = "Options"

            if contract is None:
                error_msg = f"Options contract not found for code={code}"
                logger.error(error_msg)
                return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

        elif type_ == "index":
            # 查詢指數合約
            logger.info(f"Fetching index contract for code={code} from TSE")
            contract = api.Contracts.Indexs.TSE[code]
            market = "Index"

            if contract is None:
                error_msg = f"Index contract not found for code={code} in TSE"
                logger.error(error_msg)
                return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

        else:
            error_msg = f"Unsupported type: {type_}. Supported types are: stock, futures, options, index"
            logger.error(error_msg)
            return {"statusCode": 400, "body": json.dumps({"error": error_msg})}

        # 記錄合約資料
        logger.info(f"Contract found in {market}: {json.dumps(contract.__dict__, default=str)}")

        # 查詢快照資料
        logger.info(f"Fetching quote for code={code} (type={type_})")
        quote = api.snapshots([contract])[0]
        logger.info(f"Quote fetched successfully: {json.dumps(quote, default=str)}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Quote fetched",
                "quote": quote,
                "market": market,
                "type": type_
            }, default=str)
        }

    except KeyError as ke:
        error_msg = f"Contract not found for code={code} (type={type_}, KeyError: {str(ke)})"
        logger.error(error_msg)
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}
    except Exception as e:
        error_msg = f"Error in quote: {str(e)} (type={type_})"
        logger.error(error_msg)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception traceback: {sys.exc_info()}")
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

@app.route('/contracts', methods=['GET'])
def get_contracts():
    global api
    try:
        if api is None:
            error_msg = "Shioaji API not initialized. Please login first."
            logger.error(error_msg)
            return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

        # 獲取 TSE 股票合約資料
        logger.info("Fetching TSE contracts")
        tse_contracts = {k: v.__dict__ if v is not None else None for k, v in api.Contracts.Stocks.TSE.items()}
        logger.info("TSE contracts fetched successfully")

        # 獲取 OTC 股票合約資料
        logger.info("Fetching OTC contracts")
        otc_contracts = {k: v.__dict__ if v is not None else None for k, v in api.Contracts.Stocks.OTC.items()}
        logger.info("OTC contracts fetched successfully")

        # 獲取期貨合約資料
        logger.info("Fetching Futures contracts")
        futures_contracts = {k: v.__dict__ if v is not None else None for k, v in api.Contracts.Futures.items()}
        logger.info("Futures contracts fetched successfully")

        # 獲取選擇權合約資料
        logger.info("Fetching Options contracts")
        options_contracts = {k: v.__dict__ if v is not None else None for k, v in api.Contracts.Options.items()}
        logger.info("Options contracts fetched successfully")

        # 獲取指數合約資料
        logger.info("Fetching Index contracts")
        index_contracts = {k: v.__dict__ if v is not None else None for k, v in api.Contracts.Indexs.TSE.items()}
        logger.info("Index contracts fetched successfully")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Contracts fetched",
                "tse_contracts": tse_contracts,
                "otc_contracts": otc_contracts,
                "futures_contracts": futures_contracts,
                "options_contracts": options_contracts,
                "index_contracts": index_contracts
            }, default=str)
        }

    except Exception as e:
        error_msg = f"Error in contracts: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception traceback: {sys.exc_info()}")
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
