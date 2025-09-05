# main.py
import os
import requests
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Set up logging to catch any errors and keep track of events
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration & Setup ---

# Load the Telegram bot token from an environment variable for security.
# This is crucial for deployment on platforms like Render.
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Check if the token is available
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is not set. The bot cannot start.")
    exit(1)

# URLs for API endpoints
BINANCE_P2P_URL = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price'

# Helper function to format numbers with commas for readability
def format_number(value):
    try:
        return f'{float(value):,.2f}'
    except (ValueError, TypeError):
        return value

# Helper function to get P2P data from Binance
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
    }

    try:
        response = requests.post(BINANCE_P2P_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Binance P2P data: {e}")
        return None

# --- Command Handlers ---

# /start command
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    message = (
        "Hello! I am your personal Binance assistant bot.\n\n"
        "Here are the commands you can use:\n"
        "/p2p - Get the top 10 general P2P rates for USDT in ETB.\n"
        "/p2p_amount <amount> <currency> - Get P2P rates for a specific amount. "
        "Example: `/p2p_amount 5000 ETB` or `/p2p_amount 50 USDT`.\n"
        "/convert <amount> <from_currency> <to_currency> - Convert crypto. "
        "Example: `/convert 1 BTC to ETH` or `/convert 100 USDT to TON`.\n"
        "/coin <coin_symbol> - Get real-time info about a crypto coin. "
        "Example: `/coin BTC` or `/coin SOL`."
    )
    await update.message.reply_text(message)

# /p2p command
async def p2p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and sends general P2P rates."""
    await update.message.reply_text("Fetching the top 10 P2P rates for USDT... Please wait a moment.")
    
    data = get_p2p_data(None, "BUY")
    
    if not data or 'data' not in data or not data['data']:
        await update.message.reply_text("Sorry, I could not fetch the P2P rates at this time. Please try again later.")
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
            f"**{i+1}. {merchant_name}**\n"
            f"  `Rate:` {format_number(rate)} ETB\n"
            f"  `Available:` {format_number(min_trade)} - {format_number(max_trade)} ETB\n"
            f"  `Orders:` {orders} ({round(float(completion_rate) * 100, 2)}%)\n\n"
        )
    
    await update.message.reply_text(rates_message, parse_mode='Markdown')

# /p2p_amount command
async def p2p_amount_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches P2P rates for a specific amount."""
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Please provide an amount and currency. Example: `/p2p_amount 5000 ETB` or `/p2p_amount 50 USDT`")
            return

        amount = float(args[0])
        currency = args[1].upper()
        
        trade_type = "BUY" # Default to buy
        
        await update.message.reply_text(f"Fetching P2P rates for {format_number(amount)} {currency}... Please wait.")

        # If the user provides an amount in ETB, we can search by that.
        # Otherwise, assume it's a USDT amount and convert it to ETB using a rough estimate.
        if currency == "ETB":
            data = get_p2p_data(amount, trade_type)
        else:
            # We need a rough estimate to search by amount, so we'll get the general rate first
            general_data = get_p2p_data(None, trade_type)
            if not general_data or not general_data['data']:
                 await update.message.reply_text("Could not get a base rate for conversion. Please try again later.")
                 return
            estimated_rate = float(general_data['data'][0]['adv']['price'])
            amount_in_etb = amount * estimated_rate
            data = get_p2p_data(amount_in_etb, trade_type)
        
        if not data or 'data' not in data or not data['data']:
            await update.message.reply_text(f"No P2P offers found for {format_number(amount)} {currency}.")
            return

        rates_message = f"--- **Top P2P Rates for {format_number(amount)} {currency}** ---\n\n"
        for i, ad in enumerate(data['data'][:10]):
            rate = ad['adv']['price']
            min_trade = ad['adv']['minSingleTransAmount']
            max_trade = ad['adv']['maxSingleTransAmount']
            merchant_name = ad['advertiser']['nickName']
            orders = ad['advertiser']['monthOrderCount']
            completion_rate = ad['advertiser']['monthFinishRate']

            rates_message += (
                f"**{i+1}. {merchant_name}**\n"
                f"  `Rate:` {format_number(rate)} ETB\n"
                f"  `Available:` {format_number(min_trade)} - {format_number(max_trade)} ETB\n"
                f"  `Orders:` {orders} ({round(float(completion_rate) * 100, 2)}%)\n\n"
            )
        
        await update.message.reply_text(rates_message, parse_mode='Markdown')

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid input. Please provide a valid number and currency. Example: `/p2p_amount 5000 ETB`")

# /convert command
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Converts a crypto amount from one currency to another."""
    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text("Invalid format. Example: `/convert 1 BTC to ETH`")
            return
        
        amount = float(args[0])
        from_coin = args[1].lower()
        to_coin = args[2].lower()
        
        await update.message.reply_text(f"Converting {amount} {from_coin.upper()} to {to_coin.upper()}... Please wait.")

        # Check if one of the coins is a stablecoin like USDT to simplify the conversion logic
        if from_coin == 'usdt':
            params = {
                "ids": to_coin,
                "vs_currencies": from_coin
            }
        elif to_coin == 'usdt':
            params = {
                "ids": from_coin,
                "vs_currencies": to_coin
            }
        else:
            # For non-stablecoin conversions, we'll convert both to USDT first
            params = {
                "ids": f"{from_coin},{to_coin}",
                "vs_currencies": "usdt"
            }
        
        response = requests.get(COINGECKO_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            await update.message.reply_text("Could not find one or both of the coins. Please check the symbols.")
            return

        if from_coin == 'usdt':
            to_rate = data.get(to_coin, {}).get(from_coin, None)
            if to_rate is None:
                await update.message.reply_text(f"Could not get the price for {to_coin.upper()}.")
                return
            result = amount / to_rate
            message = f"{format_number(amount)} {from_coin.upper()} is equal to {format_number(result)} {to_coin.upper()}"
        elif to_coin == 'usdt':
            from_rate = data.get(from_coin, {}).get(to_coin, None)
            if from_rate is None:
                await update.message.reply_text(f"Could not get the price for {from_coin.upper()}.")
                return
            result = amount * from_rate
            message = f"{format_number(amount)} {from_coin.upper()} is equal to {format_number(result)} {to_coin.upper()}"
        else:
            from_rate_usdt = data.get(from_coin, {}).get('usdt', None)
            to_rate_usdt = data.get(to_coin, {}).get('usdt', None)
            
            if from_rate_usdt is None or to_rate_usdt is None:
                await update.message.reply_text("Could not get conversion rates for one or both coins.")
                return
            
            result = (amount * from_rate_usdt) / to_rate_usdt
            message = f"{format_number(amount)} {from_coin.upper()} is equal to {format_number(result)} {to_coin.upper()}"

        await update.message.reply_text(message)

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid input. Please provide a valid amount and coin symbols. Example: `/convert 1 BTC to ETH`")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching CoinGecko data: {e}")
        await update.message.reply_text("There was an error while trying to fetch the conversion rate. Please try again later.")

# /coin command
async def coin_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and displays information about a specific crypto coin."""
    try:
        coin_symbol = context.args[0].lower()
        await update.message.reply_text(f"Fetching information for {coin_symbol.upper()}... Please wait.")

        # Use CoinGecko for comprehensive coin information, including market cap
        coin_url = f"https://api.coingecko.com/api/v3/coins/{coin_symbol}"
        response = requests.get(coin_url)
        response.raise_for_status()
        data = response.json()
        
        name = data.get('name', 'N/A')
        symbol = data.get('symbol', 'N/A').upper()
        market_cap_usd = data.get('market_data', {}).get('market_cap', {}).get('usd', 'N/A')
        current_price_usd = data.get('market_data', {}).get('current_price', {}).get('usd', 'N/A')
        price_change_24h = data.get('market_data', {}).get('price_change_percentage_24h', 'N/A')
        
        info_message = (
            f"--- **{name} ({symbol})** ---\n"
            f"  `Current Price:` ${format_number(current_price_usd)}\n"
            f"  `Market Cap:` ${format_number(market_cap_usd)}\n"
            f"  `24h Change:` {format_number(price_change_24h)}%\n"
            "  *Data provided by CoinGecko.*"
        )

        await update.message.reply_text(info_message, parse_mode='Markdown')

    except (IndexError, requests.exceptions.RequestException):
        await update.message.reply_text("Invalid command. Please provide a valid coin symbol. Example: `/coin BTC`")
    except json.JSONDecodeError:
        await update.message.reply_text("Could not find information for that coin. Please check the symbol.")

def main():
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("p2p", p2p_command))
    application.add_handler(CommandHandler("p2p_amount", p2p_amount_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("coin", coin_info_command))

    # Run the bot with polling
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
