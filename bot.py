import json
import os
import threading
import time
import schedule
from datetime import datetime
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

# إعدادات API
DEEPSEEK_API_URL = "https://vetrex.x10.mx/api/deepseek_chat.php"
TELEGRAM_TOKEN = "8543864168:AAGf-8hzlEdhtjggbX839sjczIUHV27qlfI"
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
                return result['response']
            elif 'text' in result:
                return result['text']
            else:
                # إذا لم يكن هناك حقل واضح، نعيد النص كاملاً
                return response.text
        except:
            # إذا فشل تحليل JSON، نعيد النص مباشرة
            return response.text
            
    except Exception as e:
        print(f"Error calling DeepSeek API: {e}")
        # رد افتراضي في حالة الخطأ
        default_poems = [
            "اسم القصيدة: نكد الجيران\n\nيا جاري اللي فوق سطحنا\nيلقي الزبالة في صحننا\nوالشاعر هو أبو القاسم الشابي\nمن تونس في القرن العشرين",
            "اسم القصيدة: شكوى الموظف\n\nمديري يطلب المستحيل\nويريد مني عمل البديل\nوالشاعر هو المتنبي\nمن العصر العباسي"
        ]
        import random
        return random.choice(default_poems)

# النشر في القناة
def post_to_channel(channel_id):
    if channel_id not in channels:
        return
    
    poem = generate_poem()
    if poem:
        try:
            bot.send_message(channel_id, poem)
            # استخراج اسم القصيدة من البداية
            lines = poem.split('\n')
            for line in lines:
                if "اسم القصيدة:" in line or "القصيدة:" in line:
                    poem_title = line.replace("اسم القصيدة:", "").replace("القصيدة:", "").strip()
                    if poem_title and poem_title not in posted_poems:
                        posted_poems.append(poem_title)
                        save_posted_poems()
                    break
        except Exception as e:
            print(f"Error posting to channel {channel_id}: {e}")

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
    keyboard = InlineKeyboardMarkup(row_width=2)
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
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )
    return keyboard

def create_channels_list_menu(action="remove"):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    if not channels:
        keyboard.add(InlineKeyboardButton("لا توجد قنوات", callback_data="no_action"))
    else:
        for channel_id, data in channels.items():
            keyboard.add(InlineKeyboardButton(
                f"📺 {data['username']}", 
                callback_data=f"{action}_{channel_id}"
            ))
    
    keyboard.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_to_options"))
    return keyboard

# أوامر البوت
@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "ليس لديك صلاحية للوصول إلى هذا البوت.")
        return
    
    user_states[message.chat.id] = "main_menu"
    
    welcome_text = """مرحباً! أنا بوت نشر الشعر الساخر العربي.
سأنشر قصائد ساخرة في أوقات محددة يومياً (6 صباحاً، 6 مساءً، 12 منتصف الليل)."""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "add_channel")
def add_channel_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "awaiting_channel"
    
    bot.edit_message_text(
        "أرسل لي اسم المستخدم الخاص بقناتك (مثال: @channelname)",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_channel_username)

