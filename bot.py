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
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from difflib import SequenceMatcher
import schedule

# ========== التهيئة ==========
TOKEN = "8543864168:AAHPqKr1glFPHaVF8NTH5OaSzrns9fIJue4"
ADMIN_ID = 6689435577
WEBHOOK_URL = "https://saher-jh37.onrender.com"

# تهيئة بوت تلجرام
bot = telebot.TeleBot(TOKEN)

# ========== إدارة الملفات ==========
CHANNELS_FILE = "channels.json"
USED_PHRASES_FILE = "used_phrases.json"
USER_PHRASES_FILE = "user_phrases.json"
PHRASE_HISTORY_FILE = "phrase_history.json"
TOPIC_HISTORY_FILE = "topic_history.json"
ADMIN_PHRASES_FILE = "admin_phrases.txt"
ADMIN_CONFIG_FILE = "admin_config.json"
BANNED_FILE = "banned.json"
SUBSCRIPTION_FILE = "subscription.json"

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
admin_config = load_json(ADMIN_CONFIG_FILE)
banned_users = load_json(BANNED_FILE)
subscription_config = load_json(SUBSCRIPTION_FILE)

# تهيئة الإعدادات الافتراضية
if not admin_config:
    admin_config = {
        "ads_interval": 24,  # ساعات بين الإعلانات
        "ads_count": 1,      # عدد الإعلانات المرسلة
        "subscription_channel": None  # قناة الاشتراك الإجباري
    }
    save_json(ADMIN_CONFIG_FILE, admin_config)

if not banned_users:
    banned_users = {
        "users": [],
        "channels": []
    }
    save_json(BANNED_FILE, banned_users)

if not subscription_config:
    subscription_config = {
        "channel_id": None,
        "channel_username": None,
        "channel_title": None,
        "enabled": False
    }
    save_json(SUBSCRIPTION_FILE, subscription_config)

# تحميل العبارات من ملف المدير
admin_phrases = []
if os.path.exists(ADMIN_PHRASES_FILE):
    with open(ADMIN_PHRASES_FILE, 'r', encoding='utf-8') as f:
        admin_phrases = [line.strip() for line in f if line.strip()]

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

# ========== توليد العبارات من ملف المدير ==========
def clean_phrase(text):
    """تنظيف العبارة من الرموز"""
    if not text:
        return ""
    
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
    """إنشاء عبارة من ملف المدير مع منع التكرار"""
    global admin_phrases
    
    if not admin_phrases:
        # إذا لم تكن هناك عبارات في الملف
        return "الكلمات تبحث عن معنى في صمت القلوب."
    
    attempts = 0
    timestamp = datetime.now().strftime("%H%M%S")
    start_index = int(timestamp[-2:]) % len(admin_phrases)
    
    while attempts < max_attempts:
        # اختيار عبارة بشكل عشوائي مع التحقق من التكرار
        for i in range(len(admin_phrases)):
            idx = (start_index + i) % len(admin_phrases)
            phrase = clean_phrase(admin_phrases[idx])
            
            if not phrase or len(phrase.strip()) < 5:
                continue
            
            is_duplicate, reason = repetition_preventer.is_phrase_duplicate(phrase)
            
            if not is_duplicate:
                return phrase
            else:
                attempts += 1
                if attempts >= max_attempts:
                    break
        
        # إذا لم نجد عبارة غير مكررة، نستخدم الأولى مع علامة
        phrase = clean_phrase(admin_phrases[0])
        if phrase:
            return f"{phrase} [جديدة]"
    
    # العبارات الاحتياطية
    fallback_phrases = [
        "في لحظات الصمت هذه، أسمع صوت قلبي يكتب ما لم تقله الكلمات.",
        "ربما نحتاج لأن نضيع قليلاً حتى نجد أنفسنا في المكان الذي لم نبحث عنه.",
        "أحيانًا تكون الذكريات وطنًا لا يعترف به أحد سوى القلب المنفى.",
        "لكل منا قصة لم تُروَ، وجرح لم يُضمّد، وضحكة علقت في الزمن.",
        "الحياة سفرية قصيرة، نحمل فيها أمتعة أثقل من ذاكرتنا."
    ]
    
    selected = fallback_phrases[int(timestamp[-1]) % len(fallback_phrases)]
    return selected

