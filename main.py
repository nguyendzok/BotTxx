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

server = Flask(__name__)
@server.route('/')
def index(): return "Bot Tai Xiu Pro is Active!"
def run_flask(): server.run(host="0.0.0.0", port=PORT)

bot = telebot.TeleBot(TOKEN)
client = MongoClient(MONGO_URI)
db = client['taixiu_database']
users_col = db['users']
counters_col = db['counters']
codes_col = db['codes']

# --- HÀM TIỆN ÍCH (UTILS) ---
cooldowns = {}
temp_bet = {} # Lưu tạm lựa chọn Tài/Xỉu của user

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

# ==========================================
# GIAO DIỆN NÚT BẤM (USER PANEL)
# ==========================================

# Giao diện Menu Chính
def get_main_menu(user):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎮 CHƠI TÀI XỈU", callback_data="u_play_menu"),
        types.InlineKeyboardButton("👤 CÁ NHÂN", callback_data="u_me")
    )
    markup.add(
        types.InlineKeyboardButton("💳 NẠP TIỀN", callback_data="u_nap"),
        types.InlineKeyboardButton("💸 RÚT TIỀN", callback_data="u_rut")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 NHẬP GIFTCODE", callback_data="u_code")
    )
    
    text = (
        "💎 ══════════════════════ 💎\n"
        "      🎰 **TAI XIU CASINO PRO** 🎰\n"
        "⚡️ Uy Tín • Nhanh Chóng • Tự Động ⚡️\n"
        "💎 ══════════════════════ 💎\n\n"
        "👤 **THÔNG TIN CỦA BẠN:**\n"
        f"├ 🆔 ID Nạp: `NAP{user['_id']}`\n"
        f"├ 🔢 STT: `#{user['stt']}` | 🌟 VIP: `{user['vip']}`\n"
        f"└ 💰 Số dư:  **{format_money(user['balance'])}**\n\n"
        "👇 **Vui lòng chọn thao tác bên dưới:**"
    )
    return text, markup

# Nút Quay Lại
def get_back_btn():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 QUAY LẠI MENU", callback_data="u_main"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if is_spam(message.from_user.id): return
    bot.clear_step_handler_by_chat_id(message.chat.id) # Xóa các bước đang nhập dở
    user = get_user(message.from_user.id, message.from_user.username)
    if user['is_banned']: return bot.reply_to(message, "⛔ Tài khoản đã bị khóa.")
    
    text, markup = get_main_menu(user)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

