import os
import time
import logging
import functools
import traceback
import psutil
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json
from flask import request, g, current_app
from dataclasses import dataclass, asdict
import threading
from collections import deque, defaultdict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure structured logging for Render
class RenderCloudLogger:
    """
    Custom logger optimized for Render's logging infrastructure
    
    Design choices:
    - JSON formatted logs for easy parsing by Render's log aggregation
    - Structured fields for better searchability
    - Performance metrics integrated into logs
    - Automatic error categorization
    """
    
    def __init__(self, app_name: str = "spotify-cover-generator"):
        self.app_name = app_name
        self.logger = logging.getLogger(app_name)
        self.logger.setLevel(logging.INFO)
        
        # Remove default handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Create JSON formatter for structured logging
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler for Render (Render captures stdout/stderr)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Performance tracking
        self.performance_metrics = deque(maxlen=1000)  # Keep last 1000 requests
        self.error_counts = defaultdict(int)
        self.start_time = datetime.utcnow()
        
    def log_structured(self, level: str, event: str, **kwargs):
        """Log structured data with consistent format"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "app": self.app_name,
            "event": event,
            "level": level,
            **kwargs
        }
        
        message = json.dumps(log_data, default=str)
        getattr(self.logger, level.lower())(message)
        
    def log_request(self, endpoint: str, method: str, status_code: int, 
                   duration_ms: float, user_id: Optional[str] = None, 
                   error: Optional[str] = None):
        """Log HTTP request with performance metrics"""
        self.performance_metrics.append({
            "timestamp": datetime.utcnow(),
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "error": error
        })
        
        self.log_structured(
            "info" if status_code < 400 else "error",
            "http_request",
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            user_id=user_id,
            error=error
        )
        
    def log_generation_attempt(self, user_id: Optional[str], playlist_url: str, 
                             success: bool, duration_ms: float, error: Optional[str] = None,
                             lora_used: Optional[str] = None, ai_model: str = "stable-diffusion"):
        """Log cover generation attempts with detailed metrics"""
        self.log_structured(
            "info" if success else "error",
            "cover_generation",
            user_id=user_id,
            playlist_url=playlist_url[:50] + "..." if len(playlist_url) > 50 else playlist_url,
            success=success,
            duration_ms=duration_ms,
            error=error,
            lora_used=lora_used,
            ai_model=ai_model
        )
        
    def log_api_call(self, service: str, endpoint: str, success: bool, 
                    duration_ms: float, error: Optional[str] = None, 
                    rate_limited: bool = False):
        """Log external API calls (Spotify, Gemini, Stable Diffusion)"""
        if not success:
            self.error_counts[f"{service}_api_error"] += 1
            
        self.log_structured(
            "info" if success else "error",
            "external_api_call",
            service=service,
            endpoint=endpoint,
            success=success,
            duration_ms=duration_ms,
            error=error,
            rate_limited=rate_limited
        )
        
    def log_system_metrics(self):
        """Log system performance metrics"""
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            self.log_structured(
                "info",
                "system_metrics",
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_available_mb=memory.available // 1024 // 1024,
                disk_percent=disk.percent,
                disk_free_gb=disk.free // 1024 // 1024 // 1024
            )
        except Exception as e:
            self.log_structured("error", "system_metrics_error", error=str(e))
            
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for the last hour"""
        if not self.performance_metrics:
            return {}
            
        recent_metrics = [
            m for m in self.performance_metrics 
            if m["timestamp"] > datetime.utcnow() - timedelta(hours=1)
        ]
        
        if not recent_metrics:
            return {}
            
        durations = [m["duration_ms"] for m in recent_metrics]
        errors = [m for m in recent_metrics if m.get("error")]
        
        return {
            "total_requests": len(recent_metrics),
            "avg_response_time_ms": sum(durations) / len(durations),
            "max_response_time_ms": max(durations),
            "error_rate": len(errors) / len(recent_metrics) * 100,
            "uptime_hours": (datetime.utcnow() - self.start_time).total_seconds() / 3600
        }

