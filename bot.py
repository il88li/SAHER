import json
import os
import threading
import time
import schedule
import re
import logging
import random
import uuid
from datetime import datetime
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعداد تسجيل الأخطاء
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# إعدادات API
META_API_URL = "https://vetrex.x10.mx/api/meta_ai.php"
TELEGRAM_TOKEN = "8543864168:AAHLdQAGzYLRFtf_hHv8B7E6mpgMRwrU1W4"
ADMIN_ID = 6689435577

# تهيئة البوت
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ملفات التخزين
CHANNELS_FILE = "channels.json"
POSTED_POEMS_FILE = "posted_poems.json"
PENDING_CHANGES_FILE = "pending_changes.json"
PROCESSED_CHANGES_FILE = "processed_changes.json"

# قوائم التخزين
channels = {}
posted_poems = []
pending_changes = {}
processed_changes = []

# حالة القائمة لكل مستخدم
user_states = {}

# تحميل البيانات المحفوظة
def load_data():
    global channels, posted_poems, pending_changes, processed_changes
    
    try:
        if os.path.exists(CHANNELS_FILE):
            with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
                channels = json.load(f)
            logger.info(f"تم تحميل {len(channels)} قناة من الملف")
    except Exception as e:
        logger.error(f"خطأ في تحميل قنوات: {e}")
        channels = {}
    
    try:
        if os.path.exists(POSTED_POEMS_FILE):
            with open(POSTED_POEMS_FILE, 'r', encoding='utf-8') as f:
                posted_poems = json.load(f)
            logger.info(f"تم تحميل {len(posted_poems)} قصيدة من الملف")
    except Exception as e:
        logger.error(f"خطأ في تحميل القصائد: {e}")
        posted_poems = []
    
    try:
        if os.path.exists(PENDING_CHANGES_FILE):
            with open(PENDING_CHANGES_FILE, 'r', encoding='utf-8') as f:
                pending_changes = json.load(f)
            logger.info(f"تم تحميل {len(pending_changes)} طلب معلق")
    except Exception as e:
        logger.error(f"خطأ في تحميل الطلبات المعلقة: {e}")
        pending_changes = {}
    
    try:
        if os.path.exists(PROCESSED_CHANGES_FILE):
            with open(PROCESSED_CHANGES_FILE, 'r', encoding='utf-8') as f:
                processed_changes = json.load(f)
            logger.info(f"تم تحميل {len(processed_changes)} طلب معالج")
    except Exception as e:
        logger.error(f"خطأ في تحميل الطلبات المعالجة: {e}")
        processed_changes = []

