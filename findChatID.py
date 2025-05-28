import telegram
import asyncio
import logging
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    # 텔레그램 봇 초기화
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logging.error("TELEGRAM_BOT_TOKEN environment variable not set")
        return
    
    bot = telegram.Bot(token=bot_token)
    
    # 최신 업데이트 가져오기
    updates = await bot.get_updates()
    
    if updates:
        for update in updates:
            if update.message and update.message.chat.type == 'private':
                chat_id = update.message.chat_id
                logging.info(f"Your Chat ID: {chat_id}")
                await bot.send_message(chat_id=chat_id, text=f"Your Chat ID is: {chat_id}")
        # 처리한 업데이트 오프셋 설정
        await bot.get_updates(offset=updates[-1].update_id + 1)
    else:
        logging.info("No new messages found. Send a message to your bot to get the Chat ID.")

if __name__ == "__main__":
    asyncio.run(main())