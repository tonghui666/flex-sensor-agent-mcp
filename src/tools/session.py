"""Session management tools for COMSOL MCP Server."""

from typing import Optional
from mcp.server import Server
from mcp.server.fastmcp import FastMCP
import mph
from mph.client import Client as MphClient
from mph.server import Server as MphServer
import mph.session as mph_session


class SessionManager:
    """Singleton manager for COMSOL client session."""
    
    _instance: Optional["SessionManager"] = None
    _client: Optional[mph.Client] = None
    _models: dict[str, mph.Model] = {}
    _current_model: Optional[str] = None
    _local_session: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def client(self) -> Optional[mph.Client]:
        return self._client
    
    @property
    def is_connected(self) -> bool:
        return self._client is not None
    
    @property
    def current_model(self) -> Optional[str]:
        return self._current_model
    
    @property
    def models(self) -> dict[str, mph.Model]:
        return self._models.copy()

    def _redirect_java_standard_streams(self) -> None:
        """Keep COMSOL's JVM from touching the MCP stdio transport."""
        try:
            import jpype

            if not jpype.isJVMStarted():
                return
            system = jpype.JClass("java.lang.System")
            byte_array_input_stream = jpype.JClass("java.io.ByteArrayInputStream")
            output_stream = jpype.JClass("java.io.OutputStream")
            print_stream = jpype.JClass("java.io.PrintStream")
            empty_bytes = jpype.JArray(jpype.JByte)([])
            system.setIn(byte_array_input_stream(empty_bytes))
            null_output = output_stream.nullOutputStream()
            system.setOut(print_stream(null_output))
            system.setErr(print_stream(output_stream.nullOutputStream()))
        except Exception:
            pass
    
    def start(self, cores: Optional[int] = None, version: Optional[str] = None) -> dict:
        """Start a COMSOL client session."""
        if self._client is not None:
            try:
                self._client.clear()
                self._models.clear()
                self._current_model = None
                return {
                    "success": True,
                    "version": self._client.version,
                    "cores": self._client.cores,
                    "standalone": self._client.standalone,
                    "message": "Cleared existing session and ready."
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to clear existing session: {e}"}
        try:
            mph_session.server = MphServer(cores=cores, version=version, port=0)
            self._client = MphClient(cores=cores, version=version, host="")
            self._client.standalone = False
            self._redirect_java_standard_streams()
            self._client.connect(mph_session.server.port, "127.0.0.1")
            mph_session.client = self._client
            self._local_session = True
            return {
                "success": True,
                "version": self._client.version,
                "cores": self._client.cores,
                "standalone": self._client.standalone,
                "port": self._client.port,
                "host": self._client.host,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def connect(self, port: int, host: str = "localhost") -> dict:
        """Connect to a remote COMSOL server."""
        if self._client is not None:
            return {
                "success": False,
                "error": "COMSOL session already running. Disconnect first."
            }
        try:
            self._client = MphClient(host="")
            self._client.standalone = False
            self._redirect_java_standard_streams()
            self._client.connect(port=port, host=host)
            self._local_session = False
            return {
                "success": True,
                "version": self._client.version,
                "port": port,
                "host": host,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def disconnect(self) -> dict:
        """Disconnect and clear the session."""
        if self._client is None:
            return {"success": True, "message": "No active session."}
        try:
            self._client.clear()
            if self._client.port:
                self._client.disconnect()
            if self._local_session and mph_session.server is not None:
                mph_session.server.stop()
                mph_session.server = None
            mph_session.client = None
            mph_session.thread = None
            self._client = None
            self._models.clear()
            self._current_model = None
            self._local_session = False
            return {"success": True, "message": "Session disconnected and models cleared."}
        except Exception as e:
            self._models.clear()
            self._current_model = None
            self._client = None
            self._local_session = False
            mph_session.client = None
            mph_session.thread = None
            return {"success": True, "message": f"Session cleared (error during disconnect: {e})"}
    
    def get_status(self) -> dict:
        """Get current session status."""
        if self._client is None:
            return {
                "connected": False,
                "message": "No active COMSOL session."
            }
        
        model_list = []
        for name in self._client.names():
            model_info = {"name": name}
            if name in self._models:
                model = self._models[name]
                model_info["file"] = model.file() if hasattr(model, 'file') else None
            model_list.append(model_info)
        
        return {
            "connected": True,
            "version": self._client.version,
            "cores": self._client.cores,
            "standalone": self._client.standalone,
            "models": model_list,
            "current_model": self._current_model,
        }
    
    def add_model(self, model: mph.Model) -> str:
        """Add a model to tracking."""
        name = model.name()
        self._models[name] = model
        if self._current_model is None:
            self._current_model = name
        return name
    
    def get_model(self, name: Optional[str] = None) -> Optional[mph.Model]:
        """Get a model by name or current model."""
        if name is None:
            name = self._current_model
        return self._models.get(name)
    
    def set_current_model(self, name: str) -> bool:
        """Set the current active model."""
        if name in self._models:
            self._current_model = name
            return True
        return False
    
    def remove_model(self, name: str) -> bool:
        """Remove a model from tracking and client."""
        if name in self._models and self._client is not None:
            try:
                self._client.remove(self._models[name])
                del self._models[name]
                if self._current_model == name:
                    self._current_model = next(iter(self._models.keys()), None)
                return True
            except Exception:
                pass
        return False


session_manager = SessionManager()


def register_session_tools(mcp: FastMCP) -> None:
    """Register session management tools with the MCP server."""
    
    @mcp.tool()
    async def comsol_start(cores: Optional[int] = None, version: Optional[str] = None) -> dict:
        """
        Start a local COMSOL client session.
        
        Args:
            cores: Number of processor cores to use (default: all available)
            version: COMSOL version to use, e.g., '6.0' (default: latest installed)
        
        Returns:
            Session info including version and core count, or error message
        """
        return session_manager.start(cores=cores, version=version)
    
    @mcp.tool()
    async def comsol_connect(port: int, host: str = "localhost") -> dict:
        """
        Connect to a remote COMSOL server.
        
        Args:
            port: Port number the COMSOL server is listening on
            host: Server hostname or IP address (default: 'localhost')
        
        Returns:
            Connection info or error message
        """
        return session_manager.connect(port=port, host=host)
    
    @mcp.tool()
    async def comsol_disconnect() -> dict:
        """
        Disconnect from COMSOL and clear all models from memory.
        
        Returns:
            Success status and message
        """
        return session_manager.disconnect()
    
    @mcp.tool()
    async def comsol_status() -> dict:
        """
        Get the current COMSOL session status.
        
        Returns:
            Session information including connection status, version, and loaded models
        """
        return session_manager.get_status()
