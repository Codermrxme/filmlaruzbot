import os
import json
import pandas as pd
from datetime import datetime, timedelta
import time
import asyncio
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackContext,
    CallbackQueryHandler
)
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi

# 🔧 .env fayldan sozlamalarni yuklash
load_dotenv()

# Bot sozlamalari
TOKEN = os.getenv('TOKEN', '')  # @BotFather dan oling
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))  # Sizning Telegram ID
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  # Kanal ID (manfiy son)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '')  # Sizning username
MAIN_CHANNEL = os.getenv('MAIN_CHANNEL', '')  # Asosiy kanal username
MONGODB_URI = os.getenv('MONGODB_URI', '')  # MongoDB connection string
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'kino_bot')  # MongoDB database nomi
PORT = int(os.getenv('PORT', 10000))  # Render uchun port

# Xatolikni tekshirish
if not TOKEN:
    raise ValueError("TOKEN .env faylda aniqlanmagan yoki noto'g'ri")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID .env faylda aniqlanmagan yoki noto'g'ri")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID .env faylda aniqlanmagan yoki noto'g'ri")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI .env faylda aniqlanmagan")
if not ADMIN_USERNAME:
    print("Diqqat: ADMIN_USERNAME .env faylda aniqlanmagan")
if not MAIN_CHANNEL:
    print("Diqqat: MAIN_CHANNEL .env faylda aniqlanmagan")

print(f"🔧 MongoDB Database nomi: {MONGO_DB_NAME}")
print(f"🔧 Port: {PORT}")

# 📂 MongoDB ulanish
try:
    client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
    
    # Database ni tekshirish
    db_names = client.list_database_names()
    print(f"📊 Mavjud databaselar: {db_names}")
    
    # Database ni tanlash yoki yaratish
    db = client[MONGO_DB_NAME]
    
    # Kolleksiyalar
    admins_collection = db['admins']
    codes_collection = db['codes']
    users_collection = db['users']
    channels_collection = db['channels']
    subscriptions_collection = db['subscriptions']
    
    # Asosiy adminni qo'shish
    if not admins_collection.find_one({"id": ADMIN_ID}):
        admins_collection.insert_one({
            "id": ADMIN_ID,
            "username": ADMIN_USERNAME,
            "added_at": datetime.now(),
            "is_main": True
        })
        print("✅ Asosiy admin qo'shildi")
    
    # Kolleksiyalarni tekshirish
    collections = db.list_collection_names()
    print(f"📁 Mavjud kolleksiyalar: {collections}")
    
    print(f"✅ MongoDB ga muvaffaqiyatli ulandi - Database: {MONGO_DB_NAME}")
except Exception as e:
    print(f"❌ MongoDB ga ulanishda xato: {e}")
    raise

# Bot ishga tushgan vaqt
BOT_START_TIME = datetime.now()

# Flask server yaratish (Render uchun)
app = Flask(__name__)

@app.route('/')
def home():
    return {
        "status": "online",
        "bot": "Kino Bot",
        "start_time": BOT_START_TIME.strftime('%Y-%m-%d %H:%M:%S'),
        "uptime": str(datetime.now() - BOT_START_TIME)
    }

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def run_flask():
    """Flask serverni ishga tushirish"""
    app.run(host='0.0.0.0', port=PORT, debug=False)

# 🛠️ Yordamchi funksiyalar
def is_admin(user_id):
    return admins_collection.find_one({"id": user_id}) is not None

def channel_link(post_id):
    return f"https://t.me/c/{str(CHANNEL_ID)[4:]}/{post_id}"

def track_user(user):
    user_data = {
        "id": user.id,
        "name": user.full_name,
        "username": user.username,
        "phone": None,
        "start_time": datetime.now(),
        "last_activity": datetime.now()
    }
    
    existing_user = users_collection.find_one({"id": user.id})
    if existing_user:
        users_collection.update_one(
            {"id": user.id},
            {"$set": {"last_activity": datetime.now()}}
        )
    else:
        users_collection.insert_one(user_data)

async def send_error_to_admin(context: CallbackContext, error_msg):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Botda xato yuz berdi:\n\n{error_msg}"
        )
    except Exception as e:
        print(f"Xatoni adminga yuborishda xato: {e}")

async def forward_to_admin(update: Update, context: CallbackContext, user, message):
    try:
        await message.forward(chat_id=ADMIN_ID)
    except Exception as e:
        error_msg = f"Adminga yuborishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

