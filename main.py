import os
import time
import random
import threading
import telebot
from telebot import types
from pymongo import MongoClient
from datetime import datetime
from flask import Flask

# ==========================================
# CẤU HÌNH BIẾN MÔI TRƯỜNG (ENV)
# ==========================================
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
MONGO_URI = os.getenv('MONGO_URI')
BANK_STK = os.getenv('BANK_STK', '11223344557766')
BANK_NAME = os.getenv('BANK_NAME', 'MB')
PORT = int(os.getenv('PORT', 10000))

# Khởi tạo Flask Server để mở Port cho Render
server = Flask(__name__)

@server.route('/')
def index():
    return "Bot Tai Xiu Pro is Active!"

def run_flask():
    server.run(host="0.0.0.0", port=PORT)

# Khởi tạo Telegram Bot & MongoDB
bot = telebot.TeleBot(TOKEN)
client = MongoClient(MONGO_URI)
db = client['taixiu_database']
users_col = db['users']
counters_col = db['counters']
codes_col = db['codes']

# --- HÀM TIỆN ÍCH (UTILS) ---
cooldowns = {}

def is_spam(user_id):
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 1.5:
        return True
    cooldowns[user_id] = now
    return False

def parse_money(text):
    """Đổi 10k -> 10000, 1m -> 1000000"""
    if not text: return -1
    text = str(text).lower().strip().replace(',', '').replace('.', '')
    try:
        if text.endswith('k'): return int(float(text[:-1]) * 1000)
        if text.endswith('m'): return int(float(text[:-1]) * 1000000)
        return int(text)
    except: return -1

def format_money(amount):
    """Đổi 10000 -> 10k"""
    if amount >= 1000000: return f"{amount/1000000:g}M"
    if amount >= 1000: return f"{amount/1000:g}k"
    return str(amount)

# --- DATABASE LOGIC ---
def get_next_stt():
    ret = counters_col.find_one_and_update({'_id': 'userid'}, {'$inc': {'seq': 1}}, upsert=True, return_document=True)
    return ret['seq']

def get_user(user_id, username=None):
    user = users_col.find_one({'_id': user_id})
    if not user:
        user = {
            '_id': user_id,
            'stt': get_next_stt(),
            'username': (username or "user").lower(),
            'balance': 5000, # Khởi tạo tặng 5k
            'vip': 0,
            'is_banned': False,
            'joined_at': datetime.now()
        }
        users_col.insert_one(user)
    return user

def find_user(ref):
    """Tìm user bằng STT, Username hoặc ID"""
    ref = str(ref).lower().replace('@', '')
    if ref.isdigit():
        return users_col.find_one({'$or': [{'stt': int(ref)}, {'_id': int(ref)}]})
    return users_col.find_one({'username': ref})

# ==========================================
# LỆNH CHO NGƯỜI CHƠI (USER)
# ==========================================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if is_spam(message.from_user.id): return
    user = get_user(message.from_user.id, message.from_user.username)
    if user['is_banned']: return
    
    text = (
        "💎 ══════════════════════ 💎\n"
        "      🎰 **TAI XIU CASINO PRO** 🎰\n"
        "💎 ══════════════════════ 💎\n"
        f"👤 Khách hàng: **{message.from_user.first_name}**\n"
        f"🆔 STT: `#{user['stt']}`  |  🌟 VIP: `{user['vip']}`\n"
        f"💰 Số dư:  **{format_money(user['balance'])}**\n"
        "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        "🎮 **Chơi:** `/play <tài/xỉu> <tiền>`\n"
        "💳 **Nạp:** `/nap <tiền>` (Min 10k)\n"
        "💸 **Rút:** `/rut <tiền> <thông tin>` (Min 70k)\n"
        "🎁 **Code:** `/code <mã>` | 👤 **Xem:** `/me` \n"
        "💎 ══════════════════════ 💎"
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['me'])
def cmd_me(message):
    user = get_user(message.from_user.id)
    rate = 1.89 + (user['vip'] * 0.1)
    text = (
        "🔰 **THÔNG TIN CÁ NHÂN**\n"
        f"🔢 STT: `#{user['stt']}`\n"
        f"💰 Số dư: **{format_money(user['balance'])}**\n"
        f"🌟 Cấp độ: `VIP {user['vip']}`\n"
        f"📈 Tỉ lệ ăn: `x{rate:.2f}`"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['play'])
