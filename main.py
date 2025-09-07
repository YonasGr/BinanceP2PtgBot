import os
import requests
import json
import logging
import asyncio
import matplotlib.pyplot as plt
import io
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InputMediaPhoto
from telegram.ext import Application, CommandHandler, ContextTypes, InlineQueryHandler
from dotenv import load_dotenv
from uuid import uuid4

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is not set. The bot cannot start.")
    exit(1)

BINANCE_P2P_URL = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
COINGECKO_COINS_LIST_URL = 'https://api.coingecko.com/api/v3/coins/list'
COINGECKO_COIN_URL = 'https://api.coingecko.com/api/v3/coins/'

coin_list_cache = {}
last_updated = 0

def format_number(value):
    try:
        if value is None:
            return 'N/A'
        return f'{float(value):,.2f}'
    except (ValueError, TypeError):
        return value

def escape_markdown(text):
    escape_chars = '_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def get_p2p_data(amount, trade_type):
    payload = {
        "proMerchantAds": False,
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "asset": "USDT",
        "fiat": "ETB",
        "tradeType": trade_type,
        "amount": amount
    }
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.post(BINANCE_P2P_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        return response.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        logger.error(f"Error fetching Binance P2P data: {e}")
        return None

async def get_coin_list():
    global coin_list_cache, last_updated
    if not coin_list_cache or (asyncio.get_running_loop().time() - last_updated > 86400):
        try:
            response = requests.get(COINGECKO_COINS_LIST_URL)
            response.raise_for_status()
            data = response.json()
            new_cache = {coin['symbol'].lower(): coin['id'] for coin in data}
            coin_list_cache = new_cache
            last_updated = asyncio.get_running_loop().time()
            logger.info("Successfully refreshed CoinGecko coin list cache.")
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Error fetching CoinGecko coin list: {e}")
            if not coin_list_cache:
                return None
    return coin_list_cache

async def get_coin_id_from_symbol(symbol):
    if not coin_list_cache:
        await get_coin_list()
    return coin_list_cache.get(symbol.lower())

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "👋 Hello! I am your Binance P2P ETB bot.\n\n"
        "You can use me in chats or inline mode (@binancep2pETBbot).\n\n"
        "Commands:\n\n"
        "/p2p - Top 10 general P2P rates for USDT in ETB\n"
        "/rate <amount> <currency> - Get top P2P rates for specific amount\n"
        "/sell <amount> usdt etb - Calculate exact ETB amount for selling USDT\n"
        "/convert <amount> <from_currency> <to_currency> - Convert crypto\n"
        "/coin <coin_symbol> - Get coin info and chart\n\n"
        "Inline Mode: Type `@binancep2pETBbot <command>` anywhere in Telegram to use all commands."
        "\n\nInformation is fetched live from Binance P2P and CoinGecko."
        "\n\n\nbot by @x_Jonah (channel: @Jonah-Notice)"
    )
    await update.message.reply_text(message)

async def p2p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching top 10 P2P rates for USDT... Please wait.")
    data = get_p2p_data(None, "BUY")
    if not data or "data" not in data or not data["data"]:
        await update.message.reply_text("Could not fetch P2P rates at this time.")
        return
    rates_message = "--- **Current Top P2P Rates (Buy USDT)** ---\n\n"
    for i, ad in enumerate(data['data'][:10]):
        rate = ad['adv']['price']
        min_trade = ad['adv']['minSingleTransAmount']
        max_trade = ad['adv']['maxSingleTransAmount']
        merchant_name = ad['advertiser']['nickName']
        orders = ad['advertiser']['monthOrderCount']
        completion_rate = ad['advertiser']['monthFinishRate']
        rates_message += (
            f"**{i+1}. {escape_markdown(merchant_name)}**\n"
            f"  `Rate:` {format_number(rate)} ETB\n"
            f"  `Available:` {format_number(min_trade)} - {format_number(max_trade)} ETB\n"
            f"  `Orders:` {orders} ({round(float(completion_rate)*100,2)}%)\n\n"
        )
    await update.message.reply_text(rates_message, parse_mode='Markdown')

async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Usage: /rate <amount> <currency>")
            return
        amount = float(args[0])
        currency = args[1].upper()
        trade_type = "BUY"
        data = get_p2p_data(amount, trade_type)
        if not data or "data" not in data or not data["data"]:
            await update.message.reply_text(f"No P2P offers found for {amount} {currency}.")
            return
        message = f"--- **Top P2P Rates for {amount} {currency}** ---\n\n"
        for i, ad in enumerate(data['data'][:10]):
            rate = ad['adv']['price']
            min_trade = ad['adv']['minSingleTransAmount']
            max_trade = ad['adv']['maxSingleTransAmount']
            merchant_name = ad['advertiser']['nickName']
            orders = ad['advertiser']['monthOrderCount']
            completion_rate = ad['advertiser']['monthFinishRate']
            message += (
                f"**{i+1}. {escape_markdown(merchant_name)}**\n"
                f"  `Rate:` {format_number(rate)} ETB\n"
                f"  `Available:` {format_number(min_trade)} - {format_number(max_trade)} ETB\n"
                f"  `Orders:` {orders} ({round(float(completion_rate)*100,2)}%)\n\n"
            )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in /rate: {e}")
        await update.message.reply_text("⚠️ Error fetching P2P rates.")

