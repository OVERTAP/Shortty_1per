import ccxt
import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# KuCoin 거래소 설정 (API 키 없이)
exchange = ccxt.kucoin({
    'enableRateLimit': True,  # 속도 제한 준수
})

# 텔레그램 봇 설정
bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def main():
    try:
        # 시장 데이터 로드 (공개 API 사용)
        markets = exchange.load_markets()
        print(f"Loaded {len(markets)} markets from KuCoin")

        # 선물 종목 필터링 (KuCoin에서는 'future' 타입 확인)
        futures_markets = {symbol: market for symbol, market in markets.items() if market['type'] == 'future'}
        print(f"Found {len(futures_markets)} futures markets")

        # 1시간봉 데이터 조회 및 알림 로직
        for symbol in futures_markets:
            try:
                # 1시간봉(OHLCV) 데이터 가져오기 (공개 API 사용)
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=2)
                if len(ohlcv) < 2:
                    continue

                # 최근 캔들 두 개 비교
                prev_close = ohlcv[-2][4]  # 이전 캔들 종가
                current_close = ohlcv[-1][4]  # 현재 캔들 종가
                change_percent = ((current_close - prev_close) / prev_close) * 100

                # 1% 이상 하락 시 알림
                if change_percent <= -1:
                    message = f"{symbol} 1h candle dropped by {abs(change_percent):.2f}%"
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                    print(f"Sent alert: {message}")

                # 속도 제한 준수를 위해 잠시 대기
                await asyncio.sleep(1)

            except Exception as e:
                print(f"Error processing {symbol}: {str(e)}")
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Error with {symbol}: {str(e)}")

    except Exception as e:
        print(f"Error loading markets: {str(e)}")
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Error in KuCoin script: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
