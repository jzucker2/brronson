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
        
        # Check required fields
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data
        
        # Check service name
        assert data["service"] == "bronson-api"
        
        # Check status is healthy
        assert data["status"] == "healthy"
        
        # Check version
        assert data["version"] == "1.0.0"
        
        # Check timestamp is a number
        assert isinstance(data["timestamp"], (int, float))
    
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
    
    def test_metrics_contain_requests_total(self):
        """Test that metrics contain requests_total counter"""
        # Make a request to generate metrics
        client.get("/health")
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for requests_total metric (from prometheus-fastapi-instrumentator)
        assert "requests_total" in metrics_text
    
    def test_metrics_contain_request_duration(self):
        """Test that metrics contain request duration histogram"""
        # Make a request to generate metrics
        client.get("/health")
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for request duration metric (from prometheus-fastapi-instrumentator)
        assert "request_duration" in metrics_text
    
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
    
    def test_metrics_contain_request_size(self):
        """Test that metrics contain request size metrics"""
        # Make a POST request to generate request size metrics
        client.post("/api/v1/items", json={"name": "test", "description": "test item"})
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for request size metric
        assert "request_size" in metrics_text
    
    def test_metrics_contain_response_size(self):
        """Test that metrics contain response size metrics"""
        # Make a request to generate response size metrics
        client.get("/api/v1/items")
        
        response = client.get("/metrics")
        metrics_text = response.text
        
        # Check for response size metric
        assert "response_size" in metrics_text

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

class TestHealthCheck:
    """Test cases specifically for health check functionality"""
    
    def test_health_check_response_time(self):
        """Test that health check responds within reasonable time"""
        import time
        start_time = time.time()
        response = client.get("/health")
        end_time = time.time()
        
        assert response.status_code == 200
        # Health check should respond within 5 seconds
        assert (end_time - start_time) < 5
    
    def test_health_check_consistency(self):
        """Test that health check returns consistent data structure"""
        response1 = client.get("/health")
        response2 = client.get("/health")
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Check that both responses have the same structure
        assert set(data1.keys()) == set(data2.keys())
        
        # Check that timestamps are different (indicating fresh data)
        assert data1["timestamp"] != data2["timestamp"]
        
        # Check that version and service name are consistent
        assert data1["version"] == data2["version"]
        assert data1["service"] == data2["service"]
    
    def test_health_check_headers(self):
        """Test that health check returns appropriate headers"""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert "content-type" in response.headers
        assert response.headers["content-type"] == "application/json"
    
    def test_health_check_with_different_methods(self):
        """Test health check with different HTTP methods"""
        # GET should work
        response = client.get("/health")
        assert response.status_code == 200
        
        # POST should not work (method not allowed)
        response = client.post("/health")
        assert response.status_code == 405
        
        # PUT should not work (method not allowed)
        response = client.put("/health")
        assert response.status_code == 405

if __name__ == "__main__":
    pytest.main([__file__]) 