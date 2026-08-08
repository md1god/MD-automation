# MD-automation

مركز الأتمتة المشترك لمشاريع MD1 (`MD1usd.com`, `MDM1.org`, وأي ريبو تاني تابع). الريبو ده مالوش واجهة أو موقع خاص بيه — دوره إنه يوفر workflows قابلة لإعادة الاستخدام (reusable workflows) وسكريبتات نمو/نشر يستدعيها ريبوهات المواقع بدل ما كل ريبو يكرر نفس الكود.

## بنية الريبو

```
.github/workflows/     Actions workflows — القابلة للاستدعاء (reusable-*.yml) وغير القابلة
growth-engines/         سكريبتات Python لتوليد ومتابعة خطط النمو والانتشار
page-generator/         مولّد صفحات HTML تلقائي (build-pages.js) + مكتبة محتوى + الصفحات الناتجة
social/                 بوت تليجرام للنشر التلقائي + إحصائيات النشر
```

## الـ Workflows

### قابلة لإعادة الاستخدام (يتم استدعاؤها من ريبوهات تانية عبر `uses:`)

| الملف | وظيفته |
|---|---|
| `reusable-build.yml` | يبني أي مشروع Node (يكتشف package.json تلقائيًا، فيه إعادة محاولة عند فشل التثبيت أو البناء) |
| `reusable-deploy.yml` | يبني وينشر مشروع على GitHub Pages |
| `reusable-deploy-static.yml` | ينشر مجلد ثابت (بدون build) على GitHub Pages |
| `reusable-content-check.yml` | يفحص وجود وحجم ملفات مطلوبة (مثلاً `dist/index.html`) بعد البناء، ويفتح Issue لو في نقص |
| `reusable-watchdog.yml` | يراقب آخر تشغيل لـ workflow معيّن في نفس الريبو، ويفتح Issue لو فشل أو توقف لمدة طويلة |
| `reusable-autofix.yml` | محاولة إصلاح تلقائي (إعادة توليد lockfile + retry build) عند فشل بناء، بيتفعّل من Issue بعلامة `build-failed` |
| `reusable-publish.yml` | ينشر أقدم رسالة من طابور محتوى (`content-queue/`) على تليجرام |

### تشغيلية (لها trigger خاص بيها، بتستدعي reusable workflows فوق)

| الملف | يشتغل إمتى | بيستدعي |
|---|---|---|
| `build.yml` | عند push/PR على main | `reusable-build.yml` |
| `deploy.yml` | بعد نجاح `Build` | `reusable-deploy.yml` |
| `auto-fix.yml` | عند فتح/تصنيف Issue بعلامة `build-failed`، بعد التحقق من صلاحيات المستخدم | `reusable-autofix.yml` |
| `publish.yml` | يدويًا | `reusable-publish.yml` |
| `pipeline.yml` | كل 6 ساعات | يعمل checkout لريبوهات المواقع الأخرى (`SITES_PAT`)، يبني، يبلّغ بالفشل، ويشغّل `publish.yml` لو كل حاجة تمام |

### مستقلة (منطقها بالكامل جوه الملف، من غير استدعاء)

| الملف | وظيفته |
|---|---|
| `Security-Audit.yml` | فحص أمني يومي: `cargo audit` للـ Rust و`slither` للـ Solidity |
| `generate-pages.yml` | كل ساعة، يولّد صفحة جديدة عبر `page-generator/build-pages.js` ويعمل commit/push للنتيجة |
| `telegram-publish.yml` | نشر يومي مجدول على تليجرام عبر `social/telegram/bot.py` |

## استخدام الـ reusable workflows من ريبو تاني

```yaml
jobs:
  check:
    uses: md1god/MD-automation/.github/workflows/reusable-content-check.yml@main
    with:
      required-files: |
        dist/index.html
        dist/404.html
      min-bytes: '400'
```

الاستدعاء بيكون دايمًا بـ `@main` (مش commit SHA ثابت) عشان يستفيد أي ريبو مستدعي من آخر تحديث في الـ reusable workflow من غير ما يحتاج يعرف الـ SHA الجديد كل مرة.

## الـ Secrets المطلوبة

| الاسم | مستخدم في |
|---|---|
| `SITES_PAT` | `pipeline.yml` — الوصول لريبوهات المواقع الأخرى (checkout + فتح Issues + تشغيل workflows) |
| `BOT_TOKEN`, `CHAT_ID` | `publish.yml` → `reusable-publish.yml` — بوت تليجرام لنشر طابور المحتوى |
| `TELEGRAM_BOT_TOKEN` | `telegram-publish.yml` — بوت تليجرام للنشر اليومي المجدول |

لازم تتأكد إن دول موجودين فعليًا في `Settings → Secrets and variables → Actions` قبل ما تعتمد على أي workflow بيستخدمهم.
