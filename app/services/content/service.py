from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import os
from PIL import Image
import magic
from langdetect import detect
from textblob import TextBlob

from app.db.models.content import Post, Channel, Tag, ContentTemplate
from app.core.config import settings
from app.services.telegram import TelegramService

class ContentService:
    def __init__(self, db: Session):
        self.db = db
        self.telegram = TelegramService()

    async def create_post(
        self,
        channel_id: int,
        text: str,
        photo_url: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        tags: List[str] = None
    ) -> Post:
        """Create a new post."""
        # Validate channel
        channel = self.db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise ValueError("Channel not found")
            
        # Create post
        post = Post(
            channel_id=channel_id,
            text=text,
            photo_url=photo_url,
            scheduled_time=scheduled_time,
            status="draft"
        )
        
        # Add tags
        if tags:
            for tag_name in tags:
                tag = self.db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    self.db.add(tag)
                post.tags.append(tag)
        
        # Add metadata
        post.metadata = {
            'content_quality': await self.analyze_content_quality(text),
            'language': await self.detect_language(text),
            'sentiment': await self.analyze_sentiment(text),
            'has_media': bool(photo_url)
        }
        
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        
        return post

    async def update_post(
        self,
        post_id: int,
        text: Optional[str] = None,
        photo_url: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None
    ) -> Post:
        """Update an existing post."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise ValueError("Post not found")
            
        if text is not None:
            post.text = text
            post.metadata.update({
                'content_quality': await self.analyze_content_quality(text),
                'language': await self.detect_language(text),
                'sentiment': await self.analyze_sentiment(text)
            })
            
        if photo_url is not None:
            post.photo_url = photo_url
            post.metadata['has_media'] = bool(photo_url)
            
        if scheduled_time is not None:
            post.scheduled_time = scheduled_time
            
        if status is not None:
            post.status = status
            
        if tags is not None:
            # Remove old tags
            post.tags = []
            # Add new tags
            for tag_name in tags:
                tag = self.db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    self.db.add(tag)
                post.tags.append(tag)
        
        self.db.commit()
        self.db.refresh(post)
        
        return post

    async def delete_post(self, post_id: int) -> bool:
        """Delete a post."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return False
            
        self.db.delete(post)
        self.db.commit()
        return True

    async def get_posts(
        self,
        channel_id: Optional[int] = None,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[Post]:
        """Get posts with filters."""
        query = self.db.query(Post)
        
        if channel_id:
            query = query.filter(Post.channel_id == channel_id)
        if status:
            query = query.filter(Post.status == status)
        if tag:
            query = query.join(Post.tags).filter(Tag.name == tag)
        if from_date:
            query = query.filter(Post.scheduled_time >= from_date)
        if to_date:
            query = query.filter(Post.scheduled_time <= to_date)
            
        return query.all()

    async def create_template(
        self,
        name: str,
        template_text: str,
        description: Optional[str] = None,
        variables: Optional[List[str]] = None
    ) -> ContentTemplate:
        """Create a content template."""
        template = ContentTemplate(
            name=name,
            template_text=template_text,
            description=description,
            variables=variables or []
        )
        
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        
        return template

    async def apply_template(
        self,
        template_id: int,
        variables: Dict[str, str]
    ) -> str:
        """Apply variables to a template."""
        template = self.db.query(ContentTemplate).filter(
            ContentTemplate.id == template_id
        ).first()
        
        if not template:
            raise ValueError("Template not found")
            
        text = template.template_text
        for var_name, value in variables.items():
            text = text.replace(f"{{{var_name}}}", value)
            
        return text

    async def analyze_content_quality(self, text: str) -> Dict:
        """Analyze content quality."""
        if not text:
            return {'score': 0, 'issues': ['Empty content']}
            
        issues = []
        score = 100
        
        # Length check
        if len(text) < 50:
            issues.append('Content too short')
            score -= 20
        elif len(text) > 2000:
            issues.append('Content too long')
            score -= 10
            
        # URL check
        if 'http' in text.lower():
            if not any(secure in text.lower() for secure in ['https://', 'http://']):
                issues.append('Invalid URL format')
                score -= 15
                
        # Basic formatting
        if text.isupper():
            issues.append('Excessive use of uppercase')
            score -= 25
            
        # Duplicate words
        words = text.lower().split()
        if len(words) != len(set(words)):
            issues.append('Contains duplicate words')
            score -= 10
            
        return {
            'score': max(0, score),
            'issues': issues
        }

    async def detect_language(self, text: str) -> str:
        """Detect text language."""
        try:
            return detect(text)
        except:
            return 'unknown'

    async def analyze_sentiment(self, text: str) -> Dict:
        """Analyze text sentiment."""
        try:
            analysis = TextBlob(text)
            return {
                'polarity': analysis.sentiment.polarity,
                'subjectivity': analysis.sentiment.subjectivity
            }
        except:
            return {
                'polarity': 0,
                'subjectivity': 0
            }

    async def validate_media(self, file_path: str) -> Dict:
        """Validate media file."""
        if not os.path.exists(file_path):
            return {'valid': False, 'error': 'File not found'}
            
        try:
            # Check file type
            mime = magic.Magic(mime=True)
            file_type = mime.from_file(file_path)
            
            if not file_type.startswith('image/'):
                return {'valid': False, 'error': 'Invalid file type'}
                
            # Check image
            with Image.open(file_path) as img:
                width, height = img.size
                format = img.format
                
                # Size validation
                if os.path.getsize(file_path) > settings.MAX_CONTENT_LENGTH:
                    return {'valid': False, 'error': 'File too large'}
                    
                return {
                    'valid': True,
                    'metadata': {
                        'width': width,
                        'height': height,
                        'format': format,
                        'mime_type': file_type
                    }
                }
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    async def optimize_image(
        self,
        file_path: str,
        max_size: Optional[int] = None,
        quality: int = 85
    ) -> str:
        """Optimize image for posting."""
        try:
            with Image.open(file_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                    
                # Resize if needed
                if max_size:
                    img.thumbnail((max_size, max_size))
                    
                # Save optimized version
                output_path = f"{os.path.splitext(file_path)[0]}_optimized.jpg"
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
                
                return output_path
        except Exception as e:
            raise ValueError(f"Failed to optimize image: {str(e)}")

    async def schedule_post(
        self,
        post_id: int,
        scheduled_time: datetime
    ) -> Post:
        """Schedule a post for publication."""
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise ValueError("Post not found")
            
        post.scheduled_time = scheduled_time
        post.status = "scheduled"
        
        self.db.commit()
        self.db.refresh(post)
        
        return post 