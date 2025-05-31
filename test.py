from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Привет! Я бот.')

updater = Updater("7933232561:AAFKAO7qFeV4PXxkMku3WHP24AGOtDRpdqg")

updater.dispatcher.add_handler(CommandHandler("start", start))

updater.start_polling()
updater.idle()