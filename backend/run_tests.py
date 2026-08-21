# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
"""
Auto Shorts — API Test Suite
Requires the backend server to be running on http://127.0.0.1:8000
"""
import requests
import json
import sys

BASE = "http://127.0.0.1:8000"
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

errors = []

def check(name, condition, detail=""):
    if condition:
        print(f"  {PASS}  {name}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  {FAIL}  {name}" + (f"  ({detail})" if detail else ""))
        errors.append(name)

print("\n=== Auto Shorts API Test Suite ===\n")

# Test 1: Health
print("1. Health check")
try:
    r = requests.get(f"{BASE}/")
    check("GET /  -> 200", r.status_code == 200, f"status={r.status_code}")
    body = r.json()
    check("response body correct", body == {"status": "ok", "message": "Auto Shorts API running"}, str(body))
except Exception as e:
    check("GET /  -> 200", False, str(e))

# Test 2: Jobs list
print("\n2. Jobs list")
jobs = []
try:
    r = requests.get(f"{BASE}/api/jobs")
    check("GET /api/jobs -> 200", r.status_code == 200, f"status={r.status_code}")
    jobs = r.json()
    check("response is a list", isinstance(jobs, list), f"type={type(jobs).__name__}")
    check("each job has required keys", all(
        {"job_id","filename","status","progress","message","clips"} <= j.keys()
        for j in jobs
    ), f"{len(jobs)} jobs")
    print(f"       Found {len(jobs)} job(s) in the database")
except Exception as e:
    check("GET /api/jobs -> 200", False, str(e))

# Test 3: Status of an existing job
print("\n3. Job status endpoint")
if jobs:
    job_id = jobs[0]["job_id"]
    try:
        r = requests.get(f"{BASE}/api/status/{job_id}")
        check("GET /api/status/<id> -> 200", r.status_code == 200, f"status={r.status_code}")
        data = r.json()
        check("job_id matches", data.get("job_id") == job_id)
        check("status field present", "status" in data, data.get("status"))
        check("progress field present", "progress" in data, str(data.get("progress")) + "%")
        check("clips field is list", isinstance(data.get("clips"), list))
        print(f"       job {job_id[:8]}...  status={data['status']}  progress={data['progress']}%")
    except Exception as e:
        check("GET /api/status/<id> -> 200", False, str(e))
else:
    print(f"  {WARN}  No existing jobs -- skipping status check")

# Test 4: 404 on unknown job
print("\n4. Error handling")
try:
    r = requests.get(f"{BASE}/api/status/nonexistent-job-id")
    check("GET /api/status/<invalid> -> 404", r.status_code == 404, f"status={r.status_code}")
except Exception as e:
    check("GET /api/status/<invalid> -> 404", False, str(e))

# Test 5: Invalid file type upload
print("\n5. Upload validation")
try:
    files = {"file": ("bad.txt", b"hello", "text/plain")}
    data = {"font": "Montserrat-Black.ttf", "destinations": "TikTok"}
    r = requests.post(f"{BASE}/api/upload", files=files, data=data)
    check("Upload .txt -> 400", r.status_code == 400, f"status={r.status_code}")
except Exception as e:
    check("Upload .txt -> 400", False, str(e))

# Summary
print("\n" + "="*40)
if errors:
    print(f"{FAIL} {len(errors)} test(s) FAILED:")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)
else:
    print(f"{PASS} All tests PASSED!")
    sys.exit(0)
