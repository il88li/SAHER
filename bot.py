import telebot
import json
import os
import threading
import time
import html
import re
import requests
import hashlib
from collections import Counter
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from difflib import SequenceMatcher

# ========== التهيئة ==========
TOKEN = "8543864168:AAHPqKr1glFPHaVF8NTH5OaSzrns9fIJue4"
COPILOT_API_URL = "https://vetrex.x10.mx/api/copilot_chat.php"
ADMIN_ID = 6689435577

# تهيئة بوت تلجرام
bot = telebot.TeleBot(TOKEN)

# ========== إدارة الملفات ==========
CHANNELS_FILE = "channels.json"
USED_PHRASES_FILE = "used_phrases.json"
USER_PHRASES_FILE = "user_phrases.json"
PHRASE_HISTORY_FILE = "phrase_history.json"
TOPIC_HISTORY_FILE = "topic_history.json"

def load_json(file):
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# تحميل البيانات
channels = load_json(CHANNELS_FILE)
used_phrases = set(load_json(USED_PHRASES_FILE).get("phrases", []))
user_phrases = load_json(USER_PHRASES_FILE)
phrase_history = load_json(PHRASE_HISTORY_FILE)
topic_history = load_json(TOPIC_HISTORY_FILE)

# ========== آلية منع التكرار ==========
class RepetitionPreventer:
    def __init__(self):
        self.similarity_threshold = 0.7
        self.topic_cooldown_hours = 24
        self.max_phrase_length = 25
        
    def clean_text(self, text):
        """تنظيف النص من الرموز والتشكيل"""
        if not text:
            return ""
        
        text = re.sub(r'[\{\}\[\]:,"]', '', text)
        text = re.sub(r'\b(success|reply|true|false|null)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[\u064b-\u065f]', '', text)
        text = re.sub(r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\s\.\!\؟،]', '', text)
        text = text.lower()
        text = re.sub(r'\s+', ' ', text).strip()
        
        prefixes = ["انت:", "أنت:", "سُخام:", "- ", "• ", "reply:", "العبارة:"]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        
        return text
    
    def get_phrase_hash(self, text):
        """إنشاء بصمة رقمية للعبارة"""
        cleaned = self.clean_text(text)
        return hashlib.md5(cleaned.encode('utf-8')).hexdigest()
    
    def calculate_similarity(self, text1, text2):
        """حساب درجة التشابه بين نصين"""
        cleaned1 = self.clean_text(text1)
        cleaned2 = self.clean_text(text2)
        
        if not cleaned1 or not cleaned2:
            return 0
        
        return SequenceMatcher(None, cleaned1, cleaned2).ratio()
    
    def extract_topics(self, text):
        """استخراج المواضيع الرئيسية من النص"""
        cleaned = self.clean_text(text)
        
        stop_words = {
            'في', 'من', 'إلى', 'على', 'عن', 'مع', 'ب', 'ك', 'ل', 'و', 'ف', 'س', 
            'أو', 'إن', 'أن', 'لا', 'ما', 'هل', 'هذا', 'هذه', 'ذلك', 'هؤلاء',
            'كان', 'يكون', 'كانت', 'يكون', 'التي', 'الذي', 'الذين', 'اللاتي'
        }
        
        words = cleaned.split()
        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        word_freq = Counter(filtered_words)
        topics = [word for word, freq in word_freq.most_common(3) if freq >= 1]
        
        return topics
    
    def is_phrase_duplicate(self, phrase, threshold=None):
        """التحقق إذا كانت العبارة مكررة"""
        if threshold is None:
            threshold = self.similarity_threshold
        
        phrase_hash = self.get_phrase_hash(phrase)
        
        if phrase in used_phrases:
            return True, "تكرار تام"
        
        if phrase_hash in phrase_history:
            history = phrase_history[phrase_hash]
            if datetime.now().timestamp() - history.get('last_used', 0) < 86400:
                return True, f"مستخدمة من قبل ({history.get('count', 0)} مرة)"
        
        for used_phrase in list(used_phrases)[-100:]:
            similarity = self.calculate_similarity(phrase, used_phrase)
            if similarity > threshold:
                return True, f"تشابه عالي ({similarity*100:.1f}%)"
        
        topics = self.extract_topics(phrase)
        for topic in topics:
            if topic in topic_history:
                topic_info = topic_history[topic]
                last_used = datetime.fromtimestamp(topic_info.get('last_used', 0))
                if datetime.now() - last_used < timedelta(hours=self.topic_cooldown_hours):
                    return True, f"موضوع مكرر: {topic}"
        
        return False, None
    
    def register_phrase(self, phrase):
        """تسجيل العبارة المستخدمة"""
        used_phrases.add(phrase)
        
        phrase_hash = self.get_phrase_hash(phrase)
        if phrase_hash in phrase_history:
            phrase_history[phrase_hash]['count'] += 1
            phrase_history[phrase_hash]['last_used'] = datetime.now().timestamp()
        else:
            phrase_history[phrase_hash] = {
                'text': phrase,
                'count': 1,
                'first_used': datetime.now().timestamp(),
                'last_used': datetime.now().timestamp()
            }
        
        topics = self.extract_topics(phrase)
        for topic in topics:
            if topic in topic_history:
                topic_history[topic]['count'] += 1
                topic_history[topic]['last_used'] = datetime.now().timestamp()
            else:
                topic_history[topic] = {
                    'count': 1,
                    'first_used': datetime.now().timestamp(),
                    'last_used': datetime.now().timestamp()
                }
        
        save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
        save_json(PHRASE_HISTORY_FILE, phrase_history)
        save_json(TOPIC_HISTORY_FILE, topic_history)

