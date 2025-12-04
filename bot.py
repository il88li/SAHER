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
GEMINI_API_KEY = "AIzaSyCc0OcyQZ8-0c3vQxhNzrvV2Qe_MbAAayQ"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
TELEGRAM_TOKEN = "8543864168:AAG7IGqJ0HAs3PZnxgw97fUgUrWygR3uNRY"
ADMIN_ID = 6689435577

# تهيئة البوت
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ملفات التخزين
CHANNELS_FILE = "channels.json"
POSTED_POEMS_FILE = "posted_poems.txt"

# قوائم التخزين
channels = {}
posted_poems = []

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

# توليد القصيدة من Gemini
def generate_poem():
    prompt = """انت شخصية اجتماعية ساردة للشعر الساخر العربي الاصيل من الكتب العربية ، اسرد لي قصيدة شعرية مضحكة ، بدون شرحها او اي تفاصيل اخرى، قدم اول بيتين فقط من القصيدة الكاملة ، ثم اشرح من هو الشاعر وفي اي زمن وفي من قال القصيدة، لاتتعلق بالنساء ، بها مواقف اجتماعية محرجة، تنمر، عنصرية، ابدء باسم القصيدة، لا تشرح او توضح او تسئل اي شيء"""
    
    headers = {
        'Content-Type': 'application/json',
        'X-goog-api-key': GEMINI_API_KEY
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
        response = requests.post(GEMINI_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if 'candidates' in result and len(result['candidates']) > 0:
            text = result['candidates'][0]['content']['parts'][0]['text']
            return text
        else:
            return "عذراً، لم أتمكن من توليد قصيدة في هذا الوقت."
            
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "عذراً، حدث خطأ في توليد المحتوى."

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
            if lines and lines[0].startswith("اسم القصيدة:"):
                poem_title = lines[0].replace("اسم القصيدة:", "").strip()
                if poem_title and poem_title not in posted_poems:
                    posted_poems.append(poem_title)
                    save_posted_poems()
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

# أوامر البوت
@bot.message_handler(commands=['start'])
def start_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "ليس لديك صلاحية للوصول إلى هذا البوت.")
        return
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("اضف قناتي", callback_data="add_channel"))
    
    welcome_text = """مرحباً! أنا بوت نشر الشعر الساخر العربي.
سأنشر قصائد ساخرة في أوقات محددة يومياً (6 صباحاً، 6 مساءً، 12 منتصف الليل)."""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "add_channel")
def add_channel_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    bot.send_message(call.message.chat.id, "أرسل لي اسم المستخدم الخاص بقناتك (مثال: @channelname)")
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
                if lines and lines[0].startswith("اسم القصيدة:"):
                    poem_title = lines[0].replace("اسم القصيدة:", "").strip()
                    if poem_title and poem_title not in posted_poems:
                        posted_poems.append(poem_title)
                        save_posted_poems()
        except Exception as e:
            bot.send_message(message.chat.id, f"تمت إضافة القناة ولكن حدث خطأ في النشر الأول: {e}")
            return
        
        bot.send_message(message.chat.id, f"تمت إضافة القناة {channel_username} بنجاح وبدأ النشر التلقائي!")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"خطأ: {e}\nتأكد من:\n1. أن البوت مدير في القناة\n2. اسم القناة صحيح")

@bot.message_handler(commands=['list_channels'])
def list_channels_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not channels:
        bot.send_message(message.chat.id, "لا توجد قنوات مضافة.")
        return
    
    text = "القنوات المضافة:\n\n"
    for idx, (channel_id, data) in enumerate(channels.items(), 1):
        text += f"{idx}. {data['username']}\n"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['remove_channel'])
def remove_channel_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not channels:
        bot.send_message(message.chat.id, "لا توجد قنوات مضافة.")
        return
    
    keyboard = InlineKeyboardMarkup()
    for channel_id, data in channels.items():
        keyboard.add(InlineKeyboardButton(data['username'], callback_data=f"remove_{channel_id}"))
    
    bot.send_message(message.chat.id, "اختر القناة التي تريد حذفها:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_"))
def remove_channel_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = call.data.replace("remove_", "")
    
    if channel_id in channels:
        channel_name = channels[channel_id]['username']
        del channels[channel_id]
        save_channels()
        bot.send_message(call.message.chat.id, f"تم حذف القناة {channel_name}")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "القناة غير موجودة")

@bot.message_handler(commands=['test_post'])
def test_post_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    bot.send_message(message.chat.id, "جاري إنشاء قصيدة اختبارية...")
    poem = generate_poem()
    if poem:
        bot.send_message(message.chat.id, poem)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "ليس لديك صلاحية للتفاعل مع هذا البوت.")
        return
    
    bot.send_message(message.chat.id, "استخدم /start للبدء")

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
    
    # تشغيل البوت
    bot.polling(none_stop=True)
