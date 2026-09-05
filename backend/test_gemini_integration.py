# -*- coding: utf-8 -*-
import sys
import io
import json
from fastapi.testclient import TestClient
from main import app
from services.llm_providers.gemini_provider import GeminiProvider
from database import init_db, get_job, create_job, update_job

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

client = TestClient(app)

def run_integration_tests():
    print("\n=== Auto Shorts & Gemini API Integration Tests ===\n")
    passed = 0
    total = 0

    def test(name, condition, extra=""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"  [PASS] {name}" + (f" -> {extra}" if extra else ""))
        else:
            print(f"  [FAIL] {name}" + (f" -> {extra}" if extra else ""))

    # 1. Root health check
    res = client.get("/")
    test("Health check GET /", res.status_code == 200, res.json().get("status"))

    # 2. Gemini status endpoint
    res = client.get("/api/gemini/status")
    data = res.json()
    test("GET /api/gemini/status", res.status_code == 200 and data.get("available") is True, f"Model: {data.get('active_model')}")

    # 3. Provider list
    res = client.get("/api/providers")
    prov_data = res.json()
    test("GET /api/providers", res.status_code == 200 and prov_data.get("active") == "Google Gemini", prov_data.get("active"))

    # 4. Direct Gemini analyze_hooks test
    gemini = GeminiProvider()
    test("GeminiProvider is_available()", gemini.is_available())

    test_transcript = (
        "Here is the brutal truth about building a seven figure business that nobody tells you on social media. "
        "Everyone thinks it comes down to brilliant marketing or viral content. But the real secret is unsexy operational discipline. "
        "If your backend systems leak cash, multiplying your traffic only bankrupts you faster."
    )
    hooks = gemini.analyze_hooks(test_transcript, num_clips=1, custom_prompt="Focus on counterintuitive business secrets")
    test("GeminiProvider analyze_hooks() returns clips", bool(hooks and len(hooks) > 0), f"Clips returned: {len(hooks) if hooks else 0}")
    if hooks and len(hooks) > 0:
        h = hooks[0]
        test("Hook contains title", bool(h.get("title")), h.get("title"))
        test("Hook contains hook_category", bool(h.get("hook_category")), h.get("hook_category"))
        test("Hook contains reason (CoT)", bool(h.get("reason")), h.get("reason")[:60] + "...")
        test("Hook contains engagement_score", float(h.get("engagement_score", 0)) > 0, str(h.get("engagement_score")))
        test("Hook contains highlight_words", bool(h.get("highlight_words")), str(h.get("highlight_words")))
        test("Hook contains social_kit", bool(h.get("social_kit")), str(h.get("social_kit", {}).get("headline")))

    # 5. Social Kit Generation Endpoint
    res = client.post("/api/generate-social-kit", json={
        "title": "The Unsexy Secret To 7 Figures",
        "transcript_segment": "Brilliant marketing will bankrupt you faster if your backend leaks cash. Focus on operational discipline."
    })
    kit_data = res.json()
    test("POST /api/generate-social-kit", res.status_code == 200 and "headline" in kit_data, kit_data.get("headline"))
    test("Social kit contains hashtags", isinstance(kit_data.get("hashtags"), list) and len(kit_data.get("hashtags")) > 0)

    # 6. Database schema & metadata storage
    init_db()
    test_id = "test_gemini_job_123"
    create_job(test_id, "test_video.mp4", "processing", 10, "Testing Gemini DB")
    update_job(test_id, status="review_ready", metadata={"gemini_tested": True, "candidates": hooks})
    job = get_job(test_id)
    test("Database stores and retrieves job", job is not None and job.get("status") == "review_ready")
    test("Database preserves metadata_json", job.get("metadata", {}).get("gemini_tested") is True)

    print(f"\nResults: {passed}/{total} tests passed.\n")
    return passed == total

if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