# ========== لوحة تحكم المدير ==========
def create_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📤 رفع ملف العبارات",
        "📢 إرسال إعلان",
        "📊 الإحصائيات",
        "🚫 حظر مستخدم/قناة",
        "✅ رفع حظر",
        "📋 قائمة المحظورين",
        "🔗 قناة الاشتراك",
        "⏰ إعدادات التوقيت",
        "🔙 رجوع"
    ]
    
    keyboard.add(*buttons[:2])
    keyboard.add(buttons[2], buttons[3])
    keyboard.add(buttons[4], buttons[5])
    keyboard.add(buttons[6], buttons[7])
    keyboard.add(buttons[8])
    
    return keyboard

def is_admin(user_id):
    """التحقق إذا كان المستخدم مدير"""
    return user_id == ADMIN_ID

@bot.message_handler(commands=['sos'])
def handle_sos(message):
    """لوحة تحكم المدير"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ هذا الأمر للمدير فقط!")
        return
    
    admin_msg = """
    🛠️ *لوحة تحكم المدير*
    
    *الإعدادات الحالية:*
    • قناة الاشتراك: {}
    • المدة بين الإعلانات: {} ساعة
    • عدد الإعلانات: {}
    • المستخدمين المحظورين: {}
    • القنوات المحظورة: {}
    
    *العبارات المخزنة:* {}
    
    اختر الخيار المطلوب من القائمة أدناه:
    """.format(
        subscription_config.get('channel_title', 'غير مضبوطة'),
        admin_config.get('ads_interval', 24),
        admin_config.get('ads_count', 1),
        len(banned_users.get('users', [])),
        len(banned_users.get('channels', [])),
        len(admin_phrases)
    )
    
    bot.send_message(message.chat.id, admin_msg, 
                     parse_mode='Markdown',
                     reply_markup=create_admin_keyboard())

@bot.message_handler(func=lambda message: message.text == "📤 رفع ملف العبارات" and is_admin(message.from_user.id))
def handle_upload_phrases(message):
    bot.reply_to(message, "📤 أرسل لي ملف نصي (.txt) يحتوي على العبارات\nكل عبارة يجب أن تكون في سطر منفصل.")
    bot.register_next_step_handler(message, process_phrases_file)

def process_phrases_file(message):
    global admin_phrases
    
    if message.document:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(ADMIN_PHRASES_FILE, 'wb') as f:
            f.write(downloaded_file)
        
        # قراءة العبارات
        with open(ADMIN_PHRASES_FILE, 'r', encoding='utf-8') as f:
            admin_phrases = [line.strip() for line in f if line.strip()]
        
        bot.reply_to(message, f"✅ تم رفع الملف بنجاح!\nتم تحميل {len(admin_phrases)} عبارة.")
    elif message.text:
        # إذا كان نصًا، حفظه كملف
        with open(ADMIN_PHRASES_FILE, 'w', encoding='utf-8') as f:
            f.write(message.text)
        
        with open(ADMIN_PHRASES_FILE, 'r', encoding='utf-8') as f:
            admin_phrases = [line.strip() for line in f if line.strip()]
        
        bot.reply_to(message, f"✅ تم حفظ العبارات!\nتم تحميل {len(admin_phrases)} عبارة.")
    else:
        bot.reply_to(message, "❌ يرجى إرسال ملف نصي (.txt) أو كتابة العبارات.")

@bot.message_handler(func=lambda message: message.text == "📢 إرسال إعلان" and is_admin(message.from_user.id))
def handle_send_ad(message):
    bot.reply_to(message, "📝 أرسل نص الإعلان الذي تريد نشره في جميع القنوات:")
    bot.register_next_step_handler(message, process_advertisement)

def process_advertisement(message):
    ad_text = message.text
    success_count = 0
    fail_count = 0
    
    for user_str, channel_info in channels.items():
        try:
            bot.send_message(channel_info['channel_id'], f"📢 إعلان:\n\n{ad_text}")
            success_count += 1
        except Exception as e:
            print(f"فشل إرسال إعلان لـ {channel_info['title']}: {e}")
            fail_count += 1
    
    bot.reply_to(message, f"✅ تم إرسال الإعلان!\n\nالنتائج:\n✅ نجاح: {success_count}\n❌ فشل: {fail_count}")

@bot.message_handler(func=lambda message: message.text == "🚫 حظر مستخدم/قناة" and is_admin(message.from_user.id))
def handle_ban_user(message):
    bot.reply_to(message, "أرسل أيدي المستخدم للحظر (رقم) أو معرف القناة (مثل @channel):")
    bot.register_next_step_handler(message, process_ban)

def process_ban(message):
    target = message.text.strip()
    
    if target.isdigit():
        # حظر مستخدم
        if int(target) not in banned_users['users']:
            banned_users['users'].append(int(target))
            save_json(BANNED_FILE, banned_users)
            bot.reply_to(message, f"✅ تم حظر المستخدم: {target}")
        else:
            bot.reply_to(message, f"⚠️ المستخدم {target} محظور بالفعل.")
    elif target.startswith('@'):
        # حظر قناة
        if target not in banned_users['channels']:
            banned_users['channels'].append(target)
            save_json(BANNED_FILE, banned_users)
            bot.reply_to(message, f"✅ تم حظر القناة: {target}")
        else:
            bot.reply_to(message, f"⚠️ القناة {target} محظورة بالفعل.")
    else:
        bot.reply_to(message, "❌ صيغة غير صحيحة. استخدم رقم أيدي أو معرف قناة يبدأ ب @")

@bot.message_handler(func=lambda message: message.text == "✅ رفع حظر" and is_admin(message.from_user.id))
def handle_unban_user(message):
    bot.reply_to(message, "أرسل أيدي المستخدم لرفع الحظر (رقم) أو معرف القناة (مثل @channel):")
    bot.register_next_step_handler(message, process_unban)

def process_unban(message):
    target = message.text.strip()
    
    if target.isdigit():
        # رفع حظر مستخدم
        target_id = int(target)
        if target_id in banned_users['users']:
            banned_users['users'].remove(target_id)
            save_json(BANNED_FILE, banned_users)
            bot.reply_to(message, f"✅ تم رفع الحظر عن المستخدم: {target}")
        else:
            bot.reply_to(message, f"⚠️ المستخدم {target} غير محظور.")
    elif target.startswith('@'):
        # رفع حظر قناة
        if target in banned_users['channels']:
            banned_users['channels'].remove(target)
            save_json(BANNED_FILE, banned_users)
            bot.reply_to(message, f"✅ تم رفع الحظر عن القناة: {target}")
        else:
            bot.reply_to(message, f"⚠️ القناة {target} غير محظورة.")
    else:
        bot.reply_to(message, "❌ صيغة غير صحيحة. استخدم رقم أيدي أو معرف قناة يبدأ ب @")

@bot.message_handler(func=lambda message: message.text == "📋 قائمة المحظورين" and is_admin(message.from_user.id))
def handle_ban_list(message):
    users_list = "\n".join([str(uid) for uid in banned_users.get('users', [])]) or "لا يوجد"
    channels_list = "\n".join(banned_users.get('channels', [])) or "لا يوجد"
    
    list_text = f"""
    📋 *قائمة المحظورين*
    
    *المستخدمين ({len(banned_users.get('users', []))}):*
    {users_list}
    
    *القنوات ({len(banned_users.get('channels', []))}):*
    {channels_list}
    """
    
    bot.reply_to(message, list_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🔗 قناة الاشتراك" and is_admin(message.from_user.id))
def handle_subscription_channel(message):
    bot.reply_to(message, "أرسل معرف قناة الاشتراك الإجباري (مثل @channel):")
    bot.register_next_step_handler(message, process_subscription_channel)

def process_subscription_channel(message):
    channel_username = message.text.strip()
    
    if not channel_username.startswith('@'):
        bot.reply_to(message, "❌ المعرف يجب أن يبدأ ب @")
        return
    
    try:
        chat = bot.get_chat(channel_username)
        
        # التحقق من عضوية البوت في القناة
        try:
            bot.get_chat_member(chat.id, bot.get_me().id)
        except:
            bot.reply_to(message, "❌ البوت ليس عضوًا في القناة! يجب إضافته أولاً.")
            return
        
        subscription_config.update({
            "channel_id": chat.id,
            "channel_username": channel_username,
            "channel_title": chat.title,
            "enabled": True
        })
        save_json(SUBSCRIPTION_FILE, subscription_config)
        
        bot.reply_to(message, f"✅ تم تعيين قناة الاشتراك: {chat.title}")
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "⏰ إعدادات التوقيت" and is_admin(message.from_user.id))
def handle_timing_settings(message):
    keyboard = InlineKeyboardMarkup(row_width=3)
    
    keyboard.add(
        InlineKeyboardButton("1 ساعة", callback_data="set_interval_1"),
        InlineKeyboardButton("6 ساعات", callback_data="set_interval_6"),
        InlineKeyboardButton("12 ساعة", callback_data="set_interval_12")
    )
    keyboard.add(
        InlineKeyboardButton("18 ساعة", callback_data="set_interval_18"),
        InlineKeyboardButton("24 ساعة", callback_data="set_interval_24"),
        InlineKeyboardButton("عدد الإعلانات", callback_data="set_ads_count")
    )
    
    bot.reply_to(message, 
                 f"⚙️ *الإعدادات الحالية:*\n\nالمدة بين الإعلانات: {admin_config.get('ads_interval', 24)} ساعة\nعدد الإعلانات: {admin_config.get('ads_count', 1)}\n\nاختر المدة الجديدة:",
                 parse_mode='Markdown',
                 reply_markup=keyboard)

@bot.message_handler(func=lambda message: message.text == "📊 الإحصائيات" and is_admin(message.from_user.id))
def handle_admin_stats(message):
    total_channels = len(channels)
    total_phrases = len(used_phrases)
    active_users = len([c for c in channels.values() if c.get('post_count', 0) > 0])
    
    stats_text = f"""
    📊 *إحصائيات البوت*
    
    *عام:*
    • إجمالي القنوات: {total_channels}
    • القنوات النشطة: {active_users}
    • العبارات المخزنة: {total_phrases}
    • العبارات المتاحة: {len(admin_phrases)}
    
    *نظام منع التكرار:*
    • العبارات الفريدة: {len(phrase_history)}
    • المواضيع المسجلة: {len(topic_history)}
    
    *آخر 5 قنوات مضافة:*
    """
    
    # إضافة آخر القنوات
    sorted_channels = sorted(
        channels.items(),
        key=lambda x: x[1].get('added_date', ''),
        reverse=True
    )[:5]
    
    for i, (user_id, channel_info) in enumerate(sorted_channels, 1):
        stats_text += f"\n{i}. {channel_info.get('title', 'غير معروف')} - {channel_info.get('post_count', 0)} منشور"
    
    bot.reply_to(message, stats_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🔙 رجوع" and is_admin(message.from_user.id))
def handle_admin_back(message):
    bot.send_message(message.chat.id, "تم الرجوع للقائمة الرئيسية.", 
                     reply_markup=telebot.types.ReplyKeyboardRemove())

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

# ========== التحقق من الاشتراك ==========
def check_subscription(user_id):
    """التحقق من اشتراك المستخدم في القناة الإجبارية"""
    if not subscription_config.get('enabled', False) or not subscription_config.get('channel_id'):
        return True  # إذا لم يتم تفعيل الاشتراك الإجباري
    
    try:
        member = bot.get_chat_member(subscription_config['channel_id'], user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# ========== معالجة الأوامر ==========
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    
    # التحقق من الحظر
    if user_id in banned_users.get('users', []):
        bot.reply_to(message, "⛔ تم حظرك من استخدام البوت.")
        return
    
    # التحقق من الاشتراك
    if not check_subscription(user_id) and subscription_config.get('enabled', False):
        channel_link = subscription_config.get('channel_username', '')
        bot.reply_to(message, 
                    f"⛔ يجب الاشتراك في قناتنا أولاً:\n{channel_link}\n\nبعد الاشتراك، أرسل /start مرة أخرى.")
        return
    
    welcome_msg = """
    🎭 *مرحبًا بك في بوت سُخام*
    
    أنا بوت النشر التلقائي بشخصية سُخام السوداوية الساخرة.
    
    *المميزات:*
    • لكل مستخدم قناة واحدة فقط
    • توليد عبارات فورية
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
    
    # التحقق من الحظر
    if user_id in banned_users.get('users', []):
        bot.answer_callback_query(call.id, "تم حظرك من استخدام البوت!")
        return
    
    # التحقق من الاشتراك
    if not check_subscription(user_id) and subscription_config.get('enabled', False):
        channel_link = subscription_config.get('channel_username', '')
        bot.answer_callback_query(call.id, f"يجب الاشتراك في: {channel_link}")
        return
    
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
        
        elif data.startswith("set_interval_"):
            handle_set_interval(call)
        
        elif data == "set_ads_count":
            handle_set_ads_count(call)
        
        else:
            bot.answer_callback_query(call.id, "زر غير معروف!")
    
    except Exception as e:
        bot.answer_callback_query(call.id, f"خطأ: {str(e)}")

