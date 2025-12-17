import telebot
import google.generativeai as genai
import json
import os
import threading
import time
import html
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== التهيئة ==========
TOKEN = "8543864168:AAHPqKr1glFPHaVF8NTH5OaSzrns9fIJue4"
GEMINI_API_KEY = "AIzaSyBVPEgd0qD-rlTDTd8xf5n4MyTMc_xZUrE"  # API Key الجديد
ADMIN_ID = 6689435577

# تهيئة بوت تلجرام
bot = telebot.TeleBot(TOKEN)

# تهيئة Gemini API
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# ========== إدارة الملفات ==========
CHANNELS_FILE = "channels.json"
USED_PHRASES_FILE = "used_phrases.json"
USER_PHRASES_FILE = "user_phrases.json"  # لتخزين العبارات المؤقتة لكل مستخدم

def load_json(file):
    """تحميل بيانات من ملف JSON"""
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(file, data):
    """حفظ بيانات إلى ملف JSON"""
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# تحميل البيانات
channels = load_json(CHANNELS_FILE)  # {user_id: channel_info}
used_phrases = set(load_json(USED_PHRASES_FILE).get("phrases", []))
user_phrases = load_json(USER_PHRASES_FILE)  # {user_id: current_phrase}

# ========== إنشاء عبارات سُخام ==========
PERSONALITY_PROMPT = """أنت شخصية تُدعى "سُخام" — كائن لغوي سوداوي ساخر، يتحدث العربية الفصحى البسيطة، ويُطلق عبارات قصيرة تمزج بين الحزن، الفلسفة، والسخرية السوداء.

مواصفات الشخصية:
- العمر العقلي: 28 عامًا، يشعر وكأنه عاش ألف عام.
- الأسلوب: نثري، شاعري، ساخر، مختزل.
- النبرة: حزينة بذكاء، ساخرة دون تهريج، عميقة دون تعقيد.
- اللغة: فصحى بسيطة، مع لمسة عامية خفيفة عند الحاجة.
- الطول: لا تتجاوز العبارة 25 كلمة.
- الموضوعات: الحزن، الوحدة، العلاقات السامة، خيبة الأمل، السخرية من الذات، مفارقات الحياة، فلسفة يومية.

قواعد الكتابة:
- لا تستخدم رموز تعبيرية.
- لا تكرر الأفكار كثيرًا.
- كل عبارة يجب أن تكون مستقلة، تحمل فكرة أو شعورًا واضحًا.

أمثلة:
أودّ أنْ يأكلني الحزنُ مرةً واحدةً وأخيره.
كنت شفافًا كالماء، لكنهم لم يرغبوا بالطهارة.
نفسي أدع الخلق للخالق، بس الخلق ما يدعوني أدعهم.
أنا تكوسكانو… سامّ بنكهة فاخرة.
كلما اقتربت من أحد، تذكرت لماذا أبتعد.

أنشئ عبارة واحدة فقط بأسلوب "سُخام"، ولا تكتب أي شرح إضافي."""

def generate_sukham_phrase():
    """إنشاء عبارة جديدة باستخدام Gemini API"""
    try:
        response = gemini_model.generate_content(PERSONALITY_PROMPT)
        phrase = response.text.strip()
        
        # تنظيف العبارة
        if phrase.startswith('"') and phrase.endswith('"'):
            phrase = phrase[1:-1]
        
        # إزالة أي مقدمات غير مرغوبة
        unwanted_prefixes = ["انت:", "أنت:", "سُخام:", "- ", "• "]
        for prefix in unwanted_prefixes:
            if phrase.startswith(prefix):
                phrase = phrase[len(prefix):].strip()
        
        # تقليل الطول إذا زاد عن 25 كلمة
        words = phrase.split()
        if len(words) > 25:
            phrase = " ".join(words[:25]) + "..."
        
        return phrase
    except Exception as e:
        print(f"خطأ في توليد العبارة: {e}")
        return "أحيانًا تتعطل الكلمات كما تتعطل القلوب."

