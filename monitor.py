# monitor.py - MEXC 버전
import ccxt
import os
import asyncio
import json
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

# 관심 종목 로드
def load_watchlist():
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)
            print(f"Loaded watchlist: {watchlist}")
            return watchlist
    except FileNotFoundError:
        print(f"Error: {WATCHLIST_FILE} not found")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding {WATCHLIST_FILE}: {e}")
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
            # API 키 없이 공개 접근 시도
            try:
                exchange_public = ccxt.mexc({
                    'enableRateLimit': True,
                    'sandbox': False
                })
                markets = exchange_public.load_markets()
                print(f"Successfully loaded {len(markets)} markets (public access)")
                exchange = exchange_public  # 공개 접근으로 교체
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
            
            # MEXC 선물 계약 찾기
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
        
        # 모든 SWAP 심볼 출력 (텔레그램 메시지 형식으로 변환)
        if swap_symbols:
            print(f"All SWAP symbols: {swap_symbols}")
            futures_symbols = swap_symbols
            # 텔레그램 메시지 형식으로 변환 (_USDT → :USDT)
            formatted_symbols = [s.replace('_USDT', ':USDT') for s in swap_symbols]
            # 텔레그램 메시지 길이 제한(4096자)을 고려해 분할
            max_message_length = 4000
            current_message = f"🏪 MEXC Futures Market Analysis:\n"
            current_message += f"📊 Total USDT contracts: {len(futures_symbols)}\n"
            current_message += f"🔍 Market types: {', '.join(market_types.keys())}\n"
            current_message += f"📈 Market type counts: {dict(list(market_types.items())[:5])}\n"
            current_message += f"✅ All USDT futures tickers:\n"

            # 티커를 한 줄에 5개씩 출력
            ticker_lines = []
            for i in range(0, len(formatted_symbols), 5):
                ticker_line = ', '.join(formatted_symbols[i:i+5])
                ticker_lines.append(ticker_line)
            
            ticker_message = '\n'.join(ticker_lines)
            if len(current_message) + len(ticker_message) <= max_message_length:
                current_message += ticker_message
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=current_message)
            else:
                # 메시지 분할
                current_message += "✅ All USDT futures tickers (part 1):\n"
                part_messages = []
                current_part = ""
                for line in ticker_lines:
                    if len(current_part) + len(line) + 1 <= max_message_length - len(current_message):
                        current_part += line + "\n"
                    else:
                        part_messages.append(current_part.strip())
                        current_part = line + "\n"
                if current_part:
                    part_messages.append(current_part.strip())
                
                # 첫 번째 메시지 전송
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=current_message + part_messages[0])
                # 나머지 메시지 전송
                for i, part in enumerate(part_messages[1:], 2):
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                         text=f"✅ All USDT futures tickers (part {i}):\n{part}")
        else:
            print("No dedicated SWAP symbols found. Using USDT futures contracts...")
            futures_symbols = [s for s in usdt_symbols if any(keyword in s.upper() for keyword in ['_USDT', '/USDT']) and markets[s].get('type') in ['swap', 'future']]
            
            if not futures_symbols:
                futures_symbols = usdt_symbols[:50]  # 상위 50개만 사용
                print(f"Using top {len(futures_symbols)} USDT pairs as futures contracts")

            # 대체 심볼도 출력
            formatted_symbols = [s.replace('_USDT', ':USDT').replace('/USDT', ':USDT') for s in futures_symbols]
            message = f"🏪 MEXC Futures Market Analysis:\n"
            message += f"📊 Total USDT contracts: {len(futures_symbols)}\n"
            message += f"🔍 Market types: {', '.join(market_types.keys())}\n"
            message += f"📈 Market type counts: {dict(list(market_types.items())[:5])}\n"
            message += f"✅ All USDT futures tickers:\n"
            message += '\n'.join([', '.join(formatted_symbols[i:i+5]) for i in range(0, len(formatted_symbols), 5)])
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

        print(f"Sent MEXC market analysis to Telegram")

        # 관심 종목이 있다면 모니터링 실행
        watchlist = load_watchlist()
        if not watchlist:
            print("No symbols in watchlist")
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                 text="📝 Watchlist is empty. Add symbols to watchlist.json!")
            return

        print(f"Monitoring {len(watchlist)} symbols from watchlist...")
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                             text=f"🔍 Starting to monitor {len(watchlist)} symbols on MEXC...")

        for symbol in watchlist:
            try:
                print(f"Checking {symbol} on MEXC...")
                
                # 심볼이 실제로 존재하는지 확인
                selected_symbol = symbol
                if symbol not in markets:
                    # 대체 심볼 형태 시도
                    alt_symbol = symbol.replace('/USDT', '_USDT').replace('-USDT-SWAP', '_USDT')
                    if alt_symbol in markets:
                        print(f"Using alternative symbol format: {alt_symbol}")
                        selected_symbol = alt_symbol
                    else:
                        print(f"Warning: {symbol} not found in MEXC markets")
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                             text=f"❌ {symbol} is not a valid MEXC futures symbol")
                        continue
                
                # 선물 마켓인지 확인
                market = markets[selected_symbol]
                print(f"Symbol {selected_symbol}: type={market.get('type')}, active={market.get('active', True)}")
                if market.get('type') != 'swap':
                    print(f"Warning: {selected_symbol} is not a futures contract")
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                         text=f"❌ {selected_symbol} is not a futures contract")
                    continue
                
                # 1시간봉 데이터 (1% 음봉 감지)
                try:
                    ohlcv_1h = exchange.fetch_ohlcv(selected_symbol, timeframe='1h', limit=2)
                    if len(ohlcv_1h) < 2:
                        print(f"Not enough 1h data for {selected_symbol}")
                        continue
                        
                    prev_close_1h = ohlcv_1h[-2][4]
                    current_close_1h = ohlcv_1h[-1][4]
                    change_percent_1h = ((current_close_1h - prev_close_1h) / prev_close_1h) * 100
                    
                    print(f"{selected_symbol} 1h change: {change_percent_1h:.2f}%")
                    
                    if change_percent_1h <= -1:
                        ticker = selected_symbol.split('/')[0] if '/' in selected_symbol else selected_symbol.split('_')[0]
                        message = f"🔴 MEXC Alert: {ticker}\n📉 1h drop: {abs(change_percent_1h):.2f}%\n💰 Price: ${current_close_1h:.6f}"
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                        print(f"Sent 1h drop alert: {message}")
                except Exception as e:
                    print(f"Error fetching 1h data for {selected_symbol}: {e}")

                # 30분봉 데이터 (이전 음봉 고점 돌파 감지)
                try:
                    ohlcv_30m = exchange.fetch_ohlcv(selected_symbol, timeframe='30m', limit=2)
                    if len(ohlcv_30m) < 2:
                        print(f"Not enough 30m data for {selected_symbol}")
                        continue
                        
                    prev_open_30m = ohlcv_30m[-2][1]
                    prev_close_30m = ohlcv_30m[-2][4]
                    prev_high_30m = ohlcv_30m[-2][2]
                    current_close_30m = ohlcv_30m[-1][4]
                    
                    # 이전 캔들이 음봉이고 현재 가격이 이전 고점을 돌파했는지 확인
                    if prev_close_30m < prev_open_30m and current_close_30m > prev_high_30m:
                        ticker = selected_symbol.split('/')[0] if '/' in selected_symbol else selected_symbol.split('_')[0]
                        message = f"🟢 MEXC Alert: {ticker}\n📈 30m breakout above bearish high\n💰 Broke: ${prev_high_30m:.6f}\n💰 Current: ${current_close_30m:.6f}"
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                        print(f"Sent breakout alert: {message}")
                except Exception as e:
                    print(f"Error fetching 30m data for {selected_symbol}: {e}")

                await asyncio.sleep(0.5)  # API 레이트 리미트 방지

            except Exception as e:
                ticker = symbol.split('/')[0] if '/' in symbol else symbol.split('_')[0]
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
