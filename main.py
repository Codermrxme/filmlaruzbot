import os
import json
import pandas as pd
from datetime import datetime
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



# 🔧 .env fayldan sozlamalarni yuklash
load_dotenv()

# Bot sozlamalari
TOKEN = os.getenv('TOKEN', '')  # @BotFather dan oling
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))  # Sizning Telegram ID
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  # Kanal ID (manfiy son)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '')  # Sizning username
MAIN_CHANNEL = os.getenv('MAIN_CHANNEL', '')  # Asosiy kanal username

# Xatolikni tekshirish
if not TOKEN:
    raise ValueError("TOKEN .env faylda aniqlanmagan yoki noto'g'ri")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID .env faylda aniqlanmagan yoki noto'g'ri")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID .env faylda aniqlanmagan yoki noto'g'ri")
if not ADMIN_USERNAME:
    print("Diqqat: ADMIN_USERNAME .env faylda aniqlanmagan")
if not MAIN_CHANNEL:
    print("Diqqat: MAIN_CHANNEL .env faylda aniqlanmagan")

# 📂 Fayllar
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = f"{DATA_DIR}/admins.json"
CODES_FILE = f"{DATA_DIR}/codes.json"
USERS_FILE = f"{DATA_DIR}/users.json"
CHANNELS_FILE = f"{DATA_DIR}/channels.json"
SUBSCRIPTIONS_FILE = f"{DATA_DIR}/subscriptions.json"

# ... (qolgan kod o'zgarishsiz qoldi) ...

# 🛠️ Yordamchi funksiyalar
def load_from_file(filename, default=None):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data is None:
                return default if default is not None else {}
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        if "admin" in filename:
            return [{"id": ADMIN_ID, "username": ADMIN_USERNAME}]
        return default if default is not None else {}

