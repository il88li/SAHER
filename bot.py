import logging
import json
import asyncio
from datetime import datetime, time
from typing import Dict, List, Set
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

# ملفات التخزين
CHANNELS_FILE = "channels.json"
POSTED_POEMS_FILE = "posted_poems.json"

class TelegramBot:
    def __init__(self):
        self.application = None
        self.scheduler = AsyncIOScheduler()
        self.channels = self.load_channels()
        self.posted_poems = self.load_posted_poems()
        
    def load_channels(self) -> Dict:
        """تحميل القنوات من الملف"""
        try:
            with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_channels(self):
        """حفظ القنوات إلى الملف"""
        with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.channels, f, ensure_ascii=False, indent=2)
    
    def load_posted_poems(self) -> List[str]:
        """تحميل القصائد المنشورة"""
        try:
            with open(POSTED_POEMS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def save_posted_poems(self):
        """حفظ القصائد المنشورة"""
        with open(POSTED_POEMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.posted_poems, f, ensure_ascii=False, indent=2)
    
    async def is_admin(self, user_id: int) -> bool:
        """التحقق إذا كان المستخدم هو المدير"""
        return user_id == ADMIN_ID
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            chat = await context.bot.get_chat(channel_username)
            chat_id = chat.id
            
            # التحقق من أن البوت مسؤول في القناة
            bot_member = await chat.get_member(context.bot.id)
            if not bot_member.status in ['administrator', 'creator']:
                await update.message.reply_text(
                    "❌ البوت ليس مسؤولاً في هذه القناة.\n"
                    "يرجى إضافة البوت كمسؤول أولاً ثم إعادة المحاولة."
                )
                return ConversationHandler.END
            
            # حفظ القناة
            self.channels[str(chat_id)] = {
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
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message
            )
            
            await update.message.reply_text(
                f"✅ تمت إضافة القناة {channel_username} بنجاح!\n"
                "تم إرسال رسالة تأكيد في القناة.\n\n"
                "سيبدأ البوت بالنشر تلقائياً في الأوقات المحددة."
            )
            
            # بدء الجدولة لهذه القناة
            self.schedule_posts_for_channel(chat_id)
            
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await update.message.reply_text(
                f"❌ حدث خطأ: {str(e)}\n"
                "تأكد من:\n"
                "1. اسم المستخدم صحيح\n"
                "2. البوت مضاف كمسؤول في القناة\n"
                "3. القناة عامة (ليست خاصة)"
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
                    json=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        poem_text = result['candidates'][0]['content']['parts'][0]['text']
                        
                        # التحقق من عدم تكرار القصيدة
                        if poem_text in self.posted_poems:
                            # إعادة المحاولة إذا كانت القصيدة مكررة
                            return await self.generate_poem()
                        
                        # حفظ القصيدة الجديدة
                        self.posted_poems.append(poem_text)
                        self.save_posted_poems()
                        
                        return poem_text
                    else:
                        error_text = await response.text()
                        logger.error(f"Gemini API error: {error_text}")
                        return "عذراً، حدث خطأ في توليد القصيدة. سيتم المحاولة في النشر القادم."
                        
        except Exception as e:
            logger.error(f"Error generating poem: {e}")
            return "عذراً، حدث خطأ في توليد القصيدة. سيتم المحاولة في النشر القادم."
    
    async def post_to_channel(self, chat_id: int):
        """النشر في القناة المحددة"""
        try:
            poem = await self.generate_poem()
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=poem
            )
            
            logger.info(f"تم النشر في القناة {chat_id}")
            
        except Exception as e:
            logger.error(f"Error posting to channel {chat_id}: {e}")
    
    def schedule_posts_for_channel(self, chat_id: int):
        """جدولة المنشورات للقناة"""
        # 6:00 صباحاً (توقيت السعودية)
        self.scheduler.add_job(
            self.post_to_channel,
            CronTrigger(hour=6, minute=0, timezone='Asia/Riyadh'),
            args=[chat_id],
            id=f'morning_{chat_id}'
        )
        
        # 12:00 ظهراً
        self.scheduler.add_job(
            self.post_to_channel,
            CronTrigger(hour=12, minute=0, timezone='Asia/Riyadh'),
            args=[chat_id],
            id=f'noon_{chat_id}'
        )
        
        # 6:00 مساءً
        self.scheduler.add_job(
            self.post_to_channel,
            CronTrigger(hour=18, minute=0, timezone='Asia/Riyadh'),
            args=[chat_id],
            id=f'evening_{chat_id}'
        )
        
        logger.info(f"تم جدولة النشر للقناة {chat_id}")
    
    def start_scheduling(self):
        """بدء الجدولة لجميع القنوات المحفوظة"""
        for chat_id_str in self.channels.keys():
            self.schedule_posts_for_channel(int(chat_id_str))
        
        self.scheduler.start()
        logger.info("تم بدء جدولة النشر")
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء المحادثة"""
        await update.message.reply_text("تم الإلغاء.")
        return ConversationHandler.END
    
    def run(self):
        """تشغيل البوت"""
        # إنشاء التطبيق
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # إنشاء ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', self.start),
                CallbackQueryHandler(self.button_handler)
            ],
            states={
                ADD_CHANNEL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_channel_username)
                ]
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )
        
        # إضافة handlers
        self.application.add_handler(conv_handler)
        
        # بدء الجدولة
        self.start_scheduling()
        
        # تشغيل البوت
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()
