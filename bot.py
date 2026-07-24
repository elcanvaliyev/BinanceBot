import requests
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "8684809969:AAGVDgUqCJLX3wyscQuRZU8BcMupYoToSHI"

alerts = []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salam 👋\n\n"
        "Siqnal yaratmaq:\n"
        "/set COIN QIYMET UP/DOWN\n\n"
        "Misal:\n"
        "/set BTCUSDT 120000 up"
    )


async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].upper()
        price = float(context.args[1])
        direction = context.args[2].lower()

        alerts.append({
            "chat": update.effective_chat.id,
            "coin": coin,
            "price": price,
            "direction": direction
        })

        await update.message.reply_text(
            f"✅ {coin} izlənir\n"
            f"Qiymət: {price}\n"
            f"İstiqamət: {direction}"
        )

    except:
        await update.message.reply_text(
            "Səhv format.\nMisal:\n/set BTCUSDT 120000 up"
        )


async def check_loop(app):
    while True:
        for alert in alerts[:]:
            try:
                url = (
                    "https://api.binance.com/api/v3/ticker/price?"
                    f"symbol={alert['coin']}"
                )

                data = requests.get(url).json()
                price = float(data["price"])

                if alert["direction"] == "up" and price >= alert["price"]:
                    await app.bot.send_message(
                        chat_id=alert["chat"],
                        text=f"🚀 {alert['coin']} çatdı!\nQiymət: {price}$"
                    )
                    alerts.remove(alert)

                elif alert["direction"] == "down" and price <= alert["price"]:
                    await app.bot.send_message(
                        chat_id=alert["chat"],
                        text=f"🔻 {alert['coin']} düşdü!\nQiymət: {price}$"
                    )
                    alerts.remove(alert)

            except Exception as e:
                print(e)

        await asyncio.sleep(30)


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set", set_alert))

    await app.initialize()

    asyncio.create_task(check_loop(app))

    await app.start()
    await app.updater.start_polling()

    print("Bot işləyir...")

    while True:
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())