import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from datetime import datetime, time

# Environment variable မှ token ကိုဖတ်ရန်
TOKEN = os.getenv("BOT_TOKEN")

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Globals
admin_id = None
user_data = {}
ledger = {}
za_data = {}
com_data = {}
pnumber_value = None
date_control = {}
overbuy_list = {}

# Utility
def reverse_number(n):
    s = str(n).zfill(2)
    return int(s[::-1])

def get_time_segment():
    now = datetime.now().time()
    return "AM" if now < time(12, 0) else "PM"

def get_current_date_key():
    now = datetime.now()
    return f"{now.strftime('%d/%m/%Y')} {get_time_segment()}"

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    admin_id = update.effective_user.id
    await update.message.reply_text("🤖 Bot started.")

async def dateopen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_current_date_key()
    date_control[key] = True
    await update.message.reply_text(f"{key} စာရင်းဖွင့်ပြီးပါပြီ")

async def dateclose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = get_current_date_key()
    date_control[key] = False
    await update.message.reply_text(f"{key} စာရင်းပိတ်လိုက်ပါပြီ")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user.username:
        await update.message.reply_text("ကျေးဇူးပြု၍ Telegram username သတ်မှတ်ပါ")
        return

    key = get_current_date_key()
    if not date_control.get(key, False):
        await update.message.reply_text("စာရင်းပိတ်ထားပါသည်")
        return

    text = update.message.text
    entries = text.split()
    added = 0
    bets = []

    if user.username not in user_data:
        user_data[user.username] = {}
    if key not in user_data[user.username]:
        user_data[user.username][key] = []

    i = 0
    while i < len(entries):
        entry = entries[i]
        
        # အထူးစနစ်များအတွက် သတ်မှတ်ချက်များ
        fixed_special_cases = {
            "အပူး": [0, 11, 22, 33, 44, 55, 66, 77, 88, 99],
            "ပါဝါ": [5, 16, 27, 38, 49, 50, 61, 72, 83, 94],
            "နက္ခ": [7, 18, 24, 35, 42, 53, 69, 70, 81, 96],
            "ညီကို": [1, 12, 23, 34, 45, 56, 67, 78, 89, 90],
            "ကိုညီ": [9, 10, 21, 32, 43, 54, 65, 76, 87, 98],
        }
        
        # ပုံမှန်အထူးစနစ်များကို စီမံခြင်း
        if entry in fixed_special_cases:
            if i+1 < len(entries) and entries[i+1].isdigit():
                amt = int(entries[i+1])
                for num in fixed_special_cases[entry]:
                    bets.append((num, amt))
                i += 2
                continue
        
        # ထိပ်/ပိတ်/ဘရိတ်/အပါ စနစ်များအတွက်
        dynamic_types = ["ထိပ်", "ပိတ်", "ဘရိတ်", "အပါ"]
        found_dynamic = False
        for dtype in dynamic_types:
            if entry.endswith(dtype):
                prefix = entry[:-len(dtype)]
                if prefix.isdigit():
                    digit_val = int(prefix)
                    if 0 <= digit_val <= 9:
                        # ဂဏန်းများကို ထုတ်ယူခြင်း
                        if dtype == "ထိပ်":
                            numbers = [digit_val * 10 + j for j in range(10)]  # 40-49
                        elif dtype == "ပိတ်":
                            numbers = [j * 10 + digit_val for j in range(10)]  # 05,15,...,95
                        elif dtype == "ဘရိတ်":
                            numbers = [n for n in range(100) if (n//10 + n%10) % 10 == digit_val]
                        elif dtype == "အပါ":
                            tens = [digit_val * 10 + j for j in range(10)]
                            units = [j * 10 + digit_val for j in range(10)]
                            numbers = list(set(tens + units))
                        
                        # ပမာဏထည့်သွင်းခြင်း
                        if i+1 < len(entries) and entries[i+1].isdigit():
                            amt = int(entries[i+1])
                            for num in numbers:
                                bets.append((num, amt))
                            i += 2
                            found_dynamic = True
                        break
        if found_dynamic:
            continue
        
        # အခွေစနစ်များ
        if entry.endswith('အခွေ') or entry.endswith('အပူးပါအခွေ'):
            base = entry[:-3] if entry.endswith('အခွေ') else entry[:-8]
            if base.isdigit():
                digits = [int(d) for d in base]
                pairs = []
                # ပုံမှန်အတွဲများ
                for j in range(len(digits)):
                    for k in range(len(digits)):
                        if j != k:
                            combo = digits[j] * 10 + digits[k]
                            if combo not in pairs:  # ထပ်နေတာကို ရှောင်ဖို့
                                pairs.append(combo)
                # အပူးပါအခွေအတွက် နှစ်ခါပါဂဏန်းများ
                if entry.endswith('အပူးပါအခွေ'):
                    for d in digits:
                        double = d * 10 + d
                        if double not in pairs:  # ထပ်နေတာကို ရှောင်ဖို့
                            pairs.append(double)
                if i+1 < len(entries) and entries[i+1].isdigit():
                    amt = int(entries[i+1])
                    for num in pairs:
                        bets.append((num, amt))
                    i += 2
                    continue
        
        # r ပါသောပုံစံများ (03r1000, 23r1000)
        if 'r' in entry:
            parts = entry.split('r')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                num = int(parts[0])
                amt = int(parts[1])
                rev = reverse_number(num)
                bets.append((num, amt))
                bets.append((rev, amt))
                i += 1
                continue
        
        # ပုံမှန်ဂဏန်းများ (22-500 or 44 500)
        if '-' in entry:
            parts = entry.split('-')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                num = int(parts[0])
                amt = int(parts[1])
                bets.append((num, amt))
                i += 1
                continue
        
        # ဂဏန်းအုပ်စုများ (22 23 34 500)
        if entry.isdigit():
            num = int(entry)
            # r ပါသော ပမာဏကို စစ်ဆေးခြင်း (1000r500)
            if i+1 < len(entries) and 'r' in entries[i+1]:
                r_parts = entries[i+1].split('r')
                if len(r_parts) == 2 and r_parts[0].isdigit() and r_parts[1].isdigit():
                    amt1 = int(r_parts[0])
                    amt2 = int(r_parts[1])
                    bets.append((num, amt1))
                    bets.append((reverse_number(num), amt2))
                    i += 2
                    continue
            # ပုံမှန်ပမာဏ
            if i+1 < len(entries) and entries[i+1].isdigit():
                amt = int(entries[i+1])
                bets.append((num, amt))
                i += 2
                continue
            # ပမာဏမပါသော ဂဏန်းများ
            bets.append((num, 500))
            i += 1
            continue
        
        i += 1

    # စာရင်းသွင်းခြင်းနှင့် စုစုပေါင်းတွက်ချက်ခြင်း
    for (num, amt) in bets:
        if 0 <= num <= 99:
            ledger[num] = ledger.get(num, 0) + amt
            user_data[user.username][key].append((num, amt))
            added += amt

    if added > 0:
        await update.message.reply_text(f"{added} လို")
    else:
        await update.message.reply_text("အချက်အလက်များကိုစစ်ဆေးပါ")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
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

    app.add_handler(CallbackQueryHandler(comza_input, pattern=r"^comza:"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), comza_text))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.run_polling()
