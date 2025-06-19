from flask import Flask, request, jsonify
import requests
import json
import os
import time
import threading
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
BASE_URL = os.getenv("OANDA_BASE_URL")
INSTRUMENT = "GBP_JPY"
UNITS = 1000
LOSS_CUT_THRESHOLD = -2000

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

open_position = {"side": None, "units": 0, "price": 0}
app = Flask(__name__)

def get_price():
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/pricing?instruments={INSTRUMENT}"
    response = requests.get(url, headers=headers)
    prices = response.json()["prices"][0]
    return float(prices["bids"][0]["price"]), float(prices["asks"][0]["price"])

def place_order(units):
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders"
    data = {
        "order": {
            "instrument": INSTRUMENT,
            "units": str(units),
            "type": "MARKET",
            "positionFill": "DEFAULT"
        }
    }
    r = requests.post(url, headers=headers, data=json.dumps(data))
    if r.status_code == 201:
        print(f"✅ 注文成功: {units}")
    else:
        print(f"❌ 注文失敗: {r.status_code} {r.text}")

def execute_trade(signal):
    global open_position
    bid, ask = get_price()
    price = ask if signal == "buy" else bid
    print(f"📈 現在価格（bid/ask）: {bid}/{ask}")

    if signal == "buy":
        if open_position["side"] == "SELL":
            place_order(UNITS)
        place_order(UNITS)
        open_position = {"side": "BUY", "units": UNITS, "price": price}

    elif signal == "sell":
        if open_position["side"] == "BUY":
            place_order(-UNITS)
        place_order(-UNITS)
        open_position = {"side": "SELL", "units": UNITS, "price": price}

def loss_cut_monitor():
    global open_position
    while True:
        if open_position["side"] and open_position["price"]:
            bid, ask = get_price()
            current_price = bid if open_position["side"] == "SELL" else ask
            pnl = (current_price - open_position["price"]) * open_position["units"]
            if open_position["side"] == "SELL":
                pnl = -pnl
            print(f"📉 含み損益: {int(pnl)}円")

            if pnl < LOSS_CUT_THRESHOLD:
                print(f"💥 ロスカット実行！損失: {int(pnl)}円")
                opposite_units = -open_position["units"] if open_position["side"] == "BUY" else UNITS
                place_order(opposite_units)
                open_position = {"side": None, "units": 0, "price": 0}
        time.sleep(30)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        print(f"📨 raw data: {request.data}")
        data = request.get_json(silent=True)
        if not data:
            print("⚠️ JSONデコード失敗。フォームデータ確認中...")
            data = request.form.to_dict()
        print(f"📦 パース結果: {data}")

        signal = data.get("signal") or data.get("action")
        if signal in ["buy", "sell"]:
            execute_trade(signal)
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "invalid signal"}), 400
    except Exception as e:
        import traceback
        print("❌ webhook内部エラー:", traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=loss_cut_monitor, daemon=True).start()
    app.run(host="0.0.0.0", port=port)
