import requests
import os
import time

BASE_URL = "http://127.0.0.1:8000"

def test_health():
    print("Testing GET / ...")
    response = requests.get(f"{BASE_URL}/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Auto Shorts API running"}
    print("Health check passed.")

def test_upload():
    print("Testing POST /api/upload ...")
    test_video = r"c:\Users\admin\Documents\auto_shorts\test\YTDown.com_YouTube_What-If-Every-Animal-Could-Talk_Media_842JVnH8qE0_001_1080p.mp4"
    if not os.path.exists(test_video):
        print(f"Error: test video {test_video} not found!")
        return None

    with open(test_video, "rb") as f:
        files = {"file": ("test_video.mp4", f, "video/mp4")}
        data = {"font": "Montserrat-Black.ttf", "destinations": "TikTok"}
        
        response = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
        
    assert response.status_code == 200
    res_data = response.json()
    assert "job_id" in res_data
    assert "upload successful" in res_data["message"].lower()
    
    job_id = res_data["job_id"]
    print(f"Upload passed! Job ID: {job_id}")
    return job_id

def test_status(job_id):
    print(f"Testing GET /api/status/{job_id} ...")
    response = requests.get(f"{BASE_URL}/api/status/{job_id}")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["job_id"] == job_id
    print(f"Status check passed. Current status: {res_data['status']}")
    
def test_jobs_list(job_id):
    print("Testing GET /api/jobs ...")
    response = requests.get(f"{BASE_URL}/api/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert isinstance(jobs, list)
    job_ids = [j["job_id"] for j in jobs]
    assert job_id in job_ids
    print(f"Jobs list passed. Found {len(jobs)} jobs in history.")

if __name__ == "__main__":
    # Wait for server to be fully up
    time.sleep(2)
    test_health()
    job_id = test_upload()
    if job_id:
        # Check status immediately
        time.sleep(1)
        test_status(job_id)
        test_jobs_list(job_id)
    print("All backend API tests completed successfully!")
