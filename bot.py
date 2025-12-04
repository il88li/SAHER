import json
import os
import threading
import time
import schedule
import re
from datetime import datetime
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

# إعدادات API
DEEPSEEK_API_URL = "https://vetrex.x10.mx/api/deepseek_chat.php"
TELEGRAM_TOKEN = "8543864168:AAHLdQAGzYLRFtf_hHv8B7E6mpgMRwrU1W4"
ADMIN_ID = 6689435577

# تهيئة البوت
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ملفات التخزين
CHANNELS_FILE = "channels.json"
POSTED_POEMS_FILE = "posted_poems.txt"

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
    except:
        channels = {}
    
    try:
        if os.path.exists(POSTED_POEMS_FILE):
            with open(POSTED_POEMS_FILE, 'r', encoding='utf-8') as f:
                posted_poems = [line.strip() for line in f.readlines()]
    except:
        posted_poems = []

# حفظ البيانات
def save_channels():
    with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

def save_posted_poems():
    with open(POSTED_POEMS_FILE, 'a', encoding='utf-8') as f:
        for poem in posted_poems:
            f.write(poem + '\n')

# وظائف تنظيف النصوص من الرموز البرمجية
def clean_text(text):
    """تنظيف النص من الرموز البرمجية والتنسيق غير المرغوب"""
    if not text:
        return ""
    
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
    
    # تنظيف المسافات الزائدة
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text

def format_poem_for_telegram(poem_text):
    """تنسيق القصيدة للعرض في تلجرام مع الخط العريض"""
    if not poem_text:
        return ""
    
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

def extract_poem_title(poem_text):
    """استخراج عنوان القصيدة من النص"""
    lines = poem_text.split('\n')
    for line in lines:
        line = clean_text(line).strip()
        if line.startswith("اسم القصيدة") or line.startswith("القصيدة") or "اسم القصيدة:" in line:
            # استخراج العنوان بعد النقطتين
            parts = line.split(":")
            if len(parts) > 1:
                title = parts[1].strip()
                # تنظيف العنوان من أي رموز إضافية
                title = clean_text(title)
                return title
    return None

# توليد القصيدة من DeepSeek API
def generate_poem():
    prompt = """انت شخصية اجتماعية ساردة للشعر الساخر العربي الاصيل من الكتب العربية ، اسرد لي قصيدة شعرية مضحكة ، بدون شرحها او اي تفاصيل اخرى، قدم اول بيتين فقط من القصيدة الكاملة ، ثم اشرح من هو الشاعر وفي اي زمن وفي من قال القصيدة، لاتتعلق بالنساء ، بها مواقف اجتماعية محرجة، تنمر، عنصرية، ابدء باسم القصيدة، لا تشرح او توضح او تسئل اي شيء"""
    
    try:
        # استخدام طريقة POST كما في المثال
        response = requests.post(
            DEEPSEEK_API_URL,
            json={"text": prompt},
            timeout=30
        )
        response.raise_for_status()
        
        # محاولة تحليل الرد كـ JSON أولاً
        try:
            result = response.json()
            if 'response' in result:
                raw_text = result['response']
            elif 'text' in result:
                raw_text = result['text']
            elif 'message' in result:
                raw_text = result['message']
            else:
                # إذا لم يكن هناك حقل واضح، نعيد النص كاملاً
                raw_text = response.text
        except:
            # إذا فشل تحليل JSON، نعيد النص مباشرة
            raw_text = response.text
        
        # تنظيف النص وتنسيقه
        cleaned_text = clean_text(raw_text)
        formatted_text = format_poem_for_telegram(cleaned_text)
        
        # استخراج العنوان
        title = extract_poem_title(cleaned_text)
        
        return {
            "raw": cleaned_text,
            "formatted": formatted_text,
            "title": title
        }
            
    except Exception as e:
        print(f"Error calling DeepSeek API: {e}")
        # رد افتراضي في حالة الخطأ
        default_poems = [
            {
                "raw": "اسم القصيدة: نكد الجيران\n\nيا جاري اللي فوق سطحنا\nيلقي الزبالة في صحننا\nوالشاعر هو أبو القاسم الشابي\nمن تونس في القرن العشرين",
                "formatted": "*اسم القصيدة: نكد الجيران*\n\n*يا جاري اللي فوق سطحنا*\n*يلقي الزبالة في صحننا*\n*والشاعر هو أبو القاسم الشابي*\n*من تونس في القرن العشرين*",
                "title": "نكد الجيران"
            },
            {
                "raw": "اسم القصيدة: شكوى الموظف\n\nمديري يطلب المستحيل\nويريد مني عمل البديل\nوالشاعر هو المتنبي\nمن العصر العباسي",
                "formatted": "*اسم القصيدة: شكوى الموظف*\n\n*مديري يطلب المستحيل*\n*ويريد مني عمل البديل*\n*والشاعر هو المتنبي*\n*من العصر العباسي*",
                "title": "شكوى الموظف"
            }
        ]
        import random
        return random.choice(default_poems)

# النشر في القناة
def post_to_channel(channel_id):
    if channel_id not in channels:
        return
    
    poem_data = generate_poem()
    if poem_data:
        try:
            # إرسال القصيدة المنسقة مع parse_mode='Markdown' للخط العريض
            bot.send_message(channel_id, poem_data["formatted"], parse_mode='Markdown')
            
            # حفظ عنوان القصيدة لمنع التكرار
            if poem_data["title"] and poem_data["title"] not in posted_poems:
                posted_poems.append(poem_data["title"])
                save_posted_poems()
                
        except Exception as e:
            print(f"Error posting to channel {channel_id}: {e}")
            # محاولة إرسال النص العادي إذا فشل التنسيق
            try:
                bot.send_message(channel_id, poem_data["raw"])
            except:
                pass

