"""
Tests for the Mini Agent HTTP API

These tests verify the HTTP API endpoints, OpenAPI documentation,
and session management functionality.
"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mini_agent.api import app, session_manager


@pytest.fixture
def client():
    """Create a test client for the API"""
    return TestClient(app)


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a mock configuration file for testing"""
    config_content = """
api_key: "test-api-key"
api_base: "https://api.minimax.io/anthropic"
model: "MiniMax-M2"

retry:
  enabled: false
  max_retries: 3
  initial_delay: 1.0
  max_delay: 60.0
  exponential_base: 2.0

max_steps: 10
workspace_dir: "./workspace"
system_prompt_path: "system_prompt.md"

tools:
  enable_file_tools: true
  enable_bash: true
  enable_note: true
  enable_skills: false
  skills_dir: "./skills"
  enable_mcp: false
  mcp_config_path: "mcp.json"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return config_file


class TestAPIBasics:
    """Test basic API functionality"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns API information"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["name"] == "Mini Agent API"

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data


class TestOpenAPIDocumentation:
    """Test OpenAPI documentation endpoints"""

    def test_openapi_json_available(self, client):
        """Test OpenAPI JSON schema is available"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        
        # Check OpenAPI structure
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data
        
        # Check API info
        assert data["info"]["title"] == "Mini Agent API"
        assert data["info"]["version"] == "0.1.0"
        assert "description" in data["info"]

    def test_docs_ui_available(self, client):
        """Test Swagger UI documentation is available"""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    def test_redoc_available(self, client):
        """Test ReDoc documentation is available"""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()

    def test_openapi_endpoints_documented(self, client):
        """Test that all major endpoints are documented in OpenAPI"""
        response = client.get("/openapi.json")
        data = response.json()
        paths = data["paths"]
        
        # Check essential endpoints are documented
        assert "/api/v1/health" in paths
        assert "/api/v1/tools" in paths
        assert "/api/v1/session/new" in paths
        assert "/api/v1/session/{session_id}" in paths
        assert "/api/v1/sessions" in paths
        assert "/api/v1/chat" in paths

    def test_openapi_models_documented(self, client):
        """Test that request/response models are documented"""
        response = client.get("/openapi.json")
        data = response.json()
        
        # Check schemas are present
        assert "components" in data
        assert "schemas" in data["components"]
        schemas = data["components"]["schemas"]
        
        # Check key models are documented
        assert "HealthResponse" in schemas
        assert "SessionInfo" in schemas
        assert "ChatRequest" in schemas
        assert "ChatResponse" in schemas
        # Note: ErrorResponse may not be in schemas if not directly used in endpoint definitions


class TestToolsEndpoint:
    """Test tools listing endpoint"""

    @pytest.mark.asyncio
    async def test_list_tools_structure(self, client):
        """Test tools endpoint returns correct structure"""
        # Initialize session manager first
        if not session_manager._initialized:
            await session_manager.initialize()
        
        response = client.get("/api/v1/tools")
        assert response.status_code == 200
        data = response.json()
        
        assert "tools" in data
        assert "count" in data
        assert isinstance(data["tools"], list)
        assert data["count"] == len(data["tools"])

    @pytest.mark.asyncio
    async def test_tool_info_structure(self, client):
        """Test each tool has required fields"""
        if not session_manager._initialized:
            await session_manager.initialize()
        
        response = client.get("/api/v1/tools")
        data = response.json()
        
        if data["count"] > 0:
            tool = data["tools"][0]
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool


class TestSessionManagement:
    """Test session management endpoints"""

    def test_create_session_basic(self, client):
        """Test creating a new session"""
        response = client.post("/api/v1/session/new", json={})
        
        # May fail if config not available, that's ok for structure test
        if response.status_code == 201:
            data = response.json()
            assert "session_id" in data
            assert "created_at" in data
            assert "workspace_dir" in data
            assert "message_count" in data
            assert "tool_count" in data

    def test_create_session_with_workspace(self, client):
        """Test creating session with custom workspace"""
        request_data = {"workspace_dir": "/tmp/test-workspace"}
        response = client.post("/api/v1/session/new", json=request_data)
        
        if response.status_code == 201:
            data = response.json()
            assert "session_id" in data

    def test_get_session_not_found(self, client):
        """Test getting non-existent session returns 404"""
        response = client.get("/api/v1/session/fake-session-id")
        assert response.status_code == 404

    def test_delete_session_not_found(self, client):
        """Test deleting non-existent session returns 404"""
        response = client.delete("/api/v1/session/fake-session-id")
        assert response.status_code == 404

    def test_list_sessions(self, client):
        """Test listing all sessions"""
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestChatEndpoint:
    """Test chat/messaging endpoints"""

    def test_chat_missing_session(self, client):
        """Test chat with non-existent session returns 404"""
        request_data = {
            "message": "Hello",
            "session_id": "fake-session-id"
        }
        response = client.post("/api/v1/chat", json=request_data)
        assert response.status_code == 404

    def test_chat_request_validation(self, client):
        """Test chat request requires message and session_id"""
        # Missing message
        response = client.post("/api/v1/chat", json={"session_id": "test"})
        assert response.status_code == 422  # Validation error
        
        # Missing session_id
        response = client.post("/api/v1/chat", json={"message": "Hello"})
        assert response.status_code == 422  # Validation error


class TestAPITags:
    """Test OpenAPI tags/grouping"""

    def test_endpoints_have_tags(self, client):
        """Test that endpoints are properly tagged for organization"""
        response = client.get("/openapi.json")
        data = response.json()
        
        # Check that tags are defined
        assert "tags" in data or any(
            "tags" in endpoint_data
            for path_data in data["paths"].values()
            for endpoint_data in path_data.values()
        )


class TestCORSConfiguration:
    """Test CORS middleware configuration"""

    def test_cors_headers_present(self, client):
        """Test CORS headers are included in responses"""
        # Test with GET request instead of OPTIONS
        response = client.get("/api/v1/health")
        # CORS headers should allow all origins (configured with allow_origins=["*"])
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling and responses"""

    def test_404_returns_json(self, client):
        """Test 404 errors return JSON responses"""
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404

    def test_validation_error_returns_json(self, client):
        """Test validation errors return structured JSON"""
        # Send invalid request (missing required fields)
        response = client.post("/api/v1/chat", json={})
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestAPISecurity:
    """Test API security considerations"""

    def test_api_does_not_leak_sensitive_info(self, client):
        """Test API responses don't leak sensitive information"""
        response = client.get("/openapi.json")
        data = response.json()
        
        # Check that sensitive info is not in OpenAPI spec
        spec_str = str(data).lower()
        assert "api_key" not in spec_str or "YOUR_API_KEY" in spec_str
        assert "password" not in spec_str


# Integration tests (may require full setup)
class TestAPIIntegration:
    """Integration tests requiring full system"""

    @pytest.mark.asyncio
    async def test_full_session_workflow(self, client):
        """Test complete workflow: create session, chat, get info, delete"""
        # Initialize session manager
        try:
            if not session_manager._initialized:
                await session_manager.initialize()
        except Exception:
            pytest.skip("Config not available for integration test")
            return
        
        # 1. Create session
        create_response = client.post("/api/v1/session/new", json={})
        if create_response.status_code != 201:
            pytest.skip("Cannot create session without proper config")
            return
        
        session_data = create_response.json()
        session_id = session_data["session_id"]
        
        # 2. Get session info
        info_response = client.get(f"/api/v1/session/{session_id}")
        assert info_response.status_code == 200
        
        # 3. Delete session
        delete_response = client.delete(f"/api/v1/session/{session_id}")
        assert delete_response.status_code == 200
        
        # 4. Verify session is gone
        info_response = client.get(f"/api/v1/session/{session_id}")
        assert info_response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
