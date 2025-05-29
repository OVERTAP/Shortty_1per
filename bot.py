# bot.py
import ccxt
import os
import asyncio
import json
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# KuCoin 거래소 설정
exchange = ccxt.kucoin({
    'enableRateLimit': True,
})

# 관심 종목 저장 파일
WATCHLIST_FILE = "watchlist.json"

# 텔레그램 봇 설정
app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Git 동기화 함수
def git_pull():
    try:
        subprocess.run(["git", "pull", "--rebase"], check=True)
        print("Successfully pulled latest changes from GitHub")
    except subprocess.CalledProcessError as e:
        print(f"Error pulling from GitHub: {e}")

def git_push():
    try:
        subprocess.run(["git", "add", WATCHLIST_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update watchlist"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("Successfully pushed changes to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"Error pushing to GitHub: {e}")

# 관심 종목 로드/저장
def load_watchlist():
    git_pull()  # 최신 상태 동기화
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(watchlist, f)
    git_push()  # 변경 사항 저장소에 반영

# 시작 명령어 (/start)
async def start(update: Update, context):
    await update.message.reply_text("KuCoin Futures Monitor 봇입니다.\n"
                                    "종목 티커(예: ETH)를 입력해 관심 종목을 추가하세요.\n"
                                    "관심 종목은 5분마다 감시되며, 1시간봉 1% 이상 음봉 시 알림을 보냅니다.\n"
                                    "30분봉 기준 이전 음봉 캔들 고점 돌파 시에도 알림을 보냅니다.\n"
                                    "/watchlist로 관심 종목 목록을 확인하세요.")

# 관심 종목 목록 확인 (/watchlist)
async def show_watchlist(update: Update, context):
    watchlist = load_watchlist()
    if not watchlist:
        await update.message.reply_text("관심 종목이 없습니다.")
        return

    keyboard = [[InlineKeyboardButton(symbol, callback_data=f"remove:{symbol}")] for symbol in watchlist]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("관심 종목 목록:", reply_markup=reply_markup)

# 관심 종목 삭제
async def remove_symbol(update: Update, context):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split(":")[1]
    watchlist = load_watchlist()
    if symbol in watchlist:
        watchlist.remove(symbol)
        save_watchlist(watchlist)
        await query.message.reply_text(f"{symbol}이(가) 관심 종목에서 삭제되었습니다.")
    else:
        await query.message.reply_text(f"{symbol}은(는) 관심 종목에 없습니다.")

# 관심 종목 추가 (티커 입력 처리)
async def add_symbol(update: Update, context):
    ticker = update.message.text.strip().upper()
    symbol = f"{ticker}/USDT"
    
    markets = exchange.load_markets()
    if symbol not in markets or markets[symbol]['type'] != 'swap':
        await update.message.reply_text(f"{symbol}은(는) KuCoin 선물 시장에 존재하지 않습니다.")
        return

    watchlist = load_watchlist()
    if symbol in watchlist:
        await update.message.reply_text(f"{symbol}은(는) 이미 관심 종목에 있습니다.")
        return

    watchlist.append(symbol)
    save_watchlist(watchlist)
    await update.message.reply_text(f"{symbol}이(가) 관심 종목에 추가되었습니다.")

async def main():
    # 텔레그램 봇 핸들러 등록
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("watchlist", show_watchlist))
    app.add_handler(CallbackQueryHandler(remove_symbol, pattern='^remove:.*'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_symbol))

    # 봇 실행
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # 봇을 종료하지 않고 지속 실행
    print("Telegram bot is running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
