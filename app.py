from flask import Flask, request, render_template_string, Response
import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

app = Flask(__name__)

API_URL = "https://resultapi.biharboardonline.org/result"
CACHE = {}
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]


def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(API_URL, params=params, headers=headers, timeout=12)
        if response.status_code == 200:
            json_data = response.json()
            if json_data.get("success") and json_data.get("data"):
                d = json_data["data"]
                sub_map = {s["sub_name"]: s["sub_total"] for s in d.get("subjects", [])}
                return {
                    "name": d.get("name"),
                    "father": d.get("father_name"),
                    "roll_no": str(d.get("roll_no")),
                    "school": d.get("school_name"),
                    "total": int(d.get("total") or 0),
                    "division": d.get("division"),
                    "subjects": sub_map,
                    "status": "Success"
                }
    except Exception:
        time.sleep(0.3)

    return {
        "name": "NOT FOUND",
        "roll_no": str(roll_no),
        "total": 0,
        "division": "FAIL",
        "subjects": {},
        "status": "Failed"
    }


@app.route("/")
def home():
    return render_template_string("<h2>Server Running ✅</h2>")


@app.route("/view")
def view():
    rollcode = request.args.get("rollcode")
    start_no = int(request.args.get("rollno"))
    count = int(request.args.get("count", 1))

    results = []
    consecutive_fail = 0

    max_workers = 100
    in_flight = set()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        next_roll = start_no
        submitted = 0

        # Initial fill
        while submitted < min(count, max_workers):
            future = executor.submit(fetch_result, rollcode, str(next_roll))
            in_flight.add(future)
            next_roll += 1
            submitted += 1

        while in_flight:
            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)

            for future in done:
                res = future.result()
                results.append(res)

                # Track consecutive failures
                if res["status"] == "Failed":
                    consecutive_fail += 1
                else:
                    consecutive_fail = 0

                # Stop condition
                if consecutive_fail >= 5:
                    print("Stopped early: 5 consecutive NOT FOUND")
                    in_flight.clear()
                    break

                # Submit next task if limit not reached
                if submitted < count:
                    future_new = executor.submit(fetch_result, rollcode, str(next_roll))
                    in_flight.add(future_new)
                    next_roll += 1
                    submitted += 1

    results.sort(key=lambda x: int(x["roll_no"]))

    # --- Data Analysis ---
    valid_results = [r for r in results if r['status'] == 'Success']
    top_score = max([r['total'] for r in valid_results]) if valid_results else 0
    passed = len([r for r in valid_results if "FAIL" not in r['division'].upper()])
    div1 = len([r for r in valid_results if "1ST" in r['division'].upper()])
    pass_pct = round((passed / len(results)) * 100, 1) if results else 0

    stats = {
        "top_score": top_score,
        "pass_pct": pass_pct,
        "div1": div1
    }

    CACHE["last_results"] = results

    return {
        "total_results": len(results),
        "top_score": top_score,
        "pass_percentage": pass_pct,
        "first_divisions": div1
    }


@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])

    def generate():
        yield "Roll,Name,Total,Division\n"
        for r in data:
            yield f"{r['roll_no']},{r['name']},{r['total']},{r['division']}\n"

    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=analysis.csv"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