def save_to_file(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def is_admin(user_id):
    admins = load_from_file(ADMINS_FILE, default=[])
    return any(admin['id'] == user_id for admin in admins)

def channel_link(post_id):
    return f"https://t.me/c/{str(CHANNEL_ID)[4:]}/{post_id}"

def track_user(user):
    users = load_from_file(USERS_FILE, default={})
    user_id = str(user.id)
    
    if user_id not in users:
        users[user_id] = {
            "id": user.id,
            "name": user.full_name,
            "username": user.username,
            "phone": None,
            "start_time": str(datetime.now()),
            "last_activity": str(datetime.now())
        }
    else:
        users[user_id]['last_activity'] = str(datetime.now())
    
    save_to_file(users, USERS_FILE)

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
        users = load_from_file(USERS_FILE, default={})
        # await context.bot.send_message(
        #     chat_id=ADMIN_ID,
        #     text=f"👤 Yangi xabar\n"
        #          f"🆔 ID: {user.id}\n"
        #          f"👤 Ism: {user.full_name}\n"
        #          f"📌 Username: @{user.username if user.username else 'yoq'}\n"
        #          f"📞 Telefon: {users.get(str(user.id), {}).get('phone', 'noma\'lum')}"
        # )
    except Exception as e:
        error_msg = f"Adminga yuborishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

def admin_menu():
    buttons = [
        ["🎬 Kino qo'shish", "📋 Kodlar ro'yxati"],
        ["🗑️ Kod o'chirish", "📢 Majburiy kanallar"],
        ["🤖 Bot funksiyalari", "✏️ Kodlarni tahrirlash"],
        ["👥 Admin tahrirlash", "👤 Foydalanuvchilar"]
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
        channels = load_from_file(CHANNELS_FILE, default=[])
        if not channels:
            return True
        
        subscriptions = load_from_file(SUBSCRIPTIONS_FILE, default={})
        
        if str(user_id) in subscriptions and subscriptions[str(user_id)]:
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
            subscriptions[str(user_id)] = True
            save_to_file(subscriptions, SUBSCRIPTIONS_FILE)
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

        users = load_from_file(USERS_FILE, default={})
        if not users:
            await update.message.reply_text("❌ Foydalanuvchilar mavjud emas!")
            return

        df = pd.DataFrame(list(users.values()))
        excel_file = f"{DATA_DIR}/users.xlsx"
        df.to_excel(excel_file, index=False)

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(excel_file, 'rb'),
            caption="📊 Foydalanuvchilar ro'yxati"
        )
    except Exception as e:
        error_msg = f"Foydalanuvchilarni eksport qilishda xato: {e}"
        print(error_msg)
        await update.message.reply_text("❌ Foydalanuvchilar ro'yxatini yuborishda xato yuz berdi!")
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
            
        admins = load_from_file(ADMINS_FILE, default=[])
        
        if any(admin['id'] == admin_id for admin in admins):
            await update.message.reply_text("❌ Bu admin allaqachon mavjud!")
            return
        
        try:
            user = await context.bot.get_chat(admin_id)
            new_admin = {
                'id': admin_id,
                'username': user.username if user.username else 'noma\'lum'
            }
            admins.append(new_admin)
            save_to_file(admins, ADMINS_FILE)
            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (@{user.username if user.username else 'noma\'lum'})")
        except Exception as e:
            print(f"Foydalanuvchi ma'lumotlarini olishda xato: {e}")
            new_admin = {
                'id': admin_id,
                'username': 'noma\'lum'
            }
            admins.append(new_admin)
            save_to_file(admins, ADMINS_FILE)
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
            
        admins = load_from_file(ADMINS_FILE, default=[])
        new_admins = [admin for admin in admins if admin['id'] != admin_id]
        
        if len(new_admins) == len(admins):
            await update.message.reply_text("❌ Bunday admin topilmadi!")
            return
        
        save_to_file(new_admins, ADMINS_FILE)
        await update.message.reply_text(f"✅ Admin o'chirildi: {admin_id}")
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
            
        codes = load_from_file(CODES_FILE, default=[])
        if any(c['code'].lower() == code.lower() for c in codes):
            await update.message.reply_text("❌ Bu kod allaqachon mavjud!")
            return
            
        codes.append({"code": code, "post_id": post_id})
        save_to_file(codes, CODES_FILE)
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
            
        codes = load_from_file(CODES_FILE, default=[])
        for c in codes:
            if c['code'].lower() == code.lower():
                c['post_id'] = new_post_id
                save_to_file(codes, CODES_FILE)
                await update.message.reply_text(f"✅ Kod tahrirlandi: {code} ➡️ {new_post_id}")
                return
                
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
        codes = load_from_file(CODES_FILE, default=[])
        codes = [c for c in codes if c['code'].lower() != code.lower()]
        save_to_file(codes, CODES_FILE)
        await update.message.reply_text(f"✅ Kod o'chirildi: {code}")
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

        codes = load_from_file(CODES_FILE, default=[])
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
        
        channels = load_from_file(CHANNELS_FILE, default=[])
        
        if any(c['id'] == channel_id for c in channels):
            await update.message.reply_text("❌ Bu kanal allaqachon mavjud!")
            return
            
        new_channel = {
            'id': channel_id,
            'name': channel_name,
            'username': username
        }
        channels.append(new_channel)
        save_to_file(channels, CHANNELS_FILE)
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
            
        channels = load_from_file(CHANNELS_FILE, default=[])
        new_channels = [c for c in channels if c['id'] != channel_id]
        
        if len(new_channels) == len(channels):
            await update.message.reply_text("❌ Bunday kanal topilmadi!")
            return
            
        save_to_file(new_channels, CHANNELS_FILE)
        await update.message.reply_text(f"✅ Kanal o'chirildi: ID {channel_id}")
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

        channels = load_from_file(CHANNELS_FILE, default=[])
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

        channels = load_from_file(CHANNELS_FILE, default=[])
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

        admins = load_from_file(ADMINS_FILE, default=[])
        message = "👥 <b>Adminlar boshqaruvi</b>\n\n"
        for admin in admins:
            message += f"🆔 {admin['id']} | 👤 @{admin.get('username', 'noma\'lum')}\n"
        
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
                    admins = load_from_file(ADMINS_FILE, default=[])
                    
                    if any(admin['id'] == admin_id for admin in admins):
                        await update.message.reply_text("❌ Bu admin allaqachon mavjud!")
                    else:
                        try:
                            user = await context.bot.get_chat(admin_id)
                            admins.append({
                                'id': admin_id,
                                'username': user.username if user.username else 'noma\'lum'
                            })
                            save_to_file(admins, ADMINS_FILE)
                            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (@{user.username if user.username else 'noma\'lum'})")
                        except Exception as e:
                            print(f"Foydalanuvchi ma'lumotlarini olishda xato: {e}")
                            admins.append({
                                'id': admin_id,
                                'username': 'noma\'lum'
                            })
                            save_to_file(admins, ADMINS_FILE)
                            await update.message.reply_text(f"✅ Admin qo'shildi: {admin_id} (username noma'lum)")
                    
                    del user_data['action']
                    await manage_admins(update, context)
                except ValueError:
                    await update.message.reply_text("❌ Noto'g'ri admin IDsi! Iltimos, raqam yuboring.")
            
            elif user_data['action'] == 'delete_admin':
                try:
                    admin_id = int(message.strip())
                    admins = load_from_file(ADMINS_FILE, default=[])
                    new_admins = [admin for admin in admins if admin['id'] != admin_id]
                    
                    if len(new_admins) == len(admins):
                        await update.message.reply_text("❌ Bunday admin topilmadi!")
                    else:
                        save_to_file(new_admins, ADMINS_FILE)
                        await update.message.reply_text(f"✅ Admin o'chirildi: {admin_id}")
                    
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
                    
                    channels = load_from_file(CHANNELS_FILE, default=[])
                    
                    if any(c['id'] == channel_id for c in channels):
                        await update.message.reply_text("❌ Bu kanal allaqachon mavjud!")
                        return
                        
                    channels.append({
                        'id': channel_id,
                        'name': channel_name,
                        'username': username
                    })
                    save_to_file(channels, CHANNELS_FILE)
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
                    channels = load_from_file(CHANNELS_FILE, default=[])
                    new_channels = [c for c in channels if c['id'] != channel_id]
                    
                    if len(new_channels) == len(channels):
                        await update.message.reply_text("❌ Bunday kanal topilmadi!")
                    else:
                        save_to_file(new_channels, CHANNELS_FILE)
                        await update.message.reply_text(f"✅ Kanal o'chirildi: ID {channel_id}")
                    
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
            await query.edit_message_text(text="Asosiy menyu:", reply_markup=admin_menu())
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
            await manage_admins(update, context)
            return
        
        elif data == "manage_channels":
            await manage_channels(update, context)
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
    except Exception as e:
        error_msg = f"Tugma bosishda xato: {e}"
        print(error_msg)
        await send_error_to_admin(context, error_msg)

async def handle_user_message(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        message = update.message
        
        track_user(user)
        
        # Telefon raqamini saqlash
        if message.contact:
            users = load_from_file(USERS_FILE, default={})
            user_id = str(user.id)
            if user_id in users:
                users[user_id]['phone'] = message.contact.phone_number
                save_to_file(users, USERS_FILE)
        
        # Admin harakatlari
        if is_admin(user.id):
            if 'action' in context.user_data:
                await handle_admin_actions(update, context)
                return
            
            text = message.text.lower()
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
            return
        
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
        text = message.text.lower()
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
            codes = load_from_file(CODES_FILE, default=[])
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
        
        if is_admin(user.id):
            await update.message.reply_text(
                "🎛️ Admin paneliga xush kelibsiz!",
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
            "<code>/users</code>"
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

def main():
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
        
        # Xabarlar
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        application.add_handler(MessageHandler(filters.CONTACT, handle_user_message))
        
        # Tugmalar
        application.add_handler(CallbackQueryHandler(button_click))

        print("Bot ishga tushdi...")
        application.run_polling()
    except Exception as e:
        print(f"Botda jiddiy xato yuz berdi: {e}")

if __name__ == '__main__':
    main()