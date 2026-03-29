from flask import Flask, request, render_template_string, Response
import requests
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

API_URL = "https://examapi.biharboardonline.org/result"
CACHE = {}
# Common subjects for the table headers
SUBJECT_LIST = ["HINDI", "SANSKRIT", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "ENGLISH"]

# ===== SCRAPING / API LOGIC =====
def fetch_result(roll_code, roll_no):
    params = {"roll_code": roll_code, "roll_no": roll_no}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(API_URL, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            json_data = response.json()
            if json_data.get("success"):
                d = json_data["data"]
                # Flatten subject data for easier table rendering
                sub_map = {s["sub_name"]: s["sub_total"] for s in d.get("subjects", [])}
                return {
                    "name": d.get("name"),
                    "father": d.get("father_name"),
                    "roll_no": d.get("roll_no"),
                    "school": d.get("school_name"),
                    "total": d.get("total"),
                    "division": d.get("division"),
                    "subjects": sub_map
                }
    except Exception as e:
        print(f"Error fetching {roll_no}: {e}")
    return None

# ===== STYLES & HTML =====
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>BSEB Result Portal 2026</title>
    <style>
        body { margin:0; font-family:'Segoe UI',sans-serif; background:#121212; color:white; display:flex; flex-direction:column; align-items:center; min-height:100vh; }
        .container { background: #1e1e2e; padding: 30px; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); margin-top: 50px; width: 400px; text-align: center; }
        input, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 6px; border: 1px solid #444; background: #2a2a3d; color: white; box-sizing: border-box; }
        button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; font-weight: bold; cursor: pointer; transition: 0.3s; }
        button:hover { transform: translateY(-2px); opacity: 0.9; }
        h2 { color: #a29bfe; margin-bottom: 20px; }
        table { width: 95%; border-collapse: collapse; margin-top: 20px; background: #1e1e2e; }
        th, td { border: 1px solid #444; padding: 12px; text-align: center; }
        th { background: #34344b; color: #a29bfe; }
        tr:nth-child(even) { background: #252538; }
        .search-box { margin: 20px 0; width: 95%; display: flex; gap: 10px; }
        .search-box input { width: 300px; margin: 0; }
        .btn-small { width: auto; padding: 8px 15px; font-size: 14px; }
    </style>
</head>
<body>
    {% if page == 'home' %}
    <div class="container">
        <h2>BSEB Result Scraper</h2>
        <form action="/view" method="get">
            <input name="rollcode" placeholder="Roll Code (e.g. 51048)" required>
            <input name="rollno" placeholder="Starting Roll No" required>
            <input name="count" type="number" placeholder="Count (Max 50)" value="5">
            <button type="submit">GET BULK RESULTS</button>
        </form>
    </div>
    {% else %}
    <h2>Examination Results</h2>
    <div class="search-box">
        <input type="text" id="srch" placeholder="Filter by Name or Roll No..." onkeyup="filterTable()">
        <a href="/download/csv"><button class="btn-small">CSV</button></a>
        <a href="/download/pdf"><button class="btn-small">PDF</button></a>
        <a href="/"><button class="btn-small" style="background:#444">Back</button></a>
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
            <tr>
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
    start_no = int(request.args.get("rollno"))
    count = int(request.args.get("count", 1))
    
    results = []
    roll_list = [str(start_no + i) for i in range(count)]
    
    with ThreadPoolExecutor(max_workers=min(count,100)) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}
        for future in as_completed(futures):
            res = future.result()
            if res: results.append(res)
    
    results.sort(key=lambda x: int(x["roll_no"]))
    CACHE["last_results"] = results
    
    return render_template_string(HTML_TEMPLATE, page='view', results=results, subjects=SUBJECT_LIST)

@app.route("/download/csv")
def download_csv():
    data = CACHE.get("last_results", [])
    def generate():
        yield "Roll No,Name,Total,Division," + ",".join(SUBJECT_LIST) + "\n"
        for r in data:
            subs = [str(r['subjects'].get(s, r['subjects'].get('M.I.L. '+s, r['subjects'].get('S.I.L. '+s, '')))) for s in SUBJECT_LIST]
            line = f"{r['roll_no']},{r['name']},{r['total']},{r['division']}," + ",".join(subs) + "\n"
            yield line
    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=results.csv"})

@app.route("/download/pdf")
def download_pdf():
    data = CACHE.get("last_results", [])
    buffer = BytesIO()
    canvas_obj = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    canvas_obj.setFont("Helvetica-Bold", 14)
    canvas_obj.drawString(200, 770, "BSEB Examination Result Report")
    canvas_obj.setFont("Helvetica", 8)
    
    header = "Roll No | Name | Total | Div | " + " | ".join(SUBJECT_LIST)
    canvas_obj.drawString(30, y, header)
    y -= 20
    
    for r in data:
        subs = [str(r['subjects'].get(s, r['subjects'].get('M.I.L. '+s, r['subjects'].get('S.I.L. '+s, '-')))) for s in SUBJECT_LIST]
        line = f"{r['roll_no']} | {r['name'][:15]} | {r['total']} | {r['division']} | " + " | ".join(subs)
        canvas_obj.drawString(30, y, line)
        y -= 15
        if y < 50:
            canvas_obj.showPage()
            y = 750
            
    canvas_obj.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={"Content-Disposition":"attachment; filename=results.pdf"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