def process_channel_username(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    channel_username = message.text.strip()
    
    if not channel_username.startswith('@'):
        channel_username = '@' + channel_username
    
    try:
        # محاولة الحصول على معلومات القناة
        chat_info = bot.get_chat(channel_username)
        channel_id = str(chat_info.id)
        
        # إضافة القناة إلى القائمة
        channels[channel_id] = {
            "username": channel_username,
            "added_date": datetime.now().isoformat()
        }
        save_channels()
        
        # نشر أول منشور
        try:
            poem = generate_poem()
            if poem:
                bot.send_message(channel_id, poem)
                # استخراج اسم القصيدة
                lines = poem.split('\n')
                for line in lines:
                    if "اسم القصيدة:" in line or "القصيدة:" in line:
                        poem_title = line.replace("اسم القصيدة:", "").replace("القصيدة:", "").strip()
                        if poem_title and poem_title not in posted_poems:
                            posted_poems.append(poem_title)
                            save_posted_poems()
                        break
        except Exception as e:
            bot.send_message(message.chat.id, 
                           f"تمت إضافة القناة ولكن حدث خطأ في النشر الأول: {str(e)[:100]}...")
            user_states[message.chat.id] = "main_menu"
            bot.send_message(message.chat.id, 
                           "تمت إضافة القناة ولكن هناك مشكلة في النشر. تأكد أن البوت مدير في القناة.",
                           reply_markup=create_main_menu())
            return
        
        user_states[message.chat.id] = "main_menu"
        bot.send_message(message.chat.id, 
                       f"✅ تمت إضافة القناة {channel_username} بنجاح وبدأ النشر التلقائي!",
                       reply_markup=create_main_menu())
        
    except Exception as e:
        user_states[message.chat.id] = "main_menu"
        error_msg = f"❌ خطأ: {str(e)[:100]}...\n\nتأكد من:\n1️⃣ أن البوت مدير في القناة\n2️⃣ اسم القناة صحيح (يبدأ بـ @)\n3️⃣ القناة عامة"
        bot.send_message(message.chat.id, error_msg, reply_markup=create_main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "more_options")
def more_options_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "more_options"
    
    bot.edit_message_text(
        "⚙️ **المزيد من الخيارات**\n\nاختر أحد الخيارات:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=create_more_options_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "list_channels")
def list_channels_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    if not channels:
        text = "📭 **عرض القنوات**\n\nلا توجد قنوات مضافة بعد."
    else:
        text = "📋 **القنوات المضافة:**\n\n"
        for idx, (channel_id, data) in enumerate(channels.items(), 1):
            text += f"{idx}. {data['username']}\n"
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=create_more_options_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "remove_channel")
def remove_channel_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    if not channels:
        bot.answer_callback_query(call.id, "لا توجد قنوات مضافة")
        return
    
    user_states[call.message.chat.id] = "removing_channel"
    
    bot.edit_message_text(
        "🗑️ **حذف قناة**\n\nاختر القناة التي تريد حذفها:",
        call.message.chat.id,
        call.message.message_id,
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
                "✅ **تم الحذف**\n\nتم حذف القناة بنجاح.\nلا توجد قنوات متبقية.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_more_options_menu()
            )
        else:
            bot.edit_message_text(
                f"✅ **تم الحذف**\n\nتم حذف القناة {channel_name} بنجاح.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_channels_list_menu("remove")
            )
    else:
        bot.answer_callback_query(call.id, "القناة غير موجودة")

@bot.callback_query_handler(func=lambda call: call.data == "test_post")
def test_post_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    bot.answer_callback_query(call.id, "جاري إنشاء قصيدة اختبارية...")
    
    poem = generate_poem()
    if poem:
        # قص النص إذا كان طويلاً جداً
        if len(poem) > 4000:
            poem = poem[:4000] + "..."
        
        bot.edit_message_text(
            f"🧪 **اختبار النشر**\n\n{poem}\n\n───\n*هذه نسخة اختبارية فقط*",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=create_more_options_menu()
        )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "main_menu"
    
    bot.edit_message_text(
        "🏠 **القائمة الرئيسية**\n\nاختر أحد الخيارات:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=create_main_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_options")
def back_to_options_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    user_states[call.message.chat.id] = "more_options"
    
    bot.edit_message_text(
        "⚙️ **المزيد من الخيارات**\n\nاختر أحد الخيارات:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=create_more_options_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "no_action")
def no_action_callback(call):
    bot.answer_callback_query(call.id, "لا يوجد شيء للقيام به")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "ليس لديك صلاحية للتفاعل مع هذا البوت.")
        return
    
    # إذا كان المستخدم في حالة انتظار اسم القناة
    if user_states.get(message.chat.id) == "awaiting_channel":
        process_channel_username(message)
    else:
        # إعادة عرض القائمة الرئيسية
        user_states[message.chat.id] = "main_menu"
        bot.send_message(message.chat.id, 
                        "🏠 **القائمة الرئيسية**\n\nاختر أحد الخيارات:",
                        reply_markup=create_main_menu())

# تشغيل البوت
if __name__ == "__main__":
    # تحميل البيانات
    load_data()
    
    # تشغيل جدولة النشر في خيط منفصل
    scheduler_thread = threading.Thread(target=schedule_posts, daemon=True)
    scheduler_thread.start()
    
    print("✅ البوت يعمل الآن...")
    print(f"📅 القنوات المضافة: {len(channels)}")
    print(f"📝 القصائد المنشورة: {len(posted_poems)}")
    print(f"🔗 API المستخدم: {DEEPSEEK_API_URL}")
    
    # تشغيل البوت
    bot.polling(none_stop=True)
