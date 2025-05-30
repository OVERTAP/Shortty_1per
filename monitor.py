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

# KuCoin 거래소 설정 - 선물 마켓 접근을 위한 옵션 추가
exchange = ccxt.kucoin({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',  # 선물/스왑 마켓 접근을 위한 설정
    }
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
    git_pull()
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

async def monitor():
    try:
        # KuCoin 선물 시장 데이터 로드
        markets = exchange.load_markets()
        print(f"Total markets loaded: {len(markets)}")

        # 디버깅: market 타입 확인
        market_types = {}
        for symbol, market in markets.items():
            market_type = market.get('type', 'unknown')
            if market_type not in market_types:
                market_types[market_type] = 0
            market_types[market_type] += 1
        
        print(f"Market types found: {market_types}")

        # 선물/스왑 종목 필터링 (KuCoin 선물 심볼 형식)
        futures_markets = {}
        for symbol, market in markets.items():
            market_type = market.get('type', '')
            # KuCoin 선물은 주로 'swap' 타입이고 'M'으로 끝나는 심볼 사용
            if market_type in ['swap', 'future']:
                # 무기한 선물(perpetual) 필터링 - 만료일이 없어야 함
                if not market.get('expiry'):
                    # KuCoin 선물 심볼 패턴 확인 (예: XBTUSDTM, ETHUSDTM 등)
                    if (symbol.endswith('USDTM') or symbol.endswith('USDM') or 
                        '/USDT' in symbol):
                        futures_markets[symbol] = market
        
        # 종목 총 개수 출력
        total_symbols = len(futures_markets)
        message = f"Total number of trading symbols in KuCoin futures market: {total_symbols}"
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(message)

        # 추가 디버깅: 필터링된 종목 목록 일부 출력
        if total_symbols > 0:
            sample_symbols = list(futures_markets.keys())[:10]  # 상위 10개만 출력
            sample_message = f"Sample futures symbols: {', '.join(sample_symbols)}"
            print(sample_message)
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=sample_message)
        else:
            print("No futures markets found. Checking symbol formats...")
            # 디버깅을 위해 모든 마켓 타입별 샘플 출력
            debug_info = []
            for market_type, count in market_types.items():
                sample_symbols = [s for s, m in markets.items() if m.get('type') == market_type][:3]
                debug_info.append(f"{market_type} ({count}): {sample_symbols}")
            
            debug_message = "Market type samples:\n" + "\n".join(debug_info)
            print(debug_message)
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=debug_message)

        # 기존 감시 로직
        print(f"Found {total_symbols} futures markets on KuCoin")

        # 관심 종목 감시
        watchlist = load_watchlist()
        if not watchlist:
            print("No symbols in watchlist")
            return

        for symbol in watchlist:
            try:
                # 심볼이 실제로 존재하는지 확인
                if symbol not in markets:
                    print(f"Symbol {symbol} not found in markets")
                    continue

                print(f"Processing {symbol}...")

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
