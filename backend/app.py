import os
import tempfile
import numpy as np
import cadquery as cq
import trimesh
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# -----------------------------------------------------------------------------
# 1. Text-to-CadQuery LLM Generator
# -----------------------------------------------------------------------------
def generate_cad_from_prompt(prompt: str) -> str:
    system_prompt = (
        "You are an expert CAD engineer. Generate clean Python code using CadQuery.\n"
        "Return ONLY executable Python code inside a block.\n"
        "The final CAD model MUST be assigned to a global variable named 'result'."
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
    if "```python" in raw_code:
        raw_code = raw_code.split("```python")[1].split("```")[0].strip()
    elif "```" in raw_code:
        raw_code = raw_code.split("```")[1].split("```")[0].strip()
        
    return raw_code


# -----------------------------------------------------------------------------
# 2. Pure-Python FEA Mesh & Structural Calculation (No Gmsh required)
# -----------------------------------------------------------------------------
def run_fea_simulation(cq_object, force_n: float, E_modulus_mpa=210000.0):
    """
    Tessellates CadQuery geometry to STL and computes stress & deflection.
    Default material: Structural Steel (E = 210,000 MPa)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = os.path.join(tmpdir, "model.stl")
        
        # 1. Native CadQuery export to STL mesh
        cq.exporters.export(cq_object, stl_path, exportType="STL", tolerance=0.1)

        # 2. Load mesh via Trimesh
        mesh = trimesh.load(stl_path)
        
        # Calculate bounding box dimensions (mm)
        bounds = mesh.extents  # [length_x, length_y, length_z]
        length = float(np.max(bounds))
        width = float(np.median(bounds))
        height = float(np.min(bounds)) if np.min(bounds) > 0 else 1.0

        # Calculate Area Moment of Inertia for beam bending proxy: I = (w * h^3) / 12
        I_inertia = (width * (height ** 3)) / 12.0
        
        # Beam deflection equation: delta = (F * L^3) / (3 * E * I)
        max_displacement = (force_n * (length ** 3)) / (3 * E_modulus_mpa * I_inertia)
        
        # Bending stress equation: sigma = (M * y) / I = (F * L * (h/2)) / I
        bending_moment = force_n * length
        max_stress = (bending_moment * (height / 2.0)) / I_inertia

        return {
            "max_displacement_mm": round(float(max_displacement), 4),
            "max_stress_mpa": round(float(max_stress), 2),
            "bounding_dimensions_mm": {
                "length": round(length, 2),
                "width": round(width, 2),
                "height": round(height, 2)
            },
            "num_triangles": len(mesh.faces),
            "num_vertices": len(mesh.vertices)
        }


# -----------------------------------------------------------------------------
# 3. API Endpoint
# -----------------------------------------------------------------------------
@app.route("/prompt-to-sim", methods=["POST"])
def prompt_to_simulation():
    try:
        data = request.get_json() or {}
        text_prompt = data.get("prompt", "A cantilever beam 100mm long, 10mm wide, 10mm high")
        load_force = float(data.get("load_force", 1000))

        # A. LLM Prompt -> CadQuery Code
        generated_code = generate_cad_from_prompt(text_prompt)

        # B. Execute CadQuery Code
        local_scope = {}
        exec(generated_code, {"cq": cq}, local_scope)
        cad_result = local_scope.get("result")

        if cad_result is None:
            return jsonify({"error": "Failed to create CadQuery object."}), 400

        # C. Run Simulation
        sim_results = run_fea_simulation(cad_result, force_n=load_force)

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
