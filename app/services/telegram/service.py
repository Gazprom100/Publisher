from typing import Dict, List, Optional
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError
import asyncio
import aiohttp
import logging
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        
    async def send_message(
        self,
        chat_id: str,
        text: str,
        photo_url: Optional[str] = None,
        reply_markup: Optional[Dict] = None
    ) -> Dict:
        """Send message to Telegram channel."""
        try:
            if photo_url:
                # Send photo with caption
                message = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                # Send text only
                message = await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
            return {
                'message_id': message.message_id,
                'date': message.date,
                'success': True
            }
            
        except TelegramError as e:
            logger.error(f"Failed to send message to {chat_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def delete_message(
        self,
        chat_id: str,
        message_id: int
    ) -> bool:
        """Delete message from Telegram channel."""
        try:
            await self.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to delete message {message_id} from {chat_id}: {str(e)}")
            return False
            
    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        photo_url: Optional[str] = None,
        reply_markup: Optional[Dict] = None
    ) -> Dict:
        """Edit existing message in Telegram channel."""
        try:
            if photo_url:
                # Edit media message
                media = InputMediaPhoto(
                    media=photo_url,
                    caption=text,
                    parse_mode='HTML'
                )
                message = await self.bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=media,
                    reply_markup=reply_markup
                )
            else:
                # Edit text message
                message = await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
            return {
                'message_id': message.message_id,
                'date': message.date,
                'success': True
            }
            
        except TelegramError as e:
            logger.error(f"Failed to edit message {message_id} in {chat_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def get_chat_info(self, chat_id: str) -> Dict:
        """Get information about a Telegram chat."""
        try:
            chat = await self.bot.get_chat(chat_id)
            return {
                'id': chat.id,
                'type': chat.type,
                'title': chat.title,
                'username': chat.username,
                'description': chat.description,
                'member_count': await self.get_member_count(chat_id),
                'success': True
            }
        except TelegramError as e:
            logger.error(f"Failed to get chat info for {chat_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def get_member_count(self, chat_id: str) -> int:
        """Get number of members in a Telegram chat."""
        try:
            return await self.bot.get_chat_members_count(chat_id)
        except TelegramError as e:
            logger.error(f"Failed to get member count for {chat_id}: {str(e)}")
            return 0
            
    async def check_bot_permissions(self, chat_id: str) -> Dict:
        """Check bot permissions in a chat."""
        try:
            member = await self.bot.get_chat_member(
                chat_id=chat_id,
                user_id=self.bot.id
            )
            
            return {
                'can_post_messages': member.can_post_messages,
                'can_edit_messages': member.can_edit_messages,
                'can_delete_messages': member.can_delete_messages,
                'is_admin': member.status in ['administrator', 'creator'],
                'success': True
            }
        except TelegramError as e:
            logger.error(f"Failed to check bot permissions in {chat_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def get_message_stats(
        self,
        chat_id: str,
        message_id: int
    ) -> Dict:
        """Get message statistics (views, forwards, etc.)."""
        try:
            message = await self.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=chat_id,
                message_id=message_id,
                disable_notification=True
            )
            
            # Delete forwarded message immediately
            await self.delete_message(chat_id, message.message_id)
            
            return {
                'views': message.views if hasattr(message, 'views') else 0,
                'forwards': message.forwards if hasattr(message, 'forwards') else 0,
                'success': True
            }
        except TelegramError as e:
            logger.error(f"Failed to get message stats for {message_id} in {chat_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def download_file(self, file_url: str) -> Optional[bytes]:
        """Download file from Telegram servers."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.error(f"Failed to download file from {file_url}: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Failed to download file from {file_url}: {str(e)}")
            return None
            
    async def validate_channel(self, chat_id: str) -> Dict:
        """Validate channel and check bot permissions."""
        chat_info = await self.get_chat_info(chat_id)
        if not chat_info['success']:
            return chat_info
            
        permissions = await self.check_bot_permissions(chat_id)
        if not permissions['success']:
            return permissions
            
        if not permissions['is_admin'] or not permissions['can_post_messages']:
            return {
                'success': False,
                'error': "Bot needs to be an admin with posting permissions"
            }
            
        return {
            'success': True,
            'chat_info': chat_info,
            'permissions': permissions
        } 