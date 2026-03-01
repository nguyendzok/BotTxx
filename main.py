import os
import time
import random
import threading
import sys
import uuid
from io import BytesIO 
import telebot
from telebot import types
from telebot.handler_backends import BaseMiddleware
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

# --- CÁC BẢNG DỮ LIỆU (COLLECTIONS) ---
users_col = db['users']
counters_col = db['counters']
codes_col = db['codes']
history_col = db['history']
deposits_col = db['deposits']
withdraws_col = db['withdraws']
transactions_col = db['transactions'] 

# ==========================================
# MIDDLEWARE: AUTO-SAVE NGƯỜI DÙNG
# ==========================================
class GlobalDatabaseMiddleware(BaseMiddleware):
    def __init__(self):
        self.update_types = ['message', 'callback_query']
        
    def pre_process(self, call_or_msg, data):
        user_obj = call_or_msg.from_user
        if user_obj and not user_obj.is_bot:
            get_user(user_obj.id, user_obj.username)
                
    def post_process(self, message, data, exception): pass

bot.setup_middleware(GlobalDatabaseMiddleware())

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
        uname = (username or "user").lower()
        user = {'_id': user_id, 'stt': get_next_stt(), 'username': uname,
                'balance': 5000, 'vip': 0, 'is_banned': False, 'joined_at': datetime.now(),
                'total_deposited': 0, 'total_bet': 0, 'total_won': 0}
        users_col.insert_one(user)
        log_transaction(user_id, 5000, "Tặng tiền tân thủ")
    elif username and user.get('username') != username.lower():
        users_col.update_one({'_id': user_id}, {'$set': {'username': username.lower()}})
        user['username'] = username.lower()
    return user

def find_user(ref):
    ref_str = str(ref).strip().lower().replace('@', '')
    if ref_str.isdigit():
        num = int(ref_str)
        return users_col.find_one({'$or': [{'stt': num}, {'_id': num}]})
    return users_col.find_one({'username': ref_str})

def add_history(d1, d2, d3, total, result):
    history_col.insert_one({'time': datetime.now(), 'd1': d1, 'd2': d2, 'd3': d3, 'total': total, 'result': result})

def log_transaction(uid, amount, reason):
    transactions_col.insert_one({"uid": uid, "amount": amount, "reason": reason, "time": datetime.now()})

# ==========================================
# CÁC MENU GIAO DIỆN CHUẨN
# ==========================================

def get_back_btn(): return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
def get_back_admin_btn(): return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ MENU ADMIN", callback_data="adm_main"))

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
    kb.row(
        types.InlineKeyboardButton("🌟 ĐẶC QUYỀN VIP", callback_data="u_vip"),
        types.InlineKeyboardButton("👨‍💻 HỖ TRỢ", url="https://t.me/chamayluon")
    )
    
    uname = user.get('username', 'user')
    text = (
        "💎 ════════════════════ 💎\n"
        "      🎰 **TAI XIU CASINO PRO** 🎰\n"
        "⚡️ Uy Tín • Nhanh Chóng • Tự Động ⚡️\n"
        "💎 ════════════════════ 💎\n\n"
        "👤 **THÔNG TIN CỦA BẠN:**\n"
        f"├ 👤 Khách hàng: `@{uname}`\n"
        f"├ 🆔 ID Nạp: `{user['_id']}`\n"
        f"├ 🔢 STT: `#{user['stt']}` | 🌟 VIP: `{user['vip']}`\n"
        f"└ 💰 Số dư:  **{format_money(user['balance'])}**\n\n"
        "👇 *Vui lòng chọn thao tác bên dưới:*"
    )
    return text, kb

def get_play_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🔵 ĐẶT TÀI", callback_data="u_play_tai"), types.InlineKeyboardButton("🔴 ĐẶT XỈU", callback_data="u_play_xiu"))
    kb.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    
    recent = list(history_col.find().sort('_id', -1).limit(15))
    trend_text = " - ".join(["🔵" if r['result']=="TÀI" else "🔴" for r in recent[::-1]]) if recent else "Chưa có cầu!"
        
    text = (
        "📊 **BÀN CƯỢC & SOI CẦU**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        f"Bóng: {trend_text}\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n🎲 **CHỌN CỬA BẠN MUỐN ĐẶT:**"
    )
    return text, kb

def get_bet_amount_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("5k", callback_data="bet_5000"), types.InlineKeyboardButton("10k", callback_data="bet_10000"), types.InlineKeyboardButton("20k", callback_data="bet_20000"),
        types.InlineKeyboardButton("50k", callback_data="bet_50000"), types.InlineKeyboardButton("100k", callback_data="bet_100000"), types.InlineKeyboardButton("500k", callback_data="bet_500000")
    )
    kb.add(types.InlineKeyboardButton("🔥 TẤT TAY (ALL IN)", callback_data="bet_allin"))
    kb.add(types.InlineKeyboardButton("✍️ SỐ TIỀN KHÁC", callback_data="bet_custom"))
    kb.add(types.InlineKeyboardButton("🔙 CHỌN LẠI CỬA", callback_data="u_play_menu"))
    return kb

def get_deposit_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(types.InlineKeyboardButton("10k", callback_data="nap_10000"), types.InlineKeyboardButton("20k", callback_data="nap_20000"), types.InlineKeyboardButton("50k", callback_data="nap_50000"),
           types.InlineKeyboardButton("100k", callback_data="nap_100000"), types.InlineKeyboardButton("200k", callback_data="nap_200000"), types.InlineKeyboardButton("500k", callback_data="nap_500000"))
    kb.add(types.InlineKeyboardButton("✍️ SỐ TIỀN KHÁC", callback_data="nap_custom"))
    kb.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    return kb