# ==========================================
# XỬ LÝ NÚT BẤM CỦA NGƯỜI CHƠI
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('u_'))
def handle_user_callbacks(call):
    if is_spam(call.from_user.id): return
    bot.clear_step_handler_by_chat_id(call.message.chat.id) # Hủy nhập tay khi bấm nút
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
            
        elif act == "u_play_menu":
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🔵 ĐẶT TÀI", callback_data="u_play_tai"),
                types.InlineKeyboardButton("🔴 ĐẶT XỈU", callback_data="u_play_xiu")
            )
            markup.add(types.InlineKeyboardButton("🔙 QUAY LẠI MENU", callback_data="u_main"))
            bot.edit_message_text("🎲 **CHỌN CỬA BẠN MUỐN ĐẶT:**", m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
            
        elif act in ["u_play_tai", "u_play_xiu"]:
            side = "TÀI" if act == "u_play_tai" else "XỈU"
            temp_bet[call.from_user.id] = side
            msg = bot.edit_message_text(f"👇 Bạn chọn **{side}**.\n\n⌨️ **HÃY NHẬP SỐ TIỀN MUỐN CƯỢC VÀO KHUNG CHAT:**\n*(VD: 10k, 50k)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
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
        pass # Bỏ qua lỗi EditMessage nếu text không thay đổi

# ==========================================
# CÁC HÀM XỬ LÝ NHẬP LIỆU (NEXT STEPS)
# ==========================================

def process_play_amount(message, old_msg_id):
    bot.delete_message(message.chat.id, message.message_id) # Xóa tin nhắn rác của user
    user = get_user(message.from_user.id)
    bet = parse_money(message.text)
    side = temp_bet.get(message.from_user.id, "TÀI")
    
    if bet < 1000 or bet > user['balance']:
        bot.edit_message_text(f"❌ Số tiền không hợp lệ hoặc không đủ! (Dư: {format_money(user['balance'])})\n\n⌨️ **Nhập lại số tiền cược:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_play_amount, old_msg_id)
        return

    # Trừ tiền
    users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -bet}})
    bot.edit_message_text("🎲 **Đang lắc xúc xắc...**", message.chat.id, old_msg_id, parse_mode='Markdown')
    time.sleep(1.2)
    
    d = [random.randint(1, 6) for _ in range(3)]
    total = sum(d)
    res_side = "TÀI" if total >= 11 else "XỈU"
    rate = 1.89 + (user['vip'] * 0.1)
    
    if side == res_side:
        win = int(bet * rate)
        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': win}})
        result = f"✅ **THẮNG** | +{format_money(win)}"
    else:
        result = f"❌ **THUA** | -{format_money(bet)}"
        
    final_bal = users_col.find_one({'_id': user['_id']})['balance']
    
    # Hiện lại menu chơi để khách cược tiếp
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔵 ĐẶT TÀI", callback_data="u_play_tai"),
        types.InlineKeyboardButton("🔴 ĐẶT XỈU", callback_data="u_play_xiu")
    )
    markup.add(types.InlineKeyboardButton("🔙 QUAY LẠI MENU", callback_data="u_main"))
    
    bot.edit_message_text(f"🔥 **KẾT QUẢ: {d[0]}-{d[1]}-{d[2]}** ➜ **{total} {res_side}**\n\nBạn đặt: {side} {format_money(bet)}\n{result}\n💰 Số dư mới: `{format_money(final_bal)}`\n\n👇 **CHƠI TIẾP:**", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')

def process_nap_amount(message, old_msg_id):
    bot.delete_message(message.chat.id, message.message_id)
    amount = parse_money(message.text)
    user = get_user(message.from_user.id)
    
    if amount < 10000:
        bot.edit_message_text("❌ Nạp tối thiểu 10k!\n\n⌨️ **Nhập lại số tiền nạp:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_nap_amount, old_msg_id)
        return
        
    qr = f"https://img.vietqr.io/image/{BANK_NAME}-{BANK_STK}-compact.png?amount={amount}&addInfo=NAP{user['_id']}"
    cap = f"🏦 **NẠP TIỀN**\n💰 Số: `{amount:,} VNĐ`\n📝 Nội dung: `NAP{user['_id']}`\n\n⚠️ Mở app ngân hàng quét mã QR trên.\nSau khi chuyển khoản, hãy **GỬI ẢNH BILL** trực tiếp vào đây!"
    
    bot.delete_message(message.chat.id, old_msg_id) # Xóa tin nhắn menu cũ
    bot.send_photo(message.chat.id, qr, caption=cap, reply_markup=get_back_btn(), parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_nap_bill, amount)

def process_nap_bill(message, amount):
    if message.content_type == 'photo':
        user = get_user(message.from_user.id)
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"📩 **BILL NẠP**\n👤 STT: #{user['stt']}\n💰 Số: {amount:,}đ\nLệnh: `/add {user['stt']} {format_money(amount)}`")
        
        # Gửi lại menu chính sau khi nạp xong
        text, markup = get_main_menu(user)
        bot.reply_to(message, "✅ Đã gửi bill cho Admin duyệt!")
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')
    else:
        text, markup = get_main_menu(get_user(message.from_user.id))
        bot.reply_to(message, "❌ Bạn không gửi ảnh Bill. Đã hủy yêu cầu nạp!")
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

def process_rut_info(message, old_msg_id):
    bot.delete_message(message.chat.id, message.message_id)
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
    bot.delete_message(message.chat.id, message.message_id)
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

# --- PHẦN ADMIN GIỮ NGUYÊN BÊN DƯỚI (Bạn nhớ chèn lại phần code Admin ẩn /admin từ phiên bản trước vào đây nhé) ---

# ... (Paste phần code @bot.message_handler(commands=['admin']) ở đây) ...

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    print(f"Bot Tai Xiu is running on Port {PORT}...")
    bot.infinity_polling()
