"""
بوت تلجرام للمودريشن الصارم - وحش الكنافة
قاموس + Gemini AI + نظام تحذيرات وطرد (نسخة الحماية الصافية)
"""

import logging
import httpx
import asyncio
from collections import defaultdict
from telegram.ext import (
    Application, MessageHandler,
    CommandHandler, filters,
)

BOT_TOKEN          = "8805350373:AAHZarv7mA2oAvDsUOL9VxyXfcDVXbec9kg"
GEMINI_API_KEY     = "AQ.Ab8RN6L2HrOgUutZpT7qvK1TJUxx_j6YKEkaTDRQ3WLdEtjkaQ"
MAX_WARNINGS       = 3   # عدد التحذيرات قبل الطرد تلقائياً

BAD_WORDS = [
    "ابن كلب","ابن قندره","ابن كحبه","انعل ابوك","كبي ابن كلب",
    "ابن منيوجه","ابن عاهره","كسمه","كس","كسمك","عير","عير بيكم",
    "خوات كحبه","اخ الكحبه","منيوج","عاهر","كحبه","كلب","قندره",
    "خرب الله","انعل دينك","ابن مفتوح","طيزك","ابوك كحبه","امك عريضه",
    "زب","چوتي","خول","لوطي","شرموطه","زانيه","طيز","منيوك",
    "عيور", "عيوره", "عايور", "العيور", "عيوررره"
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# قواعد البيانات المؤقتة للتحذيرات وطابور الرسائل
warnings = defaultdict(lambda: defaultdict(int))
message_queue = asyncio.Queue()


def check_bad_words(text: str) -> bool:
    t = text.lower()
    for word in BAD_WORDS:
        if word.lower() in t:
            return True
    return False


async def ask_gemini(text: str) -> bool:
    try:
        prompt = (
            "أنت مودريتور صارم لمجموعة عراقية. "
            "حدد إذا كانت الرسالة تحتوي على شتيمة أو كلام بذيء "
            "بأي لهجة عربية أو بحروف لاتينية أو أرقام. "
            "أجب بكلمة واحدة فقط: YES أو NO.\n\n"
            f"الرسالة: {text}"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
        if response.status_code == 429:
            return False
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logger.error(f"خطأ Gemini: {e}")
        return False


async def message_worker(context):
    """ معالج الخلفية الذكي لفحص الرسائل وحذف السيء منها """
    while True:
        update, ctx = await message_queue.get()
        try:
            msg = update.message
            if not msg or not msg.text:
                continue

            user = msg.from_user
            chat = msg.chat
            
            # تجاوز فحص المالك والمشرفين تماماً
            member = await ctx.bot.get_chat_member(chat.id, user.id)
            if member.status in ["creator", "administrator"]:
                continue

            # نظام الفحص المزدوج (القاموس المحلي + ذكاء جمناي)
            is_bad = False
            if check_bad_words(msg.text):
                is_bad = True
                logger.info(f"[-] رصد محلي: {msg.text}")
            else:
                is_bad = await ask_gemini(msg.text)
                logger.info(f"[?] فحص جمناي للرسالة [{msg.text}]: {is_bad}")
                await asyncio.sleep(1.0) # حماية الـ API من الـ 429

            if is_bad:
                await msg.delete() # حذف الرسالة فوراً
                name = f"@{user.username}" if user.username else user.full_name
                warnings[chat.id][user.id] += 1
                count = warnings[chat.id][user.id]

                if count < MAX_WARNINGS:
                    remaining = MAX_WARNINGS - count
                    await ctx.bot.send_message(
                        chat.id,
                        f"⚠️ {name} — تحذير {count}/{MAX_WARNINGS}\n"
                        f"باقي لك {remaining} تحذير قبل الطرد."
                    )
                else:
                    warnings[chat.id][user.id] = 0
                    await ctx.bot.ban_chat_member(chat.id, user.id)
                    await ctx.bot.unban_chat_member(chat.id, user.id) # طرد وإلغاء حظر ليتمكن من العودة لاحقاً برابط
                    await ctx.bot.send_message(
                        chat.id,
                        f"🚫 {name} تم طرده من المجموعة بسبب تكرار الكلام البذيء."
                    )

        except Exception as e:
            logger.error(f"خطأ في معالجة الطابور: {e}")
        finally:
            message_queue.task_done()


async def handle_message(update, context):
    """ تحويل الرسائل النصية إلى طابور المعالجة """
    await message_queue.put((update, context))


async def post_init(application: Application):
    asyncio.create_task(message_worker(application))
    logger.info("تم تشغيل طابور المودريشن بنجاح...")


async def warnings_cmd(update, context):
    """ لمعرفة تحذيرات عضو (للمشرفين فقط بالرد على رسالته) """
    member = await context.bot.get_chat_member(update.message.chat.id, update.message.from_user.id)
    if member.status not in ["creator", "administrator"]: return
    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة الشخص المراد فحص تحذيراته.")
        return
    target = update.message.reply_to_message.from_user
    name = f"@{target.username}" if target.username else target.full_name
    count = warnings[update.message.chat.id][target.id]
    await update.message.reply_text(f"📋 العضو {name} لديه {count}/{MAX_WARNINGS} تحذيرات.")


async def clear_warnings_cmd(update, context):
    """ لتصفير تحذيرات عضو (للمشرفين فقط بالرد على رسالته) """
    member = await context.bot.get_chat_member(update.message.chat.id, update.message.from_user.id)
    if member.status not in ["creator", "administrator"]: return
    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة الشخص المراد مسح تحذيراته.")
        return
    target = update.message.reply_to_message.from_user
    name = f"@{target.username}" if target.username else target.full_name
    warnings[update.message.chat.id][target.id] = 0
    await update.message.reply_text(f"✅ تم مسح وإعادة تصفير تحذيرات العضو {name} بنجاح.")


async def start_cmd(update, context):
    await update.message.reply_text(
        "🛡️ أهلاً بك! البوت شغال الآن بنظام الحماية والمودريشن الصافي.\n\n"
        "الكمندات المتاحة للمشرفين (بالرد على رسالة العضو):\n"
        "/warnings — لمعرفة تحذيرات العضو\n"
        "/clearwarnings — لمسح وتصفير تحذيرات العضو"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # تسجيل الأوامر النظيفة
    app.add_handler(CommandHandler("start",         start_cmd))
    app.add_handler(CommandHandler("warnings",      warnings_cmd))
    app.add_handler(CommandHandler("clearwarnings", clear_warnings_cmd))
    
    # فلتر استقبال الرسائل النصية فقط للفحص
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("جاري تشغيل نسخة الحماية الصافية...")
    app.run_polling()


if __name__ == "__main__":
    main()