def get_withdraw_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(types.InlineKeyboardButton("200k", callback_data="rut_200000"), types.InlineKeyboardButton("500k", callback_data="rut_500000"), types.InlineKeyboardButton("1M", callback_data="rut_1000000"),
           types.InlineKeyboardButton("2M", callback_data="rut_2000000"), types.InlineKeyboardButton("5M", callback_data="rut_5000000"), types.InlineKeyboardButton("10M", callback_data="rut_10000000"))
    kb.add(types.InlineKeyboardButton("✍️ SỐ TIỀN KHÁC", callback_data="rut_custom"))
    kb.add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    return kb

def get_admin_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("💰 CỘNG TRỪ TIỀN", callback_data="adm_money_step1"), types.InlineKeyboardButton("🎁 QUẢN LÝ CODE", callback_data="adm_code"))
    kb.add(types.InlineKeyboardButton("👥 QUẢN LÝ USER", callback_data="adm_mgr"), types.InlineKeyboardButton("📢 THÔNG BÁO", callback_data="adm_bc"))
    kb.add(types.InlineKeyboardButton("🌟 SET VIP", callback_data="adm_vip"), types.InlineKeyboardButton("🚫 BAN/UNBAN", callback_data="adm_ban"))
    return "⚙ **BẢNG ĐIỀU KHIỂN DÀNH CHO ADMIN**\n\n👇 Hãy chọn chức năng bên dưới:", kb

# ==========================================
# LỆNH NGƯỜI CHƠI & XỬ LÝ CALLBACKS
# ==========================================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if is_spam(message.from_user.id): return
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user = get_user(message.from_user.id) 
    if user.get('is_banned'): return bot.reply_to(message, "⛔ Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Admin!")
    
    text, markup = get_main_menu(user)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('u_') or call.data.endswith('_menu'))
def handle_user_menus(call):
    if is_spam(call.from_user.id): return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    user = get_user(call.from_user.id)
    if user.get('is_banned'): return bot.answer_callback_query(call.id, "⛔ Tài khoản của bạn đã bị khóa!", show_alert=True)
    
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
            rate = 1.85 + (user['vip'] * 0.05)
            total_dep = user.get('total_deposited', 0)
            total_bet = user.get('total_bet', 0)
            total_won = user.get('total_won', 0)
            uname = user.get('username', 'user')
            text = (
                f"🔰 **CÁ NHÂN**\n\n👤 Tên: `@{uname}`\n🔢 STT: `#{user['stt']}`\n💰 Dư: **{format_money(user['balance'])}**\n🌟 VIP: `{user['vip']}` (Tỉ lệ ăn: x{rate:.2f})\n"
                "〰️〰️〰️〰️〰️〰️〰️〰️\n"
                f"💵 Tổng Nạp: **{format_money(total_dep)}**\n🎲 Tổng Cược: **{format_money(total_bet)}**\n🏆 Tổng Thắng: **{format_money(total_won)}**"
            )
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')

        elif act == "u_vip":
            total_dep = user.get('total_deposited', 0)
            current_vip = user.get('vip', 0)
            new_vip = 0
            if total_dep >= 3000000: new_vip = 5
            elif total_dep >= 1500000: new_vip = 4
            elif total_dep >= 500000: new_vip = 3
            elif total_dep >= 250000: new_vip = 2
            elif total_dep >= 100000: new_vip = 1
            if new_vip > current_vip:
                current_vip = new_vip
                users_col.update_one({'_id': uid}, {'$set': {'vip': current_vip}})
            rate = 1.85 + (current_vip * 0.05)
            next_vip_text = ""
            if current_vip < 5:
                thresholds = {1: 100000, 2: 250000, 3: 500000, 4: 1500000, 5: 3000000}
                next_tier = current_vip + 1
                need = thresholds[next_tier] - total_dep
                next_vip_text = f"🚀 Nạp thêm **{format_money(need)}** để lên **VIP {next_tier}** (Tỉ lệ x{1.85 + next_tier*0.05:.2f})"
            else:
                next_vip_text = "🎉 BẠN ĐÃ ĐẠT CẤP VIP TỐI ĐA!"
            text = (
                f"🌟 **HỆ THỐNG ĐẶC QUYỀN VIP** 🌟\n\n👤 Cấp VIP hiện tại: **VIP {current_vip}**\n💵 Tổng nạp tích lũy: **{format_money(total_dep)}**\n🎲 Tỉ lệ ăn của bạn: **x{rate:.2f}**\n\n"
                f"〰️〰️〰️〰️〰️〰️〰️〰️〰️\n📜 **BẢNG MỐC VIP & TỈ LỆ ĂN:**\n• VIP 0 (Dưới 100k) ➜ x1.85\n• VIP 1 (Nạp 100k) ➜ x1.90\n• VIP 2 (Nạp 250k) ➜ x1.95\n"
                f"• VIP 3 (Nạp 500k) ➜ x2.00\n• VIP 4 (Nạp 1.5M) ➜ x2.05\n• VIP 5 (Nạp 3.0M+) ➜ x2.10\n\n{next_vip_text}"
            )
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            
        elif act == "u_play_menu":
            text, markup = get_play_menu()
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
            
        elif act in ["u_play_tai", "u_play_xiu"]:
            side = "TÀI" if act == "u_play_tai" else "XỈU"
            if uid not in temp_data: temp_data[uid] = {}
            temp_data[uid]['side'] = side
            bot.edit_message_text(f"👇 Bạn đang chọn cửa: **{side}**.\n\n👉 **VUI LÒNG CHỌN SỐ TIỀN CƯỢC:**", m.chat.id, m.message_id, reply_markup=get_bet_amount_kb(), parse_mode='Markdown')

        elif act == "deposit_menu":
            bot.edit_message_text("💳 **HỆ THỐNG NẠP TIỀN TỰ ĐỘNG**\n\n👉 Chọn số tiền bạn muốn nạp vào tài khoản:", m.chat.id, m.message_id, reply_markup=get_deposit_kb(), parse_mode='Markdown')

        elif act == "withdraw_menu":
            total_dep = user.get('total_deposited', 0)
            total_bet = user.get('total_bet', 0)
            req_bet = int(total_dep * 1.5) 
            
            if total_bet < req_bet:
                bot.edit_message_text(f"💸 **HỆ THỐNG RÚT TIỀN**\n\n❌ **BẠN CHƯA ĐỦ ĐIỀU KIỆN RÚT TIỀN!**\n*(Yêu cầu phải đạt vòng cược 150% tổng nạp)*\n\n💵 Tổng nạp: **{format_money(total_dep)}**\n🎲 Vòng cược: **{format_money(total_bet)}** / **{format_money(req_bet)}**\n\n👉 **Còn thiếu:** Bạn cần cược thêm **{format_money(req_bet - total_bet)}** nữa!", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            else:
                bot.edit_message_text(f"💸 **HỆ THỐNG RÚT TIỀN**\nSố dư khả dụng: **{format_money(user['balance'])}**\n\n👉 Chọn số tiền muốn rút (Tối thiểu 200k):", m.chat.id, m.message_id, reply_markup=get_withdraw_kb(), parse_mode='Markdown')

        elif act == "u_code":
            msg = bot.edit_message_text("🎁 **NHẬP GIFTCODE**\n\n⌨️ **Hãy nhập mã code của bạn:**", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_giftcode, m.message_id)
    except: pass 

# ==========================================
# XỬ LÝ CHƠI GAME ĐẶT CƯỢC & XÓA XÚC XẮC
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('bet_'))
def handle_bet_buttons(call):
    uid = call.from_user.id
    user = get_user(uid)
    if user.get('is_banned'): return
    act = call.data
    m = call.message
    side = temp_data.get(uid, {}).get('side', 'TÀI')
    
    if act == "bet_custom":
        msg = bot.edit_message_text(f"👇 Bạn đang chọn: **{side}**.\n\n⌨️ **NHẬP SỐ TIỀN MUỐN CƯỢC:**\n*(VD: 15k, 25000)*", m.chat.id, m.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 CHỌN LẠI TIỀN", callback_data=f"u_play_{'tai' if side=='TÀI' else 'xiu'}")), parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_play_custom_amount, m.message_id)
    else:
        if act == "bet_allin":
            bet = user['balance']
            if bet <= 0: return bot.answer_callback_query(call.id, "❌ Bạn đã hết sạch tiền rồi!", show_alert=True)
        else:
            bet = int(act.split("_")[1])
        
        if bet < 1000 or bet > user['balance']:
            return bot.answer_callback_query(call.id, f"❌ Số dư không đủ! (Dư: {format_money(user['balance'])})", show_alert=True)
            
        execute_bet(m, uid, bet, side, m.message_id)

def process_play_custom_amount(message, old_msg_id):
    uid = message.from_user.id
    try: bot.delete_message(message.chat.id, message.message_id) 
    except: pass
    user = get_user(uid)
    bet = parse_money(message.text)
    side = temp_data.get(uid, {}).get('side', 'TÀI')
    
    if bet < 1000 or bet > user['balance']:
        bot.edit_message_text(f"❌ Tiền cược không hợp lệ! (Dư: {format_money(user['balance'])})\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 CHỌN LẠI TIỀN", callback_data=f"u_play_{'tai' if side=='TÀI' else 'xiu'}")), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_play_custom_amount, old_msg_id)
        return

    execute_bet(message, uid, bet, side, old_msg_id)