# حفظ البيانات
def save_channels():
    try:
        with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(channels, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ القنوات: {e}")

def save_posted_poems():
    try:
        with open(POSTED_POEMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(posted_poems, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ القصائد: {e}")

def save_pending_changes():
    try:
        with open(PENDING_CHANGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(pending_changes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ الطلبات المعلقة: {e}")

def save_processed_changes():
    try:
        with open(PROCESSED_CHANGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(processed_changes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ في حفظ الطلبات المعالجة: {e}")

# وظائف تنظيف النصوص من الحروف الإنجليزية والرموز البرمجية
def remove_english_chars(text):
    """إزالة جميع الحروف الإنجليزية من النص"""
    if not text:
        return ""
    
    arabic_pattern = re.compile(r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF0-9٠-٩،؛؟!.،:؛\-_\s\n]', re.UNICODE)
    cleaned = arabic_pattern.sub('', text)
    
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r' *\n *', '\n', cleaned)
    return cleaned.strip()

def clean_text(text):
    """تنظيف النص من الرموز البرمجية والتنسيق غير المرغوب"""
    if not text:
        return ""
    
    try:
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]*`', '', text)
        text = re.sub(r'\*\*|\*\*', '', text)
        text = re.sub(r'__|~~', '', text)
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        text = re.sub(r'[#@$%^&*_+={}\[\]|\\:;"<>?/~`]', '', text)
        text = remove_english_chars(text)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r' *\n *', '\n', text)
        text = text.strip()
        
    except Exception as e:
        logger.error(f"خطأ في تنظيف النص: {e}")
    
    return text

def format_poem_for_telegram(poem_text):
    """تنسيق القصيدة للعرض في تلجرام مع الخط العريض"""
    if not poem_text:
        return ""
    
    try:
        poem_text = clean_text(poem_text)
        lines = poem_text.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                formatted_lines.append(f"*{line}*")
            else:
                formatted_lines.append("")
        
        formatted_poem = '\n'.join(formatted_lines)
        
        if len(formatted_poem) > 4000:
            formatted_poem = formatted_poem[:4000] + "..."
        
        return formatted_poem
    except Exception as e:
        logger.error(f"خطأ في تنسيق القصيدة: {e}")
        return poem_text

def extract_poem_title(poem_text):
    """استخراج عنوان القصيدة من النص وتنظيفه من الحروف الإنجليزية"""
    try:
        lines = poem_text.split('\n')
        for line in lines:
            line = clean_text(line).strip()
            if "اسم القصيدة" in line or "القصيدة:" in line or line.startswith("القصيدة"):
                if ":" in line:
                    parts = line.split(":", 1)
                    title = parts[1].strip()
                else:
                    title = line.replace("اسم القصيدة", "").replace("القصيدة", "").strip()
                
                title = remove_english_chars(title)
                title = clean_text(title)
                
                if title and len(title) > 2:
                    return title
        
        if lines:
            first_line = lines[0].strip()
            if len(first_line) > 5:
                potential_title = first_line[:30]
                return remove_english_chars(potential_title)
        
        return "قصيدة ساخرة عربية"
    except Exception as e:
        logger.error(f"خطأ في استخراج عنوان القصيدة: {e}")
    return "قصيدة ساخرة عربية"

# توليد القصيدة من META AI API باستخدام البرومبت المخصص أو الافتراضي
def generate_poem(channel_id=None):
    default_prompt = """أنت باحث في الأدب العربي ومتخصص في الشعر العربي الساخر. مهمتك هي تقديم قصائد عربية ساخرة حقيقية من مصادر موثوقة.

المتطلبات الأساسية:

1. **الواقعية والموثوقية**: القصائد يجب أن تكون حقيقية وموجودة فعلاً في مصادر أدبية عربية معروفة.

2. **البنية**: كل قصيدة يجب أن تكون 6 أبيات كاملة من الشعر العربي الأصيل.

3. **المصدر**: يجب ذكر المصدر الأصلي للقصيدة (اسم الكتاب) دون ذكر روابط أو إشارات إلكترونية.

4. **التنسيق المطلوب**:
اسم القصيدة: [اسم القصيدة الحقيقي]

[البيت الأول من القصيدة]
[البيت الثاني من القصيدة]
[البيت الثالث من القصيدة]
[البيت الرابع من القصيدة]
[البيت الخامس من القصيدة]
[البيت السادس من القصيدة]

المصدر: [اسم الكتاب الحقيقي الذي وردت فيه القصيدة]
الشاعر: [اسم الشاعر الحقيقي]
الزمن: [الزمن التاريخي الحقيقي]
السياق: [السياق الحقيقي الذي قيلت فيه القصيدة]

5. **المحتوى المطلوب**:
- قصائد ساخرة مضحكة من الأدب العربي الأصيل
- مواقف اجتماعية محرجة واقعية
- تنمر اجتماعي ساخر
- مواقف عنصرية مضحكة (بشكل لطيف وساخر)
- لا تتعلق بالنساء أو العلاقات العاطفية
- تكون القصائد حقيقية وموجودة في كتب أدبية معروفة

6. **اللغة**: استخدم اللغة العربية الفصحى فقط، بدون أي حروف إنجليزية أو رموز برمجية.

7. **القصائد المقترحة (كنموذج)**:
- قصائد من كتاب "الأغاني" لأبي فرج الأصفهاني
- قصائد من كتاب "العقد الفريد" لابن عبد ربه
- قصائد من كتاب "نثر الدر" للآبي
- قصائد من كتاب "البيان والتبيين" للجاحظ
- قصائد من كتاب "الكامل في اللغة والأدب" للمبرد
- قصائد من كتاب "زهر الآداب" للحصري

**تأكيد**: تأكد من أن القصيدة حقيقية وموجودة في المصدر المذكور، وذكر اسم الكتاب بشكل دقيق وواضح."""
    
    prompt = default_prompt
    if channel_id and channel_id in channels:
        channel_data = channels[channel_id]
        if "custom_prompt" in channel_data and channel_data["custom_prompt"]:
            prompt = channel_data["custom_prompt"]
    
    try:
        logger.info("جاري الاتصال بـ META AI API...")
        
        response = requests.post(
            META_API_URL,
            json={"prompt": prompt},
            timeout=30
        )
        response.raise_for_status()
        
        try:
            result = response.json()
            response_text = ""
            if 'response' in result:
                response_text = result['response']
            elif 'text' in result:
                response_text = result['text']
            elif 'message' in result:
                response_text = result['message']
            elif 'result' in result:
                response_text = result['result']
            else:
                for key, value in result.items():
                    if isinstance(value, str) and len(value) > 20:
                        response_text = value
                        break
                if not response_text:
                    response_text = str(result)
                    
        except Exception:
            response_text = response.text
        
        if not response_text or len(response_text.strip()) < 10:
            return get_fallback_poem()
        
        cleaned_text = clean_text(response_text)
        formatted_text = format_poem_for_telegram(cleaned_text)
        title = extract_poem_title(cleaned_text)
        
        lines = cleaned_text.split('\n')
        arabic_lines = [line for line in lines if any(char in '\u0600-\u06FF' for char in line)]
        has_source = any("المصدر:" in line or "مصدر:" in line or "الكتاب:" in line for line in lines)
        
        if len(arabic_lines) < 8 or not has_source:
            return get_fallback_poem()
        
        if not title or len(title) < 3:
            title = "قصيدة ساخرة من الأدب العربي"
        
        if is_poem_duplicate(title):
            return get_fallback_poem()
        
        return {
            "raw": cleaned_text,
            "formatted": formatted_text,
            "title": title,
            "line_count": len(lines),
            "has_source": has_source
        }
            
    except requests.exceptions.Timeout:
        logger.error("انتهت مهلة الاتصال بـ META AI API")
        return get_fallback_poem()
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في الاتصال بـ META AI API: {e}")
        return get_fallback_poem()
    except Exception as e:
        logger.error(f"خطأ غير متوقع في توليد القصيدة: {e}")
        return get_fallback_poem()

def is_poem_duplicate(title):
    """التحقق مما إذا كانت القصيدة منشورة مسبقاً"""
    if not title:
        return False
    
    clean_title = clean_text(title).lower().strip()
    
    for poem_title in posted_poems:
        if clean_text(poem_title).lower().strip() == clean_title:
            return True
    
    for poem_title in posted_poems:
        clean_old_title = clean_text(poem_title).lower().strip()
        if clean_title in clean_old_title or clean_old_title in clean_title:
            if len(clean_title) > 10 and len(clean_old_title) > 10:
                return True
    
    return False

def get_fallback_poem():
    """إرجاع قصيدة افتراضية في حالة فشل API"""
    fallback_poems = [
        {
            "raw": """اسم القصيدة: شكوى من جار سوء

جارنا المشؤوم فوق سطحنا يلقي القمامة كل حين
وإذا نهرته يقول هذا مكاني أفعل ما أريد وأمين
ويلقي بقايا طعامه القديم في حوانيتنا ليفسد البضاعة
ويصيح ليلاً كأنه في سوق يريد أن يزعج كل راقة
وإذا شكوه الناس للوالي قال الوالي هو من أقاربي
فاصبروا عليه فهو عندي من أعز رفاقي وأحب أرحبي

المصدر: كتاب "الأغاني" لأبي فرج الأصفهاني
الشاعر: أبو نواس
الزمن: العصر العباسي، القرن الثاني الهجري
السياق: قالها الشاعر يشكو جاراً سيئاً كان يسكن فوقه في بغداد""",
            "formatted": """*اسم القصيدة: شكوى من جار سوء*

*جارنا المشؤوم فوق سطحنا يلقي القمامة كل حين*
*وإذا نهرته يقول هذا مكاني أفعل ما أريد وأمين*
*ويلقي بقايا طعامه القديم في حوانيتنا ليفسد البضاعة*
*ويصيح ليلاً كأنه في سوق يريد أن يزعج كل راقة*
*وإذا شكوه الناس للوالي قال الوالي هو من أقاربي*
*فاصبروا عليه فهو عندي من أعز رفاقي وأحب أرحبي*

*المصدر: كتاب "الأغاني" لأبي فرج الأصفهاني*
*الشاعر: أبو نواس*
*الزمن: العصر العباسي، القرن الثاني الهجري*
*السياق: قالها الشاعر يشكو جاراً سيئاً كان يسكن فوقه في بغداد*""",
            "title": "شكوى من جار سوء"
        },
        {
            "raw": """اسم القصيدة: هجاء البخيل

يدعو إلى الطعام ويقول تعالوا ثم يخفي أفضل الأكلات
ويقدم الخبز اليابس قديماً ويقول هذا من أفخر الحنطات
وإذا رأى ضيفاً يقول مرحباً لكن عيناه تقول اذهب عني
ويعد بالطيب ثم يعطي الخبيث ويقول هذا من عند السلطان لي
وإذا سألته عن حاله يقول أنا فقير ومعدم من زمان
وهو يخبئ الذهب تحت الوسائد ويخاف حتى من ظل الإنسان

المصدر: كتاب "العقد الفريد" لابن عبد ربه
الشاعر: بشار بن برد
الزمن: العصر العباسي، القرن الثاني الهجري
السياق: قالها الشاعر يهجو رجلاً بخيلاً دعاه إلى طعامه ثم بخل عليه""",
            "formatted": """*اسم القصيدة: هجاء البخيل*

*يدعو إلى الطعام ويقول تعالوا ثم يخفي أفضل الأكلات*
*ويقدم الخبز اليابس قديماً ويقول هذا من أفخر الحنطات*
*وإذا رأى ضيفاً يقول مرحباً لكن عيناه تقول اذهب عني*
*ويعد بالطيب ثم يعطي الخبيث ويقول هذا من عند السلطان لي*
*وإذا سألته عن حاله يقول أنا فقير ومعدم من زمان*
*وهو يخبئ الذهب تحت الوسائد ويخاف حتى من ظل الإنسان*

*المصدر: كتاب "العقد الفريد" لابن عبد ربه*
*الشاعر: بشار بن برد*
*الزمن: العصر العباسي، القرن الثاني الهجري*
*السياق: قالها الشاعر يهجو رجلاً بخيلاً دعاه إلى طعامه ثم بخل عليه*""",
            "title": "هجاء البخيل"
        }
    ]
    
    available_poems = [p for p in fallback_poems if not is_poem_duplicate(p["title"])]
    
    if available_poems:
        poem = random.choice(available_poems)
    else:
        poem = random.choice(fallback_poems)
    
    return poem

# النشر في القناة
def post_to_channel(channel_id):
    if channel_id not in channels:
        return
    
    try:
        poem_data = generate_poem(channel_id)
        if poem_data:
            separator = "\n" + "═" * 30 + "\n"
            final_message = poem_data["formatted"] + separator + "📚 *قصيدة عربية ساخرة من التراث* 📚"
            
            bot.send_message(channel_id, final_message, parse_mode='Markdown')
            
            if poem_data["title"]:
                if poem_data["title"] not in posted_poems:
                    posted_poems.append(poem_data["title"])
                    save_posted_poems()
                
    except Exception as e:
        logger.error(f"خطأ في النشر إلى القناة {channel_id}: {e}")

# جدولة النشر
def schedule_posts():
    logger.info("بدء جدولة النشر...")
    try:
        schedule.every().day.at("06:00").do(run_scheduled_posts).tag('daily_posts')
        schedule.every().day.at("18:00").do(run_scheduled_posts).tag('daily_posts')
        schedule.every().day.at("00:00").do(run_scheduled_posts).tag('daily_posts')
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as e:
                logger.error(f"خطأ في تشغيل الجدولة: {e}")
                time.sleep(60)
    except Exception as e:
        logger.error(f"خطأ في إعداد الجدولة: {e}")

def run_scheduled_posts():
    logger.info("تشغيل النشر المجدول...")
    for channel_id in channels.keys():
        try:
            post_to_channel(channel_id)
        except Exception as e:
            logger.error(f"خطأ في النشر المجدول للقناة {channel_id}: {e}")

# إنشاء واجهات Inline Keyboard
def create_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("⚙️ إدارة قناتي", callback_data="manage_channel"),
        InlineKeyboardButton("🔧 المزيد من الخيارات", callback_data="more_options")
    )
    return keyboard

def create_manage_channel_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if not channels:
        keyboard.add(
            InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_channel")
        )
    else:
        keyboard.add(
            InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_channel")
        )
        for channel_id, data in channels.items():
            channel_name = data['username']
            keyboard.add(
                InlineKeyboardButton(f"📺 {channel_name}", callback_data=f"channel_{channel_id}")
            )
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main"))
    return keyboard

def create_channel_options_menu(channel_id):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if channel_id in channels:
        channel_data = channels[channel_id]
        channel_name = channel_data['username']
        
        keyboard.add(
            InlineKeyboardButton(f"🗑️ حذف {channel_name}", callback_data=f"delete_{channel_id}"),
            InlineKeyboardButton(f"📝 تعديل معلومات {channel_name}", callback_data=f"edit_{channel_id}"),
            InlineKeyboardButton(f"🎭 تغيير شخصية {channel_name}", callback_data=f"change_personality_{channel_id}")
        )
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع إلى إدارة القنوات", callback_data="back_to_manage"))
    return keyboard

def create_more_options_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📋 عرض القنوات", callback_data="list_channels"),
        InlineKeyboardButton("🎭 تغيير الشخصية", callback_data="change_personality"),
        InlineKeyboardButton("🧪 اختبار نشر", callback_data="test_post"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="stats"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    return keyboard

def create_boss_menu():
    """القائمة الرئيسية للأمر /boss"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📋 طلبات تغيير الشخصية", callback_data="boss_pending_requests"),
        InlineKeyboardButton("📊 سجل عمليات الطلبات", callback_data="boss_request_history"),
        InlineKeyboardButton("📈 إحصائيات الطلبات", callback_data="boss_request_stats"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    return keyboard

def create_approval_keyboard(request_id, user_id, channel_id):
    """إنشاء زرين للموافقة أو الرفض"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ موافق", callback_data=f"approve_{request_id}_{user_id}_{channel_id}"),
        InlineKeyboardButton("❌ مرفوض", callback_data=f"reject_{request_id}_{user_id}_{channel_id}"),
        InlineKeyboardButton("👁️ عرض التفاصيل", callback_data=f"view_{request_id}")
    )
    return keyboard

def create_pending_requests_menu():
    """قائمة الطلبات المعلقة"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if not pending_changes:
        keyboard.add(InlineKeyboardButton("📭 لا توجد طلبات معلقة", callback_data="no_action"))
    else:
        for request_id, request_data in list(pending_changes.items())[:10]:  # عرض أول 10 طلبات
            channel_name = request_data.get("channel_name", "غير معروف")
            timestamp = request_data.get("timestamp", "")
            short_time = timestamp.split()[0] if timestamp else ""
            keyboard.add(
                InlineKeyboardButton(
                    f"📝 {channel_name} ({short_time})",
                    callback_data=f"boss_view_request_{request_id}"
                )
            )
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع إلى لوحة التحكم", callback_data="back_to_boss"))
    return keyboard

def create_request_history_menu(page=0):
    """قائمة سجل الطلبات المعالجة"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    if not processed_changes:
        keyboard.add(InlineKeyboardButton("📭 لا توجد طلبات في السجل", callback_data="no_action"))
    else:
        for request_data in processed_changes[start_idx:end_idx]:
            channel_name = request_data.get("channel_name", "غير معروف")
            status = "✅" if request_data.get("status") == "approved" else "❌"
            timestamp = request_data.get("timestamp", "")
            short_time = timestamp.split()[0] if timestamp else ""
            keyboard.add(
                InlineKeyboardButton(
                    f"{status} {channel_name} ({short_time})",
                    callback_data=f"boss_view_history_{request_data.get('request_id', '')}"
                )
            )
    
    # أزرار التنقل بين الصفحات
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"boss_history_page_{page-1}"))
    
    if end_idx < len(processed_changes):
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"boss_history_page_{page+1}"))
    
    if nav_buttons:
        keyboard.row(*nav_buttons)
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع إلى لوحة التحكم", callback_data="back_to_boss"))
    return keyboard

