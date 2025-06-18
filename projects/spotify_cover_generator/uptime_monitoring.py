"""
External uptime monitoring setup for third-party services
"""

import requests
import json
from typing import Dict, List
import os

class UptimeRobotAPI:
    """
    UptimeRobot API integration for external monitoring
    
    Design choices:
    - External monitoring ensures independence from app failures
    - Multiple check types (HTTP, keyword, port)
    - Integration with existing alert system
    - Automated monitor creation for new services
    """
    
    def __init__(self):
        self.api_key = os.getenv('UPTIMEROBOT_API_KEY')
        self.base_url = "https://api.uptimerobot.com/v2"
        
    def create_monitor(self, monitor_config: Dict) -> bool:
        """Create a new monitor"""
        if not self.api_key:
            print("UptimeRobot API key not configured")
            return False
            
        endpoint = f"{self.base_url}/newMonitor"
        
        data = {
            'api_key': self.api_key,
            'format': 'json',
            **monitor_config
        }
        
        try:
            response = requests.post(endpoint, data=data)
            result = response.json()
            
            if result.get('stat') == 'ok':
                print(f"Monitor created successfully: {monitor_config.get('friendly_name')}")
                return True
            else:
                print(f"Failed to create monitor: {result.get('error', {}).get('message')}")
                return False
                
        except Exception as e:
            print(f"Error creating monitor: {e}")
            return False
    
    def setup_app_monitoring(self, app_url: str) -> List[bool]:
        """Set up comprehensive monitoring for the app"""
        monitors = [
            {
                'friendly_name': 'Spotify Cover Gen - Main App',
                'url': f"{app_url}/",
                'type': 1,  # HTTP
                'interval': 300,  # 5 minutes
                'keyword_type': 2,  # keyword exists
                'keyword_value': 'Spotify Music Cover Generator'
            },
            {
                'friendly_name': 'Spotify Cover Gen - Health Check',
                'url': f"{app_url}/health",
                'type': 1,  # HTTP
                'interval': 300,
                'keyword_type': 2,
                'keyword_value': 'healthy'
            },
            {
                'friendly_name': 'Spotify Cover Gen - Generate Endpoint',
                'url': f"{app_url}/generate",
                'type': 1,  # HTTP
                'interval': 600,  # 10 minutes
                'http_method': 1  # GET
            }
        ]
        
        results = []
        for monitor in monitors:
            results.append(self.create_monitor(monitor))
            
        return results

# Pingdom integration (alternative to UptimeRobot)
class PingdomAPI:
    """Pingdom API integration"""
    
    def __init__(self):
        self.api_token = os.getenv('PINGDOM_API_TOKEN')
        self.email = os.getenv('PINGDOM_EMAIL')
        
    def create_check(self, check_config: Dict) -> bool:
        """Create Pingdom check"""
        if not self.api_token:
            print("Pingdom API token not configured")
            return False
            
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                'https://api.pingdom.com/api/3.1/checks',
                headers=headers,
                json=check_config
            )
            
            if response.status_code == 200:
                print(f"Pingdom check created: {check_config.get('name')}")
                return True
            else:
                print(f"Failed to create Pingdom check: {response.text}")
                return False
                
        except Exception as e:
            print(f"Error creating Pingdom check: {e}")
            return False

def setup_external_monitoring():
    """Set up external monitoring services"""
    app_url = os.getenv('RENDER_EXTERNAL_URL') or os.getenv('APP_URL')
    
    if not app_url:
        print("App URL not configured for external monitoring")
        return
    
    # Try UptimeRobot first
    uptimerobot = UptimeRobotAPI()
    if uptimerobot.api_key:
        print("Setting up UptimeRobot monitoring...")
        results = uptimerobot.setup_app_monitoring(app_url)
        if all(results):
            print("✅ UptimeRobot monitoring setup complete")
        else:
            print("⚠️ Some UptimeRobot monitors failed to create")
    
    # Fallback to Pingdom
    else:
        pingdom = PingdomAPI()
        if pingdom.api_token:
            print("Setting up Pingdom monitoring...")
            checks = [
                {
                    'name': 'Spotify Cover Gen - Main',
                    'host': app_url.replace('https://', '').replace('http://', ''),
                    'type': 'http',
                    'resolution': 5
                }
            ]
            
            for check in checks:
                pingdom.create_check(check)
        else:
            print("⚠️ No external monitoring API keys configured")

if __name__ == "__main__":
    setup_external_monitoring()
