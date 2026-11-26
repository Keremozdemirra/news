"""Instagram API with Instagram Login: the few calls the desk needs. Standard library only.

The token lives in the IG_TOKEN environment variable (a GitHub Actions secret) and
nowhere else. It is sent as a Bearer header, never in a URL, and every error
message is scrubbed of it before it can reach a log, because the repository and
its Action logs are public.

Docs read 2026-11-26: developers.facebook.com/docs/instagram-platform/content-publishing
(host graph.instagram.com, JPEG only, carousel up to 20 items, status_code polling).
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .feeds import CTX

# Meta's apps created after 2025 use "API setup with Unified login": a system-user token that never
# expires, on graph.facebook.com. Older Instagram-login tokens live on graph.instagram.com.
HOST = os.environ.get("IG_API_HOST", "https://graph.facebook.com")
SYSTEM_TOKEN = "graph.facebook.com" in HOST
VERSION = os.environ.get("IG_API_VERSION", "v27.0")


class IGError(RuntimeError):
    pass


class Client:
    def __init__(self, token=None, user_id=None, opener=urllib.request.urlopen):
        self.token = token or os.environ.get("IG_TOKEN", "")
        self.user_id = user_id or os.environ.get("IG_USER_ID", "")
        self.opener = opener
        if not self.token or not self.user_id:
            raise IGError("IG_TOKEN and IG_USER_ID must be set")

    def _scrub(self, text):
        return (text or "").replace(self.token, "<token>")

    def call(self, method, path, params=None, versioned=True):
        url = f"{HOST}/{VERSION}/{path}" if versioned else f"{HOST}/{path}"
        data = None
        if method == "GET" and params:
            url += "?" + urllib.parse.urlencode(params)
        elif params:
            data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.token}"})
        try:
            with self.opener(req, timeout=60, context=CTX) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise IGError(self._scrub(f"{method} {path}: HTTP {e.code}: {body[:400]}")) from None
        except urllib.error.URLError as e:
            raise IGError(self._scrub(f"{method} {path}: {e.reason}")) from None

    # publishing

    def image_item(self, image_url):
        return self.call("POST", f"{self.user_id}/media", {"image_url": image_url, "is_carousel_item": "true"})["id"]

    def carousel(self, children, caption):
        return self.call("POST", f"{self.user_id}/media",
                         {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]

    def single(self, image_url, caption):
        return self.call("POST", f"{self.user_id}/media", {"image_url": image_url, "caption": caption})["id"]

    def story(self, image_url, sleep=time.sleep, user_tags=None):
        """A 1080x1920 image story. Returns the media id. Stories carry no caption and no link via the API;
        user_tags ([{"username": ..., "x": 0.5, "y": 0.5}], supported on stories since July 2025) mentions an account."""
        params = {"media_type": "STORIES", "image_url": image_url}
        if user_tags:
            params["user_tags"] = json.dumps(user_tags)
        c = self.call("POST", f"{self.user_id}/media", params)["id"]
        self.wait(c, sleep=sleep)
        return self.publish(c)

    def wait(self, container, tries=6, pause=30, sleep=time.sleep):
        # Meta's advice: poll once a minute for at most five minutes; images finish sooner
        for _ in range(tries):
            status = self.call("GET", container, {"fields": "status_code"}).get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return status
            if status in ("ERROR", "EXPIRED"):
                raise IGError(f"container {container}: {status}")
            sleep(pause)
        raise IGError(f"container {container}: not ready after {tries * pause}s")

    def publish(self, container):
        return self.call("POST", f"{self.user_id}/media_publish", {"creation_id": container})["id"]

    def permalink(self, media_id):
        return self.call("GET", media_id, {"fields": "permalink"}).get("permalink", "")

    def quota(self):
        rows = self.call("GET", f"{self.user_id}/content_publishing_limit", {"fields": "quota_usage,config"}).get("data", [])
        return rows[0] if rows else {}

    def post_carousel(self, image_urls, caption, sleep=time.sleep):
        """Returns (media_id, permalink). One image goes up as a single post."""
        if len(image_urls) == 1:
            c = self.single(image_urls[0], caption)
        else:
            kids = [self.image_item(u) for u in image_urls[:20]]
            for k in kids:
                self.wait(k, sleep=sleep)
            c = self.carousel(kids, caption)
        self.wait(c, sleep=sleep)
        media = self.publish(c)
        return media, self.permalink(media)

    # comments

    def comments(self, media_id):
        got = self.call("GET", f"{media_id}/comments", {"fields": "id,text,username,timestamp,replies{username}"})
        return got.get("data", [])

    def reply(self, comment_id, message):
        return self.call("POST", f"{comment_id}/replies", {"message": message})["id"]

    def private_reply(self, comment_id, text):
        """One DM to the person who wrote a comment: Meta's private replies, allowed once per comment within
        7 days. Needs instagram_business_manage_messages."""
        return self.call("POST", f"{self.user_id}/messages",
                         {"recipient": json.dumps({"comment_id": comment_id}), "message": json.dumps({"text": text})})

    def delete(self, media_id):
        """Remove a post or story from the account. Meta answers {"success": true} when it is gone."""
        return self.call("DELETE", media_id).get("success", False)

    def own_username(self):
        # "me" is the system user under a unified-login token, so ask the Instagram account itself
        return self.call("GET", self.user_id, {"fields": "username"}).get("username", "")

    # insights

    def media_insights(self, media_id, metrics=("reach", "saved", "shares", "likes", "comments", "views")):
        """One call per metric, so a metric Meta renamed or retired costs only itself."""
        out = {}
        for m in metrics:
            try:
                rows = self.call("GET", f"{media_id}/insights", {"metric": m}).get("data", [])
                if rows and rows[0].get("values"):
                    out[m] = rows[0]["values"][0].get("value")
                elif rows and "total_value" in rows[0]:
                    out[m] = rows[0]["total_value"].get("value")
            except IGError as e:
                out.setdefault("_errors", []).append(str(e)[:160])
        return out

    def followers(self):
        return self.call("GET", self.user_id, {"fields": "followers_count,media_count"})

    # token

    def refresh(self):
        """Extends a long-lived token by 60 days. Returns seconds until expiry; the token itself is not returned.
        A system-user token never expires, so there is nothing to refresh."""
        if SYSTEM_TOKEN:
            return {"expires_in": 10 ** 9, "changed": False}
        got = self.call("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, versioned=False)
        if got.get("access_token") and got["access_token"] != self.token:
            # the stored secret must be replaced by hand; the new value never goes to a log
            return {"expires_in": got.get("expires_in"), "changed": True}
        return {"expires_in": got.get("expires_in"), "changed": False}