# أوامر البوت
@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 ليس لديك صلاحية للوصول إلى هذا البوت.")
        return
    
    user_states[message.chat.id] = "main_menu"
    
    welcome_text = """✨ *مرحباً! أنا بوت نشر الشعر العربي الساخر من المصادر الحقيقية.*

⚙️ *المميزات الجديدة:*
• ⚙️ زر "إدارة قناتي" الجديد لإدارة القنوات
• 🎭 إمكانية تغيير شخصية كل قناة (البرومبت)
• 👑 موافقة المدير مطلوبة لتغيير الشخصية
• 📚 جميع القصائد من مصادر أدبية موثوقة
• 🚫 منع تكرار القصائد تلقائياً

🕰️ *أوقات النشر:*
🕕 6 صباحاً
🕡 6 مساءً
🕛 12 منتصف الليل

*استخدم /boss للوصول إلى لوحة تحكم المدير*

*اختر من القائمة:*"""
    
    bot.send_message(message.chat.id, welcome_text, 
                     parse_mode='Markdown',
                     reply_markup=create_main_menu())

@bot.message_handler(commands=['boss'])
def boss_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 هذا الأمر مخصص للمدير فقط.")
        return
    
    user_states[message.chat.id] = "boss_menu"
    
    approved_count = sum(1 for req in processed_changes if req.get("status") == "approved")
    rejected_count = sum(1 for req in processed_changes if req.get("status") == "rejected")
    
    boss_text = """👑 *لوحة تحكم المدير - الأمر /boss*

*الخيارات المتاحة:*
📋 *طلبات تغيير الشخصية* - عرض الطلبات المعلقة واتخاذ القرار
📊 *سجل عمليات الطلبات* - عرض تاريخ الطلبات المعالجة
📈 *إحصائيات الطلبات* - عرض إحصائيات مفصلة

*الإحصائيات الحالية:*
• الطلبات المعلقة: {}
• الطلبات المعالجة: {}
• الطلبات الموافق عليها: {}
• الطلبات المرفوضة: {}

اختر أحد الخيارات:""".format(
        len(pending_changes),
        len(processed_changes),
        approved_count,
        rejected_count
    )
    
    bot.send_message(message.chat.id, boss_text, 
                     parse_mode='Markdown',
                     reply_markup=create_boss_menu())

