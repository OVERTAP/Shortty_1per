# monitor.py
import ccxt
import os
import asyncio
import json
import subprocess
from telegram import Bot
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# KuCoin 거래소 설정
exchange = ccxt.kucoin({
    'enableRateLimit': True,
})

# 텔레그램 봇 설정
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 관심 종목 저장 파일
WATCHLIST_FILE = "watchlist.json"

# Git 동기화 함수
def git_pull():
    try:
        subprocess.run(["git", "pull", "--rebase"], check=True)
        print("Successfully pulled latest changes from GitHub")
    except subprocess.CalledProcessError as e:
        print(f"Error pulling from GitHub: {e}")

# 관심 종목 로드
def load_watchlist():
    git_pull()  # 최신 상태 동기화
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

async def monitor():
    try:
        # KuCoin 선물 시장 데이터 로드
        markets = exchange.load_markets()
        futures_markets = {symbol: market for symbol, market in markets.items() 
                          if market['type'] == 'swap' and not symbol.endswith(":USDT")}
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

if __name__ == "__main__":
    asyncio.run(monitor())
