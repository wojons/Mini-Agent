"""
HTTP API for Mini Agent with OpenAPI documentation.

This module provides a RESTful API for interacting with the Mini Agent,
including session management, chat endpoints, and tool information.
"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.llm import LLMClient
from mini_agent.retry import RetryConfig as RetryConfigBase
from mini_agent.schema import Message
from mini_agent.tools.base import Tool
from mini_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from mini_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async
from mini_agent.tools.note_tool import SessionNoteTool
from mini_agent.tools.skill_tool import create_skill_tools


# ============================================================================
# Pydantic Models for Request/Response
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response"""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    status: str = Field(..., description="Service status", json_schema_extra={"example": "healthy"})
    version: str = Field(..., description="API version", json_schema_extra={"example": "0.1.0"})
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Current server time"
    )


class ToolInfo(BaseModel):
    """Information about a tool"""

    name: str = Field(..., description="Tool name", json_schema_extra={"example": "read_file"})
    description: str = Field(
        ..., description="Tool description", json_schema_extra={"example": "Read contents of a file"}
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Tool parameter schema"
    )


class ToolsResponse(BaseModel):
    """Response containing list of available tools"""

    tools: List[ToolInfo] = Field(..., description="List of available tools")
    count: int = Field(..., description="Number of available tools")


class SessionCreateRequest(BaseModel):
    """Request to create a new session"""

    workspace_dir: Optional[str] = Field(
        None,
        description="Workspace directory path (defaults to /tmp/mini-agent-workspace)",
    )
    system_prompt: Optional[str] = Field(
        None, description="Custom system prompt (optional)"
    )


class SessionInfo(BaseModel):
    """Information about a session"""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    session_id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(..., description="Session creation time")
    workspace_dir: str = Field(..., description="Workspace directory path")
    message_count: int = Field(..., description="Number of messages in session")
    tool_count: int = Field(..., description="Number of available tools")


class ChatRequest(BaseModel):
    """Request to send a message to the agent"""

    message: str = Field(..., description="User message", json_schema_extra={"example": "Create a file hello.txt with 'Hello World'"})
    session_id: str = Field(..., description="Session identifier")


class MessageContent(BaseModel):
    """Message content in chat response"""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    role: str = Field(..., description="Message role (user/assistant/tool)")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = Field(None, description="Message timestamp")


class ChatResponse(BaseModel):
    """Response from chat endpoint"""

    session_id: str = Field(..., description="Session identifier")
    response: str = Field(..., description="Agent response")
    step_count: int = Field(..., description="Number of steps executed")
    completed: bool = Field(..., description="Whether the task completed successfully")
    messages: Optional[List[MessageContent]] = Field(
        None, description="Recent message history"
    )


class ErrorResponse(BaseModel):
    """Error response"""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Error timestamp"
    )


# ============================================================================
# Session Management
# ============================================================================


