import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from datetime import datetime, time
import pytz

# Environment variable
TOKEN = os.getenv("BOT_TOKEN")

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Timezone setup
MYANMAR_TIMEZONE = pytz.timezone('Asia/Yangon')

# Globals
admin_id = None
user_data = {}
ledger = {}
za_data = {}
com_data = {}
pnumber_value = None
date_control = {}
overbuy_list = {}
message_store = {}
overbuy_selections = {}
break_limit = None

def reverse_number(n):
    s = str(n).zfill(2)
    return int(s[::-1])

def get_time_segment():
    now = datetime.now(MYANMAR_TIMEZONE).time()
    return "AM" if now < time(12, 0) else "PM"

def get_current_date_key():
    now = datetime.now(MYANMAR_TIMEZONE)
    return f"{now.strftime('%d/%m/%Y')} {get_time_segment()}"

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    if update.effective_user.id == admin_id:
        keyboard = [
            ["/dateopen", "/dateclose"],
            ["/ledger", "/break"],
            ["/overbuy", "/pnumber"],
            ["/comandza", "/total"],
            ["/tsent", "/alldata"],
            ["/reset", "/posthis"]
        ]
    else:
        keyboard = [
            ["/posthis"]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("မီနူးကိုရွေးချယ်ပါ", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    admin_id = update.effective_user.id
    logger.info(f"Admin set to: {admin_id}")
    await update.message.reply_text("🤖 Bot started. Admin privileges granted!")
    await show_menu(update, context)

async def dateopen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    if update.effective_user.id != admin_id:
        await update.message.reply_text("❌ Admin only command")
        return
        
    key = get_current_date_key()
    date_control[key] = True
    logger.info(f"Ledger opened for {key}")
    await update.message.reply_text(f"✅ {key} စာရင်းဖွင့်ပြီးပါပြီ")

async def dateclose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    if update.effective_user.id != admin_id:
        await update.message.reply_text("❌ Admin only command")
        return
        
    key = get_current_date_key()
    date_control[key] = False
    logger.info(f"Ledger closed for {key}")
    await update.message.reply_text(f"✅ {key} စာရင်းပိတ်လိုက်ပါပြီ")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        text = update.message.text
        
        if not user or not user.username:
            await update.message.reply_text("❌ ကျေးဇူးပြု၍ Telegram username သတ်မှတ်ပါ")
            return

        key = get_current_date_key()
        if not date_control.get(key, False):
            await update.message.reply_text("❌ စာရင်းပိတ်ထားပါသည်")
            return

        if not text:
            await update.message.reply_text("⚠️ မက်ဆေ့ဂျ်မရှိပါ")
            return

        if any(c in text for c in ['%', '&', '*', '$']):
            await update.message.reply_text("⚠️ မှားနေပါတယ်\nအထူးသင်္ကေတများ (%&*$) မပါရပါ\nဥပမာ: 12-500")
            return

        entries = text.split()
        bets = []
        total_amount = 0

        i = 0
        while i < len(entries):
            entry = entries[i]
            
            if i + 2 < len(entries):
                if (entries[i].isdigit() and entries[i+1].isdigit() and entries[i+2].isdigit()):
                    num1 = int(entries[i])
                    num2 = int(entries[i+1])
                    amt = int(entries[i+2])
                    
                    if 0 <= num1 <= 99 and 0 <= num2 <= 99:
                        bets.append(f"{num1:02d}-{amt}")
                        bets.append(f"{num2:02d}-{amt}")
                        total_amount += amt * 2
                        i += 3
                        continue
            
            if '/' in entry:
                parts = entry.split('/')
                if len(parts) >= 3 and all(p.isdigit() for p in parts):
                    amt = int(parts[-1])
                    for num_str in parts[:-1]:
                        num = int(num_str)
                        if 0 <= num <= 99:
                            bets.append(f"{num:02d}-{amt}")
                            total_amount += amt
                    i += 1
                    continue
            
            if '-' in entry and 'r' not in entry:
                parts = entry.split('-')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    num = int(parts[0])
                    amt = int(parts[1])
                    if 0 <= num <= 99:
                        bets.append(f"{num:02d}-{amt}")
                        total_amount += amt
                        i += 1
                        continue
            
            if 'r' in entry and '-' not in entry:
                parts = entry.split('r')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    num = int(parts[0])
                    amt = int(parts[1])
                    rev = reverse_number(num)
                    if 0 <= num <= 99:
                        bets.append(f"{num:02d}-{amt}")
                        bets.append(f"{rev:02d}-{amt}")
                        total_amount += amt * 2
                        i += 1
                        continue
            
            if 'r' in entry and '-' in entry:
                main_part, r_part = entry.split('r', 1)
                if '-' in main_part:
                    num_part, amt_part = main_part.split('-')
                    if num_part.isdigit() and amt_part.isdigit() and r_part.isdigit():
                        num = int(num_part)
                        amt1 = int(amt_part)
                        amt2 = int(r_part)
                        rev = reverse_number(num)
                        if 0 <= num <= 99:
                            bets.append(f"{num:02d}-{amt1}")
                            bets.append(f"{rev:02d}-{amt2}")
                            total_amount += amt1 + amt2
                            i += 1
                            continue
            
            if entry.isdigit() and i+1 < len(entries) and 'r' in entries[i+1]:
                num = int(entry)
                r_part = entries[i+1]
                if r_part.count('r') == 1:
                    amt_part1, amt_part2 = r_part.split('r')
                    if amt_part1.isdigit() and amt_part2.isdigit():
                        amt1 = int(amt_part1)
                        amt2 = int(amt_part2)
                        rev = reverse_number(num)
                        if 0 <= num <= 99:
                            bets.append(f"{num:02d}-{amt1}")
                            bets.append(f"{rev:02d}-{amt2}")
                            total_amount += amt1 + amt2
                            i += 2
                            continue
            
            if 'အခွေ' in entry or 'အပူးပါအခွေ' in entry:
                base = entry.replace('အခွေ', '').replace('အပူးပါ', '')
                if base.isdigit() and len(base) >= 2:
                    digits = [int(d) for d in base]
                    pairs = []
                    for j in range(len(digits)):
                        for k in range(len(digits)):
                            if j != k:
                                combo = digits[j] * 10 + digits[k]
                                if combo not in pairs:
                                    pairs.append(combo)
                    
                    if 'အပူးပါအခွေ' in entry:
                        for d in digits:
                            double = d * 10 + d
                            if double not in pairs:
                                pairs.append(double)
                    
                    if i+1 < len(entries) and entries[i+1].isdigit():
                        amt = int(entries[i+1])
                        for num in pairs:
                            bets.append(f"{num:02d}-{amt}")
                            total_amount += amt
                        i += 2
                        continue
            
            fixed_special_cases = {
                "အပူး": [0, 11, 22, 33, 44, 55, 66, 77, 88, 99],
                "ပါဝါ": [5, 16, 27, 38, 49, 50, 61, 72, 83, 94],
                "နက္ခ": [7, 18, 24, 35, 42, 53, 69, 70, 81, 96],
                "ညီကို": [1, 12, 23, 34, 45, 56, 67, 78, 89, 90],
                "ကိုညီ": [9, 10, 21, 32, 43, 54, 65, 76, 87, 98],
            }
            
            if entry in fixed_special_cases:
                if i+1 < len(entries) and entries[i+1].isdigit():
                    amt = int(entries[i+1])
                    for num in fixed_special_cases[entry]:
                        bets.append(f"{num:02d}-{amt}")
                        total_amount += amt
                    i += 2
                    continue
            
            dynamic_types = ["ထိပ်", "ပိတ်", "ဘရိတ်", "အပါ"]
            found_dynamic = False
            for dtype in dynamic_types:
                if entry.endswith(dtype):
                    prefix = entry[:-len(dtype)]
                    if prefix.isdigit():
                        digit_val = int(prefix)
                        if 0 <= digit_val <= 9:
                            numbers = []
                            if dtype == "ထိပ်":
                                numbers = [digit_val * 10 + j for j in range(10)]
                            elif dtype == "ပိတ်":
                                numbers = [j * 10 + digit_val for j in range(10)]
                            elif dtype == "ဘရိတ်":
                                numbers = [n for n in range(100) if (n//10 + n%10) % 10 == digit_val]
                            elif dtype == "အပါ":
                                tens = [digit_val * 10 + j for j in range(10)]
                                units = [j * 10 + digit_val for j in range(10)]
                                numbers = list(set(tens + units))
                            
                            if i+1 < len(entries) and entries[i+1].isdigit():
                                amt = int(entries[i+1])
                                for num in numbers:
                                    bets.append(f"{num:02d}-{amt}")
                                    total_amount += amt
                                i += 2
                                found_dynamic = True
                            break
            if found_dynamic:
                continue
            
            if entry.isdigit():
                num = int(entry)
                if 0 <= num <= 99:
                    if i+1 < len(entries) and entries[i+1].isdigit():
                        amt = int(entries[i+1])
                        bets.append(f"{num:02d}-{amt}")
                        total_amount += amt
                        i += 2
                    else:
                        bets.append(f"{num:02d}-500")
                        total_amount += 500
                        i += 1
                    continue
            
            i += 1

        if user.username not in user_data:
            user_data[user.username] = {}
        if key not in user_data[user.username]:
            user_data[user.username][key] = []

        for bet in bets:
            num, amt = bet.split('-')
            num = int(num)
            amt = int(amt)
            ledger[num] = ledger.get(num, 0) + amt
            user_data[user.username][key].append((num, amt))

        if bets:
            response = "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
            keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{user.id}:{update.message.message_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            sent_message = await update.message.reply_text(response, reply_markup=reply_markup)
            message_store[(user.id, update.message.message_id)] = (sent_message.message_id, bets, total_amount)
        else:
            await update.message.reply_text("⚠️ အချက်အလက်များကိုစစ်ဆေးပါ")
            
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def delete_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, user_id_str, message_id_str = query.data.split(':')
        user_id = int(user_id_str)
        message_id = int(message_id_str)
        
        if query.from_user.id != admin_id:
            if (user_id, message_id) in message_store:
                sent_message_id, bets, total_amount = message_store[(user_id, message_id)]
                response = "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
                keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{user_id}:{message_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text=f"❌ User များမဖျက်နိုင်ပါ၊ Admin ကိုဆက်သွယ်ပါ\n\n{response}",
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text("❌ User များမဖျက်နိုင်ပါ၊ Admin ကိုဆက်သွယ်ပါ")
            return
        
        keyboard = [
            [InlineKeyboardButton("✅ OK", callback_data=f"confirm_delete:{user_id}:{message_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_delete:{user_id}:{message_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚠️ သေချာလား? ဒီလောင်းကြေးကိုဖျက်မှာလား?", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in delete_bet: {str(e)}")
        await query.edit_message_text("❌ Error occurred while processing deletion")

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, user_id_str, message_id_str = query.data.split(':')
        user_id = int(user_id_str)
        message_id = int(message_id_str)
        
        if (user_id, message_id) not in message_store:
            await query.edit_message_text("❌ ဒေတာမတွေ့ပါ")
            return
            
        sent_message_id, bets, total_amount = message_store[(user_id, message_id)]
        key = get_current_date_key()
        
        username = None
        for uname, data in user_data.items():
            if key in data:
                for bet in data[key]:
                    num, amt = bet
                    if f"{num:02d}-{amt}" in bets:
                        username = uname
                        break
                if username:
                    break
        
        if not username:
            await query.edit_message_text("❌ User မတွေ့ပါ")
            return
        
        for bet in bets:
            num, amt = bet.split('-')
            num = int(num)
            amt = int(amt)
            
            if num in ledger:
                ledger[num] -= amt
                if ledger[num] <= 0:
                    del ledger[num]
            
            if username in user_data and key in user_data[username]:
                user_data[username][key] = [
                    (n, a) for n, a in user_data[username][key] 
                    if not (n == num and a == amt)
                ]
                
                if not user_data[username][key]:
                    del user_data[username][key]
                    if not user_data[username]:
                        del user_data[username]
        
        del message_store[(user_id, message_id)]
        
        await query.edit_message_text("✅ လောင်းကြေးဖျက်ပြီးပါပြီ")
        
    except Exception as e:
        logger.error(f"Error in confirm_delete: {str(e)}")
        await query.edit_message_text("❌ Error occurred while deleting bet")

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, user_id_str, message_id_str = query.data.split(':')
        user_id = int(user_id_str)
        message_id = int(message_id_str)
        
        if (user_id, message_id) in message_store:
            sent_message_id, bets, total_amount = message_store[(user_id, message_id)]
            response = "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
            keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{user_id}:{message_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup)
        else:
            await query.edit_message_text("ℹ️ ဖျက်ခြင်းကိုပယ်ဖျက်လိုက်ပါပြီ")
            
    except Exception as e:
        logger.error(f"Error in cancel_delete: {str(e)}")
        await query.edit_message_text("❌ Error occurred while canceling deletion")

async def ledger_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        lines = ["📒 လက်ကျန်ငွေစာရင်း"]
        for i in range(100):
            total = ledger.get(i, 0)
            if total > 0:
                if pnumber_value is not None and i == pnumber_value:
                    lines.append(f"🔴 {i:02d} ➤ {total} 🔴")
                else:
                    lines.append(f"{i:02d} ➤ {total}")
        
        if len(lines) == 1:
            await update.message.reply_text("ℹ️ လက်ရှိတွင် လောင်းကြေးမရှိပါ")
        else:
            if pnumber_value is not None:
                lines.append(f"\n🔴 Power Number: {pnumber_value:02d} ➤ {ledger.get(pnumber_value, 0)}")
            await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Error in ledger: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def break_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, break_limit
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not context.args:
            if break_limit is None:
                await update.message.reply_text("ℹ️ Usage: /break [limit]\nℹ️ လက်ရှိတွင် break limit မသတ်မှတ်ရသေးပါ")
            else:
                await update.message.reply_text(f"ℹ️ Usage: /break [limit]\nℹ️ လက်ရှိ break limit: {break_limit}")
            return
            
        try:
            new_limit = int(context.args[0])
            break_limit = new_limit
            await update.message.reply_text(f"✅ Break limit ကို {break_limit} အဖြစ်သတ်မှတ်ပြီးပါပြီ")
            
            msg = [f"📌 Limit ({break_limit}) ကျော်ဂဏန်းများ:"]
            for k, v in ledger.items():
                if v > break_limit:
                    msg.append(f"{k:02d} ➤ {v - break_limit}")
            
            if len(msg) == 1:
                await update.message.reply_text(f"ℹ️ ဘယ်ဂဏန်းမှ limit ({break_limit}) မကျော်ပါ")
            else:
                await update.message.reply_text("\n".join(msg))
                
        except ValueError:
            await update.message.reply_text("⚠️ Limit amount ထည့်ပါ (ဥပမာ: /break 5000)")
            
    except Exception as e:
        logger.error(f"Error in break: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def overbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, break_limit
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not context.args:
            await update.message.reply_text("ℹ️ ကာဒိုင်အမည်ထည့်ပါ")
            return
            
        if break_limit is None:
            await update.message.reply_text("⚠️ ကျေးဇူးပြု၍ /break [limit] ဖြင့် limit သတ်မှတ်ပါ")
            return
            
        username = context.args[0]
        context.user_data['overbuy_username'] = username
        
        over_numbers = {num: amt - break_limit for num, amt in ledger.items() if amt > break_limit}
        
        if not over_numbers:
            await update.message.reply_text(f"ℹ️ ဘယ်ဂဏန်းမှ limit ({break_limit}) မကျော်ပါ")
            return
            
        overbuy_selections[username] = over_numbers.copy()
        
        msg = [f"{username} ထံမှာတင်ရန်များ (Limit: {break_limit}):"]
        buttons = []
        for num, amt in over_numbers.items():
            buttons.append([InlineKeyboardButton(f"{num:02d} ➤ {amt} {'✅' if num in overbuy_selections[username] else '⬜'}", 
                          callback_data=f"overbuy_select:{num}")])
        
        buttons.append([
            InlineKeyboardButton("Select All", callback_data="overbuy_select_all"),
            InlineKeyboardButton("Unselect All", callback_data="overbuy_unselect_all")
        ])
        buttons.append([InlineKeyboardButton("OK", callback_data="overbuy_confirm")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in overbuy: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def overbuy_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, num_str = query.data.split(':')
        num = int(num_str)
        username = context.user_data.get('overbuy_username')
        
        if username not in overbuy_selections:
            await query.edit_message_text("❌ Error: User not found")
            return
            
        if num in overbuy_selections[username]:
            del overbuy_selections[username][num]
        else:
            overbuy_selections[username][num] = ledger[num] - break_limit
            
        msg = [f"{username} ထံမှာတင်ရန်များ (Limit: {break_limit}):"]
        buttons = []
        for n, amt in overbuy_selections[username].items():
            buttons.append([InlineKeyboardButton(f"{n:02d} ➤ {amt} {'✅' if n in overbuy_selections[username] else '⬜'}", 
                          callback_data=f"overbuy_select:{n}")])
        
        buttons.append([
            InlineKeyboardButton("Select All", callback_data="overbuy_select_all"),
            InlineKeyboardButton("Unselect All", callback_data="overbuy_unselect_all")
        ])
        buttons.append([InlineKeyboardButton("OK", callback_data="overbuy_confirm")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in overbuy_select: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def overbuy_select_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        username = context.user_data.get('overbuy_username')
        if username not in overbuy_selections:
            await query.edit_message_text("❌ Error: User not found")
            return
            
        overbuy_selections[username] = {num: amt - break_limit for num, amt in ledger.items() if amt > break_limit}
        
        msg = [f"{username} ထံမှာတင်ရန်များ (Limit: {break_limit}):"]
        buttons = []
        for num, amt in overbuy_selections[username].items():
            buttons.append([InlineKeyboardButton(f"{num:02d} ➤ {amt} ✅", 
                          callback_data=f"overbuy_select:{num}")])
        
        buttons.append([
            InlineKeyboardButton("Select All", callback_data="overbuy_select_all"),
            InlineKeyboardButton("Unselect All", callback_data="overbuy_unselect_all")
        ])
        buttons.append([InlineKeyboardButton("OK", callback_data="overbuy_confirm")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in overbuy_select_all: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def overbuy_unselect_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        username = context.user_data.get('overbuy_username')
        if username not in overbuy_selections:
            await query.edit_message_text("❌ Error: User not found")
            return
            
        overbuy_selections[username] = {}
        
        msg = [f"{username} ထံမှာတင်ရန်များ (Limit: {break_limit}):"]
        buttons = []
        for num, amt in ledger.items():
            if amt > break_limit:
                buttons.append([InlineKeyboardButton(f"{num:02d} ➤ {amt - break_limit} ⬜", 
                              callback_data=f"overbuy_select:{num}")])
        
        buttons.append([
            InlineKeyboardButton("Select All", callback_data="overbuy_select_all"),
            InlineKeyboardButton("Unselect All", callback_data="overbuy_unselect_all")
        ])
        buttons.append([InlineKeyboardButton("OK", callback_data="overbuy_confirm")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in overbuy_unselect_all: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def overbuy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        username = context.user_data.get('overbuy_username')
        if username not in overbuy_selections:
            await query.edit_message_text("❌ Error: User not found")
            return
            
        selected_numbers = overbuy_selections[username]
        if not selected_numbers:
            await query.edit_message_text("⚠️ ဘာဂဏန်းမှမရွေးထားပါ")
            return
            
        key = get_current_date_key()
        if username not in user_data:
            user_data[username] = {}
        if key not in user_data[username]:
            user_data[username][key] = []
            
        total_amount = 0
        bets = []
        for num, amt in selected_numbers.items():
            user_data[username][key].append((num, -amt))
            bets.append(f"{num:02d}-{amt}")
            total_amount += amt
            
            ledger[num] = ledger.get(num, 0) - amt
            if ledger[num] <= 0:
                del ledger[num]
        
        overbuy_list[username] = selected_numbers.copy()
        
        response = f"{username}\n" + "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
        await query.edit_message_text(response)
        
    except Exception as e:
        logger.error(f"Error in overbuy_confirm: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def pnumber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, pnumber_value
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not context.args:
            await update.message.reply_text("ℹ️ Usage: /pnumber [number]")
            return
            
        num = int(context.args[0])
        if num < 0 or num > 99:
            await update.message.reply_text("⚠️ ဂဏန်းကို 0 နှင့် 99 ကြားထည့်ပါ")
            return
            
        pnumber_value = num
        msg = []
        for user, records in user_data.items():
            total = 0
            for date_key in records:
                for bet_num, amt in records[date_key]:
                    if bet_num == pnumber_value:
                        total += amt
            if total > 0:
                msg.append(f"{user}: {pnumber_value:02d} ➤ {total}")
        
        if msg:
            await update.message.reply_text("\n".join(msg))
        else:
            await update.message.reply_text(f"ℹ️ {pnumber_value:02d} အတွက် လောင်းကြေးမရှိပါ")
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ ဂဏန်းမှန်မှန်ထည့်ပါ (ဥပမာ: /pnumber 15)")
    except Exception as e:
        logger.error(f"Error in pnumber: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def comandza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not user_data:
            await update.message.reply_text("ℹ️ လက်ရှိ user မရှိပါ")
            return
            
        users = list(user_data.keys())
        keyboard = [[InlineKeyboardButton(u, callback_data=f"comza:{u}")] for u in users]
        await update.message.reply_text("👉 User ကိုရွေးပါ", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error in comandza: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def comza_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        context.user_data['selected_user'] = query.data.split(":")[1]
        await query.edit_message_text(f"👉 {context.user_data['selected_user']} ကိုရွေးထားသည်။ 15/80 လို့ထည့်ပါ")
    except Exception as e:
        logger.error(f"Error in comza_input: {str(e)}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def comza_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = context.user_data.get('selected_user')
        if not user:
            await handle_message(update, context)
            return
            
        text = update.message.text
        if text and '/' in text:
            try:
                parts = text.split('/')
                if len(parts) != 2:
                    raise ValueError
                
                com = int(parts[0])
                za = int(parts[1])
                
                if com < 0 or com > 100 or za < 0:
                    raise ValueError
                    
                com_data[user] = com
                za_data[user] = za
                del context.user_data['selected_user']
                await update.message.reply_text(f"✅ Com {com}%, Za {za} မှတ်ထားပြီး")
            except:
                await update.message.reply_text("⚠️ မှန်မှန်ရေးပါ (ဥပမာ: 15/80)")
        else:
            await update.message.reply_text("⚠️ ဖော်မတ်မှားနေပါသည်။ 15/80 လို့ထည့်ပါ")
    except Exception as e:
        logger.error(f"Error in comza_text: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not user_data:
            await update.message.reply_text("ℹ️ လက်ရှိစာရင်းမရှိပါ")
            return
            
        if pnumber_value is None:
            await update.message.reply_text("ℹ️ ကျေးဇူးပြု၍ /pnumber 15")
            return
            
        msg = []
        total_net = 0
        
        for user, records in user_data.items():
            user_total_amt = 0
            user_pamt = 0
            
            for date_key in records:
                for num, amt in records[date_key]:
                    user_total_amt += amt
                    if num == pnumber_value:
                        user_pamt += amt
            
            com = com_data.get(user, 0)
            za = za_data.get(user, 0)
            
            commission_amt = (user_total_amt * com) // 100
            after_com = user_total_amt - commission_amt
            win_amt = user_pamt * za
            
            net = after_com - win_amt
            status = "ဒိုင်ကပေးရမည်" if net < 0 else "ဒိုင်ကရမည်"
            
            user_report = (
                f"👤 {user}\n"
                f"💵 စုစုပေါင်း: {user_total_amt}\n"
                f"📊 Com({com}%) ➤ {commission_amt}\n"
                f"💰 Com ပြီး: {after_com}\n"
                f"🔢 Power Number({pnumber_value:02d}) ➤ {user_pamt}\n"
                f"🎯 Za({za}) ➤ {win_amt}\n"
                f"📈 ရလဒ်: {abs(net)} ({status})\n"
                "-----------------"
            )
            msg.append(user_report)
            total_net += net

        msg.append(f"\n📊 စုစုပေါင်းရလဒ်: {abs(total_net)} ({'ဒိုင်အရှုံး' if total_net < 0 else 'ဒိုင်အမြတ်'})")

        if msg:
            await update.message.reply_text("\n".join(msg))
        else:
            await update.message.reply_text("ℹ️ တွက်ချက်မှုများအတွက် ဒေတာမရှိပါ")
    except Exception as e:
        logger.error(f"Error in total: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def tsent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not user_data:
            await update.message.reply_text("ℹ️ လက်ရှိ user မရှိပါ")
            return
            
        for user in user_data:
            user_report = []
            total_amt = 0
            
            for date_key, records in user_data[user].items():
                user_report.append(f"📅 {date_key}:")
                for num, amt in records:
                    user_report.append(f"  - {num:02d} ➤ {amt}")
                    total_amt += amt
            
            user_report.append(f"💵 စုစုပေါင်း: {total_amt}")
            await update.message.reply_text("\n".join(user_report))
        
        await update.message.reply_text("✅ စာရင်းများအားလုံး ပေးပို့ပြီးပါပြီ")
    except Exception as e:
        logger.error(f"Error in tsent: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def alldata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not user_data:
            await update.message.reply_text("ℹ️ လက်ရှိစာရင်းမရှိပါ")
            return
            
        msg = ["👥 မှတ်ပုံတင်ထားသော user များ:"]
        msg.extend([f"• {user}" for user in user_data.keys()])
        
        await update.message.reply_text("\n".join(msg))
    except Exception as e:
        logger.error(f"Error in alldata: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, user_data, ledger, za_data, com_data, date_control, overbuy_list, overbuy_selections, break_limit
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        user_data = {}
        ledger = {}
        za_data = {}
        com_data = {}
        date_control = {}
        overbuy_list = {}
        overbuy_selections = {}
        break_limit = None
        
        await update.message.reply_text("✅ ဒေတာများအားလုံးကို ပြန်လည်သုတ်သင်ပြီးပါပြီ")
    except Exception as e:
        logger.error(f"Error in reset_data: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def posthis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        is_admin = user.id == admin_id
        
        if is_admin and not context.args:
            if not user_data:
                await update.message.reply_text("ℹ️ လက်ရှိ user မရှိပါ")
                return
                
            keyboard = [[InlineKeyboardButton(u, callback_data=f"posthis:{u}")] for u in user_data.keys()]
            await update.message.reply_text(
                "ဘယ် user ရဲ့စာရင်းကိုကြည့်မလဲ?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        username = user.username if not is_admin else context.args[0] if context.args else None
        
        if not username:
            await update.message.reply_text("❌ User မရှိပါ")
            return
            
        if username not in user_data:
            await update.message.reply_text(f"ℹ️ {username} အတွက် စာရင်းမရှိပါ")
            return
            
        msg = [f"📊 {username} ရဲ့လောင်းကြေးမှတ်တမ်း"]
        total_amount = 0
        pnumber_total = 0
        
        for date_key in user_data[username]:
            msg.append(f"\n📅 {date_key}:")
            for num, amt in user_data[username][date_key]:
                if pnumber_value is not None and num == pnumber_value:
                    msg.append(f"🔴 {num:02d} ➤ {amt} 🔴")
                    pnumber_total += amt
                else:
                    msg.append(f"{num:02d} ➤ {amt}")
                total_amount += amt
        
        msg.append(f"\n💵 စုစုပေါင်း: {total_amount}")
        
        if pnumber_value is not None:
            msg.append(f"🔴 Power Number ({pnumber_value:02d}) စုစုပေါင်း: {pnumber_total}")
        
        await update.message.reply_text("\n".join(msg))
        
    except Exception as e:
        logger.error(f"Error in posthis: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def posthis_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, username = query.data.split(':')
        msg = [f"📊 {username} ရဲ့လောင်းကြေးမှတ်တမ်း"]
        total_amount = 0
        pnumber_total = 0
        
        if username in user_data:
            for date_key in user_data[username]:
                msg.append(f"\n📅 {date_key}:")
                for num, amt in user_data[username][date_key]:
                    if pnumber_value is not None and num == pnumber_value:
                        msg.append(f"🔴 {num:02d} ➤ {amt} 🔴")
                        pnumber_total += amt
                    else:
                        msg.append(f"{num:02d} ➤ {amt}")
                    total_amount += amt
            
            msg.append(f"\n💵 စုစုပေါင်း: {total_amount}")
            
            if pnumber_value is not None:
                msg.append(f"🔴 Power Number ({pnumber_value:02d}) စုစုပေါင်း: {pnumber_total}")
            
            await query.edit_message_text("\n".join(msg))
        else:
            await query.edit_message_text(f"ℹ️ {username} အတွက် စာရင်းမရှိပါ")
            
    except Exception as e:
        logger.error(f"Error in posthis_callback: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is not set")
        
    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("dateopen", dateopen))
    app.add_handler(CommandHandler("dateclose", dateclose))
    app.add_handler(CommandHandler("ledger", ledger_summary))
    app.add_handler(CommandHandler("break", break_command))
    app.add_handler(CommandHandler("overbuy", overbuy))
    app.add_handler(CommandHandler("pnumber", pnumber))
    app.add_handler(CommandHandler("comandza", comandza))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("tsent", tsent))
    app.add_handler(CommandHandler("alldata", alldata))
    app.add_handler(CommandHandler("reset", reset_data))
    app.add_handler(CommandHandler("posthis", posthis))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(comza_input, pattern=r"^comza:"))
    app.add_handler(CallbackQueryHandler(delete_bet, pattern=r"^delete:"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern=r"^confirm_delete:"))
    app.add_handler(CallbackQueryHandler(cancel_delete, pattern=r"^cancel_delete:"))
    app.add_handler(CallbackQueryHandler(overbuy_select, pattern=r"^overbuy_select:"))
    app.add_handler(CallbackQueryHandler(overbuy_select_all, pattern=r"^overbuy_select_all$"))
    app.add_handler(CallbackQueryHandler(overbuy_unselect_all, pattern=r"^overbuy_unselect_all$"))
    app.add_handler(CallbackQueryHandler(overbuy_confirm, pattern=r"^overbuy_confirm$"))
    app.add_handler(CallbackQueryHandler(posthis_callback, pattern=r"^posthis:"))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, comza_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Bot is starting...")
    app.run_polling()
