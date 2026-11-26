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
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import redact
from .feeds import CTX

# Meta's apps created after 2025 use "API setup with Unified login": a system-user token that never
# expires, on graph.facebook.com. Older Instagram-login tokens live on graph.instagram.com.
HOST = os.environ.get("IG_API_HOST", "https://graph.facebook.com")
SYSTEM_TOKEN = "graph.facebook.com" in HOST
VERSION = os.environ.get("IG_API_VERSION", "v27.0")


class IGError(RuntimeError):
    pass


class VideoRejected(IGError):
    """A video container failed (ERROR, EXPIRED or never ready) before anything was published, so the post can
    still go out as stills in the same attempt."""


ALT_REJECTED = re.compile(r"alt_text|invalid parameter|\(#100\)", re.I)


class Client:
    def __init__(self, token=None, user_id=None, opener=urllib.request.urlopen):
        self.token = token or os.environ.get("IG_TOKEN", "")
        self.user_id = user_id or os.environ.get("IG_USER_ID", "")
        self.opener = opener
        if not self.token or not self.user_id:
            raise IGError("IG_TOKEN and IG_USER_ID must be set")

    def _scrub(self, text):
        return redact.scrub((text or "").replace(self.token, "<token>"))

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

    def image_item(self, image_url, alt_text=None):
        """alt_text (up to 1,000 characters) is accepted on a single image or an image in a carousel, not on
        Reels or Stories: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
        (added 2025-03-24 per the content-publishing changelog). Alt text is an extra: if Instagram refuses the
        field, the image is created without it rather than losing the post."""
        params = {"image_url": image_url, "is_carousel_item": "true"}
        if alt_text:
            try:
                return self.call("POST", f"{self.user_id}/media", {**params, "alt_text": alt_text})["id"]
            except IGError as e:
                if not ALT_REJECTED.search(str(e)):
                    raise
        return self.call("POST", f"{self.user_id}/media", params)["id"]

    def video_item(self, video_url, thumb_offset=None):
        """A carousel child video (media_type=VIDEO, is_carousel_item). Spec: MP4/MOV, H.264 or HEVC, closed GOP,
        4:2:0, AAC up to 48 kHz, 23-60 fps, 3-60 s, 100 MB; thumb_offset in ms picks the cover frame (ig-user/media
        reference, read 2026-11-27). The carousel crops every child to the first child's aspect: our card is 4:5."""
        params = {"media_type": "VIDEO", "video_url": video_url, "is_carousel_item": "true"}
        if thumb_offset is not None:
            params["thumb_offset"] = str(int(thumb_offset))
        return self.call("POST", f"{self.user_id}/media", params)["id"]

    def _video_ready(self, container, sleep):
        """Video is processed on Meta's side: up to six minutes. Any failure here comes before a publish call."""
        try:
            self.wait(container, tries=12, pause=30, sleep=sleep)
        except IGError as e:
            raise VideoRejected(str(e)) from None

    def carousel(self, children, caption):
        return self.call("POST", f"{self.user_id}/media",
                         {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]

    def single(self, image_url, caption, alt_text=None):
        params = {"image_url": image_url, "caption": caption}
        if alt_text:
            try:
                return self.call("POST", f"{self.user_id}/media", {**params, "alt_text": alt_text})["id"]
            except IGError as e:
                if not ALT_REJECTED.search(str(e)):
                    raise
        return self.call("POST", f"{self.user_id}/media", params)["id"]

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

    def recent_media(self, limit=25):
        """The account's newest feed posts, newest first. The duplicate check reads this before every publish."""
        return self.call("GET", f"{self.user_id}/media",
                         {"fields": "id,caption,timestamp,permalink,comments_count", "limit": limit}).get("data", [])

    def quota(self):
        rows = self.call("GET", f"{self.user_id}/content_publishing_limit", {"fields": "quota_usage,config"}).get("data", [])
        return rows[0] if rows else {}

    def reel(self, video_url, caption, share_to_feed=True, trial="", sleep=time.sleep, cover_url=None):
        """A Reel from a public MP4. Returns (media_id, permalink). share_to_feed true shows it on the grid and
        in Feed as well as the Reels tab. trial ("MANUAL" or "SS_PERFORMANCE", the graduation_strategy) makes it a
        trial Reel shown to non-followers first; an account that cannot post trial Reels gets a normal one, since the
        refusal comes at container creation, before anything is published. cover_url: a public JPEG for the Reels
        tab (9:16; the feed shows its middle square). Both parameters and the video spec (MP4/MOV without edit lists,
        moov first, H.264 or HEVC, AAC up to 48 kHz, 23-60 fps, 3 s to 15 min, 9:16 recommended) are in
        https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media
        and the trial_params section of the content-publishing guide. Video is processed on Meta's side, so the
        wait is longer than for an image."""
        params = {"media_type": "REELS", "video_url": video_url, "caption": caption,
                  "share_to_feed": "true" if share_to_feed else "false"}
        if cover_url:
            params["cover_url"] = cover_url
        try:
            c = self.call("POST", f"{self.user_id}/media", {**params, **({"trial_params": json.dumps({"graduation_strategy": trial})} if trial else {})})["id"]
        except IGError as e:
            # Meta does not document the refusal an account gets when it cannot post trial Reels, so any refusal
            # of a trial container earns one try as a normal Reel
            if not trial:
                raise VideoRejected(str(e)) from None
            try:
                c = self.call("POST", f"{self.user_id}/media", params)["id"]
            except IGError as e2:
                raise VideoRejected(str(e2)) from None
        self._video_ready(c, sleep)
        media = self.publish(c)
        try:
            link = self.permalink(media)
        except IGError:
            link = ""
        return media, link

    def post_carousel(self, image_urls, caption, sleep=time.sleep, alt_texts=None, video_first=None, thumb_offset=None):
        """Returns (media_id, permalink). One image goes up as a single post. alt_texts: one string per image.
        video_first: a public MP4 that takes the first image's place (the video card); if its container fails,
        VideoRejected is raised before anything is published."""
        alts = list(alt_texts or [])
        if len(image_urls) == 1 and not video_first:
            c = self.single(image_urls[0], caption, alts[0] if alts else None)
        else:
            if video_first:
                try:
                    first = self.video_item(video_first, thumb_offset)
                except IGError as e:
                    raise VideoRejected(str(e)) from None
                self._video_ready(first, sleep)
                kids = [first] + [self.image_item(u, alts[i] if i < len(alts) else None) for i, u in enumerate(image_urls[:20]) if i > 0]
            else:
                kids = [self.image_item(u, alts[i] if i < len(alts) else None) for i, u in enumerate(image_urls[:20])]
            for k in kids[1 if video_first else 0:]:
                self.wait(k, sleep=sleep)
            c = self.carousel(kids, caption)
        self.wait(c, sleep=sleep)
        media = self.publish(c)
        try:
            link = self.permalink(media)
        except IGError:
            link = ""  # the post is live; losing its id here would make the desk publish it again
        return media, link

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

    def token_expiry(self):
        """When IG_TOKEN stops working, from Meta's debug_token (a token may inspect itself):
        expires_at and data_access_expires_at as {"expires", "data_access"} UTC datetimes (None: no end reported,
        as for a system-user token). refresh() assumes a token on graph.facebook.com never expires; this is what checks that."""
        from datetime import datetime, timezone
        got = self.call("GET", "debug_token", {"input_token": self.token}).get("data", {})
        # expires_at 0 means the token itself never expires; data_access_expires_at is the separate 90-day window
        # after which Meta stops returning user data until someone re-authorises the app. Both are reported, apart.
        at = lambda k: datetime.fromtimestamp(got[k], timezone.utc) if got.get(k) else None  # noqa: E731
        return {"expires": at("expires_at"), "data_access": at("data_access_expires_at")}

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