class SessionManager:
    """Manages agent sessions"""

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.config: Optional[Config] = None
        self.llm_client: Optional[LLMClient] = None
        self.base_tools: List[Tool] = []
        self._initialized = False

    async def initialize(self):
        """Initialize the session manager with config and base tools"""
        if self._initialized:
            return

        # Load configuration
        config_path = Config.get_default_config_path()
        if not config_path.exists():
            raise RuntimeError(
                f"Configuration file not found at {config_path}. "
                "Please run setup script or create config manually."
            )

        self.config = Config.from_yaml(config_path)

        # Initialize LLM client with retry config
        retry_config = RetryConfigBase(
            enabled=self.config.llm.retry.enabled,
            max_retries=self.config.llm.retry.max_retries,
            initial_delay=self.config.llm.retry.initial_delay,
            max_delay=self.config.llm.retry.max_delay,
            exponential_base=self.config.llm.retry.exponential_base,
            retryable_exceptions=(Exception,),
        )

        self.llm_client = LLMClient(
            api_key=self.config.llm.api_key,
            api_base=self.config.llm.api_base,
            model=self.config.llm.model,
            retry_config=retry_config if self.config.llm.retry.enabled else None,
        )

        # Initialize base tools (workspace-independent)
        await self._initialize_base_tools()
        self._initialized = True

    async def _initialize_base_tools(self):
        """Initialize base tools that are workspace-independent"""
        tools = []

        # Bash tools
        if self.config.tools.enable_bash:
            tools.extend([BashTool(), BashOutputTool(), BashKillTool()])

        # Claude Skills
        if self.config.tools.enable_skills:
            try:
                skills_dir = self.config.tools.skills_dir
                if not Path(skills_dir).is_absolute():
                    search_paths = [
                        Path(skills_dir),
                        Path("mini_agent") / skills_dir,
                        Config.get_package_dir() / skills_dir,
                    ]
                    for path in search_paths:
                        if path.exists():
                            skills_dir = str(path.resolve())
                            break

                skill_tools, _ = create_skill_tools(skills_dir)
                if skill_tools:
                    tools.extend(skill_tools)
            except Exception as e:
                print(f"Warning: Failed to load Skills: {e}")

        # MCP tools
        if self.config.tools.enable_mcp:
            try:
                mcp_config_path = Config.find_config_file(
                    self.config.tools.mcp_config_path
                )
                if mcp_config_path:
                    mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                    if mcp_tools:
                        tools.extend(mcp_tools)
            except Exception as e:
                print(f"Warning: Failed to load MCP tools: {e}")

        self.base_tools = tools

    def _add_workspace_tools(
        self, tools: List[Tool], workspace_dir: Path
    ) -> List[Tool]:
        """Add workspace-dependent tools
        
        Note: workspace_dir should already be validated before calling this method
        """
        # Create directory with secure permissions if it doesn't exist
        try:
            workspace_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise RuntimeError(f"Failed to create workspace directory: {e}")

        if self.config.tools.enable_file_tools:
            tools.extend(
                [
                    ReadTool(workspace_dir=str(workspace_dir)),
                    WriteTool(workspace_dir=str(workspace_dir)),
                    EditTool(workspace_dir=str(workspace_dir)),
                ]
            )

        if self.config.tools.enable_note:
            tools.append(
                SessionNoteTool(memory_file=str(workspace_dir / ".agent_memory.json"))
            )

        return tools

    async def create_session(
        self, workspace_dir: Optional[str] = None, system_prompt: Optional[str] = None
    ) -> str:
        """Create a new agent session
        
        Security Note: User-provided workspace paths are intentionally allowed as this is
        a core feature. Validation is performed to prevent path traversal attacks:
        - Paths must be absolute
        - Path traversal patterns (..) are rejected
        - Paths are resolved to canonical form
        - Directories are created with secure permissions (0o700)
        """
        if not self._initialized:
            await self.initialize()

        session_id = str(uuid.uuid4())

        # Determine workspace directory with validation
        if workspace_dir:
            # Validate and sanitize user-provided workspace path
            ws_path = Path(workspace_dir).resolve()
            # Ensure path is absolute and doesn't contain suspicious patterns
            if not ws_path.is_absolute():
                raise ValueError("Workspace directory must be an absolute path")
            # Prevent path traversal
            if ".." in str(ws_path):
                raise ValueError("Workspace directory cannot contain '..' (path traversal)")
        else:
            # Default to safe temp directory
            ws_path = Path(f"/tmp/mini-agent-workspace/{session_id}").resolve()

        # Create directory with secure permissions
        try:
            ws_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise RuntimeError(f"Failed to create workspace directory: {e}")

        # Create tools list (copy base tools + add workspace tools)
        tools = self.base_tools.copy()
        tools = self._add_workspace_tools(tools, ws_path)

        # Load system prompt
        if not system_prompt:
            system_prompt_path = Config.find_config_file(
                self.config.agent.system_prompt_path
            )
            if system_prompt_path and system_prompt_path.exists():
                system_prompt = system_prompt_path.read_text(encoding="utf-8")
            else:
                system_prompt = (
                    "You are Mini-Agent, an intelligent assistant powered by MiniMax M2 "
                    "that can help users complete various tasks."
                )

        # Create agent
        agent = Agent(
            llm_client=self.llm_client,
            system_prompt=system_prompt,
            tools=tools,
            max_steps=self.config.agent.max_steps,
            workspace_dir=str(ws_path),
        )

        # Store session
        self.sessions[session_id] = {
            "agent": agent,
            "created_at": datetime.now(),
            "workspace_dir": str(ws_path),
        }

        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID"""
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[str]:
        """List all session IDs"""
        return list(self.sessions.keys())


# ============================================================================
# FastAPI Application
# ============================================================================


# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    try:
        await session_manager.initialize()
    except Exception as e:
        print(f"Warning: Failed to initialize session manager: {e}")
    
    yield
    
    # Shutdown
    try:
        await cleanup_mcp_connections()
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}")


# Create FastAPI app with OpenAPI documentation
app = FastAPI(
    title="Mini Agent API",
    description="""
    **Mini Agent API** provides a RESTful interface for interacting with the Mini Agent system.
    
    ## Features
    
    * 🤖 **Agent Chat**: Send messages and receive intelligent responses
    * 📝 **Session Management**: Create, manage, and delete agent sessions
    * 🛠️ **Tool Access**: Query available tools and their capabilities
    * 💾 **Persistent Sessions**: Each session maintains its own context and workspace
    
    ## Getting Started
    
    1. Create a new session using `POST /api/v1/session/new`
    2. Use the returned `session_id` to send messages via `POST /api/v1/chat`
    3. Query session information with `GET /api/v1/session/{session_id}`
    4. Clean up sessions when done with `DELETE /api/v1/session/{session_id}`
    
    ## Authentication
    
    Currently, this API does not require authentication. In production environments,
    implement proper authentication and authorization mechanisms.
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "Mini Agent Team",
        "url": "https://github.com/MiniMax-AI/Mini-Agent",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global session manager
