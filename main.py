import os
import time
import random
import threading
import sys
import uuid
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

# Khởi tạo Server Flask
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
history_col = db['history']
deposits_col = db['deposits']
withdraws_col = db['withdraws']

# --- HÀM TIỆN ÍCH (UTILS) ---
cooldowns = {}
temp_data = {}

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
        # THÊM: total_deposited (tổng nạp) và total_bet (tổng cược) để tính vòng cược
        user = {'_id': user_id, 'stt': get_next_stt(), 'username': (username or "user").lower(),
                'balance': 5000, 'vip': 0, 'is_banned': False, 'joined_at': datetime.now(),
                'total_deposited': 0, 'total_bet': 0}
        users_col.insert_one(user)
    return user

def add_history(d1, d2, d3, total, result):
    history_col.insert_one({'time': datetime.now(), 'd1': d1, 'd2': d2, 'd3': d3, 'total': total, 'result': result})

# ==========================================
# CÁC MENU GIAO DIỆN CHUẨN (UI COMPONENTS)
# ==========================================

def get_back_btn():
    return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))

def get_back_admin_btn():
    return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ MENU ADMIN", callback_data="adm_main"))

def get_main_menu(user):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🎲 CHƠI & SOI CẦU", callback_data="u_play_menu"))
    kb.row(
        types.InlineKeyboardButton("💳 NẠP TIỀN", callback_data="deposit_menu"),
        types.InlineKeyboardButton("💸 RÚT TIỀN", callback_data="withdraw_menu")
    )
    kb.row(
        types.InlineKeyboardButton("🎁 NHẬP CODE", callback_data="u_code"),
        types.InlineKeyboardButton("👤 CÁ NHÂN", callback_data="u_me")
    )
    
    text = (
        "💎 ════════════════════ 💎\n"
        "      🎰 **TAI XIU CASINO PRO** 🎰\n"
        "⚡️ Uy Tín • Nhanh Chóng • Tự Động ⚡️\n"
        "💎 ════════════════════ 💎\n\n"
        "👤 **THÔNG TIN CỦA BẠN:**\n"
        f"├ 🆔 ID Nạp: `{user['_id']}`\n"
        f"├ 🔢 STT: `#{user['stt']}` | 🌟 VIP: `{user['vip']}`\n"
        f"└ 💰 Số dư:  **{format_money(user['balance'])}**\n\n"
        "👇 *Vui lòng chọn thao tác bên dưới:*"
    )
    return text, kb

def get_play_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔵 ĐẶT TÀI", callback_data="u_play_tai"),
        types.InlineKeyboardButton("🔴 ĐẶT XỈU", callback_data="u_play_xiu")
    )
    kb.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    
    recent = list(history_col.find().sort('_id', -1).limit(15))
    trend_text = " - ".join(["🔵" if r['result']=="TÀI" else "🔴" for r in recent[::-1]]) if recent else "Chưa có cầu!"
        
    text = (
        "📊 **BÀN CƯỢC & SOI CẦU**\n"
        "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        f"Bóng: {trend_text}\n"
        "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
        "🎲 **CHỌN CỬA BẠN MUỐN ĐẶT:**"
    )
    return text, kb

def get_deposit_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("10k", callback_data="nap_10000"),
        types.InlineKeyboardButton("20k", callback_data="nap_20000"),
        types.InlineKeyboardButton("50k", callback_data="nap_50000"),
        types.InlineKeyboardButton("100k", callback_data="nap_100000"),
        types.InlineKeyboardButton("200k", callback_data="nap_200000"),
        types.InlineKeyboardButton("500k", callback_data="nap_500000")
    )
    kb.add(types.InlineKeyboardButton("✍️ SỐ TIỀN KHÁC", callback_data="nap_custom"))
    kb.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    return kb

def get_withdraw_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("100k", callback_data="rut_100000"),
        types.InlineKeyboardButton("200k", callback_data="rut_200000"),
        types.InlineKeyboardButton("500k", callback_data="rut_500000"),
        types.InlineKeyboardButton("1M", callback_data="rut_1000000"),
        types.InlineKeyboardButton("2M", callback_data="rut_2000000"),
        types.InlineKeyboardButton("5M", callback_data="rut_5000000")
    )
    kb.add(types.InlineKeyboardButton("✍️ SỐ TIỀN KHÁC", callback_data="rut_custom"))
    kb.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    return kb

