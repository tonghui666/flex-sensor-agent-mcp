"""Flexible pressure sensor workflow tools for COMSOL MCP Server."""

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path
from typing import Optional

import jpype
from mcp.server.fastmcp import FastMCP

from .session import session_manager
from ..utils.versioning import generate_latest_path, generate_version_path


JInt = jpype.JInt


def _parse_dxf_entities(path: str | Path) -> tuple[list[tuple[str, dict[str, list[str]]]], dict]:
    """Parse the small subset of DXF entities needed for sensor profiles."""
    path = Path(path)
    lines = path.read_text(errors="ignore").splitlines()
    pairs = list(zip([s.strip() for s in lines[0::2]], [s.strip() for s in lines[1::2]]))

    entities: list[tuple[str, dict[str, list[str]]]] = []
    i = 0
    while i < len(pairs):
        code, value = pairs[i]
        if code == "0" and value in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE"}:
            kind = value
            data: dict[str, list[str]] = {}
            i += 1
            while i < len(pairs) and pairs[i][0] != "0":
                data.setdefault(pairs[i][0], []).append(pairs[i][1])
                i += 1
            entities.append((kind, data))
            continue
        i += 1

    xs: list[float] = []
    ys: list[float] = []
    for kind, data in entities:
        if kind == "LINE":
            for code in ("10", "11"):
                xs.extend(float(v) for v in data.get(code, []))
            for code in ("20", "21"):
                ys.extend(float(v) for v in data.get(code, []))
        elif kind == "ARC":
            cx = float(data["10"][0])
            cy = float(data["20"][0])
            radius = float(data["40"][0])
            start = math.radians(float(data["50"][0]))
            end = math.radians(float(data["51"][0]))
            if end < start:
                end += 2 * math.pi
            angles = [start, end]
            for cardinal in (0, math.pi / 2, math.pi, 3 * math.pi / 2, 2 * math.pi):
                test = cardinal
                if test < start:
                    test += 2 * math.pi
                if start <= test <= end:
                    angles.append(test)
            xs.extend(cx + radius * math.cos(a) for a in angles)
            ys.extend(cy + radius * math.sin(a) for a in angles)

    if not xs or not ys:
        raise ValueError(f"No supported LINE/ARC geometry found in {path}")

    bounds = {
        "xmin": min(xs),
        "xmax": max(xs),
        "ymin": min(ys),
        "ymax": max(ys),
    }
    bounds["width"] = bounds["xmax"] - bounds["xmin"]
    bounds["height"] = bounds["ymax"] - bounds["ymin"]
    return entities, bounds


def _create_box_selection(comp, tag: str, entitydim: int, xmin: str, xmax: str, ymin: str, ymax: str, condition: str) -> None:
    sel = comp.selection().create(tag, "Box")
    try:
        sel.geom("geom1", JInt(entitydim))
    except Exception:
        sel.geom(JInt(entitydim))
    sel.set("entitydim", JInt(entitydim))
    sel.set("condition", condition)
    sel.set("xmin", xmin)
    sel.set("xmax", xmax)
    sel.set("ymin", ymin)
    sel.set("ymax", ymax)
    sel.set("groupcontang", True)


def _try_set(feature, name: str, value) -> None:
    try:
        feature.set(name, value)
    except Exception:
        pass


def _parse_parameter_values(plist: str) -> list[float]:
    values: list[float] = []
    for token in plist.split():
        if token.startswith("range(") and token.endswith(")"):
            start, step, stop = [float(part.strip()) for part in token[6:-1].split(",")]
            value = start
            if step == 0:
                raise ValueError("range step cannot be zero")
            if step > 0:
                while value <= stop + abs(step) * 1e-9:
                    values.append(round(value, 12))
                    value += step
            else:
                while value >= stop - abs(step) * 1e-9:
                    values.append(round(value, 12))
                    value += step
        else:
            values.append(float(token))
    return values


def _line_integral(jm, expr: str, selection: str) -> list[float]:
    tag = "flex_sensor_int_auto"
    try:
        jm.result().numerical().remove(tag)
    except Exception:
        pass
    num = jm.result().numerical().create(tag, "IntLine")
    num.set("data", "dset1")
    num.selection().named(selection)
    num.set("expr", [expr])
    real = num.getReal()
    return [float(value) for value in real[0]]


