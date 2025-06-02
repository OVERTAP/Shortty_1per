# monitor.py - MEXC 버전
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

# MEXC 거래소 설정 - API 키 없이도 공개 데이터 접근 가능
exchange = ccxt.mexc({
    'apiKey': os.getenv('MEXC_API_KEY', ''),
    'secret': os.getenv('MEXC_SECRET', ''),
    'password': os.getenv('MEXC_PASSWORD', ''),
    'sandbox': False,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',  # 선물 거래 기본 설정
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
        print("Loading markets from MEXC...")
        
        # 마켓 로드 시도
        try:
            markets = exchange.load_markets()
            print(f"Successfully loaded {len(markets)} markets from MEXC")
        except Exception as e:
            print(f"Error loading markets: {e}")
            # API 키 없이도 공개 데이터는 접근 가능하도록 재시도
            try:
                exchange_public = ccxt.mexc({
                    'enableRateLimit': True,
                    'sandbox': False
                })
                markets = exchange_public.load_markets()
                print(f"Successfully loaded {len(markets)} markets (public access)")
                exchange = exchange_public  # 공개 접근으로 교체 (global 선언 제거)
            except Exception as e2:
                print(f"Failed to load markets even with public access: {e2}")
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                     text=f"Failed to connect to MEXC: {str(e2)}")
                return

        # 디버깅: 마켓 정보 분석
        print("Analyzing MEXC market data...")
        market_types = {}
        swap_symbols = []
        usdt_symbols = []
        
        for symbol, market in markets.items():
            market_type = market.get('type', 'unknown')
            market_types[market_type] = market_types.get(market_type, 0) + 1
            
            # MEXC 선물 계약 찾기 (여러 형태 지원)
            if (market_type == 'swap' and 
                market.get('active', True) and
                market.get('quote') == 'USDT'):
                swap_symbols.append(symbol)
                
            # USDT로 거래되는 모든 활성 심볼
            if ('USDT' in symbol and 
                market.get('active', True)):
                usdt_symbols.append(symbol)
        
        print(f"Market types distribution: {market_types}")
        print(f"Found {len(swap_symbols)} USDT perpetual swap contracts")
        print(f"Found {len(usdt_symbols)} total USDT pairs")
        
        # 상위 몇 개 SWAP 심볼 출력
        if swap_symbols:
            print(f"Sample SWAP symbols: {swap_symbols[:10]}")
            futures_symbols = swap_symbols
        else:
            # SWAP이 없다면 USDT 페어 중에서 선물 계약 찾기
            print("No dedicated SWAP symbols found. Using USDT futures contracts...")
            futures_symbols = [s for s in usdt_symbols if any(keyword in s.upper() for keyword in ['_USDT', '/USDT']) and market_types.get(markets[s].get('type')) and markets[s].get('type') in ['swap', 'future']]
            
            if not futures_symbols:
                # 모든 USDT 페어를 대상으로 사용
                futures_symbols = usdt_symbols[:50]  # 상위 50개만 사용
                print(f"Using top {len(futures_symbols)} USDT pairs as futures contracts")

        # 총 개수 텔레그램으로 전송
        total_symbols = len(futures_symbols)
        message = f"🏪 MEXC Futures Market Analysis:\n"
        message += f"📊 Total USDT contracts: {total_symbols}\n"
        message += f"🔍 Market types: {', '.join(market_types.keys())}\n"
        message += f"📈 Market type counts: {dict(list(market_types.items())[:5])}\n"
        
        if futures_symbols:
            sample_symbols = [s.replace('_USDT', '').replace('/USDT', '') for s in futures_symbols[:5]]
            message += f"✅ Sample tickers: {', '.join(sample_symbols)}"
        else:
            message += "❌ No suitable futures contracts found"
            
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"Sent MEXC market analysis to Telegram")

        # 관심 종목이 있다면 모니터링 실행
        watchlist = load_watchlist()
        if not watchlist:
            print("No symbols in watchlist")
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                 text="📝 Watchlist is empty. Add symbols using the bot!")
            return

        print(f"Monitoring {len(watchlist)} symbols from watchlist...")
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                             text=f"🔍 Starting to monitor {len(watchlist)} symbols on MEXC...")

        for symbol in watchlist:
            try:
                print(f"Checking {symbol} on MEXC...")
                
                # 심볼이 실제로 존재하는지 확인
                if symbol not in markets:
                    print(f"Warning: {symbol} not found in MEXC markets")
                    # 대체 심볼 형태 시도
                    alt_symbol = symbol.replace('-USDT-SWAP', '/USDT').replace('-USDT', '/USDT')
                    if alt_symbol in markets:
                        symbol = alt_symbol
                        print(f"Using alternative symbol format: {symbol}")
                    else:
                        continue
                
                # 1시간봉 데이터 (1% 음봉 감지)
                try:
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=2)
                    if len(ohlcv_1h) < 2:
                        print(f"Not enough 1h data for {symbol}")
                        continue
                        
                    prev_close_1h = ohlcv_1h[-2][4]
                    current_close_1h = ohlcv_1h[-1][4]
                    change_percent_1h = ((current_close_1h - prev_close_1h) / prev_close_1h) * 100
                    
                    print(f"{symbol} 1h change: {change_percent_1h:.2f}%")
                    
                    if change_percent_1h <= -1:
                        ticker = symbol.split('/')[0] if '/' in symbol else symbol.split('-')[0]
                        message = f"🔴 MEXC Alert: {ticker}\n📉 1h drop: {abs(change_percent_1h):.2f}%\n💰 Price: ${current_close_1h:.6f}"
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                        print(f"Sent 1h drop alert: {message}")
                except Exception as e:
                    print(f"Error fetching 1h data for {symbol}: {e}")

                # 30분봉 데이터 (이전 음봉 고점 돌파 감지)
                try:
                    ohlcv_30m = exchange.fetch_ohlcv(symbol, timeframe='30m', limit=2)
                    if len(ohlcv_30m) < 2:
                        print(f"Not enough 30m data for {symbol}")
                        continue
                        
                    prev_open_30m = ohlcv_30m[-2][1]
                    prev_close_30m = ohlcv_30m[-2][4]
                    prev_high_30m = ohlcv_30m[-2][2]
                    current_close_30m = ohlcv_30m[-1][4]
                    
                    # 이전 캔들이 음봉이고 현재 가격이 이전 고점을 돌파했는지 확인
                    if prev_close_30m < prev_open_30m and current_close_30m > prev_high_30m:
                        ticker = symbol.split('/')[0] if '/' in symbol else symbol.split('-')[0]
                        message = f"🟢 MEXC Alert: {ticker}\n📈 30m breakout above bearish high\n💰 Broke: ${prev_high_30m:.6f}\n💰 Current: ${current_close_30m:.6f}"
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                        print(f"Sent breakout alert: {message}")
                except Exception as e:
                    print(f"Error fetching 30m data for {symbol}: {e}")

                await asyncio.sleep(0.5)  # API 레이트 리미트 방지

            except Exception as e:
                ticker = symbol.split('/')[0] if '/' in symbol else symbol.split('-')[0]
                error_msg = f"❌ Error processing {ticker}: {str(e)}"
                print(error_msg)
                # 에러가 너무 많으면 텔레그램 스팸 방지
                if "not found" not in str(e).lower():
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=error_msg)

        print("MEXC monitoring cycle completed")
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                             text="✅ MEXC monitoring cycle completed successfully")

    except Exception as e:
        error_msg = f"💥 Critical error in MEXC monitor: {str(e)}"
        print(error_msg)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=error_msg)

if __name__ == "__main__":
    asyncio.run(monitor())
