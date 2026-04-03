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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BSEB Analytics Dashboard</title>
    <style>
        :root { --primary: #764ba2; --secondary: #667eea; --accent: #00d2ff; --bg: #0f0f1a; --card: #1e1e2e; }
        body { margin:0; font-family: 'Inter', sans-serif; background: var(--bg); color: white; }
        
        /* Home Page Styling */
        .hero { height: 100vh; display: flex; align-items: center; justify-content: center; background: radial-gradient(circle at top right, #1a1a3a, #0f0f1a); }
        .glass-card { background: rgba(30, 30, 46, 0.8); backdrop-filter: blur(10px); padding: 40px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); width: 400px; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }
        
        /* Dashboard Styling */
        .dashboard { padding: 20px 50px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-box { background: var(--card); padding: 20px; border-radius: 15px; border-left: 5px solid var(--accent); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .stat-box h4 { margin: 0; opacity: 0.7; font-size: 14px; text-transform: uppercase; }
        .stat-box p { margin: 10px 0 0; font-size: 28px; font-weight: bold; color: var(--accent); }

        /* Table Styling */
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
                <input name="count" type="number" placeholder="Batch Size" value="50">
                <button type="submit">GENERATE DASHBOARD</button>
            </form>
        </div>
    </div>
    {% else %}
    <div class="dashboard">
        <h2 style="margin-bottom:5px;">School Analysis Dashboard</h2>
        <p style="opacity:0.6; margin-bottom:30px;">Batch: {{ rollcode }} | Results: {{ results|length }}</p>

        <div class="stats-grid">
            <div class="stat-box"><h4>Total Students</h4><p>{{ results|length }}</p></div>
            <div class="stat-box" style="border-left-color: #27ae60;"><h4>Pass %</h4><p>{{ stats.pass_pct }}%</p></div>
            <div class="stat-box" style="border-left-color: gold;"><h4>Highest Score</h4><p>{{ stats.top_score }}</p></div>
            <div class="stat-box" style="border-left-color: #f39c12;"><h4>1st Divisions</h4><p>{{ stats.div1 }}</p></div>
        </div>

        <div class="controls">
            <input type="text" id="srch" class="search-bar" placeholder="Search by name or roll..." onkeyup="filterTable()">
            <div style="float:right">
                <a href="/download/csv"><button style="width:auto; padding:8px 20px;">Download CSV</button></a>
                <a href="/"><button style="width:auto; padding:8px 20px; background:#444">New Search</button></a>
            </div>
        </div>

        <div class="table-container">
            <table id="resTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Roll No</th>
                        <th onclick="sortTable(1)">Student Name</th>
                        <th onclick="sortTable(2)">Total</th>
                        <th onclick="sortTable(3)">Division</th>
                        {% for sub in subjects %} <th onclick="sortTable({{ loop.index + 3 }})">{{ sub }}</th> {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    {% for r in results %}
                    <tr class="{% if r.total == stats.top_score and r.total > 0 %}topper-row{% endif %}">
                        <td>{{ r.roll_no }}</td>
                        <td style="text-align:left; padding-left:20px;">
                            {{ r.name }} 
                            {% if r.total == stats.top_score and r.total > 0 %} 🏆 {% endif %}
                        </td>
                        <td><b>{{ r.total }}</b></td>
                        <td>
                            <span class="badge badge-{{ '1st' if '1ST' in r.division.upper() else '2nd' if '2ND' in r.division.upper() else 'fail' }}">
                                {{ r.division }}
                            </span>
                        </td>
                        {% for sub in subjects %}
                        <td>{{ r.subjects.get('M.I.L. ' + sub, r.subjects.get('S.I.L. ' + sub, r.subjects.get(sub, '-'))) }}</td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function filterTable() {
            let val = document.getElementById('srch').value.toLowerCase();
            let rows = document.querySelector('#resTable tbody').rows;
            for (let row of rows) {
                row.style.display = row.innerText.toLowerCase().includes(val) ? '' : 'none';
            }
        }
        function sortTable(n) {
            const table = document.getElementById("resTable");
            let rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            switching = true; dir = "asc";
            while (switching) {
                switching = false; rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {
                    shouldSwitch = false;
                    x = rows[i].getElementsByTagName("TD")[n];
                    y = rows[i + 1].getElementsByTagName("TD")[n];
                    let xV = x.innerText.toLowerCase(); let yV = y.innerText.toLowerCase();
                    if (!isNaN(parseFloat(xV))) { xV = parseFloat(xV); yV = parseFloat(yV); }
                    if (dir == "asc" ? xV > yV : xV < yV) { shouldSwitch = true; break; }
                }
                if (shouldSwitch) { rows[i].parentNode.insertBefore(rows[i + 1], rows[i]); switching = true; switchcount++; }
                else if (switchcount == 0 && dir == "asc") { dir = "desc"; switching = true; }
            }
        }
    </script>
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
    with ThreadPoolExecutor(max_workers=min(count,100)) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}
        for future in as_completed(futures):
            results.append(future.result())
    
    results.sort(key=lambda x: int(x["roll_no"]))
    
    # --- Data Analysis ---
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
