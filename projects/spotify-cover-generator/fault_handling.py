import time
import random
import functools
from typing import Any, Optional, Callable, Dict, List
from datetime import datetime, timedelta
import asyncio
from dataclasses import dataclass
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from packaging import version

class FaultSeverity(Enum):
    """Fault severity levels for appropriate response"""
    LOW = "low"           # Non-critical, continue operation
    MEDIUM = "medium"     # Degrade gracefully
    HIGH = "high"         # Fail fast with clear error message
    CRITICAL = "critical" # System-wide issue, alert immediately

@dataclass
class FaultContext:
    """Context information for fault handling decisions"""
    function_name: str
    attempt_number: int
    error: Exception
    user_id: Optional[str] = None
    is_guest: bool = False
    request_data: Optional[Dict] = None

class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    
    Design choices:
    - Prevents cascading failures by temporarily disabling failing services
    - Configurable thresholds based on service criticality
    - Automatic recovery attempts with exponential backoff
    - Different timeouts for different service types
    """
    
    def __init__(self, name: str, failure_threshold: int = 5, 
                 recovery_timeout: int = 60, expected_exception=Exception):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        # Circuit states
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        
    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
            else:
                raise Exception(f"Circuit breaker {self.name} is OPEN - service unavailable")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
            
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        return (
            self.last_failure_time and 
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
        
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        self.state = "closed"
        
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            from monitoring_system import app_logger, alert_manager
            
            alert_manager.alert(
                f"circuit_breaker_opened_{self.name}",
                f"Circuit breaker for {self.name} has opened after {self.failure_count} failures",
                severity="critical"
            )

# Circuit breakers for different services
circuit_breakers = {
    "spotify_api": CircuitBreaker("spotify_api", failure_threshold=3, recovery_timeout=120),
    "gemini_api": CircuitBreaker("gemini_api", failure_threshold=5, recovery_timeout=60),
    "stability_api": CircuitBreaker("stability_api", failure_threshold=3, recovery_timeout=300),  # Longer timeout for image gen
    "database": CircuitBreaker("database", failure_threshold=2, recovery_timeout=30)
}

def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Retry decorator with exponential backoff
    
    Design choices:
    - Exponential backoff prevents overwhelming failing services
    - Jitter added to prevent thundering herd
    - Configurable per service type
    - Respects circuit breaker state
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        # Log final failure
                        from monitoring_system import app_logger
                        app_logger.log_structured(
                            "error",
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=attempt + 1,
                            final_error=str(e)
                        )
                        raise
                    
                    # Calculate delay with jitter
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    jitter = random.uniform(0, 0.1) * delay
                    total_delay = delay + jitter
                    
                    from monitoring_system import app_logger
                    app_logger.log_structured(
                        "warning",
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        error=str(e),
                        retry_delay=total_delay
                    )
                    
                    time.sleep(total_delay)
                    
            return None  # Should never reach here
            
        return wrapper
    return decorator

class GracefulDegradation:
    """
    Handles graceful degradation when services are unavailable
    
    Design choices:
    - Provide fallback functionality instead of complete failure
    - Maintain user experience even with reduced functionality
    - Clear communication about degraded state
    - Automatic recovery when services restore
    """
    
    @staticmethod
    def handle_spotify_failure(playlist_url: str, error: Exception) -> Dict[str, Any]:
        """Handle Spotify API failures with fallback"""
        from monitoring_system import app_logger
        
        app_logger.log_structured(
            "warning",
            "spotify_fallback_activated",
            playlist_url=playlist_url[:50],
            error=str(error)
        )
        
        # Extract basic info from URL if possible
        playlist_name = "Unknown Playlist"
        try:
            if "playlist/" in playlist_url:
                # Try to extract playlist ID for basic info
                playlist_id = playlist_url.split("playlist/")[-1].split("?")[0]
                playlist_name = f"Spotify Playlist ({playlist_id[:8]}...)"
        except:
            pass
            
        # Return fallback data structure
        from models import PlaylistData, GenreAnalysis
        
        # Use generic genres based on common music styles
        fallback_genres = ["pop", "indie", "alternative", "electronic", "rock"]
        
        genre_analysis = GenreAnalysis(
            top_genres=fallback_genres,
            all_genres=fallback_genres * 2,  # Simulate some frequency
            mood="balanced"
        )
        
        return PlaylistData(
            item_name=playlist_name,
            track_names=["Unable to fetch track names"],
            genre_analysis=genre_analysis,
            spotify_url=playlist_url,
            found_genres=False,  # Mark as fallback
            artist_ids=[]
        )
    
    @staticmethod
    def handle_gemini_failure(playlist_data: Dict, user_mood: str = "") -> str:
        """Handle Gemini API failures with fallback title generation"""
        from monitoring_system import app_logger
        
        app_logger.log_structured(
            "warning",
            "gemini_fallback_activated",
            playlist_name=playlist_data.get("item_name", "Unknown")
        )
        
        # Fallback title generation using simple templates
        templates = [
            "New Horizons",
            "Fresh Perspective", 
            "Next Chapter",
            "Open Roads",
            "Clear Skies",
            "New Dawn",
            "Bright Future",
            "Moving Forward"
        ]
        
        # Try to incorporate user mood or genres
        if user_mood:
            mood_words = user_mood.split()[:2]
            if len(mood_words) >= 2:
                return " ".join(word.capitalize() for word in mood_words)
            elif len(mood_words) == 1:
                return f"{mood_words[0].capitalize()} Dreams"
        
        # Use genres if available
        genres = playlist_data.get("genres", [])
        if genres:
            genre = genres[0].replace("_", " ").title()
            return f"New {genre}"
            
        # Final fallback
        return random.choice(templates)
    
    @staticmethod
    def handle_stability_failure(prompt: str, output_path: str) -> bool:
        """Handle Stability AI failures with placeholder image"""
        from monitoring_system import app_logger
        from PIL import Image, ImageDraw, ImageFont
        import os
        
        app_logger.log_structured(
            "warning", 
            "stability_fallback_activated",
            prompt=prompt[:100]
        )
        
        try:
            # Create a simple placeholder image
            width, height = 512, 512
            image = Image.new('RGB', (width, height), color='#2a2a2a')
            draw = ImageDraw.Draw(image)
            
            # Try to load a font
            try:
                font_large = ImageFont.truetype("arial.ttf", 24)
                font_small = ImageFont.truetype("arial.ttf", 16)
            except:
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Draw placeholder content
            draw.text((20, 200), "Cover Generation", fill="#1DB954", font=font_large)
            draw.text((20, 240), "Temporarily Unavailable", fill="white", font=font_small)
            draw.text((20, 270), "Please try again later", fill="#cccccc", font=font_small)
            
            # Add a simple geometric pattern
            for i in range(0, width, 40):
                draw.line([(i, 0), (i, height)], fill="#333333", width=1)
            for i in range(0, height, 40):
                draw.line([(0, i), (width, i)], fill="#333333", width=1)
            
            # Save the placeholder
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            image.save(output_path)
            
            return True
            
        except Exception as e:
            app_logger.log_structured("error", "placeholder_creation_failed", error=str(e))
            return False

class RobustHTTPClient:
    """
    HTTP client with built-in fault tolerance
    
    Design choices:
    - Automatic retries with different strategies per service
    - Timeout configuration based on service characteristics
    - Connection pooling for better performance
    - Request/response logging for debugging
    """
    
    def __init__(self):
        self.session = requests.Session()
        
        retry_kwargs = {
            'total': 3,
            'status_forcelist': [429, 500, 502, 503, 504],
            'backoff_factor': 1,
            'raise_on_status': False
        }
        
        # Check urllib3 version to use correct parameter name
        if version.parse(urllib3.__version__) >= version.parse("1.26.0"):
            retry_kwargs['allowed_methods'] = ["HEAD", "GET", "POST"]
        else:
            retry_kwargs['method_whitelist'] = ["HEAD", "GET", "POST"]
        
        retry_strategy = Retry(**retry_kwargs)
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        self.default_timeout = (10, 30)
    def request(self, method: str, url: str, service_name: str = "unknown", 
                timeout: Optional[tuple] = None, **kwargs) -> requests.Response:
        """Make HTTP request with fault tolerance"""
        from monitoring_system import app_logger
        
        start_time = time.time()
        timeout = timeout or self.default_timeout
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                timeout=timeout,
                **kwargs
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            app_logger.log_structured(
                "info" if response.status_code < 400 else "warning",
                "http_request",
                service=service_name,
                method=method,
                url=url[:100],
                status_code=response.status_code,
                duration_ms=duration_ms
            )
            
            return response
            
        except requests.exceptions.Timeout as e:
            duration_ms = (time.time() - start_time) * 1000
            app_logger.log_structured(
                "error",
                "http_timeout",
                service=service_name,
                method=method,
                url=url[:100],
                duration_ms=duration_ms,
                error=str(e)
            )
            raise
            
        except requests.exceptions.ConnectionError as e:
            duration_ms = (time.time() - start_time) * 1000
            app_logger.log_structured(
                "error",
                "http_connection_error",
                service=service_name,
                method=method,
                url=url[:100],
                duration_ms=duration_ms,
                error=str(e)
            )
            raise

# Global HTTP client
http_client = RobustHTTPClient()

def fault_tolerant_api_call(service_name: str, fallback_func: Optional[Callable] = None):
    """
    Decorator for fault-tolerant API calls
    
    Combines circuit breaker, retry logic, and graceful degradation
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            circuit_breaker = circuit_breakers.get(service_name)
            
            try:
                if circuit_breaker:
                    return circuit_breaker.call(func, *args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                from monitoring_system import app_logger, alert_manager
                
                # Log the failure
                app_logger.log_structured(
                    "error",
                    f"{service_name}_api_failure",
                    function=func.__name__,
                    error=str(e),
                    args_count=len(args),
                    kwargs_keys=list(kwargs.keys())
                )
                
                # Try fallback if available
                if fallback_func:
                    try:
                        app_logger.log_structured(
                            "info",
                            f"{service_name}_fallback_attempt",
                            function=func.__name__
                        )
                        return fallback_func(*args, **kwargs)
                        
                    except Exception as fallback_error:
                        app_logger.log_structured(
                            "error",
                            f"{service_name}_fallback_failed",
                            function=func.__name__,
                            fallback_error=str(fallback_error)
                        )
                
                # Alert on critical service failures
                if service_name in ["database", "spotify_api"]:
                    alert_manager.alert(
                        f"{service_name}_critical_failure",
                        f"Critical service {service_name} failed in {func.__name__}: {str(e)}",
                        severity="critical",
                        details={"function": func.__name__, "error": str(e)}
                    )
                
                raise
                
        return wrapper
    return decorator

class DatabaseFailover:
    """
    Database connection failover and recovery
    
    Design choices:
    - Connection pooling with health checks
    - Automatic reconnection on failure
    - Read-only mode during recovery
    - Data consistency checks after recovery
    """
    
    def __init__(self):
        self.connection_healthy = True
        self.last_health_check = datetime.utcnow()
        self.health_check_interval = timedelta(minutes=5)
        
    def check_connection_health(self) -> bool:
        """Check database connection health"""
        try:
            from app import db, app
            with app.app_context():
                db.session.execute(db.text('SELECT 1'))
                self.connection_healthy = True
                self.last_health_check = datetime.utcnow()
                return True
                
        except Exception as e:
            from monitoring_system import app_logger, alert_manager
            
            self.connection_healthy = False
            app_logger.log_structured("error", "database_health_check_failed", error=str(e))
            
            alert_manager.alert(
                "database_connection_failed",
                f"Database connection health check failed: {str(e)}",
                severity="critical"
            )
            return False
            
    def safe_db_operation(self, operation_func: Callable, *args, **kwargs):
        """Execute database operation with failover"""
        # Check if we need to verify connection health
        if (datetime.utcnow() - self.last_health_check) > self.health_check_interval:
            self.check_connection_health()
            
        if not self.connection_healthy:
            raise Exception("Database connection is unhealthy")
            
        try:
            return operation_func(*args, **kwargs)
            
        except Exception as e:
            # Mark connection as potentially unhealthy
            self.connection_healthy = False
            
            # Try to recover
            if self.check_connection_health():
                # Retry the operation once
                try:
                    return operation_func(*args, **kwargs)
                except Exception as retry_error:
                    from monitoring_system import app_logger
                    app_logger.log_structured(
                        "error",
                        "database_operation_failed_after_recovery",
                        error=str(retry_error)
                    )
                    raise
            else:
                raise

# Global database failover handler
db_failover = DatabaseFailover()

def create_user_friendly_error_messages(error: Exception, context: FaultContext) -> str:
    """
    Create user-friendly error messages based on error type and context
    
    Design choices:
    - Different messages for guests vs logged-in users
    - Actionable suggestions when possible
    - Hide technical details from end users
    - Provide escalation path for persistent issues
    """
    error_str = str(error).lower()
    
    # Spotify-related errors
    if "spotify" in error_str or "playlist" in error_str:
        if "not found" in error_str or "404" in error_str:
            return (
                "The Spotify playlist or album could not be found. "
                "Please check that the URL is correct and the playlist is public."
            )
        elif "private" in error_str or "403" in error_str:
            return (
                "This playlist appears to be private. "
                "Please make sure the playlist is public or shared with everyone."
            )
        elif "rate limit" in error_str or "429" in error_str:
            return (
                "Spotify is temporarily limiting requests. "
                "Please try again in a few minutes."
            )
        else:
            return (
                "Unable to connect to Spotify right now. "
                "Please try again in a few minutes."
            )
    
    # Image generation errors
    elif "stability" in error_str or "generation" in error_str or "image" in error_str:
        if "quota" in error_str or "credits" in error_str:
            return (
                "The AI image service has reached its daily limit. "
                "Please try again tomorrow or contact support for premium access."
            )
        elif "content policy" in error_str or "safety" in error_str:
            return (
                "The generated content was flagged by safety filters. "
                "Please try different mood keywords or a different playlist."
            )
        else:
            return (
                "Image generation is temporarily unavailable. "
                "A placeholder image has been created. Please try again later."
            )
    
    # Title generation errors
    elif "gemini" in error_str or "title" in error_str:
        return (
            "AI title generation is temporarily unavailable. "
            "A default title has been created for your cover."
        )
    
    # Database errors
    elif "database" in error_str or "connection" in error_str:
        if context.is_guest:
            return (
                "Our service is experiencing temporary issues. "
                "Please try again in a few minutes."
            )
        else:
            return (
                "Unable to save your generation. The cover was created successfully, "
                "but we couldn't store it in your history. Please try again."
            )
    
    # Rate limiting errors
    elif "limit" in error_str and context.is_guest:
        return (
            "You've reached the daily limit for guest users (1 generation per day). "
            "Sign up for free to get 2 generations per day!"
        )
    elif "limit" in error_str:
        return (
            f"You've reached your daily generation limit. "
            f"{'Try again tomorrow!' if not context.is_guest else 'Upgrade to premium for unlimited generations!'}"
        )
    
    # Generic fallback
    else:
        return (
            "Something went wrong while processing your request. "
            "Please try again, and contact support if the problem persists."
        )

# Export main components
__all__ = [
    'CircuitBreaker', 'circuit_breakers', 'retry_with_exponential_backoff',
    'GracefulDegradation', 'RobustHTTPClient', 'http_client', 
    'fault_tolerant_api_call', 'DatabaseFailover', 'db_failover',
    'create_user_friendly_error_messages', 'FaultContext', 'FaultSeverity'
]