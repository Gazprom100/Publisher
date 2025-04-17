# Project Structure

```
publisher/
├── alembic/                    # Database migrations
├── app/
│   ├── api/                    # API endpoints
│   │   ├── v1/
│   │   │   ├── analytics.py    # Analytics endpoints
│   │   │   ├── auth.py        # Authentication endpoints
│   │   │   ├── channels.py    # Channel management
│   │   │   ├── content.py     # Content management
│   │   │   └── scheduler.py   # Scheduling endpoints
│   ├── core/
│   │   ├── auth.py            # Authentication logic
│   │   ├── config.py          # Configuration management
│   │   ├── security.py        # Security utilities
│   │   └── logging.py         # Logging configuration
│   ├── db/
│   │   ├── base.py            # Database setup
│   │   ├── models/            # SQLAlchemy models
│   │   └── session.py         # Database session management
│   ├── services/
│   │   ├── analytics/         # Analytics services
│   │   ├── content/           # Content management
│   │   ├── scheduler/         # Scheduling services
│   │   └── telegram/          # Telegram integration
│   ├── tasks/                 # Celery tasks
│   └── utils/                 # Utility functions
├── static/
│   ├── css/                   # Stylesheets
│   ├── js/                    # JavaScript files
│   └── img/                   # Images
├── templates/                 # HTML templates
├── tests/                     # Test files
├── .env                       # Environment variables
├── alembic.ini               # Alembic configuration
├── celery_config.py          # Celery configuration
├── docker-compose.yml        # Docker composition
├── Dockerfile                # Docker configuration
├── requirements.txt          # Python dependencies
└── README.md                # Project documentation
``` 