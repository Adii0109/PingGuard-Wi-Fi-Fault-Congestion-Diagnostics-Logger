from datetime import date
from flask import Flask, jsonify, request, send_file
from database import init_and_clean_database, get_available_days, get_records_by_day

app = Flask(__name__)
init_and_clean_database()


@app.route("/")
def home():
    return send_file("index.html")


@app.route("/api/days", methods=["GET"])
def api_days():
    return jsonify({"days": get_available_days()})


@app.route("/api/records", methods=["GET"])
@app.route("/api/records", methods=["GET"])
def api_records():
    selected_day = request.args.get("day")
    if not selected_day:
        days = get_available_days()
        selected_day = days[0] if days else date.today().strftime("%Y-%m-%d")
    return jsonify({"day": selected_day, "sessions": get_records_by_day(selected_day)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
