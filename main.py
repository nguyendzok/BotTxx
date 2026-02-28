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
# CẤU HÌNH HỆ THỐNG (ENV)
# ==========================================
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
MONGO_URI = os.getenv('MONGO_URI')
BANK_STK = os.getenv('BANK_STK', '11223344557766')
BANK_NAME = os.getenv('BANK_NAME', 'MB')
PORT = int(os.getenv('PORT', 10000))

# Khởi tạo Flask Port
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is Running!"
def run_web(): app.run(host="0.0.0.0", port=PORT)

# Khởi tạo Bot & DB
bot = telebot.TeleBot(TOKEN)
client = MongoClient(MONGO_URI)
db = client['taixiu_pro_db']
users_col = db['users']
counters_col = db['counters']
codes_col = db['codes']

# --- HÀM HỖ TRỢ (UTILS) ---
cooldowns = {}
def is_spam(user_id):
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 1.2: return True
    cooldowns[user_id] = now
    return False

def parse_money(text):
    if not text: return -1
    text = text.lower().strip().replace(',', '').replace('.', '')
    try:
        if text.endswith('k'): return int(float(text[:-1]) * 1000)
        if text.endswith('m'): return int(float(text[:-1]) * 1000000)
        return int(text)
    except: return -1

def format_money(amount):
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
        user = {'_id': user_id, 'stt': get_next_stt(), 'username': (username or "user").lower(),
                'balance': 5000, 'vip': 0, 'is_banned': False, 'joined_at': datetime.now()}
        users_col.insert_one(user)
    return user

def find_user(ref):
    ref = str(ref).lower().replace('@', '')
    if ref.isdigit(): return users_col.find_one({'$or': [{'stt': int(ref)}, {'_id': int(ref)}]})
    return users_col.find_one({'username': ref})

# ==========================================
# CHỨC NĂNG NGƯỜI CHƠI
# ==========================================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if is_spam(message.from_user.id): return
    user = get_user(message.from_user.id, message.from_user.username)
    if user['is_banned']: return
    
    text = (
        "✨ ══════════════════════ ✨\n"
        "      🎰 **TAI XIU CASINO PRO** 🎰\n"
        "✨ ══════════════════════ ✨\n"
        f"👤 Khách: **{message.from_user.first_name}**\n"
        f"🆔 STT: `#{user['stt']}` | 🌟 VIP: `{user['vip']}`\n"
        f"💰 Số dư: **{format_money(user['balance'])}**\n"
        "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        "🎮 `/play <tài/xỉu> <tiền>`\n"
        "💳 `/nap <tiền>` | 💸 `/rut <tiền> <stk>`\n"
        "🎁 `/code <mã>` | 📊 `/me` (Thông tin)\n"
        "✨ ══════════════════════ ✨"
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['me'])
def cmd_me(message):
    user = get_user(message.from_user.id)
    rate = 1.89 + (user['vip'] * 0.1)
    bot.reply_to(message, f"🔰 **INFO**\nSTT: `#{user['stt']}`\nDư: **{format_money(user['balance'])}**\nVIP: `{user['vip']}` (x{rate:.2f})", parse_mode='Markdown')

@bot.message_handler(commands=['play'])
def cmd_play(message):
    if is_spam(message.from_user.id): return
    user = get_user(message.from_user.id)
    if user['is_banned']: return
    try:
        args = message.text.split()
        side = args[1].lower()
        bet = parse_money(args[2])
        if side not in ['tài', 'xỉu', 'tai', 'xiu'] or bet < 1000 or bet > user['balance']:
            return bot.reply_to(message, "❌ Tiền cược không hợp lệ!")

        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -bet}})
        msg = bot.send_message(message.chat.id, "🎲 **Đang lắc...**")
        time.sleep(1.2)
        
        d = [random.randint(1, 6) for _ in range(3)]
        total = sum(d)
        res = "tài" if total >= 11 else "xỉu"
        rate = 1.89 + (user['vip'] * 0.1)
        
        if side in res:
            win = int(bet * rate)
            users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': win}})
            status = f"✅ **THẮNG** | +{format_money(win)}"
        else:
            status = f"❌ **THUA** | -{format_money(bet)}"
            
        new_bal = users_col.find_one({'_id': user['_id']})['balance']
        bot.edit_message_text(f"🎲 **{d[0]}-{d[1]}-{d[2]}** ➜ {total} {res.upper()}\n{status}\n💰 Dư: `{format_money(new_bal)}`", message.chat.id, msg.message_id, parse_mode='Markdown')
    except: bot.reply_to(message, "⚠️ VD: `/play tài 10k`")

