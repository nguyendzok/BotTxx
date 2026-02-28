import os
import time
import random
import threading
import sys
import telebot
from telebot import types
from pymongo import MongoClient
from datetime import datetime
from flask import Flask

# ==========================================
# CẤU HÌNH BIẾN MÔI TRƯỜNG (ENV)
# ==========================================
TOKEN = os.getenv('BOT_TOKEN')

if not TOKEN:
    print("❌ LỖI: KHÔNG TÌM THẤY BOT_TOKEN! HÃY KIỂM TRA LẠI MỤC ENVIRONMENT TRÊN RENDER.")
    sys.exit(1)

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
MONGO_URI = os.getenv('MONGO_URI')
BANK_STK = os.getenv('BANK_STK', '11223344557766')
BANK_NAME = os.getenv('BANK_NAME', 'MB')
PORT = int(os.getenv('PORT', 10000))

# Mở Port cho Render
server = Flask(__name__)
@server.route('/')
def index(): return "Bot Tai Xiu Pro Max is Active!"
def run_flask(): server.run(host="0.0.0.0", port=PORT)

# Khởi tạo Bot & Database
bot = telebot.TeleBot(TOKEN)
client = MongoClient(MONGO_URI)
db = client['taixiu_database']
users_col = db['users']
counters_col = db['counters']
codes_col = db['codes']
history_col = db['history'] # Bảng mới lưu Lịch sử Soi Cầu

# --- HÀM TIỆN ÍCH (UTILS) ---
cooldowns = {}
temp_bet = {}

def is_spam(user_id):
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 1.0: return True
    cooldowns[user_id] = now
    return False

def parse_money(text):
    if not text: return -1
    text = str(text).lower().strip().replace(',', '').replace('.', '')
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

def add_history(d1, d2, d3, total, result):
    history_col.insert_one({
        'time': datetime.now(),
        'd1': d1, 'd2': d2, 'd3': d3,
        'total': total, 'result': result
    })

# ==========================================
# GIAO DIỆN NGƯỜI CHƠI (USER PANEL)
# ==========================================

def get_main_menu(user):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎮 CHƠI TÀI XỈU", callback_data="u_play_menu"),
        types.InlineKeyboardButton("📊 SOI CẦU", callback_data="u_soicau")
    )
    markup.add(
        types.InlineKeyboardButton("💳 NẠP TIỀN", callback_data="u_nap"),
        types.InlineKeyboardButton("💸 RÚT TIỀN", callback_data="u_rut")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 NHẬP CODE", callback_data="u_code"),
        types.InlineKeyboardButton("👤 CÁ NHÂN", callback_data="u_me")
    )
    
    text = (
        "💎 ════════════════════ 💎\n"
        "      🎰 **TAI XIU CASINO PRO** 🎰\n"
        "⚡️ Uy Tín • Nhanh Chóng • Tự Động ⚡️\n"
        "💎 ════════════════════ 💎\n\n"
        "👤 **THÔNG TIN CỦA BẠN:**\n"
        f"├ 🆔 ID Nạp: `NAP{user['_id']}`\n"
        f"├ 🔢 STT: `#{user['stt']}` | 🌟 VIP: `{user['vip']}`\n"
        f"└ 💰 Số dư:  **{format_money(user['balance'])}**\n\n"
        "👇 **Vui lòng chọn thao tác bên dưới:**"
    )
    return text, markup

def get_play_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔵 ĐẶT TÀI", callback_data="u_play_tai"),
        types.InlineKeyboardButton("🔴 ĐẶT XỈU", callback_data="u_play_xiu")
    )
    markup.add(
        types.InlineKeyboardButton("📊 SOI CẦU", callback_data="u_soicau"),
        types.InlineKeyboardButton("🔙 QUAY LẠI", callback_data="u_main")
    )
    return markup

def get_back_btn():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 QUAY LẠI MENU", callback_data="u_main"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if is_spam(message.from_user.id): return
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user = get_user(message.from_user.id, message.from_user.username)
    if user['is_banned']: return bot.reply_to(message, "⛔ Tài khoản đã bị khóa.")
    
    text, markup = get_main_menu(user)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