def handle_set_interval(call):
    """معالجة تغيير مدة الإعلانات"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "هذا الخيار للمدير فقط!")
        return
    
    try:
        hours = int(call.data.replace("set_interval_", ""))
        admin_config['ads_interval'] = hours
        save_json(ADMIN_CONFIG_FILE, admin_config)
        
        bot.answer_callback_query(call.id, f"تم تعيين المدة إلى {hours} ساعة")
        
        # تحديث الرسالة
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ تم تعيين المدة بين الإعلانات إلى {hours} ساعة",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"خطأ: {str(e)}")

def handle_set_ads_count(call):
    """معالجة تغيير عدد الإعلانات"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "هذا الخيار للمدير فقط!")
        return
    
    bot.answer_callback_query(call.id, "سيتم إضافة هذه الميزة قريبًا")

# ========== وظائف البوت الأساسية (نفس الكود السابق) ==========
# [أبقى على نفس وظائف handle_my_channel, handle_generate_phrase, handle_publish_to_channel, 
# handle_add_channel_start, process_add_channel, handle_delete_channel, handle_help, 
# handle_stats, handle_back_to_main, handle_cancel, publish_phrase_to_channel, 
# handle_force_publish - مع تعديلات بسيطة لتعمل مع النظام الجديد]

# أضف هذه الدوال كما هي من الكود الأصلي مع تعديل بسيط:
def handle_my_channel(call):
    # نفس الكود مع تعديل بسيط للرسائل
    pass

