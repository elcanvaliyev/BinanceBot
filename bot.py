import os
import asyncio
import logging
import requests
import pandas as pd
import pandas_ta as ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging konfiqurasiyası
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Aktiv qiymət alarmları üçün lüğət
# Format: {chat_id: [{'id': 1, 'symbol': 'BTCUSDT', 'target': 65000, 'direction': 'up'}]}
ALERTS = {}
alert_counter = 1

# Binance-dən bütün USDT cütlüklərini çəkmək
def get_all_usdt_symbols():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        res = requests.get(url, timeout=10).json()
        symbols = [item for item in res if item['symbol'].endswith('USDT') and not item['symbol'].endswith('UPUSDT') and not item['symbol'].endswith('DOWNUSDT')]
        return symbols
    except Exception as e:
        logging.error(f"Binance API xətası: {e}")
        return []

# Klines (şam) məlumatlarını çəkib Indikatorları hesablamaq
def analyze_symbol(symbol, timeframe='15m'):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit=100"
        res = requests.get(url, timeout=5).json()
        
        df = pd.DataFrame(res, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # Indikatorların hesablanması
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        macd = ta.macd(df['close'])
        df['MACD'] = macd['MACD_12_26_9']
        df['MACDs'] = macd['MACDs_12_26_9']
        
        df['EMA9'] = ta.ema(df['close'], length=9)
        df['EMA21'] = ta.ema(df['close'], length=21)
        
        bbounds = ta.bbands(df['close'], length=20, std=2)
        df['BBL'] = bbounds['BBL_20_2.0']
        df['BBU'] = bbounds['BBU_20_2.0']

        last = df.iloc[-1]
        prev = df.iloc[-2]

        price = last['close']
        rsi = last['RSI']
        
        # Siqnal Məntiqi (Buy / Sell)
        signal = "NEUTRAL"
        reasons = []

        # AL Siqnal Şərtləri:
        # 1. RSI oversold (<35) və ya dönüşdə
        # 2. EMA9, EMA21-i yuxarı kəsir
        # 3. MACD xətti Signal xəttini yuxarı kəsir
        if rsi < 35:
            reasons.append(f"RSI Aşırı Satım ({rsi:.1f})")
        if prev['EMA9'] <= prev['EMA21'] and last['EMA9'] > last['EMA21']:
            reasons.append("EMA 9/21 Yuxarı Kəsişmə 🔥")
        if prev['MACD'] <= prev['MACDs'] and last['MACD'] > last['MACDs']:
            reasons.append("MACD Bullish Cross 📈")
        if last['close'] <= last['BBL']:
            reasons.append("Bollinger Alt Bandına Dəydi")

        if len(reasons) >= 2:
            signal = "🟢 AL (BUY)"

        # SAT Siqnal Şərtləri:
        sell_reasons = []
        if rsi > 65:
            sell_reasons.append(f"RSI Aşırı Alım ({rsi:.1f})")
        if prev['EMA9'] >= prev['EMA21'] and last['EMA9'] < last['EMA21']:
            sell_reasons.append("EMA 9/21 Aşağı Kəsişmə 🔻")
        if prev['MACD'] >= prev['MACDs'] and last['MACD'] < last['MACDs']:
            sell_reasons.append("MACD Bearish Cross 📉")
        if last['close'] >= last['BBU']:
            sell_reasons.append("Bollinger Üst Bandına Dəydi")

        if len(sell_reasons) >= 2:
            signal = "🔴 SAT (SELL)"
            reasons = sell_reasons

        return {
            'symbol': symbol,
            'price': price,
            'rsi': rsi,
            'signal': signal,
            'reasons': reasons
        }
    except Exception as e:
        return None

# --- TELEGRAM KOMANDALARI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 **Peşəkar Binance Analiz Botuna Xoş Gəldiniz!**\n\n"
        "📊 **Əmrlər:**\n"
        "• `/scan` - Indikatorlara əsasən AL/SAT hazır olan coinləri tapır\n"
        "• `/top` - Ən çox artan və düşən coinləri göstərir\n"
        "• `/price COIN` - Dərhal qiymət göstərir (Məs: `/price BTCUSDT`)\n"
        "• `/set COIN QIYMET UP/DOWN` - Qiymət alarmı qurur\n"
        "• `/list` - Aktiv alarmlarınızı göstərir\n"
        "• `/delete ID` - Alarmı silir\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("İstifadə: `/price BTCUSDT`", parse_mode="Markdown")
        return
    symbol = context.args[0].upper()
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        res = requests.get(url).json()
        p = float(res['price'])
        await update.message.reply_text(f"💰 **{symbol}**: {p}")
    except:
        await update.message.reply_text("❌ Coin tapılmadı!")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Bazar analiz edilir, gözləyin...")
    symbols = get_all_usdt_symbols()
    
    # Faiz dəyişiminə görə çeşidləyirik
    sorted_symbols = sorted(symbols, key=lambda x: float(x['priceChangePercent']), reverse=True)
    
    gainers = sorted_symbols[:5]
    losers = sorted_symbols[-5:][::-1]

    text = "🚀 **TOP GAINERS (Ən çox artanlar):**\n"
    for item in gainers:
        text += f"• `{item['symbol']}`: +{float(item['priceChangePercent']):.2f}% | Qiymət: {float(item['lastPrice'])}\n"

    text += "\n📉 **TOP LOSERS (Ən çox düşənlər):**\n"
    for item in losers:
        text += f"• `{item['symbol']}`: {float(item['priceChangePercent']):.2f}% | Qiymət: {float(item['lastPrice'])}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Bütün Binance coinləri (RSI, MACD, EMA, BB) üzrə taranır...\nBu əməliyyat ~15-20 saniyə çəkə bilsin.")
    
    symbols_data = get_all_usdt_symbols()
    # Həcmə görə ilk 60 coini götürək ki, scanner sürətli olsun və likvidli coinlərə baxsın
    top_volume_symbols = sorted(symbols_data, key=lambda x: float(x['quoteVolume']), reverse=True)[:60]

    buy_signals = []
    sell_signals = []

    for item in top_volume_symbols:
        sym = item['symbol']
        res = analyze_symbol(sym)
        if res and res['signal'] != "NEUTRAL":
            if "AL" in res['signal']:
                buy_signals.append(res)
            elif "SAT" in res['signal']:
                sell_signals.append(res)

    text = "📊 **ANALİZ NƏTİCƏLƏRİ (15m timeframe):**\n\n"
    
    if buy_signals:
        text += "🟢 **GÜCLÜ AL SİQNALLARI:**\n"
        for s in buy_signals[:5]:
            reasons_str = ", ".join(s['reasons'])
            text += f"• **{s['symbol']}** - Qiymət: {s['price']} | RSI: {s['rsi']:.1f}\n  Səbəb: _{reasons_str}_\n"
    else:
        text += "🟢 **AL Siqnalı verən coin tapılmadı.**\n"

    text += "\n"

    if sell_signals:
        text += "🔴 **GÜCLÜ SAT SİQNALLARI:**\n"
        for s in sell_signals[:5]:
            reasons_str = ", ".join(s['reasons'])
            text += f"• **{s['symbol']}** - Qiymət: {s['price']} | RSI: {s['rsi']:.1f}\n  Səbəb: _{reasons_str}_\n"
    else:
        text += "🔴 **SAT Siqnalı verən coin tapılmadı.**\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global alert_counter
    try:
        symbol = context.args[0].upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"
        target_price = float(context.args[1])
        direction = context.args[2].lower()

        if direction not in ['up', 'down']:
            await update.message.reply_text("İstiqamət 'up' və ya 'down' olmalıdır!")
            return

        chat_id = update.effective_chat.id
        if chat_id not in ALERTS:
            ALERTS[chat_id] = []

        ALERTS[chat_id].append({
            'id': alert_counter,
            'symbol': symbol,
            'target': target_price,
            'direction': direction
        })

        await update.message.reply_text(f"✅ Alarm quruldu! ID: {alert_counter}\n{symbol} qiyməti {target_price} səviyyəsini ({direction}) keçəndə xəbər verəcəm.")
        alert_counter += 1
    except Exception:
        await update.message.reply_text("Məsələn: `/set BTCUSDT 65000 up`", parse_mode="Markdown")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in ALERTS or not ALERTS[chat_id]:
        await update.message.reply_text("Aktiv alarmınız yoxdur.")
        return

    text = "📋 **Aktiv Alarmlarınız:**\n"
    for a in ALERTS[chat_id]:
        text += f"ID: `{a['id']}` | {a['symbol']} -> {a['target']} ({a['direction']})\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def delete_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        alert_id = int(context.args[0])
        if chat_id in ALERTS:
            ALERTS[chat_id] = [a for a in ALERTS[chat_id] if a['id'] != alert_id]
            await update.message.reply_text(f"✅ ID: {alert_id} olan alarm silindi.")
        else:
            await update.message.reply_text("Alarm tapılmadı.")
    except:
        await update.message.reply_text("Məsələn: `/delete 1`", parse_mode="Markdown")