def cmd_play(message):
    if is_spam(message.from_user.id): return
    user = get_user(message.from_user.id)
    if user['is_banned']: return
    
    try:
        args = message.text.split()
        side = args[1].lower()
        bet = parse_money(args[2])
        
        if side not in ['tài', 'xỉu', 'tai', 'xiu']: return
        if bet < 1000 or bet > user['balance']:
            return bot.reply_to(message, f"❌ Tiền cược không hợp lệ! Dư: {format_money(user['balance'])}")

        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -bet}})
        msg = bot.send_message(message.chat.id, "🎲 **Đang lắc xúc xắc...**")
        time.sleep(1.2)
        
        d = [random.randint(1, 6) for _ in range(3)]
        total = sum(d)
        res_side = "tài" if total >= 11 else "xỉu"
        rate = 1.89 + (user['vip'] * 0.1)
        
        if side in res_side:
            win = int(bet * rate)
            users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': win}})
            result = f"✅ **THẮNG** | +{format_money(win)}"
        else:
            result = f"❌ **THUA** | -{format_money(bet)}"
            
        final_bal = users_col.find_one({'_id': user['_id']})['balance']
        bot.edit_message_text(
            f"🎲 Kết quả: **{d[0]}-{d[1]}-{d[2]}** ➜ **{total} {res_side.upper()}**\n"
            f"{result}\n💰 Số dư hiện tại: `{format_money(final_bal)}`",
            chat_id=message.chat.id, message_id=msg.message_id, parse_mode='Markdown'
        )
    except: bot.reply_to(message, "⚠️ Cú pháp: `/play tài 10k`")

# ==========================================
# HỆ THỐNG NẠP / RÚT / CODE
# ==========================================

@bot.message_handler(commands=['nap'])
def cmd_nap(message):
    try:
        amount = parse_money(message.text.split()[1])
        if amount < 10000: return bot.reply_to(message, "❌ Nạp tối thiểu 10k!")
        user = get_user(message.from_user.id)
        qr = f"https://img.vietqr.io/image/{BANK_NAME}-{BANK_STK}-compact.png?amount={amount}&addInfo=NAP{user['_id']}"
        cap = f"🏦 **NẠP TIỀN**\n💰 Số: `{amount:,} VNĐ`\n📝 Nội dung: `NAP{user['_id']}`\n⚠️ Gửi bill vào đây!"
        bot.send_photo(message.chat.id, qr, caption=cap, parse_mode='Markdown')
        bot.register_next_step_handler(message, step_confirm_nap, amount)
    except: bot.reply_to(message, "⚠️ Cú pháp: `/nap 50k`")

def step_confirm_nap(message, amount):
    if message.content_type == 'photo':
        user = get_user(message.from_user.id)
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                       caption=f"📩 **BILL NẠP**\n👤 STT: #{user['stt']}\n💰 Số: {amount:,}đ\nLệnh: `/add {user['stt']} {format_money(amount)}`")
        bot.reply_to(message, "✅ Đã gửi bill cho Admin duyệt!")
    else: bot.reply_to(message, "❌ Hủy nạp (Không gửi ảnh bill).")

@bot.message_handler(commands=['rut'])
def cmd_rut(message):
    try:
        args = message.text.split(maxsplit=2)
        amount = parse_money(args[1])
        info = args[2]
        user = get_user(message.from_user.id)
        if amount < 70000 or amount > user['balance']: return bot.reply_to(message, "❌ Không đủ dư hoặc rút dưới 70k!")
        
        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -amount}})
        bot.send_message(ADMIN_ID, f"💸 **YÊU CẦU RÚT**\n👤 STT: #{user['stt']}\n💰 Số: {format_money(amount)}\n💳 Thông tin: `{info}`")
        bot.reply_to(message, "✅ Yêu cầu rút tiền đã được gửi tới hệ thống!")
    except: bot.reply_to(message, "⚠️ Cú pháp: `/rut 100k VCB 123...`")

@bot.message_handler(commands=['code'])
def cmd_code(message):
    user = get_user(message.from_user.id)
    try:
        c_name = message.text.split()[1].upper()
        code = codes_col.find_one({'_id': c_name})
        if not code or code['uses_left'] <= 0 or user['_id'] in code['used_by']:
            return bot.reply_to(message, "❌ Mã không hợp lệ hoặc đã hết lượt!")
        
        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': code['reward']}})
        codes_col.update_one({'_id': c_name}, {'$inc': {'uses_left': -1}, '$push': {'used_by': user['_id']}})
        bot.reply_to(message, f"🎁 Nhập thành công! Bạn nhận được **{format_money(code['reward'])}**.")
    except: bot.reply_to(message, "⚠️ Cú pháp: `/code <mã>`")

