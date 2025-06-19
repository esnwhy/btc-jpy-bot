
from dotenv import load_dotenv
import os
import time
import threading
import requests
import json
import hmac
import hashlib
from flask import Flask, request, jsonify

load_dotenv()
API_KEY = os.getenv("BITFLYER_API_KEY")
API_SECRET = os.getenv("BITFLYER_API_SECRET")
BASE_URL = "https://api.bitflyer.com"
PRODUCT_CODE = "FX_BTC_JPY"
ORDER_SIZE_JPY = 1000
LOSS_CUT_THRESHOLD = -200

open_position = {"side": None, "size": 0, "price": 0}
app = Flask(__name__)

def get_current_price():
    try:
        res = requests.get(f"{BASE_URL}/v1/ticker", params={"product_code": PRODUCT_CODE})
        return res.json()["ltp"]
    except Exception as e:
        print(f"⚠️ 価格取得エラー: {e}")
        return 8000000

def create_signature(timestamp, method, path, body, secret):
    message = f"{timestamp}{method}{path}{body}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def place_order(side, size):
    path = "/v1/me/sendchildorder"
    url = BASE_URL + path
    method = "POST"
    body_dict = {
        "product_code": PRODUCT_CODE,
        "child_order_type": "MARKET",
        "side": side,
        "size": round(size, 8),
        "minute_to_expire": 10000,
        "time_in_force": "GTC"
    }
    body = json.dumps(body_dict)
    timestamp = str(int(time.time()))
    sign = create_signature(timestamp, method, path, body, API_SECRET)
    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-SIGN": sign,
        "Content-Type": "application/json"
    }

    print(f"💰 BTC注文送信中: {side} {size} BTC")
    try:
        response = requests.post(url, headers=headers, data=body)
        if response.status_code == 200:
            print(f"✅ 注文成功: {response.json()}")
        else:
            print(f"❌ 注文失敗: {response.status_code} {response.text}")
    except Exception as e:
        print(f"⚠️ 通信エラー: {e}")

def execute_trade(action):
    global open_position
    price = get_current_price()
    size = ORDER_SIZE_JPY / price

    if action == "buy":
        print("🟢 buyアラート受信！")
        if open_position["side"] == "SELL":
            print("🔄 売りポジションを解消中")
            place_order("BUY", open_position["size"])
        place_order("BUY", size)
        open_position = {"side": "BUY", "size": size, "price": price}
    elif action == "sell":
        print("🔴 sellアラート受信！")
        if open_position["side"] == "BUY":
            print("🔄 買いポジションを解消中")
            place_order("SELL", open_position["size"])
        place_order("SELL", size)
        open_position = {"side": "SELL", "size": size, "price": price}

def loss_cut_monitor():
    while True:
        if open_position["side"] and open_position["price"]:
            current_price = get_current_price()
            pnl = (current_price - open_position["price"]) * open_position["size"]
            if open_position["side"] == "SELL":
                pnl = -pnl
            print(f"📉 ロスカット監視中... 含み損益: {int(pnl)}円")
            if pnl < LOSS_CUT_THRESHOLD:
                print(f"💥 ロスカット実行！損失: {int(pnl)}円")
                opposite = "SELL" if open_position["side"] == "BUY" else "BUY"
                place_order(opposite, open_position["size"])
                open_position.update({"side": None, "size": 0, "price": 0})
        time.sleep(30)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)
        if not data:
            print("⚠️ JSONパース失敗。Fallbackとしてフォームデータを確認")
            data = request.form.to_dict()
        print(f"📦 受信データ: {data}")

        action = data.get("action") or data.get("signal")  # ← 両方対応
        if action in ["buy", "sell"]:
            execute_trade(action)
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "invalid action"}), 400
    except Exception as e:
        print(f"❌ Webhook処理中エラー: {e}")
        print(f"🔍 request.data: {request.data}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=loss_cut_monitor, daemon=True).start()
    app.run(host="0.0.0.0", port=port)