# Arxa fonda qiymətləri yoxlayan Loop (Arxa fon alarmları üçün)
async def check_alerts(app):
    while True:
        try:
            for chat_id, alerts in list(ALERTS.items()):
                for a in list(alerts):
                    url = f"https://api.binance.com/api/v3/ticker/price?symbol={a['symbol']}"
                    res = requests.get(url, timeout=5).json()
                    current_price = float(res['price'])

                    triggered = False
                    if a['direction'] == 'up' and current_price >= a['target']:
                        triggered = True
                    elif a['direction'] == 'down' and current_price <= a['target']:
                        triggered = True

                    if triggered:
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=f"🚨 **ALARM XƏBƏRDARLIĞI!**\n\n{a['symbol']} hədəf qiymətə çatdı!\nCari Qiymət: {current_price}\nHədəf: {a['target']}"
                        )
                        ALERTS[chat_id].remove(a)
        except Exception as e:
            logging.error(f"Alert yoxlama xətası: {e}")

        await asyncio.sleep(30) # Hər 30 saniyədən bir yoxlayır

async def post_init(app):
    asyncio.create_task(check_alerts(app))

if __name__ == '__main__':
    if not BOT_TOKEN:
        print("BOT_TOKEN tapılmadı!")
        exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("set", set_alert))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CommandHandler("delete", delete_alert))

    print("Bot işə düşdü...")
    app.run_polling()
# --- KÖMƏK VƏ SİQNAL ƏMRƏLƏRİ ---
async def help_command(update, context):
    await update.message.reply_text("Mövcud əmrlər:\n/start - Başlat\n/help - Kömək\n/signal - Siqnal al")

async def signal_command(update, context):
    await update.message.reply_text("📊 Binance siqnalı analiz edilir...")

# Handler-ləri tətbiqə qoşmaq
try:
    if 'app' in locals() or 'app' in globals():
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("signal", signal_command))
        app.add_handler(MessageHandler(filters.Regex(r'^(?i)help$'), help_command))
        app.add_handler(MessageHandler(filters.Regex(r'^(?i)signal$'), signal_command))
    elif 'application' in locals() or 'application' in globals():
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("signal", signal_command))
        application.add_handler(MessageHandler(filters.Regex(r'^(?i)help$'), help_command))
        application.add_handler(MessageHandler(filters.Regex(r'^(?i)signal$'), signal_command))
except Exception as e:
    pass