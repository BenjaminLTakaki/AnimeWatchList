"""URL helper functions for SkillsTown."""
from flask import url_for, request

def get_url_for(endpoint, **values):
    """
    Enhanced url_for function that maintains the query string and correctly handles
    subdirectory deployments, making it more robust for different hosting environments.
    
    Args:
        endpoint: The name of the endpoint to generate URL for
        **values: Parameters to pass to the URL builder
        
    Returns:
        str: Generated URL with query parameters
    """
    # Generate the URL for the endpoint
    url = url_for(endpoint, **values)
    
    # Preserve query parameters if any
    if request.query_string:
        url = f"{url}?{request.query_string.decode('utf-8')}"
        
    return url