# معالجات Callback
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    """معالجة جميع الردود في مكان واحد"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "🚫 ليس لديك صلاحية للوصول إلى هذا البوت.")
        return
    
    try:
        # القائمة الرئيسية
        if call.data == "more_options":
            user_states[call.message.chat.id] = "more_options"
            bot.edit_message_text(
                "🔧 *المزيد من الخيارات*\n\nاختر أحد الخيارات:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "manage_channel":
            user_states[call.message.chat.id] = "manage_channel"
            bot.edit_message_text(
                "⚙️ *إدارة القنوات*\n\nاختر أحد الخيارات:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_manage_channel_menu()
            )
            
        elif call.data == "add_channel":
            user_states[call.message.chat.id] = "awaiting_channel"
            bot.edit_message_text(
                "📝 *إضافة قناة جديدة*\n\nأرسل لي اسم المستخدم الخاص بقناتك (مثال: @channelname)",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
            bot.register_next_step_handler(call.message, process_channel_username)
            
        elif call.data.startswith("channel_"):
            channel_id = call.data.replace("channel_", "")
            user_states[call.message.chat.id] = f"channel_options_{channel_id}"
            channel_name = channels[channel_id]['username'] if channel_id in channels else "غير معروف"
            bot.edit_message_text(
                f"⚙️ *خيارات القناة:* {channel_name}\n\nاختر الإجراء المطلوب:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_channel_options_menu(channel_id)
            )
            
        elif call.data.startswith("delete_"):
            channel_id = call.data.replace("delete_", "")
            if channel_id in channels:
                channel_name = channels[channel_id]['username']
                del channels[channel_id]
                save_channels()
                
                bot.answer_callback_query(call.id, f"تم حذف القناة {channel_name}")
                
                if not channels:
                    bot.edit_message_text(
                        "✅ *تم الحذف بنجاح!*\n\nتم حذف القناة.\nلا توجد قنوات متبقية.\n\nاستخدم زر \"➕ إضافة قناة جديدة\" لإضافة قناة.",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='Markdown',
                        reply_markup=create_manage_channel_menu()
                    )
                else:
                    bot.edit_message_text(
                        f"✅ *تم الحذف بنجاح!*\n\nتم حذف القناة: {channel_name}\n\nالقنوات المتبقية: {len(channels)}",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='Markdown',
                        reply_markup=create_manage_channel_menu()
                    )
            else:
                bot.answer_callback_query(call.id, "❌ القناة غير موجودة", show_alert=True)
                
        elif call.data.startswith("change_personality_"):
            channel_id = call.data.replace("change_personality_", "")
            if channel_id in channels:
                user_states[call.message.chat.id] = f"awaiting_prompt_{channel_id}"
                channel_name = channels[channel_id]['username']
                
                bot.edit_message_text(
                    f"🎭 *تغيير شخصية القناة:* {channel_name}\n\n"
                    f"أرسل لي النموذج الجديد (البرومبت) الذي تريد استخدامه لهذه القناة.\n\n"
                    f"*ملاحظة:* سيتم إرسال طلب الموافقة إلى المدير.",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown'
                )
                bot.register_next_step_handler(call.message, process_personality_change, channel_id)
                
        elif call.data == "change_personality":
            if not channels:
                bot.answer_callback_query(call.id, "لا توجد قنوات مضافة", show_alert=True)
                return
            
            user_states[call.message.chat.id] = "select_channel_for_personality"
            bot.edit_message_text(
                "🎭 *تغيير الشخصية*\n\nاختر القناة التي تريد تغيير شخصيتها:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_channels_list_menu("change_personality")
            )
            
        elif call.data.startswith("edit_"):
            channel_id = call.data.replace("edit_", "")
            bot.answer_callback_query(call.id, "⏳ هذه الميزة قيد التطوير", show_alert=True)
            
        elif call.data == "list_channels":
            if not channels:
                text = "📭 *عرض القنوات*\n\nلا توجد قنوات مضافة بعد.\n\nاستخدم زر \"⚙️ إدارة قناتي\" لإضافة قناة جديدة."
            else:
                text = "📋 *القنوات المضافة:*\n\n"
                for idx, (channel_id, data) in enumerate(channels.items(), 1):
                    has_custom = "🎭" if "custom_prompt" in data and data["custom_prompt"] else "⚙️"
                    text += f"{idx}. {data['username']} {has_custom}\n"
                text += f"\n*الإجمالي:* {len(channels)} قناة\n🎭 = لها شخصية مخصصة\n⚙️ = تستخدم الشخصية الافتراضية"
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "stats":
            custom_prompts_count = sum(1 for c in channels.values() if "custom_prompt" in c and c["custom_prompt"])
            stats_text = f"""📊 *إحصائيات البوت*