# ==========================================
# ADMIN PANEL (FULL LOGIC)
# ==========================================

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 + Tiền", callback_data="adm_add"),
        types.InlineKeyboardButton("➖ - Tiền", callback_data="adm_sub"),
        types.InlineKeyboardButton("🎁 Tạo Code", callback_data="adm_code"),
        types.InlineKeyboardButton("📢 Thông Báo", callback_data="adm_bc"),
        types.InlineKeyboardButton("🌟 Set VIP", callback_data="adm_vip"),
        types.InlineKeyboardButton("🚫 Ban/Unban", callback_data="adm_ban")
    )
    bot.send_message(message.chat.id, "🛠 **HỆ THỐNG QUẢN TRỊ ADMIN**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_adm_calls(call):
    if call.from_user.id != ADMIN_ID: return
    act = call.data
    m = call.message
    if act == "adm_add":
        bot.send_message(m.chat.id, "Nhập: `STT SốTiền` (VD: `1 50k`)")
        bot.register_next_step_handler(m, step_adm_add)
    elif act == "adm_sub":
        bot.send_message(m.chat.id, "Nhập: `STT SốTiền` (VD: `1 20k`)")
        bot.register_next_step_handler(m, step_adm_sub)
    elif act == "adm_code":
        bot.send_message(m.chat.id, "Nhập: `TênCode Tiền Lượt` (VD: `KM100 100k 50`)")
        bot.register_next_step_handler(m, step_adm_code)
    elif act == "adm_bc":
        bot.send_message(m.chat.id, "Nhập nội dung thông báo gửi toàn Server:")
        bot.register_next_step_handler(m, step_adm_bc)
    elif act == "adm_vip":
        bot.send_message(m.chat.id, "Nhập: `STT CấpVIP` (VD: `1 2`)")
        bot.register_next_step_handler(m, step_adm_vip)
    elif act == "adm_ban":
        bot.send_message(m.chat.id, "Nhập: `STT HànhĐộng` (VD: `1 ban` hoặc `1 unban`)")
        bot.register_next_step_handler(m, step_adm_ban)

def step_adm_add(message):
    try:
        ref, money = message.text.split()
        amt = parse_money(money)
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': amt}})
            bot.reply_to(message, f"✅ Đã cộng {format_money(amt)} cho #{u['stt']}")
            bot.send_message(u['_id'], f"🎉 Bạn được cộng **{format_money(amt)}**!")
        else: bot.reply_to(message, "❌ Không tìm thấy User")
    except: bot.reply_to(message, "Lỗi cú pháp!")

def step_adm_sub(message):
    try:
        ref, money = message.text.split()
        amt = parse_money(money)
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': -amt}})
            bot.reply_to(message, f"✅ Đã trừ {format_money(amt)} của #{u['stt']}")
        else: bot.reply_to(message, "❌ Không tìm thấy User")
    except: bot.reply_to(message, "Lỗi cú pháp!")

def step_adm_code(message):
    try:
        name, money, uses = message.text.split()
        amt = parse_money(money)
        codes_col.update_one({'_id': name.upper()}, {'$set': {'reward': amt, 'uses_left': int(uses), 'used_by': []}}, upsert=True)
        bot.reply_to(message, f"🎁 Đã tạo code `{name.upper()}`: {format_money(amt)} ({uses} lượt)")
    except: bot.reply_to(message, "Lỗi cú pháp!")

def step_adm_bc(message):
    users = users_col.find({}, {'_id': 1})
    count = 0
    for u in users:
        try:
            bot.send_message(u['_id'], f"📢 **THÔNG BÁO HỆ THỐNG**\n\n{message.text}", parse_mode='Markdown')
            count += 1
            time.sleep(0.04)
        except: pass
    bot.reply_to(message, f"✅ Đã gửi tới {count} người.")

def step_adm_vip(message):
    try:
        ref, lv = message.text.split()
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$set': {'vip': int(lv)}})
            bot.reply_to(message, f"✅ Đã set VIP {lv} cho #{u['stt']}")
            bot.send_message(u['_id'], f"🌟 Bạn đã được nâng cấp lên **VIP {lv}**!")
    except: bot.reply_to(message, "Lỗi cú pháp!")

def step_adm_ban(message):
    try:
        ref, act = message.text.split()
        is_ban = True if act.lower() == 'ban' else False
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$set': {'is_banned': is_ban}})
            bot.reply_to(message, f"✅ Đã {'Khóa' if is_ban else 'Mở'} #{u['stt']}")
    except: bot.reply_to(message, "Lỗi cú pháp!")

# ==========================================
# NẠP / RÚT / CODE
# ==========================================

@bot.message_handler(commands=['nap'])
def cmd_nap(message):
    try:
        amt = parse_money(message.text.split()[1])
        if amt < 10000: return bot.reply_to(message, "Min 10k!")
        u = get_user(message.from_user.id)
        qr = f"https://img.vietqr.io/image/{BANK_NAME}-{BANK_STK}-compact.png?amount={amt}&addInfo=NAP{u['_id']}"
        bot.send_photo(message.chat.id, qr, caption=f"🏦 Nạp `{amt:,}đ`\nNội dung: `NAP{u['_id']}`\n⚠️ Gửi ảnh bill vào đây!")
        bot.register_next_step_handler(message, step_confirm_nap, amt)
    except: bot.reply_to(message, "⚠️ VD: `/nap 50k`")

def step_confirm_nap(message, amt):
    if message.content_type == 'photo':
        u = get_user(message.from_user.id)
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"📩 **BILL**\nSTT: #{u['stt']}\nSố: {amt:,}\nLệnh: `/add {u['stt']} {format_money(amt)}`")
        bot.reply_to(message, "✅ Đã gửi bill!")
    else: bot.reply_to(message, "❌ Hủy.")

