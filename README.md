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
| `pipeline.yml` | كل 6 ساعات | يفحص بناء ريبوهات المواقع الأخرى، ثم يشغّل `publish.yml` لو كل حاجة تمام |

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

## التحقق المحلي قبل التشغيل

```bash
python -m pip install -r md1_global_agent/requirements.txt
python -m compileall -q md1_global_agent growth-engines social
node --check page-generator/build-pages.js
```

## MD1 Global Scout — نشر فعلي متعدد اللغات

التشغيل اليومي (`md1-global-scout.yml`):

1. يبحث عن فرص **جديدة فقط** (يتخطى كل ما فُحص أو نُشر سابقًا ويتصفح صفحات بحث أعمق).
2. يكتب خطة عربية للأفضل بدون ذكر اسم المصدر أو رابطه.
3. يترجمها إلى 9 لغات (`page_languages` في `config.yaml`) بالنماذج المجانية؛ أي لغة تفشل تُتخطى فقط.
4. بوابات جودة وخصوصية (تسريب المصدر، الطول، اللغة، الكود الضار) ثم يشغّل workflow `generate-pages.yml` في `MDM1.org`.
5. لا يعتبر النشر ناجحًا إلا بعد نجاح الـ workflow **وفتح الرابط الحي** والعثور على عنوان الصفحة فيه.
6. ترويج تلقائي في قناة تليجرام (عربي + إنجليزي + رابط)، وتقرير عربي لك يذكر ما نُشر وروابطه ولغاته.
7. تفاصيل المصدر (المعرّف ← الاسم) تصلك **في رسالة خاصة فقط**، ولا تُطبع في السجلات ولا تُحفظ في الريبو.

صفحات الموقع تفتح بلغة جهاز الزائر (`navigator.languages`) مع زر 🌐 لتغيير اللغة، وتتذكر اختياره.
اللغة غير المدعومة تعرض الإنجليزية.

### منع التكرار (مستويان)

`md1_global_agent/memory/ledger.json` يحفظ **هاشات مفتاحية** فقط (لا أسماء):
- **مفحوصة**: ما ظهر في تقرير أو خُطّط لا يظهر مرة أخرى.
- **منشورة**: ما نُشر له صفحة لا يُنشر ثانيةً (والموقع نفسه يرفض نفس `scout_id` مرتين).

سر اختياري `LEDGER_SALT`: اضبطه مرة واحدة ولا تغيّره لاحقًا.

الصفحات التي فشل نشرها (مثل انتهاء `SITES_PAT`) تُحفظ منقّحة في `memory/pending/` وتُعاد محاولتها تلقائيًا.

### الأسرار المطلوبة لهذا الـ workflow

| الاسم | الاستخدام |
|---|---|
| `SITES_PAT` | توكن بصلاحية **Actions: write + Contents: write** على `MDM1.org` (لتشغيل الـ workflow وقراءة السجل) |
| `BOT_TOKEN` / `TELEGRAM_BOT_TOKEN`, `CHAT_ID` | تقرير تليجرام والترويج في القناة (البوت يجب أن يكون مشرفًا في القناة) |
| `GROQ_API_KEY` / `OPENROUTER_API_KEY` / `OPENCODE_API_KEY` / `API_KEYS` | نماذج الخطة والترجمة |
| `LEDGER_SALT` (اختياري) | تقوية هاش سجل منع التكرار |

إعادة بناء كود مشاريع خارجية ليست مفعّلة تلقائيًا: الوكيل يولد خطة فقط ولا يشغّل كودًا غير موثوق داخل GitHub Actions.
