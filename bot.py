import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from datetime import datetime, time, timedelta
import pytz
import re
import calendar

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
user_data = {}  # {username: {date_key: [(num, amt)]}}
ledger = {}     # {date_key: {number: total_amount}}
break_limits = {}  # {date_key: limit}
pnumber_per_date = {}  # {date_key: power_number}
date_control = {}  # {date_key: True/False}
overbuy_list = {}  # {date_key: {username: {num: amount}}}
message_store = {}  # {(user_id, message_id): (sent_message_id, bets, total_amount, date_key)}
overbuy_selections = {}  # {date_key: {username: {num: amount}}}
current_working_date = None  # For admin date selection

# Com and Za data
com_data = {}
za_data = {}

def reverse_number(n):
    s = str(n).zfill(2)
    return int(s[::-1])

def get_time_segment():
    now = datetime.now(MYANMAR_TIMEZONE).time()
    return "AM" if now < time(12, 0) else "PM"

def get_current_date_key():
    now = datetime.now(MYANMAR_TIMEZONE)
    return f"{now.strftime('%d/%m/%Y')} {get_time_segment()}"

def get_available_dates():
    dates = set()
    # Get dates from user data
    for user_data_dict in user_data.values():
        dates.update(user_data_dict.keys())
    # Get dates from ledger
    dates.update(ledger.keys())
    # Get dates from break limits
    dates.update(break_limits.keys())
    # Get dates from pnumber
    dates.update(pnumber_per_date.keys())
    return sorted(dates, reverse=True)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    if update.effective_user.id == admin_id:
        keyboard = [
            ["/dateopen", "/dateclose"],
            ["/ledger", "/break"],
            ["/overbuy", "/pnumber"],
            ["/comandza", "/total"],
            ["/tsent", "/alldata"],
            ["/reset", "/posthis", "/dateall"],
            ["/Cdate", "/Ddate"]
        ]
    else:
        keyboard = [
            ["/posthis"]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("မီနူးကိုရွေးချယ်ပါ", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, current_working_date
    admin_id = update.effective_user.id
    current_working_date = get_current_date_key()
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
            
            # Improved handling for formats like 12-56-78r1000
            if 'r' in entry and '-' in entry:
                parts = entry.split('r')
                if len(parts) == 2 and parts[1].isdigit():
                    base_amount = int(parts[1])
                    reverse_amount = int(parts[1])
                    
                    # Split left part by '-' to get numbers
                    numbers = []
                    for num_str in parts[0].split('-'):
                        if num_str.isdigit():
                            num = int(num_str)
                            if 0 <= num <= 99:
                                numbers.append(num)
                    
                    if numbers:
                        for num in numbers:
                            bets.append(f"{num:02d}-{base_amount}")
                            rev = reverse_number(num)
                            bets.append(f"{rev:02d}-{reverse_amount}")
                            total_amount += base_amount + reverse_amount
                        i += 1
                        continue
            
            # Improved handling for formats like 12-56-78-1000r500
            if 'r' in entry and '-' in entry:
                parts = entry.split('r')
                if len(parts) == 2 and parts[1].isdigit():
                    reverse_amount = int(parts[1])
                    
                    # Split left part by '-' to get numbers and base amount
                    left_parts = parts[0].split('-')
                    if len(left_parts) >= 2 and left_parts[-1].isdigit():
                        base_amount = int(left_parts[-1])
                        numbers = []
                        for num_str in left_parts[:-1]:
                            if num_str.isdigit():
                                num = int(num_str)
                                if 0 <= num <= 99:
                                    numbers.append(num)
                        
                        if numbers:
                            for num in numbers:
                                bets.append(f"{num:02d}-{base_amount}")
                                rev = reverse_number(num)
                                bets.append(f"{rev:02d}-{reverse_amount}")
                                total_amount += base_amount + reverse_amount
                            i += 1
                            continue
            
            # Improved handling for formats like 67/34/12/1000r500
            if '/' in entry and 'r' in entry:
                parts = entry.split('/')
                # Find the part with 'r'
                r_index = -1
                for j, part in enumerate(parts):
                    if 'r' in part:
                        r_index = j
                        break
                
                if r_index > 0:
                    numbers = []
                    for j in range(r_index):
                        if parts[j].isdigit():
                            num = int(parts[j])
                            if 0 <= num <= 99:
                                numbers.append(num)
                    
                    if parts[r_index].count('r') == 1:
                        amt_parts = parts[r_index].split('r')
                        if len(amt_parts) == 2 and amt_parts[0].isdigit() and amt_parts[1].isdigit():
                            base_amt = int(amt_parts[0])
                            reverse_amt = int(amt_parts[1])
                            
                            for num in numbers:
                                bets.append(f"{num:02d}-{base_amt}")
                                rev = reverse_number(num)
                                bets.append(f"{rev:02d}-{reverse_amt}")
                                total_amount += base_amt + reverse_amt
                            
                            # Check if there's a next part for additional reverse
                            if r_index + 1 < len(parts) and parts[r_index+1].isdigit():
                                extra_rev_amt = int(parts[r_index+1])
                                for num in numbers:
                                    rev = reverse_number(num)
                                    bets.append(f"{rev:02d}-{extra_rev_amt}")
                                    total_amount += extra_rev_amt
                                i += 1  # Skip extra amount
                                
                            i += 1
                            continue
            
            # Improved handling for formats like 12-34-56-100r200
            if '-' in entry and 'r' in entry:
                parts = entry.split('-')
                # Find the part with 'r'
                r_index = -1
                for j, part in enumerate(parts):
                    if 'r' in part:
                        r_index = j
                        break
                
                if r_index > 0:
                    numbers = []
                    for j in range(r_index):
                        if parts[j].isdigit():
                            num = int(parts[j])
                            if 0 <= num <= 99:
                                numbers.append(num)
                    
                    if parts[r_index].count('r') == 1:
                        amt_parts = parts[r_index].split('r')
                        if len(amt_parts) == 2 and amt_parts[0].isdigit() and amt_parts[1].isdigit():
                            base_amt = int(amt_parts[0])
                            reverse_amt = int(amt_parts[1])
                            
                            for num in numbers:
                                bets.append(f"{num:02d}-{base_amt}")
                                rev = reverse_number(num)
                                bets.append(f"{rev:02d}-{reverse_amt}")
                                total_amount += base_amt + reverse_amt
                            
                            # Check if there's a next part for additional reverse
                            if r_index + 1 < len(parts) and parts[r_index+1].isdigit():
                                extra_rev_amt = int(parts[r_index+1])
                                for num in numbers:
                                    rev = reverse_number(num)
                                    bets.append(f"{rev:02d}-{extra_rev_amt}")
                                    total_amount += extra_rev_amt
                                i += 1  # Skip extra amount
                                
                            i += 1
                            continue
            
            # Original parsing logic with improvements
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

        # Initialize ledger for this date if not exists
        if key not in ledger:
            ledger[key] = {}

        for bet in bets:
            num, amt = bet.split('-')
            num = int(num)
            amt = int(amt)
            
            # Update ledger for this date
            ledger[key][num] = ledger[key].get(num, 0) + amt
            
            # Update user data
            user_data[user.username][key].append((num, amt))

        if bets:
            response = "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
            keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{user.id}:{update.message.message_id}:{key}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            sent_message = await update.message.reply_text(response, reply_markup=reply_markup)
            message_store[(user.id, update.message.message_id)] = (sent_message.message_id, bets, total_amount, key)
        else:
            await update.message.reply_text("⚠️ အချက်အလက်များကိုစစ်ဆေးပါ")
            
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def delete_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, user_id_str, message_id_str, date_key = query.data.split(':')
        user_id = int(user_id_str)
        message_id = int(message_id_str)
        
        if query.from_user.id != admin_id:
            if (user_id, message_id) in message_store:
                sent_message_id, bets, total_amount, _ = message_store[(user_id, message_id)]
                response = "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
                keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{user_id}:{message_id}:{date_key}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text=f"❌ User များမဖျက်နိုင်ပါ၊ Admin ကိုဆက်သွယ်ပါ\n\n{response}",
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text("❌ User များမဖျက်နိုင်ပါ၊ Admin ကိုဆက်သွယ်ပါ")
            return
        
        keyboard = [
            [InlineKeyboardButton("✅ OK", callback_data=f"confirm_delete:{user_id}:{message_id}:{date_key}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_delete:{user_id}:{message_id}:{date_key}")]
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
        _, user_id_str, message_id_str, date_key = query.data.split(':')
        user_id = int(user_id_str)
        message_id = int(message_id_str)
        
        if (user_id, message_id) not in message_store:
            await query.edit_message_text("❌ ဒေတာမတွေ့ပါ")
            return
            
        sent_message_id, bets, total_amount, _ = message_store[(user_id, message_id)]
        
        username = None
        for uname, data in user_data.items():
            if date_key in data:
                for bet in data[date_key]:
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
            
            if date_key in ledger and num in ledger[date_key]:
                ledger[date_key][num] -= amt
                if ledger[date_key][num] <= 0:
                    del ledger[date_key][num]
                # Remove date from ledger if empty
                if not ledger[date_key]:
                    del ledger[date_key]
            
            if username in user_data and date_key in user_data[username]:
                user_data[username][date_key] = [
                    (n, a) for n, a in user_data[username][date_key] 
                    if not (n == num and a == amt)
                ]
                
                if not user_data[username][date_key]:
                    del user_data[username][date_key]
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
        _, user_id_str, message_id_str, date_key = query.data.split(':')
        user_id = int(user_id_str)
        message_id = int(message_id_str)
        
        if (user_id, message_id) in message_store:
            sent_message_id, bets, total_amount, _ = message_store[(user_id, message_id)]
            response = "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
            keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{user_id}:{message_id}:{date_key}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup)
        else:
            await query.edit_message_text("ℹ️ ဖျက်ခြင်းကိုပယ်ဖျက်လိုက်ပါပြီ")
            
    except Exception as e:
        logger.error(f"Error in cancel_delete: {str(e)}")
        await query.edit_message_text("❌ Error occurred while canceling deletion")

async def ledger_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, current_working_date
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Determine which date to show
        date_key = current_working_date if current_working_date else get_current_date_key()
        
        if date_key not in ledger:
            await update.message.reply_text(f"ℹ️ {date_key} အတွက် လက်ရှိတွင် လောင်းကြေးမရှိပါ")
            return
            
        lines = [f"📒 {date_key} လက်ကျန်ငွေစာရင်း"]
        ledger_data = ledger[date_key]
        
        for i in range(100):
            total = ledger_data.get(i, 0)
            if total > 0:
                if date_key in pnumber_per_date and i == pnumber_per_date[date_key]:
                    lines.append(f"🔴 {i:02d} ➤ {total} 🔴")
                else:
                    lines.append(f"{i:02d} ➤ {total}")
        
        if len(lines) == 1:
            await update.message.reply_text(f"ℹ️ {date_key} အတွက် လက်ရှိတွင် လောင်းကြေးမရှိပါ")
        else:
            if date_key in pnumber_per_date:
                pnum = pnumber_per_date[date_key]
                lines.append(f"\n🔴 Power Number: {pnum:02d} ➤ {ledger_data.get(pnum, 0)}")
            await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Error in ledger: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def break_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, break_limits, current_working_date
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Determine which date to work on
        date_key = current_working_date if current_working_date else get_current_date_key()
            
        if not context.args:
            if date_key in break_limits:
                await update.message.reply_text(f"ℹ️ Usage: /break [limit]\nℹ️ လက်ရှိတွင် break limit: {break_limits[date_key]}")
            else:
                await update.message.reply_text(f"ℹ️ Usage: /break [limit]\nℹ️ {date_key} အတွက် break limit မသတ်မှတ်ရသေးပါ")
            return
            
        try:
            new_limit = int(context.args[0])
            break_limits[date_key] = new_limit
            await update.message.reply_text(f"✅ {date_key} အတွက် Break limit ကို {new_limit} အဖြစ်သတ်မှတ်ပြီးပါပြီ")
            
            if date_key not in ledger:
                await update.message.reply_text(f"ℹ️ {date_key} အတွက် လောင်းကြေးမရှိသေးပါ")
                return
                
            ledger_data = ledger[date_key]
            msg = [f"📌 {date_key} အတွက် Limit ({new_limit}) ကျော်ဂဏန်းများ:"]
            found = False
            
            for num, amt in ledger_data.items():
                if amt > new_limit:
                    msg.append(f"{num:02d} ➤ {amt - new_limit}")
                    found = True
            
            if not found:
                await update.message.reply_text(f"ℹ️ {date_key} အတွက် ဘယ်ဂဏန်းမှ limit ({new_limit}) မကျော်ပါ")
            else:
                await update.message.reply_text("\n".join(msg))
                
        except ValueError:
            await update.message.reply_text("⚠️ Limit amount ထည့်ပါ (ဥပမာ: /break 5000)")
            
    except Exception as e:
        logger.error(f"Error in break: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def overbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, break_limits, current_working_date
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Determine which date to work on
        date_key = current_working_date if current_working_date else get_current_date_key()
            
        if not context.args:
            await update.message.reply_text("ℹ️ ကာဒိုင်အမည်ထည့်ပါ")
            return
            
        if date_key not in break_limits:
            await update.message.reply_text(f"⚠️ {date_key} အတွက် ကျေးဇူးပြု၍ /break [limit] ဖြင့် limit သတ်မှတ်ပါ")
            return
            
        if date_key not in ledger:
            await update.message.reply_text(f"ℹ️ {date_key} အတွက် လောင်းကြေးမရှိသေးပါ")
            return
            
        username = context.args[0]
        context.user_data['overbuy_username'] = username
        context.user_data['overbuy_date'] = date_key
        
        ledger_data = ledger[date_key]
        break_limit_val = break_limits[date_key]
        over_numbers = {num: amt - break_limit_val for num, amt in ledger_data.items() if amt > break_limit_val}
        
        if not over_numbers:
            await update.message.reply_text(f"ℹ️ {date_key} အတွက် ဘယ်ဂဏန်းမှ limit ({break_limit_val}) မကျော်ပါ")
            return
            
        if date_key not in overbuy_selections:
            overbuy_selections[date_key] = {}
        overbuy_selections[date_key][username] = over_numbers.copy()
        
        msg = [f"{username} ထံမှာတင်ရန်များ (Date: {date_key}, Limit: {break_limit_val}):"]
        buttons = []
        for num, amt in over_numbers.items():
            buttons.append([InlineKeyboardButton(f"{num:02d} ➤ {amt} {'✅' if num in overbuy_selections[date_key][username] else '⬜'}", 
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
        date_key = context.user_data.get('overbuy_date')
        
        if not username or not date_key:
            await query.edit_message_text("❌ Error: User or date not found")
            return
            
        if date_key not in overbuy_selections or username not in overbuy_selections[date_key]:
            await query.edit_message_text("❌ Error: Selection data not found")
            return
            
        if num in overbuy_selections[date_key][username]:
            del overbuy_selections[date_key][username][num]
        else:
            break_limit_val = break_limits[date_key]
            overbuy_selections[date_key][username][num] = ledger[date_key][num] - break_limit_val
            
        msg = [f"{username} ထံမှာတင်ရန်များ (Date: {date_key}):"]
        buttons = []
        for n, amt in overbuy_selections[date_key][username].items():
            buttons.append([InlineKeyboardButton(f"{n:02d} ➤ {amt} {'✅' if n in overbuy_selections[date_key][username] else '⬜'}", 
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
        date_key = context.user_data.get('overbuy_date')
        
        if not username or not date_key:
            await query.edit_message_text("❌ Error: User or date not found")
            return
            
        if date_key not in overbuy_selections:
            overbuy_selections[date_key] = {}
            
        break_limit_val = break_limits[date_key]
        ledger_data = ledger[date_key]
        overbuy_selections[date_key][username] = {
            num: amt - break_limit_val 
            for num, amt in ledger_data.items() 
            if amt > break_limit_val
        }
        
        msg = [f"{username} ထံမှာတင်ရန်များ (Date: {date_key}):"]
        buttons = []
        for num, amt in overbuy_selections[date_key][username].items():
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
        date_key = context.user_data.get('overbuy_date')
        
        if not username or not date_key:
            await query.edit_message_text("❌ Error: User or date not found")
            return
            
        if date_key not in overbuy_selections:
            overbuy_selections[date_key] = {}
            
        overbuy_selections[date_key][username] = {}
        
        break_limit_val = break_limits[date_key]
        ledger_data = ledger[date_key]
        over_numbers = {num: amt - break_limit_val for num, amt in ledger_data.items() if amt > break_limit_val}
        
        msg = [f"{username} ထံမှာတင်ရန်များ (Date: {date_key}):"]
        buttons = []
        for num, amt in over_numbers.items():
            buttons.append([InlineKeyboardButton(f"{num:02d} ➤ {amt} ⬜", 
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
        date_key = context.user_data.get('overbuy_date')
        
        if not username or not date_key:
            await query.edit_message_text("❌ Error: User or date not found")
            return
            
        if date_key not in overbuy_selections or username not in overbuy_selections[date_key]:
            await query.edit_message_text("❌ Error: Selection data not found")
            return
            
        selected_numbers = overbuy_selections[date_key][username]
        if not selected_numbers:
            await query.edit_message_text("⚠️ ဘာဂဏန်းမှမရွေးထားပါ")
            return
            
        if username not in user_data:
            user_data[username] = {}
        if date_key not in user_data[username]:
            user_data[username][date_key] = []
            
        total_amount = 0
        bets = []
        for num, amt in selected_numbers.items():
            user_data[username][date_key].append((num, -amt))
            bets.append(f"{num:02d}-{amt}")
            total_amount += amt
            
            # Update ledger
            ledger[date_key][num] = ledger[date_key].get(num, 0) - amt
            if ledger[date_key][num] <= 0:
                del ledger[date_key][num]
        
        # Initialize overbuy_list for date if needed
        if date_key not in overbuy_list:
            overbuy_list[date_key] = {}
        overbuy_list[date_key][username] = selected_numbers.copy()
        
        response = f"{username} - {date_key}\n" + "\n".join(bets) + f"\nစုစုပေါင်း {total_amount} ကျပ်"
        await query.edit_message_text(response)
        
    except Exception as e:
        logger.error(f"Error in overbuy_confirm: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def pnumber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, pnumber_per_date, current_working_date
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Determine which date to work on
        date_key = current_working_date if current_working_date else get_current_date_key()
            
        if not context.args:
            if date_key in pnumber_per_date:
                await update.message.reply_text(f"ℹ️ Usage: /pnumber [number]\nℹ️ {date_key} အတွက် Power Number: {pnumber_per_date[date_key]:02d}")
            else:
                await update.message.reply_text(f"ℹ️ Usage: /pnumber [number]\nℹ️ {date_key} အတွက် Power Number မသတ်မှတ်ရသေးပါ")
            return
            
        try:
            num = int(context.args[0])
            if num < 0 or num > 99:
                await update.message.reply_text("⚠️ ဂဏန်းကို 0 နှင့် 99 ကြားထည့်ပါ")
                return
                
            pnumber_per_date[date_key] = num
            await update.message.reply_text(f"✅ {date_key} အတွက် Power Number ကို {num:02d} အဖြစ်သတ်မှတ်ပြီး")
            
            # Show report for this date
            msg = []
            total_power = 0
            
            for user, records in user_data.items():
                if date_key in records:
                    user_total = 0
                    for bet_num, amt in records[date_key]:
                        if bet_num == num:
                            user_total += amt
                    if user_total > 0:
                        msg.append(f"{user}: {num:02d} ➤ {user_total}")
                        total_power += user_total
            
            if msg:
                msg.append(f"\n🔴 {date_key} အတွက် Power Number စုစုပေါင်း: {total_power}")
                await update.message.reply_text("\n".join(msg))
            else:
                await update.message.reply_text(f"ℹ️ {date_key} အတွက် {num:02d} အတွက် လောင်းကြေးမရှိပါ")
                
        except ValueError:
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
    global admin_id, current_working_date
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Determine which date to work on
        date_key = current_working_date if current_working_date else get_current_date_key()
            
        if date_key not in pnumber_per_date:
            await update.message.reply_text(f"⚠️ {date_key} အတွက် ကျေးဇူးပြု၍ /pnumber [number] ဖြင့် Power Number သတ်မှတ်ပါ")
            return
            
        if not user_data:
            await update.message.reply_text("ℹ️ လက်ရှိစာရင်းမရှိပါ")
            return
            
        pnum = pnumber_per_date[date_key]
        msg = [f"📊 {date_key} အတွက် စုပေါင်းရလဒ်"]
        total_net = 0
        
        for user, records in user_data.items():
            if date_key in records:
                user_total_amt = 0
                user_pamt = 0
                
                for num, amt in records[date_key]:
                    user_total_amt += amt
                    if num == pnum:
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
                    f"🔢 Power Number({pnum:02d}) ➤ {user_pamt}\n"
                    f"🎯 Za({za}) ➤ {win_amt}\n"
                    f"📈 ရလဒ်: {abs(net)} ({status})\n"
                    "-----------------"
                )
                msg.append(user_report)
                total_net += net

        if len(msg) > 1:
            msg.append(f"\n📊 စုစုပေါင်းရလဒ်: {abs(total_net)} ({'ဒိုင်အရှုံး' if total_net < 0 else 'ဒိုင်အမြတ်'})")
            await update.message.reply_text("\n".join(msg))
        else:
            await update.message.reply_text(f"ℹ️ {date_key} အတွက် ဒေတာမရှိပါ")
    except Exception as e:
        logger.error(f"Error in total: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def tsent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id, current_working_date
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Determine which date to work on
        date_key = current_working_date if current_working_date else get_current_date_key()
            
        if not user_data:
            await update.message.reply_text("ℹ️ လက်ရှိ user မရှိပါ")
            return
            
        for user in user_data:
            if date_key in user_data[user]:
                user_report = [f"👤 {user} - {date_key}:"]
                total_amt = 0
                
                for num, amt in user_data[user][date_key]:
                    user_report.append(f"  - {num:02d} ➤ {amt}")
                    total_amt += amt
                
                user_report.append(f"💵 စုစုပေါင်း: {total_amt}")
                await update.message.reply_text("\n".join(user_report))
        
        await update.message.reply_text(f"✅ {date_key} အတွက် စာရင်းများအားလုံး ပေးပို့ပြီးပါပြီ")
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
    global admin_id, user_data, ledger, za_data, com_data, date_control, overbuy_list, overbuy_selections, break_limits, pnumber_per_date, current_working_date
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
        break_limits = {}
        pnumber_per_date = {}
        current_working_date = get_current_date_key()
        
        await update.message.reply_text("✅ ဒေတာများအားလုံးကို ပြန်လည်သုတ်သင်ပြီး လက်ရှိနေ့သို့ပြန်လည်သတ်မှတ်ပြီးပါပြီ")
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
            
        # For non-admin, show current date only
        date_key = get_current_date_key() if not is_admin else None
        
        msg = [f"📊 {username} ရဲ့လောင်းကြေးမှတ်တမ်း"]
        total_amount = 0
        pnumber_total = 0
        
        if is_admin:
            # Admin can see all dates
            for date_key in user_data[username]:
                pnum = pnumber_per_date.get(date_key, None)
                pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
                
                msg.append(f"\n📅 {date_key}{pnum_str}:")
                for num, amt in user_data[username][date_key]:
                    if pnum is not None and num == pnum:
                        msg.append(f"🔴 {num:02d} ➤ {amt} 🔴")
                        pnumber_total += amt
                    else:
                        msg.append(f"{num:02d} ➤ {amt}")
                    total_amount += amt
        else:
            # Non-admin only sees current date
            if date_key in user_data[username]:
                pnum = pnumber_per_date.get(date_key, None)
                pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
                
                msg.append(f"\n📅 {date_key}{pnum_str}:")
                for num, amt in user_data[username][date_key]:
                    if pnum is not None and num == pnum:
                        msg.append(f"🔴 {num:02d} ➤ {amt} 🔴")
                        pnumber_total += amt
                    else:
                        msg.append(f"{num:02d} ➤ {amt}")
                    total_amount += amt
        
        if len(msg) > 1:
            msg.append(f"\n💵 စုစုပေါင်း: {total_amount}")
            if pnumber_total > 0:
                msg.append(f"🔴 Power Number စုစုပေါင်း: {pnumber_total}")
            await update.message.reply_text("\n".join(msg))
        else:
            await update.message.reply_text(f"ℹ️ {username} အတွက် စာရင်းမရှိပါ")
        
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
                pnum = pnumber_per_date.get(date_key, None)
                pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
                
                msg.append(f"\n📅 {date_key}{pnum_str}:")
                for num, amt in user_data[username][date_key]:
                    if pnum is not None and num == pnum:
                        msg.append(f"🔴 {num:02d} ➤ {amt} 🔴")
                        pnumber_total += amt
                    else:
                        msg.append(f"{num:02d} ➤ {amt}")
                    total_amount += amt
            
            if len(msg) > 1:
                msg.append(f"\n💵 စုစုပေါင်း: {total_amount}")
                if pnumber_total > 0:
                    msg.append(f"🔴 Power Number စုစုပေါင်း: {pnumber_total}")
                await query.edit_message_text("\n".join(msg))
            else:
                await query.edit_message_text(f"ℹ️ {username} အတွက် စာရင်းမရှိပါ")
        else:
            await query.edit_message_text(f"ℹ️ {username} အတွက် စာရင်း�မရှိပါ")
            
    except Exception as e:
        logger.error(f"Error in posthis_callback: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def dateall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Get all unique dates from user_data
        all_dates = get_available_dates()
        
        if not all_dates:
            await update.message.reply_text("ℹ️ မည်သည့်စာရင်းမှ မရှိသေးပါ")
            return
            
        # Initialize selection dictionary
        dateall_selections = {date: False for date in all_dates}
        context.user_data['dateall_selections'] = dateall_selections
        
        # Build message with checkboxes
        msg = ["📅 စာရင်းရှိသည့်နေ့ရက်များကို ရွေးချယ်ပါ:"]
        buttons = []
        
        for date in all_dates:
            pnum = pnumber_per_date.get(date, None)
            pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
            
            is_selected = dateall_selections[date]
            button_text = f"{date}{pnum_str} {'✅' if is_selected else '⬜'}"
            buttons.append([InlineKeyboardButton(button_text, callback_data=f"dateall_toggle:{date}")])
        
        buttons.append([InlineKeyboardButton("👁‍🗨 View", callback_data="dateall_view")])
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await update.message.reply_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in dateall: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def dateall_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, date_key = query.data.split(':')
        dateall_selections = context.user_data.get('dateall_selections', {})
        
        if date_key not in dateall_selections:
            await query.edit_message_text("❌ Error: Date not found")
            return
            
        # Toggle selection status
        dateall_selections[date_key] = not dateall_selections[date_key]
        context.user_data['dateall_selections'] = dateall_selections
        
        # Rebuild the message with updated selections
        msg = ["📅 စာရင်းရှိသည့်နေ့ရက်များကို ရွေးချယ်ပါ:"]
        buttons = []
        
        for date in dateall_selections.keys():
            pnum = pnumber_per_date.get(date, None)
            pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
            
            is_selected = dateall_selections[date]
            button_text = f"{date}{pnum_str} {'✅' if is_selected else '⬜'}"
            buttons.append([InlineKeyboardButton(button_text, callback_data=f"dateall_toggle:{date}")])
        
        buttons.append([InlineKeyboardButton("👁‍🗨 View", callback_data="dateall_view")])
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in dateall_toggle: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def dateall_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        dateall_selections = context.user_data.get('dateall_selections', {})
        
        # Get selected dates
        selected_dates = [date for date, selected in dateall_selections.items() if selected]
        
        if not selected_dates:
            await query.edit_message_text("⚠️ မည်သည့်နေ့ရက်ကိုမှ မရွေးချယ်ထားပါ")
            return
            
        # Aggregate data for each user across selected dates
        user_totals = {}
        overall_total = 0
        overall_power_total = 0
        
        for user in user_data:
            user_total_amt = 0
            user_pamt = 0
            
            for date in selected_dates:
                if user in user_data and date in user_data[user]:
                    # Get pnumber for this date if exists
                    pnum = pnumber_per_date.get(date, None)
                    
                    for num, amt in user_data[user][date]:
                        user_total_amt += amt
                        if pnum is not None and num == pnum:
                            user_pamt += amt
            
            if user_total_amt > 0:
                user_totals[user] = {
                    'total': user_total_amt,
                    'power_total': user_pamt
                }
                overall_total += user_total_amt
                overall_power_total += user_pamt
        
        # Build report
        msg = ["📊 ရွေးချယ်ထားသည့် နေ့ရက်များ စုပေါင်းရလဒ်:"]
        msg.append(f"📅 နေ့ရက်များ: {', '.join(selected_dates)}\n")
        
        # Add overbuy data
        for date in selected_dates:
            if date in overbuy_list and user in overbuy_list[date]:
                if user not in user_totals:
                    user_totals[user] = {'total': 0, 'power_total': 0}
                
                overbuy_data = overbuy_list[date][user]
                if overbuy_data:
                    msg.append(f"👤 {user} - {date} Overbuy:")
                    for num, amt in overbuy_data.items():
                        msg.append(f"  - {num:02d} ➤ {amt}")
                    msg.append("")
        
        for user, data in user_totals.items():
            msg.append(f"👤 {user}:")
            msg.append(f"  💵 စုစုပေါင်း: {data['total']}")
            msg.append(f"  🔴 Power Number စုစုပေါင်း: {data['power_total']}")
            msg.append("")
        
        if user_totals:
            msg.append(f"📊 စုစုပေါင်း:")
            msg.append(f"  💵 လောင်းကြေးစုစုပေါင်း: {overall_total}")
            msg.append(f"  🔴 Power Number စုစုပေါင်း: {overall_power_total}")
            await query.edit_message_text("\n".join(msg))
        else:
            await query.edit_message_text("ℹ️ ရွေးချယ်ထားသည့် နေ့ရက်များတွင် ဒေတာမရှိပါ")
        
    except Exception as e:
        logger.error(f"Error in dateall_view: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def change_working_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
        
        # Show calendar with AM/PM selection
        keyboard = [
            [InlineKeyboardButton("🗓 လက်ရှိလအတွက် ပြက္ခဒိန်", callback_data="cdate_calendar")],
            [InlineKeyboardButton("⏰ AM ရွေးရန်", callback_data="cdate_am")],
            [InlineKeyboardButton("🌙 PM ရွေးရန်", callback_data="cdate_pm")],
            [InlineKeyboardButton("📆 ယနေ့ဖွင့်ရန်", callback_data="cdate_open")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👉 လက်ရှိ အလုပ်လုပ်ရမည့်နေ့ရက်ကို ရွေးချယ်ပါ\n"
            "• ပြက္ခဒိန်ဖြင့်ရွေးရန်: 🗓 ခလုတ်ကိုနှိပ်ပါ\n"
            "• AM သို့ပြောင်းရန်: ⏰ ခလုတ်ကိုနှိပ်ပါ\n"
            "• PM သို့ပြောင်းရန်: 🌙 ခလုတ်ကိုနှိပ်ပါ\n"
            "• ယနေ့သို့ပြန်ရန်: 📆 ခလုတ်ကိုနှိပ်ပါ",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in change_working_date: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def show_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        now = datetime.now(MYANMAR_TIMEZONE)
        year, month = now.year, now.month
        
        # Create calendar header
        cal_header = calendar.month_name[month] + " " + str(year)
        days = ["တနင်္လာ", "အင်္ဂါ", "ဗုဒ္ဓဟူး", "ကြာသပတေး", "သောကြာ", "စနေ", "တနင်္ဂနွေ"]
        
        # Generate calendar days
        cal = calendar.monthcalendar(year, month)
        keyboard = []
        keyboard.append([InlineKeyboardButton(cal_header, callback_data="ignore")])
        keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in days])
        
        for week in cal:
            week_buttons = []
            for day in week:
                if day == 0:
                    week_buttons.append(InlineKeyboardButton(" ", callback_data="ignore"))
                else:
                    date_str = f"{day:02d}/{month:02d}/{year}"
                    week_buttons.append(InlineKeyboardButton(str(day), callback_data=f"cdate_day:{date_str}"))
            keyboard.append(week_buttons)
        
        # Add navigation and back buttons
        keyboard.append([
            InlineKeyboardButton("⬅️ ယခင်", callback_data="cdate_prev_month"),
            InlineKeyboardButton("➡️ နောက်", callback_data="cdate_next_month")
        ])
        keyboard.append([InlineKeyboardButton("🔙 နောက်သို့", callback_data="cdate_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🗓 နေ့ရက်ရွေးရန် ပြက္ခဒိန်", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in show_calendar: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def handle_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, date_str = query.data.split(':')
        context.user_data['selected_date'] = date_str
        
        # Ask for AM/PM selection
        keyboard = [
            [InlineKeyboardButton("⏰ AM", callback_data="cdate_set_am")],
            [InlineKeyboardButton("🌙 PM", callback_data="cdate_set_pm")],
            [InlineKeyboardButton("🔙 နောက်သို့", callback_data="cdate_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"👉 {date_str} အတွက် အချိန်ပိုင်းရွေးပါ",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_day_selection: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def set_am_pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        global current_working_date
        time_segment = "AM" if "am" in query.data else "PM"
        date_str = context.user_data.get('selected_date', '')
        
        if not date_str:
            await query.edit_message_text("❌ Error: Date not selected")
            return
            
        current_working_date = f"{date_str} {time_segment}"
        await query.edit_message_text(f"✅ လက်ရှိ အလုပ်လုပ်ရမည့်နေ့ရက်ကို {current_working_date} အဖြစ်ပြောင်းလိုက်ပါပြီ")
        
    except Exception as e:
        logger.error(f"Error in set_am_pm: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def set_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_working_date
    try:
        if current_working_date:
            date_part = current_working_date.split()[0]
            current_working_date = f"{date_part} AM"
            await update.callback_query.edit_message_text(f"✅ လက်ရှိ အလုပ်လုပ်ရမည့်နေ့ရက်ကို {current_working_date} အဖြစ်ပြောင်းလိုက်ပါပြီ")
        else:
            await update.callback_query.edit_message_text("❌ လက်ရှိနေ့ရက် သတ်မှတ်ထားခြင်းမရှိပါ")
    except Exception as e:
        logger.error(f"Error in set_am: {str(e)}")
        await update.callback_query.edit_message_text("❌ Error occurred")

async def set_pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_working_date
    try:
        if current_working_date:
            date_part = current_working_date.split()[0]
            current_working_date = f"{date_part} PM"
            await update.callback_query.edit_message_text(f"✅ လက်ရှိ အလုပ်လုပ်ရမည့်နေ့ရက်ကို {current_working_date} အဖြစ်ပြောင်းလိုက်ပါပြီ")
        else:
            await update.callback_query.edit_message_text("❌ လက်ရှိနေ့ရက် သတ်မှတ်ထားခြင်းမရှိပါ")
    except Exception as e:
        logger.error(f"Error in set_pm: {str(e)}")
        await update.callback_query.edit_message_text("❌ Error occurred")

async def open_current_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        global current_working_date
        current_working_date = get_current_date_key()
        await query.edit_message_text(f"✅ လက်ရှိ အလုပ်လုပ်ရမည့်နေ့ရက်ကို {current_working_date} အဖြစ်ပြောင်းလိုက်ပါပြီ")
    except Exception as e:
        logger.error(f"Error in open_current_date: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def navigate_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Placeholder for month navigation
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("ℹ️ လများလှန်ကြည့်ခြင်းအား နောက်ထပ်ဗားရှင်းတွင် ထည့်သွင်းပါမည်")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await change_working_date(update, context)

async def delete_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        # Get all available dates
        available_dates = get_available_dates()
        
        if not available_dates:
            await update.message.reply_text("ℹ️ မည်သည့်စာရင်းမှ မရှိသေးပါ")
            return
            
        # Initialize selection dictionary
        datedelete_selections = {date: False for date in available_dates}
        context.user_data['datedelete_selections'] = datedelete_selections
        
        # Build message with checkboxes
        msg = ["🗑 ဖျက်လိုသောနေ့ရက်များကို ရွေးချယ်ပါ:"]
        buttons = []
        
        for date in available_dates:
            pnum = pnumber_per_date.get(date, None)
            pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
            
            is_selected = datedelete_selections[date]
            button_text = f"{date}{pnum_str} {'✅' if is_selected else '⬜'}"
            buttons.append([InlineKeyboardButton(button_text, callback_data=f"datedelete_toggle:{date}")])
        
        buttons.append([InlineKeyboardButton("✅ Delete Selected", callback_data="datedelete_confirm")])
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await update.message.reply_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in delete_date: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def datedelete_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, date_key = query.data.split(':')
        datedelete_selections = context.user_data.get('datedelete_selections', {})
        
        if date_key not in datedelete_selections:
            await query.edit_message_text("❌ Error: Date not found")
            return
            
        # Toggle selection status
        datedelete_selections[date_key] = not datedelete_selections[date_key]
        context.user_data['datedelete_selections'] = datedelete_selections
        
        # Rebuild the message with updated selections
        msg = ["🗑 ဖျက်လိုသောနေ့ရက်များကို ရွေးချယ်ပါ:"]
        buttons = []
        
        for date in datedelete_selections.keys():
            pnum = pnumber_per_date.get(date, None)
            pnum_str = f" [P: {pnum:02d}]" if pnum is not None else ""
            
            is_selected = datedelete_selections[date]
            button_text = f"{date}{pnum_str} {'✅' if is_selected else '⬜'}"
            buttons.append([InlineKeyboardButton(button_text, callback_data=f"datedelete_toggle:{date}")])
        
        buttons.append([InlineKeyboardButton("✅ Delete Selected", callback_data="datedelete_confirm")])
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_text("\n".join(msg), reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in datedelete_toggle: {str(e)}")
        await query.edit_message_text("❌ Error occurred")

async def datedelete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        datedelete_selections = context.user_data.get('datedelete_selections', {})
        
        # Get selected dates
        selected_dates = [date for date, selected in datedelete_selections.items() if selected]
        
        if not selected_dates:
            await query.edit_message_text("⚠️ မည်သည့်နေ့ရက်ကိုမှ မရွေးချယ်ထားပါ")
            return
            
        # Delete data for selected dates
        for date_key in selected_dates:
            # Remove from user_data
            for user in list(user_data.keys()):
                if date_key in user_data[user]:
                    del user_data[user][date_key]
                # Remove user if no dates left
                if not user_data[user]:
                    del user_data[user]
            
            # Remove from ledger
            if date_key in ledger:
                del ledger[date_key]
            
            # Remove from break_limits
            if date_key in break_limits:
                del break_limits[date_key]
            
            # Remove from pnumber_per_date
            if date_key in pnumber_per_date:
                del pnumber_per_date[date_key]
            
            # Remove from date_control
            if date_key in date_control:
                del date_control[date_key]
            
            # Remove from overbuy_list
            if date_key in overbuy_list:
                del overbuy_list[date_key]
            
            # Remove from overbuy_selections
            if date_key in overbuy_selections:
                del overbuy_selections[date_key]
        
        # Clear current working date if it was deleted
        global current_working_date
        if current_working_date in selected_dates:
            current_working_date = None
        
        await query.edit_message_text(f"✅ အောက်ပါနေ့ရက်များ ဖျက်ပြီးပါပြီ:\n{', '.join(selected_dates)}")
        
    except Exception as e:
        logger.error(f"Error in datedelete_confirm: {str(e)}")
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
    app.add_handler(CommandHandler("dateall", dateall))
    app.add_handler(CommandHandler("Cdate", change_working_date))
    app.add_handler(CommandHandler("Ddate", delete_date))

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
    app.add_handler(CallbackQueryHandler(dateall_toggle, pattern=r"^dateall_toggle:"))
    app.add_handler(CallbackQueryHandler(dateall_view, pattern=r"^dateall_view$"))
    
    # New calendar handlers
    app.add_handler(CallbackQueryHandler(show_calendar, pattern=r"^cdate_calendar$"))
    app.add_handler(CallbackQueryHandler(handle_day_selection, pattern=r"^cdate_day:"))
    app.add_handler(CallbackQueryHandler(set_am, pattern=r"^cdate_am$"))
    app.add_handler(CallbackQueryHandler(set_pm, pattern=r"^cdate_pm$"))
    app.add_handler(CallbackQueryHandler(set_am_pm, pattern=r"^cdate_set_am$|^cdate_set_pm$"))
    app.add_handler(CallbackQueryHandler(open_current_date, pattern=r"^cdate_open$"))
    app.add_handler(CallbackQueryHandler(navigate_month, pattern=r"^cdate_prev_month$|^cdate_next_month$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern=r"^cdate_back$"))
    
    app.add_handler(CallbackQueryHandler(datedelete_toggle, pattern=r"^datedelete_toggle:"))
    app.add_handler(CallbackQueryHandler(datedelete_confirm, pattern=r"^datedelete_confirm$"))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, comza_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Bot is starting...")
    app.run_polling()