@bot.message_handler(commands=['rut'])
def cmd_rut(message):
    try:
        args = message.text.split(maxsplit=2)
        amt = parse_money(args[1])
        info = args[2]
        u = get_user(message.from_user.id)
        if amt < 70000 or amt > u['balance']: return bot.reply_to(message, "Số dư không đủ hoặc < 70k!")
        users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': -amt}})
        bot.send_message(ADMIN_ID, f"💸 **RÚT TIỀN**\nSTT: #{u['stt']}\nSố: {format_money(amt)}\nThông tin: `{info}`")
        bot.reply_to(message, "✅ Đã gửi yêu cầu rút!")
    except: bot.reply_to(message, "⚠️ `/rut 100k <STK>`")

@bot.message_handler(commands=['code'])
def cmd_code(message):
    u = get_user(message.from_user.id)
    try:
        c_name = message.text.split()[1].upper()
        code = codes_col.find_one({'_id': c_name})
        if not code or code['uses_left'] <= 0 or u['_id'] in code['used_by']:
            return bot.reply_to(message, "❌ Code lỗi!")
        users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': code['reward']}})
        codes_col.update_one({'_id': c_name}, {'$inc': {'uses_left': -1}, '$push': {'used_by': u['_id']}})
        bot.reply_to(message, f"🎁 Xong! +{format_money(code['reward'])}")
    except: bot.reply_to(message, "⚠️ `/code <mã>`")

# --- START ---
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    print(f"Bot is running on Port {PORT}...")
    bot.infinity_polling()