def admin_menu():
    buttons = [
        ["🎬 Kino qo'shish", "📋 Kodlar ro'yxati"],
        ["🗑️ Kod o'chirish", "📢 Majburiy kanallar"],
        ["🤖 Bot funksiyalari", "✏️ Kodlarni tahrirlash"],
        ["👥 Admin tahrirlash", "👤 Foydalanuvchilar"],
        ["📊 Statistika", "👤 Foydalanuvchi menyusi"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def user_menu():
    buttons = [
        ["📞 Admin bilan bog'lanish", "📢 Bizning kanal"],
        ["ℹ️ Yordam"]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def check_subscription(user_id, context: CallbackContext):
    try:
        channels = list(channels_collection.find())
        if not channels:
            return True
        
        subscription = subscriptions_collection.find_one({"user_id": user_id})
        if subscription and subscription.get('subscribed', False):
            return True
        
        not_subscribed = []
        for channel in channels:
            try:
                member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
                if member.status in ['left', 'kicked']:
                    not_subscribed.append(channel)
            except Exception as e:
                print(f"Obunani tekshirishda xato: {e}")
                not_subscribed.append(channel)
        
        if not not_subscribed:
            subscriptions_collection.update_one(
                {"user_id": user_id},
                {"$set": {"subscribed": True, "checked_at": datetime.now()}},
                upsert=True
            )
            return True
        
        return not_subscribed
    except Exception as e:
        error_msg = f"Obunani tekshirishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)
        return True

async def export_users(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        users = list(users_collection.find())
        if not users:
            await update.message.reply_text("❌ Foydalanuvchilar mavjud emas!")
            return

        # MongoDB _id maydonini olib tashlash
        for user in users:
            user.pop('_id', None)
            if 'start_time' in user and isinstance(user['start_time'], datetime):
                user['start_time'] = user['start_time'].strftime('%Y-%m-%d %H:%M:%S')
            if 'last_activity' in user and isinstance(user['last_activity'], datetime):
                user['last_activity'] = user['last_activity'].strftime('%Y-%m-%d %H:%M:%S')
        
        df = pd.DataFrame(users)
        excel_file = "users.xlsx"
        df.to_excel(excel_file, index=False)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(excel_file, 'rb'),
            caption="📊 Foydalanuvchilar ro'yxati"
        )
        
        # Vaqtinchalik faylni o'chirish
        os.remove(excel_file)
    except Exception as e:
        error_msg = f"Foydalanuvchilarni eksport qilishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Foydalanuvchilar ro'yxatini yuborishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def show_statistics(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        # Foydalanuvchilar soni
        total_users = users_collection.count_documents({})
        
        # Faol foydalanuvchilar (oxirgi 7 kun ichida faol bo'lganlar)
        seven_days_ago = datetime.now() - timedelta(days=7)
        active_users = users_collection.count_documents({
            "last_activity": {"$gte": seven_days_ago}
        })
        
        # Bugungi yangi foydalanuvchilar
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        new_users_today = users_collection.count_documents({
            "start_time": {"$gte": today}
        })
        
        # Kodlar soni
        total_codes = codes_collection.count_documents({})
        
        # Kanallar soni
        total_channels = channels_collection.count_documents({})
        
        # Bot ishlash vaqti
        uptime = datetime.now() - BOT_START_TIME
        uptime_days = uptime.days
        uptime_hours = uptime.seconds // 3600
        uptime_minutes = (uptime.seconds % 3600) // 60
        
        # Toshkent vaqti
        tashkent_time = datetime.utcnow() + timedelta(hours=5)
        
        # Statistika xabari
        stats_message = (
            "📊 <b>Bot Statistikasi</b>\n\n"
            f"👥 <b>Jami foydalanuvchilar:</b> {total_users}\n"
            f"🟢 <b>Faol foydalanuvchilar (7 kun):</b> {active_users}\n"
            f"🆕 <b>Bugungi yangi foydalanuvchilar:</b> {new_users_today}\n"
            f"🔑 <b>Jami kodlar:</b> {total_codes}\n"
            f"📢 <b>Majburiy kanallar:</b> {total_channels}\n\n"
            f"⏰ <b>Bot ishlash vaqti:</b>\n"
            f"   {uptime_days} kun, {uptime_hours} soat, {uptime_minutes} daqiqa\n"
            f"🕒 <b>Toshkent vaqti:</b>\n"
            f"   {tashkent_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📈 <b>Faollik darajasi:</b> {round((active_users / total_users * 100) if total_users > 0 else 0, 1)}%\n"
            f"🚀 <b>Bot ishga tushgan vaqti:</b>\n"
            f"   {BOT_START_TIME.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await update.message.reply_text(stats_message, parse_mode='HTML')
        
    except Exception as e:
        error_msg = f"Statistika ko'rsatishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Statistika ko'rsatishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def add_admin(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if not context.args:
            await update.message.reply_text("❌ Admin IDsi kiritilmadi!\nFoydalanish: /addAdmin [USER_ID]")
            return
            
        try:
            admin_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri format! Admin ID raqam bo'lishi kerak.")
            return
        
        if admins_collection.find_one({"id": admin_id}):
            await update.message.reply_text("❌ Bu admin allaqachon mavjud!")
            return
        
        try:
            user = await context.bot.get_chat(admin_id)
            new_admin = {
                'id': admin_id,
                'username': user.username if user.username else 'nomalum',
                'added_at': datetime.now(),
                'added_by': update.effective_user.id
            }
            admins_collection.insert_one(new_admin)
            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (@{user.username if user.username else 'nomalum'})")
        except Exception as e:
            print(f"Foydalanuvchi ma'lumotlarini olishda xato: {e}")
            new_admin = {
                'id': admin_id,
                'username': 'nomalum',
                'added_at': datetime.now(),
                'added_by': update.effective_user.id
            }
            admins_collection.insert_one(new_admin)
            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (username noma'lum)")
    except Exception as e:
        error_msg = f"Admin qo'shishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Admin qo'shishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def remove_admin(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if not context.args:
            await update.message.reply_text("❌ Admin IDsi kiritilmadi!\nFoydalanish: /removeAdmin [USER_ID]")
            return
            
        try:
            admin_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri format! Admin ID raqam bo'lishi kerak.")
            return
        
        if admin_id == ADMIN_ID:
            await update.message.reply_text("❌ Asosiy adminni o'chirib bo'lmaydi!")
            return
            
        result = admins_collection.delete_one({"id": admin_id})
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Admin o'chirildi: {admin_id}")
        else:
            await update.message.reply_text("❌ Bunday admin topilmadi!")
    except Exception as e:
        error_msg = f"Admin o'chirishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Admin o'chirishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def add_code(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Noto'g'ri format!\nFoydalanish: /kod [KOD] [POST_ID]")
            return
            
        code = context.args[0]
        try:
            post_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri format! POST_ID raqam bo'lishi kerak.")
            return
        
        if codes_collection.find_one({"code": {"$regex": f"^{code}$", "$options": "i"}}):
            await update.message.reply_text("❌ Bu kod allaqachon mavjud!")
            return
        
        new_code = {
            "code": code,
            "post_id": post_id,
            "added_at": datetime.now(),
            "added_by": update.effective_user.id
        }
        codes_collection.insert_one(new_code)
        await update.message.reply_text(f"✅ Kod qo'shildi: {code} ➡️ {post_id}")
    except Exception as e:
        error_msg = f"Kod qo'shishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kod qo'shishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def edit_code(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Noto'g'ri format!\nFoydalanish: /tahrirlash [KOD] [YANGI_POST_ID]")
            return
            
        code = context.args[0]
        try:
            new_post_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri format! POST_ID raqam bo'lishi kerak.")
            return
        
        result = codes_collection.update_one(
            {"code": {"$regex": f"^{code}$", "$options": "i"}},
            {"$set": {"post_id": new_post_id, "updated_at": datetime.now()}}
        )
        
        if result.modified_count > 0:
            await update.message.reply_text(f"✅ Kod tahrirlandi: {code} ➡️ {new_post_id}")
        else:
            await update.message.reply_text("❌ Bunday kod topilmadi!")
    except Exception as e:
        error_msg = f"Kodni tahrirlashda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kodni tahrirlashda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def delete_code(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if not context.args:
            await update.message.reply_text("❌ Kod kiritilmadi!\nFoydalanish: /ochirish [KOD]")
            return
            
        code = context.args[0]
        result = codes_collection.delete_one({"code": {"$regex": f"^{code}$", "$options": "i"}})
        
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Kod o'chirildi: {code}")
        else:
            await update.message.reply_text("❌ Bunday kod topilmadi!")
    except Exception as e:
        error_msg = f"Kodni o'chirishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kodni o'chirishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def list_codes(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        codes = list(codes_collection.find())
        if not codes:
            await update.message.reply_text("❌ Kodlar mavjud emas!")
            return

        message = "📋 Kodlar ro'yxati:\n\n"
        for code in codes:
            message += f"🔑 {code['code']} ➡️ {channel_link(code['post_id'])}\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        error_msg = f"Kodlar ro'yxatini ko'rsatishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kodlar ro'yxatini ko'rsatishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def add_channel(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Noto'g'ri format!\nFoydalanish: /kanalqoshish [KANAL_ID] [KANAL_NOMI]")
            return
            
        try:
            channel_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri format! KANAL_ID raqam bo'lishi kerak.")
            return
            
        channel_name = ' '.join(context.args[1:])
        
        try:
            channel = await context.bot.get_chat(channel_id)
            username = channel.username if channel.username else "noma'lum"
        except Exception as e:
            print(f"Kanal ma'lumotlarini olishda xato: {e}")
            username = "noma'lum"
        
        if channels_collection.find_one({"id": channel_id}):
            await update.message.reply_text("❌ Bu kanal allaqachon mavjud!")
            return
        
        new_channel = {
            'id': channel_id,
            'name': channel_name,
            'username': username,
            'added_at': datetime.now(),
            'added_by': update.effective_user.id
        }
        channels_collection.insert_one(new_channel)
        await update.message.reply_text(f"✅ Kanal qo'shildi:\nID: {channel_id}\nNomi: {channel_name}\nUsername: @{username}")
    except Exception as e:
        error_msg = f"Kanal qo'shishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kanal qo'shishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def delete_channel(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        if not context.args:
            await update.message.reply_text("❌ Kanal IDsi kiritilmadi!\nFoydalanish: /kanalochirish [KANAL_ID]")
            return
            
        try:
            channel_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Noto'g'ri format! KANAL_ID raqam bo'lishi kerak.")
            return
            
        result = channels_collection.delete_one({"id": channel_id})
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Kanal o'chirildi: ID {channel_id}")
        else:
            await update.message.reply_text("❌ Bunday kanal topilmadi!")
    except Exception as e:
        error_msg = f"Kanal o'chirishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kanal o'chirishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def list_channels(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        channels = list(channels_collection.find())
        if not channels:
            await update.message.reply_text("❌ Majburiy kanallar mavjud emas!")
            return

        message = "📢 Majburiy kanallar:\n\n"
        for channel in channels:
            message += f"📌 {channel['name']}\nID: {channel['id']}\nUsername: @{channel['username']}\n\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        error_msg = f"Kanallar ro'yxatini ko'rsatishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kanallar ro'yxatini ko'rsatishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def manage_channels(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        channels = list(channels_collection.find())
        message = "📢 <b>Majburiy kanallar</b>\n\n"
        for channel in channels:
            message += f"📌 {channel['name']}\nID: {channel['id']}\nUsername: @{channel['username']}\n\n"
        
        buttons = [
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_channel")],
            [InlineKeyboardButton("🗑️ Kanal o'chirish", callback_data="delete_channel")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        error_msg = f"Kanallarni boshqarishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Kanallarni boshqarishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def manage_admins(update: Update, context: CallbackContext):
    try:
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Sizda bunday huquq yo'q!")
            return

        admins = list(admins_collection.find())
        message = "👥 <b>Adminlar boshqaruvi</b>\n\n"
        for admin in admins:
            message += f"🆔 {admin['id']} | 👤 @{admin.get('username', 'nomalum')}\n"
        
        buttons = [
            [InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin")],
            [InlineKeyboardButton("🗑️ Admin o'chirish", callback_data="delete_admin")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        error_msg = f"Adminlarni boshqarishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Adminlarni boshqarishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def handle_admin_actions(update: Update, context: CallbackContext):
    try:
        user_data = context.user_data
        message = update.message.text
        
        if 'action' in user_data:
            if user_data['action'] == 'add_admin':
                try:
                    admin_id = int(message)
                    
                    if admins_collection.find_one({"id": admin_id}):
                        await update.message.reply_text("❌ Bu admin allaqachon mavjud!")
                    else:
                        try:
                            user = await context.bot.get_chat(admin_id)
                            new_admin = {
                                'id': admin_id,
                                'username': user.username if user.username else 'nomalum',
                                'added_at': datetime.now(),
                                'added_by': update.effective_user.id
                            }
                            admins_collection.insert_one(new_admin)
                            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (@{user.username if user.username else 'nomalum'})")
                        except Exception as e:
                            print(f"Foydalanuvchi ma'lumotlarini olishda xato: {e}")
                            new_admin = {
                                'id': admin_id,
                                'username': 'nomalum',
                                'added_at': datetime.now(),
                                'added_by': update.effective_user.id
                            }
                            admins_collection.insert_one(new_admin)
                            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (username noma'lum)")
                    
                    del user_data['action']
                    await manage_admins(update, context)
                except ValueError:
                    await update.message.reply_text("❌ Noto'g'ri admin IDsi! Iltimos, raqam yuboring.")
            
            elif user_data['action'] == 'delete_admin':
                try:
                    admin_id = int(message.strip())
                    
                    if admin_id == ADMIN_ID:
                        await update.message.reply_text("❌ Asosiy adminni o'chirib bo'lmaydi!")
                    else:
                        result = admins_collection.delete_one({"id": admin_id})
                        if result.deleted_count > 0:
                            await update.message.reply_text(f"✅ Admin o'chirildi: {admin_id}")
                        else:
                            await update.message.reply_text("❌ Bunday admin topilmadi!")
                    
                    del user_data['action']
                    await manage_admins(update, context)
                except ValueError:
                    await update.message.reply_text("❌ Noto'g'ri format! Iltimos, admin ID raqamini yuboring.")

            elif user_data['action'] == 'add_channel':
                try:
                    if "|" not in message:
                        await update.message.reply_text("❌ Noto'g'ri format! Iltimos: KANAL_ID|KANAL_NOMI\nMasalan: -100123456789|Kino Kanali")
                        return
                    
                    channel_id_str, channel_name = message.split("|", 1)
                    try:
                        channel_id = int(channel_id_str.strip())
                    except ValueError:
                        await update.message.reply_text("❌ Noto'g'ri format! KANAL_ID raqam bo'lishi kerak.")
                        return
                        
                    channel_name = channel_name.strip()
                    
                    try:
                        channel = await context.bot.get_chat(channel_id)
                        username = channel.username if channel.username else "noma'lum"
                    except Exception as e:
                        print(f"Kanal ma'lumotlarini olishda xato: {e}")
                        username = "noma'lum"
                    
                    if channels_collection.find_one({"id": channel_id}):
                        await update.message.reply_text("❌ Bu kanal allaqachon mavjud!")
                        return
                        
                    new_channel = {
                        'id': channel_id,
                        'name': channel_name,
                        'username': username,
                        'added_at': datetime.now(),
                        'added_by': update.effective_user.id
                    }
                    channels_collection.insert_one(new_channel)
                    await update.message.reply_text(f"✅ Kanal qo'shildi:\nID: {channel_id}\nNomi: {channel_name}\nUsername: @{username}")
                    
                    del user_data['action']
                    await manage_channels(update, context)
                except Exception as e:
                    error_msg = f"Kanal qo'shishda xato: {e}"
                    print(error_msg)
                    await update.message.reply_text("❌ Kanal qo'shishda xato yuz berdi!")
                    await send_error_to_admin(context, error_msg)
            
            elif user_data['action'] == 'delete_channel':
                try:
                    channel_id = int(message.strip())
                    result = channels_collection.delete_one({"id": channel_id})
                    
                    if result.deleted_count > 0:
                        await update.message.reply_text(f"✅ Kanal o'chirildi: ID {channel_id}")
                    else:
                        await update.message.reply_text("❌ Bunday kanal topilmadi!")
                    
                    del user_data['action']
                    await manage_channels(update, context)
                except ValueError:
                    await update.message.reply_text("❌ Noto'g'ri format! Iltimos, kanal ID raqamini yuboring.")
    except Exception as e:
        error_msg = f"Admin harakatlarini boshqarishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Amalni bajarishda xato yuz berdi!")
        await send_error_to_admin(context, error_msg)

async def button_click(update: Update, context: CallbackContext):
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "main_menu":
            await query.message.reply_text(
                text="Asosiy menyu:",
                reply_markup=admin_menu())
            await query.message.delete()
            return
        
        elif data == "add_admin":
            await query.edit_message_text(
                text="Yangi admin ID sini yuboring:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="manage_admins")]]))
            context.user_data['action'] = 'add_admin'
            return
        
        elif data == "delete_admin":
            await query.edit_message_text(
                text="O'chiriladigan admin ID sini yuboring:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="manage_admins")]]))
            context.user_data['action'] = 'delete_admin'
            return
        
        elif data == "add_channel":
            await query.edit_message_text(
                text="Kanal ID va nomini yuboring (format: KANAL_ID|KANAL_NOMI):\n\n"
                     "Masalan: <code>-100123456789|Kino Kanali</code>\n\n"
                     "❗ Eslatma: Bot kanalda admin bo'lishi shart emas!",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="manage_channels")]]))
            context.user_data['action'] = 'add_channel'
            return
        
        elif data == "delete_channel":
            await query.edit_message_text(
                text="O'chiriladigan kanal ID sini yuboring:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="manage_channels")]]))
            context.user_data['action'] = 'delete_channel'
            return
        
        elif data == "manage_admins":
            await manage_admins_callback(update, context)
            return
        
        elif data == "manage_channels":
            await manage_channels_callback(update, context)
            return
        
        elif data == "check_subscription":
            user_id = query.from_user.id
            subscription_status = await check_subscription(user_id, context)
            
            if subscription_status is True:
                await query.edit_message_text(
                    text="✅ Barcha kanallarga obuna bo'lgansiz!\n\n"
                         "🎬 Endi botdan foydalanishingiz mumkin. Kod yuboring.",
                    reply_markup=user_menu())
            else:
                channels = subscription_status
                buttons = []
                for channel in channels:
                    if channel['username'] and channel['username'] != "noma'lum":
                        buttons.append([InlineKeyboardButton(
                            f"📢 {channel['name']} kanaliga obuna bo'lish", 
                            url=f"https://t.me/{channel['username']}")])
                    else:
                        buttons.append([InlineKeyboardButton(
                            f"📢 {channel['name']} kanali",
                            callback_data="no_username")])
                
                buttons.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_subscription")])
                
                await query.edit_message_text(
                    text="⚠️ Hali barcha kanallarga obuna bo'lmagansiz:",
                    reply_markup=InlineKeyboardMarkup(buttons))
        
        elif data == "no_username":
            await query.answer("❗ Bu kanalda username mavjud emas. Kanalga qo'lda obuna bo'lishingiz kerak.", show_alert=True)
        
        elif data == "switch_to_user":
            await query.edit_message_text(
                text="👤 Foydalanuvchi menyusiga o'tdingiz",
                reply_markup=user_menu())
        
        elif data == "switch_to_admin":
            await query.edit_message_text(
                text="🎛️ Admin menyusiga qaytdingiz",
                reply_markup=admin_menu())
    except Exception as e:
        error_msg = f"Tugma bosishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

async def manage_admins_callback(update: Update, context: CallbackContext):
    """Callback uchun alohida adminlarni boshqarish funksiyasi"""
    try:
        query = update.callback_query
        await query.answer()
        
        admins = list(admins_collection.find())
        message = "👥 <b>Adminlar boshqaruvi</b>\n\n"
        for admin in admins:
            message += f"🆔 {admin['id']} | 👤 @{admin.get('username', 'nomalum')}\n"
        
        buttons = [
            [InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin")],
            [InlineKeyboardButton("🗑️ Admin o'chirish", callback_data="delete_admin")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        error_msg = f"Adminlarni boshqarishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

async def manage_channels_callback(update: Update, context: CallbackContext):
    """Callback uchun alohida kanallarni boshqarish funksiyasi"""
    try:
        query = update.callback_query
        await query.answer()
        
        channels = list(channels_collection.find())
        message = "📢 <b>Majburiy kanallar</b>\n\n"
        for channel in channels:
            message += f"📌 {channel['name']}\nID: {channel['id']}\nUsername: @{channel['username']}\n\n"
        
        buttons = [
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_channel")],
            [InlineKeyboardButton("🗑️ Kanal o'chirish", callback_data="delete_channel")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        error_msg = f"Kanallarni boshqarishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

async def handle_user_message(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        message = update.message
        
        track_user(user)
        
        # Telefon raqamini saqlash
        if message.contact:
            users_collection.update_one(
                {"id": user.id},
                {"$set": {"phone": message.contact.phone_number}}
            )
        
        text = message.text.lower()
        
        # Admin menyusi o'tish funksiyalari
        if "foydalanuvchi menyusi" in text and is_admin(user.id):
            context.user_data['current_menu'] = 'user'
            await update.message.reply_text(
                "👤 Foydalanuvchi menyusiga o'tdingiz\n\n"
                "🎛️ Admin menyusiga qaytish uchun /admin buyrug'ini yuboring.",
                reply_markup=user_menu())
            return
        elif text == "/admin" and is_admin(user.id):
            context.user_data['current_menu'] = 'admin'
            await update.message.reply_text(
                "🎛️ Admin menyusiga qaytdingiz",
                reply_markup=admin_menu())
            return
        
        # Agar admin bo'lsa va foydalanuvchi menyusida bo'lsa
        if is_admin(user.id) and context.user_data.get('current_menu') == 'user':
            # Admin foydalanuvchi menyusida bo'lganda
            if "admin bilan bog'lanish" in text:
                await update.message.reply_text(
                    f"📞 Admin bilan bog'lanish: @{ADMIN_USERNAME}\n\n"
                    "Yoki shu yerga xabaringizni yozib qoldiring:",
                    reply_markup=ReplyKeyboardMarkup([["Orqaga"]], resize_keyboard=True))
            elif "bizning kanal" in text:
                await update.message.reply_text(f"📢 Bizning asosiy kanal: @{MAIN_CHANNEL}")
            elif "yordam" in text:
                await user_help(update)
            elif "orqaga" in text:
                await update.message.reply_text("Bosh menyu:", reply_markup=user_menu())
            else:
                # Kodlarni tekshirish
                codes = list(codes_collection.find())
                code_found = False
                for code in codes:
                    if code['code'].lower() == message.text.lower():
                        try:
                            await context.bot.copy_message(
                                chat_id=user.id,
                                from_chat_id=CHANNEL_ID,
                                message_id=code['post_id'],
                                disable_notification=True)
                            code_found = True
                            break
                        except Exception as e:
                            print(f"Xato: {e}")
                            await message.reply_text("❌ Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
                            return
                
                if not code_found:
                    await message.reply_text(
                        "❌ Bunday kod topilmadi!\n"
                        "🔍 Kodni bilmasangiz, pastdagi menyudan kerakli bo'limni tanlang.\n\n"
                        "🎛️ Admin menyusiga qaytish uchun /admin buyrug'ini yuboring.",
                        reply_markup=user_menu())
            return
        
        # Agar admin bo'lsa va admin menyusida bo'lsa
        if is_admin(user.id):
            if 'action' in context.user_data:
                await handle_admin_actions(update, context)
                return
            
            if "kino qo'shish" in text:
                await update.message.reply_text("Yangi kod qo'shish:\n/kod [KOD] [POST_ID]\nMasalan: /kod premium 123")
            elif "kodlar ro'yxati" in text:
                await list_codes(update, context)
            elif "kod o'chirish" in text:
                await update.message.reply_text("Kodni o'chirish:\n/ochirish [KOD]\nMasalan: /ochirish premium")
            elif "majburiy kanallar" in text:
                await manage_channels(update, context)
            elif "bot funksiyalari" in text:
                await bot_help(update)
            elif "kodlarni tahrirlash" in text:
                await update.message.reply_text("Kodni tahrirlash:\n/tahrirlash [KOD] [YANGI_POST_ID]\nMasalan: /tahrirlash premium 456")
            elif "admin tahrirlash" in text:
                await manage_admins(update, context)
            elif "foydalanuvchilar" in text:
                await export_users(update, context)
            elif "statistika" in text:
                await show_statistics(update, context)
            return
        
        # Oddiy foydalanuvchilar uchun
        # Obunani tekshirish
        subscription_status = await check_subscription(user.id, context)
        if subscription_status is not True:
            channels = subscription_status
            buttons = []
            for channel in channels:
                if channel['username'] and channel['username'] != "noma'lum":
                    buttons.append([InlineKeyboardButton(
                        f"📢 {channel['name']} kanaliga obuna bo'lish", 
                        url=f"https://t.me/{channel['username']}")])
                else:
                    buttons.append([InlineKeyboardButton(
                        f"📢 {channel['name']} kanali",
                        callback_data="no_username")])
            
            buttons.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_subscription")])
            
            await message.reply_text(
                "⚠️ Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling:",
                reply_markup=InlineKeyboardMarkup(buttons))
            return
        
        # Foydalanuvchi buyruqlari
        if "admin bilan bog'lanish" in text:
            await update.message.reply_text(
                f"📞 Admin bilan bog'lanish: @{ADMIN_USERNAME}\n\n"
                "Yoki shu yerga xabaringizni yozib qoldiring:",
                reply_markup=ReplyKeyboardMarkup([["Orqaga"]], resize_keyboard=True))
        elif "bizning kanal" in text:
            await update.message.reply_text(f"📢 Bizning asosiy kanal: @{MAIN_CHANNEL}")
        elif "yordam" in text:
            await user_help(update)
        elif "orqaga" in text:
            await update.message.reply_text("Bosh menyu:", reply_markup=user_menu())
        else:
            codes = list(codes_collection.find())
            for code in codes:
                if code['code'].lower() == message.text.lower():
                    try:
                        await context.bot.copy_message(
                            chat_id=user.id,
                            from_chat_id=CHANNEL_ID,
                            message_id=code['post_id'],
                            disable_notification=True)
                        return
                    except Exception as e:
                        print(f"Xato: {e}")
                        await message.reply_text("❌ Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
                        return
            
            await forward_to_admin(update, context, user, message)
            await message.reply_text(
                "❌ Bunday kod topilmadi!\n"
                "🔍 Kodni bilmasangiz, pastdagi menyudan kerakli bo'limni tanlang.",
                reply_markup=user_menu())
    except Exception as e:
        error_msg = f"Foydalanuvchi xabarini qayta ishlashda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

async def start(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        track_user(user)
        
        # Menyu holatini saqlash
        context.user_data['current_menu'] = 'admin' if is_admin(user.id) else 'user'
        
        if is_admin(user.id):
            await update.message.reply_text(
                "🎛️ Admin paneliga xush kelibsiz!\n\n"
                "👤 Foydalanuvchi menyusiga o'tish uchun 'Foydalanuvchi menyusi' tugmasini bosing.\n"
                "🎛️ Admin menyusiga qaytish uchun /admin buyrug'ini yuboring.",
                reply_markup=admin_menu())
        else:
            # Obunani tekshirish
            subscription_status = await check_subscription(user.id, context)
            if subscription_status is not True:
                channels = subscription_status
                buttons = []
                for channel in channels:
                    if channel['username'] and channel['username'] != "noma'lum":
                        buttons.append([InlineKeyboardButton(
                            f"📢 {channel['name']} kanaliga obuna bo'lish", 
                            url=f"https://t.me/{channel['username']}")])
                    else:
                        buttons.append([InlineKeyboardButton(
                            f"📢 {channel['name']} kanali",
                            callback_data="no_username")])
                
                buttons.append([InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_subscription")])
                
                await update.message.reply_text(
                    "🎬 Kino Botga xush kelibsiz!\n\n"
                    "⚠️ Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling:",
                    reply_markup=InlineKeyboardMarkup(buttons))
                return
            
            await update.message.reply_text(
                "🎬 Kino Botga xush kelibsiz!\n\n"
                "📽️ Kod yuboring va kinolarga ega bo'ling.\n"
                "🔍 Kodni bilmasangiz, pastdagi menyudan kerakli bo'limni tanlang.",
                reply_markup=user_menu())
    except Exception as e:
        error_msg = f"Start komandasida xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

async def bot_help(update: Update):
    try:
        help_text = (
            "🤖 <b>Bot funksiyalari:</b>\n\n"
            "🎬 <b>Kino qo'shish:</b>\n"
            "<code>/kod [KOD] [POST_ID]</code>\n"
            "Masalan: <code>/kod premium 123</code>\n\n"
            "✏️ <b>Kodni tahrirlash:</b>\n"
            "<code>/tahrirlash [KOD] [YANGI_POST_ID]</code>\n"
            "Masalan: <code>/tahrirlash premium 456</code>\n\n"
            "🗑️ <b>Kodni o'chirish:</b>\n"
            "<code>/ochirish [KOD]</code>\n"
            "Masalan: <code>/ochirish premium</code>\n\n"
            "📋 <b>Kodlar ro'yxati:</b>\n"
            "<code>/royxat</code>\n\n"
            "👥 <b>Admin qo'shish:</b>\n"
            "<code>/addAdmin [USER_ID]</code>\n"
            "Masalan: <code>/addAdmin 123456789</code>\n\n"
            "🗑️ <b>Admin o'chirish:</b>\n"
            "<code>/removeAdmin [USER_ID]</code>\n"
            "Masalan: <code>/removeAdmin 123456789</code>\n\n"
            "📢 <b>Kanal qo'shish:</b>\n"
            "<code>/kanalqoshish [KANAL_ID] [KANAL_NOMI]</code>\n"
            "Masalan: <code>/kanalqoshish -100123456789 Kino Kanali</code>\n\n"
            "🗑️ <b>Kanal o'chirish:</b>\n"
            "<code>/kanalochirish [KANAL_ID]</code>\n"
            "Masalan: <code>/kanalochirish -100123456789</code>\n\n"
            "📋 <b>Kanallar ro'yxati:</b>\n"
            "<code>/kanallar</code>\n\n"
            "👤 <b>Foydalanuvchilar ro'yxati:</b>\n"
            "<code>/users</code>\n\n"
            "📊 <b>Statistika:</b>\n"
            "Admin menyusidan 'Statistika' tugmasini bosing"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
    except Exception as e:
        error_msg = f"Yordam ko'rsatishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(update._context, error_msg)

async def user_help(update: Update):
    try:
        help_text = (
            "ℹ️ <b>Yordam:</b>\n\n"
            "🔢 Kinolarni olish uchun kodni yuboring\n"
            f"📞 Agar kodni bilmasangiz, admin bilan bog'laning: @{ADMIN_USERNAME}\n"
            f"📢 Bizning kanalimizga a'zo bo'ling: @{MAIN_CHANNEL}"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
    except Exception as e:
        error_msg = f"Foydalanuvchi yordamida xato: {e}"
        print(error_msg)
        await send_error_to_admin(update._context, error_msg)

# Botni doimiy faol saqlash funksiyasi
def keep_bot_active():
    """Botni doimiy faol saqlash uchun ichki faollik"""
    async def internal_activity():
        while True:
            try:
                # Har 4-5 daqiqa oralig'ida ichki faollik
                await asyncio.sleep(250 + (time.time() % 10))  # 4-5 daqiqa oralig'ida
                
                # Bot holatini tekshirish va log qilish
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                total_users = users_collection.count_documents({})
                
                print(f"🟢 Bot faol: {current_time} | Foydalanuvchilar: {total_users}")
                
                # Har 1 soatda statistika logi
                if datetime.now().minute == 0:
                    active_users = users_collection.count_documents({
                        "last_activity": {"$gte": datetime.now() - timedelta(days=1)}
                    })
                    print(f"📊 Soatlik statistika: {total_users} jami, {active_users} faol")
                    
            except Exception as e:
                print(f"❌ Bot faollik funksiyasida xato: {e}")
    
    # Yangi task yaratish
    asyncio.create_task(internal_activity())

# Botni ishga tushirish
async def start_bot():
    """Botni ishga tushirish"""
    try:
        application = Application.builder().token(TOKEN).build()
        
        # Buyruqlar
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("kod", add_code))
        application.add_handler(CommandHandler("tahrirlash", edit_code))
        application.add_handler(CommandHandler("ochirish", delete_code))
        application.add_handler(CommandHandler("royxat", list_codes))
        application.add_handler(CommandHandler("kanalqoshish", add_channel))
        application.add_handler(CommandHandler("kanalochirish", delete_channel))
        application.add_handler(CommandHandler("kanallar", list_channels))
        application.add_handler(CommandHandler("addAdmin", add_admin))
        application.add_handler(CommandHandler("removeAdmin", remove_admin))
        application.add_handler(CommandHandler("users", export_users))
        application.add_handler(CommandHandler("yordam", user_help))
        application.add_handler(CommandHandler("help", bot_help))
        application.add_handler(CommandHandler("admin", start))  # Admin menyusiga qaytish
        
        # Xabarlar
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(MessageHandler(filters.CONTACT, handle_user_message))
        
        # Tugmalar
        application.add_handler(CallbackQueryHandler(button_click))

        print("🤖 Bot ishga tushdi...")
        print(f"👤 Asosiy admin: {ADMIN_ID}")
        print(f"📊 MongoDB Database: {MONGO_DB_NAME}")
        print(f"⏰ Bot ishga tushgan vaqt: {BOT_START_TIME.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Botni faol saqlash funksiyasini ishga tushirish
        keep_bot_active()
        print("🔄 Bot faollik funksiyasi ishga tushdi")
        
        print("⏳ Bot polling ni boshladi...")
        
        # Botni ishga tushirish
        await application.run_polling()
        
    except Exception as e:
        print(f"❌ Botda jiddiy xato yuz berdi: {e}")

def main():
    """Asosiy funksiya"""
    try:
        # Flask serverni yangi threadda ishga tushirish
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"🌐 Flask server {PORT} portda ishga tushdi")
        
        # Asyncio event loop ni ishga tushirish
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("\n🛑 Bot to'xtatildi")
    except Exception as e:
        print(f"❌ Botda jiddiy xato yuz berdi: {e}")

if __name__ == '__main__':
    main()