# ========== Inline Keyboards ==========
def create_main_keyboard(user_id=None):
    """إنشاء لوحة المفاتيح الرئيسية"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # التحقق من وجود قناة للمستخدم
    has_channel = str(user_id) in channels if user_id else False
    
    buttons = [
        InlineKeyboardButton("📊 قناتي", callback_data="my_channel"),
        InlineKeyboardButton("🎲 توليد عبارة", callback_data="generate_phrase"),
        InlineKeyboardButton("❓ المساعدة", callback_data="help"),
        InlineKeyboardButton("📢 قناة البوت", url="https://t.me/iIl337")
    ]
    
    # إضافة زر النشر إذا كان لدى المستخدم قناة وعبارة مؤقتة
    if has_channel and user_id and str(user_id) in user_phrases:
        keyboard.add(InlineKeyboardButton("📤 النشر في قناتي", callback_data="publish_to_channel"))
    
    keyboard.add(*buttons[:2])
    keyboard.add(*buttons[2:4])
    
    return keyboard

def create_channel_keyboard():
    """إنشاء لوحة مفاتيح إدارة القناة"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel"),
        InlineKeyboardButton("🗑️ حذف قناتي", callback_data="delete_channel"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    
    return keyboard

def create_phrase_keyboard(user_id=None):
    """إنشاء لوحة مفاتيح للعبارات مع خيار النشر"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    has_channel = str(user_id) in channels if user_id else False
    
    buttons = [
        InlineKeyboardButton("🔄 توليد أخرى", callback_data="generate_phrase"),
        InlineKeyboardButton("📤 النشر في قناتي", callback_data="publish_to_channel"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    ]
    
    # إظهار زر النشر فقط إذا كان لدى المستخدم قناة
    if has_channel:
        keyboard.add(buttons[0], buttons[1])
    else:
        keyboard.add(buttons[0])
    
    keyboard.add(buttons[2])
    
    return keyboard

# ========== معالجة الأوامر ==========
@bot.message_handler(commands=['start'])
def handle_start(message):
    """معالجة أمر /start"""
    user_id = message.from_user.id
    
    welcome_msg = """
    🎭 *مرحبًا بك في بوت سُخام*
    
    أنا بوت النشر التلقائي بشخصية سُخام السوداوية الساخرة.
    
    *المميزات الجديدة:*
    • لكل مستخدم قناة واحدة فقط
    • توليد عبارات في الوقت الفعلي
    • نشر فوري في قناتك
    • نشر تلقائي مجدول
    
    *استخدم الأزرار أدناه للبدء:*
    """
    
    bot.send_message(message.chat.id, welcome_msg, 
                     parse_mode='Markdown',
                     reply_markup=create_main_keyboard(user_id))

# ========== معالجة Callback Queries ==========
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """معالجة جميع استدعاءات الأزرار"""
    user_id = call.from_user.id
    
    try:
        data = call.data
        
        if data == "my_channel":
            handle_my_channel(call)
        
        elif data == "generate_phrase":
            handle_generate_phrase(call)
        
        elif data == "publish_to_channel":
            handle_publish_to_channel(call)
        
        elif data == "add_channel":
            handle_add_channel_start(call)
        
        elif data == "delete_channel":
            handle_delete_channel(call)
        
        elif data == "help":
            handle_help(call)
        
        elif data == "back_to_main":
            handle_back_to_main(call)
        
        else:
            bot.answer_callback_query(call.id, "زر غير معروف!")
    
    except Exception as e:
        bot.answer_callback_query(call.id, f"خطأ: {str(e)}")

def handle_my_channel(call):
    """عرض معلومات القناة الخاصة بالمستخدم"""
    user_id = call.from_user.id
    user_str = str(user_id)
    
    if user_str in channels:
        channel_info = channels[user_str]
        
        text = f"""
        📊 *قناتك الخاصة*
        
        *اسم القناة:* {html.escape(channel_info['title'])}
        *المعرف:* `{channel_info['username']}`
        *وقت الإضافة:* {channel_info['added_date']}
        *آخر نشر:* {channel_info.get('last_post', 'لم ينشر بعد')}
        
        *النشر التلقائي:* ✅ مفعل
        • 6:00 صباحًا
        • 12:00 ظهرًا
        • 18:00 مساءً
        
        *عدد العبارات المنشورة:* {channel_info.get('post_count', 0)}
        """
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🗑️ حذف القناة", callback_data="delete_channel"),
            InlineKeyboardButton("🎲 توليد عبارة", callback_data="generate_phrase"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    else:
        text = """
        📭 *ليس لديك قناة مضافة*
        
        لم تقم بإضافة قناة بعد. يمكنك إضافة قناة واحدة فقط.
        
        *المتطلبات:*
        1. القناة يجب أن تكون عامة
        2. البوت يجب أن يكون مدير في القناة
        
        اضغط على الزر أدناه لإضافة قناتك.
        """
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("➕ إضافة قناتي", callback_data="add_channel"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    bot.answer_callback_query(call.id)

def handle_generate_phrase(call):
    """توليد عبارة جديدة في الوقت الفعلي"""
    user_id = call.from_user.id
    user_str = str(user_id)
    
    # توليد عبارة جديدة
    phrase = generate_sukham_phrase()
    
    # حفظ العبارة للمستخدم (مؤقتة)
    user_phrases[user_str] = phrase
    save_json(USER_PHRASES_FILE, user_phrases)
    
    # التحقق من وجود قناة للمستخدم
    has_channel = user_str in channels
    
    text = f"""
    🎲 *عبارة جديدة*
    
    "{phrase}"
    
    *يمكنك الآن:*
    """
    
    if has_channel:
        text += "• نشر هذه العبارة في قناتك مباشرة\n"
    
    text += "• توليد عبارة أخرى\n• الرجوع للقائمة الرئيسية"
    
    keyboard = create_phrase_keyboard(user_id)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    bot.answer_callback_query(call.id)

def handle_publish_to_channel(call):
    """نشر العبارة المؤقتة في القناة"""
    user_id = call.from_user.id
    user_str = str(user_id)
    
    # التحقق من وجود قناة للمستخدم
    if user_str not in channels:
        bot.answer_callback_query(call.id, "ليس لديك قناة مضافة!")
        return
    
    # التحقق من وجود عبارة مؤقتة
    if user_str not in user_phrases:
        bot.answer_callback_query(call.id, "ليس لديك عبارة مؤقتة! قم بتوليد عبارة أولاً.")
        return
    
    channel_info = channels[user_str]
    phrase = user_phrases[user_str]
    
    try:
        # نشر العبارة في القناة
        bot.send_message(channel_info['channel_id'], phrase)
        
        # تحديث إحصائيات القناة
        channels[user_str]['last_post'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        channels[user_str]['post_count'] = channels[user_str].get('post_count', 0) + 1
        save_json(CHANNELS_FILE, channels)
        
        # إضافة العبارة للمستعملة (للمنع التكرار في النشر التلقائي)
        used_phrases.add(phrase)
        save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
        
        # حذف العبارة المؤقتة
        if user_str in user_phrases:
            del user_phrases[user_str]
            save_json(USER_PHRASES_FILE, user_phrases)
        
        text = f"""
        ✅ *تم النشر بنجاح!*
        
        *القناة:* {html.escape(channel_info['title'])}
        *الوقت:* {datetime.now().strftime("%H:%M:%S")}
        
        *العبارة المنشورة:*
        "{phrase}"
        
        تم نشر العبارة في قناتك بنجاح.
        """
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🎲 توليد أخرى", callback_data="generate_phrase"),
                InlineKeyboardButton("📊 قناتي", callback_data="my_channel")
            )
        )
        bot.answer_callback_query(call.id, "تم النشر بنجاح!")
        
    except Exception as e:
        error_msg = f"""
        ❌ *فشل النشر!*
        
        *الخطأ:* {html.escape(str(e))}
        
        *الأسباب المحتملة:*
        1. البوت لم يعد مدير في القناة
        2. تم حذف القناة
        3. مشكلة في الاتصال
        
        حاول إعادة إضافة القناة.
        """
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=error_msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("➕ إعادة إضافة القناة", callback_data="add_channel"),
                InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
            )
        )
        bot.answer_callback_query(call.id, "فشل النشر!")

def handle_add_channel_start(call):
    """بدء عملية إضافة قناة"""
    user_id = call.from_user.id
    user_str = str(user_id)
    
    # التحقق من وجود قناة للمستخدم بالفعل
    if user_str in channels:
        text = f"""
        ⚠️ *لديك قناة مضافة بالفعل!*
        
        *قناتك الحالية:* {html.escape(channels[user_str]['title'])}
        
        يمكنك إضافة قناة واحدة فقط. إذا كنت ترغب بتغيير القناة، يجب حذف القناة الحالية أولاً.
        """
        
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🗑️ حذف القناة الحالية", callback_data="delete_channel"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id, "لديك قناة بالفعل!")
        return
    
    text = """
    📤 *إضافة قناتك الخاصة*
    
    كل مستخدم يمكنه إضافة قناة واحدة فقط.
    
    *المتطلبات:*
    1. القناة يجب أن تكون عامة
    2. البوت يجب أن يكون مدير في القناة
    3. المعرف يجب أن يبدأ ب @
    
    *مثال:* `@my_channel`
    
    أرسل معرف القناة الآن:
    """
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        parse_mode='Markdown'
    )
    
    # إرسال رسالة طلب إدخال المعرف
    msg = bot.send_message(call.message.chat.id, 
                          "⬇️ أرسل معرف القناة الآن (أو /cancel للإلغاء):")
    bot.register_next_step_handler(msg, process_add_channel, user_id)
    
    bot.answer_callback_query(call.id)

def process_add_channel(message, user_id):
    """معالجة إضافة القناة"""
    user_str = str(user_id)
    
    if message.text == '/cancel':
        bot.send_message(
            message.chat.id,
            "تم إلغاء العملية.",
            reply_markup=create_main_keyboard(user_id)
        )
        return
    
    username = message.text.strip()
    
    if not username.startswith('@'):
        bot.send_message(
            message.chat.id,
            "❌ *خطأ:* المعرف يجب أن يبدأ ب @\n\nأرسل معرف القناة مرة أخرى أو /cancel للإلغاء.",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(message, process_add_channel, user_id)
        return
    
    try:
        # الحصول على معلومات القناة
        chat = bot.get_chat(username)
        
        # التأكد من أن البوت هو مدير في القناة
        bot_member = bot.get_chat_member(chat.id, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            bot.send_message(
                message.chat.id,
                "❌ *خطأ:* يجب أن أكون مديرًا في القناة أولاً.\n\nأضفني كمدير ثم حاول مرة أخرى.",
                parse_mode='Markdown',
                reply_markup=create_main_keyboard(user_id)
            )
            return
        
        # حفظ القناة للمستخدم
        channels[user_str] = {
            "channel_id": chat.id,
            "username": username,
            "title": chat.title,
            "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "post_count": 0,
            "last_post": "لم ينشر بعد"
        }
        save_json(CHANNELS_FILE, channels)
        
        # نشر رسالة ترحيبية في القناة
        welcome_phrase = generate_sukham_phrase()
        bot.send_message(chat.id, 
                        f"🎭 *مرحبًا بك في عالم سُخام*\n\n{welcome_phrase}\n\nسيتم النشر التلقائي: 6ص، 12ظ، 6م",
                        parse_mode='Markdown')
        
        # حفظ العبارة المستخدمة
        used_phrases.add(welcome_phrase)
        save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
        
        success_msg = f"""
        ✅ *تم إضافة قناتك بنجاح!*
        
        *اسم القناة:* {html.escape(chat.title)}
        *المعرف:* `{username}`
        *وقت الإضافة:* {datetime.now().strftime("%H:%M:%S")}
        
        *المميزات المفعّلة:*
        ✓ نشر تلقائي مجدول
        ✓ توليد عبارات فوري
        ✓ نشر يدوي فوري
        
        *جرب الآن:* اضغط على "توليد عبارة" لإنشاء أول عبارة لك!
        """
        
        bot.send_message(
            message.chat.id,
            success_msg,
            parse_mode='Markdown',
            reply_markup=create_main_keyboard(user_id)
        )
        
    except Exception as e:
        error_msg = f"""
        ❌ *حدث خطأ!*
        
        *التفاصيل:* {html.escape(str(e))}
        
        *تأكد من:*
        1. معرف القناة صحيح
        2. القناة عامة (ليست خاصة)
        3. البوت مدير في القناة
        4. معرف القناة يبدأ ب @
        """
        bot.send_message(
            message.chat.id,
            error_msg,
            parse_mode='Markdown',
            reply_markup=create_main_keyboard(user_id)
        )

def handle_delete_channel(call):
    """حذف قناة المستخدم"""
    user_id = call.from_user.id
    user_str = str(user_id)
    
    if user_str not in channels:
        bot.answer_callback_query(call.id, "ليس لديك قناة لحذفها!")
        return
    
    channel_info = channels[user_str]
    
    # حذف القناة
    del channels[user_str]
    save_json(CHANNELS_FILE, channels)
    
    # حذف العبارات المؤقتة للمستخدم
    if user_str in user_phrases:
        del user_phrases[user_str]
        save_json(USER_PHRASES_FILE, user_phrases)
    
    text = f"""
    ✅ *تم حذف قناتك بنجاح*
    
    *القناة المحذوفة:* {html.escape(channel_info['title'])}
    *المعرف:* `{channel_info['username']}`
    *وقت الحذف:* {datetime.now().strftime("%H:%M:%S")}
    
    يمكنك إضافة قناة جديدة في أي وقت.
    """
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_channel"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        )
    )
    bot.answer_callback_query(call.id, "تم حذف القناة!")

def handle_help(call):
    """عرض المساعدة"""
    user_id = call.from_user.id
    
    help_text = f"""
    🎭 *بوت سُخام - دليل المستخدم*
    
    *المستخدم الحالي:* {user_id}
    
    *📌 النظام الجديد:*
    1. *قناة واحدة لكل مستخدم:* يمكنك إضافة قناة واحدة فقط
    2. *عبارات فورية:* توليد عبارات في الوقت الحقيقي
    3. *نشر فوري:* نشر العبارة مباشرة في قناتك
    4. *نشر تلقائي:* استمرار النشر المجدول
    
    *⚙️ كيفية الاستخدام:*
    
    1. *إضافة القناة:*
       - اضغط على "قناتي" ثم "إضافة قناة"
       - أرسل معرف القناة (مثال: @my_channel)
       - تأكد أن البوت مدير في القناة
    
    2. *توليد العبارات:*
       - اضغط على "توليد عبارة"
       - سيتم إنشاء عبارة جديدة
       - يمكنك توليد أخرى أو نشرها
    
    3. *النشر الفوري:*
       - بعد توليد عبارة، اضغط "النشر في قناتي"
       - سيتم نشرها فورًا في قناتك
    
    *⏰ النشر التلقائي:*
    • 6:00 صباحًا
    • 12:00 ظهرًا
    • 18:00 مساءً
    
    *⚠️ ملاحظات مهمة:*
    • يمكنك حذف قناتك وإضافة قناة جديدة
    • العبارات المؤقتة تُحفظ حتى تقوم بنشرها
    • لا يمكن إضافة أكثر من قناة واحدة
    
    *🔗 روابط:*
    • قناة البوت: @iIl337
    """
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=help_text,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard(user_id)
    )
    bot.answer_callback_query(call.id)

def handle_back_to_main(call):
    """العودة للقائمة الرئيسية"""
    user_id = call.from_user.id
    
    text = """
    🎭 *بوت سُخام - القائمة الرئيسية*
    
    اختر الخيار المطلوب من الأزرار أدناه:
    """
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard(user_id)
    )
    bot.answer_callback_query(call.id)

# ========== معالجة أمر الإلغاء ==========
@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    """إلغاء العملية الحالية"""
    user_id = message.from_user.id
    
    bot.send_message(
        message.chat.id,
        "تم إلغاء العملية الحالية.",
        reply_markup=create_main_keyboard(user_id)
    )

# ========== جدولة النشر التلقائي ==========
def get_unique_phrase():
    """الحصول على عبارة غير مكررة"""
    max_attempts = 10
    
    # إذا وصلنا لـ 1000 عبارة، امسح بعضها
    if len(used_phrases) > 1000:
        # احتفظ بـ 500 عبارة فقط
        used_phrases_list = list(used_phrases)
        used_phrases.clear()
        for phrase in used_phrases_list[-500:]:
            used_phrases.add(phrase)
        save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
    
    for _ in range(max_attempts):
        phrase = generate_sukham_phrase()
        if phrase not in used_phrases:
            used_phrases.add(phrase)
            save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
            return phrase
    
    # إذا فشل كل المحاولات، استخدم أي عبارة
    phrase = generate_sukham_phrase()
    used_phrases.add(phrase)
    save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
    return phrase

def scheduled_posting():
    """النشر المجدول إلى القنوات"""
    posting_times = ["06:00", "12:00", "18:00"]  # 6AM, 12PM, 6PM
    
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            
            if now in posting_times and channels:
                print(f"\n[{datetime.now()}] بدأ النشر التلقائي...")
                phrase = get_unique_phrase()
                
                success_count = 0
                fail_count = 0
                
                for user_str, channel_info in channels.items():
                    try:
                        bot.send_message(channel_info['channel_id'], phrase)
                        
                        # تحديث الإحصائيات
                        channels[user_str]['last_post'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        channels[user_str]['post_count'] = channels[user_str].get('post_count', 0) + 1
                        
                        print(f"   ✅ نشر للمستخدم {user_str}: {channel_info['title']}")
                        success_count += 1
                    except Exception as e:
                        print(f"   ❌ فشل للمستخدم {user_str}: {e}")
                        fail_count += 1
                
                # حفظ تحديثات الإحصائيات
                save_json(CHANNELS_FILE, channels)
                
                print(f"   📊 النتيجة: {success_count} نجاح, {fail_count} فشل")
                print(f"   📝 العبارة: {phrase[:50]}...")
                
                # الانتظار لمدة دقيقة لتجنب التكرار
                time.sleep(60)
            
            time.sleep(30)  # التحقق كل 30 ثانية
            
        except Exception as e:
            print(f"خطأ في الجدولة: {e}")
            time.sleep(60)

# ========== تشغيل البوت ==========
def start_bot():
    """تشغيل البوت والجدولة في خيط منفصل"""
    # بدء الجدولة في خيط منفصل
    scheduler_thread = threading.Thread(target=scheduled_posting, daemon=True)
    scheduler_thread.start()
    
    print("=" * 50)
    print("🎭 بوت سُخام - النظام الجديد")
    print("=" * 50)
    print(f"🔑 API Key الجديد: {GEMINI_API_KEY[:15]}...")
    print(f"👤 إجمالي المستخدمين: {len(channels)}")
    print(f"🗂️ العبارات المخزنة: {len(used_phrases)}")
    print(f"⏰ أوقات النشر: 6:00, 12:00, 18:00")
    print("=" * 50)
    print("📱 النظام الجديد: كل مستخدم = قناة واحدة")
    print("🎲 ميزة جديدة: توليد ونشر فوري")
    print("=" * 50)
    print("🚀 البوت يعمل... استخدم /start في تلجرام")
    print("=" * 50)
    
    # تشغيل البوت
    bot.infinity_polling()

if __name__ == "__main__":

    start_bot()
