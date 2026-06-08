"""HTTP transport entry point for the COMSOL MCP server."""

import os

from mcp.server.fastmcp import FastMCP

from .tools.session import register_session_tools
from .tools.model import register_model_tools
from .tools.parameters import register_parameter_tools
from .tools.geometry import register_geometry_tools
from .tools.physics import register_physics_tools
from .tools.mesh import register_mesh_tools
from .tools.study import register_study_tools
from .tools.results import register_results_tools
from .tools.flexible_sensor import register_flexible_sensor_tools
from .resources.model_resources import register_model_resources
from .knowledge.embedded import register_knowledge_tools


def build_server() -> FastMCP:
    """Build a COMSOL MCP server bound to localhost HTTP."""
    host = os.environ.get("COMSOL_MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("COMSOL_MCP_HTTP_PORT", "8765"))
    mcp = FastMCP("COMSOL MCP", host=host, port=port)

    register_session_tools(mcp)
    register_model_tools(mcp)
    register_parameter_tools(mcp)
    register_geometry_tools(mcp)
    register_physics_tools(mcp)
    register_mesh_tools(mcp)
    register_study_tools(mcp)
    register_results_tools(mcp)
    register_flexible_sensor_tools(mcp)
    register_knowledge_tools(mcp)
    register_model_resources(mcp)

    return mcp


def main() -> None:
    """Run the COMSOL MCP server over streamable HTTP."""
    build_server().run("streamable-http")


if __name__ == "__main__":
    main()