# ==========================================
# XỬ LÝ NÚT BẤM (CALLBACKS)
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('u_'))
def handle_user_callbacks(call):
    if is_spam(call.from_user.id): return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    user = get_user(call.from_user.id)
    if user['is_banned']: return
    
    act = call.data
    m = call.message
    
    try:
        if act == "u_main":
            text, markup = get_main_menu(user)
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
            
        elif act == "u_me":
            rate = 1.89 + (user['vip'] * 0.1)
            text = f"🔰 **CÁ NHÂN**\n\n👤 Tên: @{user['username']}\n🔢 STT: `#{user['stt']}`\n💰 Dư: **{format_money(user['balance'])}**\n🌟 VIP: `{user['vip']}` (Tỉ lệ ăn: x{rate:.2f})"
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            
        elif act == "u_soicau":
            # Lấy 15 ván gần nhất từ Database
            recent = list(history_col.find().sort('_id', -1).limit(15))
            if not recent:
                text = "📊 **BẢNG SOI CẦU**\n\nChưa có dữ liệu phiên nào!"
            else:
                text = "📊 **BẢNG SOI CẦU (15 PHIÊN GẦN NHẤT)**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                # Hiển thị dạng cầu ngang (VD: T - X - T - T)
                trend = " - ".join(["🔵" if r['result']=="TÀI" else "🔴" for r in recent[::-1]])
                text += f"Bóng:\n{trend}\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                # Chi tiết 5 ván gần nhất
                text += "🔍 **Chi tiết 5 ván gần nhất:**\n"
                for i, r in enumerate(recent[:5]):
                    text += f"▪️ Ván {-i}: `{r['d1']}-{r['d2']}-{r['d3']}` = **{r['total']}** ({r['result']})\n"
                    
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=get_play_menu(), parse_mode='Markdown')

        elif act == "u_play_menu":
            bot.edit_message_text("🎲 **CHỌN CỬA BẠN MUỐN ĐẶT:**", m.chat.id, m.message_id, reply_markup=get_play_menu(), parse_mode='Markdown')
            
        elif act in ["u_play_tai", "u_play_xiu"]:
            side = "TÀI" if act == "u_play_tai" else "XỈU"
            temp_bet[call.from_user.id] = side
            msg = bot.edit_message_text(f"👇 Bạn đang chọn cửa: **{side}**.\n\n⌨️ **HÃY NHẬP SỐ TIỀN MUỐN CƯỢC VÀO ĐÂY:**\n*(VD: 10k, 50k, 1m)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_play_amount, m.message_id)

        elif act == "u_nap":
            msg = bot.edit_message_text("💳 **NẠP TIỀN**\n\n⌨️ **Hãy nhập số tiền bạn muốn nạp:**\n*(Tối thiểu 10k)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_nap_amount, m.message_id)
            
        elif act == "u_rut":
            msg = bot.edit_message_text("💸 **RÚT TIỀN**\n\n⌨️ **Hãy nhập số tiền và STK:**\n*(VD: 100k MB 0123 Nguyen Van A)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_rut_info, m.message_id)
            
        elif act == "u_code":
            msg = bot.edit_message_text("🎁 **NHẬP GIFTCODE**\n\n⌨️ **Hãy nhập mã code của bạn:**", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_giftcode, m.message_id)
            
    except Exception as e:
        pass 

# ==========================================
# XỬ LÝ NHẬP LIỆU (NEXT STEPS) & ANIMATION
# ==========================================

def process_play_amount(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id) # Xóa text 10k khách vừa gõ
    except: pass
    
    user = get_user(message.from_user.id)
    bet = parse_money(message.text)
    side = temp_bet.get(message.from_user.id, "TÀI")
    
    if bet < 1000 or bet > user['balance']:
        bot.edit_message_text(f"❌ Số tiền không hợp lệ hoặc không đủ! (Dư: {format_money(user['balance'])})\n\n⌨️ **Nhập lại số tiền cược:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_play_amount, old_msg_id)
        return

    # Trừ tiền
    users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -bet}})
    
    # Xóa menu cũ để hiện Animation Xúc xắc
    try: bot.delete_message(message.chat.id, old_msg_id)
    except: pass

    # Gửi 3 viên xúc xắc động của Telegram
    d1_msg = bot.send_dice(message.chat.id, emoji='🎲')
    d2_msg = bot.send_dice(message.chat.id, emoji='🎲')
    d3_msg = bot.send_dice(message.chat.id, emoji='🎲')
    
    # Chờ xúc xắc lăn xong (khoảng 3.5 giây)
    time.sleep(3.5)
    
    # Lấy kết quả từ server Telegram
    d1 = d1_msg.dice.value
    d2 = d2_msg.dice.value
    d3 = d3_msg.dice.value
    total = d1 + d2 + d3
    res_side = "TÀI" if total >= 11 else "XỈU"
    rate = 1.89 + (user['vip'] * 0.1)
    
    # Lưu vào lịch sử Soi Cầu
    add_history(d1, d2, d3, total, res_side)
    
    # Kiểm tra kết quả
    if side == res_side:
        win = int(bet * rate)
        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': win}})
        result = f"✅ **BẠN THẮNG** | +{format_money(win)}"
    else:
        result = f"❌ **BẠN THUA** | -{format_money(bet)}"
        
    final_bal = users_col.find_one({'_id': user['_id']})['balance']
    
    # Gửi bảng kết quả
    text = (
        f"🔥 **KẾT QUẢ: {d1} - {d2} - {d3}** ➜ **{total} {res_side}**\n"
        "〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        f"Bạn đặt: {side} {format_money(bet)}\n"
        f"{result}\n"
        f"💰 Số dư mới: `{format_money(final_bal)}`\n\n"
        f"👇 **CHƠI TIẾP BÊN DƯỚI:**"
    )
    bot.send_message(message.chat.id, text, reply_markup=get_play_menu(), parse_mode='Markdown')

def process_nap_amount(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    amount = parse_money(message.text)
    user = get_user(message.from_user.id)
    
    if amount < 10000:
        bot.edit_message_text("❌ Nạp tối thiểu 10k!\n\n⌨️ **Nhập lại số tiền nạp:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_nap_amount, old_msg_id)
        return
        
    qr = f"https://img.vietqr.io/image/{BANK_NAME}-{BANK_STK}-compact.png?amount={amount}&addInfo=NAP{user['_id']}"
    cap = f"🏦 **NẠP TIỀN**\n💰 Số: `{amount:,} VNĐ`\n📝 Nội dung: `NAP{user['_id']}`\n\n⚠️ Gửi ảnh bill vào đây sau khi chuyển khoản!"
    
    try: bot.delete_message(message.chat.id, old_msg_id)
    except: pass
    
    bot.send_photo(message.chat.id, qr, caption=cap, reply_markup=get_back_btn(), parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_nap_bill, amount)

def process_nap_bill(message, amount):
    if message.content_type == 'photo':
        user = get_user(message.from_user.id)
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"📩 **BILL NẠP**\n👤 STT: #{user['stt']}\n💰 Số: {amount:,}đ\nLệnh: `/add {user['stt']} {format_money(amount)}`")
        
        text, markup = get_main_menu(user)
        bot.reply_to(message, "✅ Đã gửi bill cho Admin duyệt!")
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')
    else:
        text, markup = get_main_menu(get_user(message.from_user.id))
        bot.reply_to(message, "❌ Không nhận được ảnh. Yêu cầu nạp đã hủy!")
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

def process_rut_info(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        args = message.text.split(maxsplit=1)
        amount = parse_money(args[0])
        info = args[1]
        user = get_user(message.from_user.id)
        
        if amount < 70000 or amount > user['balance']:
            bot.edit_message_text("❌ Không đủ số dư hoặc rút dưới 70k!\n\n⌨️ **Nhập lại (VD: 100k STK):**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_info, old_msg_id)
            return
            
        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -amount}})
        bot.send_message(ADMIN_ID, f"💸 **YÊU CẦU RÚT**\n👤 STT: #{user['stt']}\n💰 Số: {format_money(amount)}\n💳 Thông tin: `{info}`")
        bot.edit_message_text(f"✅ Đã gửi yêu cầu rút **{format_money(amount)}** tới hệ thống!", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
    except:
        bot.edit_message_text("⚠️ Sai cú pháp!\n\n⌨️ **Nhập lại (VD: 100k MB 0123 Nguyen Van A):**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_info, old_msg_id)

def process_giftcode(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    user = get_user(message.from_user.id)
    c_name = message.text.strip().upper()
    code = codes_col.find_one({'_id': c_name})
    
    if not code or code['uses_left'] <= 0 or user['_id'] in code['used_by']:
        bot.edit_message_text("❌ Mã code sai hoặc đã hết lượt!\n\n⌨️ **Thử nhập lại mã khác:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_giftcode, old_msg_id)
        return
        
    users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': code['reward']}})
    codes_col.update_one({'_id': c_name}, {'$inc': {'uses_left': -1}, '$push': {'used_by': user['_id']}})
    bot.edit_message_text(f"🎁 **NHẬP CODE THÀNH CÔNG!**\nBạn nhận được: **{format_money(code['reward'])}**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')


# ==========================================
# ADMIN PANEL BÍ MẬT (VIẾT TAY /admin)
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
    bot.send_message(message.chat.id, "🛠 **BẢNG ĐIỀU KHIỂN ADMIN**", reply_markup=markup)

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
    threading.Thread(target=run_flask).start()
    print(f"Bot Tai Xiu is running on Port {PORT}...")
    bot.infinity_polling()
