from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import logging

from app.db.models.content import Post, Channel
from app.services.telegram import TelegramService
from app.core.config import settings

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, db: Session):
        self.db = db
        self.telegram = TelegramService()
        self.scheduler = self._setup_scheduler()
        
    def _setup_scheduler(self) -> AsyncIOScheduler:
        """Setup APScheduler with SQLAlchemy job store."""
        jobstores = {
            'default': SQLAlchemyJobStore(url=settings.SQLALCHEMY_DATABASE_URI)
        }
        
        scheduler = AsyncIOScheduler(jobstores=jobstores)
        scheduler.start()
        return scheduler
        
    async def schedule_post(
        self,
        post_id: int,
        scheduled_time: datetime
    ) -> Dict:
        """Schedule a post for publication."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return {
                'success': False,
                'error': 'Post not found'
            }
            
        # Add job to scheduler
        job = self.scheduler.add_job(
            self.publish_post,
            'date',
            run_date=scheduled_time,
            args=[post_id],
            id=f'post_{post_id}',
            replace_existing=True
        )
        
        # Update post status
        post.status = 'scheduled'
        post.scheduled_time = scheduled_time
        self.db.commit()
        
        return {
            'success': True,
            'job_id': job.id,
            'scheduled_time': scheduled_time
        }
        
    async def cancel_scheduled_post(self, post_id: int) -> Dict:
        """Cancel a scheduled post."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return {
                'success': False,
                'error': 'Post not found'
            }
            
        try:
            self.scheduler.remove_job(f'post_{post_id}')
            post.status = 'draft'
            post.scheduled_time = None
            self.db.commit()
            
            return {
                'success': True,
                'message': 'Post scheduling cancelled'
            }
        except Exception as e:
            logger.error(f"Failed to cancel scheduled post {post_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def reschedule_post(
        self,
        post_id: int,
        new_time: datetime
    ) -> Dict:
        """Reschedule a post to a new time."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return {
                'success': False,
                'error': 'Post not found'
            }
            
        try:
            self.scheduler.reschedule_job(
                f'post_{post_id}',
                trigger='date',
                run_date=new_time
            )
            
            post.scheduled_time = new_time
            self.db.commit()
            
            return {
                'success': True,
                'new_time': new_time
            }
        except Exception as e:
            logger.error(f"Failed to reschedule post {post_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def get_scheduled_posts(
        self,
        channel_id: Optional[int] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get list of scheduled posts."""
        query = self.db.query(Post).filter(Post.status == 'scheduled')
        
        if channel_id:
            query = query.filter(Post.channel_id == channel_id)
        if from_date:
            query = query.filter(Post.scheduled_time >= from_date)
        if to_date:
            query = query.filter(Post.scheduled_time <= to_date)
            
        posts = query.all()
        return [
            {
                'id': post.id,
                'channel_id': post.channel_id,
                'scheduled_time': post.scheduled_time,
                'text': post.text,
                'has_photo': bool(post.photo_url)
            }
            for post in posts
        ]
        
    async def get_optimal_schedule(
        self,
        channel_id: int,
        posts_per_day: int = 3,
        days: int = 7
    ) -> List[datetime]:
        """Generate optimal schedule based on analytics."""
        # Get channel's best performing hours
        channel = self.db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise ValueError("Channel not found")
            
        # Get analytics data (implement your analytics logic here)
        best_hours = [9, 13, 17, 20]  # Example hours
        
        # Generate schedule
        schedule = []
        current_date = datetime.now()
        
        for day in range(days):
            date = current_date + timedelta(days=day)
            for hour in best_hours[:posts_per_day]:
                schedule.append(
                    date.replace(hour=hour, minute=0, second=0, microsecond=0)
                )
                
        return schedule
        
    async def publish_post(self, post_id: int):
        """Publish a post to Telegram channel."""
        try:
            post = self.db.query(Post).filter(Post.id == post_id).first()
            if not post:
                logger.error(f"Post {post_id} not found")
                return
                
            channel = self.db.query(Channel).filter(Channel.id == post.channel_id).first()
            if not channel:
                logger.error(f"Channel not found for post {post_id}")
                return
                
            # Send message to Telegram
            result = await self.telegram.send_message(
                chat_id=channel.channel_id,
                text=post.text,
                photo_url=post.photo_url
            )
            
            if result['success']:
                post.status = 'published'
                post.published_time = datetime.utcnow()
                post.metadata['telegram_message_id'] = result['message_id']
            else:
                post.status = 'failed'
                post.error_message = result.get('error', 'Unknown error')
                
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to publish post {post_id}: {str(e)}")
            if post:
                post.status = 'failed'
                post.error_message = str(e)
                self.db.commit()
                
    async def retry_failed_post(self, post_id: int) -> Dict:
        """Retry publishing a failed post."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return {
                'success': False,
                'error': 'Post not found'
            }
            
        if post.status != 'failed':
            return {
                'success': False,
                'error': 'Post is not in failed status'
            }
            
        try:
            await self.publish_post(post_id)
            return {
                'success': True,
                'message': 'Post republishing initiated'
            }
        except Exception as e:
            logger.error(f"Failed to retry post {post_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            } 