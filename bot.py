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
logger = logging.getLogger(__name__)

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
    logger.info(f"Admin set to: {admin_id}")
    await update.message.reply_text("🤖 Bot started. Admin privileges granted!")

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
        logger.info(f"Message from {user.username}: {update.message.text}")
        
        if not user.username:
            await update.message.reply_text("❌ ကျေးဇူးပြု၍ Telegram username သတ်မှတ်ပါ")
            return

        key = get_current_date_key()
        if not date_control.get(key, False):
            await update.message.reply_text("❌ စာရင်းပိတ်ထားပါသည်")
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
            logger.info(f"Processing entry: {entry}")
            
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
                    logger.info(f"Special case {entry} with amount {amt}")
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
                                numbers = [digit_val * 10 + j for j in range(10)]
                            elif dtype == "ပိတ်":
                                numbers = [j * 10 + digit_val for j in range(10)]
                            elif dtype == "ဘရိတ်":
                                numbers = [n for n in range(100) if (n//10 + n%10) % 10 == digit_val]
                            elif dtype == "အပါ":
                                tens = [digit_val * 10 + j for j in range(10)]
                                units = [j * 10 + digit_val for j in range(10)]
                                numbers = list(set(tens + units))
                            
                            # ပမာဏထည့်သွင်းခြင်း
                            if i+1 < len(entries) and entries[i+1].isdigit():
                                amt = int(entries[i+1])
                                logger.info(f"Dynamic {dtype} {digit_val} with amount {amt}")
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
                                if combo not in pairs:
                                    pairs.append(combo)
                    # အပူးပါအခွေအတွက် နှစ်ခါပါဂဏန်းများ
                    if entry.endswith('အပူးပါအခွေ'):
                        for d in digits:
                            double = d * 10 + d
                            if double not in pairs:
                                pairs.append(double)
                    if i+1 < len(entries) and entries[i+1].isdigit():
                        amt = int(entries[i+1])
                        logger.info(f"Box system {entry} with amount {amt}")
                        for num in pairs:
                            bets.append((num, amt))
                        i += 2
                        continue
            
            # r ပါသောပုံစံများ
            if 'r' in entry:
                parts = entry.split('r')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    num = int(parts[0])
                    amt = int(parts[1])
                    rev = reverse_number(num)
                    logger.info(f"r system: {num} and {rev} with {amt}")
                    bets.append((num, amt))
                    bets.append((rev, amt))
                    i += 1
                    continue
            
            # ပုံမှန်ဂဏန်းများ
            if '-' in entry:
                parts = entry.split('-')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    num = int(parts[0])
                    amt = int(parts[1])
                    logger.info(f"Normal entry: {num} with {amt}")
                    bets.append((num, amt))
                    i += 1
                    continue
            
            # ဂဏန်းအုပ်စုများ
            if entry.isdigit():
                num = int(entry)
                # r ပါသော ပမာဏကို စစ်ဆေးခြင်း
                if i+1 < len(entries) and 'r' in entries[i+1]:
                    r_parts = entries[i+1].split('r')
                    if len(r_parts) == 2 and r_parts[0].isdigit() and r_parts[1].isdigit():
                        amt1 = int(r_parts[0])
                        amt2 = int(r_parts[1])
                        rev = reverse_number(num)
                        logger.info(f"Group with r: {num} ({amt1}), {rev} ({amt2})")
                        bets.append((num, amt1))
                        bets.append((rev, amt2))
                        i += 2
                        continue
                # ပုံမှန်ပမာဏ
                if i+1 < len(entries) and entries[i+1].isdigit():
                    amt = int(entries[i+1])
                    logger.info(f"Group: {num} with {amt}")
                    bets.append((num, amt))
                    i += 2
                    continue
                # ပမာဏမပါသော ဂဏန်းများ
                logger.info(f"Single number: {num} with default 500")
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
            await update.message.reply_text(f"✅ {added} လို")
        else:
            await update.message.reply_text("⚠️ အချက်အလက်များကိုစစ်ဆေးပါ")
            
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def ledger_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        lines = ["📒 Ledger Summary"]
        for i in range(100):
            total = ledger.get(i, 0)
            if total > 0:
                lines.append(f"{i:02d} ➤ {total}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Error in ledger: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ... (ကျန်သော command များကို try-except ထည့်ပြီး logging ထည့်ထားပါမည်)

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is not set")
        
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
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Bot is starting...")
    app.run_polling()
