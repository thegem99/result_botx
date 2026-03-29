from flask import Flask, request, render_template_string, Response
import requests
import os
import time
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

API_URL = "https://examapi.biharboardonline.org/result"
CACHE = {}
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(5):
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=12)
            if response.status_code == 200:
                json_data = response.json()
                if json_data.get("success") and json_data.get("data"):
                    d = json_data["data"]
                    sub_map = {s["sub_name"]: s["sub_total"] for s in d.get("subjects", [])}
                    return {
                        "name": d.get("name"),
                        "roll_no": str(d.get("roll_no")),
                        "total": int(d.get("total") or 0),
                        "division": d.get("division").upper(),
                        "subjects": sub_map,
                        "status": "Success"
                    }
                else: break 
        except Exception: time.sleep(0.3)
    return {"name": "NOT FOUND", "roll_no": str(roll_no), "total": 0, "division": "FAIL", "subjects": {}, "status": "Failed"}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BSEB Medal Dashboard</title>
    <style>
        :root { --gold: #FFD700; --silver: #C0C0C0; --bronze: #CD7F32; --fail: #ff4d4d; --bg: #0a0a12; --card: #161625; }
        body { margin:0; font-family: 'Segoe UI', system-ui; background: var(--bg); color: white; padding: 20px; }
        
        /* Stats Bar */
        .stats-container { display: flex; gap: 15px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat-card { background: var(--card); flex: 1; min-width: 150px; padding: 20px; border-radius: 15px; text-align: center; border-bottom: 4px solid #333; transition: 0.3s; }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-card h3 { margin: 0; font-size: 12px; opacity: 0.6; text-transform: uppercase; }
        .stat-card p { margin: 10px 0 0; font-size: 24px; font-weight: bold; }
        
        /* Specific Medal Borders */
        .border-gold { border-color: var(--gold); color: var(--gold); box-shadow: 0 0 15px rgba(255, 215, 0, 0.1); }
        .border-silver { border-color: var(--silver); color: var(--silver); }
        .border-bronze { border-color: var(--bronze); color: var(--bronze); }
        .border-fail { border-color: var(--fail); color: var(--fail); }

        /* Table Medals */
        .medal-icon { font-size: 18px; margin-right: 8px; }
        .row-1st { background: rgba(255, 215, 0, 0.05) !important; }
        .row-2nd { background: rgba(192, 192, 192, 0.05) !important; }
        .row-3rd { background: rgba(205, 127, 50, 0.05) !important; }

        table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 12px; overflow: hidden; }
        th { background: #1f1f35; padding: 15px; color: #a29bfe; cursor: pointer; text-align: center; }
        td { padding: 12px; text-align: center; border-bottom: 1px solid #252538; }
        
        .hero-input { background: var(--card); padding: 40px; border-radius: 20px; width: 400px; margin: 100px auto; text-align: center; border: 1px solid #333; }
        input { width: 90%; padding: 12px; margin: 10px 0; border-radius: 8px; border: 1px solid #444; background: #0a0a12; color: white; }
        button { width: 95%; padding: 12px; background: linear-gradient(45deg, #667eea, #764ba2); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    {% if page == 'home' %}
    <div class="hero-input">
        <h1 style="color:#a29bfe">BSEB Analytics</h1>
        <form action="/view" method="get">
            <input name="rollcode" placeholder="Roll Code" required>
            <input name="rollno" placeholder="Start Roll No" required>
            <input name="count" type="number" value="100">
            <button type="submit">GENERATE REPORT</button>
        </form>
    </div>
    {% else %}
    <h2>School Performance: {{ rollcode }}</h2>
    
    <div class="stats-container">
        <div class="stat-card border-gold"><h3>Gold (1st Div)</h3><p>{{ stats.div1 }}</p></div>
        <div class="stat-card border-silver"><h3>Silver (2nd Div)</h3><p>{{ stats.div2 }}</p></div>
        <div class="stat-card border-bronze"><h3>Bronze (3rd Div)</h3><p>{{ stats.div3 }}</p></div>
        <div class="stat-card border-fail"><h3>Failures</h3><p>{{ stats.fail }}</p></div>
        <div class="stat-card" style="border-color:#a29bfe"><h3>Total Students</h3><p>{{ results|length }}</p></div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Roll No</th>
                <th>Student</th>
                <th>Total Marks</th>
                <th>Medal/Div</th>
                {% for sub in subjects %} <th>{{ sub }}</th> {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for r in results %}
            {% set div = r.division %}
            <tr class="{% if '1ST' in div %}row-1st{% elif '2ND' in div %}row-2nd{% elif '3RD' in div %}row-3rd{% endif %}">
                <td>{{ r.roll_no }}</td>
                <td style="text-align:left">
                    {% if '1ST' in div %}<span class="medal-icon">🥇</span>
                    {% elif '2ND' in div %}<span class="medal-icon">🥈</span>
                    {% elif '3RD' in div %}<span class="medal-icon">🥉</span>
                    {% else %}<span class="medal-icon">❌</span>{% endif %}
                    {{ r.name }}
                </td>
                <td><b>{{ r.total }}</b></td>
                <td style="font-weight:bold; color: {% if '1ST' in div %}var(--gold){% elif '2ND' in div %}var(--silver){% elif '3RD' in div %}var(--bronze){% else %}var(--fail){% endif %}">
                    {{ div }}
                </td>
                {% for sub in subjects %}
                <td>{{ r.subjects.get('M.I.L. ' + sub, r.subjects.get('S.I.L. ' + sub, r.subjects.get(sub, '-'))) }}</td>
                {% endfor %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
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
    with ThreadPoolExecutor(max_workers=min(200,count)) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}
        for future in as_completed(futures):
            results.append(future.result())
    
    results.sort(key=lambda x: int(x["roll_no"]))
    
    # Advanced Stats
    stats = {
        "div1": len([r for r in results if "1ST" in r['division']]),
        "div2": len([r for r in results if "2ND" in r['division']]),
        "div3": len([r for r in results if "3RD" in r['division']]),
        "fail": len([r for r in results if "FAIL" in r['division']])
    }
    
    return render_template_string(HTML_TEMPLATE, page='view', results=results, subjects=SUBJECT_LIST, rollcode=rollcode, stats=stats)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
