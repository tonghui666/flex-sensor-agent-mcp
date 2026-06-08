# Flexible Pressure Sensor Agent MCP

This repository is a local COMSOL MCP Server fork adapted for flexible pressure
sensor simulation. It exposes COMSOL Multiphysics workflows as MCP tools so an
AI agent can analyze a DXF microstructure, build a contact-compression model,
solve a parametric sweep, and export contact-response metrics.

## What This MCP Adds

The flexible pressure sensor workflow is implemented in:

- `src/tools/flexible_sensor.py`
- `src/server.py`
- `src/http_server.py`
- `src/tools/__init__.py`
- `src/tools/geometry.py`

New MCP tools:

| Tool | Purpose |
| --- | --- |
| `flex_sensor_analyze_dxf` | Parse common DXF `LINE`/`ARC` microstructure geometry and return bounds, entity counts, and a unit recommendation. |
| `flex_sensor_build_contact_model` | Build a 2D COMSOL contact-compression model from a DXF profile, including electrode, material, selections, contact pair, mesh, and stationary sweep. |
| `flex_sensor_export_contact_results` | Export contact length, thresholded contact length, pressure integral, and average pressure from a solved sweep. |

The generic `geometry_import` tool was also patched to use COMSOL's Java
geometry feature API for CAD import.

## Local COMSOL Setup

The development machine used:

- COMSOL Multiphysics 6.3 installed at `D:\COMSOL63`
- Python 3.10+
- MCP Python SDK
- MPh/JPype connection to COMSOL Java Client

Install Python dependencies:

```powershell
python -m pip install -e .
```

Start the MCP server:

```powershell
python -m src.server
```

If using the HTTP sidecar/proxy setup, start the configured HTTP MCP server and
point the stdio proxy to it according to your local Codex/Claude/OpenCode MCP
configuration.

## Typical Agent Workflow

1. Start COMSOL:

```python
comsol_start(version="6.3")
```

2. Analyze the sensor DXF:

```python
flex_sensor_analyze_dxf(
    dxf_path=r"C:\path\to\sensor_profile.dxf"
)
```

3. Build and optionally solve the contact model:

```python
flex_sensor_build_contact_model(
    dxf_path=r"C:\path\to\sensor_profile.dxf",
    model_name="flex_sensor_contact",
    para_list="range(0,0.01,1)",
    displacement_coefficient="10[um]",
    solve=True,
)
```

4. Export contact results:

```python
flex_sensor_export_contact_results(
    model_name="flex_sensor_contact",
    para_list="range(0,0.01,1)"
)
```

## Model Assumptions

- 2D flexible pressure sensor contact-compression model.
- DXF drawing units are normally treated as micrometers for microstructure
  profiles.
- Sensitive layer uses Solid Mechanics with a Neo-Hookean hyperelastic material
  through Lamé parameters.
- Upper electrode is modeled as structural steel with prescribed downward
  displacement.
- Contact pair source is the electrode bottom boundary; destination is the
  sensitive-layer top boundary.
- Contact postprocessing uses line integration on the contact destination
  boundary, because contact pressure is a boundary variable.

## GitHub Packaging Notes

The repository intentionally ignores:

- `.venv/`
- `comsol_models/`
- `knowledge_base/`
- `logs/`
- generated `.mph` files
- generated contact CSV/SVG outputs

These files can be very large or machine-specific and should not be committed
unless you explicitly want to publish examples.