# جدولة النشر
def schedule_posts():
    schedule.every().day.at("06:00").do(run_scheduled_posts)
    schedule.every().day.at("18:00").do(run_scheduled_posts)
    schedule.every().day.at("00:00").do(run_scheduled_posts)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def run_scheduled_posts():
    for channel_id in channels.keys():
        post_to_channel(channel_id)

# إنشاء واجهات Inline Keyboard
def create_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)  # ترتيب عمودي
    keyboard.add(
        InlineKeyboardButton("📢 اضف قناتي", callback_data="add_channel"),
        InlineKeyboardButton("⚙️ المزيد من الخيارات", callback_data="more_options")
    )
    return keyboard

def create_more_options_menu():
    keyboard = InlineKeyboardMarkup(row_width=1)  # ترتيب عمودي
    keyboard.add(
        InlineKeyboardButton("📋 عرض القنوات", callback_data="list_channels"),
        InlineKeyboardButton("🗑️ حذف قناة", callback_data="remove_channel"),
        InlineKeyboardButton("🧪 اختبار نشر", callback_data="test_post"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="stats"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    return keyboard

def create_channels_list_menu(action="remove"):
    keyboard = InlineKeyboardMarkup(row_width=1)  # ترتيب عمودي
    
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
    
    welcome_text = """✨ *مرحباً! أنا بوت نشر الشعر الساخر العربي.*

سأنشر قصائد ساخرة في أوقات محددة يومياً:
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
    
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    try:
        # التحقق من أن القناة غير مضافة مسبقاً
        for channel_id, data in channels.items():
            if data['username'].lower() == channel_username.lower():
                user_states[message.chat.id] = "main_menu"
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
            bot.get_chat_administrators(channel_id)
        except:
            user_states[message.chat.id] = "main_menu"
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
        
        # نشر أول منشور
        try:
            poem_data = generate_poem()
            if poem_data:
                bot.send_message(channel_id, poem_data["formatted"], parse_mode='Markdown')
                
                # حفظ عنوان القصيدة
                if poem_data["title"] and poem_data["title"] not in posted_poems:
                    posted_poems.append(poem_data["title"])
                    save_posted_poems()
                    
        except Exception as e:
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
                       f"✅ *تمت العملية بنجاح!*\n\nتمت إضافة القناة: {channel_username}\nوبدأ النشر التلقائي في الأوقات المحددة.",
                       parse_mode='Markdown',
                       reply_markup=create_main_menu())
        
    except Exception as e:
        user_states[message.chat.id] = "main_menu"
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

@bot.callback_query_handler(func=lambda call: call.data == "more_options")
def more_options_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "more_options"
    
    bot.edit_message_text(
        "⚙️ *المزيد من الخيارات*\n\nاختر أحد الخيارات:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_more_options_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "list_channels")
def list_channels_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
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

@bot.callback_query_handler(func=lambda call: call.data == "stats")
def stats_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    stats_text = f"""📊 *إحصائيات البوت*

*القنوات المضافة:* {len(channels)}
*القصائد المنشورة:* {len(posted_poems)}
*الحالة:* ✅ يعمل

*أوقات النشر:*
🕕 6:00 صباحاً
🕡 18:00 مساءً
🕛 00:00 منتصف الليل"""

    bot.edit_message_text(
        stats_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_more_options_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "remove_channel")
def remove_channel_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_"))
def remove_channel_selected(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = call.data.replace("remove_", "")
    
    if channel_id in channels:
        channel_name = channels[channel_id]['username']
        del channels[channel_id]
        save_channels()
        
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

@bot.callback_query_handler(func=lambda call: call.data == "test_post")
def test_post_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    bot.answer_callback_query(call.id, "جاري إنشاء قصيدة اختبارية...")
    
    poem_data = generate_poem()
    if poem_data:
        test_message = f"""🧪 *اختبار النشر*

{poem_data["formatted"]}

───
*ملاحظة:* هذه نسخة اختبارية فقط
*العنوان:* {poem_data.get('title', 'غير معروف')}
*عدد الأحرف:* {len(poem_data['formatted'])}"""
        
        bot.edit_message_text(
            test_message,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=create_more_options_menu()
        )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "main_menu"
    
    bot.edit_message_text(
        "🏠 *القائمة الرئيسية*\n\nاختر أحد الخيارات:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_options")
def back_to_options_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "more_options"
    
    bot.edit_message_text(
        "⚙️ *المزيد من الخيارات*\n\nاختر أحد الخيارات:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=create_more_options_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "no_action")
def no_action_callback(call):
    bot.answer_callback_query(call.id, "لا يوجد شيء للقيام به")

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

# تشغيل البوت
if __name__ == "__main__":
    # تحميل البيانات
    load_data()
    
    # تشغيل جدولة النشر في خيط منفصل
    scheduler_thread = threading.Thread(target=schedule_posts, daemon=True)
    scheduler_thread.start()
    
    print("=" * 50)
    print("✅ البوت يعمل الآن...")
    print(f"📅 القنوات المضافة: {len(channels)}")
    print(f"📝 القصائد المنشورة: {len(posted_poems)}")
    print(f"🔗 API المستخدم: {DEEPSEEK_API_URL}")
    print
