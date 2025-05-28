import ccxt
import os
import asyncio
import json
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# KuCoin 거래소 설정 (API 키 없이)
exchange = ccxt.kucoin({
    'enableRateLimit': True,
})

# 관심 종목 저장 파일
WATCHLIST_FILE = "watchlist.json"

# 텔레그램 봇 설정
app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 관심 종목 로드/저장
def load_watchlist():
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(watchlist, f)

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
    if symbol not in markets or markets[symbol]['type'] != 'future':
        await update.message.reply_text(f"{symbol}은(는) KuCoin 선물 시장에 존재하지 않습니다.")
        return

    watchlist = load_watchlist()
    if symbol in watchlist:
        await update.message.reply_text(f"{symbol}은(는) 이미 관심 종목에 있습니다.")
        return

    watchlist.append(symbol)
    save_watchlist(watchlist)
    await update.message.reply_text(f"{symbol}이(가) 관심 종목에 추가되었습니다.")

# 메인 감시 로직
async def monitor():
    try:
        # KuCoin 선물 시장 데이터 로드
        markets = exchange.load_markets()
        futures_markets = {symbol: market for symbol, market in markets.items() 
                          if market['type'] == 'future' and not symbol.endswith(":USDT")}
        print(f"Found {len(futures_markets)} futures markets on KuCoin")

        # 관심 종목 감시
        watchlist = load_watchlist()
        if not watchlist:
            print("No symbols in watchlist")
            return

        for symbol in watchlist:
            try:
                # 1시간봉 데이터 (1% 음봉 감지)
                ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=2)
                if len(ohlcv_1h) < 2:
                    continue
                prev_close_1h = ohlcv_1h[-2][4]
                current_close_1h = ohlcv_1h[-1][4]
                change_percent_1h = ((current_close_1h - prev_close_1h) / prev_close_1h) * 100
                if change_percent_1h <= -1:
                    message = f"{symbol} 1h candle dropped by {abs(change_percent_1h):.2f}%"
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                    print(f"Sent alert: {message}")

                # 30분봉 데이터 (이전 음봉 고점 돌파 감지)
                ohlcv_30m = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=2)
                if len(ohlcv_30m) < 2:
                    continue
                prev_open_30m = ohlcv_30m[-2][1]
                prev_close_30m = ohlcv_30m[-2][4]
                prev_high_30m = ohlcv_30m[-2][2]
                current_close_30m = ohlcv_30m[-1][4]
                if prev_close_30m < prev_open_30m and current_close_30m > prev_high_30m:
                    message = f"{symbol} 30m candle broke above previous bearish candle high ({prev_high_30m})"
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                    print(f"Sent alert: {message}")

                await asyncio.sleep(1)

            except Exception as e:
                print(f"Error processing {symbol}: {str(e)}")
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Error with {symbol}: {str(e)}")

    except Exception as e:
        print(f"Error loading markets: {str(e)}")
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Error in KuCoin script: {str(e)}")

# 텔레그램 봇 핸들러 등록 및 실행
def main():
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("watchlist", show_watchlist))
    app.add_handler(CallbackQueryHandler(remove_symbol, pattern='^remove:.*'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_symbol))

    # 봇 실행 및 감시 루프
    loop = asyncio.get_event_loop()
    loop.create_task(app.initialize())
    loop.create_task(app.start())
    loop.create_task(app.updater.start_polling())

    # 5분마다 감시 (GitHub Actions에서 이미 5분마다 실행되므로 루프 불필요)
    loop.run_until_complete(monitor())

    # 봇 종료
    loop.run_until_complete(app.updater.stop())
    loop.run_until_complete(app.stop())
    loop.run_until_complete(app.shutdown())

if __name__ == "__main__":
    main()
