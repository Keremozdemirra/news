# Cross-posting platforms

Every feed post that goes out on Instagram is also sent to the platforms below. All are OFF until you
switch them on. A platform is skipped without a word while its secrets are missing. Each step list
ends with the secrets to store and the one setting to flip in `desk.json`.

Store a secret like this (the command asks you to paste the value, nothing is echoed or written to a file):

    gh secret set NAME -R Keremozdemirra/news

To switch a platform on, set it to `true` in `desk.json` under `"platforms"` and push. To switch it off
again, set it back to `false`. Never paste a token into a chat, an issue or a file.

## Threads

1. Open developers.facebook.com, go to My Apps, and use the app that already runs the Instagram connection (or create one).
2. Add the "Threads API" use case to the app.
3. Under the app's roles, add the Threads account as a Threads Tester, then accept the invite in Threads (Settings > Account > Website permissions > Invites).
4. Request the permissions `threads_basic` and `threads_content_publish`. Without advanced access they only work for testers, which is enough for your own account.
5. In the Threads API settings, generate a user access token for the tester account. Exchange it for a long-lived token (60 days) as described in the Threads "Get access tokens" page.
6. Read your Threads user ID from the same page (or call `GET https://graph.threads.com/v1.0/me?fields=id` with the token).
7. Store the secrets:

        gh secret set THREADS_TOKEN -R Keremozdemirra/news
        gh secret set THREADS_USER_ID -R Keremozdemirra/news

8. Set `"threads": true` in `desk.json`.

The long-lived token expires after 60 days. Refresh it before then (`GET https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token&access_token=...`) and store the new value with the same `gh secret set`. This refresh is not automated yet.

## Facebook Page

1. In Facebook, create a Page for boardread (Pages > Create new Page). It must be a Page; a personal profile cannot be posted to.
2. In developers.facebook.com, use the same app as Instagram. Under Use cases, add "Manage everything on your Page".
3. Request `pages_manage_posts`, `pages_read_engagement` and `pages_show_list`.
4. In Business Settings, create a system user (or use the existing one), assign the Page to it with full control, then generate a token for the app with those three permissions. A system-user token for a Page does not expire. (Alternative: Graph API Explorer, user token with the permissions, then `GET /me/accounts` returns a Page token for each Page.)
5. Read the Page ID: Page > About > Page transparency, or the `id` field in the `/me/accounts` answer.
6. Store the secrets:

        gh secret set FB_PAGE_TOKEN -R Keremozdemirra/news
        gh secret set FB_PAGE_ID -R Keremozdemirra/news

7. Set `"facebook": true` in `desk.json`.

## Bluesky

1. Create the account at bsky.app. Pick the handle you want (for example `boardread.bsky.social`).
2. Verify the e-mail address.
3. Settings > Privacy and security > App passwords > Add App Password. Name it `desk`. Copy it once; it looks like `xxxx-xxxx-xxxx-xxxx`. Never use the real account password.
4. Store the secrets (handle without the @):

        gh secret set BSKY_HANDLE -R Keremozdemirra/news
        gh secret set BSKY_APP_PASSWORD -R Keremozdemirra/news

5. Set `"bluesky": true` in `desk.json`.

To cut access later, delete the app password in the same settings page.

## Telegram channel

1. In Telegram, message @BotFather, send `/newbot`, and follow the prompts. It answers with the bot token.
2. Create a channel (New Channel). Make it public and give it a username such as `boardread` so post links work.
3. Open the channel > Administrators > Add Administrator, pick your bot, and allow "Post messages".
4. The channel value is `@boardread` (the public username with @). For a private channel it is the numeric id, which starts with `-100`; links to posts are then left empty.
5. Store the secrets:

        gh secret set TG_BOT_TOKEN -R Keremozdemirra/news
        gh secret set TG_CHANNEL -R Keremozdemirra/news

6. Set `"telegram": true` in `desk.json`.

## X

Not built yet.

## Notes

- Each platform is posted at most once per story. If a send fails or its result is unknown, the post's `post.json` keeps an `attempted` marker under `platforms` and the desk logs it for you; check the account and fill in `id` and `url` by hand, or clear the marker to allow one more try.
- A rate-limit or block answer pauses only that platform for 24 hours. Instagram is never affected.
