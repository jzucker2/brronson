import pytest
from fastapi.testclient import TestClient
from app.main import app
import re

client = TestClient(app)

class TestAPIEndpoints:
    """Test cases for API endpoints"""
    
    def test_root_endpoint(self):
        """Test the root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Welcome to Bronson API"
        assert data["version"] == "1.0.0"
    
    def test_health_check(self):
        """Test the health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "bronson-api"
    
    def test_get_items(self):
        """Test getting list of items"""
        response = client.get("/api/v1/items")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 3
    
    def test_create_item(self):
        """Test creating a new item"""
        item_data = {"name": "Test Item", "description": "A test item"}
        response = client.post("/api/v1/items", json=item_data)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Item created"
        assert data["item"] == item_data
    
    def test_get_item_by_id(self):
        """Test getting a specific item by ID"""
        item_id = 123
        response = client.get(f"/api/v1/items/{item_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["item_id"] == item_id
        assert data["name"] == f"Item {item_id}"

class TestMetrics:
    """Test cases for Prometheus metrics"""
    
    def test_metrics_endpoint_exists(self):
        """Test that metrics endpoint exists and returns data"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    
    def test_metrics_contain_http_requests_total(self):
        """Test that metrics contain http_requests_total counter"""
        # Make a request to generate metrics
        client.get("/health")
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for http_requests_total metric
        assert "http_requests_total" in metrics_text
    
    def test_metrics_contain_http_request_duration(self):
        """Test that metrics contain http_request_duration_seconds histogram"""
        # Make a request to generate metrics
        client.get("/health")
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for http_request_duration_seconds metric
        assert "http_request_duration_seconds" in metrics_text
    
    def test_metrics_format(self):
        """Test that metrics are in proper Prometheus format"""
        # Make some requests to generate metrics
        client.get("/")
        client.get("/health")
        client.get("/api/v1/items")
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for proper Prometheus format
        lines = metrics_text.strip().split('\n')
        
        # Should have some metric lines
        assert len(lines) > 0
        
        # Check that lines start with metric names or are comments
        for line in lines:
            if line and not line.startswith('#'):
                # Should match Prometheus metric format
                assert re.match(r'^[a-zA-Z_:][a-zA-Z0-9_:]*\s', line) is not None

class TestErrorHandling:
    """Test cases for error handling"""
    
    def test_404_for_nonexistent_endpoint(self):
        """Test 404 response for non-existent endpoints"""
        response = client.get("/nonexistent")
        assert response.status_code == 404
    
    def test_405_for_wrong_method(self):
        """Test 405 response for wrong HTTP method"""
        response = client.post("/")
        assert response.status_code == 405

if __name__ == "__main__":
    pytest.main([__file__]) 