# ==========================================
# ADMIN PANEL (ẨN KHỎI MENU)
# ==========================================

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 Thêm Tiền", callback_data="adm_add"),
        types.InlineKeyboardButton("➖ Trừ Tiền", callback_data="adm_sub"),
        types.InlineKeyboardButton("🎁 Tạo Code", callback_data="adm_code"),
        types.InlineKeyboardButton("📢 Thông Báo", callback_data="adm_bc"),
        types.InlineKeyboardButton("🌟 Set VIP", callback_data="adm_vip"),
        types.InlineKeyboardButton("🚫 Ban/Unban", callback_data="adm_ban")
    )
    bot.send_message(message.chat.id, "🛠 **HỆ THỐNG ADMIN**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_buttons(call):
    if call.from_user.id != ADMIN_ID: return
    act = call.data
    m = call.message
    if act == "adm_add":
        msg = bot.send_message(m.chat.id, "Nhập: `STT SốTiền` (VD: `1 50k`)")
        bot.register_next_step_handler(msg, process_add)
    elif act == "adm_sub":
        msg = bot.send_message(m.chat.id, "Nhập: `STT SốTiền` (VD: `1 10k`)")
        bot.register_next_step_handler(msg, process_sub)
    elif act == "adm_code":
        msg = bot.send_message(m.chat.id, "Nhập: `Mã Tiền Lượt` (VD: `VIP100 100k 10`)")
        bot.register_next_step_handler(msg, process_code)
    elif act == "adm_bc":
        msg = bot.send_message(m.chat.id, "Nhập nội dung thông báo cho toàn Server:")
        bot.register_next_step_handler(msg, process_bc)
    elif act == "adm_vip":
        msg = bot.send_message(m.chat.id, "Nhập: `STT CấpVIP` (VD: `1 2`)")
        bot.register_next_step_handler(msg, process_vip)
    elif act == "adm_ban":
        msg = bot.send_message(m.chat.id, "Nhập: `STT ban/unban` (VD: `1 ban`)")
        bot.register_next_step_handler(msg, process_ban)

# --- XỬ LÝ NEXT STEP ADMIN ---

def process_add(message):
    try:
        ref, money = message.text.split()
        amt = parse_money(money)
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': amt}})
            bot.reply_to(message, f"✅ Đã cộng {format_money(amt)} cho #{u['stt']}")
            bot.send_message(u['_id'], f"🔔 Admin đã nạp **{format_money(amt)}** cho bạn!")
        else: bot.reply_to(message, "❌ Không thấy User!")
    except: bot.reply_to(message, "⚠️ Lỗi cú pháp!")

def process_sub(message):
    try:
        ref, money = message.text.split()
        amt = parse_money(money)
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': -amt}})
            bot.reply_to(message, f"✅ Đã trừ {format_money(amt)} của #{u['stt']}")
        else: bot.reply_to(message, "❌ Không thấy User!")
    except: bot.reply_to(message, "⚠️ Lỗi!")

def process_code(message):
    try:
        n, m, l = message.text.split()
        amt = parse_money(m)
        codes_col.update_one({'_id': n.upper()}, {'$set': {'reward': amt, 'uses_left': int(l), 'used_by': []}}, upsert=True)
        bot.reply_to(message, f"🎁 Code `{n.upper()}`: {format_money(amt)} ({l} lượt) đã tạo!")
    except: bot.reply_to(message, "⚠️ Lỗi!")

def process_bc(message):
    users = users_col.find({}, {'_id': 1})
    count = 0
    for u in users:
        try:
            bot.send_message(u['_id'], f"📢 **THÔNG BÁO HỆ THỐNG**\n\n{message.text}", parse_mode='Markdown')
            count += 1
            time.sleep(0.04)
        except: pass
    bot.reply_to(message, f"✅ Đã gửi tới {count} người dùng.")

def process_vip(message):
    try:
        ref, lv = message.text.split()
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$set': {'vip': int(lv)}})
            bot.reply_to(message, f"✅ Đã set VIP {lv} cho #{u['stt']}")
            bot.send_message(u['_id'], f"🌟 Chúc mừng! Bạn đã lên **VIP {lv}**.")
    except: bot.reply_to(message, "⚠️ Lỗi!")

def process_ban(message):
    try:
        ref, act = message.text.split()
        is_ban = True if act.lower() == 'ban' else False
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$set': {'is_banned': is_ban}})
            bot.reply_to(message, f"✅ Đã {'Khóa' if is_ban else 'Mở'} #{u['stt']}")
    except: bot.reply_to(message, "⚠️ Lỗi!")

# --- CHẠY SERVER PORT & BOT ---
if __name__ == "__main__":
    # Luồng chạy Flask (Port)
    threading.Thread(target=run_flask).start()
    print(f"Bot Tai Xiu is running on Port {PORT}...")
    # Luồng chạy Bot
    bot.infinity_polling()
