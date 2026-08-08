import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from config import CHANNEL_USERNAME
from posts_sequence import POSTS_SEQUENCE
from stats import log_publish

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
POSTS_FILE = os.path.join(os.path.dirname(__file__), "posts_sequence.py")


def send_text(text: str):
    try:
        resp = requests.post(
            f"{API_BASE}/sendMessage",
            data={"chat_id": CHANNEL_USERNAME, "text": text, "parse_mode": "HTML"},
            timeout=30,
        )
        return resp.ok, (None if resp.ok else resp.text)
    except requests.RequestException as e:
        return False, str(e)


def send_photo(image_path: str, caption: str):
    try:
        with open(image_path, "rb") as img:
            resp = requests.post(
                f"{API_BASE}/sendPhoto",
                data={"chat_id": CHANNEL_USERNAME, "caption": caption, "parse_mode": "HTML"},
                files={"photo": img},
                timeout=60,
            )
        return resp.ok, (None if resp.ok else resp.text)
    except (requests.RequestException, FileNotFoundError) as e:
        return False, str(e)


def mark_as_sent(post_id: str):
    """يحدّث الملف نفسه ويغيّر sent': False إلى True لهذا المنشور تحديدًا فقط."""
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # يبحث عن الـ id تحديدًا ويغيّر أقرب "sent": False بعده فقط
    pattern = re.compile(
        r'("id":\s*"' + re.escape(post_id) + r'".*?"sent":\s*)False',
        re.DOTALL,
    )
    new_content, count = pattern.subn(r"\1True", content, count=1)

    if count == 0:
        print(f"⚠️ تحذير: لم يتم العثور على {post_id} لتحديثه في الملف.")
        return False

    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def main():
    if not BOT_TOKEN:
        print("❌ خطأ: TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة (تأكد من إضافته في Secrets)")
        sys.exit(1)

    pending = [p for p in POSTS_SEQUENCE if not p.get("sent")]

    if not pending:
        print("ℹ️ لا توجد منشورات جديدة للنشر. كل المنشورات المتاحة نُشرت بالفعل.")
        return

    post = pending[0]
    image_path = post.get("image_path")

    if image_path and os.path.exists(image_path):
        ok, error = send_photo(image_path, post["text"])
    elif image_path:
        # الصورة محددة لكن الملف مش موجود - ينشر كنص بدل ما يفشل بالكامل
        print(f"⚠️ الصورة {image_path} غير موجودة، سيتم النشر كنص فقط.")
        ok, error = send_text(post["text"])
    else:
        ok, error = send_text(post["text"])

    log_publish("telegram", post["id"], ok, error)

    if ok:
        mark_as_sent(post["id"])
        print(f"✅ تم نشر {post['id']} بنجاح وتحديث الحالة.")
    else:
        print(f"❌ فشل نشر {post['id']}: {error}")
        # لا يوقف الـ workflow بالكامل كخطأ فادح، فقط يسجل الفشل
        # يمكن مراجعته لاحقًا في stats/publish_log.json دون كسر الأتمتة القادمة


if __name__ == "__main__":
    main()