def execute_bet(message, uid, bet, side, old_msg_id):
    user = get_user(uid)
    
    users_col.update_one({'_id': uid}, {'$inc': {'balance': -bet, 'total_bet': bet}})
    log_transaction(uid, -bet, f"Cược {side}")
    
    try: bot.delete_message(message.chat.id, old_msg_id)
    except: pass

    old_dice_msgs = temp_data.get(uid, {}).get('dice_msgs', [])
    for msg_id in old_dice_msgs:
        try: bot.delete_message(message.chat.id, msg_id)
        except: pass

    d1_msg = bot.send_dice(message.chat.id, emoji='🎲')
    d2_msg = bot.send_dice(message.chat.id, emoji='🎲')
    d3_msg = bot.send_dice(message.chat.id, emoji='🎲')
    
    if uid not in temp_data: temp_data[uid] = {}
    temp_data[uid]['dice_msgs'] = [d1_msg.message_id, d2_msg.message_id, d3_msg.message_id]
    
    time.sleep(3.5)
    
    d1, d2, d3 = d1_msg.dice.value, d2_msg.dice.value, d3_msg.dice.value
    total = d1 + d2 + d3
    res_side = "TÀI" if total >= 11 else "XỈU"
    rate = round(1.85 + (user['vip'] * 0.05), 2)
    
    add_history(d1, d2, d3, total, res_side)
    
    if side == res_side:
        win = int(bet * rate)
        users_col.update_one({'_id': uid}, {'$inc': {'balance': win, 'total_won': win}})
        log_transaction(uid, win, f"Thắng cược {side}")
        result = f"✅ **BẠN THẮNG** | +{format_money(win)}"
    else:
        result = f"❌ **BẠN THUA** | -{format_money(bet)}"
        
    final_bal = users_col.find_one({'_id': uid})['balance']
    text, markup = get_play_menu()
    bot.send_message(message.chat.id, f"🔥 **KẾT QUẢ: {d1}-{d2}-{d3}** ➜ **{total} {res_side}**\nBạn đặt: {side} {format_money(bet)}\n{result}\n💰 Số dư: `{format_money(final_bal)}`\n\n{text}", reply_markup=markup, parse_mode='Markdown')