def handle_generate_phrase(call):
    # نفس الكود
    pass

def handle_publish_to_channel(call):
    # نفس الكود
    pass

# ... [بقية الدوال كما هي]

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
                        # التحقق من حظر القناة
                        if channel_info.get('username', '') in banned_users.get('channels', []):
                            print(f"   ⚠️ تخطي قناة محظورة: {channel_info['title']}")
                            continue
                        
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

# ========== إرسال الطلبات الدورية للويب هووك ==========
def send_keep_alive():
    """إرسال طلب كل 5 دقائق للحفاظ على نشاط البوت"""
    def ping_webhook():
        try:
            response = requests.get(WEBHOOK_URL, timeout=10)
            print(f"[{datetime.now()}] ✅ Pinged webhook - Status: {response.status_code}")
        except Exception as e:
            print(f"[{datetime.now()}] ❌ Failed to ping webhook: {e}")
    
    # تشغيل أول ping
    ping_webhook()
    
    # جدولة ping كل 5 دقائق
    while True:
        schedule.every(5).minutes.do(ping_webhook)
        
        while True:
            schedule.run_pending()
            time.sleep(1)

# ========== تشغيل البوت ==========
def start_bot():
    # بدء خيط النشر التلقائي
    scheduler_thread = threading.Thread(target=scheduled_posting, daemon=True)
    scheduler_thread.start()
    
    # بدء خيط إرسال الطلبات الدورية
    keep_alive_thread = threading.Thread(target=send_keep_alive, daemon=True)
    keep_alive_thread.start()
    
    print("=" * 50)
    print("🎭 بوت سُخام - النظام الجديد")
    print("=" * 50)
    print(f"👤 المدير: {ADMIN_ID}")
    print(f"🌐 Webhook: {WEBHOOK_URL}")
    print(f"👤 إجمالي المستخدمين: {len(channels)}")
    print(f"🗂️ العبارات المخزنة: {len(admin_phrases)}")
    print(f"⏰ أوقات النشر: 6:00, 12:00, 18:00")
    print("=" * 50)
    print("📱 النظام الجديد: كل مستخدم = قناة واحدة")
    print("🛠️ لوحة تحكم المدير: /sos")
    print("🔄 نظام منع التكرار: مفعل")
    print("🔗 اشتراك إجباري: {}".format("مفعل" if subscription_config.get('enabled') else "معطل"))
    print("=" * 50)
    print("🚀 البوت يعمل... استخدم /start في تلجرام")
    print("=" * 50)
    
    bot.infinity_polling()

if __name__ == "__main__":
    start_bot()
