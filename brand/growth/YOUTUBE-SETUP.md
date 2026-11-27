# Connect the YouTube channel (once, about 10 minutes)

Uploads go to https://www.youtube.com/@boardread through the YouTube Data API. The desk asks for one permission,
`youtube.upload`: it can upload videos and nothing else. It cannot read, edit or delete videos, and it cannot comment.

## 1. Google Cloud project

1. Open https://console.cloud.google.com/ while signed in as the Google account that owns @boardread.
2. Top bar, project picker: **New project**, name it `boardread-youtube`, then **Create** and select it.
3. **APIs & Services > Library**, search **YouTube Data API v3**, then **Enable**.

## 2. Consent screen

4. **Google Auth Platform > Branding** (the console calls it "OAuth consent screen" in some menus). Click **Get started**:
   app name `Boardread`, your email as the support address, audience **External**, your email as the contact, accept,
   then **Create**.
5. **Data access > Add or remove scopes**: tick `.../auth/youtube.upload` (filter on "youtube.upload"), then **Update**
   and **Save**.
6. **Audience > Publish app**, confirm. The status must read **In production**. In "Testing", Google expires the refresh
   token after 7 days and uploads stop. Verification is not needed while only you sign in. Google shows an
   "unverified app" warning at sign-in instead.

## 3. Desktop client

7. **Clients > Create client**, type **Desktop app**, name `boardread-desk`, then **Create**. Keep the dialog open: it
   shows the client ID and the client secret. Don't download or save them anywhere.

## 4. Store the credential on GitHub

8. In a terminal, in the repo (`gh` logged in):

   ```bash
   cd ~/agents/projects/loopbrief-desk && git pull && python3 scripts/youtube_token.py
   ```

   Paste the client ID, then the secret (the secret stays hidden). The browser opens Google's sign-in. Pick the account,
   then the **Boardread** channel if Google asks. On the warning screen, click **Advanced**, then **Go to Boardread**, then **Continue**.
   The script stores `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN` as GitHub secrets. It prints nothing
   secret and writes nothing to disk.

## 5. Switch on

9. Set `"shorts": true` under `growth` in `desk.json` (or ask the desk session to). The publish workflow then uploads
   Shorts from stories already on the site that cleared the social bar and carry an openly licensed photo.
   `shorts_per_day` sets how many a day (default 2; the code stops at 10) and `shorts_spacing_minutes` the gap between
   two uploads (default 180).

To disconnect: remove the app at https://myaccount.google.com/permissions, or delete the three secrets.
