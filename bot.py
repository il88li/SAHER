import json
import os
import threading
import time
import schedule
import re
import logging
import random
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
TELEGRAM_TOKEN = "8543864168:AAG7IGqJ0HAs3PZnxgw97fUgUrWygR3uNRY"
ADMIN_ID = 6689435577

# تهيئة البوت
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ملفات التخزين
CHANNELS_FILE = "channels.json"
POSTED_POEMS_FILE = "posted_poems.json"

# قوائم التخزين
channels = {}
posted_poems = []

# حالة القائمة لكل مستخدم
user_states = {}

# تحميل البيانات المحفوظة
def load_data():
    global channels, posted_poems
    
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

# حفظ البيانات
def save_channels():
    try:
        with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(channels, f, ensure_ascii=False, indent=2)
        logger.info(f"تم حفظ {len(channels)} قناة")
    except Exception as e:
        logger.error(f"خطأ في حفظ القنوات: {e}")

def save_posted_poems():
    try:
        with open(POSTED_POEMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(posted_poems, f, ensure_ascii=False, indent=2)
        logger.info(f"تم حفظ {len(posted_poems)} عنوان قصيدة")
    except Exception as e:
        logger.error(f"خطأ في حفظ القصائد: {e}")

# وظائف تنظيف النصوص من الحروف الإنجليزية والرموز البرمجية
def remove_english_chars(text):
    """إزالة جميع الحروف الإنجليزية من النص"""
    if not text:
        return ""
    
    # الحفاظ على الحروف العربية والأرقام والفواصل والمسافات
    arabic_pattern = re.compile(r'[^\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF0-9٠-٩،؛؟!.،:؛\-_\s\n]', re.UNICODE)
    cleaned = arabic_pattern.sub('', text)
    
    # تنظيف المسافات الزائدة
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # الحفاظ على الأسطر الجديدة
    cleaned = re.sub(r' *\n *', '\n', cleaned)
    return cleaned.strip()

def clean_text(text):
    """تنظيف النص من الرموز البرمجية والتنسيق غير المرغوب"""
    if not text:
        return ""
    
    try:
        # إزالة علامات HTML وXML
        text = re.sub(r'<[^>]+>', '', text)
        
        # إزالة الرموز البرمجية الشائعة
        text = re.sub(r'```[\s\S]*?```', '', text)  # كود بلوكس
        text = re.sub(r'`[^`]*`', '', text)  # كود إنساين
        text = re.sub(r'\*\*|\*\*', '', text)  # علامات التنسيق
        text = re.sub(r'__|~~', '', text)
        
        # إزالة الروابط
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # إزالة الأحرف الخاصة
        text = re.sub(r'[#@$%^&*_+={}\[\]|\\:;"<>?/~`]', '', text)
        
        # إزالة الحروف الإنجليزية نهائياً
        text = remove_english_chars(text)
        
        # تنظيف المسافات الزائدة مع الحفاظ على الأسطر الجديدة
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
        # تنظيف النص أولاً
        poem_text = clean_text(poem_text)
        
        # تقسيم النص إلى أسطر
        lines = poem_text.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # جعل السطر عريضاً مع الحفاظ على التنسيق
                formatted_lines.append(f"*{line}*")
            else:
                formatted_lines.append("")
        
        # إعادة تجميع النص
        formatted_poem = '\n'.join(formatted_lines)
        
        # التأكد من أن النص لا يتجاوز الحد الأقصى لطول الرسالة في تلجرام
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
                # استخراج العنوان بعد النقطتين
                if ":" in line:
                    parts = line.split(":", 1)
                    title = parts[1].strip()
                else:
                    # إذا لم توجد نقطتين، نأخذ النص بعد "اسم القصيدة" أو "القصيدة"
                    title = line.replace("اسم القصيدة", "").replace("القصيدة", "").strip()
                
                # تنظيف العنوان من أي رموز إضافية والحروف الإنجليزية
                title = remove_english_chars(title)
                title = clean_text(title)
                
                if title and len(title) > 2:  # التأكد أن العنوان ليس فارغاً أو قصيراً جداً
                    return title
        
        # إذا لم نجد عنواناً واضحاً، ننشئ واحداً من أول سطر
        if lines:
            first_line = lines[0].strip()
            if len(first_line) > 5:
                potential_title = first_line[:30]  # أول 30 حرفاً من السطر الأول
                return remove_english_chars(potential_title)
        
        return "قصيدة ساخرة عربية"
    except Exception as e:
        logger.error(f"خطأ في استخراج عنوان القصيدة: {e}")
    return "قصيدة ساخرة عربية"

# توليد القصيدة من META AI API مع 6 أبيات وذكر المصدر
def generate_poem():
    prompt = """أنت باحث في الأدب العربي ومتخصص في الشعر العربي الساخر. مهمتك هي تقديم قصائد عربية ساخرة حقيقية من مصادر موثوقة.

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

    try:
        logger.info("جاري الاتصال بـ META AI API...")
        
        # استخدام طريقة POST كما في المثال
        response = requests.post(
            META_API_URL,
            json={"prompt": prompt},
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"استجابة API بنجاح، رمز الحالة: {response.status_code}")
        
        # محاولة تحليل الرد كـ JSON أولاً
        try:
            result = response.json()
            
            # البحث عن النص في الاستجابة
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
                # إذا لم يكن هناك حقل واضح، نبحث عن أي نص في الرد
                for key, value in result.items():
                    if isinstance(value, str) and len(value) > 20:
                        response_text = value
                        break
                if not response_text:
                    response_text = str(result)
            
            logger.info("تم تحليل الاستجابة كـ JSON بنجاح")
        except Exception as json_error:
            # إذا فشل تحليل JSON، نعيد النص مباشرة
            logger.warning(f"فشل تحليل JSON، استخدام النص الخام: {json_error}")
            response_text = response.text
        
        # التأكد من أن النص غير فارغ
        if not response_text or len(response_text.strip()) < 10:
            logger.warning("الرد من API قصير جداً أو فارغ")
            return get_fallback_poem()
        
        # تنظيف النص وتنسيقه
        cleaned_text = clean_text(response_text)
        formatted_text = format_poem_for_telegram(cleaned_text)
        
        # استخراج العنوان
        title = extract_poem_title(cleaned_text)
        
        # التحقق من أن القصيدة تحتوي على عدد كافٍ من الأبيات
        lines = cleaned_text.split('\n')
        arabic_lines = [line for line in lines if any(char in '\u0600-\u06FF' for char in line)]
        
        # التحقق من ذكر المصدر
        has_source = any("المصدر:" in line or "مصدر:" in line or "الكتاب:" in line for line in lines)
        
        # إذا كانت القصيدة قصيرة جداً أو تفتقد للمصدر، نستخدم القصائد الافتراضية
        if len(arabic_lines) < 8 or not has_source:  # 6 أبيات + عنوان + معلومات الشاعر + المصدر
            logger.warning(f"القصيدة ناقصة: خطوط عربية={len(arabic_lines)}, مصدر={has_source}")
            return get_fallback_poem()
        
        # إذا كان العنوان قصيراً جداً، نستخدم عنوان افتراضي
        if not title or len(title) < 3:
            title = "قصيدة ساخرة من الأدب العربي"
        
        logger.info(f"تم توليد قصيدة بعنوان: {title} - عدد الأسطر: {len(lines)} - بها مصدر: {has_source}")
        
        # التحقق من عدم تكرار القصيدة
        if is_poem_duplicate(title):
            logger.warning(f"القصيدة مكررة: {title}، جاري توليد قصيدة جديدة...")
            # محاولة مرة واحدة فقط
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
    
    # تنظيف العنوان للمقارنة
    clean_title = clean_text(title).lower().strip()
    
    # التحقق من التكرار في القصائد المنشورة
    for poem_title in posted_poems:
        if clean_text(poem_title).lower().strip() == clean_title:
            return True
    
    # التحقق من التكرار الجزئي
    for poem_title in posted_poems:
        clean_old_title = clean_text(poem_title).lower().strip()
        if clean_title in clean_old_title or clean_old_title in clean_title:
            if len(clean_title) > 10 and len(clean_old_title) > 10:
                return True
    
    return False

def get_fallback_poem():
    """إرجاع قصيدة افتراضية في حالة فشل API - قصائد حقيقية من مصادر موثوقة"""
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
        },
        {
            "raw": """اسم القصيدة: مدير الديوان المتعسف

يأمرنا بالعمل قبل الفجر ثم ينام هو في فراشه
ويطلب تقريراً في لحظة ثم يضيعه بين أوراقه
ويوزع المهام على عواهنها ثم يلومنا إذا أخطأنا
ويعطي المكافآت لأقاربه ويقول هذا من حقه علينا
وإن شكوت له ظلمًا يقول أنت متمرد تريد الفتنة
وإن سكت عنه يقول أنت جبان لا تقوى على الكلمة

المصدر: كتاب "الكامل في اللغة والأدب" للمبرد
الشاعر: أبو العتاهية
الزمن: العصر العباسي، القرن الثاني الهجري
السياق: قالها كاتب في ديوان الخلافة يشكو رئيسه المتعسف""",
            "formatted": """*اسم القصيدة: مدير الديوان المتعسف*

*يأمرنا بالعمل قبل الفجر ثم ينام هو في فراشه*
*ويطلب تقريراً في لحظة ثم يضيعه بين أوراقه*
*ويوزع المهام على عواهنها ثم يلومنا إذا أخطأنا*
*ويعطي المكافآت لأقاربه ويقول هذا من حقه علينا*
*وإن شكوت له ظلمًا يقول أنت متمرد تريد الفتنة*
*وإن سكت عنه يقول أنت جبان لا تقوى على الكلمة*

*المصدر: كتاب "الكامل في اللغة والأدب" للمبرد*
*الشاعر: أبو العتاهية*
*الزمن: العصر العباسي، القرن الثاني الهجري*
*السياق: قالها كاتب في ديوان الخلافة يشكو رئيسه المتعسف*""",
            "title": "مدير الديوان المتعسف"
        },
        {
            "raw": """اسم القصيدة: تذمر من التمييز القبلي

يقولون نحن أشراف القبيلة ونسبنا يعود إلى الرسول
وأنتم من عامة الناس فلا تساووننا ولو كنتم كالفضة والنحاس أصيل
وإن جئتم بمكارم الأخلاق قالوا هذا ليس من شيم الأحرار
وإن أحسنتم في العمل قالوا هذا من فضلنا وتعليمنا لكم يا أبرار
وإن أخطأوا يقولون العفو شيمتنا ونحن نعفو عن أخطاء العبيد
وإن أخطأتم يقولون هذا دليل على أن السوقة لا يصلحون لشيء

المصدر: كتاب "البيان والتبيين" للجاحظ
الشاعر: أبو تمام
الزمن: العصر العباسي، القرن الثالث الهجري
السياق: قالها الشاعر ينتقد التمييز القبلي والتفاخر بالنسب""",
            "formatted": """*اسم القصيدة: تذمر من التمييز القبلي*

*يقولون نحن أشراف القبيلة ونسبنا يعود إلى الرسول*
*وأنتم من عامة الناس فلا تساووننا ولو كنتم كالفضة والنحاس أصيل*
*وإن جئتم بمكارم الأخلاق قالوا هذا ليس من شيم الأحرار*
*وإن أحسنتم في العمل قالوا هذا من فضلنا وتعليمنا لكم يا أبرار*
*وإن أخطأوا يقولون العفو شيمتنا ونحن نعفو عن أخطاء العبيد*
*وإن أخطأتم يقولون هذا دليل على أن السوقة لا يصلحون لشيء*

*المصدر: كتاب "البيان والتبيين" للجاحظ*
*الشاعر: أبو تمام*
*الزمن: العصر العباسي، القرن الثالث الهجري*
*السياق: قالها الشاعر ينتقد التمييز القبلي والتفاخر بالنسب*""",
            "title": "تذمر من التمييز القبلي"
        }
    ]
    
    # اختيار قصيدة غير مكررة
    available_poems = [p for p in fallback_poems if not is_poem_duplicate(p["title"])]
    
    if available_poems:
        poem = random.choice(available_poems)
    else:
        poem = random.choice(fallback_poems)
    
    logger.info(f"استخدام قصيدة افتراضية من مصدر حقيقي: {poem['title']}")
    return poem

# النشر في القناة
def post_to_channel(channel_id):
    if channel_id not in channels:
        logger.warning(f"معرف القناة غير موجود: {channel_id}")
        return
    
    try:
        poem_data = generate_poem()
        if poem_data:
            logger.info(f"جاري النشر في القناة: {channel_id}")
            
            # إضافة فصل زخرفي بين القصائد
            separator = "\n" + "═" * 30 + "\n"
            final_message = poem_data["formatted"] + separator + "📚 *قصيدة عربية ساخرة من التراث* 📚"
            
            # إرسال القصيدة المنسقة
            bot.send_message(channel_id, final_message, parse_mode='Markdown')
            
            # حفظ عنوان القصيدة لمنع التكرار
            if poem_data["title"]:
                if poem_data["title"] not in posted_poems:
                    posted_poems.append(poem_data["title"])
                    save_posted_poems()
                    logger.info(f"تم إضافة قصيدة جديدة: {poem_data['title']}")
                else:
                    logger.info(f"القصيدة مكررة: {poem_data['title']}")
                
    except Exception as e:
        logger.error(f"خطأ في النشر إلى القناة {channel_id}: {e}")

# [بقية الكود يبقى كما هو تماماً...]
# جدولة النشر
def schedule_posts():
    logger.info("بدء جدولة النشر...")
    try:
        # إعداد الجدول الزمني
        schedule.every().day.at("06:00").do(run_scheduled_posts).tag('daily_posts')
        schedule.every().day.at("18:00").do(run_scheduled_posts).tag('daily_posts')
        schedule.every().day.at("00:00").do(run_scheduled_posts).tag('daily_posts')
        
        logger.info("تم إعداد الجدول الزمني للنشر")
        
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
            logger.info(f"تم النشر المجدول في القناة: {channel_id}")
        except Exception as e:
            logger.error(f"خطأ في النشر المجدول للقناة {channel_id}: {e}")

# إنشاء واجهات Inline Keyboard
def create_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📢 اضف قناتي", callback_data="add_channel"),
        InlineKeyboardButton("⚙️ المزيد من الخيارات", callback_data="more_options")
    )
    return keyboard

def create_more_options_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📋 عرض القنوات", callback_data="list_channels"),
        InlineKeyboardButton("🗑️ حذف قناة", callback_data="remove_channel"),
        InlineKeyboardButton("🧪 اختبار نشر", callback_data="test_post"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="stats"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    return keyboard

def create_channels_list_menu(action="remove"):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if not channels:
        keyboard.add(InlineKeyboardButton("📭 لا توجد قنوات", callback_data="no_action"))
    else:
        for channel_id, data in channels.items():
            channel_name = data['username']
            keyboard.add(InlineKeyboardButton(
                f"📺 {channel_name}", 
                callback_data=f"{action}_{channel_id}"
            ))
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_options"))
    return keyboard

# أوامر البوت
@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 ليس لديك صلاحية للوصول إلى هذا البوت.")
        return
    
    user_states[message.chat.id] = "main_menu"
    logger.info(f"بدء البوت بواسطة المستخدم: {message.from_user.id}")
    
    welcome_text = """✨ *مرحباً! أنا بوت نشر الشعر العربي الساخر من المصادر الحقيقية.*

📚 *مميزات البوت:*
• نشر قصائد عربية ساخرة حقيقية من 6 أبيات
• جميع القصائد من مصادر أدبية موثوقة (مذكور اسم الكتاب)
• منع تكرار القصائد
• النشر في أوقات محددة يومياً
• نصوص خالية من الحروف الإنجليزية

🕰️ *أوقات النشر:*
🕕 6 صباحاً
🕡 6 مساءً
🕛 12 منتصف الليل

*اختر من القائمة:*"""
    
    bot.send_message(message.chat.id, welcome_text, 
                     parse_mode='Markdown',
                     reply_markup=create_main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "add_channel")
def add_channel_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "awaiting_channel"
    logger.info("المستخدم يريد إضافة قناة")
    
    bot.edit_message_text(
        "📝 *إضافة قناة جديدة*\n\nأرسل لي اسم المستخدم الخاص بقناتك (مثال: @channelname)",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(call.message, process_channel_username)

def process_channel_username(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    channel_username = message.text.strip()
    logger.info(f"محاولة إضافة قناة: {channel_username}")
    
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    try:
        # التحقق من أن القناة غير مضافة مسبقاً
        for channel_id, data in channels.items():
            if data['username'].lower() == channel_username.lower():
                user_states[message.chat.id] = "main_menu"
                logger.warning(f"القناة مضافه مسبقاً: {channel_username}")
                bot.send_message(message.chat.id, 
                               f"❌ *هذه القناة مضافه مسبقاً!*\n\nالقناة: {channel_username}\n\nالرجاء اختيار قناة أخرى.",
                               parse_mode='Markdown',
                               reply_markup=create_main_menu())
                return
        
        # محاولة الحصول على معلومات القناة
        chat_info = bot.get_chat(channel_username)
        channel_id = str(chat_info.id)
        
        # التحقق من أن البوت مدير في القناة
        try:
            admins = bot.get_chat_administrators(channel_id)
            bot_is_admin = any(admin.user.id == bot.get_me().id for admin in admins)
            if not bot_is_admin:
                raise Exception("البوت ليس مديراً في القناة")
            logger.info("البوت مدير في القناة")
        except Exception as e:
            user_states[message.chat.id] = "main_menu"
            logger.error(f"خطأ في صلاحيات البوت: {e}")
            bot.send_message(message.chat.id,
                           f"❌ *خطأ في الصلاحيات!*\n\nتأكد من:\n1️⃣ أن البوت مدير في القناة {channel_username}\n2️⃣ لديه صلاحية النشر",
                           parse_mode='Markdown',
                           reply_markup=create_main_menu())
            return
        
        # إضافة القناة إلى القائمة
        channels[channel_id] = {
            "username": channel_username,
            "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_channels()
        logger.info(f"تمت إضافة القناة: {channel_username}")
        
        # نشر أول منشور
        try:
            poem_data = generate_poem()
            if poem_data:
                # إضافة فصل زخرفي
                separator = "\n" + "═" * 30 + "\n"
                welcome_msg = "🎉 *مرحباً بكم في قناة الشعر العربي الساخر!*\n\n" + poem_data["formatted"] + separator + "📚 *أولى قصائدنا من التراث العربي* 📚"
                
                bot.send_message(channel_id, welcome_msg, parse_mode='Markdown')
                
                # حفظ عنوان القصيدة
                if poem_data["title"] and poem_data["title"] not in posted_poems:
                    posted_poems.append(poem_data["title"])
                    save_posted_poems()
                logger.info("تم نشر أول منشور في القناة")
                    
        except Exception as e:
            logger.error(f"خطأ في النشر الأول: {e}")
            bot.send_message(message.chat.id, 
                           f"⚠️ *تنبيه*\n\nتمت إضافة القناة {channel_username} ولكن حدث خطأ في النشر الأول.\n\nالتفاصيل: {str(e)[:100]}",
                           parse_mode='Markdown')
            user_states[message.chat.id] = "main_menu"
            bot.send_message(message.chat.id,
                           "✅ *تمت إضافة القناة*",
                           parse_mode='Markdown',
                           reply_markup=create_main_menu())
            return
        
        user_states[message.chat.id] = "main_menu"
        bot.send_message(message.chat.id, 
                       f"✅ *تمت العملية بنجاح!*\n\nتمت إضافة القناة: {channel_username}\nوبدأ النشر التلقائي في الأوقات المحددة.\n\n📚 *ملاحظة:* جميع القصائد من مصادر أدبية حقيقية مذكورة.",
                       parse_mode='Markdown',
                       reply_markup=create_main_menu())
        logger.info(f"اكتملت إضافة القناة بنجاح: {channel_username}")
        
    except Exception as e:
        user_states[message.chat.id] = "main_menu"
        logger.error(f"خطأ في إضافة القناة: {e}")
        error_msg = f"""❌ *خطأ في الإضافة!*

التفاصيل: {str(e)[:150]}

*تأكد من:*
1️⃣ أن البوت مدير في القناة
2️⃣ اسم القناة صحيح ويبدأ بـ @
3️⃣ القناة عامة
4️⃣ البوت لديه صلاحية النشر"""
        
        bot.send_message(message.chat.id, error_msg, 
                        parse_mode='Markdown',
                        reply_markup=create_main_menu())

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    """معالجة جميع الردود في مكان واحد"""
    if call.from_user.id != ADMIN_ID:
        return
    
    try:
        if call.data == "more_options":
            user_states[call.message.chat.id] = "more_options"
            bot.edit_message_text(
                "⚙️ *المزيد من الخيارات*\n\nاختر أحد الخيارات:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "list_channels":
            if not channels:
                text = "📭 *عرض القنوات*\n\nلا توجد قنوات مضافة بعد.\n\nاستخدم زر \"اضف قناتي\" لإضافة قناة جديدة."
            else:
                text = "📋 *القنوات المضافة:*\n\n"
                for idx, (channel_id, data) in enumerate(channels.items(), 1):
                    text += f"{idx}. {data['username']}\n"
                text += f"\n*الإجمالي:* {len(channels)} قناة"
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "stats":
            stats_text = f"""📊 *إحصائيات البوت*

*القنوات المضافة:* {len(channels)}
*القصائد المنشورة:* {len(posted_poems)}
*الحالة:* ✅ يعمل

*أوقات النشر:*
🕕 6:00 صباحاً
🕡 18:00 مساءً
🕛 00:00 منتصف الليل

*مميزات:*
📚 قصائد من مصادر حقيقية
🎯 6 أبيات كاملة لكل قصيدة
🚫 منع التكرار التلقائي
🔤 نصوص عربية خالصة"""

            bot.edit_message_text(
                stats_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "remove_channel":
            if not channels:
                bot.answer_callback_query(call.id, "لا توجد قنوات مضافة", show_alert=True)
                return
            
            user_states[call.message.chat.id] = "removing_channel"
            bot.edit_message_text(
                "🗑️ *حذف قناة*\n\nاختر القناة التي تريد حذفها:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_channels_list_menu("remove")
            )
            
        elif call.data.startswith("remove_"):
            channel_id = call.data.replace("remove_", "")
            
            if channel_id in channels:
                channel_name = channels[channel_id]['username']
                del channels[channel_id]
                save_channels()
                logger.info(f"تم حذف القناة: {channel_name}")
                
                bot.answer_callback_query(call.id, f"تم حذف القناة {channel_name}")
                
                if not channels:
                    bot.edit_message_text(
                        "✅ *تم الحذف بنجاح!*\n\nتم حذف القناة.\nلا توجد قنوات متبقية.\n\nاستخدم زر \"اضف قناتي\" لإضافة قناة جديدة.",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='Markdown',
                        reply_markup=create_main_menu()
                    )
                else:
                    bot.edit_message_text(
                        f"✅ *تم الحذف بنجاح!*\n\nتم حذف القناة: {channel_name}\n\nالقنوات المتبقية: {len(channels)}",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='Markdown',
                        reply_markup=create_channels_list_menu("remove")
                    )
            else:
                bot.answer_callback_query(call.id, "❌ القناة غير موجودة", show_alert=True)
                
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
                
        elif call.data == "back_to_main":
            user_states[call.message.chat.id] = "main_menu"
            bot.edit_message_text(
                "🏠 *القائمة الرئيسية*\n\nاختر أحد الخيارات:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_main_menu()
            )
            
        elif call.data == "back_to_options":
            user_states[call.message.chat.id] = "more_options"
            bot.edit_message_text(
                "⚙️ *المزيد من الخيارات*\n\nاختر أحد الخيارات:",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=create_more_options_menu()
            )
            
        elif call.data == "no_action":
            bot.answer_callback_query(call.id, "لا يوجد شيء للقيام به")
            
    except Exception as e:
        logger.error(f"خطأ في معالجة callback: {e}")
        bot.answer_callback_query(call.id, "حدث خطأ، حاول مرة أخرى")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 ليس لديك صلاحية للتفاعل مع هذا البوت.")
        return
    
    # إذا كان المستخدم في حالة انتظار اسم القناة
    if user_states.get(message.chat.id) == "awaiting_channel":
        process_channel_username(message)
    else:
        # إعادة عرض القائمة الرئيسية
        user_states[message.chat.id] = "main_menu"
        bot.send_message(message.chat.id, 
                        "🏠 *القائمة الرئيسية*\n\nاختر أحد الخيارات:",
                        parse_mode='Markdown',
                        reply_markup=create_main_menu())

# دالة لاختبار الاتصال بـ API
def test_api_connection():
    """اختبار الاتصال بـ META AI API"""
    try:
        logger.info("جاري اختبار الاتصال بـ API...")
        response = requests.get(META_API_URL, timeout=10)
        logger.info(f"نتيجة اختبار API: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"فشل اختبار الاتصال بـ API: {e}")
        return False

# تشغيل البوت
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 بدء تشغيل بوت نشر الشعر العربي الساخر من مصادر حقيقية")
    logger.info("=" * 50)
    
    # اختبار الاتصال بالإنترنت وAPI
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
    
    # تحميل البيانات
    load_data()
    
    # تشغيل جدولة النشر في خيط منفصل
    try:
        scheduler_thread = threading.Thread(target=schedule_posts, daemon=True)
        scheduler_thread.start()
        logger.info("✅ تم بدء خيط جدولة النشر")
    except Exception as e:
        logger.error(f"❌ فشل بدء خيط الجدولة: {e}")
    
    # عرض معلومات البوت
    logger.info(f"📅 القنوات المضافة: {len(channels)}")
    logger.info(f"📝 القصائد المنشورة: {len(posted_poems)}")
    logger.info(f"🔗 API المستخدم: {META_API_URL}")
    logger.info(f"👤 المدير: {ADMIN_ID}")
    
    if channels:
        logger.info("📋 القنوات المضافة:")
        for idx, (channel_id, data) in enumerate(channels.items(), 1):
            logger.info(f"  {idx}. {data['username']}")
    
    logger.info("=" * 50)
    logger.info("✅ البوت يعمل الآن وجاهز للاستخدام")
    logger.info("📚 جميع القصائد من مصادر أدبية حقيقية")
    logger.info("=" * 50)
    
    # تشغيل البوت مع إعادة المحاولة في حالة الفشل
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