async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 3:
            await update.message.reply_text("Usage: /sell <amount> usdt etb")
            return
        amount = float(context.args[0])
        from_currency = context.args[1].lower()
        to_currency = context.args[2].lower()
        if from_currency != "usdt" or to_currency != "etb":
            await update.message.reply_text("Currently only USDT → ETB is supported.")
            return
        data = get_p2p_data(amount, "SELL")
        if not data or "data" not in data or len(data["data"]) < 6:
            await update.message.reply_text("Could not fetch enough P2P offers right now.")
            return
        # Skip first 5 offers, take 6th as safest rate
        best_offer = data["data"][5]
        rate = float(best_offer["adv"]["price"])
        merchant_name = best_offer["advertiser"]["nickName"]
        completion_rate = float(best_offer["advertiser"]["monthFinishRate"]) * 100
        orders = best_offer["advertiser"]["monthOrderCount"]
        total_etb = amount * rate
        message = (
            f"💱 Best P2P Rate for {amount} USDT → ETB\n\n"
            f"1 USDT = {format_number(rate)} ETB\n"
            f"{amount} USDT = {format_number(total_etb)} ETB\n\n"
            f"👤 Seller: {escape_markdown(merchant_name)}\n"
            f"📊 Orders: {orders}, Completion: {completion_rate:.2f}%"
        )
        await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in /sell: {e}")
        await update.message.reply_text("⚠️ Error while fetching P2P conversion.")

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 3:
            await update.message.reply_text("Usage: /convert <amount> <from_currency> <to_currency>")
            return
        amount = float(context.args[0])
        from_currency = context.args[1].lower()
        to_currency = context.args[2].lower()
        from_id = await get_coin_id_from_symbol(from_currency)
        to_id = await get_coin_id_from_symbol(to_currency)
        if not from_id or not to_id:
            await update.message.reply_text(f"Could not find coins {from_currency.upper()} or {to_currency.upper()}")
            return
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": f"{from_id},{to_id}", "vs_currencies": "usd"}
        response = requests.get(url, params=params)
        response.raise_for_status()
        prices = response.json()
        from_rate_usd = prices.get(from_id, {}).get("usd")
        to_rate_usd = prices.get(to_id, {}).get("usd")
        if from_rate_usd is None or to_rate_usd is None:
            await update.message.reply_text("Price data not available.")
            return
        result = (amount * from_rate_usd) / to_rate_usd
        rate_from_to = from_rate_usd / to_rate_usd
        rate_to_from = to_rate_usd / from_rate_usd
        message = (
            f"{amount} {from_currency.upper()} ≈ {result:.6f} {to_currency.upper()}\n\n"
            f"1 {from_currency.upper()} ≈ {rate_from_to:.6f} {to_currency.upper()}\n"
            f"1 {to_currency.upper()} ≈ {rate_to_from:.6f} {from_currency.upper()}"
        )
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in /convert: {e}")
        await update.message.reply_text("⚠️ Error while converting.")

