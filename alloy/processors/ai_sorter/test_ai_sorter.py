import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from ai_sorter import app, parse_ai_output

client = TestClient(app)

def test_health_endpoint():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "ai-sorter"}

def test_sort_endpoint_missing_api_key():
    """Test sort endpoint fails without API key"""
    with patch.dict(os.environ, {}, clear=True):
        response = client.post("/sort", json={
            "items": [{"type": "log", "content": {"message": "Server crashed"}}]
        })
        assert response.status_code == 500
        assert "API key missing" in response.json()["detail"]

def test_sort_endpoint_empty_items():
    """Test sort endpoint with empty items list"""
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key"}):
        response = client.post("/sort", json={"items": []})
        assert response.status_code == 200
        assert response.json() == []

@patch('ai_sorter.requests.post')
def test_sort_endpoint_success(mock_post):
    """Test successful sorting with mocked AI API"""
    # Mock AI API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": """```yaml
classifications:
  - category: critical
    forward_to: alerting
```"""
            }
        }]
    }
    mock_post.return_value = mock_response
    
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key"}):
        response = client.post("/sort", json={
            "items": [{"type": "log", "content": {"message": "Server crashed"}}]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category"] == "critical"
        assert data[0]["forward_to"] == "alerting"
        assert data[0]["item"]["type"] == "log"

@patch('ai_sorter.requests.post')
def test_sort_endpoint_ai_api_error(mock_post):
    """Test handling of AI API errors"""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response
    
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key"}):
        response = client.post("/sort", json={
            "items": [{"type": "log", "content": {"message": "Server crashed"}}]
        })
        
        assert response.status_code == 500
        assert "AI API error: 500" in response.json()["detail"]

@patch('ai_sorter.requests.post')
def test_sort_endpoint_request_timeout(mock_post):
    """Test handling of request timeouts"""
    import requests
    mock_post.side_effect = requests.exceptions.Timeout("Request timeout")
    
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key"}):
        response = client.post("/sort", json={
            "items": [{"type": "log", "content": {"message": "Server crashed"}}]
        })
        
        assert response.status_code == 500
        assert "Failed to communicate with AI API" in response.json()["detail"]

def test_parse_ai_output_valid_yaml():
    """Test parsing valid YAML output from AI"""
    yaml_output = """```yaml
classifications:
  - category: critical
    forward_to: alerting
  - category: info
    forward_to: storage
```"""
    
    result = parse_ai_output(yaml_output)
    assert len(result) == 2
    assert result[0]["category"] == "critical"
    assert result[0]["forward_to"] == "alerting"
    assert result[1]["category"] == "info"
    assert result[1]["forward_to"] == "storage"

def test_parse_ai_output_plain_yaml():
    """Test parsing plain YAML without code blocks"""
    yaml_output = """classifications:
  - category: warning
    forward_to: storage"""
    
    result = parse_ai_output(yaml_output)
    assert len(result) == 1
    assert result[0]["category"] == "warning"
    assert result[0]["forward_to"] == "storage"

def test_parse_ai_output_invalid_yaml():
    """Test handling of invalid YAML"""
    invalid_yaml = "invalid: yaml: content: ["
    
    result = parse_ai_output(invalid_yaml)
    assert result == []

def test_parse_ai_output_unexpected_format():
    """Test handling of unexpected format"""
    unexpected_output = "This is not YAML at all"
    
    result = parse_ai_output(unexpected_output)
    assert result == []

@patch('ai_sorter.requests.post')
def test_sort_endpoint_fallback_classification(mock_post):
    """Test fallback classification when AI doesn't provide enough classifications"""
    # Mock AI API response with only one classification for two items
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": """```yaml
classifications:
  - category: critical
    forward_to: alerting
```"""
            }
        }]
    }
    mock_post.return_value = mock_response
    
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key"}):
        response = client.post("/sort", json={
            "items": [
                {"type": "log", "content": {"message": "Server crashed"}},
                {"type": "metric", "content": {"name": "cpu_usage"}}
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        # First item gets AI classification
        assert data[0]["category"] == "critical"
        assert data[0]["forward_to"] == "alerting"
        
        # Second item gets fallback classification
        assert data[1]["category"] == "info"
        assert data[1]["forward_to"] == "storage"

def test_sort_endpoint_multiple_items():
    """Test sorting multiple items"""
    with patch.dict(os.environ, {"GROK_API_KEY": "test-key"}):
        with patch('ai_sorter.requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": """```yaml
classifications:
  - category: critical
    forward_to: alerting
  - category: warning
    forward_to: storage
  - category: info
    forward_to: archive
```"""
                    }
                }]
            }
            mock_post.return_value = mock_response
            
            response = client.post("/sort", json={
                "items": [
                    {"type": "log", "content": {"level": "error", "message": "Database connection failed"}},
                    {"type": "metric", "content": {"name": "response_time", "value": 1500}},
                    {"type": "trace", "content": {"operation": "user_login", "duration": "100ms"}}
                ]
            })
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            
            assert data[0]["category"] == "critical"
            assert data[1]["category"] == "warning"
            assert data[2]["category"] == "info"

if __name__ == "__main__":
    pytest.main([__file__])