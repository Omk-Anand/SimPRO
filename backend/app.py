import os
import uuid
import numpy as np
import cadquery as cq
import gmsh
from skfem import MeshTet, Basis, ElementVector, ElementTetP1, condense, solve
from skfem.models.elasticity import linear_elasticity, lame_parameters
from skfem.models.poisson import laplace
from skfem.helpers import sym_grad, eye, trace
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)

# Allow the frontend (different origin) to call this API.
# Lock this down to your actual frontend domain(s) in production, e.g.:
# CORS(app, resources={r"/api/*": {"origins": "https://your-frontend.vercel.app"}})
CORS(app)

# Featherless.ai OpenAI-compatible endpoint (access to a large catalog of open models).
# Get a key at https://featherless.ai and set it as the FEATHERLESS_API_KEY env var on Render.
FEATHERLESS_ENDPOINT = "https://api.featherless.ai/v1"
FEATHERLESS_MODEL = os.environ.get("FEATHERLESS_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct")

client = OpenAI(
    base_url=FEATHERLESS_ENDPOINT,
    api_key=os.environ.get("FEATHERLESS_API_KEY"),
)

# Where generated STL files are written so they can be served back to the browser.
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Material properties: Young's modulus (MPa), Poisson's ratio, thermal conductivity (W/m·K).
MATERIAL_PROPERTIES = {
    "aluminum": {"E_mpa": 69000.0, "nu": 0.33, "k_w_mk": 167.0},   # Aluminum 6061
    "titanium": {"E_mpa": 113800.0, "nu": 0.34, "k_w_mk": 6.7},    # Titanium Ti-6Al-4V
    "pla": {"E_mpa": 3500.0, "nu": 0.36, "k_w_mk": 0.13},          # PLA (3D printed)
}
DEFAULT_MATERIAL = {"E_mpa": 210000.0, "nu": 0.3, "k_w_mk": 50.0}  # Structural steel fallback

# Thermal boundary assumption: one face acts as a heat source (e.g. a motor mount),
# the opposite face sits at ambient. This is a simplification for a heat-map preview,
# not a substitute for a full convective CFD simulation.
THERMAL_HOT_C = 80.0
THERMAL_AMBIENT_C = 20.0


# -----------------------------------------------------------------------------
# 1. Text-to-CadQuery LLM Generator
# -----------------------------------------------------------------------------
def generate_cad_from_prompt(prompt: str) -> str:
    system_prompt = (
        "You are an expert CAD engineer. Generate clean Python code using CadQuery.\n"
        "Return ONLY executable Python code inside a block.\n"
        "The final CAD model MUST be assigned to a global variable named 'result'.\n"
        "The result MUST be a single, closed, watertight solid (not a shell, sketch, "
        "or multi-body compound) so it can be volumetrically meshed for simulation. "
        "Keep geometry simple enough to mesh reliably (avoid extremely thin walls "
        "or near-zero-thickness features)."
    )

    response = client.chat.completions.create(
        model=FEATHERLESS_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create CadQuery code for: {prompt}"}
        ],
        temperature=0.2
    )

    raw_code = response.choices[0].message.content
    if "```python" in raw_code:
        raw_code = raw_code.split("```python")[1].split("```")[0].strip()
    elif "```" in raw_code:
        raw_code = raw_code.split("```")[1].split("```")[0].strip()

    return raw_code


# -----------------------------------------------------------------------------
# 2. Volumetric meshing (gmsh, OCC kernel, direct from STEP — not tessellated STL)
# -----------------------------------------------------------------------------
def build_volume_mesh(cad_result, tmp_step_path: str, mesh_size_mm: float = None):
    """
    Exports the CadQuery solid to STEP (preserves exact curved geometry, unlike
    STL tessellation) and meshes it volumetrically with gmsh's OCC kernel.
    Returns node coordinates, tetrahedra (for FEA), and boundary triangles
    (for the STL served to the frontend) — all sharing the same node indices,
    so simulation results map directly onto the visualized surface.
    """
    cq.exporters.export(cad_result, tmp_step_path, exportType="STEP")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("part")
        gmsh.model.occ.importShapes(tmp_step_path)
        gmsh.model.occ.synchronize()

        # Auto-size the mesh relative to the model's bounding box if not specified.
        bbox = gmsh.model.getBoundingBox(-1, -1)
        diag = float(np.linalg.norm(np.array(bbox[3:6]) - np.array(bbox[0:3])))
        size = mesh_size_mm or max(diag / 20.0, 0.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size / 5.0)
        gmsh.model.mesh.generate(3)

        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        coords = np.array(node_coords, dtype=float).reshape(-1, 3)
        tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

        vol_types, _, vol_nodes = gmsh.model.mesh.getElements(dim=3)
        if 4 not in vol_types:
            raise ValueError("Geometry did not produce a valid tetrahedral volume mesh.")
        tet_pos = list(vol_types).index(4)
        tets_raw = np.array(vol_nodes[tet_pos], dtype=np.int64).reshape(-1, 4)
        tets = np.vectorize(tag_to_idx.get)(tets_raw)

        surf_types, _, surf_nodes = gmsh.model.mesh.getElements(dim=2)
        tri_pos = list(surf_types).index(2)
        tris_raw = np.array(surf_nodes[tri_pos], dtype=np.int64).reshape(-1, 3)
        tris = np.vectorize(tag_to_idx.get)(tris_raw)
    finally:
        gmsh.finalize()

    return coords, tets, tris