async def coin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin_symbol = context.args[0].lower()
        coin_id = await get_coin_id_from_symbol(coin_symbol)
        if not coin_id:
            await update.message.reply_text(f"Could not find information for {coin_symbol.upper()}.")
            return
        await update.message.reply_text(f"Fetching information for {coin_symbol.upper()}...")
        coin_url = f"{COINGECKO_COIN_URL}{coin_id}"
        response = requests.get(coin_url)
        response.raise_for_status()
        data = response.json()
        chart_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        chart_params = {"vs_currency": "usd", "days": "7"}
        chart_response = requests.get(chart_url, params=chart_params)
        chart_response.raise_for_status()
        chart_data = chart_response.json()
        prices = [p[1] for p in chart_data["prices"]]
        times = [p[0] for p in chart_data["prices"]]
        plt.figure(figsize=(8, 4))
        plt.plot(times, prices, color="blue")
        plt.title(f"{data['name']} (7D Price in USD)")
        plt.xlabel("Time")
        plt.ylabel("Price (USD)")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()
        name = data.get('name', 'N/A')
        symbol = data.get('symbol', 'N/A').upper()
        market_cap_usd = data.get('market_data', {}).get('market_cap', {}).get('usd', 'N/A')
        current_price_usd = data.get('market_data', {}).get('current_price', {}).get('usd', 'N/A')
        price_change_24h = data.get('market_data', {}).get('price_change_percentage_24h', 'N/A')
        info_message = (
            f"--- **{escape_markdown(name)} ({escape_markdown(symbol)})** ---\n"
            f"  `Current Price:` ${format_number(current_price_usd)}\n"
            f"  `Market Cap:` ${format_number(market_cap_usd)}\n"
            f"  `24h Change:` {format_number(price_change_24h)}%\n"
            "  *Data provided by CoinGecko.*"
        )
        await update.message.reply_photo(photo=buf, caption=info_message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in /coin: {e}")
        await update.message.reply_text("Error fetching coin info.")

# ----------------- INLINE QUERY HANDLER -----------------
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    results = []

    if not query:
        return

    args = query.split()
    cmd = args[0].lower()
    args_only = args[1:]

    # /p2p
    if cmd == "p2p":
        data = get_p2p_data(None, "BUY")
        if data and "data" in data:
            text = "--- Top 10 P2P Rates (Buy USDT) ---\n\n"
            for i, ad in enumerate(data["data"][:10]):
                rate = ad['adv']['price']
                merchant_name = ad['advertiser']['nickName']
                text += f"{i+1}. {escape_markdown(merchant_name)}: {format_number(rate)} ETB\n"
            results.append(InlineQueryResultArticle(
                id=str(uuid4()), title="Top P2P Rates", input_message_content=InputTextMessageContent(text)
            ))

    # /rate
    elif cmd == "rate" and len(args_only) == 2:
        amount = float(args_only[0])
        currency = args_only[1].upper()
        data = get_p2p_data(amount, "BUY")
        if data and "data" in data:
            text = f"--- Top P2P Rates for {amount} {currency} ---\n\n"
            for i, ad in enumerate(data["data"][:10]):
                rate = ad['adv']['price']
                merchant_name = ad['advertiser']['nickName']
                text += f"{i+1}. {escape_markdown(merchant_name)}: {format_number(rate)} ETB\n"
            results.append(InlineQueryResultArticle(
                id=str(uuid4()), title=f"P2P Rates for {amount} {currency}",
                input_message_content=InputTextMessageContent(text)
            ))

    # /sell
    elif cmd == "sell" and len(args_only) == 3:
        amount = float(args_only[0])
        from_currency = args_only[1].lower()
        to_currency = args_only[2].lower()
        if from_currency == "usdt" and to_currency == "etb":
            data = get_p2p_data(amount, "SELL")
            if data and "data" in data and len(data["data"]) >= 6:
                best_offer = data["data"][5]
                rate = float(best_offer["adv"]["price"])
                total_etb = amount * rate
                text = f"{amount} USDT → {format_number(total_etb)} ETB (1 USDT={format_number(rate)} ETB)"
                results.append(InlineQueryResultArticle(
                    id=str(uuid4()), title=f"Sell {amount} USDT", input_message_content=InputTextMessageContent(text)
                ))

    # /convert
    elif cmd == "convert" and len(args_only) == 3:
        amount = float(args_only[0])
        from_currency = args_only[1].lower()
        to_currency = args_only[2].lower()
        from_id = await get_coin_id_from_symbol(from_currency)
        to_id = await get_coin_id_from_symbol(to_currency)
        if from_id and to_id:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": f"{from_id},{to_id}", "vs_currencies": "usd"}
            response = requests.get(url, params=params)
            prices = response.json()
            from_rate_usd = prices.get(from_id, {}).get("usd")
            to_rate_usd = prices.get(to_id, {}).get("usd")
            if from_rate_usd and to_rate_usd:
                result = (amount * from_rate_usd) / to_rate_usd
                text = f"{amount} {from_currency.upper()} ≈ {result:.6f} {to_currency.upper()}"
                results.append(InlineQueryResultArticle(
                    id=str(uuid4()), title=f"Convert {amount} {from_currency.upper()} → {to_currency.upper()}",
                    input_message_content=InputTextMessageContent(text)
                ))

    # /coin
    elif cmd == "coin" and len(args_only) == 1:
        coin_symbol = args_only[0].lower()
        coin_id = await get_coin_id_from_symbol(coin_symbol)
        if coin_id:
            coin_url = f"{COINGECKO_COIN_URL}{coin_id}"
            response = requests.get(coin_url)
            data = response.json()
            chart_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            chart_params = {"vs_currency": "usd", "days": "7"}
            chart_response = requests.get(chart_url, params=chart_params)
            chart_data = chart_response.json()
            prices = [p[1] for p in chart_data["prices"]]
            times = [p[0] for p in chart_data["prices"]]
            plt.figure(figsize=(8, 4))
            plt.plot(times, prices, color="blue")
            plt.title(f"{data['name']} (7D Price in USD)")
            plt.xlabel("Time")
            plt.ylabel("Price (USD)")
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)
            plt.close()
            media = InputMediaPhoto(buf, caption=f"{data['name']} ({data['symbol'].upper()}) 7D chart")
            results.append(InlineQueryResultArticle(
                id=str(uuid4()), title=f"{data['name']} Chart",
                input_message_content=InputTextMessageContent(f"{data['name']} Chart (7D)")
            ))

    if results:
        await update.inline_query.answer(results, cache_time=5)

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Load CoinGecko coin list before starting
    asyncio.get_event_loop().run_until_complete(get_coin_list())

    # Normal command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("p2p", p2p_command))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("sell", sell_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("coin", coin_command))

    # Inline query handler
    application.add_handler(InlineQueryHandler(inline_query))

    logger.info("Starting bot in normal + inline mode...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()



