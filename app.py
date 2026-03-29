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
# Standard subjects to display in the table
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

# ===== API LOGIC WITH 5-ATTEMPT RETRY =====
def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Try up to 5 times for a single roll number
    for attempt in range(5):
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=12)
            if response.status_code == 200:
                json_data = response.json()
                if json_data.get("success") and json_data.get("data"):
                    d = json_data["data"]
                    # Map subjects: The API uses names like "M.I.L. HINDI"
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
                    # If API says success is false, the roll number likely doesn't exist
                    break 
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed for {roll_no}: {e}")
            time.sleep(1) # Wait before retrying
            
    # Fallback: If 5 attempts fail or result not found, return blank data to keep sorting intact
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
    <title>BSEB Result Portal 2026</title>
    <style>
        body { margin:0; font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background:#0f0f1a; color:white; display:flex; flex-direction:column; align-items:center; min-height:100vh; }
        .container { background: #1e1e2e; padding: 30px; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); margin-top: 50px; width: 420px; text-align: center; border: 1px solid #333; }
        input, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 6px; border: 1px solid #444; background: #2a2a3d; color: white; box-sizing: border-box; font-size: 16px; }
        input:focus { border-color: #764ba2; outline: none; box-shadow: 0 0 8px rgba(118, 75, 162, 0.4); }
        button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; font-weight: bold; cursor: pointer; transition: 0.3s; text-transform: uppercase; }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.3); }
        h2 { color: #a29bfe; margin-bottom: 20px; letter-spacing: 1px; }
        .res-header { width: 95%; display: flex; justify-content: space-between; align-items: center; margin-top: 30px; }
        table { width: 98%; border-collapse: collapse; margin: 20px 0; background: #1e1e2e; border-radius: 8px; overflow: hidden; font-size: 14px; }
        th, td { border: 1px solid #333; padding: 12px; text-align: center; }
        th { background: #34344b; color: #a29bfe; font-weight: 600; }
        tr:hover { background: #252538; }
        .status-failed { color: #ff7675; font-weight: bold; }
        .search-bar { padding: 10px; width: 300px; border-radius: 20px; border: 1px solid #444; background: #1e1e2e; color: white; }
        .btn-group { display: flex; gap: 10px; }
        .btn-small { width: auto; padding: 8px 15px; font-size: 13px; }
    </style>
</head>
<body>
    {% if page == 'home' %}
    <div class="container">
        <h2>BSEB Result Portal</h2>
        <form action="/view" method="get">
            <input name="rollcode" placeholder="Roll Code (e.g., 51048)" required>
            <input name="rollno" placeholder="Starting Roll Number" required>
            <input name="count" type="number" placeholder="How many students?" value="10" min="1" max="100">
            <button type="submit">Fetch Results</button>
        </form>
    </div>
    {% else %}
    <div class="res-header">
        <h2>Results Sheet</h2>
        <input type="text" id="srch" class="search-bar" placeholder="Search Name/Roll..." onkeyup="filterTable()">
        <div class="btn-group">
            <a href="/download/csv"><button class="btn-small">Export CSV</button></a>
            <a href="/download/pdf"><button class="btn-small">Export PDF</button></a>
            <a href="/"><button class="btn-small" style="background:#444">New Search</button></a>
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
                {# Checking for names with prefixes like M.I.L. or S.I.L. #}
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
        count = int(request.args.get("count", 1))
    except (ValueError, TypeError):
        return "Invalid input. Please enter numbers for Roll No and Count."

    results = []
    roll_list = [str(start_no + i) for i in range(count)]
    
    # Use ThreadPool to fetch concurrently
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
    
    # Important: Strict numerical sorting by roll number
    results.sort(key=lambda x: int(x["roll_no"]))
    CACHE["last_results"] = results
    
    return render_template_string(HTML_TEMPLATE, page='view', results=results, subjects=SUBJECT_LIST)

@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])
    def generate():
        yield "Roll No,Name,Father,Total,Division," + ",".join(SUBJECT_LIST) + "\n"
        for r in data:
            subs = [str(r['subjects'].get(s, r['subjects'].get('M.I.L. '+s, r['subjects'].get('S.I.L. '+s, '')))) for s in SUBJECT_LIST]
            line = f"{r['roll_no']},{r['name']},{r['father']},{r['total']},{r['division']}," + ",".join(subs) + "\n"
            yield line
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=bseb_results.csv"})

@app.route("/download/pdf")
def download_pdf():
    data = CACHE.get("last_results", [])
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    p.setFont("Helvetica-Bold", 14)
    p.drawString(200, 770, "BSEB Examination Result Report")
    p.setFont("Helvetica", 8)
    
    header = "Roll No | Name | Total | Div | " + " | ".join(SUBJECT_LIST)
    p.drawString(30, y, header)
    y -= 20
    
    for r in data:
        subs = [str(r['subjects'].get(s, r['subjects'].get('M.I.L. '+s, r['subjects'].get('S.I.L. '+s, '-')))) for s in SUBJECT_LIST]
        line = f"{r['roll_no']} | {r['name'][:15]} | {r['total']} | {r['division']} | " + " | ".join(subs)
        p.drawString(30, y, line)
        y -= 15
        if y < 50:
            p.showPage()
            y = 750
            
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={"Content-Disposition":"attachment; filename=bseb_results.pdf"})

if __name__ == "__main__":
    # Get port from environment for deployment, fallback to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
