from flask import Flask, jsonify
from bot import get_market_status

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "mode": "PAPER ONLY",
        "message": "BTC STVPT paper bot server is running"
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/market")
def market():
    return jsonify(get_market_status())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