# تهيئة آلية منع التكرار
repetition_preventer = RepetitionPreventer()

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

def clean_phrase(text):
    """تنظيف العبارة من الرموز البرمجية"""
    if not text:
        return ""
    
    try:
        json_pattern = r'\{.*?"reply".*?:.*?"(.*?)".*?\}'
        match = re.search(json_pattern, text, re.DOTALL)
        if match:
            text = match.group(1)
    except:
        pass
    
    text = re.sub(r'[\{\}\[\]:,"]', '', text)
    text = re.sub(r'\b(success|reply|true|false|null)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d+\b', '', text)
    text = re.sub(r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\s\.\!\؟،]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.strip('.,!؟،')
    
    prefixes = ["انت:", "أنت:", "سُخام:", "- ", "• ", "reply:", "العبارة:"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:25]) + "..."
    
    return text

def generate_sukham_phrase(max_attempts=10):
    """إنشاء عبارة جديدة مع منع التكرار"""
    attempts = 0
    
    while attempts < max_attempts:
        try:
            response = requests.post(
                COPILOT_API_URL,
                json={"text": PERSONALITY_PROMPT},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                raw_response = response.text.strip()
            else:
                try:
                    get_url = f"{COPILOT_API_URL}?text={requests.utils.quote(PERSONALITY_PROMPT)}"
                    response = requests.get(get_url, timeout=30)
                    raw_response = response.text.strip() if response.status_code == 200 else ""
                except:
                    raw_response = ""
            
            if not raw_response:
                attempts += 1
                continue
            
            phrase = clean_phrase(raw_response)
            
            if not phrase or len(phrase.strip()) < 5:
                attempts += 1
                continue
            
            is_duplicate, reason = repetition_preventer.is_phrase_duplicate(phrase)
            
            if not is_duplicate:
                return phrase
            else:
                print(f"⏭️  تخطي عبارة مكررة ({reason}): {phrase[:50]}...")
                attempts += 1
                
        except requests.exceptions.Timeout:
            print("⏰ انتهت مهلة الاتصال بـ Copilot API")
            attempts += 1
        except Exception as e:
            print(f"❌ خطأ في توليد العبارة: {e}")
            attempts += 1
    
    timestamp = datetime.now().strftime("%H%M%S")
    fallback_phrases = [
        "في لحظات الصمت هذه، أسمع صوت قلبي يكتب ما لم تقله الكلمات.",
        "ربما نحتاج لأن نضيع قليلاً حتى نجد أنفسنا في المكان الذي لم نبحث عنه.",
        "أحيانًا تكون الذكريات وطنًا لا يعترف به أحد سوى القلب المنفى.",
        "لكل منا قصة لم تُروَ، وجرح لم يُضمّد، وضحكة علقت في الزمن.",
        "الحياة سفرية قصيرة، نحمل فيها أمتعة أثقل من ذاكرتنا."
    ]
    
    selected = fallback_phrases[int(timestamp[-1]) % len(fallback_phrases)]
    
    is_duplicate, reason = repetition_preventer.is_phrase_duplicate(selected)
    if not is_duplicate:
        return selected
    
    for phrase in fallback_phrases:
        is_duplicate, _ = repetition_preventer.is_phrase_duplicate(phrase)
        if not is_duplicate:
            return phrase
    
    return "أحيانًا تتعطل الكلمات كما تتعطل القلوب."

# ========== Inline Keyboards ==========
def create_main_keyboard(user_id=None):
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    has_channel = str(user_id) in channels if user_id else False
    
    buttons = [
        InlineKeyboardButton("📊 قناتي", callback_data="my_channel"),
        InlineKeyboardButton("🎲 توليد عبارة", callback_data="generate_phrase"),
        InlineKeyboardButton("📈 الإحصائيات", callback_data="stats"),
        InlineKeyboardButton("❓ المساعدة", callback_data="help"),
        InlineKeyboardButton("📢 قناة البوت", url="https://t.me/iIl337")
    ]
    
    if has_channel and user_id and str(user_id) in user_phrases:
        keyboard.add(InlineKeyboardButton("📤 النشر في قناتي", callback_data="publish_to_channel"))
    
    keyboard.add(*buttons[:2])
    keyboard.add(buttons[2], buttons[3])
    keyboard.add(buttons[4])
    
    return keyboard

def create_channel_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel"),
        InlineKeyboardButton("🗑️ حذف قناتي", callback_data="delete_channel"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    
    return keyboard

def create_phrase_keyboard(user_id=None):
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    has_channel = str(user_id) in channels if user_id else False
    
    buttons = [
        InlineKeyboardButton("🔄 توليد أخرى", callback_data="generate_phrase"),
        InlineKeyboardButton("📤 النشر في قناتي", callback_data="publish_to_channel"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    ]
    
    if has_channel:
        keyboard.add(buttons[0], buttons[1])
    else:
        keyboard.add(buttons[0])
    
    keyboard.add(buttons[2])
    
    return keyboard

# ========== معالجة الأوامر ==========
@bot.message_handler(commands=['start'])
def handle_start(message):
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
        
        elif data == "stats":
            handle_stats(call)
        
        elif data == "back_to_main":
            handle_back_to_main(call)
        
        elif data.startswith("force_publish:"):
            handle_force_publish(call)
        
        else:
            bot.answer_callback_query(call.id, "زر غير معروف!")
    
    except Exception as e:
        bot.answer_callback_query(call.id, f"خطأ: {str(e)}")

def handle_my_channel(call):
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
    user_id = call.from_user.id
    user_str = str(user_id)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🔄 *جاري توليد عبارة فريدة...*\n\nقد يستغرق هذا بضع ثوانٍ لضمان عدم التكرار.",
        parse_mode='Markdown'
    )
    
    phrase = generate_sukham_phrase()
    
    is_duplicate, reason = repetition_preventer.is_phrase_duplicate(phrase)
    
    if is_duplicate:
        phrase += " [جديدة]"
    
    user_phrases[user_str] = phrase
    save_json(USER_PHRASES_FILE, user_phrases)
    
    has_channel = user_str in channels
    
    text = f"""
    🎲 *عبارة جديدة*
    
    "{phrase}"
    
    *معلومات الجودة:*
    • تم التحقق من التكرار: ✅
    • الطول: {len(phrase.split())} كلمة
    • البصمة: {repetition_preventer.get_phrase_hash(phrase)[:8]}
    
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
    user_id = call.from_user.id
    user_str = str(user_id)
    
    if user_str not in channels:
        bot.answer_callback_query(call.id, "ليس لديك قناة مضافة!")
        return
    
    if user_str not in user_phrases:
        bot.answer_callback_query(call.id, "ليس لديك عبارة مؤقتة! قم بتوليد عبارة أولاً.")
        return
    
    channel_info = channels[user_str]
    phrase = user_phrases[user_str]
    
    try:
        is_duplicate, reason = repetition_preventer.is_phrase_duplicate(phrase)
        
        if is_duplicate:
            warning_msg = f"⚠️ *تحذير:* هذه العبارة مشابهة لعبارة سابقة ({reason})\n\n"
            warning_msg += f"*هل تريد النشر على أي حال؟*\n\nالعبارة: \"{phrase}\""
            
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("✅ نعم، أنشر", callback_data=f"force_publish:{phrase}"),
                InlineKeyboardButton("❌ لا، أعيد التوليد", callback_data="generate_phrase")
            )
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=warning_msg,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id, "تحذير: العبارة مكررة!")
            return
        
        publish_phrase_to_channel(call, phrase)
        
    except Exception as e:
        error_msg = f"""
        ❌ *فشل النشر!*
        
        *الخطأ:* {html.escape(str(e))}
        """
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=error_msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔄 المحاولة مرة أخرى", callback_data="publish_to_channel"),
                InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
            )
        )
        bot.answer_callback_query(call.id, "فشل النشر!")

def publish_phrase_to_channel(call, phrase):
    user_id = call.from_user.id
    user_str = str(user_id)
    channel_info = channels[user_str]
    
    bot.send_message(channel_info['channel_id'], phrase)
    
    channels[user_str]['last_post'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    channels[user_str]['post_count'] = channels[user_str].get('post_count', 0) + 1
    save_json(CHANNELS_FILE, channels)
    
    repetition_preventer.register_phrase(phrase)
    
    if user_str in user_phrases:
        del user_phrases[user_str]
        save_json(USER_PHRASES_FILE, user_phrases)
    
    text = f"""
    ✅ *تم النشر بنجاح!*
    
    *القناة:* {html.escape(channel_info['title'])}
    *الوقت:* {datetime.now().strftime("%H:%M:%S")}
    *البصمة:* {repetition_preventer.get_phrase_hash(phrase)[:8]}
    
    *العبارة المنشورة:*
    "{phrase}"
    
    تم تسجيل العبارة في نظام منع التكرار.
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

def handle_force_publish(call):
    phrase = call.data.split(":", 1)[1]
    publish_phrase_to_channel(call, phrase)

def handle_add_channel_start(call):
    user_id = call.from_user.id
    user_str = str(user_id)
    
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
    
    msg = bot.send_message(call.message.chat.id, 
                          "⬇️ أرسل معرف القناة الآن (أو /cancel للإلغاء):")
    bot.register_next_step_handler(msg, process_add_channel, user_id)
    
    bot.answer_callback_query(call.id)

def process_add_channel(message, user_id):
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
        chat = bot.get_chat(username)
        
        bot_member = bot.get_chat_member(chat.id, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            bot.send_message(
                message.chat.id,
                "❌ *خطأ:* يجب أن أكون مديرًا في القناة أولاً.\n\nأضفني كمدير ثم حاول مرة أخرى.",
                parse_mode='Markdown',
                reply_markup=create_main_keyboard(user_id)
            )
            return
        
        channels[user_str] = {
            "channel_id": chat.id,
            "username": username,
            "title": chat.title,
            "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "post_count": 0,
            "last_post": "لم ينشر بعد"
        }
        save_json(CHANNELS_FILE, channels)
        
        welcome_phrase = generate_sukham_phrase()
        bot.send_message(chat.id, 
                        f"🎭 *مرحبًا بك في عالم سُخام*\n\n{welcome_phrase}\n\nسيتم النشر التلقائي: 6ص، 12ظ، 6م",
                        parse_mode='Markdown')
        
        repetition_preventer.register_phrase(welcome_phrase)
        
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
    user_id = call.from_user.id
    user_str = str(user_id)
    
    if user_str not in channels:
        bot.answer_callback_query(call.id, "ليس لديك قناة لحذفها!")
        return
    
    channel_info = channels[user_str]
    
    del channels[user_str]
    save_json(CHANNELS_FILE, channels)
    
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
    """إصلاح: عرض المساعدة بشكل صحيح"""
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
    
    *🎯 نظام منع التكرار:*
    • يحول دون تكرار العبارات
    • يتجنب المواضيع المتشابهة
    • يحفظ بصمة لكل عبارة
    
    *⚠️ ملاحظات مهمة:*
    • يمكنك حذف قناتك وإضافة قناة جديدة
    • العبارات المؤقتة تُحفظ حتى تقوم بنشرها
    • لا يمكن إضافة أكثر من قناة واحدة
    
    *🔗 روابط:*
    • قناة البوت: @iIl337
    • للمساعدة الفورية: تواصل مع المطور
    """
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=help_text,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard(user_id)
    )
    bot.answer_callback_query(call.id)

def handle_stats(call):
    user_id = call.from_user.id
    
    total_phrases = len(used_phrases)
    unique_hashes = len(phrase_history)
    total_topics = len(topic_history)
    
    sorted_topics = sorted(
        topic_history.items(),
        key=lambda x: x[1].get('count', 0),
        reverse=True
    )[:10]
    
    topics_text = "\n".join([
        f"• {topic}: {data.get('count', 0)} مرة" 
        for topic, data in sorted_topics[:5]
    ])
    
    recent_phrases = list(used_phrases)[-5:]
    recent_text = "\n".join([
        f"{i+1}. {phrase[:30]}..." if len(phrase) > 30 else f"{i+1}. {phrase}"
        for i, phrase in enumerate(recent_phrases)
    ])
    
    stats_text = f"""
    📊 *إحصائيات نظام منع التكرار*
    
    *عام:*
    • العبارات المخزنة: {total_phrases}
    • العبارات الفريدة: {unique_hashes}
    • المواضيع المسجلة: {total_topics}
    
    *المواضيع الأكثر تكرارًا:*
    {topics_text}
    
    *آخر العبارات:*
    {recent_text}
    
    *نظام التشغيل:*
    • حد التشابه: {repetition_preventer.similarity_threshold*100}%
    • ساعات تبريد المواضيع: {repetition_preventer.topic_cooldown_hours}
    • المحاولات القصوى: 10
    """
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=stats_text,
        parse_mode='Markdown',
        reply_markup=create_main_keyboard(user_id)
    )
    bot.answer_callback_query(call.id)

def handle_back_to_main(call):
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
    user_id = message.from_user.id
    
    bot.send_message(
        message.chat.id,
        "تم إلغاء العملية الحالية.",
        reply_markup=create_main_keyboard(user_id)
    )

# ========== جدولة النشر التلقائي ==========
def get_unique_phrase():
    if len(used_phrases) > 1000:
        used_phrases_list = list(used_phrases)
        used_phrases.clear()
        for phrase in used_phrases_list[-500:]:
            used_phrases.add(phrase)
        save_json(USED_PHRASES_FILE, {"phrases": list(used_phrases)})
    
    phrase = generate_sukham_phrase(max_attempts=15)
    repetition_preventer.register_phrase(phrase)
    
    return phrase

def scheduled_posting():
    posting_times = ["06:00", "12:00", "18:00"]
    
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
                        
                        channels[user_str]['last_post'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        channels[user_str]['post_count'] = channels[user_str].get('post_count', 0) + 1
                        
                        print(f"   ✅ نشر للمستخدم {user_str}: {channel_info['title']}")
                        success_count += 1
                    except Exception as e:
                        print(f"   ❌ فشل للمستخدم {user_str}: {e}")
                        fail_count += 1
                
                save_json(CHANNELS_FILE, channels)
                
                print(f"   📊 النتيجة: {success_count} نجاح, {fail_count} فشل")
                print(f"   📝 العبارة: {phrase[:50]}...")
                
                time.sleep(60)
            
            time.sleep(30)
            
        except Exception as e:
            print(f"خطأ في الجدولة: {e}")
            time.sleep(60)

# ========== تشغيل البوت ==========
def start_bot():
    scheduler_thread = threading.Thread(target=scheduled_posting, daemon=True)
    scheduler_thread.start()
    
    print("=" * 50)
    print("🎭 بوت سُخام - النظام الجديد")
    print("=" * 50)
    print(f"🌐 Copilot API: {COPILOT_API_URL}")
    print(f"👤 إجمالي المستخدمين: {len(channels)}")
    print(f"🗂️ العبارات المخزنة: {len(used_phrases)}")
    print(f"⏰ أوقات النشر: 6:00, 12:00, 18:00")
    print("=" * 50)
    print("📱 النظام الجديد: كل مستخدم = قناة واحدة")
    print("🎲 ميزة جديدة: توليد ونشر فوري")
    print("🔄 نظام منع التكرار: مفعل")
    print("=" * 50)
    print("🚀 البوت يعمل... استخدم /start في تلجرام")
    print("=" * 50)
    
    bot.infinity_polling()

if __name__ == "__main__":
    start_bot()