def write_stl_from_surface(coords: np.ndarray, tris: np.ndarray, stl_path: str):
    """Writes an ASCII STL from the gmsh boundary triangles (same nodes as the FEA mesh)."""
    with open(stl_path, "w") as f:
        f.write("solid model\n")
        for tri in tris:
            v0, v1, v2 = coords[tri[0]], coords[tri[1]], coords[tri[2]]
            normal = np.cross(v1 - v0, v2 - v0)
            norm_len = np.linalg.norm(normal)
            normal = normal / norm_len if norm_len > 0 else np.array([0.0, 0.0, 1.0])
            f.write(f"facet normal {normal[0]:.6e} {normal[1]:.6e} {normal[2]:.6e}\n")
            f.write("outer loop\n")
            for v in (v0, v1, v2):
                f.write(f"vertex {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}\n")
            f.write("endloop\nendfacet\n")
        f.write("endsolid model\n")


# -----------------------------------------------------------------------------
# 3. Structural FEA — linear elasticity, von Mises stress per node
# -----------------------------------------------------------------------------
def run_structural_fea(coords: np.ndarray, tets: np.ndarray, force_n: float, E_mpa: float, nu: float):
    """
    Fixed (clamped) at the lowest-Z face (e.g. a mounting plate), with the load
    applied downward at the highest-Z face. This is a simplifying assumption —
    real boundary conditions depend on how the part is actually mounted/loaded.
    """
    mesh = MeshTet(coords.T, tets.T)
    lam, mu = lame_parameters(E_mpa, nu)
    e_vec = ElementVector(ElementTetP1())
    basis = Basis(mesh, e_vec)

    K = linear_elasticity(lam, mu).assemble(basis)

    z = coords[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    tol = (z_max - z_min) * 0.02 + 1e-6

    fixed_dofs = basis.get_dofs(lambda x: x[2] <= z_min + tol)
    loaded_dofs = basis.get_dofs(lambda x: x[2] >= z_max - tol)
    loaded_z_dofs = loaded_dofs.nodal["u^3"]

    if len(loaded_z_dofs) == 0 or len(fixed_dofs.all()) == 0:
        raise ValueError("Could not identify distinct top/bottom faces for boundary conditions.")

    f = np.zeros(basis.N)
    f[loaded_z_dofs] = -force_n / len(loaded_z_dofs)

    u = solve(*condense(K, f, D=fixed_dofs.all()))

    ux = u[basis.nodal_dofs[0]]
    uy = u[basis.nodal_dofs[1]]
    uz = u[basis.nodal_dofs[2]]
    disp_mag = np.sqrt(ux**2 + uy**2 + uz**2)

    # Von Mises stress: computed per element at quadrature points, then
    # averaged onto nodes for a smooth per-vertex field the frontend can color.
    uh = basis.interpolate(u)
    eps = sym_grad(uh)
    tr_eps = trace(eps)
    ident = eye(tr_eps, 3)
    sigma = lam * ident * tr_eps + 2.0 * mu * eps
    s11, s22, s33 = sigma[0][0], sigma[1][1], sigma[2][2]
    s12, s13, s23 = sigma[0][1], sigma[0][2], sigma[1][2]
    vm_qp = np.sqrt(0.5 * ((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2
                            + 6 * (s12**2 + s13**2 + s23**2)))
    vm_elem = vm_qp.mean(axis=1)

    n_nodes = coords.shape[0]
    node_stress_sum = np.zeros(n_nodes)
    node_stress_count = np.zeros(n_nodes)
    for elem_idx in range(tets.shape[0]):
        for node_idx in tets[elem_idx]:
            node_stress_sum[node_idx] += vm_elem[elem_idx]
            node_stress_count[node_idx] += 1
    node_stress = node_stress_sum / np.maximum(node_stress_count, 1)

    return {
        "displacement_field_mm": disp_mag.tolist(),
        "stress_field_mpa": node_stress.tolist(),
        "max_displacement_mm": round(float(disp_mag.max()), 5),
        "max_von_mises_stress_mpa": round(float(node_stress.max()), 3),
    }


# -----------------------------------------------------------------------------
# 4. Thermal FEA — steady-state conduction, temperature per node
# -----------------------------------------------------------------------------
def run_thermal_fea(coords: np.ndarray, tets: np.ndarray, k_w_mk: float):
    """
    Steady-state heat *conduction* (not full convective CFD). One face is held
    at a fixed "hot" temperature (e.g. near a motor), the opposite face at
    ambient, approximating where heat concentrates in the part.
    """
    mesh = MeshTet(coords.T, tets.T)
    basis = Basis(mesh, ElementTetP1())
    L = laplace.assemble(basis) * k_w_mk

    z = coords[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    tol = (z_max - z_min) * 0.02 + 1e-6

    hot_dofs = basis.get_dofs(lambda x: x[2] >= z_max - tol)
    cold_dofs = basis.get_dofs(lambda x: x[2] <= z_min + tol)

    T = basis.zeros()
    T[hot_dofs.all()] = THERMAL_HOT_C
    T[cold_dofs.all()] = THERMAL_AMBIENT_C
    D = np.union1d(hot_dofs.all(), cold_dofs.all())

    T_sol = solve(*condense(L, x=T, D=D))

    return {
        "temperature_field_c": T_sol.tolist(),
        "max_temperature_c": round(float(T_sol.max()), 2),
        "min_temperature_c": round(float(T_sol.min()), 2),
    }


# -----------------------------------------------------------------------------
# 5. Static file route — serves generated STL models back to the frontend
# -----------------------------------------------------------------------------
@app.route("/models/<path:filename>", methods=["GET"])
def serve_model(filename):
    return send_from_directory(MODELS_DIR, filename)


# -----------------------------------------------------------------------------
# 6. API Endpoint — matches what frontend/src/Dashboard.jsx calls
# -----------------------------------------------------------------------------
@app.route("/api/simulate", methods=["POST"])
def prompt_to_simulation():
    logs = []
    try:
        data = request.get_json() or {}
        text_prompt = data.get("prompt", "A cantilever beam 100mm long, 10mm wide, 10mm high")
        load_force = float(data.get("load_force", 1000))
        material = str(data.get("material", "aluminum")).lower()
        mat_props = MATERIAL_PROPERTIES.get(material, DEFAULT_MATERIAL)

        # A. LLM Prompt -> CadQuery Code
        logs.append(f"Generating CAD geometry for prompt: \"{text_prompt}\"")
        generated_code = generate_cad_from_prompt(text_prompt)

        # B. Execute CadQuery Code
        logs.append("Executing generated CadQuery script...")
        local_scope = {}
        exec(generated_code, {"cq": cq}, local_scope)
        cad_result = local_scope.get("result")

        if cad_result is None:
            return jsonify({
                "success": False,
                "iterationLogs": logs + ["Failed to create CadQuery object from generated code."],
                "modelFileUrl": None,
                "msg": "Failed to create CadQuery object."
            }), 400

        # C. Build a volumetric mesh from the exact solid (not a tessellated approximation)
        logs.append("Meshing geometry (gmsh, volumetric tetrahedra)...")
        run_id = uuid.uuid4().hex
        step_path = os.path.join(MODELS_DIR, f"{run_id}.step")
        try:
            coords, tets, tris = build_volume_mesh(cad_result, step_path)
        finally:
            if os.path.exists(step_path):
                os.remove(step_path)
        logs.append(f"Mesh generated: {coords.shape[0]} nodes, {tets.shape[0]} tetrahedra.")

        # D. Write the STL for the 3D viewer, using the same nodes as the FEA mesh
        filename = f"{run_id}.stl"
        stl_path = os.path.join(MODELS_DIR, filename)
        write_stl_from_surface(coords, tris, stl_path)

        # E. Structural FEA — von Mises stress + displacement, per node
        logs.append(f"Running structural FEA ({material}, {load_force}N)...")
        structural = run_structural_fea(coords, tets, load_force, mat_props["E_mpa"], mat_props["nu"])
        logs.append(f"Max stress: {structural['max_von_mises_stress_mpa']} MPa, "
                     f"max displacement: {structural['max_displacement_mm']} mm.")

        # F. Thermal FEA — steady-state conduction heat map, per node
        logs.append("Running thermal FEA (steady-state conduction)...")
        thermal = run_thermal_fea(coords, tets, mat_props["k_w_mk"])
        logs.append(f"Temperature range: {thermal['min_temperature_c']}\u2013{thermal['max_temperature_c']}\u00b0C.")

        logs.append("Simulation complete.")
        model_file_url = request.host_url.rstrip("/") + f"/models/{filename}"

        return jsonify({
            "success": True,
            "iterationLogs": logs,
            "modelFileUrl": model_file_url,
            "msg": "Simulation completed successfully.",
            "prompt": text_prompt,
            "generated_code": generated_code,
            "mesh": {
                "num_nodes": int(coords.shape[0]),
                "num_tetrahedra": int(tets.shape[0]),
                "node_coordinates_mm": coords.tolist(),
            },
            "structural": structural,
            "thermal": thermal,
        }), 200

    except Exception as e:
        app.logger.exception("Simulation failed")
        return jsonify({
            "success": False,
            "iterationLogs": logs + [f"Error: {str(e)}"],
            "modelFileUrl": None,
            "msg": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    