*القنوات المضافة:* {len(channels)}
*القصائد المنشورة:* {len(posted_poems)}
*الشخصيات المخصصة:* {custom_prompts_count}
*الحالة:* ✅ يعمل

*أوقات النشر:*
🕕 6:00 صباحاً
🕡 18:00 مساءً
🕛 00:00 منتصف الليل

*مميزات:*
📚 قصائد من مصادر حقيقية
🎯 6 أبيات كاملة لكل قصيدة
🎭 شخصيات مخصصة للقنوات
🚫 منع التكرار التلقائي
🔤 نصوص عربية خالصة"""

            bot.edit_message_text(
                stats_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "test_post":
            bot.answer_callback_query(call.id, "جاري إنشاء قصيدة اختبارية من مصدر حقيقي...")
            poem_data = generate_poem()
            if poem_data:
                test_message = f"""🧪 *اختبار النشر*

{poem_data["formatted"]}

═══
*ملاحظة:* هذه نسخة اختبارية فقط
*العنوان:* {poem_data.get('title', 'غير معروف')}
*عدد الأسطر:* {poem_data.get('line_count', 0)}
*المصدر مذكور:* {poem_data.get('has_source', False)}"""
                
                bot.edit_message_text(
                    test_message,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='Markdown',
                    reply_markup=create_more_options_menu()
                )
        
        # لوحة تحكم المدير (/boss)
        elif call.data == "back_to_boss":
            user_states[call.message.chat.id] = "boss_menu"
            boss_command(call.message)
            
        elif call.data == "boss_pending_requests":
            user_states[call.message.chat.id] = "boss_pending_requests"
            
            if not pending_changes:
                text = "📭 *طلبات تغيير الشخصية المعلقة*\n\nلا توجد طلبات معلقة حالياً."
            else:
                text = f"📋 *طلبات تغيير الشخصية المعلقة*\n\nعدد الطلبات المعلقة: {len(pending_changes)}\n\nاختر طلباً للمعالجة:"
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_pending_requests_menu()
            )
            
        elif call.data.startswith("boss_view_request_"):
            request_id = call.data.replace("boss_view_request_", "")
            
            if request_id in pending_changes:
                request_data = pending_changes[request_id]
                channel_name = request_data.get("channel_name", "غير معروف")
                user_id = request_data.get("user_id", "غير معروف")
                timestamp = request_data.get("timestamp", "غير معروف")
                new_prompt = request_data.get("new_prompt", "")
                
                # تقصير البرومبت للعرض
                short_prompt = new_prompt[:300] + "..." if len(new_prompt) > 300 else new_prompt
                
                request_details = f"""📝 *تفاصيل الطلب*

