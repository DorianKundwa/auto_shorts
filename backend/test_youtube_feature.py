# -*- coding: utf-8 -*-
import sys
import io
import json
from fastapi.testclient import TestClient
from main import app
from database import (
    init_db, save_youtube_config, get_youtube_config,
    save_youtube_token, get_youtube_token, delete_youtube_token,
    record_published_video, get_published_videos
)
from services.youtube_service import YouTubeService

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

client = TestClient(app)

def run_tests():
    print("\n=== Auto Shorts: YouTube Channel Linking & Publishing Tests ===\n")
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

    def cleanup_db():
        import sqlite3
        try:
            conn = sqlite3.connect("auto_shorts.db")
            c = conn.cursor()
            c.execute("DELETE FROM youtube_config WHERE key IN ('client_id', 'client_secret')")
            c.execute("DELETE FROM youtube_tokens WHERE channel_id LIKE 'UC_TEST%'")
            c.execute("DELETE FROM published_videos WHERE job_id='test_job_456'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Cleanup warning: {e}")

    # Ensure clean slate before running tests
    cleanup_db()

    try:
        # 1. Database initialization
        init_db()
        test("Database tables initialized", True)

        # 2. Test invalid client ID rejection / unconfigured status
        res = client.post("/api/youtube/configure", json={
            "client_id": "test-dummy-placeholder",
            "client_secret": "test-secret",
            "redirect_uri": "http://localhost:8000/api/youtube/callback"
        })
        res_invalid_status = client.get("/api/youtube/status")
        test("Invalid Client ID treated as unconfigured", res_invalid_status.json().get("configured") is False)

        # 3. Configure YouTube Client ID & Secret with valid-format mock ID
        mock_client_id = "242796880153-mockclientidforunittest012345.apps.googleusercontent.com"
        res = client.post("/api/youtube/configure", json={
            "client_id": mock_client_id,
            "client_secret": "test-secret-67890",
            "redirect_uri": "http://localhost:8000/api/youtube/callback"
        })
        test("POST /api/youtube/configure", res.status_code == 200, res.json().get("message"))

        # 4. Verify status endpoint
        res = client.get("/api/youtube/status")
        status_data = res.json()
        test("GET /api/youtube/status configured", status_data.get("configured") is True, f"Preview: {status_data.get('client_id_preview')}")

        # 5. Auth URL generation
        res = client.get("/api/youtube/auth-url")
        auth_data = res.json()
        test("GET /api/youtube/auth-url", res.status_code == 200 and "accounts.google.com" in auth_data.get("auth_url", ""), (auth_data.get("auth_url") or "")[:60] + "...")
        test("Auth URL includes youtube.upload scope", "youtube.upload" in (auth_data.get("auth_url") or ""))

        # 6. Title formatting helper
        formatted1 = YouTubeService.format_shorts_title("10x Productivity Secret")
        test("Appends #Shorts to title", formatted1 == "10x Productivity Secret #Shorts", formatted1)

        formatted2 = YouTubeService.format_shorts_title("Already Has #Shorts")
        test("Does not duplicate #Shorts", formatted2 == "Already Has #Shorts", formatted2)

        long_title = "A" * 120
        formatted3 = YouTubeService.format_shorts_title(long_title)
        test("Truncates title to max 100 chars", len(formatted3) <= 100 and formatted3.endswith("#Shorts"), f"len={len(formatted3)}")

        # 7. Token Storage & Retrieval
        fake_token = {
            "access_token": "ya29.fake_token_for_testing",
            "refresh_token": "1//fake_refresh_token",
            "expires_at": 9999999999,
            "scope": "https://www.googleapis.com/auth/youtube.upload"
        }
        save_youtube_token("UC_TEST_CHANNEL_123", "Test Creator Channel", "https://example.com/avatar.jpg", fake_token)
        retrieved = get_youtube_token("UC_TEST_CHANNEL_123")
        test("Token saved and retrieved from SQLite", retrieved is not None and retrieved.get("channel_id") == "UC_TEST_CHANNEL_123")

        # 8. Record and retrieve published video
        rec_id = record_published_video(
            job_id="test_job_456",
            clip_path="output/clip_1.mp4",
            youtube_video_id="dQw4w9WgXcQ",
            youtube_url="https://youtube.com/shorts/dQw4w9WgXcQ",
            title="10x Productivity Secret #Shorts",
            description="Great short description",
            privacy_status="public"
        )
        test("Record published video", bool(rec_id))

        res = client.get("/api/youtube/published")
        pub_list = res.json()
        test("GET /api/youtube/published returns history", len(pub_list) > 0 and pub_list[0]["youtube_video_id"] == "dQw4w9WgXcQ", pub_list[0]["youtube_url"])

        # 9. Disconnect endpoint
        res = client.post("/api/youtube/disconnect")
        test("POST /api/youtube/disconnect", res.status_code == 200)

        res = client.get("/api/youtube/status")
        test("Status reflects disconnected", res.json().get("connected") is False)

    finally:
        # Guarantee cleanup of all test artifacts so live database is never polluted
        cleanup_db()

    print(f"\nResults: {passed}/{total} tests passed.\n")
    return passed == total

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
