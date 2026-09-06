import os
import time
import json
import requests
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()

META_AUTH_URL    = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL   = "https://graph.facebook.com/v19.0/oauth/access_token"
META_GRAPH_URL   = "https://graph.facebook.com/v19.0"

# Scopes required for Instagram Content Publishing
META_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_read_engagement",
    "business_management",
]


class InstagramService:
    """
    Meta Graph API service for Instagram Reels / short-form video publishing.

    Flow:
      1. User authorises via Facebook Login (OAuth 2.0).
      2. Short-lived token is exchanged for a long-lived token (60 days).
      3. Long-lived token is used to fetch the linked Instagram Business/Creator account.
      4. Reel is published using the two-step container + publish approach.

    Prerequisites (user must supply):
      - app_id     : Meta App ID from developers.facebook.com
      - app_secret : Meta App Secret
      - Redirect URI must be registered as a Valid OAuth Redirect URI in the Meta App

    References:
      https://developers.facebook.com/docs/instagram-api/reference/ig-user/media
      https://developers.facebook.com/docs/instagram-api/guides/content-publishing
    """

    # ── Auth URL ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_auth_url(
        app_id:       str,
        redirect_uri: str,
        state:        str = "auto_shorts_instagram_oauth",
    ) -> str:
        """Construct the Facebook Login OAuth dialog URL for Instagram publishing scopes."""
        scope_str = ",".join(META_SCOPES)
        return (
            f"{META_AUTH_URL}?"
            f"client_id={app_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope_str}"
            f"&response_type=code"
            f"&state={state}"
        )

    # ── Code Exchange ─────────────────────────────────────────────────────────

    @staticmethod
    def exchange_code(
        code:         str,
        app_id:       str,
        app_secret:   str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """
        Exchange short-lived auth code for a short-lived token, then immediately
        upgrade it to a long-lived token (~60 days).
        """
        # Step 1: Short-lived token
        short_resp = requests.get(
            META_TOKEN_URL,
            params={
                "client_id":     app_id,
                "client_secret": app_secret,
                "redirect_uri":  redirect_uri,
                "code":          code,
            },
            timeout=20,
        )
        if short_resp.status_code != 200:
            raise ValueError(
                f"Meta token exchange failed: HTTP {short_resp.status_code} — {short_resp.text}"
            )

        short_data = short_resp.json()
        if "error" in short_data:
            raise ValueError(
                f"Meta token error: {short_data['error'].get('message', 'Unknown error')}"
            )

        short_token = short_data.get("access_token")
        if not short_token:
            raise ValueError("Meta did not return a short-lived access token.")

        # Step 2: Upgrade to long-lived token
        ll_resp = requests.get(
            f"{META_GRAPH_URL}/oauth/access_token",
            params={
                "grant_type":        "fb_exchange_token",
                "client_id":         app_id,
                "client_secret":     app_secret,
                "fb_exchange_token": short_token,
            },
            timeout=20,
        )

        if ll_resp.status_code != 200:
            # Fall back to short-lived token
            token_data = short_data.copy()
            token_data["expires_at"] = time.time() + short_data.get("expires_in", 3600)
            return token_data

        ll_data = ll_resp.json()
        if "error" in ll_data:
            token_data = short_data.copy()
            token_data["expires_at"] = time.time() + short_data.get("expires_in", 3600)
            return token_data

        ll_token = ll_data.get("access_token", short_token)
        expires_in = ll_data.get("expires_in", 5184000)   # ~60 days default
        token_data = {
            "access_token": ll_token,
            "token_type":   ll_data.get("token_type", "bearer"),
            "expires_in":   expires_in,
            "expires_at":   time.time() + expires_in,
        }
        return token_data

    # ── Token Refresh ─────────────────────────────────────────────────────────

    @staticmethod
    def refresh_long_lived_token(
        token_data: Dict[str, Any],
        app_id:     str,
        app_secret: str,
    ) -> Dict[str, Any]:
        """
        Long-lived tokens can be refreshed within their validity window.
        Refresh if less than 7 days remain.
        """
        now        = time.time()
        expires_at = token_data.get("expires_at", 0)
        seven_days = 7 * 24 * 3600

        if expires_at - now > seven_days:
            return token_data

        access_token = token_data.get("access_token")
        if not access_token:
            return token_data

        resp = requests.get(
            f"{META_GRAPH_URL}/oauth/access_token",
            params={
                "grant_type":        "fb_exchange_token",
                "client_id":         app_id,
                "client_secret":     app_secret,
                "fb_exchange_token": access_token,
            },
            timeout=20,
        )

        if resp.status_code == 200:
            new_data = resp.json()
            if "access_token" in new_data:
                token_data["access_token"] = new_data["access_token"]
                expires_in = new_data.get("expires_in", 5184000)
                token_data["expires_at"] = time.time() + expires_in
        else:
            print(f"[InstagramService] Long-lived token refresh failed: HTTP {resp.status_code}")

        return token_data

    # ── User Profile ──────────────────────────────────────────────────────────

    @staticmethod
    def get_user_profile(access_token: str) -> Dict[str, Any]:
        """
        Fetch Facebook user info, then find the linked Instagram Business/Creator account.
        Returns ig_user_id, username, avatar, name.
        """
        # Step 1: Get Facebook user ID
        me_resp = requests.get(
            f"{META_GRAPH_URL}/me",
            params={"fields": "id,name,picture.type(large)", "access_token": access_token},
            timeout=15,
        )
        if me_resp.status_code != 200:
            raise ValueError(
                f"Meta /me endpoint failed: HTTP {me_resp.status_code} — {me_resp.text}"
            )

        me_data  = me_resp.json()
        if "error" in me_data:
            raise ValueError(f"Meta /me error: {me_data['error'].get('message')}")

        fb_user_id = me_data.get("id")
        fb_name    = me_data.get("name", "Instagram User")
        fb_avatar  = me_data.get("picture", {}).get("data", {}).get("url", "")

        # Step 2: Get Pages managed by this user
        pages_resp = requests.get(
            f"{META_GRAPH_URL}/{fb_user_id}/accounts",
            params={"access_token": access_token, "fields": "id,name,instagram_business_account"},
            timeout=15,
        )
        if pages_resp.status_code != 200:
            raise ValueError(
                f"Meta /accounts failed: HTTP {pages_resp.status_code} — {pages_resp.text}"
            )

        pages_data = pages_resp.json()
        pages = pages_data.get("data", [])

        ig_user_id  = None
        ig_username = None
        ig_avatar   = fb_avatar
        ig_name     = fb_name
        page_token  = None

        for page in pages:
            ig_biz = page.get("instagram_business_account")
            if ig_biz:
                ig_user_id = ig_biz.get("id")
                page_id    = page.get("id")

                # Get page-scoped token
                page_token_resp = requests.get(
                    f"{META_GRAPH_URL}/{page_id}",
                    params={"fields": "access_token", "access_token": access_token},
                    timeout=10,
                )
                if page_token_resp.status_code == 200:
                    page_token = page_token_resp.json().get("access_token", access_token)

                # Get IG profile details
                ig_resp = requests.get(
                    f"{META_GRAPH_URL}/{ig_user_id}",
                    params={
                        "fields":       "id,username,name,profile_picture_url",
                        "access_token": page_token or access_token,
                    },
                    timeout=10,
                )
                if ig_resp.status_code == 200:
                    ig_data     = ig_resp.json()
                    ig_username = ig_data.get("username", fb_name)
                    ig_name     = ig_data.get("name", fb_name)
                    ig_avatar   = ig_data.get("profile_picture_url", fb_avatar)
                break

        if not ig_user_id:
            raise ValueError(
                "No Instagram Business or Creator account found linked to this Facebook profile. "
                "Please connect an Instagram Business/Creator account to a Facebook Page first."
            )

        return {
            "ig_user_id":  ig_user_id,
            "username":    ig_username or fb_name,
            "name":        ig_name,
            "avatar":      ig_avatar,
            "page_token":  page_token or access_token,
        }

    # ── Reel Publishing ───────────────────────────────────────────────────────

    @classmethod
    def publish_reel(
        cls,
        video_url:    str,          # Publicly accessible URL of the video file
        caption:      str,
        token_data:   Dict[str, Any],
        app_id:       str,
        app_secret:   str,
        ig_user_id:   str,
        page_token:   str,
    ) -> Dict[str, Any]:
        """
        Publish a Reel to Instagram using the two-step container approach.

        NOTE: The Instagram Graph API does NOT support direct binary upload — it
        requires a publicly accessible video URL. The backend serves output videos
        via the /output static route, so callers must pass the public URL.

        Returns: { "post_id": str, "permalink": str }
        """
        if not video_url:
            raise ValueError("A publicly accessible video URL is required for Instagram Reels.")

        # Refresh token if near expiry
        token_data   = cls.refresh_long_lived_token(token_data, app_id, app_secret)
        access_token = page_token or token_data.get("access_token")
        if not access_token:
            raise ValueError("Missing valid Instagram/Meta access token.")

        caption = (caption or "Check this out!").strip()[:2200]

        # Step 1: Create media container (Reel)
        container_resp = requests.post(
            f"{META_GRAPH_URL}/{ig_user_id}/media",
            data={
                "video_url":   video_url,
                "caption":     caption,
                "media_type":  "REELS",
                "access_token": access_token,
            },
            timeout=60,
        )

        if container_resp.status_code not in (200, 201):
            raise ValueError(
                f"Instagram media container creation failed: HTTP {container_resp.status_code} — {container_resp.text}"
            )

        container_data = container_resp.json()
        if "error" in container_data:
            raise ValueError(
                f"Instagram container error: {container_data['error'].get('message')}"
            )

        container_id = container_data.get("id")
        if not container_id:
            raise ValueError(f"Instagram did not return a container ID: {container_data}")

        # Step 2: Poll until container is ready (FINISHED status)
        for attempt in range(24):  # Up to 2 minutes
            time.sleep(5)
            status_resp = requests.get(
                f"{META_GRAPH_URL}/{container_id}",
                params={
                    "fields":       "status_code,status",
                    "access_token": access_token,
                },
                timeout=15,
            )
            if status_resp.status_code == 200:
                status_data   = status_resp.json()
                status_code   = status_data.get("status_code", "")
                if status_code == "FINISHED":
                    break
                elif status_code in ("ERROR", "EXPIRED"):
                    raise ValueError(
                        f"Instagram container processing failed: {status_data.get('status', status_code)}"
                    )

        # Step 3: Publish the container
        publish_resp = requests.post(
            f"{META_GRAPH_URL}/{ig_user_id}/media_publish",
            data={
                "creation_id":  container_id,
                "access_token": access_token,
            },
            timeout=30,
        )

        if publish_resp.status_code not in (200, 201):
            raise ValueError(
                f"Instagram publish failed: HTTP {publish_resp.status_code} — {publish_resp.text}"
            )

        publish_data = publish_resp.json()
        if "error" in publish_data:
            raise ValueError(
                f"Instagram publish error: {publish_data['error'].get('message')}"
            )

        post_id = publish_data.get("id")
        if not post_id:
            raise ValueError(f"Instagram did not return a post ID: {publish_data}")

        # Step 4: Fetch permalink
        permalink = f"https://www.instagram.com/"
        try:
            perm_resp = requests.get(
                f"{META_GRAPH_URL}/{post_id}",
                params={"fields": "permalink", "access_token": access_token},
                timeout=10,
            )
            if perm_resp.status_code == 200:
                permalink = perm_resp.json().get("permalink", permalink)
        except Exception:
            pass

        return {
            "success":   True,
            "post_id":   post_id,
            "permalink": permalink,
        }
