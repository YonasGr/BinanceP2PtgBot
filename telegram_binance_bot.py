# This script is designed to run on a service like Render and uses environment variables.
# It is important to keep sensitive information like your bot token and API keys out of your code.

import os
import telegram
from telegram.ext import Updater, CommandHandler

# --- Environment Variables ---
# Get the bot token and API keys from environment variables.
# This keeps your sensitive information secure and out of your code.
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')

# Check if the environment variables are set
if not all([TELEGRAM_BOT_TOKEN, BINANCE_API_KEY, BINANCE_API_SECRET]):
    print("Error: Missing one or more environment variables.")
    print("Please set TELEGRAM_BOT_TOKEN, BINANCE_API_KEY, and BINANCE_API_SECRET.")
    exit()

# Set up the bot
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Define a simple start command handler
def start(update, context):
    """Sends a welcome message when the /start command is issued."""
    update.message.reply_text('Hello! I am your Telegram bot.')

# Add a command handler
start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

# Start the bot
def main():
    """Start the bot."""
    updater.start_polling()
    print("Bot started and listening for updates...")

if __name__ == '__main__':
    main()