def register_flexible_sensor_tools(mcp: FastMCP) -> None:
    """Register flexible pressure sensor workflow tools."""

    @mcp.tool()
    def flex_sensor_analyze_dxf(dxf_path: str) -> dict:
        """
        Analyze a DXF microstructure profile before importing it into COMSOL.

        Returns entity counts, bounds, and a unit recommendation. The tool is
        intentionally conservative and only parses common LINE/ARC profiles.
        """
        try:
            path = Path(dxf_path)
            if not path.exists():
                return {"success": False, "error": f"DXF file not found: {dxf_path}"}
            entities, bounds = _parse_dxf_entities(path)
            counts = Counter(kind for kind, _ in entities)
            unit_recommendation = "um" if bounds["width"] < 10000 and bounds["height"] < 10000 else "m"
            return {
                "success": True,
                "file": str(path.resolve()),
                "entity_counts": dict(counts),
                "bounds": bounds,
                "unit_recommendation": unit_recommendation,
                "notes": [
                    "For the reference sensor DXF, drawing units are treated as micrometers.",
                    "Sharp corners should be rounded before import if contact convergence is poor.",
                ],
            }
        except Exception as exc:
            return {"success": False, "error": f"Failed to analyze DXF: {exc}"}

    @mcp.tool()
    def flex_sensor_build_contact_model(
        dxf_path: str,
        model_name: str = "flex_sensor_contact",
        para_list: str = "range(0,0.01,1)",
        solve: bool = False,
        save: bool = True,
        save_path: Optional[str] = None,
        geometry_unit: str = "um",
        displacement_coefficient: str = "10[um]",
        lambda_lame: str = "1.2e6[Pa]",
        mu_lame: str = "2.4e6[Pa]",
        sensor_density: str = "1000[kg/m^3]",
        thickness: str = "1[um]",
        initial_gap_um: float = 0.1,
        electrode_height_um: float = 2.0,
        electrode_margin_um: float = 10.0,
        mesh_size: int = 5,
        max_seg_iter: int = 200,
        max_sub_iter: int = 50,
        use_rigid_domain: bool = False,
    ) -> dict:
        """
        Build a 2D flexible pressure sensor contact-compression model from DXF.

        The model follows the workflow validated for microstructured flexible
        pressure sensors: DXF sensitive layer, steel upper electrode, Neo-Hookean
        sensitive material, fixed bottom, side x-constraints, downward electrode
        displacement, contact pair, normal mesh, and stationary parametric sweep.
        """
        if not session_manager.is_connected or session_manager.client is None:
            return {"success": False, "error": "No active COMSOL session. Start with comsol_start first."}

        try:
            path = Path(dxf_path)
            if not path.exists():
                return {"success": False, "error": f"DXF file not found: {dxf_path}"}

            entities, bounds = _parse_dxf_entities(path)
            xmin = bounds["xmin"]
            xmax = bounds["xmax"]
            ymin = bounds["ymin"]
            ymax = bounds["ymax"]
            width = bounds["width"]
            height = bounds["height"]
            tol = max(width, height) * 1e-4
            base_top_y = ymin + 0.50 * height
            electrode_bottom = ymax + initial_gap_um

            client = session_manager.client
            model = client.create(model_name)
            actual_name = session_manager.add_model(model)
            session_manager.set_current_model(actual_name)
            jm = model.java
            jm.label(f"{actual_name}.mph")

            jm.param().set("para", "0", "Dimensionless displacement sweep parameter")
            jm.param().set("disp_coeff", displacement_coefficient, "Downward displacement coefficient")
            jm.param().set("lambda_lame", lambda_lame, "Neo-Hookean Lame lambda")
            jm.param().set("mu_lame", mu_lame, "Neo-Hookean Lame mu")
            jm.param().set("rho_sensor", sensor_density, "Sensitive layer density")
            jm.param().set("thickness", thickness, "2D out-of-plane thickness")

            comp = jm.component().create("comp1", True)
            geom = comp.geom().create("geom1", 2)
            geom.lengthUnit(geometry_unit)

            imp = geom.feature().create("imp1", "Import")
            imp.label("Sensitive layer DXF")
            imp.set("filename", str(path.resolve()))
            _try_set(imp, "selresult", True)

            rect = geom.feature().create("r_plate", "Rectangle")
            rect.label("Upper steel electrode")
            rect.set("size", [f"{width + 2 * electrode_margin_um}", f"{electrode_height_um}"])
            rect.set("pos", [f"{xmin - electrode_margin_um}", f"{electrode_bottom}"])
            _try_set(rect, "selresult", True)

            geom.feature("fin").set("action", "assembly")
            geom.feature("fin").set("createpairs", False)
            geom.run()

            _create_box_selection(comp, "sel_sensor_dom", 2, f"{xmin - tol}", f"{xmax + tol}", f"{ymin - tol}", f"{ymax + tol}", "inside")
            _create_box_selection(
                comp,
                "sel_plate_dom",
                2,
                f"{xmin - electrode_margin_um - tol}",
                f"{xmax + electrode_margin_um + tol}",
                f"{electrode_bottom - tol}",
                f"{electrode_bottom + electrode_height_um + tol}",
                "inside",
            )
            _create_box_selection(comp, "sel_bottom", 1, f"{xmin - tol}", f"{xmax + tol}", f"{ymin - tol}", f"{ymin + tol}", "inside")
            _create_box_selection(comp, "sel_left", 1, f"{xmin - tol}", f"{xmin + tol}", f"{ymin - tol}", f"{ymax + tol}", "inside")
            _create_box_selection(comp, "sel_right", 1, f"{xmax - tol}", f"{xmax + tol}", f"{ymin - tol}", f"{ymax + tol}", "inside")
            comp.selection().create("sel_sides", "Union")
            comp.selection("sel_sides").set("entitydim", JInt(1))
            comp.selection("sel_sides").set("input", ["sel_left", "sel_right"])
            _create_box_selection(comp, "sel_sensor_top", 1, f"{xmin - tol}", f"{xmax + tol}", f"{base_top_y}", f"{ymax + tol}", "inside")
            _create_box_selection(
                comp,
                "sel_plate_bottom",
                1,
                f"{xmin - electrode_margin_um - tol}",
                f"{xmax + electrode_margin_um + tol}",
                f"{electrode_bottom - tol}",
                f"{electrode_bottom + tol}",
                "inside",
            )

            comp.pair().create("p1", "Contact")
            comp.pair("p1").pairName("upper_electrode_to_sensitive_layer")
            comp.pair("p1").source().named("sel_plate_bottom")
            comp.pair("p1").destination().named("sel_sensor_top")

            mat_sensor = comp.material().create("mat_sensor", "Common")
            mat_sensor.label("Sensitive Neo-Hookean layer")
            mat_sensor.selection().named("sel_sensor_dom")
            mat_sensor.propertyGroup().create("Lame", "Lame", "Lame_parameters")
            mat_sensor.propertyGroup("Lame").set("lambLame", ["lambda_lame"])
            mat_sensor.propertyGroup("Lame").set("muLame", ["mu_lame"])
            mat_sensor.propertyGroup("def").set("density", ["rho_sensor"])

            mat_plate = comp.material().create("mat_plate", "Common")
            mat_plate.label("Structural steel electrode")
            mat_plate.selection().named("sel_plate_dom")
            mat_plate.propertyGroup().create("Enu", "Enu", "Young's modulus and Poisson's ratio")
            mat_plate.propertyGroup("Enu").set("E", "200[GPa]")
            mat_plate.propertyGroup("Enu").set("nu", "0.30")
            mat_plate.propertyGroup("def").set("density", ["7850[kg/m^3]"])

            solid = comp.physics().create("solid", "SolidMechanics", "geom1")
            solid.prop("d").set("d", "thickness")

            hmm = solid.create("hmm1", "HyperelasticModel", JInt(2))
            hmm.label("Neo-Hookean sensitive layer")
            hmm.selection().named("sel_sensor_dom")
            _try_set(hmm, "MaterialModel", "NeoHookean")

            if use_rigid_domain:
                rigid = solid.create("rig_plate", "RigidDomain", JInt(2))
                rigid.selection().named("sel_plate_dom")

            fix = solid.create("fix_bottom", "Fixed", JInt(1))
            fix.selection().named("sel_bottom")

            side_disp = solid.create("disp_sides", "Displacement1", JInt(1))
            side_disp.selection().named("sel_sides")
            side_disp.setIndex("Direction", "prescribed", JInt(0))
            side_disp.setIndex("U0", "0", JInt(0))

            plate_disp = solid.create("disp_plate", "Displacement2", JInt(2))
            plate_disp.selection().named("sel_plate_dom")
            plate_disp.setIndex("Direction", "prescribed", JInt(0))
            plate_disp.setIndex("Direction", "prescribed", JInt(1))
            plate_disp.setIndex("U0", "0", JInt(0))
            plate_disp.setIndex("U0", "-disp_coeff*para", JInt(1))

            try:
                contact = solid.feature("dcnt1")
            except Exception:
                contact = solid.create("dcnt1", "Contact", JInt(1))
            contact.set("pairSelection", "list")
            contact.set("pairs", ["p1"])
            contact.set("ContactMethodCtrl", "AugmentedLagrange")
            _try_set(contact, "tunedFor", "Stability")

            mesh = comp.mesh().create("mesh1", "geom1")
            mesh.autoMeshSize(JInt(mesh_size))
            mesh.run()

            study = jm.study().create("std1")
            stat = study.create("stat", "Stationary")
            stat.set("useparam", True)
            stat.setIndex("pname", "para", JInt(0))
            stat.setIndex("plistarr", para_list, JInt(0))
            stat.setIndex("punit", "", JInt(0))

            solve_status = None
            if solve:
                study.createAutoSequences("all")
                try:
                    seg = jm.sol("sol1").feature("s1").feature("se1")
                    seg.set("maxsegiter", JInt(max_seg_iter))
                    for subtag in ("ss1", "ls1"):
                        try:
                            seg.feature(subtag).set("maxsubiter", JInt(max_sub_iter))
                        except Exception:
                            pass
                except Exception:
                    pass
                jm.sol("sol1").runAll()
                solve_status = "completed"

            version_path = None
            latest_path = None
            if save:
                if save_path:
                    latest_path = str(Path(save_path).resolve())
                    Path(latest_path).parent.mkdir(parents=True, exist_ok=True)
                    model.save(latest_path)
                else:
                    version_path = generate_version_path(actual_name)
                    latest_path = generate_latest_path(actual_name)
                    model.save(version_path)
                    model.save(latest_path)

            return {
                "success": True,
                "model": actual_name,
                "dxf": str(path.resolve()),
                "geometry_unit": geometry_unit,
                "bounds": bounds,
                "entity_counts": dict(Counter(kind for kind, _ in entities)),
                "geometry_entities": list(geom.getNEntities()),
                "sweep": para_list,
                "solve_status": solve_status,
                "saved_version": version_path,
                "saved_latest": latest_path,
                "selections": {
                    "sensor_domain": "sel_sensor_dom",
                    "plate_domain": "sel_plate_dom",
                    "sensor_top": "sel_sensor_top",
                    "plate_bottom": "sel_plate_bottom",
                    "sensor_bottom": "sel_bottom",
                    "sensor_sides": "sel_sides",
                },
                "postprocess_hint": "Use flex_sensor_export_contact_results after solving.",
            }
        except Exception as exc:
            return {"success": False, "error": f"Failed to build flexible sensor model: {exc}"}

    @mcp.tool()
    def flex_sensor_export_contact_results(
        model_name: Optional[str] = None,
        output_path: Optional[str] = None,
        para_list: str = "range(0,0.01,1)",
        displacement_coefficient_um: float = 10.0,
        target_selection: str = "sel_sensor_top",
        pressure_expression: str = "solid.Tn",
        threshold_expression: str = "1[Pa]",
    ) -> dict:
        """
        Export flexible sensor contact length and pressure-integral results.

        The model must already contain a solved dataset `dset1` and a boundary
        selection for the contact destination, normally `sel_sensor_top`.
        """
        model = session_manager.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'no current model'}"}

        try:
            jm = model.java
            para_values = _parse_parameter_values(para_list)
            top_length = _line_integral(jm, "1", target_selection)
            contact_length = _line_integral(jm, f"{pressure_expression}>0", target_selection)
            contact_length_threshold = _line_integral(jm, f"{pressure_expression}>{threshold_expression}", target_selection)
            pressure_integral = _line_integral(jm, f"{pressure_expression}*({pressure_expression}>0)", target_selection)

            if output_path:
                csv_path = Path(output_path)
            else:
                base = Path(generate_latest_path(model.name())).with_suffix("")
                csv_path = base.parent / f"{base.name}_contact_results.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            rows = []
            with csv_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [
                        "para",
                        "displacement_um",
                        "top_length_um",
                        "contact_length_um",
                        "contact_length_threshold_um",
                        "pressure_integral",
                        "avg_pressure_over_contact",
                    ]
                )
                for i, para in enumerate(para_values):
                    length = contact_length[i] if i < len(contact_length) else float("nan")
                    pint = pressure_integral[i] if i < len(pressure_integral) else float("nan")
                    avg = pint / length if length and math.isfinite(length) else 0.0
                    row = [
                        para,
                        para * displacement_coefficient_um,
                        top_length[min(i, len(top_length) - 1)],
                        length,
                        contact_length_threshold[i] if i < len(contact_length_threshold) else float("nan"),
                        pint,
                        avg,
                    ]
                    rows.append(row)
                    writer.writerow(row)

            return {
                "success": True,
                "model": model.name(),
                "output_path": str(csv_path.resolve()),
                "rows": len(rows),
                "first_row": rows[0] if rows else None,
                "last_row": rows[-1] if rows else None,
                "pressure_expression": pressure_expression,
                "threshold_expression": threshold_expression,
            }
        except Exception as exc:
            return {"success": False, "error": f"Failed to export contact results: {exc}"}