def get_admin_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("💰 CỘNG TIỀN", callback_data="adm_add"),
        types.InlineKeyboardButton("➖ TRỪ TIỀN", callback_data="adm_sub")
    )
    kb.add(
        types.InlineKeyboardButton("🎁 TẠO CODE", callback_data="adm_code"),
        types.InlineKeyboardButton("📢 THÔNG BÁO", callback_data="adm_bc")
    )
    kb.add(
        types.InlineKeyboardButton("🌟 SET VIP", callback_data="adm_vip"),
        types.InlineKeyboardButton("🚫 BAN/UNBAN", callback_data="adm_ban")
    )
    return "⚙ **BẢNG ĐIỀU KHIỂN DÀNH CHO ADMIN**\n\n👇 Hãy chọn chức năng bên dưới:", kb

# ==========================================
# LỆNH NGƯỜI CHƠI & XỬ LÝ CALLBACKS
# ==========================================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if is_spam(message.from_user.id): return
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user = get_user(message.from_user.id, message.from_user.username)
    if user['is_banned']: return bot.reply_to(message, "⛔ Tài khoản đã bị khóa.")
    
    text, markup = get_main_menu(user)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('u_') or call.data.endswith('_menu'))
def handle_user_menus(call):
    if is_spam(call.from_user.id): return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    user = get_user(call.from_user.id)
    if user['is_banned']: return
    
    act = call.data
    m = call.message
    uid = call.from_user.id
    
    try:
        if act == "u_main":
            text, markup = get_main_menu(user)
            if m.content_type == 'photo':
                bot.delete_message(m.chat.id, m.message_id)
                bot.send_message(m.chat.id, text, reply_markup=markup, parse_mode='Markdown')
            else:
                bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
            
        elif act == "u_me":
            rate = 1.89 + (user['vip'] * 0.1)
            total_dep = user.get('total_deposited', 0)
            total_bet = user.get('total_bet', 0)
            
            text = (
                f"🔰 **CÁ NHÂN**\n\n"
                f"👤 Tên: @{user['username']}\n"
                f"🔢 STT: `#{user['stt']}`\n"
                f"💰 Dư: **{format_money(user['balance'])}**\n"
                f"🌟 VIP: `{user['vip']}` (Tỉ lệ ăn: x{rate:.2f})\n"
                "〰️〰️〰️〰️〰️〰️〰️〰️\n"
                f"💵 Tổng Nạp: **{format_money(total_dep)}**\n"
                f"🎲 Tổng Cược: **{format_money(total_bet)}**"
            )
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            
        elif act == "u_play_menu":
            text, markup = get_play_menu()
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
            
        elif act in ["u_play_tai", "u_play_xiu"]:
            side = "TÀI" if act == "u_play_tai" else "XỈU"
            temp_data[uid] = {'action': 'play', 'side': side}
            msg = bot.edit_message_text(f"👇 Bạn đang chọn: **{side}**.\n\n⌨️ **NHẬP SỐ TIỀN MUỐN CƯỢC VÀO KHUNG CHAT:**\n*(VD: 10k, 50k)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_play_amount, m.message_id)

        elif act == "deposit_menu":
            bot.edit_message_text("💳 **HỆ THỐNG NẠP TIỀN TỰ ĐỘNG**\n\n👉 Chọn số tiền bạn muốn nạp vào tài khoản:", m.chat.id, m.message_id, reply_markup=get_deposit_kb(), parse_mode='Markdown')

        # --- LOGIC TÍNH TOÁN VÒNG CƯỢC 150% TRƯỚC KHI RÚT ---
        elif act == "withdraw_menu":
            total_dep = user.get('total_deposited', 0)
            total_bet = user.get('total_bet', 0)
            req_bet = int(total_dep * 1.5) # Yêu cầu cược = 150% nạp
            
            if total_bet < req_bet:
                rem_bet = req_bet - total_bet
                text_error = (
                    f"💸 **HỆ THỐNG RÚT TIỀN**\n\n"
                    f"❌ **BẠN CHƯA ĐỦ ĐIỀU KIỆN RÚT TIỀN!**\n"
                    f"*(Yêu cầu phải đạt vòng cược 150% tổng nạp)*\n\n"
                    f"💵 Tổng tiền đã nạp: **{format_money(total_dep)}**\n"
                    f"🎲 Vòng cược hiện tại: **{format_money(total_bet)}** / **{format_money(req_bet)}**\n\n"
                    f"👉 **Còn thiếu:** Bạn cần cược thêm **{format_money(rem_bet)}** nữa để mở khóa tính năng rút tiền!"
                )
                bot.edit_message_text(text_error, m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            else:
                bot.edit_message_text(f"💸 **HỆ THỐNG RÚT TIỀN**\nSố dư khả dụng: **{format_money(user['balance'])}**\n\n👉 Chọn số tiền muốn rút (Tối thiểu 100k):", m.chat.id, m.message_id, reply_markup=get_withdraw_kb(), parse_mode='Markdown')

        elif act == "u_code":
            msg = bot.edit_message_text("🎁 **NHẬP GIFTCODE**\n\n⌨️ **Hãy nhập mã code của bạn:**", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_giftcode, m.message_id)
            
    except: pass 

# ==========================================
# XỬ LÝ CHƠI GAME & CỘNG VÒNG CƯỢC
# ==========================================

def process_play_amount(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id) 
    except: pass
    user = get_user(message.from_user.id)
    bet = parse_money(message.text)
    side = temp_data.get(message.from_user.id, {}).get('side', 'TÀI')
    
    if bet < 1000 or bet > user['balance']:
        bot.edit_message_text(f"❌ Tiền cược không hợp lệ! (Dư: {format_money(user['balance'])})\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_play_amount, old_msg_id)
        return

    # Trừ tiền balance VÀ CỘNG tiền cược vào total_bet
    users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': -bet, 'total_bet': bet}})
    try: bot.delete_message(message.chat.id, old_msg_id)
    except: pass

    d1_msg = bot.send_dice(message.chat.id, emoji='🎲')
    d2_msg = bot.send_dice(message.chat.id, emoji='🎲')
    d3_msg = bot.send_dice(message.chat.id, emoji='🎲')
    time.sleep(3.5)
    
    d1, d2, d3 = d1_msg.dice.value, d2_msg.dice.value, d3_msg.dice.value
    total = d1 + d2 + d3
    res_side = "TÀI" if total >= 11 else "XỈU"
    rate = 1.89 + (user['vip'] * 0.1)
    
    add_history(d1, d2, d3, total, res_side)
    
    if side == res_side:
        win = int(bet * rate)
        users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': win}})
        result = f"✅ **BẠN THẮNG** | +{format_money(win)}"
    else:
        result = f"❌ **BẠN THUA** | -{format_money(bet)}"
        
    final_bal = users_col.find_one({'_id': user['_id']})['balance']
    text, markup = get_play_menu()
    bot.send_message(message.chat.id, f"🔥 **KẾT QUẢ: {d1}-{d2}-{d3}** ➜ **{total} {res_side}**\nBạn đặt: {side} {format_money(bet)}\n{result}\n💰 Số dư: `{format_money(final_bal)}`\n\n{text}", reply_markup=markup, parse_mode='Markdown')

def process_giftcode(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    user = get_user(message.from_user.id)
    c_name = message.text.strip().upper()
    code = codes_col.find_one({'_id': c_name})
    
    if not code or code['uses_left'] <= 0 or user['_id'] in code['used_by']:
        bot.edit_message_text("❌ Mã sai hoặc hết lượt!\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_giftcode, old_msg_id)
        return
        
    users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': code['reward']}})
    codes_col.update_one({'_id': c_name}, {'$inc': {'uses_left': -1}, '$push': {'used_by': user['_id']}})
    bot.edit_message_text(f"🎁 **NHẬP CODE THÀNH CÔNG!**\nNhận được: **{format_money(code['reward'])}**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')

# ==========================================
# NẠP TIỀN (DEPOSIT)
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('nap_') or call.data.startswith('canceldep_'))
def handle_deposit_calls(call):
    user = get_user(call.from_user.id)
    act = call.data
    m = call.message
    uid = call.from_user.id
    
    if act == "nap_custom":
        msg = bot.edit_message_text("⌨️ **NHẬP SỐ TIỀN MUỐN NẠP:**\n*(Min 10k, VD: 15k, 15000)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_nap_custom, m.message_id)
        
    elif act.startswith("nap_"):
        amt = int(act.split("_")[1])
        generate_deposit_qr(m, user, amt)
        
    elif act.startswith("canceldep_"):
        dep_id = act.split("_")[1]
        deposits_col.update_one({"_id": dep_id, "user_id": uid}, {"$set": {"status": "cancelled"}})
        try: bot.delete_message(m.chat.id, m.message_id)
        except: pass
        text, markup = get_main_menu(user)
        bot.send_message(m.chat.id, f"✅ Đã hủy đơn nạp.\n\n{text}", reply_markup=markup, parse_mode='Markdown')

def process_nap_custom(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    amount = parse_money(message.text)
    user = get_user(message.from_user.id)
    
    if amount < 10000:
        bot.edit_message_text("❌ Nạp tối thiểu 10k!\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_nap_custom, old_msg_id)
        return
    generate_deposit_qr(message, user, amount, old_msg_id)

def generate_deposit_qr(message, user, amt, msg_id_to_delete=None):
    if msg_id_to_delete:
        try: bot.delete_message(message.chat.id, msg_id_to_delete)
        except: pass
    else:
        try: bot.delete_message(message.chat.id, message.message_id)
        except: pass

    now_time = int(time.time())
    deposits_col.update_many({"user_id": user['_id'], "status": "pending", "expired_at": {"$lt": now_time}}, {"$set": {"status": "cancelled"}})
    
    if deposits_col.find_one({"user_id": user['_id'], "status": "pending"}):
        bot.send_message(message.chat.id, "❌ Bạn đang có 1 đơn nạp chưa hoàn thành. Hãy hủy nó trước!", reply_markup=get_back_btn())
        return

    tran_code = str(uuid.uuid4())[:6].upper()
    content = f"NAP {user['_id']} {tran_code}"
    content_encoded = content.replace(' ', '%20')
    name_encoded = BANK_NAME.replace(' ', '%20')
    qr_url = f"https://img.vietqr.io/image/MB-{BANK_STK}-compact2.png?amount={amt}&addInfo={content_encoded}&accountName={name_encoded}"
    
    dep_id = str(uuid.uuid4())
    deposits_col.insert_one({"_id": dep_id, "user_id": user['_id'], "amount": amt, "content": content, "status": "pending", "expired_at": now_time + 600})

    cap = (
        f"💳 **YÊU CẦU CHUYỂN KHOẢN**\n\n"
        f"🏦 Ngân hàng: **MB Bank**\n"
        f"👤 Chủ tài khoản: **{BANK_NAME}**\n"
        f"🔢 Số tài khoản: `{BANK_STK}`\n"
        f"💵 Số tiền: **{format_money(amt)}**\n"
        f"📝 Nội dung CK: `{content}`\n\n"
        f"⚠️ **HƯỚNG DẪN:**\n"
        f"1. Quét mã QR ở trên.\n"
        f"2. Chuyển khoản xong, hãy **GỬI ẢNH BIÊN LAI** vào khung chat này để Admin duyệt!\n"
        f"⏳ Đơn sẽ tự hủy sau 10 phút."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ HỦY ĐƠN NẠP NÀY", callback_data=f"canceldep_{dep_id}"))
    markup.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    bot.send_photo(message.chat.id, photo=qr_url, caption=cap, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(content_types=['photo'])
def handle_bill_photo(message):
    uid = message.from_user.id
    dep = deposits_col.find_one({"user_id": uid, "status": "pending"})
    if not dep: return 
        
    deposits_col.update_one({"_id": dep['_id']}, {"$set": {"status": "reviewing", "bill_file_id": message.photo[-1].file_id}})

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ DUYỆT CỘNG", callback_data=f"admappr_{dep['_id']}"), 
        types.InlineKeyboardButton("❌ TỪ CHỐI", callback_data=f"admreje_{dep['_id']}")
    )
    user = get_user(uid)
    uname = f"@{user['username']}" if user.get('username') else "Ẩn danh"
    
    cap = (
        f"💳 **CÓ BILL NẠP MỚI**\n\n"
        f"👤 User: `{uid}` ({uname})\n"
        f"💵 Tiền báo nạp: **{format_money(dep['amount'])}**\n"
        f"🏷 Nội dung CK: `{dep['content']}`"
    )
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=cap, parse_mode="Markdown", reply_markup=kb)
    
    bot.reply_to(message, "✅ **Đã gửi biên lai cho Admin!** Hệ thống sẽ cộng tiền sớm nhất.", parse_mode="Markdown")
    text, menu = get_main_menu(user)
    bot.send_message(message.chat.id, text, reply_markup=menu, parse_mode='Markdown')

# ==========================================
# RÚT TIỀN (WITHDRAW) - UPDATE MIN 100K & VÒNG CƯỢC
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('rut_'))
def handle_withdraw_calls(call):
    user = get_user(call.from_user.id)
    act = call.data
    m = call.message
    uid = call.from_user.id
    
    # Kẻ thù hack API chèn lệnh rút: Phải double-check lại vòng cược ở đây
    total_dep = user.get('total_deposited', 0)
    total_bet = user.get('total_bet', 0)
    req_bet = int(total_dep * 1.5)
    
    if total_bet < req_bet:
        return bot.answer_callback_query(call.id, f"❌ Chưa đủ điều kiện! Bạn cần cược thêm {format_money(req_bet - total_bet)}", show_alert=True)
    
    if act == "rut_custom":
        msg = bot.edit_message_text(f"⌨️ **NHẬP SỐ TIỀN MUỐN RÚT:**\n*(Min 100k, Dư: {format_money(user['balance'])})*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_rut_custom, m.message_id)
        
    elif act.startswith("rut_"):
        amt = int(act.split("_")[1])
        if amt < 100000 or amt > user['balance']:
            return bot.answer_callback_query(call.id, "❌ Bạn không đủ số dư để rút mức này!", show_alert=True)
            
        temp_data[uid] = {'action': 'rut', 'amount': amt}
        msg = bot.edit_message_text(f"💸 Đang rút: **{format_money(amt)}**\n\n⌨️ **NHẬP THÔNG TIN NHẬN TIỀN:**\n*(VD: MB 12345 Nguyen Van A)*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_rut_info, m.message_id)

def process_rut_custom(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    amt = parse_money(message.text)
    user = get_user(message.from_user.id)
    
    # Kiểm tra vòng cược 1 lần nữa cho an toàn
    total_dep = user.get('total_deposited', 0)
    total_bet = user.get('total_bet', 0)
    req_bet = int(total_dep * 1.5)
    
    if total_bet < req_bet:
        bot.edit_message_text(f"❌ Bạn cần cược thêm {format_money(req_bet - total_bet)} nữa để mở khóa rút tiền!", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        return

    if amt < 100000 or amt > user['balance']:
        bot.edit_message_text(f"❌ Số tiền không hợp lệ! (Min 100k, Dư: {format_money(user['balance'])})\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_custom, old_msg_id)
        return
        
    temp_data[user['_id']] = {'action': 'rut', 'amount': amt}
    bot.edit_message_text(f"💸 Đang rút: **{format_money(amt)}**\n\n⌨️ **NHẬP THÔNG TIN NHẬN TIỀN:**\n*(VD: MB 12345 Nguyen Van A)*", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_info, old_msg_id)

def process_rut_info(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    uid = message.from_user.id
    user = get_user(uid)
    amt = temp_data.get(uid, {}).get('amount', 0)
    info = message.text.strip()
    
    if amt < 100000 or amt > user['balance']:
        text, markup = get_main_menu(user)
        bot.edit_message_text(f"❌ Có lỗi xảy ra. Đã hủy lệnh rút!\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')
        return

    users_col.update_one({'_id': uid}, {'$inc': {'balance': -amt}})
    w_id = str(uuid.uuid4())
    withdraws_col.insert_one({"_id": w_id, "user_id": uid, "amount": amt, "info": info, "status": "pending", "time": datetime.now()})
    
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ ĐÃ CHUYỂN TIỀN (DUYỆT)", callback_data=f"admw_appr_{w_id}"),
        types.InlineKeyboardButton("❌ TỪ CHỐI (HOÀN TIỀN)", callback_data=f"admw_reje_{w_id}")
    )
    admin_text = f"💸 **YÊU CẦU RÚT TIỀN**\n👤 STT: `#{user['stt']}` (ID: `{uid}`)\n💰 Số tiền: **{format_money(amt)}** ({amt:,} VNĐ)\n💳 Thông tin CK: `{info}`"
    bot.send_message(ADMIN_ID, admin_text, reply_markup=kb, parse_mode='Markdown')
    
    text, m_markup = get_main_menu(get_user(uid))
    bot.edit_message_text(f"✅ Đã gửi yêu cầu rút **{format_money(amt)}** tới hệ thống! Đang chờ Admin xử lý.\n\n{text}", message.chat.id, old_msg_id, reply_markup=m_markup, parse_mode='Markdown')

# ==========================================
# ADMIN MENU (BẢNG QUẢN TRỊ TƯƠNG TÁC)
# ==========================================

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    text, markup = get_admin_menu()
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm'))
def handle_admin_actions(call):
    if call.from_user.id != ADMIN_ID: return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    act = call.data
    m = call.message
    
    # --- ADMIN XỬ LÝ BILL NẠP ---
    if act.startswith("admappr_"):
        dep_id = act.split("_")[1]
        dep = deposits_col.find_one({"_id": dep_id})
        if dep and dep['status'] == 'reviewing':
            # QUAN TRỌNG: Cộng cả balance VÀ total_deposited
            users_col.update_one({'_id': dep['user_id']}, {'$inc': {'balance': dep['amount'], 'total_deposited': dep['amount']}})
            deposits_col.update_one({'_id': dep_id}, {'$set': {'status': 'approved'}})
            bot.edit_message_caption(f"✅ **ĐÃ DUYỆT CỘNG {format_money(dep['amount'])}**\n\n" + m.caption, m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(dep['user_id'], f"🎉 **Ting Ting!**\nAdmin đã duyệt nạp **{format_money(dep['amount'])}**! Tiền đã được cập nhật vào ví.", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)
            
    elif act.startswith("admreje_"):
        dep_id = act.split("_")[1]
        dep = deposits_col.find_one({"_id": dep_id})
        if dep and dep['status'] == 'reviewing':
            deposits_col.update_one({'_id': dep_id}, {'$set': {'status': 'rejected'}})
            bot.edit_message_caption(f"❌ **ĐÃ TỪ CHỐI BILL**\n\n" + m.caption, m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(dep['user_id'], f"⚠️ **NẠP THẤT BẠI**\nBiên lai nạp **{format_money(dep['amount'])}** của bạn bị từ chối!", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)

    # --- ADMIN XỬ LÝ ĐƠN RÚT ---
    elif act.startswith("admw_appr_"):
        w_id = act.split("_")[2]
        w = withdraws_col.find_one({"_id": w_id})
        if w and w['status'] == 'pending':
            withdraws_col.update_one({'_id': w_id}, {'$set': {'status': 'approved'}})
            bot.edit_message_text(f"✅ **ĐÃ CHUYỂN TIỀN THÀNH CÔNG**\n\n{m.text}", m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(w['user_id'], f"🎉 **RÚT THÀNH CÔNG**\nYêu cầu rút **{format_money(w['amount'])}** đã được xử lý. Tiền đã về tài khoản ngân hàng của bạn!", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)

    elif act.startswith("admw_reje_"):
        w_id = act.split("_")[2]
        w = withdraws_col.find_one({"_id": w_id})
        if w and w['status'] == 'pending':
            withdraws_col.update_one({'_id': w_id}, {'$set': {'status': 'rejected'}})
            users_col.update_one({'_id': w['user_id']}, {'$inc': {'balance': w['amount']}}) # HOÀN TIỀN
            bot.edit_message_text(f"❌ **ĐÃ TỪ CHỐI VÀ HOÀN TIỀN**\n\n{m.text}", m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(w['user_id'], f"⚠️ **RÚT THẤT BẠI**\nYêu cầu rút **{format_money(w['amount'])}** bị từ chối. Số điểm đã được hoàn lại vào ví của bạn!", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)

    # --- CÁC NÚT MENU ADMIN ---
    try:
        if act == "adm_main":
            text, markup = get_admin_menu()
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
            
        elif act == "adm_add":
            msg = bot.edit_message_text("💰 **CỘNG TIỀN CHO KHÁCH**\n\n⌨️ Nhập theo cú pháp: `STT/ID SốTiền`\n*(VD: `1 50k`)*", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_money, m.message_id, True)
            
        elif act == "adm_sub":
            msg = bot.edit_message_text("➖ **TRỪ TIỀN KHÁCH**\n\n⌨️ Nhập theo cú pháp: `STT/ID SốTiền`\n*(VD: `1 10k`)*", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_money, m.message_id, False)
            
        elif act == "adm_code":
            msg = bot.edit_message_text("🎁 **TẠO MÃ GIFTCODE**\n\n⌨️ Nhập: `Mã Tiền Lượt`\n*(VD: `VIP100 100k 10`)*", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_code, m.message_id)
            
        elif act == "adm_bc":
            msg = bot.edit_message_text("📢 **THÔNG BÁO TOÀN SERVER**\n\n⌨️ Nhập nội dung thông báo:", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_bc, m.message_id)
            
        elif act == "adm_vip":
            msg = bot.edit_message_text("🌟 **CẤP VIP CHO KHÁCH**\n\n⌨️ Nhập: `STT/ID CấpVIP`\n*(VD: `1 2`)*", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_vip, m.message_id)
            
        elif act == "adm_ban":
            msg = bot.edit_message_text("🚫 **KHÓA TÀI KHOẢN**\n\n⌨️ Nhập: `STT/ID ban` hoặc `unban`\n*(VD: `1 ban`)*", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_ban, m.message_id)
    except: pass

def process_adm_money(message, old_msg_id, is_add):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        ref, money = message.text.split()
        amt = parse_money(money)
        u = find_user(ref)
        if u:
            final_amt = amt if is_add else -amt
            users_col.update_one({'_id': u['_id']}, {'$inc': {'balance': final_amt}})
            action_text = "CỘNG" if is_add else "TRỪ"
            
            if is_add:
                try: bot.send_message(u['_id'], f"🔔 Admin đã gửi tặng **{format_money(amt)}** cho bạn!")
                except: pass
                
            text, markup = get_admin_menu()
            bot.edit_message_text(f"✅ Đã **{action_text} {format_money(amt)}** cho #{u['stt']}\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')
        else: raise Exception
    except:
        bot.edit_message_text("❌ Lỗi cú pháp!\n⌨️ Nhập lại (VD: `1 50k`):", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_money, old_msg_id, is_add)

def process_adm_code(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        n, m, l = message.text.split()
        amt = parse_money(m)
        codes_col.update_one({'_id': n.upper()}, {'$set': {'reward': amt, 'uses_left': int(l), 'used_by': []}}, upsert=True)
        text, markup = get_admin_menu()
        bot.edit_message_text(f"🎁 Code `{n.upper()}`: {format_money(amt)} ({l} lượt) đã tạo!\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')
    except:
        bot.edit_message_text("❌ Lỗi cú pháp!\n⌨️ Nhập lại (VD: `KM100 100k 10`):", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_code, old_msg_id)

def process_adm_bc(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    users = users_col.find({}, {'_id': 1})
    count = 0
    for u in users:
        try:
            bot.send_message(u['_id'], f"📢 **THÔNG BÁO TỪ HỆ THỐNG**\n\n{message.text}", parse_mode='Markdown')
            count += 1
            time.sleep(0.04)
        except: pass
    text, markup = get_admin_menu()
    bot.edit_message_text(f"✅ Đã gửi thông báo tới {count} người.\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')

def process_adm_vip(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        ref, lv = message.text.split()
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$set': {'vip': int(lv)}})
            text, markup = get_admin_menu()
            bot.edit_message_text(f"✅ Đã set VIP {lv} cho #{u['stt']}\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')
        else: raise Exception
    except:
        bot.edit_message_text("❌ Lỗi!\n⌨️ Nhập lại (VD: `1 2`):", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_vip, old_msg_id)

def process_adm_ban(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        ref, act = message.text.split()
        is_ban = True if act.lower() == 'ban' else False
        u = find_user(ref)
        if u:
            users_col.update_one({'_id': u['_id']}, {'$set': {'is_banned': is_ban}})
            text, markup = get_admin_menu()
            bot.edit_message_text(f"✅ Đã {'Khóa' if is_ban else 'Mở'} #{u['stt']}\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')
        else: raise Exception
    except:
        bot.edit_message_text("❌ Lỗi!\n⌨️ Nhập lại (VD: `1 ban`):", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_ban, old_msg_id)

# ================= AUTO HỦY ĐƠN NẠP NGẦM =================
def auto_cancel_deposits():
    while True:
        try:
            now_time = int(time.time())
            deposits_col.update_many({"status": "pending", "expired_at": {"$lt": now_time}}, {"$set": {"status": "cancelled"}})
        except: pass
        time.sleep(60)

# --- CHẠY SERVER PORT & BOT ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=auto_cancel_deposits, daemon=True).start()
    print(f"Bot Tai Xiu is running on Port {PORT}...")
    bot.infinity_polling()
