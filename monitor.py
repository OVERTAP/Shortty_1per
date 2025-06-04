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
        'defaultType': 'swap',
    }
})

# 텔레그램 봇 설정
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# 파일 경로
WATCHLIST_FILE = "watchlist.json"
PRICES_FILE = "prices.json"
FIRST_RUN_FILE = "is_first_run.json"

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

def load_prices():
    try:
        with open(PRICES_FILE, 'r') as f:
            prices = json.load(f)
            print(f"Loaded prices: {prices}")
            return prices
    except FileNotFoundError:
        print(f"Error: {PRICES_FILE} not found")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding {PRICES_FILE}: {e}")
        return {}

def save_prices(prices):
    try:
        with open(PRICES_FILE, 'w') as f:
            json.dump(prices, f, indent=2)
        print(f"Saved prices: {prices}")
    except Exception as e:
        print(f"Error saving {PRICES_FILE}: {e}")

def check_first_run():
    try:
        with open(FIRST_RUN_FILE, 'r') as f:
            data = json.load(f)
            return data.get("is_first_run", True)
    except FileNotFoundError:
        return True

def update_first_run():
    try:
        with open(FIRST_RUN_FILE, 'w') as f:
            json.dump({"is_first_run": False}, f, indent=2)
        print("Updated first run status to False")
    except Exception as e:
        print(f"Error updating {FIRST_RUN_FILE}: {e}")

async def monitor():
    try:
        print("Loading markets from MEXC...")
        try:
            markets = exchange.load_markets()
            print(f"Successfully loaded {len(markets)} markets from MEXC")
        except Exception as e:
            print(f"Error loading markets: {e}")
            try:
                exchange_public = ccxt.mexc({
                    'enableRateLimit': True,
                    'sandbox': False
                })
                markets = exchange_public.load_markets()
                print(f"Successfully loaded {len(markets)} markets (public access)")
                exchange = exchange_public
            except Exception as e2:
                print(f"Failed to load markets even with public access: {e2}")
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                       text=f"Failed to connect to MEXC: {str(e2)}")
                return

        print("Analyzing MEXC market data...")
        market_types = {}
        swap_symbols = []
        usdt_symbols = []

        for symbol, market in markets.items():
            market_type = market.get('type', 'unknown')
            market_types[market_type] = market_types.get(market_type, 0) + 1
            if market_type == 'swap' and market.get('active', True) and market.get('quote') == 'USDT':
                swap_symbols.append(symbol)
            if 'USDT' in symbol and market.get('active', True):
                usdt_symbols.append(symbol)

        print(f"Market types distribution: {market_types}")
        print(f"Found {len(swap_symbols)} USDT perpetual swap contracts")
        print(f"Found {len(usdt_symbols)} total USDT pairs")

        watchlist = load_watchlist()
        if not watchlist:
            print("No symbols in watchlist")
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, 
                                   text="📝 Watchlist is empty. Add symbols to watchlist.json!")
            return

        is_first_run = check_first_run()
        if is_first_run:
            print("This is the first run. Sending watchlist to Telegram...")
            formatted_watchlist = [s.replace('_USDT', ':USDT') for s in watchlist]
            message = f"🔍 Watchlist symbols ({len(watchlist)}):\n"
            message += '\n'.join([', '.join(formatted_watchlist[i:i+5]) for i in range(0, len(formatted_watchlist), 5)])
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            update_first_run()

        print(f"Monitoring {len(watchlist)} symbols from watchlist...")

        previous_prices = load_prices()
        current_prices = {}

        has_drops = False
        drop_message = "🔴 MEXC Price Drop Alerts:\n"

        for symbol in watchlist:
            try:
                print(f"Checking {symbol} on MEXC...")
                selected_symbol = symbol
                if symbol not in markets:
                    alt_symbol = symbol.replace('/USDT', '_USDT').replace('-USDT-SWAP', '_USDT')
                    if alt_symbol in markets:
                        print(f"Using alternative symbol format: {alt_symbol}")
                        selected_symbol = alt_symbol
                    else:
                        print(f"Warning: {symbol} not found in MEXC markets")
                        continue

                market = markets[selected_symbol]
                print(f"Symbol {selected_symbol}: type={market.get('type')}, active={market.get('active', True)}")
                if market.get('type') != 'swap':
                    print(f"Warning: {selected_symbol} is not a futures contract")
                    continue

                ticker = exchange.fetch_ticker(selected_symbol)
                current_price = ticker.get('last')
                if not current_price:
                    print(f"No last price available for {selected_symbol}")
                    continue

                current_prices[selected_symbol] = current_price
                print(f"Current price for {selected_symbol}: ${current_price:.6f}")

                previous_price = previous_prices.get(selected_symbol)
                if previous_price is not None:
                    change_percent = ((current_price - previous_price) / previous_price) * 100
                    print(f"{selected_symbol} price change: {change_percent:.2f}%")
                    if change_percent <= -1:
                        ticker_name = selected_symbol.split('/')[0] if '/' in selected_symbol else selected_symbol.split('_')[0]
                        drop_message += f"📉 {ticker_name}: {abs(change_percent):.2f}% drop\n"
                        drop_message += f"💰 Previous: ${previous_price:.6f}\n"
                        drop_message += f"💰 Current: ${current_price:.6f}\n\n"
                        has_drops = True

                await asyncio.sleep(0.5)

            except Exception as e:
                ticker = symbol.split('/')[0] if '/' in symbol else symbol.split('_')[0]
                error_msg = f"❌ Error processing {ticker}: {str(e)}"
                print(error_msg)

        save_prices(current_prices)

        if has_drops:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=drop_message.strip())
            print("Sent price drop alerts to Telegram")

        print("MEXC monitoring cycle completed")

    except Exception as e:
        error_msg = f"💥 Critical error in MEXC monitor: {str(e)}"
        print(error_msg)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=error_msg)

if __name__ == "__main__":
    asyncio.run(monitor())
