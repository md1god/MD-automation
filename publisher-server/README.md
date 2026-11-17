# MD1 Publisher Server

خادم نشر مباشر (REST + MCP) بلا أي اعتماديات خارجية. يستطيع Claude وأي وكيل ذكاء اصطناعي يدعم MCP أن ينشر عبره على حساباتك. كل الاتصالات تستخدم الواجهات الرسمية الموثّقة لكل منصة، وكل المفاتيح تبقى في متغيرات البيئة عندك فقط.

## الأدوات (MCP) والنقاط (REST)

| MCP tool | REST | الوظيفة |
|---|---|---|
| `list_platforms` | `GET /platforms` | المنصات المدعومة وهل هي مضبوطة |
| `publish_post` | `POST /publish` | نشر نص على منصة أو أكثر. `dry_run:true` يتحقق دون نشر |
| `discover_social_links` | `POST /discover` | يقرأ صفحة https عامة ويستخرج روابط حسابات التواصل |

المصادقة: `Authorization: Bearer <API_KEY>`. لعملاء MCP التي تقبل رابطاً فقط استخدم `https://<service>.onrender.com/mcp/<API_KEY>`.

## المنصات ومتغيراتها

| id | المتغيرات |
|---|---|
| bluesky | `BSKY_HANDLE` `BSKY_APP_PASSWORD` |
| mastodon | `MASTODON_HOST` `MASTODON_TOKEN` |
| telegram | `TELEGRAM_BOT_TOKEN` `TELEGRAM_CHAT_ID` |
| discord | `DISCORD_WEBHOOK_URL` |
| linkedin | `LINKEDIN_ACCESS_TOKEN` `LINKEDIN_AUTHOR_URN` (اختياري `LINKEDIN_API_VERSION`) |
| x | `X_ACCESS_TOKEN` (OAuth2 user token بصلاحية tweet.write) |
| facebook (صفحة) | `FACEBOOK_PAGE_ID` `FACEBOOK_PAGE_TOKEN` |
| reddit | `REDDIT_CLIENT_ID` `REDDIT_CLIENT_SECRET` `REDDIT_USERNAME` `REDDIT_PASSWORD` (`REDDIT_SUBREDDIT`) |
| devto | `DEVTO_API_KEY` |
| wordpress | `WORDPRESS_URL` `WORDPRESS_USER` `WORDPRESS_APP_PASSWORD` |
| github | `GITHUB_PUBLISH_TOKEN` `GITHUB_PUBLISH_REPO` (`GITHUB_PUBLISH_DIR` `GITHUB_PUBLISH_BRANCH`) |
| webhook | `WEBHOOK_URL` |

## النشر على Render (من الجوال)

1. Render ← New ← Blueprint ← اختر ريبو `MD-automation` (يقرأ `render.yaml`).
2. من Environment انسخ قيمة `API_KEY` المولّدة، واضبط `PUBLIC_URL` على رابط الخدمة، وأضف مفاتيح المنصات التي تريدها فقط.
3. أضف في Claude موصلاً مخصصاً بالرابط `https://<service>.onrender.com/mcp/<API_KEY>`.

## ربط LinkedIn تلقائياً

أنشئ تطبيقاً في linkedin.com/developers وفعّل «Share on LinkedIn» و«Sign In with LinkedIn using OpenID Connect»، وأضف Redirect URL: `<PUBLIC_URL>/oauth/linkedin/callback`، ثم ضع `LINKEDIN_CLIENT_ID` و`LINKEDIN_CLIENT_SECRET`. افتح `<PUBLIC_URL>/oauth/linkedin/start?key=<API_KEY>` فتظهر لك قيمتا `LINKEDIN_ACCESS_TOKEN` و`LINKEDIN_AUTHOR_URN` لتنسخهما إلى Render. الرمز ينتهي بعد نحو 60 يوماً فكرّر الربط.

## حدود صريحة

- **Hacker News، YouTube، TikTok، Instagram:** غير مدعومة هنا. HN بلا واجهة نشر، والبقية تحتاج رفع وسائط وموافقة مراجعة من المنصة. استخدم صفحة https://mdm1.org/apps/ai-social-publisher.html لتجهيز النص ثم الإرسال اليدوي.
- X وLinkedIn وFacebook وReddit تفرض شروطاً وتسعيراً وحدوداً قد تتغير، والمحوّلات كُتبت من التوثيق الرسمي واختُبرت بمحاكاة الشبكة فقط، فجرّب كل منصة بـ`dry_run` ثم بمنشور حقيقي واحد.
- الحماية من التكرار وحد الساعة محفوظان في الذاكرة ويُصفَّران عند إعادة التشغيل (الخطة المجانية تنام عند الخمول).
- جلب الروابط يمنع العناوين الداخلية (SSRF) ولا يقبل إلا https على المنفذ 443.
- لا تستخدم الخادم لنشر مكرر أو ترويجي كثيف: المنصات تحظر الحسابات على ذلك.

## الاختبار

```
cd publisher-server && npm test
```
