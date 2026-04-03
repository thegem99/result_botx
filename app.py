from flask import Flask, request, render_template_string, Response
import requests
import os
import time
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

API_URL = "https://resultapi.biharboardonline.org/result"
CACHE = {}
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(1):
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
                else: break 
        except Exception: time.sleep(0.3)
    return {"name": "NOT FOUND", "roll_no": str(roll_no), "total": 0, "division": "FAIL", "subjects": {}, "status": "Failed"}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BSEB Analytics Dashboard</title>
    <style>
        :root { --primary: #764ba2; --secondary: #667eea; --accent: #00d2ff; --bg: #0f0f1a; --card: #1e1e2e; }
        body { margin:0; font-family: 'Inter', sans-serif; background: var(--bg); color: white; }
        .hero { height: 100vh; display: flex; align-items: center; justify-content: center; background: radial-gradient(circle at top right, #1a1a3a, #0f0f1a); }
        .glass-card { background: rgba(30, 30, 46, 0.8); backdrop-filter: blur(10px); padding: 40px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); width: 400px; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }
        .dashboard { padding: 20px 50px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-box { background: var(--card); padding: 20px; border-radius: 15px; border-left: 5px solid var(--accent); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .stat-box h4 { margin: 0; opacity: 0.7; font-size: 14px; text-transform: uppercase; }
        .stat-box p { margin: 10px 0 0; font-size: 28px; font-weight: bold; color: var(--accent); }
        .table-container { background: var(--card); border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #252538; padding: 15px; text-align: center; color: var(--accent); cursor: pointer; text-transform: uppercase; letter-spacing: 1px; }
        td { padding: 12px; text-align: center; border-bottom: 1px solid #2d2d3f; }
        tr:hover { background: rgba(255,255,255,0.03); }
        .topper-row { background: rgba(255, 215, 0, 0.1) !important; border-left: 4px solid gold; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .badge-1st { background: #27ae60; } .badge-2nd { background: #f39c12; } .badge-fail { background: #e74c3c; }
        input, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: none; outline: none; }
        input { background: #2d2d3f; color: white; }
        button { background: linear-gradient(to right, var(--secondary), var(--primary)); color: white; font-weight: bold; cursor: pointer; transition: 0.3s; }
        button:hover { opacity: 0.9; transform: scale(1.02); }
        .search-bar { width: 300px; margin-bottom: 20px; float: left; }
        .controls { overflow: hidden; margin-top: 20px; }
    </style>
</head>
<body>
{% if page == 'home' %}
<div class="hero">
<div class="glass-card">
<h1 style="color:var(--accent)">BSEB Pro</h1>
<p>Advanced Result Analytics Portal</p>
<form action="/view" method="get">
<input name="rollcode" placeholder="Roll Code" required>
<input name="rollno" placeholder="Starting Roll No" required>
<input name="count" type="number" value="50">
<button type="submit">GENERATE DASHBOARD</button>
</form>
</div>
</div>
{% else %}
<div class="dashboard">
<h2>School Analysis Dashboard</h2>
<p>Batch: {{ rollcode }} | Results: {{ results|length }}</p>
<table border="1">
{% for r in results %}
<tr><td>{{ r.roll_no }}</td><td>{{ r.name }}</td><td>{{ r.total }}</td></tr>
{% endfor %}
</table>
</div>
{% endif %}
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE, page='home')

@app.route("/view")
def view():
    rollcode = request.args.get("rollcode")
    start_no = int(request.args.get("rollno"))
    count = int(request.args.get("count", 1))
    
    results = []
    roll_list = [str(start_no + i) for i in range(count)]

    # ✅ CHANGE 1: max threads 100
    with ThreadPoolExecutor(max_workers=min(count, 100)) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}

        # ✅ CHANGE 2: stop after 5 fails
        consecutive_fail = 0

        for future in as_completed(futures):
            res = future.result()
            results.append(res)

            if res["status"] == "Failed":
                consecutive_fail += 1
            else:
                consecutive_fail = 0

            if consecutive_fail >= 5:
                break
    
    results.sort(key=lambda x: int(x["roll_no"]))
    
    valid_results = [r for r in results if r['status'] == 'Success']
    top_score = max([r['total'] for r in valid_results]) if valid_results else 0
    passed = len([r for r in valid_results if "FAIL" not in r['division'].upper()])
    div1 = len([r for r in valid_results if "1ST" in r['division'].upper()])
    pass_pct = round((passed / len(results)) * 100, 1) if results else 0
    
    stats = {"top_score": top_score, "pass_pct": pass_pct, "div1": div1}
    CACHE["last_results"] = results
    
    return render_template_string(HTML_TEMPLATE, page='view', results=results, subjects=SUBJECT_LIST, rollcode=rollcode, stats=stats)

@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])
    def generate():
        yield "Roll,Name,Total,Division\n"
        for r in data: yield f"{r['roll_no']},{r['name']},{r['total']},{r['division']}\n"
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=analysis.csv"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
