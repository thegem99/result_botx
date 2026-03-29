from flask import Flask, request, render_template_string, Response
import requests
import os
import time
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Configuration
API_URL = "https://examapi.biharboardonline.org/result"
CACHE = {}
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

# ===== API LOGIC WITH 5-ATTEMPT RETRY =====
def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for attempt in range(5):
        try:
            # Increased timeout slightly for large batches
            response = requests.get(API_URL, params=params, headers=headers, timeout=15)
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
                        "total": d.get("total"),
                        "division": d.get("division"),
                        "subjects": sub_map,
                        "status": "Success"
                    }
                else:
                    break 
        except Exception as e:
            time.sleep(1) # Back off for 1 second
            
    return {
        "name": "NOT FOUND",
        "father": "-",
        "roll_no": str(roll_no),
        "school": "-",
        "total": "-",
        "division": "-",
        "subjects": {},
        "status": "Failed"
    }

# ===== UI TEMPLATE =====
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>BSEB Bulk Scraper</title>
    <style>
        body { margin:0; font-family:'Segoe UI',sans-serif; background:#0f0f1a; color:white; display:flex; flex-direction:column; align-items:center; min-height:100vh; }
        .container { background: #1e1e2e; padding: 30px; border-radius: 12px; margin-top: 50px; width: 420px; text-align: center; border: 1px solid #333; }
        input, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 6px; border: 1px solid #444; background: #2a2a3d; color: white; box-sizing: border-box; }
        button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; font-weight: bold; cursor: pointer; }
        h2 { color: #a29bfe; }
        table { width: 98%; border-collapse: collapse; margin: 20px 0; background: #1e1e2e; font-size: 13px; }
        th, td { border: 1px solid #333; padding: 8px; text-align: center; }
        th { background: #34344b; color: #a29bfe; }
        .status-failed { color: #ff7675; }
        .res-header { width: 95%; display: flex; justify-content: space-between; align-items: center; margin-top: 20px; }
        .search-bar { padding: 8px; width: 250px; border-radius: 15px; border: 1px solid #444; background: #1e1e2e; color: white; }
    </style>
</head>
<body>
    {% if page == 'home' %}
    <div class="container">
        <h2>BSEB School Scraper</h2>
        <form action="/view" method="get">
            <input name="rollcode" placeholder="Roll Code" required>
            <input name="rollno" placeholder="Starting Roll Number" required>
            <input name="count" type="number" placeholder="Number of Students (e.g., 500)" value="100">
            <button type="submit">Start School Scan</button>
        </form>
    </div>
    {% else %}
    <div class="res-header">
        <h3>Results for Code: {{ rollcode }}</h3>
        <input type="text" id="srch" class="search-bar" placeholder="Filter list..." onkeyup="filterTable()">
        <div>
            <a href="/download/csv"><button style="width:auto; padding:5px 10px;">CSV</button></a>
            <a href="/download/pdf"><button style="width:auto; padding:5px 10px;">PDF</button></a>
            <a href="/"><button style="width:auto; padding:5px 10px; background:#444">Back</button></a>
        </div>
    </div>
    <table id="resTable">
        <thead>
            <tr>
                <th>Roll No</th>
                <th>Name</th>
                <th>Total</th>
                <th>Division</th>
                {% for sub in subjects %} <th>{{ sub }}</th> {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for r in results %}
            <tr class="{% if r.status == 'Failed' %}status-failed{% endif %}">
                <td>{{ r.roll_no }}</td>
                <td>{{ r.name }}</td>
                <td><b>{{ r.total }}</b></td>
                <td>{{ r.division }}</td>
                {% for sub in subjects %}
                <td>{{ r.subjects.get('M.I.L. ' + sub, r.subjects.get('S.I.L. ' + sub, r.subjects.get(sub, '-'))) }}</td>
                {% endfor %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
    <script>
        function filterTable() {
            let val = document.getElementById('srch').value.toLowerCase();
            let rows = document.querySelector('#resTable tbody').rows;
            for (let row of rows) {
                row.style.display = row.innerText.toLowerCase().includes(val) ? '' : 'none';
            }
        }
    </script>
    {% endif %}
</body>
</html>
"""

# ===== ROUTES =====
@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE, page='home')

@app.route("/view")
def view():
    rollcode = request.args.get("rollcode")
    try:
        start_no = int(request.args.get("rollno"))
        # Removed Max limit, but set default to 1 if empty
        count = int(request.args.get("count", 1))
    except (ValueError, TypeError):
        return "Please enter valid numbers."

    results = []
    roll_list = [str(start_no + i) for i in range(count)]
    
    # Using 50 workers for better speed on large school scans
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}
        for future in as_completed(futures):
            res = future.result()
            if res: results.append(res)
    
    results.sort(key=lambda x: int(x["roll_no"]))
    CACHE["last_results"] = results
    
    return render_template_string(HTML_TEMPLATE, page='view', results=results, subjects=SUBJECT_LIST, rollcode=rollcode)

@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])
    def generate():
        yield "Roll No,Name,Father,Total,Division," + ",".join(SUBJECT_LIST) + "\n"
        for r in data:
            subs = [str(r['subjects'].get(s, r['subjects'].get('M.I.L. '+s, r['subjects'].get('S.I.L. '+s, '')))) for s in SUBJECT_LIST]
            line = f"{r['roll_no']},{r['name']},{r['father']},{r['total']},{r['division']}," + ",".join(subs) + "\n"
            yield line
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=school_results.csv"})

@app.route("/download/pdf")
def download_pdf():
    data = CACHE.get("last_results", [])
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    p.setFont("Helvetica-Bold", 12)
    p.drawString(30, 770, f"BSEB Result Report - Batch Scan")
    p.setFont("Helvetica", 7)
    
    header = "Roll No | Name | Total | Div | " + " | ".join(SUBJECT_LIST)
    p.drawString(30, y, header)
    y -= 15
    
    for r in data:
        subs = [str(r['subjects'].get(s, r['subjects'].get('M.I.L. '+s, r['subjects'].get('S.I.L. '+s, '-')))) for s in SUBJECT_LIST]
        line = f"{r['roll_no']} | {r['name'][:15]} | {r['total']} | {r['division']} | " + " | ".join(subs)
        p.drawString(30, y, line)
        y -= 12
        if y < 40:
            p.showPage()
            p.setFont("Helvetica", 7)
            y = 750
            
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={"Content-Disposition":"attachment; filename=school_results.pdf"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
