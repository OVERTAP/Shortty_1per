import ccxt
import json
import os
import telegram
import asyncio
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 텔레그램 봇 초기화
bot = telegram.Bot(token=os.environ['TELEGRAM_BOT_TOKEN'])
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# 관심 종목 저장소
WATCHLIST_FILE = 'watchlist.json'

def load_watchlist():
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(watchlist, f)

async def send_telegram_message(message):
    await bot.send_message(chat_id=CHAT_ID, text=message)

# 텔레그램 메시지 핸들러
async def handle_telegram_updates():
    updates = await bot.get_updates(timeout=10)
    watchlist = load_watchlist()
    for update in updates:
        if update.message and update.message.text:
            ticker = update.message.text.strip().upper()
            symbol = f"{ticker}/USDT"
            if symbol not in watchlist:
                watchlist.append(symbol)
                save_watchlist(watchlist)
                await send_telegram_message(f"Added {symbol} to watchlist")
    # 오프셋 업데이트
    if updates:
        await bot.get_updates(offset=updates[-1].update_id + 1)

async def main():
    # 바이낸스 선물 시장 초기화
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    # 종목 조회
    markets = exchange.load_markets()
    symbols = [symbol for symbol in markets.keys() if ':USDT' not in symbol and symbol.endswith('/USDT')]
    logging.info(f"Found {len(symbols)} trading symbols")

    # 관심 종목 로드
    watchlist = load_watchlist()

    # 텔레그램 업데이트 처리
    await handle_telegram_updates()

    # 관심 종목 가격 감시
    for symbol in watchlist:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=2)
            if len(ohlcv) >= 2:
                prev_close = ohlcv[-2][4]  # 이전 캔들 종가
                current_close = ohlcv[-1][4]  # 현재 캔들 종가
                change_percent = ((current_close - prev_close) / prev_close) * 100
                if change_percent <= -1:
                    await send_telegram_message(f"{symbol} 1h candle dropped by {abs(change_percent):.2f}%")
        except Exception as e:
            logging.error(f"Error monitoring {symbol}: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())