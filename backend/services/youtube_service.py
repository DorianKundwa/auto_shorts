import os
import time
import json
import requests
from typing import Dict, Any, Optional, List, Tuple
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeService:
    """Service handling YouTube OAuth 2.0 channel linking and direct Shorts publishing."""

    @staticmethod
    def get_auth_url(client_id: str, redirect_uri: str, state: str = "auto_shorts_oauth") -> str:
        """Construct the Google OAuth 2.0 consent URL for YouTube scopes."""
        scope_str = "+".join(SCOPES)
        return (
            f"{OAUTH_AUTH_URL}?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"scope={scope_str}&"
            f"access_type=offline&"
            f"prompt=consent&"
            f"state={state}"
        )

    @staticmethod
    def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(OAUTH_TOKEN_URL, data=payload, headers=headers, timeout=20)
        if resp.status_code != 200:
            raise ValueError(f"Failed to exchange code: HTTP {resp.status_code} - {resp.text}")

        data = resp.json()
        expires_in = data.get("expires_in", 3600)
        data["expires_at"] = time.time() + expires_in
        return data

    @staticmethod
    def refresh_access_token(token_data: Dict[str, Any], client_id: str, client_secret: str) -> Dict[str, Any]:
        """Check token expiry and refresh access token if needed."""
        now = time.time()
        expires_at = token_data.get("expires_at", 0)

        # If token still valid for more than 60s, return as-is
        if expires_at - now > 60 and token_data.get("access_token"):
            return token_data

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            return token_data

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(OAUTH_TOKEN_URL, data=payload, headers=headers, timeout=20)
        if resp.status_code == 200:
            new_data = resp.json()
            token_data["access_token"] = new_data["access_token"]
            expires_in = new_data.get("expires_in", 3600)
            token_data["expires_at"] = time.time() + expires_in
        else:
            print(f"[YouTubeService] Token refresh failed: HTTP {resp.status_code} - {resp.text}")

        return token_data

    @staticmethod
    def get_channel_profile(access_token: str) -> Dict[str, Any]:
        """Fetch linked YouTube channel details (title, handle, thumbnail, subscriber count)."""
        url = f"{YOUTUBE_API_BASE}/channels?part=snippet,statistics&mine=true"
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise ValueError(f"Failed to fetch YouTube channel profile: HTTP {resp.status_code} - {resp.text}")

        data = resp.json()
        items = data.get("items", [])
        if not items:
            raise ValueError("No YouTube channel found for the authorized Google account.")

        channel = items[0]
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})

        avatar = (
            thumbnails.get("default", {}).get("url") or
            thumbnails.get("medium", {}).get("url") or
            ""
        )

        return {
            "channel_id": channel.get("id"),
            "title": snippet.get("title", "My YouTube Channel"),
            "custom_url": snippet.get("customUrl", ""),
            "avatar": avatar,
            "subscriber_count": stats.get("subscriberCount", "0"),
        }

    @staticmethod
    def format_shorts_title(raw_title: str) -> str:
        """Format title to guarantee #Shorts tag and strict length <= 100 chars."""
        clean_title = (raw_title or "Viral Short").strip()
        if "#Shorts" not in clean_title and "#shorts" not in clean_title.lower():
            clean_title = f"{clean_title} #Shorts"

        if len(clean_title) > 100:
            tag = " #Shorts"
            max_len = 100 - len(tag)
            clean_title = clean_title[:max_len].strip() + tag

        return clean_title

    @classmethod
    def upload_short(
        cls,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str,
        token_data: Dict[str, Any],
        client_id: str,
        client_secret: str,
    ) -> Dict[str, Any]:
        """
        Upload a video file to YouTube as a Short using resumable upload protocol.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at {video_path}")

        file_size = os.path.getsize(video_path)
        if file_size <= 0:
            raise ValueError("Video file is empty (0 bytes).")

        # Refresh token if needed
        token_data = cls.refresh_access_token(token_data, client_id, client_secret)
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Missing valid YouTube OAuth access token.")

        formatted_title = cls.format_shorts_title(title)
        privacy = privacy_status.lower() if privacy_status else "public"
        if privacy not in ("public", "unlisted", "private"):
            privacy = "public"

        # Ensure description references #Shorts for discovery
        if "#Shorts" not in description and "#shorts" not in description.lower():
            description = f"{description}\n\n#Shorts #YouTubeShorts"

        metadata_payload = {
            "snippet": {
                "title": formatted_title,
                "description": description,
                "tags": tags or ["Shorts", "Viral"],
                "categoryId": "22",  # People & Blogs / Entertainment
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        # Step 1: Initiate Resumable Upload Session
        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        }
        init_url = f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status"

        init_resp = requests.post(
            init_url,
            headers=init_headers,
            json=metadata_payload,
            timeout=30,
        )

        if init_resp.status_code not in (200, 201):
            raise ValueError(
                f"Failed to initiate YouTube upload session: HTTP {init_resp.status_code} - {init_resp.text}"
            )

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            raise ValueError("YouTube did not return a resumable upload Location URL.")

        # Step 2: Upload Video File Content in Chunks (or full stream)
        with open(video_path, "rb") as video_file:
            upload_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
            }
            upload_resp = requests.put(
                upload_url,
                headers=upload_headers,
                data=video_file,
                timeout=300,  # Allow up to 5 min for large uploads
            )

        if upload_resp.status_code not in (200, 201):
            raise ValueError(
                f"YouTube video upload stream failed: HTTP {upload_resp.status_code} - {upload_resp.text}"
            )

        resp_json = upload_resp.json()
        video_id = resp_json.get("id")
        if not video_id:
            raise ValueError(f"YouTube response missing video ID: {resp_json}")

        youtube_url = f"https://youtube.com/shorts/{video_id}"

        return {
            "success": True,
            "video_id": video_id,
            "youtube_url": youtube_url,
            "title": formatted_title,
            "privacy_status": privacy,
        }