# Global logger instance
app_logger = RenderCloudLogger()

@dataclass
class HealthCheckResult:
    """Health check result with detailed component status"""
    service: str
    healthy: bool
    response_time_ms: float
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class HealthChecker:
    """
    Comprehensive health checking for all service dependencies
    
    Design choices:
    - Individual component checks for granular monitoring
    - Timeout handling to prevent health checks from hanging
    - Detailed error reporting for faster debugging
    - Render-specific optimizations (checking external services that matter)
    """
    
    def __init__(self):
        self.last_check_time = None
        self.last_results = {}
        
    def check_database(self) -> HealthCheckResult:
        """Check PostgreSQL database connectivity"""
        start_time = time.time()
        try:
            from app import db, app
            with app.app_context():
                # Simple query to test connection
                db.session.execute(db.text('SELECT 1'))
                response_time = (time.time() - start_time) * 1000
                return HealthCheckResult(
                    service="database",
                    healthy=True,
                    response_time_ms=response_time
                )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                service="database",
                healthy=False,
                response_time_ms=response_time,
                error=str(e)
            )
            
    def check_spotify_api(self) -> HealthCheckResult:
        """Check Spotify API connectivity"""
        start_time = time.time()
        try:
            from spotify_client import sp
            if sp:
                # Simple search to test API
                sp.search(q='test', type='track', limit=1)
                response_time = (time.time() - start_time) * 1000
                return HealthCheckResult(
                    service="spotify_api",
                    healthy=True,
                    response_time_ms=response_time
                )
            else:
                return HealthCheckResult(
                    service="spotify_api",
                    healthy=False,
                    response_time_ms=0,
                    error="Spotify client not initialized"
                )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                service="spotify_api",
                healthy=False,
                response_time_ms=response_time,
                error=str(e)
            )
            
    def check_gemini_api(self) -> HealthCheckResult:
        """Check Google Gemini API connectivity"""
        start_time = time.time()
        try:
            from config import GEMINI_API_KEY, GEMINI_API_URL
            if not GEMINI_API_KEY:
                return HealthCheckResult(
                    service="gemini_api",
                    healthy=False,
                    response_time_ms=0,
                    error="API key not configured"
                )
                
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": "test"}]}],
                "generationConfig": {"maxOutputTokens": 5}
            }
            
            url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                return HealthCheckResult(
                    service="gemini_api",
                    healthy=True,
                    response_time_ms=response_time
                )
            else:
                return HealthCheckResult(
                    service="gemini_api",
                    healthy=False,
                    response_time_ms=response_time,
                    error=f"HTTP {response.status_code}: {response.text[:100]}"
                )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                service="gemini_api",
                healthy=False,
                response_time_ms=response_time,
                error=str(e)
            )
            
    def check_stability_api(self) -> HealthCheckResult:
        """Check Stability AI API connectivity"""
        start_time = time.time()
        try:
            from config import STABILITY_API_KEY
            if not STABILITY_API_KEY:
                return HealthCheckResult(
                    service="stability_api",
                    healthy=False,
                    response_time_ms=0,
                    error="API key not configured"
                )
            
            # Just check if we can reach the API endpoint
            headers = {"Authorization": f"Bearer {STABILITY_API_KEY}"}
            response = requests.get(
                "https://api.stability.ai/v1/user/account", 
                headers=headers, 
                timeout=10
            )
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code in [200, 401]:  # 401 is ok, means API is reachable
                return HealthCheckResult(
                    service="stability_api",
                    healthy=True,
                    response_time_ms=response_time
                )
            else:
                return HealthCheckResult(
                    service="stability_api",
                    healthy=False,
                    response_time_ms=response_time,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                service="stability_api",
                healthy=False,
                response_time_ms=response_time,
                error=str(e)
            )
            
    def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all health checks and return results"""
        checks = [
            self.check_database,
            self.check_spotify_api,
            self.check_gemini_api,
            self.check_stability_api
        ]
        
        results = {}
        for check in checks:
            try:
                result = check()
                results[result.service] = result
            except Exception as e:
                # Fallback if health check itself fails
                results[check.__name__.replace('check_', '')] = HealthCheckResult(
                    service=check.__name__.replace('check_', ''),
                    healthy=False,
                    response_time_ms=0,
                    error=f"Health check failed: {str(e)}"
                )
                
        self.last_check_time = datetime.utcnow()
        self.last_results = results
        return results

# Global health checker
health_checker = HealthChecker()

class AlertManager:
    """
    Alert system for critical failures and performance issues
    
    Design choices:
    - Email alerts for critical issues (suitable for small team/solo developer)
    - Rate limiting to prevent alert spam
    - Severity levels to prioritize issues
    - Integration with multiple notification channels
    """
    
    def __init__(self):
        self.email_config = {
            'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            'smtp_port': int(os.getenv('SMTP_PORT', '587')),
            'email_user': os.getenv('ALERT_EMAIL_USER'),
            'email_pass': os.getenv('ALERT_EMAIL_PASS'),
            'alert_recipients': os.getenv('ALERT_RECIPIENTS', '').split(',')
        }
        
        # Rate limiting for alerts (don't spam)
        self.alert_cooldowns = defaultdict(lambda: datetime.min)
        self.cooldown_periods = {
            'critical': timedelta(minutes=15),
            'warning': timedelta(hours=1),
            'info': timedelta(hours=4)
        }
        
    def should_send_alert(self, alert_type: str, severity: str) -> bool:
        """Check if we should send alert based on cooldown"""
        key = f"{alert_type}_{severity}"
        now = datetime.utcnow()
        last_sent = self.alert_cooldowns[key]
        cooldown = self.cooldown_periods.get(severity, timedelta(hours=1))
        
        if now - last_sent > cooldown:
            self.alert_cooldowns[key] = now
            return True
        return False
        
    def send_email_alert(self, subject: str, message: str, severity: str = 'warning'):
        """Send email alert"""
        if not self.email_config['email_user'] or not self.email_config['alert_recipients']:
            app_logger.log_structured("warning", "email_alert_not_configured")
            return
            
        try:
            msg = MimeMultipart()
            msg['From'] = self.email_config['email_user']
            msg['To'] = ', '.join(self.email_config['alert_recipients'])
            msg['Subject'] = f"[{severity.upper()}] Spotify Cover Gen: {subject}"
            
            body = f"""
            Alert Time: {datetime.utcnow().isoformat()}
            Severity: {severity.upper()}
            
            {message}
            
            --
            Spotify Cover Generator Monitoring System
            Deployed on Render
            """
            
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['email_user'], self.email_config['email_pass'])
            server.send_message(msg)
            server.quit()
            
            app_logger.log_structured("info", "alert_sent", 
                                    subject=subject, severity=severity)
            
        except Exception as e:
            app_logger.log_structured("error", "alert_send_failed", 
                                    error=str(e), subject=subject)
            
    def send_slack_webhook(self, message: str, severity: str = 'warning'):
        """Send Slack alert via webhook"""
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        if not webhook_url:
            return
            
        try:
            color_map = {
                'critical': '#FF0000',
                'warning': '#FFA500', 
                'info': '#00FF00'
            }
            
            payload = {
                "attachments": [{
                    "color": color_map.get(severity, '#FFA500'),
                    "title": f"Spotify Cover Generator Alert ({severity.upper()})",
                    "text": message,
                    "timestamp": int(datetime.utcnow().timestamp())
                }]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                app_logger.log_structured("info", "slack_alert_sent", severity=severity)
            else:
                app_logger.log_structured("error", "slack_alert_failed", 
                                        status_code=response.status_code)
                
        except Exception as e:
            app_logger.log_structured("error", "slack_alert_failed", error=str(e))
            
    def alert(self, alert_type: str, message: str, severity: str = 'warning', 
             details: Optional[Dict] = None):
        """Send alert through all configured channels"""
        if not self.should_send_alert(alert_type, severity):
            return
            
        app_logger.log_structured(severity, f"alert_{alert_type}", 
                                message=message, details=details)
        
        # Send through all channels
        if severity in ['critical', 'warning']:
            self.send_email_alert(alert_type.replace('_', ' ').title(), message, severity)
            self.send_slack_webhook(message, severity)

# Global alert manager
alert_manager = AlertManager()

def monitor_performance(func):
    """
    Decorator for monitoring function performance and errors
    
    This decorator automatically logs:
    - Function execution time
    - Success/failure status
    - Error details
    - Function arguments (sanitized)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        function_name = f"{func.__module__}.{func.__name__}"
        
        # Sanitize arguments (remove sensitive data)
        safe_kwargs = {k: v for k, v in kwargs.items() 
                      if k not in ['password', 'token', 'key', 'secret']}
        
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            
            app_logger.log_structured(
                "info", 
                "function_execution",
                function=function_name,
                duration_ms=duration_ms,
                success=True,
                kwargs=safe_kwargs
            )
            
            # Alert on slow functions (>10 seconds)
            if duration_ms > 10000:
                alert_manager.alert(
                    "slow_function",
                    f"Function {function_name} took {duration_ms:.0f}ms to execute",
                    severity="warning",
                    details={"function": function_name, "duration_ms": duration_ms}
                )
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_details = {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
            
            app_logger.log_structured(
                "error",
                "function_error", 
                function=function_name,
                duration_ms=duration_ms,
                success=False,
                kwargs=safe_kwargs,
                **error_details
            )
            
            # Alert on critical function failures
            if func.__name__ in ['generate_cover', 'extract_playlist_data', 'generate_cover_image']:
                alert_manager.alert(
                    "critical_function_failure",
                    f"Critical function {function_name} failed: {str(e)}",
                    severity="critical",
                    details=error_details
                )
            
            raise
            
    return wrapper

def monitor_api_calls(service_name: str):
    """Decorator for monitoring external API calls"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                app_logger.log_api_call(
                    service=service_name,
                    endpoint=func.__name__,
                    success=True,
                    duration_ms=duration_ms
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                is_rate_limited = "rate limit" in str(e).lower() or "429" in str(e)
                
                app_logger.log_api_call(
                    service=service_name,
                    endpoint=func.__name__,
                    success=False,
                    duration_ms=duration_ms,
                    error=str(e),
                    rate_limited=is_rate_limited
                )
                
                # Alert on repeated API failures
                if not is_rate_limited:
                    alert_manager.alert(
                        f"{service_name}_api_failure",
                        f"{service_name} API call failed: {str(e)}",
                        severity="warning"
                    )
                
                raise
                
        return wrapper
    return decorator

class SystemMonitor:
    """
    Background system monitoring for resource usage and health
    
    Runs in a separate thread to continuously monitor:
    - System resources (CPU, memory, disk)
    - Application health
    - Error rates
    - Performance trends
    """
    
    def __init__(self, check_interval: int = 300):  # 5 minutes
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        
    def start(self):
        """Start background monitoring"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        app_logger.log_structured("info", "system_monitor_started")
        
    def stop(self):
        """Stop background monitoring"""
        self.running = False
        if self.thread:
            self.thread.join()
        app_logger.log_structured("info", "system_monitor_stopped")
        
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Log system metrics
                app_logger.log_system_metrics()
                
                # Run health checks
                health_results = health_checker.run_all_checks()
                
                # Check for unhealthy services
                unhealthy_services = [
                    name for name, result in health_results.items() 
                    if not result.healthy
                ]
                
                if unhealthy_services:
                    alert_manager.alert(
                        "service_health_check_failed",
                        f"Unhealthy services detected: {', '.join(unhealthy_services)}",
                        severity="critical" if "database" in unhealthy_services else "warning",
                        details={"unhealthy_services": unhealthy_services}
                    )
                
                # Check performance metrics
                perf_summary = app_logger.get_performance_summary()
                if perf_summary:
                    # Alert on high error rate
                    if perf_summary.get("error_rate", 0) > 25:
                        alert_manager.alert(
                            "high_error_rate",
                            f"Error rate is {perf_summary['error_rate']:.1f}% over the last hour",
                            severity="warning",
                            details=perf_summary
                        )
                    
                    # Alert on slow response times
                    if perf_summary.get("avg_response_time_ms", 0) > 5000:
                        alert_manager.alert(
                            "slow_response_times",
                            f"Average response time is {perf_summary['avg_response_time_ms']:.0f}ms",
                            severity="warning",
                            details=perf_summary
                        )
                
            except Exception as e:
                app_logger.log_structured("error", "monitor_loop_error", error=str(e))
                
            # Wait for next check
            time.sleep(self.check_interval)

# Global system monitor
system_monitor = SystemMonitor()

def setup_monitoring(app):
    """Set up monitoring for Flask app"""
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
        
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            duration_ms = (time.time() - g.start_time) * 1000
            
            # Get user ID if available
            user_id = None
            try:
                from app import get_current_user
                user = get_current_user()
                user_id = str(user.id) if user else None
            except:
                pass
                
            app_logger.log_request(
                endpoint=request.endpoint or request.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=user_id,
                error=None if response.status_code < 400 else f"HTTP {response.status_code}"
            )
            
        return response
        
    @app.errorhandler(500)
    def handle_500_error(e):
        app_logger.log_structured(
            "error",
            "server_error",
            error=str(e),
            endpoint=request.endpoint,
            method=request.method,
            url=request.url
        )
        
        alert_manager.alert(
            "server_error",
            f"500 error on {request.method} {request.path}: {str(e)}",
            severity="critical"
        )
        
        return "Internal Server Error", 500
        
    # FIXED: Check if health route already exists before adding it
    if not any(rule.endpoint == 'health_check' for rule in app.url_map.iter_rules()):
        @app.route('/health')
        def health_check():
            """Health check endpoint for uptime monitoring"""
            try:
                health_results = health_checker.run_all_checks()
                all_healthy = all(result.healthy for result in health_results.values())
                
                response_data = {
                    "status": "healthy" if all_healthy else "degraded",
                    "timestamp": datetime.utcnow().isoformat(),
                    "uptime_hours": (datetime.utcnow() - app_logger.start_time).total_seconds() / 3600,
                    "services": {name: asdict(result) for name, result in health_results.items()},
                    "performance": app_logger.get_performance_summary()
                }
                
                return response_data, 200 if all_healthy else 503
                
            except Exception as e:
                app_logger.log_structured("error", "health_check_failed", error=str(e))
                return {"status": "error", "error": str(e)}, 500
    
    # FIXED: Check if metrics route already exists before adding it        
    if not any(rule.endpoint == 'metrics_endpoint' for rule in app.url_map.iter_rules()):
        @app.route('/metrics')
        def metrics_endpoint():
            """Detailed metrics endpoint"""
            try:
                return {
                    "performance": app_logger.get_performance_summary(),
                    "error_counts": dict(app_logger.error_counts),
                    "uptime_hours": (datetime.utcnow() - app_logger.start_time).total_seconds() / 3600,
                    "last_health_check": health_checker.last_check_time.isoformat() if health_checker.last_check_time else None
                }
            except Exception as e:
                return {"error": str(e)}, 500
    
    # Start background monitoring
    system_monitor.start()
    
    app_logger.log_structured("info", "monitoring_setup_complete")

# Export decorators and utilities for use in other modules
__all__ = [
    'app_logger', 'health_checker', 'alert_manager', 'system_monitor',
    'monitor_performance', 'monitor_api_calls', 'setup_monitoring',
    'RenderCloudLogger', 'HealthChecker', 'AlertManager', 'SystemMonitor'
]