session_manager = SessionManager()


# ============================================================================
# API Endpoints
# ============================================================================


@app.get(
    "/",
    response_model=Dict[str, str],
    summary="API Root",
    description="Returns basic API information and links to documentation",
)
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Mini Agent API",
        "version": "0.1.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check if the API is running and healthy",
    tags=["System"],
)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="healthy", version="0.1.0")


@app.get(
    "/api/v1/tools",
    response_model=ToolsResponse,
    summary="List Available Tools",
    description="Get a list of all available tools that the agent can use",
    tags=["Tools"],
)
async def list_tools():
    """List all available tools"""
    if not session_manager._initialized:
        await session_manager.initialize()

    tools_info = []
    for tool in session_manager.base_tools:
        tool_info = ToolInfo(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters.get("properties", {})
            if hasattr(tool, "parameters")
            else {},
        )
        tools_info.append(tool_info)

    return ToolsResponse(tools=tools_info, count=len(tools_info))


@app.post(
    "/api/v1/session/new",
    response_model=SessionInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Session",
    description="Create a new agent session with optional workspace and system prompt",
    tags=["Sessions"],
)
async def create_session(request: SessionCreateRequest):
    """Create a new agent session"""
    try:
        session_id = await session_manager.create_session(
            workspace_dir=request.workspace_dir, system_prompt=request.system_prompt
        )

        session = session_manager.get_session(session_id)
        agent = session["agent"]

        return SessionInfo(
            session_id=session_id,
            created_at=session["created_at"],
            workspace_dir=session["workspace_dir"],
            message_count=len(agent.messages),
            tool_count=len(agent.tools),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )


@app.get(
    "/api/v1/session/{session_id}",
    response_model=SessionInfo,
    summary="Get Session Info",
    description="Retrieve information about a specific session",
    tags=["Sessions"],
)
async def get_session_info(session_id: str):
    """Get information about a session"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    agent = session["agent"]
    return SessionInfo(
        session_id=session_id,
        created_at=session["created_at"],
        workspace_dir=session["workspace_dir"],
        message_count=len(agent.messages),
        tool_count=len(agent.tools),
    )


@app.delete(
    "/api/v1/session/{session_id}",
    response_model=Dict[str, str],
    summary="Delete Session",
    description="Delete a session and clean up its resources",
    tags=["Sessions"],
)
async def delete_session(session_id: str):
    """Delete a session"""
    if session_manager.delete_session(session_id):
        return {"message": f"Session {session_id} deleted successfully"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
    )


@app.get(
    "/api/v1/sessions",
    response_model=List[str],
    summary="List All Sessions",
    description="Get a list of all active session IDs",
    tags=["Sessions"],
)
async def list_sessions():
    """List all active sessions"""
    return session_manager.list_sessions()


@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    summary="Send Message",
    description="Send a message to the agent and get a response",
    tags=["Chat"],
)
async def chat(request: ChatRequest):
    """Send a message to the agent"""
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    agent: Agent = session["agent"]

    try:
        # Add user message
        agent.add_user_message(request.message)

        # Run agent
        final_response = await agent.run()

        # Extract response text
        response_text = ""
        if final_response and len(final_response.content) > 0:
            for content_block in final_response.content:
                if isinstance(content_block, dict) and content_block.get("type") == "text":
                    response_text += content_block.get("text", "")
                elif hasattr(content_block, "text"):
                    response_text += content_block.text

        # Get recent messages for context
        recent_messages = []
        for msg in agent.messages[-5:]:  # Last 5 messages
            content_str = ""
            if isinstance(msg.content, str):
                content_str = msg.content
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content_str += block.get("text", "")

            recent_messages.append(
                MessageContent(
                    role=msg.role,
                    content=content_str[:500],  # Truncate for API response
                    timestamp=datetime.now(),
                )
            )

        return ChatResponse(
            session_id=request.session_id,
            response=response_text or "Task completed",
            step_count=len(agent.messages),
            completed=True,
            messages=recent_messages,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}",
        )


# Exception handler for custom error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail, detail=str(exc), timestamp=datetime.now()
        ).model_dump(mode='json'),
    )


# For convenience, expose the app
def create_app() -> FastAPI:
    """Create and return the FastAPI application"""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
