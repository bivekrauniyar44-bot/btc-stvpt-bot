from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "mode": "PAPER ONLY",
        "message": "BTC STVPT bot server is running"
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
