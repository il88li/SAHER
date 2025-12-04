import logging
import json
import asyncio
from datetime import datetime, time, timedelta
import os
from typing import Dict, List
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# إعدادات API
GEMINI_API_KEY = "AIzaSyCc0OcyQZ8-0c3vQxhNzrvV2Qe_MbAAayQ"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
TELEGRAM_TOKEN = "8543864168:AAG7IGqJ0HAs3PZnxgw97fUgUrWygRR3uNRY"

# تعريف حالات المحادثة
ADD_CHANNEL, GET_CHANNEL_USERNAME = range(2)

# ID المدير
ADMIN_ID = 6689435577

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# أسماء الملفات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(BASE_DIR, "channels.json")
POSTED_POEMS_FILE = os.path.join(BASE_DIR, "posted_poems.json")

class TelegramBot:
    def __init__(self):
        self.channels = self.load_channels()
        self.posted_poems = self.load_posted_poems()
        self.scheduler = AsyncIOScheduler()
        
    def load_channels(self) -> Dict:
        """تحميل القنوات من الملف"""
        try:
            if os.path.exists(CHANNELS_FILE):
                with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # تحويل مفاتيح JSON من نص إلى int لاستخدامها كـ chat_id
                    return {int(k): v for k, v in data.items()}
            return {}
        except Exception as e:
            logger.error(f"Error loading channels: {e}")
            return {}
    
    def save_channels(self):
        """حفظ القنوات إلى الملف"""
        try:
            with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
                # تحويل مفاتيح int إلى نص للتخزين في JSON
                data = {str(k): v for k, v in self.channels.items()}
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving channels: {e}")
    
    def load_posted_poems(self) -> List[str]:
        """تحميل القصائد المنشورة"""
        try:
            if os.path.exists(POSTED_POEMS_FILE):
                with open(POSTED_POEMS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading posted poems: {e}")
            return []
    
    def save_posted_poems(self):
        """حفظ القصائد المنشورة"""
        try:
            with open(POSTED_POEMS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.posted_poems, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving posted poems: {e}")
    
    async def is_admin(self, user_id: int) -> bool:
        """التحقق إذا كان المستخدم هو المدير"""
        return user_id == ADMIN_ID
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        user = update.effective_user
        
        if not await self.is_admin(user.id):
            await update.message.reply_text("ليس لديك صلاحية لاستخدام هذا البوت.")
            return
        
        keyboard = [
            [InlineKeyboardButton("اضف قناتي", callback_data='add_channel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "مرحباً! أنا بوت النشر التلقائي للشعر الساخر العربي.\n\n"
            "اضغط على الزر أدناه لإضافة قناتك:",
            reply_markup=reply_markup
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة ضغطات الأزرار"""
        query = update.callback_query
        await query.answer()
        
        if not await self.is_admin(query.from_user.id):
            await query.edit_message_text("ليس لديك صلاحية لاستخدام هذا البوت.")
            return
        
        if query.data == 'add_channel':
            await query.edit_message_text(
                "يرجى إرسال اسم المستخدم العام للقناة (بدون @).\n"
                "مثال: my_channel\n\n"
                "تأكد من أن البوت تمت إضافته كمسؤول في القناة."
            )
            return ADD_CHANNEL
        
        return ConversationHandler.END
    
    async def get_channel_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """الحصول على اسم المستخدم للقناة"""
        user = update.effective_user
        
        if not await self.is_admin(user.id):
            await update.message.reply_text("ليس لديك صلاحية لاستخدام هذا البوت.")
            return ConversationHandler.END
        
        channel_username = update.message.text.strip()
        
        if not channel_username:
            await update.message.reply_text("يرجى إرسال اسم مستخدم صحيح.")
            return ADD_CHANNEL
        
        # إضافة @ إذا لم تكن موجودة
        if not channel_username.startswith('@'):
            channel_username = '@' + channel_username
        
        try:
            # محاولة الحصول على معلومات القناة
            bot = context.bot
            chat = await bot.get_chat(channel_username)
            chat_id = chat.id
            
            # التحقق من أن البوت مسؤول في القناة
            bot_member = await chat.get_member(bot.id)
            if bot_member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    "❌ البوت ليس مسؤولاً في هذه القناة.\n"
                    "يرجى إضافة البوت كمسؤول أولاً ثم إعادة المحاولة."
                )
                return ConversationHandler.END
            
            # حفظ القناة
            self.channels[chat_id] = {
                'username': channel_username,
                'title': chat.title,
                'added_by': user.id,
                'added_date': datetime.now().isoformat()
            }
            self.save_channels()
            
            # إرسال رسالة تأكيد في القناة
            welcome_message = (
                "✅ تم تفعيل البوت في هذه القناة بنجاح!\n\n"
                "سيقوم البوت بنشر قصائد ساخرة عربية في الأوقات التالية:\n"
                "• 6:00 صباحاً\n• 12:00 ظهراً\n• 6:00 مساءً\n\n"
                "سيتم البدء في النشر تلقائياً من الآن."
            )
            
            await bot.send_message(
                chat_id=chat_id,
                text=welcome_message
            )
            
            await update.message.reply_text(
                f"✅ تمت إضافة القناة {channel_username} بنجاح!\n"
                "تم إرسال رسالة تأكيد في القناة.\n\n"
                "سيبدأ البوت بالنشر تلقائياً في الأوقات المحددة."
            )
            
            # بدء الجدولة لهذه القناة
            await self.schedule_posts_for_channel(chat_id)
            
        except TelegramError as e:
            logger.error(f"Telegram error adding channel: {e}")
            await update.message.reply_text(
                f"❌ حدث خطأ: {str(e)}\n"
                "تأكد من:\n"
                "1. اسم المستخدم صحيح\n"
                "2. البوت مضاف كمسؤول في القناة\n"
                "3. القناة عامة (ليست خاصة)"
            )
        except Exception as e:
            logger.error(f"Unexpected error adding channel: {e}")
            await update.message.reply_text(
                f"❌ حدث خطأ غير متوقع: {str(e)}"
            )
        
        return ConversationHandler.END
    
    async def generate_poem(self) -> str:
        """إنشاء قصيدة باستخدام Gemini API"""
        prompt = """انت شخصية اجتماعية ساردة للشعر الساخر العربي الاصيل من الكتب العربية ، اسرد لي قصيدة شعرية مضحكة ، بدون شرحها او اي تفاصيل اخرى، قدم اول بيتين فقط من القصيدة الكاملة ، ثم اشرح من هو الشاعر وفي اي زمن وفي من قال القصيدة، لاتتعلق بالنساء ، بها مواقف اجتماعية محرجة، تنمر، عنصرية، ابدء باسم القصيدة، لا تشرح او توضح او تسئل اي شيء"""
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if 'candidates' in result and len(result['candidates']) > 0:
                            poem_text = result['candidates'][0]['content']['parts'][0]['text']
                            
                            # التحقق من عدم تكرار القصيدة
                            if poem_text in self.posted_poems:
                                # إعادة المحاولة إذا كانت القصيدة مكررة
                                logger.info("Poem already posted, generating new one...")
                                return await self.generate_poem()
                            
                            # حفظ القصيدة الجديدة
                            self.posted_poems.append(poem_text)
                            self.save_posted_poems()
                            
                            return poem_text
                        else:
                            logger.error("No candidates in Gemini response")
                            return "عذراً، حدث خطأ في توليد القصيدة. سيتم المحاولة في النشر القادم."
                    else:
                        error_text = await response.text()
                        logger.error(f"Gemini API error {response.status}: {error_text}")
                        return "عذراً، حدث خطأ في توليد القصيدة. سيتم المحاولة في النشر القادم."
                        
        except asyncio.TimeoutError:
            logger.error("Gemini API timeout")
            return "عذراً، تجاوز الوقت المحدد لتوليد القصيدة. سيتم المحاولة في النشر القادم."
        except Exception as e:
            logger.error(f"Error generating poem: {e}")
            return "عذراً، حدث خطأ في توليد القصيدة. سيتم المحاولة في النشر القادم."
    
    async def post_to_channel(self, chat_id: int):
        """النشر في القناة المحددة"""
        try:
            poem = await self.generate_poem()
            
            # إرسال المنشور
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=poem
            )
            
            logger.info(f"تم النشر في القناة {chat_id}")
            
        except TelegramError as e:
            logger.error(f"Telegram error posting to channel {chat_id}: {e}")
            # إزالة القناة إذا كان البوت لم يعد مسؤولاً
            if "Chat not found" in str(e) or "bot is not a member" in str(e) or "bot was kicked" in str(e):
                if chat_id in self.channels:
                    del self.channels[chat_id]
                    self.save_channels()
                    logger.info(f"تم إزالة القناة {chat_id} بسبب عدم صلاحية الوصول")
        except Exception as e:
            logger.error(f"Unexpected error posting to channel {chat_id}: {e}")
    
    async def schedule_posts_for_channel(self, chat_id: int):
        """جدولة المنشورات للقناة"""
        # إزالة أي جدول موجود لنفس القناة
        for job in self.scheduler.get_jobs():
            if str(chat_id) in job.id:
                job.remove()
        
        # 6:00 صباحاً (توقيت السعودية)
        self.scheduler.add_job(
            self.post_to_channel,
            CronTrigger(hour=6, minute=0, timezone='Asia/Riyadh'),
            args=[chat_id],
            id=f'morning_{chat_id}',
            replace_existing=True
        )
        
        # 12:00 ظهراً
        self.scheduler.add_job(
            self.post_to_channel,
            CronTrigger(hour=12, minute=0, timezone='Asia/Riyadh'),
            args=[chat_id],
            id=f'noon_{chat_id}',
            replace_existing=True
        )
        
        # 6:00 مساءً
        self.scheduler.add_job(
            self.post_to_channel,
            CronTrigger(hour=18, minute=0, timezone='Asia/Riyadh'),
            args=[chat_id],
            id=f'evening_{chat_id}',
            replace_existing=True
        )
        
        logger.info(f"تم جدولة النشر للقناة {chat_id}")
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء المحادثة"""
        await update.message.reply_text("تم الإلغاء.")
        return ConversationHandler.END
    
    async def init_scheduler(self):
        """تهيئة المجدول لجميع القنوات"""
        for chat_id in self.channels.keys():
            await self.schedule_posts_for_channel(chat_id)
        
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("تم بدء جدولة النشر")
    
    async def post_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر للنشر الفوري (/postnow)"""
        user = update.effective_user
        
        if not await self.is_admin(user.id):
            await update.message.reply_text("ليس لديك صلاحية لاستخدام هذا البوت.")
            return
        
        # النشر في جميع القنوات فوراً
        for chat_id in self.channels.keys():
            await self.post_to_channel(chat_id)
        
        await update.message.reply_text("تم النشر في جميع القنوات بنجاح!")
    
    async def list_channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر لعرض القنوات (/channels)"""
        user = update.effective_user
        
        if not await self.is_admin(user.id):
            await update.message.reply_text("ليس لديك صلاحية لاستخدام هذا البوت.")
            return
        
        if not self.channels:
            await update.message.reply_text("لم تتم إضافة أي قنوات بعد.")
            return
        
        message = "📋 **القنوات المضافة:**\n\n"
        for idx, (chat_id, channel_info) in enumerate(self.channels.items(), 1):
            message += f"{idx}. {channel_info['title']} ({channel_info['username']})\n"
            message += f"   تمت الإضافة: {channel_info['added_date'][:10]}\n\n"
        
        await update.message.reply_text(message)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء العام"""
        logger.error(f"حدث خطأ: {context.error}")
        
        if update and isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "عذراً، حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقاً."
                )
            except:
                pass
    
    async def post_on_startup(self, application: Application):
        """إجراءات عند بدء تشغيل البوت"""
        logger.info("بدء تشغيل البوت...")
        
        # تهيئة المجدول
        await self.init_scheduler()
        
        # إرسال رسالة للمدير
        try:
            await application.bot.send_message(
                chat_id=ADMIN_ID,
                text="✅ تم تشغيل بوت الشعر الساخر بنجاح!"
            )
        except Exception as e:
            logger.error(f"Error sending startup message: {e}")
    
    def run(self):
        """تشغيل البوت"""
        # إنشاء التطبيق
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # تخزين نسخة من الكائن في context
        self.application.bot_data['bot_instance'] = self
        
        # إنشاء ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.start_command),
                CallbackQueryHandler(self.button_callback)
            ],
            states={
                ADD_CHANNEL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_channel_username)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
            allow_reentry=True
        )
        
        # إضافة handlers
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler("postnow", self.post_now_command))
        self.application.add_handler(CommandHandler("channels", self.list_channels_command))
        
        # إضافة معالج الأخطاء
        self.application.add_error_handler(self.error_handler)
        
        # إضافة إجراءات عند بدء التشغيل
        self.application.post_init = self.post_on_startup
        
        # تشغيل البوت
        logger.info("بدء تشغيل البوت في وضع الاستطلاع...")
        self.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()
