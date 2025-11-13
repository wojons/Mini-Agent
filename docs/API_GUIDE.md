# Mini Agent HTTP API

The Mini Agent HTTP API provides a RESTful interface for interacting with the Mini Agent system through HTTP requests. It includes full OpenAPI documentation with automatic schema generation.

## Table of Contents

- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Request/Response Models](#requestresponse-models)
- [Example Usage](#example-usage)
- [OpenAPI Documentation](#openapi-documentation)

## Quick Start

### Starting the API Server

```bash
# Start the API server (default: http://127.0.0.1:8000)
mini-agent-api

# Start on a custom port
mini-agent-api --port 8080

# Start with auto-reload for development
mini-agent-api --reload

# Listen on all interfaces
mini-agent-api --host 0.0.0.0 --port 8000
```

### Accessing Documentation

Once the server is running, you can access:

- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc
- **OpenAPI Schema**: http://127.0.0.1:8000/openapi.json

## API Endpoints

### System Endpoints

#### `GET /`
**Root endpoint** - Returns basic API information

**Response:**
```json
{
  "name": "Mini Agent API",
  "version": "0.1.0",
  "docs": "/docs",
  "openapi": "/openapi.json"
}
```

#### `GET /api/v1/health`
**Health check** - Verify the API is running

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2025-11-13T06:11:24.793403"
}
```

### Tools Endpoints

#### `GET /api/v1/tools`
**List available tools** - Get all tools the agent can use

**Response:**
```json
{
  "tools": [
    {
      "name": "bash",
      "description": "Execute bash commands...",
      "parameters": {...}
    },
    {
      "name": "read_file",
      "description": "Read contents of a file...",
      "parameters": {...}
    }
  ],
  "count": 15
}
```

### Session Management Endpoints

#### `POST /api/v1/session/new`
**Create new session** - Start a new agent session

**Request Body:**
```json
{
  "workspace_dir": "/path/to/workspace",  // optional
  "system_prompt": "Custom prompt..."     // optional
}
```

**Response:**
```json
{
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "created_at": "2025-11-13T06:11:24.793403",
  "workspace_dir": "/tmp/mini-agent-workspace/...",
  "message_count": 1,
  "tool_count": 15
}
```

#### `GET /api/v1/session/{session_id}`
**Get session info** - Retrieve session details

**Response:**
```json
{
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "created_at": "2025-11-13T06:11:24.793403",
  "workspace_dir": "/tmp/mini-agent-workspace/...",
  "message_count": 3,
  "tool_count": 15
}
```

#### `DELETE /api/v1/session/{session_id}`
**Delete session** - Clean up a session

**Response:**
```json
{
  "message": "Session 123e4567-e89b-12d3-a456-426614174000 deleted successfully"
}
```

#### `GET /api/v1/sessions`
**List all sessions** - Get all active session IDs

**Response:**
```json
[
  "123e4567-e89b-12d3-a456-426614174000",
  "223e4567-e89b-12d3-a456-426614174001"
]
```

### Chat Endpoints

#### `POST /api/v1/chat`
**Send message** - Send a message to the agent and get a response

**Request Body:**
```json
{
  "message": "Create a file hello.txt with 'Hello World'",
  "session_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Response:**
```json
{
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "response": "I've created the file hello.txt with the content 'Hello World'",
  "step_count": 5,
  "completed": true,
  "messages": [
    {
      "role": "user",
      "content": "Create a file hello.txt with 'Hello World'",
      "timestamp": "2025-11-13T06:11:24.793403"
    },
    {
      "role": "assistant",
      "content": "I'll create the file...",
      "timestamp": "2025-11-13T06:11:25.123456"
    }
  ]
}
```

## Request/Response Models

### SessionCreateRequest
```typescript
{
  workspace_dir?: string  // Optional workspace directory path
  system_prompt?: string  // Optional custom system prompt
}
```

### SessionInfo
```typescript
{
  session_id: string      // Unique session identifier
  created_at: datetime    // Session creation timestamp
  workspace_dir: string   // Workspace directory path
  message_count: number   // Number of messages in session
  tool_count: number      // Number of available tools
}
```

### ChatRequest
```typescript
{
  message: string         // User message (required)
  session_id: string      // Session identifier (required)
}
```

### ChatResponse
```typescript
{
  session_id: string      // Session identifier
  response: string        // Agent response
  step_count: number      // Number of steps executed
  completed: boolean      // Whether task completed
  messages?: MessageContent[]  // Recent message history
}
```

### ErrorResponse
```typescript
{
  error: string          // Error message
  detail?: string        // Detailed error information
  timestamp: datetime    // Error timestamp
}
```

## Example Usage

### Python Example

```python
import requests

# API base URL
base_url = "http://127.0.0.1:8000"

# 1. Create a new session
response = requests.post(f"{base_url}/api/v1/session/new", json={})
session_data = response.json()
session_id = session_data["session_id"]
print(f"Created session: {session_id}")

# 2. Send a message
chat_response = requests.post(
    f"{base_url}/api/v1/chat",
    json={
        "message": "Create a file hello.txt with 'Hello World'",
        "session_id": session_id
    }
)
result = chat_response.json()
print(f"Agent response: {result['response']}")

# 3. Get session info
info_response = requests.get(f"{base_url}/api/v1/session/{session_id}")
print(f"Session info: {info_response.json()}")

# 4. Delete session
delete_response = requests.delete(f"{base_url}/api/v1/session/{session_id}")
print(f"Cleanup: {delete_response.json()}")
```

### cURL Examples

```bash
# Health check
curl http://127.0.0.1:8000/api/v1/health

# Create session
curl -X POST http://127.0.0.1:8000/api/v1/session/new \
  -H "Content-Type: application/json" \
  -d '{}'

# Send message (replace SESSION_ID)
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List files in current directory",
    "session_id": "SESSION_ID"
  }'

# Get session info
curl http://127.0.0.1:8000/api/v1/session/SESSION_ID

# Delete session
curl -X DELETE http://127.0.0.1:8000/api/v1/session/SESSION_ID

# List all tools
curl http://127.0.0.1:8000/api/v1/tools
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');

const baseUrl = 'http://127.0.0.1:8000';

async function main() {
  // Create session
  const sessionResponse = await axios.post(`${baseUrl}/api/v1/session/new`, {});
  const sessionId = sessionResponse.data.session_id;
  console.log(`Created session: ${sessionId}`);

  // Send message
  const chatResponse = await axios.post(`${baseUrl}/api/v1/chat`, {
    message: "Create a file hello.txt with 'Hello World'",
    session_id: sessionId
  });
  console.log(`Agent response: ${chatResponse.data.response}`);

  // Get session info
  const infoResponse = await axios.get(`${baseUrl}/api/v1/session/${sessionId}`);
  console.log('Session info:', infoResponse.data);

  // Delete session
  const deleteResponse = await axios.delete(`${baseUrl}/api/v1/session/${sessionId}`);
  console.log('Cleanup:', deleteResponse.data);
}

main().catch(console.error);
```

## OpenAPI Documentation

### Interactive Documentation

The API provides two interactive documentation interfaces:

1. **Swagger UI** (`/docs`): Full interactive API explorer
   - Try out API endpoints directly in the browser
   - View request/response examples
   - Test authentication and parameters

2. **ReDoc** (`/redoc`): Clean, searchable documentation
   - Three-column layout for easy navigation
   - Detailed schema descriptions
   - Download OpenAPI spec

### OpenAPI Specification

The complete OpenAPI 3.1 specification is available at `/openapi.json`. This can be used to:

- Generate client libraries in any language
- Import into API testing tools (Postman, Insomnia)
- Generate mock servers
- Validate requests/responses

**Key Features:**
- Full endpoint documentation with descriptions
- Request/response schema definitions
- Example values for all models
- Error response documentation
- Tag-based organization (System, Tools, Sessions, Chat)
- Contact and license information

### Generating Client Libraries

You can generate client libraries using tools like OpenAPI Generator:

```bash
# Generate Python client
openapi-generator-cli generate \
  -i http://127.0.0.1:8000/openapi.json \
  -g python \
  -o ./python-client

# Generate TypeScript client
openapi-generator-cli generate \
  -i http://127.0.0.1:8000/openapi.json \
  -g typescript-fetch \
  -o ./typescript-client
```

## Configuration

The API server uses the same configuration as the CLI tool. Ensure you have:

1. Configuration file at one of:
   - `mini_agent/config/config.yaml` (development)
   - `~/.mini-agent/config/config.yaml` (user)
   - `<package>/mini_agent/config/config.yaml` (installed)

2. Valid API key for MiniMax M2 model

See [README.md](../README.md) for configuration details.

## Error Handling

All errors return a consistent format:

```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "timestamp": "2025-11-13T06:11:24.793403"
}
```

**Common HTTP Status Codes:**
- `200`: Success
- `201`: Created (session)
- `400`: Bad Request
- `404`: Not Found (session not found)
- `422`: Validation Error (invalid request)
- `500`: Internal Server Error

## Security Considerations

⚠️ **Important**: The current API does not include authentication or authorization.

For production deployments:

1. Implement API key authentication
2. Add rate limiting
3. Use HTTPS/TLS
4. Restrict CORS origins
5. Add request validation
6. Implement logging and monitoring
7. Consider using a reverse proxy (nginx, traefik)

## CORS

The API includes CORS middleware configured to allow all origins (`*`). For production:

```python
# Restrict to specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Testing

Run the API tests:

```bash
pytest tests/test_api.py -v
```

The test suite includes:
- Basic API functionality tests
- OpenAPI documentation validation
- Endpoint structure tests
- Error handling tests
- Integration tests

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Use a different port
mini-agent-api --port 8080
```

### Configuration Not Found

```bash
# Run setup script
curl -fsSL https://raw.githubusercontent.com/MiniMax-AI/Mini-Agent/main/scripts/setup-config.sh | bash

# Or copy example config
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml
```

### Import Errors

```bash
# Reinstall package
pip install -e .

# Or install missing dependencies
pip install fastapi uvicorn
```

## License

This API is part of Mini Agent and is licensed under the MIT License. See [LICENSE](../LICENSE) for details.
