@app.route("/view")
def view():
    rollcode = request.args.get("rollcode")
    start_no = int(request.args.get("rollno"))
    count = int(request.args.get("count", 1))
    
    results = []
    roll_list = [str(start_no + i) for i in range(count)]

    # ✅ CHANGE 1: 200 → 100
    with ThreadPoolExecutor(max_workers=min(count,100)) as executor:
        futures = {executor.submit(fetch_result, rollcode, rn): rn for rn in roll_list}
        
        # ✅ CHANGE 2: consecutive fail logic
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
    
    # --- Data Analysis ---
    valid_results = [r for r in results if r['status'] == 'Success']
    top_score = max([r['total'] for r in valid_results]) if valid_results else 0
    passed = len([r for r in valid_results if "FAIL" not in r['division'].upper()])
    div1 = len([r for r in valid_results if "1ST" in r['division'].upper()])
    pass_pct = round((passed / len(results)) * 100, 1) if results else 0
    
    stats = {"top_score": top_score, "pass_pct": pass_pct, "div1": div1}
    CACHE["last_results"] = results
    
    return render_template_string(HTML_TEMPLATE, page='view', results=results, subjects=SUBJECT_LIST, rollcode=rollcode, stats=stats)
