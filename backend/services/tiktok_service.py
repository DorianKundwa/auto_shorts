import os
import time
import json
import hashlib
import secrets
import base64
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

TIKTOK_AUTH_URL    = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL   = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_REVOKE_URL  = "https://open.tiktokapis.com/v2/oauth/revoke/"
TIKTOK_USER_URL    = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_UPLOAD_URL  = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL  = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

TIKTOK_SCOPES = [
    "user.info.basic",
    "video.publish",
    "video.upload",
]


class TikTokService:
    """
    TikTok Content Posting API v2 — OAuth 2.0 (PKCE) channel linking and
    direct video publishing via the TikTok Open Platform.

    Prerequisites (user must supply):
      - app_key   : Client Key from TikTok Developer portal
      - app_secret: Client Secret from TikTok Developer portal
      - Redirect URI must be registered in the TikTok app settings

    References:
      https://developers.tiktok.com/doc/oauth-user-access-token-management/
      https://developers.tiktok.com/doc/content-posting-api-get-started/
    """

    # ── PKCE helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Return (code_verifier, code_challenge) for PKCE OAuth flow."""
        code_verifier  = secrets.token_urlsafe(64)
        digest         = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return code_verifier, code_challenge

    # ── Auth URL ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_auth_url(
        app_key:       str,
        redirect_uri:  str,
        code_verifier: str,
        state:         str = "auto_shorts_tiktok_oauth",
    ) -> str:
        """Construct the TikTok OAuth 2.0 consent URL with PKCE."""
        digest         = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        scope_str = ",".join(TIKTOK_SCOPES)
        params = (
            f"client_key={app_key}"
            f"&scope={scope_str}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
        return f"{TIKTOK_AUTH_URL}?{params}"

    # ── Code Exchange ─────────────────────────────────────────────────────────

    @staticmethod
    def exchange_code(
        code:          str,
        code_verifier: str,
        app_key:       str,
        app_secret:    str,
        redirect_uri:  str,
    ) -> Dict[str, Any]:
        """Exchange authorization code for access & refresh tokens."""
        payload = {
            "client_key":     app_key,
            "client_secret":  app_secret,
            "code":           code,
            "grant_type":     "authorization_code",
            "redirect_uri":   redirect_uri,
            "code_verifier":  code_verifier,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(TIKTOK_TOKEN_URL, data=payload, headers=headers, timeout=20)
        if resp.status_code != 200:
            raise ValueError(
                f"TikTok token exchange failed: HTTP {resp.status_code} — {resp.text}"
            )

        data = resp.json()
        if data.get("error"):
            raise ValueError(
                f"TikTok token error: {data.get('error')} — {data.get('error_description')}"
            )

        token_data = data.get("data", data)
        expires_in = token_data.get("expires_in", 86400)
        token_data["expires_at"] = time.time() + expires_in
        return token_data

    # ── Token Refresh ─────────────────────────────────────────────────────────

    @staticmethod
    def refresh_access_token(
        token_data:  Dict[str, Any],
        app_key:     str,
        app_secret:  str,
    ) -> Dict[str, Any]:
        """Refresh the TikTok access token if it's near expiry (< 60s remaining)."""
        now        = time.time()
        expires_at = token_data.get("expires_at", 0)

        if expires_at - now > 60 and token_data.get("access_token"):
            return token_data

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise ValueError("No TikTok refresh token available. Please re-authorise.")

        payload = {
            "client_key":    app_key,
            "client_secret": app_secret,
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(TIKTOK_TOKEN_URL, data=payload, headers=headers, timeout=20)

        if resp.status_code == 200:
            new_data = resp.json().get("data", resp.json())
            token_data["access_token"] = new_data.get("access_token", token_data["access_token"])
            expires_in = new_data.get("expires_in", 86400)
            token_data["expires_at"] = time.time() + expires_in
            if new_data.get("refresh_token"):
                token_data["refresh_token"] = new_data["refresh_token"]
        else:
            print(f"[TikTokService] Token refresh failed: HTTP {resp.status_code} — {resp.text}")

        return token_data

    # ── User Profile ──────────────────────────────────────────────────────────

    @staticmethod
    def get_creator_info(access_token: str) -> Dict[str, Any]:
        """
        Fetch the authenticated TikTok creator's profile info.
        Returns open_id, display_name, avatar_url.
        """
        fields = "open_id,union_id,avatar_url,display_name,username"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }
        resp = requests.get(
            f"{TIKTOK_USER_URL}?fields={fields}",
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(
                f"TikTok user info fetch failed: HTTP {resp.status_code} — {resp.text}"
            )

        data = resp.json()
        if data.get("error", {}).get("code") and data["error"]["code"] != "ok":
            raise ValueError(
                f"TikTok user info error: {data['error'].get('message', 'Unknown error')}"
            )

        user_data = data.get("data", {}).get("user", {})
        return {
            "open_id":      user_data.get("open_id", ""),
            "display_name": user_data.get("display_name", "TikTok Creator"),
            "username":     user_data.get("username", ""),
            "avatar_url":   user_data.get("avatar_url", ""),
        }

    # ── Video Upload ──────────────────────────────────────────────────────────

    @classmethod
    def upload_video(
        cls,
        video_path:    str,
        title:         str,
        privacy_level: str,          # "SELF_ONLY" | "MUTUAL_FOLLOW_FRIENDS" | "FOLLOWER_OF_CREATOR" | "PUBLIC_TO_EVERYONE"
        token_data:    Dict[str, Any],
        app_key:       str,
        app_secret:    str,
        disable_duet:  bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
    ) -> Dict[str, Any]:
        """
        Upload a video to TikTok using the Content Posting API v2.
        Uses FILE_UPLOAD source type (direct binary upload).

        Returns: { "publish_id": str, "share_url": str }
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = os.path.getsize(video_path)
        if file_size <= 0:
            raise ValueError("Video file is empty (0 bytes).")

        # Refresh token if needed
        token_data    = cls.refresh_access_token(token_data, app_key, app_secret)
        access_token  = token_data.get("access_token")
        if not access_token:
            raise ValueError("Missing valid TikTok access token.")

        # Clamp title to 150 chars (TikTok limit)
        title = (title or "Check this out!").strip()[:150]

        # Valid privacy levels
        valid_privacy = {
            "SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS",
            "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE",
        }
        if privacy_level not in valid_privacy:
            privacy_level = "PUBLIC_TO_EVERYONE"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        }

        # Step 1: Initialize upload session
        init_payload = {
            "post_info": {
                "title":            title,
                "privacy_level":    privacy_level,
                "disable_duet":     disable_duet,
                "disable_stitch":   disable_stitch,
                "disable_comment":  disable_comment,
            },
            "source_info": {
                "source":          "FILE_UPLOAD",
                "video_size":      file_size,
                "chunk_size":      file_size,   # single-chunk upload
                "total_chunk_count": 1,
            },
        }

        init_resp = requests.post(
            TIKTOK_UPLOAD_URL,
            headers=headers,
            json=init_payload,
            timeout=30,
        )

        if init_resp.status_code not in (200, 201):
            raise ValueError(
                f"TikTok upload init failed: HTTP {init_resp.status_code} — {init_resp.text}"
            )

        init_data = init_resp.json()
        if init_data.get("error", {}).get("code") and init_data["error"]["code"] != "ok":
            raise ValueError(
                f"TikTok upload init error: {init_data['error'].get('message')}"
            )

        publish_id = init_data.get("data", {}).get("publish_id")
        upload_url = init_data.get("data", {}).get("upload_url")

        if not publish_id or not upload_url:
            raise ValueError(f"TikTok did not return publish_id/upload_url: {init_data}")

        # Step 2: Upload the video binary
        with open(video_path, "rb") as vf:
            upload_headers = {
                "Content-Type":  "video/mp4",
                "Content-Length": str(file_size),
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            }
            upload_resp = requests.put(
                upload_url,
                headers=upload_headers,
                data=vf,
                timeout=300,
            )

        if upload_resp.status_code not in (200, 201, 204):
            raise ValueError(
                f"TikTok video chunk upload failed: HTTP {upload_resp.status_code} — {upload_resp.text}"
            )

        # Step 3: Poll for processing status (up to 60s)
        share_url = f"https://www.tiktok.com/"
        for _ in range(12):
            time.sleep(5)
            status_resp = requests.post(
                TIKTOK_STATUS_URL,
                headers=headers,
                json={"publish_id": publish_id},
                timeout=20,
            )
            if status_resp.status_code == 200:
                status_data = status_resp.json().get("data", {})
                process_status = status_data.get("status", "")
                if process_status == "PUBLISH_COMPLETE":
                    share_url = status_data.get("publicaly_available_post_id", [""])[0]
                    if share_url:
                        share_url = f"https://www.tiktok.com/@me/video/{share_url}"
                    else:
                        share_url = "https://www.tiktok.com/foryou"
                    break
                elif process_status in ("FAILED", "SPAM_RISK_TOO_MANY_POSTS"):
                    fail_reason = status_data.get("fail_reason", "Unknown reason")
                    raise ValueError(f"TikTok post failed: {fail_reason}")

        return {
            "success":    True,
            "publish_id": publish_id,
            "share_url":  share_url,
            "title":      title,
            "privacy":    privacy_level,
        }