def process_giftcode(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    user = get_user(message.from_user.id)
    c_name = message.text.strip().upper()
    code = codes_col.find_one({'_id': c_name})
    
    if not code or code['uses_left'] <= 0 or user['_id'] in code['used_by']:
        bot.edit_message_text("❌ Mã sai, hết lượt hoặc bạn đã sử dụng!\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_giftcode, old_msg_id)
        return
        
    users_col.update_one({'_id': user['_id']}, {'$inc': {'balance': code['reward']}})
    codes_col.update_one({'_id': c_name}, {'$inc': {'uses_left': -1}, '$push': {'used_by': user['_id']}})
    log_transaction(user['_id'], code['reward'], f"Nhập Code {c_name}")
    bot.edit_message_text(f"🎁 **NHẬP CODE THÀNH CÔNG!**\nNhận được: **{format_money(code['reward'])}**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')

# ==========================================
# NẠP TIỀN & RÚT TIỀN 
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('nap_') or call.data.startswith('canceldep_'))
def handle_deposit_calls(call):
    user = get_user(call.from_user.id)
    if user.get('is_banned'): return
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
        return bot.send_message(message.chat.id, "❌ Bạn đang có 1 đơn nạp chưa hoàn thành. Hãy hủy nó trước!", reply_markup=get_back_btn())

    tran_code = str(uuid.uuid4())[:6].upper()
    content = f"NAP {user['_id']} {tran_code}"
    qr_url = f"https://img.vietqr.io/image/MB-{BANK_STK}-compact2.png?amount={amt}&addInfo={content.replace(' ', '%20')}&accountName={BANK_NAME.replace(' ', '%20')}"
    
    dep_id = str(uuid.uuid4())
    deposits_col.insert_one({"_id": dep_id, "user_id": user['_id'], "amount": amt, "content": content, "status": "pending", "expired_at": now_time + 600})

    cap = f"💳 **YÊU CẦU CHUYỂN KHOẢN**\n\n🏦 Ngân hàng: **MB Bank**\n👤 Chủ tài khoản: **{BANK_NAME}**\n🔢 Số tài khoản: `{BANK_STK}`\n💵 Số tiền: **{format_money(amt)}**\n📝 Nội dung CK: `{content}`\n\n⚠️ **HƯỚNG DẪN:**\n1. Quét mã QR.\n2. Gửi ảnh biên lai vào đây để duyệt.\n⏳ Tự hủy sau 10 phút."
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ HỦY ĐƠN NẠP NÀY", callback_data=f"canceldep_{dep_id}")).add(types.InlineKeyboardButton("🏠 VỀ TRANG CHỦ", callback_data="u_main"))
    bot.send_photo(message.chat.id, photo=qr_url, caption=cap, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(content_types=['photo'])
def handle_bill_photo(message):
    uid = message.from_user.id
    dep = deposits_col.find_one({"user_id": uid, "status": "pending"})
    if not dep: return 
        
    deposits_col.update_one({"_id": dep['_id']}, {"$set": {"status": "reviewing", "bill_file_id": message.photo[-1].file_id}})

    kb = types.InlineKeyboardMarkup(row_width=2).add(types.InlineKeyboardButton("✅ DUYỆT CỘNG", callback_data=f"admappr_{dep['_id']}"), types.InlineKeyboardButton("❌ TỪ CHỐI", callback_data=f"admreje_{dep['_id']}"))
    user = get_user(uid)
    uname = f"@{user.get('username', 'user')}"
    cap = f"💳 **CÓ BILL NẠP MỚI**\n👤 User: `{uid}` (`{uname}`)\n💵 Tiền nạp: **{format_money(dep['amount'])}**\n🏷 Nội dung CK: `{dep['content']}`"
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=cap, parse_mode="Markdown", reply_markup=kb)
    
    bot.reply_to(message, "✅ **Đã gửi biên lai cho Admin!** Hệ thống sẽ cộng tiền sớm nhất.", parse_mode="Markdown")
    text, menu = get_main_menu(user)
    bot.send_message(message.chat.id, text, reply_markup=menu, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('rut_'))
def handle_withdraw_calls(call):
    user = get_user(call.from_user.id)
    if user.get('is_banned'): return
    act = call.data
    m = call.message
    uid = call.from_user.id
    
    total_dep = user.get('total_deposited', 0)
    total_bet = user.get('total_bet', 0)
    req_bet = int(total_dep * 1.5)
    
    if total_bet < req_bet: return bot.answer_callback_query(call.id, f"❌ Chưa đủ điều kiện! Bạn cần cược thêm {format_money(req_bet - total_bet)}", show_alert=True)
    
    if act == "rut_custom":
        msg = bot.edit_message_text(f"⌨️ **NHẬP SỐ TIỀN MUỐN RÚT:**\n*(Min 200k, Dư: {format_money(user['balance'])})*", m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_rut_custom, m.message_id)
    elif act.startswith("rut_"):
        amt = int(act.split("_")[1])
        if amt < 200000 or amt > user['balance']: return bot.answer_callback_query(call.id, "❌ Không đủ số dư hoặc dưới mức tối thiểu!", show_alert=True)
            
        if uid not in temp_data: temp_data[uid] = {}
        temp_data[uid]['amount'] = amt
        
        text_prompt = (
            f"💸 Bạn đang đặt lệnh rút: **{format_money(amt)}**\n\n"
            "⌨️ **NHẬP THÔNG TIN TÀI KHOẢN NHẬN TIỀN:**\n"
            "*(Bắt buộc ghi theo thứ tự: NgânHàng STK TênChủTàiKhoản)*\n"
            "*(VD: MB 123456789 NGUYEN VAN A)*"
        )
        msg = bot.edit_message_text(text_prompt, m.chat.id, m.message_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_rut_info, m.message_id)

def process_rut_custom(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    amt = parse_money(message.text)
    user = get_user(message.from_user.id)
    
    if amt < 200000 or amt > user['balance']:
        bot.edit_message_text(f"❌ Số tiền không hợp lệ! (Min 200k, Dư: {format_money(user['balance'])})\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_custom, old_msg_id)
        return
        
    if user['_id'] not in temp_data: temp_data[user['_id']] = {}
    temp_data[user['_id']]['amount'] = amt
    
    text_prompt = (
        f"💸 Bạn đang đặt lệnh rút: **{format_money(amt)}**\n\n"
        "⌨️ **NHẬP THÔNG TIN TÀI KHOẢN NHẬN TIỀN:**\n"
        "*(Bắt buộc ghi theo thứ tự: NgânHàng STK TênChủTàiKhoản)*\n"
        "*(VD: MB 123456789 NGUYEN VAN A)*"
    )
    bot.edit_message_text(text_prompt, message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_info, old_msg_id)

def process_rut_info(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    uid = message.from_user.id
    user = get_user(uid)
    amt = temp_data.get(uid, {}).get('amount', 0)
    raw_info = message.text.strip()
    
    info_parts = raw_info.split()
    if len(info_parts) < 3:
        bot.edit_message_text(f"❌ Sai định dạng! Vui lòng nhập đúng: `NgânHàng STK Tên`\n*(VD: MB 12345 NGUYEN VAN A)*\n\n⌨️ **Nhập lại:**", message.chat.id, old_msg_id, reply_markup=get_back_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_rut_info, old_msg_id)
        return

    bank_id = info_parts[0].upper()
    acc_no = info_parts[1]
    acc_name = " ".join(info_parts[2:]).upper().replace(' ', '%20')
    
    if amt < 200000 or amt > user['balance']:
        text, markup = get_main_menu(user)
        return bot.edit_message_text(f"❌ Có lỗi xảy ra. Đã hủy lệnh rút!\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')

    users_col.update_one({'_id': uid}, {'$inc': {'balance': -amt}})
    log_transaction(uid, -amt, "Tạo đơn rút tiền")
    w_id = str(uuid.uuid4())
    withdraws_col.insert_one({"_id": w_id, "user_id": uid, "amount": amt, "info": raw_info, "status": "pending", "time": datetime.now()})
    
    qr_url = f"https://img.vietqr.io/image/{bank_id}-{acc_no}-compact2.png?amount={amt}&accountName={acc_name}&addInfo=ThanhToanRutTien"
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ CHUYỂN TIỀN (DUYỆT)", callback_data=f"admw_appr_{w_id}"), types.InlineKeyboardButton("❌ TỪ CHỐI (HOÀN TIỀN)", callback_data=f"admw_reje_{w_id}"))
    
    admin_text = f"💸 **YÊU CẦU RÚT TIỀN**\n👤 STT: `#{user['stt']}` (ID: `{uid}`)\n💰 Số tiền: **{format_money(amt)}**\n💳 Thông tin: `{raw_info}`\n\n*(Admin quét mã QR ở trên để chuyển khoản tự động)*"
    
    try: bot.send_photo(ADMIN_ID, photo=qr_url, caption=admin_text, reply_markup=kb, parse_mode='Markdown')
    except Exception: bot.send_message(ADMIN_ID, admin_text, reply_markup=kb, parse_mode='Markdown')
    
    text, m_markup = get_main_menu(get_user(uid))
    bot.edit_message_text(f"✅ Đã gửi yêu cầu rút **{format_money(amt)}** tới hệ thống! Đang chờ duyệt.\n\n{text}", message.chat.id, old_msg_id, reply_markup=m_markup, parse_mode='Markdown')

# ==========================================
# ADMIN MENU QUẢN TRỊ 
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
    
    # ---------------- NÚT BAN/UNBAN TÍCH HỢP ----------------
    if act.startswith("adm_toggleban_"):
        uid_str = act.split("adm_toggleban_")[1]
        target_uid = int(uid_str) if uid_str.isdigit() else uid_str
        
        u = users_col.find_one({'_id': target_uid})
        if u:
            new_status = not u.get('is_banned', False)
            users_col.update_one({'_id': target_uid}, {'$set': {'is_banned': new_status}})
            
            # Tự động load lại bảng thông tin user với trạng thái mới
            u['is_banned'] = new_status
            uname = f"@{u['username']}" if u.get('username') else "Không có"
            status_text = "🔴 ĐANG BỊ KHÓA" if new_status else "🟢 HOẠT ĐỘNG BÌNH THƯỜNG"
            
            text = (f"👤 **THÔNG TIN KHÁCH HÀNG**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                    f"🔢 STT: `#{u['stt']}` | 🆔 ID: `{u['_id']}`\n📝 Username: `{uname}` | 🌟 VIP: `{u.get('vip', 0)}`\n"
                    f"⚠️ Trạng thái: **{status_text}**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                    f"💰 Dư hiện tại: **{format_money(u.get('balance', 0))}**\n💵 Tổng Nạp: **{format_money(u.get('total_deposited', 0))}**\n"
                    f"🎲 Tổng Cược: **{format_money(u.get('total_bet', 0))}**\n🏆 Tổng Thắng: **{format_money(u.get('total_won', 0))}**")
            
            kb = types.InlineKeyboardMarkup(row_width=1)
            btn_text = "🟢 MỞ KHÓA (UNBAN)" if new_status else "🚫 KHÓA TÀI KHOẢN (BAN)"
            kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_toggleban_{u['_id']}"))
            kb.add(get_back_admin_btn().keyboard[0][0])
            
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=kb, parse_mode='Markdown')
            bot.answer_callback_query(call.id, f"✅ Đã {'Khóa' if new_status else 'Mở Khóa'} thành công #{u['stt']}", show_alert=False)
        return
    # --------------------------------------------------------

    if act.startswith("admappr_"):
        dep_id = act.split("_")[1]
        dep = deposits_col.find_one({"_id": dep_id})
        if dep and dep['status'] == 'reviewing':
            uid = dep['user_id']
            amt = dep['amount']
            users_col.update_one({'_id': uid}, {'$inc': {'balance': amt, 'total_deposited': amt}})
            deposits_col.update_one({'_id': dep_id}, {'$set': {'status': 'approved'}})
            log_transaction(uid, amt, "Nạp tiền thành công")
            bot.edit_message_caption(f"✅ **ĐÃ DUYỆT CỘNG {format_money(amt)}**\n\n" + m.caption, m.chat.id, m.message_id, parse_mode='Markdown')
            
            updated_u = users_col.find_one({'_id': uid})
            total_dep = updated_u.get('total_deposited', 0)
            current_vip = updated_u.get('vip', 0)
            
            new_vip = 0
            if total_dep >= 3000000: new_vip = 5
            elif total_dep >= 1500000: new_vip = 4
            elif total_dep >= 500000: new_vip = 3
            elif total_dep >= 250000: new_vip = 2
            elif total_dep >= 100000: new_vip = 1
            
            if new_vip > current_vip:
                users_col.update_one({'_id': uid}, {'$set': {'vip': new_vip}})
                try: bot.send_message(uid, f"🎉 **ĐÃ DUYỆT NẠP {format_money(amt)}**\n\n🎊 **CHÚC MỪNG!** Tổng nạp của bạn đạt {format_money(total_dep)}.\nBạn được thăng lên **VIP {new_vip}** với tỉ lệ ăn **x{1.85 + new_vip*0.05:.2f}**!", parse_mode='Markdown')
                except: pass
            else:
                try: bot.send_message(uid, f"🎉 Admin đã duyệt nạp **{format_money(amt)}**!", parse_mode='Markdown')
                except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)
            
    elif act.startswith("admreje_"):
        dep_id = act.split("_")[1]
        dep = deposits_col.find_one({"_id": dep_id})
        if dep and dep['status'] == 'reviewing':
            deposits_col.update_one({'_id': dep_id}, {'$set': {'status': 'rejected'}})
            bot.edit_message_caption(f"❌ **ĐÃ TỪ CHỐI BILL**\n\n" + m.caption, m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(dep['user_id'], f"⚠️ Biên lai nạp **{format_money(dep['amount'])}** bị từ chối!", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)

    elif act.startswith("admw_appr_"):
        w_id = act.split("_")[2]
        w = withdraws_col.find_one({"_id": w_id})
        if w and w['status'] == 'pending':
            withdraws_col.update_one({'_id': w_id}, {'$set': {'status': 'approved'}})
            if m.content_type == 'photo': bot.edit_message_caption(f"✅ **ĐÃ CHUYỂN TIỀN THÀNH CÔNG**\n\n{m.caption}", m.chat.id, m.message_id, parse_mode='Markdown')
            else: bot.edit_message_text(f"✅ **ĐÃ CHUYỂN TIỀN THÀNH CÔNG**\n\n{m.text}", m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(w['user_id'], f"🎉 Rút thành công **{format_money(w['amount'])}**. Tiền đã về tài khoản!", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)

    elif act.startswith("admw_reje_"):
        w_id = act.split("_")[2]
        w = withdraws_col.find_one({"_id": w_id})
        if w and w['status'] == 'pending':
            withdraws_col.update_one({'_id': w_id}, {'$set': {'status': 'rejected'}})
            users_col.update_one({'_id': w['user_id']}, {'$inc': {'balance': w['amount']}}) 
            log_transaction(w['user_id'], w['amount'], "Hoàn tiền rút bị từ chối")
            if m.content_type == 'photo': bot.edit_message_caption(f"❌ **ĐÃ TỪ CHỐI VÀ HOÀN TIỀN**\n\n{m.caption}", m.chat.id, m.message_id, parse_mode='Markdown')
            else: bot.edit_message_text(f"❌ **ĐÃ TỪ CHỐI VÀ HOÀN TIỀN**\n\n{m.text}", m.chat.id, m.message_id, parse_mode='Markdown')
            try: bot.send_message(w['user_id'], f"⚠️ Yêu cầu rút **{format_money(w['amount'])}** bị từ chối. Số điểm đã hoàn lại vào ví!", parse_mode='Markdown')
            except: pass
        else: bot.answer_callback_query(call.id, "❌ Đơn này đã xử lý!", show_alert=True)

    try:
        if act == "adm_main":
            text, markup = get_admin_menu()
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=markup, parse_mode='Markdown')
        elif act == "adm_money_step1":
            msg = bot.edit_message_text("💰 **CỘNG/TRỪ TIỀN KHÁCH HÀNG**\n👉 **BƯỚC 1:** Nhập `STT`, `ID` hoặc `@Username` của khách:\n*(VD: 1 hoặc @nguyenvana)*", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_money_step2, m.message_id)
            
        elif act == "adm_code":
            codes = list(codes_col.find())
            if not codes:
                text = "🎁 **HỆ THỐNG QUẢN LÝ GIFTCODE**\n\n📭 Hiện tại chưa có mã Code nào đang hoạt động."
            else:
                text = "🎁 **HỆ THỐNG QUẢN LÝ GIFTCODE**\n\n📋 **Danh sách Code đang hoạt động:**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                for c in codes:
                    text += f"🎫 Mã: `{c['_id']}`\n💰 Thưởng: **{format_money(c['reward'])}**\n🔄 Lượt còn lại: **{c['uses_left']}** lượt\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
            
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(
                types.InlineKeyboardButton("➕ TẠO CODE MỚI", callback_data="adm_code_add"),
                types.InlineKeyboardButton("🗑 XÓA TẤT CẢ", callback_data="adm_code_del_all")
            )
            kb.add(get_back_admin_btn().keyboard[0][0])
            bot.edit_message_text(text, m.chat.id, m.message_id, reply_markup=kb, parse_mode='Markdown')
            
        elif act == "adm_code_add":
            msg = bot.edit_message_text("🎁 **TẠO MÃ GIFTCODE MỚI**\n\n⌨️ Nhập theo cú pháp: `Mã Tiền Lượt`\n*(VD: `VIP100 100k 10`)*\n\n⚠️ *Lưu ý: Mã code viết liền không dấu.*", m.chat.id, m.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 HỦY BỎ", callback_data="adm_code")), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_code, m.message_id)
            
        elif act == "adm_code_del_all":
            codes_col.delete_many({})
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ QUẢN LÝ CODE", callback_data="adm_code"))
            bot.edit_message_text("🗑 **Đã xóa toàn bộ mã Giftcode hiện có trong hệ thống!**", m.chat.id, m.message_id, reply_markup=kb, parse_mode='Markdown')
        
        # ====================================================
        # HIỂN THỊ DANH SÁCH USER TRỰC TIẾP LÊN MÀN HÌNH ADMIN
        # ====================================================
        elif act == "adm_mgr":
            cursor = users_col.find().sort("stt", 1)
            count = users_col.count_documents({})
            text_list = f"👥 **DANH SÁCH {count} NGƯỜI DÙNG:**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
            
            shown_count = 0
            for u in cursor:
                uname = f"@{u.get('username', 'user')}"
                bal = format_money(u.get('balance', 0))
                tbet = format_money(u.get('total_bet', 0))
                twon = format_money(u.get('total_won', 0))
                
                line = f"`#{u['stt']}` | `{uname}` | Dư: {bal} | Cược: {tbet} | Win: {twon}\n"
                
                if len(text_list) + len(line) > 3500:
                    text_list += f"\n*... và {count - shown_count} người dùng khác.*"
                    break
                    
                text_list += line
                shown_count += 1
            
            if count == 0:
                text_list += "📭 Hệ thống chưa có khách hàng nào!\n"
            
            text_list += "〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n👇 **Chọn chức năng quản lý chi tiết:**"
            
            kb = types.InlineKeyboardMarkup(row_width=1)
            if count > shown_count:
                kb.add(types.InlineKeyboardButton("📜 XUẤT TOÀN BỘ RA FILE TXT", callback_data="adm_mgr_list"))
            else:
                kb.add(types.InlineKeyboardButton("📜 XUẤT DANH SÁCH RA FILE TXT", callback_data="adm_mgr_list"))
                
            kb.add(
                types.InlineKeyboardButton("🔍 SOI THÔNG TIN TỪ STT", callback_data="adm_mgr_info"),
                get_back_admin_btn().keyboard[0][0]
            )
            bot.edit_message_text(text_list, m.chat.id, m.message_id, reply_markup=kb, parse_mode='Markdown')
            
        elif act == "adm_mgr_list":
            bot.edit_message_text("⏳ Đang xuất dữ liệu từ hệ thống, vui lòng chờ...", m.chat.id, m.message_id)
            try:
                cursor = users_col.find().sort("stt", 1)
                text_list = "📋 DANH SÁCH NGƯỜI DÙNG SỬ DỤNG BOT\n"
                text_list += "="*50 + "\n\n"
                count = 0
                for u in cursor:
                    uname = u.get("username", "Ẩn_danh")
                    bal = u.get("balance", 0)
                    tbet = u.get("total_bet", 0)
                    twon = u.get("total_won", 0)
                    text_list += f"STT: #{u['stt']} | ID: {u['_id']} | @{uname}\n"
                    text_list += f" ├ Số dư hiện tại : {bal:,} VNĐ\n"
                    text_list += f" ├ Số tiền cược   : {tbet:,} VNĐ\n"
                    text_list += f" └ Số tiền thắng  : {twon:,} VNĐ\n"
                    text_list += "-"*50 + "\n"
                    count += 1
                
                if count == 0:
                    bot.edit_message_text("📭 Hệ thống chưa có người dùng nào!", m.chat.id, m.message_id, reply_markup=get_back_admin_btn())
                else:
                    bio = BytesIO(text_list.encode('utf-8'))
                    bot.send_document(m.chat.id, types.InputFile(bio, filename="Danh_sach_user.txt"), caption=f"✅ Đã xuất thành công **{count} người dùng**.\n*(Sắp xếp theo STT tăng dần)*", parse_mode='Markdown', reply_markup=get_back_admin_btn())
                    bot.delete_message(m.chat.id, m.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ Lỗi: {e}", m.chat.id, m.message_id, reply_markup=get_back_admin_btn())
                
        elif act == "adm_mgr_info":
            msg = bot.edit_message_text("👥 **XEM THÔNG TIN USER**\n\n⌨️ Nhập `STT` hoặc `Username` của khách:", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_mgr_info, m.message_id)
            
        elif act == "adm_bc":
            msg = bot.edit_message_text("📢 **THÔNG BÁO**\n⌨️ Nhập nội dung cần gửi:", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_bc, m.message_id)
        elif act == "adm_vip":
            msg = bot.edit_message_text("🌟 **SET VIP**\n⌨️ Nhập: `STT/ID CấpVIP` (VD: `1 2`)", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_vip, m.message_id)
            
        # ---------------- SỬA LẠI NÚT BAN CŨ ----------------
        elif act == "adm_ban":
            msg = bot.edit_message_text("🚫 **KHÓA / MỞ TÀI KHOẢN**\n\n⌨️ Nhập `STT` hoặc `Username` của khách cần xử lý:", m.chat.id, m.message_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
            bot.register_next_step_handler(msg, process_adm_ban, m.message_id)
    except: pass

def process_adm_money_step2(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    ref = message.text.strip()
    u = find_user(ref)
    if not u:
        bot.edit_message_text("❌ Không tìm thấy User!\n⌨️ Nhập lại STT/ID/Username:", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_money_step2, old_msg_id)
        return
    
    if message.from_user.id not in temp_data: temp_data[message.from_user.id] = {}
    temp_data[message.from_user.id]['target_user'] = u
    
    uname = f"@{u['username']}" if u.get('username') else "Không có"
    text = (f"👤 Đang chọn Khách: `{uname}` (STT: `#{u['stt']}`)\n💰 Số dư hiện tại: **{format_money(u.get('balance', 0))}**\n\n"
            "👉 **BƯỚC 2: Nhập số tiền**\n➕ CỘNG TIỀN: Nhập `50k`\n➖ TRỪ TIỀN: Nhập `-50k`\n\n⌨️ Nhập số tiền vào ô chat:")
    bot.edit_message_text(text, message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_money_step3, old_msg_id)

def process_adm_money_step3(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    text_amt = message.text.strip().lower()
    is_sub = False
    if text_amt.startswith('-'):
        is_sub = True
        text_amt = text_amt[1:] 
        
    amt = parse_money(text_amt)
    if amt < 0: 
        bot.edit_message_text("❌ Số tiền không hợp lệ!\n⌨️ Nhập lại (VD: `50k` hoặc `-50k`):", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_money_step3, old_msg_id)
        return
        
    target_user = temp_data.get(message.from_user.id, {}).get('target_user')
    final_amt = -amt if is_sub else amt
    users_col.update_one({'_id': target_user['_id']}, {'$inc': {'balance': final_amt}})
    
    action_text = "TRỪ" if is_sub else "CỘNG"
    log_transaction(target_user['_id'], final_amt, f"Admin {action_text.lower()} tiền")
    
    if not is_sub:
        try: bot.send_message(target_user['_id'], f"🔔 Admin đã gửi tặng **{format_money(amt)}** cho bạn!")
        except: pass
        
    text, markup = get_admin_menu()
    bot.edit_message_text(f"✅ Đã **{action_text} {format_money(amt)}** cho #{target_user['stt']}\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')

def process_adm_mgr_info(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    ref = message.text.strip()
    u = find_user(ref)
    if u:
        uname = f"@{u['username']}" if u.get('username') else "Không có"
        is_ban = u.get('is_banned', False)
        status_text = "🔴 ĐANG BỊ KHÓA" if is_ban else "🟢 HOẠT ĐỘNG BÌNH THƯỜNG"
        
        text = (f"👤 **THÔNG TIN KHÁCH HÀNG**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                f"🔢 STT: `#{u['stt']}` | 🆔 ID: `{u['_id']}`\n📝 Username: `{uname}` | 🌟 VIP: `{u.get('vip', 0)}`\n"
                f"⚠️ Trạng thái: **{status_text}**\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
                f"💰 Dư hiện tại: **{format_money(u.get('balance', 0))}**\n💵 Tổng Nạp: **{format_money(u.get('total_deposited', 0))}**\n"
                f"🎲 Tổng Cược: **{format_money(u.get('total_bet', 0))}**\n🏆 Tổng Thắng: **{format_money(u.get('total_won', 0))}**")
        
        # Thêm nút bấm Ban/Unban trực tiếp ở dưới cùng
        kb = types.InlineKeyboardMarkup(row_width=1)
        btn_text = "🟢 MỞ KHÓA (UNBAN)" if is_ban else "🚫 KHÓA TÀI KHOẢN (BAN)"
        kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_toggleban_{u['_id']}"))
        kb.add(get_back_admin_btn().keyboard[0][0])
        
        bot.edit_message_text(text, message.chat.id, old_msg_id, reply_markup=kb, parse_mode='Markdown')
    else:
        bot.edit_message_text("❌ Không tìm thấy User!\n⌨️ Nhập lại:", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_mgr_info, old_msg_id)

def process_adm_code(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    try:
        n, m, l = message.text.split()
        amt = parse_money(m)
        codes_col.update_one({'_id': n.upper()}, {'$set': {'reward': amt, 'uses_left': int(l), 'used_by': []}}, upsert=True)
        
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ QUẢN LÝ CODE", callback_data="adm_code"))
        bot.edit_message_text(f"✅ Đã tạo thành công Code `{n.upper()}`!\n💰 Trị giá: {format_money(amt)}\n🔄 Số lượt: {l}", message.chat.id, old_msg_id, reply_markup=kb, parse_mode='Markdown')
    except:
        bot.edit_message_text("❌ Lỗi cú pháp!\n⌨️ Nhập lại (VD: `KM100 100k 10`):", message.chat.id, old_msg_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 VỀ QUẢN LÝ CODE", callback_data="adm_code")), parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(message.chat.id, process_adm_code, old_msg_id)

def process_adm_bc(message, old_msg_id):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    users = users_col.find({}, {'_id': 1})
    count = 0
    for u in users:
        try:
            bot.send_message(u['_id'], f"📢 **THÔNG BÁO TỪ HỆ THỐNG**\n\n{message.text}", parse_mode='Markdown')
            count += 1; time.sleep(0.04)
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
    ref = message.text.strip()
    u = find_user(ref)
    if u:
        new_status = not u.get('is_banned', False)
        users_col.update_one({'_id': u['_id']}, {'$set': {'is_banned': new_status}})
        text, markup = get_admin_menu()
        status_str = "KHÓA" if new_status else "MỞ KHÓA"
        bot.edit_message_text(f"✅ Đã **{status_str}** tài khoản #{u['stt']} (`@{u.get('username', 'N/A')}`)\n\n{text}", message.chat.id, old_msg_id, reply_markup=markup, parse_mode='Markdown')
    else:
        bot.edit_message_text("❌ Lỗi! Không tìm thấy khách hàng.\n⌨️ Nhập lại `STT`:", message.chat.id, old_msg_id, reply_markup=get_back_admin_btn(), parse_mode='Markdown')
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
