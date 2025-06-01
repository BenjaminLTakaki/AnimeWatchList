"""
Render-specific configuration and deployment settings
"""

import os
from pathlib import Path

# Render environment detection
IS_RENDER = bool(os.getenv('RENDER'))
RENDER_SERVICE_NAME = os.getenv('RENDER_SERVICE_NAME', 'spotify-cover-generator')

# Logging configuration for Render
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter'
        },
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'json' if IS_RENDER else 'standard',
            'stream': 'ext://sys.stdout'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    }
}

# Render-specific paths (use /tmp for temporary files)
if IS_RENDER:
    TEMP_DIR = Path("/tmp")
    UPLOAD_DIR = TEMP_DIR / "uploads"
    COVERS_DIR = TEMP_DIR / "generated_covers"
    LORAS_DIR = TEMP_DIR / "loras"
    
    # Ensure directories exist
    for directory in [UPLOAD_DIR, COVERS_DIR, LORAS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
else:
    # Local development paths
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
    TEMP_DIR = BASE_DIR / "temp"
    UPLOAD_DIR = BASE_DIR / "uploads"
    COVERS_DIR = BASE_DIR / "generated_covers"
    LORAS_DIR = BASE_DIR / "loras"

# Health check configuration
HEALTH_CHECK_CONFIG = {
    'check_interval_seconds': 300,  # 5 minutes
    'timeout_seconds': 30,
    'failure_threshold': 3,
    'recovery_timeout_seconds': 120
}

# Alert configuration
ALERT_CONFIG = {
    'email_enabled': bool(os.getenv('ALERT_EMAIL_USER')),
    'slack_enabled': bool(os.getenv('SLACK_WEBHOOK_URL')),
    'cooldown_critical_minutes': 15,
    'cooldown_warning_hours': 1,
    'cooldown_info_hours': 4
}

# Performance monitoring thresholds
PERFORMANCE_THRESHOLDS = {
    'response_time_warning_ms': 5000,
    'response_time_critical_ms': 10000,
    'error_rate_warning_percent': 10,
    'error_rate_critical_percent': 25,
    'cpu_warning_percent': 80,
    'cpu_critical_percent': 95,
    'memory_warning_percent': 85,
    'memory_critical_percent': 95
}

# Circuit breaker configuration
CIRCUIT_BREAKER_CONFIG = {
    'spotify_api': {
        'failure_threshold': 3,
        'recovery_timeout': 120,
        'timeout': 30
    },
    'gemini_api': {
        'failure_threshold': 5,
        'recovery_timeout': 60,
        'timeout': 30
    },
    'stability_api': {
        'failure_threshold': 3,
        'recovery_timeout': 300,  # Longer for image generation
        'timeout': 60
    },
    'database': {
        'failure_threshold': 2,
        'recovery_timeout': 30,
        'timeout': 10
    }
}