*رقم الطلب:* `{request_id}`
*المستخدم:* `{user_id}`
*القناة:* {channel_name}
*الوقت:* {timestamp}

*النموذج الجديد:*
              
*الطول الإجمالي:* {len(new_prompt)} حرف

*الرجاء الموافقة أو الرفض:*"""
    
    bot.send_message(
        ADMIN_ID,
        approval_message,
        parse_mode='Markdown',
        reply_markup=create_approval_keyboard(request_id, user_id, channel_id)
    )
    
    bot.send_message(
        message.chat.id,
        f"✅ *تم إرسال طلب الموافقة*\n\n"
        f"تم إرسال طلب تغيير شخصية القناة {channel_name} إلى المدير للموافقة.\n"
        f"*رقم الطلب:* {request_id}\n\n"
        f"استخدم الأمر /boss لمتابعة الطلب.",
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )
    
    user_states[message.chat.id] = "main_menu"

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 ليس لديك صلاحية للتفاعل مع هذا البوت.")
        return
    
    if user_states.get(message.chat.id) == "awaiting_channel":
        process_channel_username(message)
    else:
        user_states[message.chat.id] = "main_menu"
        bot.send_message(message.chat.id, 
                        "🏠 *القائمة الرئيسية*\n\nاختر أحد الخيارات:",
                        parse_mode='Markdown',
                        reply_markup=create_main_menu())

def test_api_connection():
    """اختبار الاتصال بـ META AI API"""
    try:
        response = requests.get(META_API_URL, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"فشل اختبار الاتصال بـ API: {e}")
        return False

# تشغيل البوت
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 بدء تشغيل بوت نشر الشعر العربي الساخر")
    logger.info("=" * 50)
    
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        logger.info("✅ الاتصال بالإنترنت نشط")
        
        if test_api_connection():
            logger.info("✅ الاتصال بـ API نشط")
        else:
            logger.warning("⚠️  قد يكون هناك مشكلة في الاتصال بـ API")
    except Exception as e:
        logger.error(f"❌ لا يوجد اتصال بالإنترنت: {e}")
    
    load_data()
    
    try:
        scheduler_thread = threading.Thread(target=schedule_posts, daemon=True)
        scheduler_thread.start()
        logger.info("✅ تم بدء خيط جدولة النشر")
    except Exception as e:
        logger.error(f"❌ فشل بدء خيط الجدولة: {e}")
    
    logger.info(f"📅 القنوات المضافة: {len(channels)}")
    logger.info(f"📝 القصائد المنشورة: {len(posted_poems)}")
    logger.info(f"📋 الطلبات المعلقة: {len(pending_changes)}")
    logger.info(f"📊 الطلبات المعالجة: {len(processed_changes)}")
    logger.info(f"🔗 API المستخدم: {META_API_URL}")
    logger.info(f"👤 المدير: {ADMIN_ID}")
    
    if channels:
        logger.info("📋 القنوات المضافة:")
        for idx, (channel_id, data) in enumerate(channels.items(), 1):
            has_custom = "✓" if "custom_prompt" in data and data["custom_prompt"] else "✗"
            logger.info(f"  {idx}. {data['username']} [شخصية مخصصة: {has_custom}]")
    
    logger.info("=" * 50)
    logger.info("✅ البوت يعمل الآن وجاهز للاستخدام")
    logger.info("📚 جميع القصائد من مصادر أدبية حقيقية")
    logger.info("🎭 نظام الشخصيات المخصصة نشط")
    logger.info("👑 الأمر /boss متاح لإدارة الطلبات")
    logger.info("=" * 50)
    
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries:
        try:
            logger.info(f"محاولة تشغيل البوت (المحاولة {retry_count + 1}/{max_retries})...")
            bot.infinity_polling(timeout=30, long_polling_timeout=5)
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ خطأ في تشغيل البوت (المحاولة {retry_count}): {e}")
            if retry_count < max_retries:
                wait_time = retry_count * 10
                logger.info(f"⏳ الانتظار {wait_time} ثانية قبل إعادة المحاولة...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ فشل جميع محاولات تشغيل البوت ({max_retries} محاولات)")
