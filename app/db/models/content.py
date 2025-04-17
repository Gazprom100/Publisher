from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.models.base import Base

class Channel(Base):
    """Channel model for managing Telegram channels."""
    title = Column(String(255), nullable=False)
    channel_id = Column(String(255), unique=True, nullable=False)
    sheet_name = Column(String(255), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    member_count = Column(Integer, default=0)
    settings = Column(JSON, default={})
    
    posts = relationship("Post", back_populates="channel")
    analytics = relationship("ChannelAnalytics", back_populates="channel")

class Post(Base):
    """Post model for managing content."""
    channel_id = Column(Integer, ForeignKey("channel.id"))
    text = Column(Text)
    photo_url = Column(String(1024))
    scheduled_time = Column(DateTime)
    published_time = Column(DateTime)
    status = Column(String(50), default="draft")  # draft, scheduled, published, failed
    error_message = Column(Text)
    metadata = Column(JSON, default={})
    
    channel = relationship("Channel", back_populates="posts")
    analytics = relationship("PostAnalytics", back_populates="post")
    tags = relationship("Tag", secondary="post_tags")

class Tag(Base):
    """Tag model for categorizing posts."""
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    color = Column(String(7), default="#000000")
    
    posts = relationship("Post", secondary="post_tags")

class PostTags(Base):
    """Association table for Post-Tag many-to-many relationship."""
    post_id = Column(Integer, ForeignKey("post.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tag.id"), primary_key=True)

class PostAnalytics(Base):
    """Analytics data for individual posts."""
    post_id = Column(Integer, ForeignKey("post.id"))
    views = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    reactions = Column(JSON, default={})
    reach = Column(Integer, default=0)
    engagement_rate = Column(Float)
    metadata = Column(JSON, default={})
    
    post = relationship("Post", back_populates="analytics")

class ChannelAnalytics(Base):
    """Analytics data for channels."""
    channel_id = Column(Integer, ForeignKey("channel.id"))
    date = Column(DateTime, nullable=False)
    member_count = Column(Integer, default=0)
    post_count = Column(Integer, default=0)
    total_views = Column(Integer, default=0)
    total_shares = Column(Integer, default=0)
    engagement_rate = Column(Float)
    metadata = Column(JSON, default={})
    
    channel = relationship("Channel", back_populates="analytics")

class ContentTemplate(Base):
    """Templates for post content."""
    name = Column(String(255), nullable=False)
    description = Column(Text)
    template_text = Column(Text, nullable=False)
    variables = Column(JSON, default=[])
    metadata = Column(JSON, default={})
    is_active = Column(Boolean, default=True) 