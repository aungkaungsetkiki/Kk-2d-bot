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
    """ဂဏန်းကိုပြောင်းပြန်လှန်ပေးခြင်း (23 -> 32)"""
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
    try:
        admin_id = update.effective_user.id
        logger.info(f"Admin set to: {admin_id}")
        await update.message.reply_text("🤖 Bot started. Admin privileges granted!")
    except Exception as e:
        logger.error(f"Error in start: {str(e)}")
        await update.message.reply_text("❌ Bot initialization failed")

async def dateopen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        key = get_current_date_key()
        date_control[key] = True
        logger.info(f"Ledger opened for {key}")
        await update.message.reply_text(f"✅ {key} စာရင်းဖွင့်ပြီးပါပြီ")
    except Exception as e:
        logger.error(f"Error in dateopen: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def dateclose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        key = get_current_date_key()
        date_control[key] = False
        logger.info(f"Ledger closed for {key}")
        await update.message.reply_text(f"✅ {key} စာရင်းပိတ်လိုက်ပါပြီ")
    except Exception as e:
        logger.error(f"Error in dateclose: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

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

        entries = text.split()
        added = 0
        bets = []

        if user.username not in user_data:
            user_data[user.username] = {}
        if key not in user_data[user.username]:
            user_data[user.username][key] = []

        # ========== Multi-number format handling ==========
        # ဂဏန်းအများကြီးနဲ့ ပမာဏတစ်ခု (12 25 36 15 48 69 50 25 36 40 400)
        if len(entries) > 1 and entries[-1].isdigit():
            amount = int(entries[-1])
            numbers = []
            
            for token in entries[:-1]:
                if token.isdigit() and 0 <= int(token) <= 99:
                    numbers.append(int(token))
            
            if numbers and amount > 0:
                for num in numbers:
                    bets.append((num, amount))
                i = len(entries)
            else:
                i = 0
        # Reverse multi-number format (12 34 56r1000)
        elif len(entries) > 1 and any('r' in token for token in entries):
            # Find the last reverse token
            reverse_token = None
            for idx, token in enumerate(entries):
                if 'r' in token:
                    reverse_token = (idx, token)
            
            if reverse_token:
                idx, token = reverse_token
                parts = token.split('r')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    amount = int(parts[1])
                    numbers = []
                    
                    # Collect all numbers except the reverse token
                    for j in range(len(entries)):
                        if j != idx and entries[j].isdigit() and 0 <= int(entries[j]) <= 99:
                            numbers.append(int(entries[j]))
                    
                    # Add the number from the reverse token
                    numbers.append(int(parts[0]))
                    
                    if numbers and amount > 0:
                        for num in numbers:
                            bets.append((num, amount))
                            bets.append((reverse_number(num), amount))
                        i = len(entries)
                    else:
                        i = 0
                else:
                    i = 0
            else:
                i = 0
        else:
            i = 0

        # Process individual tokens
        while i < len(entries):
            entry = entries[i]
            
            # အထူးစနစ်များ (အပူး, ပါဝါ, နက္ခ, ညီကို, ကိုညီ)
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
                else:
                    i += 1
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
                                for num in numbers:
                                    bets.append((num, amt))
                                i += 2
                                found_dynamic = True
                            else:
                                i += 1
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
                        for num in pairs:
                            bets.append((num, amt))
                        i += 2
                        continue
                    else:
                        i += 1
                        continue
                else:
                    i += 1
                    continue
            
            # r ပါသောပုံစံများ
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
                else:
                    i += 1
                    continue
            
            # ပုံမှန်ဂဏန်းများ
            if '-' in entry:
                parts = entry.split('-')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    num = int(parts[0])
                    amt = int(parts[1])
                    bets.append((num, amt))
                    i += 1
                    continue
                else:
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
                        bets.append((num, amt1))
                        bets.append((rev, amt2))
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
            
            # မညီမညာဖြစ်သောအချက်အလက်များကို skip လုပ်ခြင်း
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
        lines = ["📒 လက်ကျန်ငွေစာရင်း"]
        for i in range(100):
            total = ledger.get(i, 0)
            if total > 0:
                lines.append(f"{i:02d} ➤ {total}")
        
        if len(lines) == 1:
            await update.message.reply_text("ℹ️ လက်ရှိတွင် လောင်းကြေးမရှိပါ")
        else:
            await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Error in ledger: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def break_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not context.args:
            await update.message.reply_text("ℹ️ Usage: /break [limit]")
            return
            
        limit = int(context.args[0])
        msg = ["📌 Limit ကျော်ဂဏန်းများ:"]
        for k, v in ledger.items():
            if v > limit:
                msg.append(f"{k:02d} ➤ {v - limit}")
        
        if len(msg) == 1:
            await update.message.reply_text("ℹ️ ဘယ်ဂဏန်းမှ limit မကျော်ပါ")
        else:
            await update.message.reply_text("\n".join(msg))
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Limit amount ထည့်ပါ (ဥပမာ: /break 5000)")
    except Exception as e:
        logger.error(f"Error in break: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def overbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global admin_id
    try:
        if update.effective_user.id != admin_id:
            await update.message.reply_text("❌ Admin only command")
            return
            
        if not context.args:
            await update.message.reply_text("ℹ️ Usage: /overbuy [username]")
            return
            
        user = context.args[0]
        overbuy_list[user] = ledger.copy()
        await update.message.reply_text(f"✅ {user} အတွက် overbuy စာရင်းပြထားပါတယ်")
    except Exception as e:
        logger.error(f"Error in overbuy: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

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
            # No selected user, process as normal bet
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
            await update.message.reply_text("ℹ️ ကျေးဇူးပြု၍ /pnumber ဖြင့် power number သတ်မှတ်ပါ")
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

        # Grand total
        grand_status = "ဒိုင်အရှုံး" if total_net < 0 else "ဒိုင်အမြတ်"
        msg.append(f"\n📊 စုစုပေါင်းရလဒ်: {abs(total_net)} ({grand_status})")

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
    global admin_id, user_data, ledger, za_data, com_data, date_control, overbuy_list
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
        
        await update.message.reply_text("✅ ဒေတာများအားလုံးကို ပြန်လည်သုတ်သင်ပြီးပါပြီ")
    except Exception as e:
        logger.error(f"Error in reset_data: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

# Main
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
    app.add_handler(CommandHandler("reset", reset_data))

    # Callback and message handlers
    app.add_handler(CallbackQueryHandler(comza_input, pattern=r"^comza:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, comza_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Bot is starting...")
    app.run_polling()
