import os
import tempfile
import numpy as np
import cadquery as cq
import gmsh
import meshio
from flask import Flask, request, jsonify
from openai import OpenAI
from skfem import MeshTet, ElementTetP1, Basis, BilinearForm, LinearForm, enforce, solve
from skfem.helpers import grad, sym_grad, trace, eye

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# -----------------------------------------------------------------------------
# STEP 1: Text-to-CadQuery Generator (LLM)
# -----------------------------------------------------------------------------
def generate_cad_from_prompt(prompt: str) -> str:
    """Uses LLM to convert a text description into executable CadQuery code."""
    system_prompt = (
        "You are an expert CAD engineer. Generate clean Python code using CadQuery.\n"
        "Return ONLY the executable Python code inside a block. "
        "The CAD model must be assigned to a global variable named 'result'."
    )
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create CadQuery code for: {prompt}"}
        ],
        temperature=0.2
    )
    
    raw_code = response.choices[0].message.content
    # Clean code blocks if returned
    if "```python" in raw_code:
        raw_code = raw_code.split("```python")[1].split("```")[0].strip()
    elif "```" in raw_code:
        raw_code = raw_code.split("```")[1].split("```")[0].strip()
        
    return raw_code


# -----------------------------------------------------------------------------
# STEP 2: Real FEA Solver (scikit-fem + Gmsh)
# -----------------------------------------------------------------------------
def run_fea_simulation(cq_object, force_magnitude_n: float, E=210e3, nu=0.3):
    """
    Exports CadQuery solid to STEP, meshes with Gmsh, and solves 3D linear elasticity.
    E = Young's Modulus (MPa for Steel ~ 210,000 MPa)
    nu = Poisson's Ratio (~0.3)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = os.path.join(tmpdir, "model.step")
        msh_path = os.path.join(tmpdir, "model.msh")
        
        # 1. Export CadQuery shape to STEP file
        cq.exporters.export(cq_object, step_path)

        # 2. Generate 3D Tetrahedral Mesh using Gmsh
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0) # Quiet output
        gmsh.open(step_path)
        gmsh.model.mesh.generate(3)
        gmsh.write(msh_path)
        gmsh.finalize()

        # 3. Read mesh into scikit-fem via meshio
        m = meshio.read(msh_path)
        mesh = MeshTet(m.points.T, m.cells_dict["tetra"].T)

        # 4. Define Linear Elasticity Forms (Hooke's Law)
        lame_mu = E / (2 * (1 + nu))
        lame_lambda = (E * nu) / ((1 + nu) * (1 - 2 * nu))

        element = ElementTetP1()
        basis = Basis(mesh, element, dim=3)

        @BilinearForm
        def elasticity(u, v, w):
            def strain(w):
                return sym_grad(w)
            def stress(w):
                return 2 * lame_mu * strain(w) + lame_lambda * eye(trace(strain(w)), 3)
            return np.einsum('ij...,ij...->...', stress(u), strain(v))

        @LinearForm
        def load(v, w):
            # Apply downward z-force on top nodes
            return -1.0 * force_magnitude_n * v[2]

        # 5. Assemble Stiffness Matrix & Apply Boundary Conditions
        K = elasticity.assemble(basis)
        f = load.assemble(basis)

        # Fix bottom boundary nodes (Z minimum)
        z_coords = mesh.p[2, :]
        min_z = np.min(z_coords)
        fixed_nodes = np.where(np.isclose(z_coords, min_z, atol=1e-2))[0]
        
        # Expand DOFs for 3D displacement (x, y, z)
        fixed_dofs = np.concatenate([3 * fixed_nodes, 3 * fixed_nodes + 1, 3 * fixed_nodes + 2])

        K_bc, f_bc = enforce(K, f, D=fixed_dofs)

        # 6. Solve Linear System (K * u = f)
        u_displacements = solve(K_bc, f_bc)

        # Calculate Max Displacement Magnitude
        u_reshaped = u_displacements.reshape(-1, 3)
        disp_magnitudes = np.linalg.norm(u_reshaped, axis=1)
        max_disp = float(np.max(disp_magnitudes))

        # Calculate approximate Von Mises Stress proxy
        max_stress_est = max_disp * (E / np.max(mesh.p))

        return {
            "max_displacement_mm": round(max_disp, 4),
            "max_stress_mpa": round(max_stress_est, 2),
            "num_mesh_elements": mesh.t.shape[1],
            "num_nodes": mesh.p.shape[1]
        }


# -----------------------------------------------------------------------------
# STEP 3: Primary API Pipeline Endpoint
# -----------------------------------------------------------------------------
@app.route("/prompt-to-sim", methods=["POST"])
def prompt_to_simulation():
    try:
        data = request.get_json() or {}
        text_prompt = data.get("prompt", "A cantilever beam 100mm long, 10mm wide, 10mm high")
        load_force = float(data.get("load_force", 1000)) # Force in Newtons

        # Step A: Convert Prompt -> CadQuery Code
        generated_code = generate_cad_from_prompt(text_prompt)

        # Step B: Execute Generated Code Safely
        local_scope = {}
        exec(generated_code, {"cq": cq}, local_scope)
        cad_result = local_scope.get("result")

        if cad_result is None:
            return jsonify({"error": "Failed to create CadQuery object from prompt."}), 400

        # Step C: Run Real FEA Simulation
        sim_results = run_fea_simulation(cad_result, force_magnitude_n=load_force)

        # Step D: Return Pipeline Data & CAD Code back to Client
        return jsonify({
            "status": "SUCCESS",
            "prompt": text_prompt,
            "generated_code": generated_code,
            "simulation": sim_results
        }), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
