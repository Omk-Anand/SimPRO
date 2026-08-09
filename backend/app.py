import os
import uuid
import numpy as np
import cadquery as cq
import trimesh
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)

# Allow the frontend (different origin) to call this API.
# Lock this down to your actual frontend domain(s) in production, e.g.:
# CORS(app, resources={r"/api/*": {"origins": "https://your-frontend.vercel.app"}})
CORS(app)

# Azure AI Foundry's OpenAI-compatible v1 API. The SDK is pointed at the
# base_url (everything up to /v1); individual calls (e.g. client.responses.create)
# append their own path, so we strip the trailing "/responses" if present.
AZURE_AI_ENDPOINT = "https://avneh-4789-resource.services.ai.azure.com/openai/v1"
AZURE_AI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.5")

client = OpenAI(
    base_url=AZURE_AI_ENDPOINT,
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
)

# Where generated STL files are written so they can be served back to the browser.
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Young's modulus (MPa) per material option offered in the frontend dropdown.
MATERIAL_PROPERTIES = {
    "aluminum": 69000.0,   # Aluminum 6061
    "titanium": 113800.0,  # Titanium Ti-6Al-4V
    "pla": 3500.0,         # PLA Plastic (3D Printed)
}
DEFAULT_E_MODULUS_MPA = 210000.0  # Structural steel, used if material is unrecognized


# -----------------------------------------------------------------------------
# 1. Text-to-CadQuery LLM Generator
# -----------------------------------------------------------------------------
def generate_cad_from_prompt(prompt: str) -> str:
    system_prompt = (
        "You are an expert CAD engineer. Generate clean Python code using CadQuery.\n"
        "Return ONLY executable Python code inside a block.\n"
        "The final CAD model MUST be assigned to a global variable named 'result'."
    )

    response = client.responses.create(
        model=AZURE_AI_DEPLOYMENT,
        instructions=system_prompt,
        input=f"Create CadQuery code for: {prompt}",
        temperature=0.2
    )

    raw_code = response.output_text
    if "```python" in raw_code:
        raw_code = raw_code.split("```python")[1].split("```")[0].strip()
    elif "```" in raw_code:
        raw_code = raw_code.split("```")[1].split("```")[0].strip()

    return raw_code


# -----------------------------------------------------------------------------
# 2. Pure-Python FEA Mesh & Structural Calculation (No Gmsh required)
# -----------------------------------------------------------------------------
def run_fea_simulation(cq_object, force_n: float, stl_path: str, E_modulus_mpa=DEFAULT_E_MODULUS_MPA):
    """
    Tessellates CadQuery geometry to STL (saved at stl_path, which is served
    back to the frontend) and computes stress & deflection.
    """
    # 1. Native CadQuery export to STL mesh — written to a persistent, servable path
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
# 3. Static file route — serves generated STL models back to the frontend
# -----------------------------------------------------------------------------
@app.route("/models/<path:filename>", methods=["GET"])
def serve_model(filename):
    return send_from_directory(MODELS_DIR, filename)


# -----------------------------------------------------------------------------
# 4. API Endpoint — matches what frontend/src/Dashboard.jsx calls
# -----------------------------------------------------------------------------
@app.route("/api/simulate", methods=["POST"])
def prompt_to_simulation():
    logs = []
    try:
        data = request.get_json() or {}
        text_prompt = data.get("prompt", "A cantilever beam 100mm long, 10mm wide, 10mm high")
        load_force = float(data.get("load_force", 1000))
        material = str(data.get("material", "aluminum")).lower()
        e_modulus_mpa = MATERIAL_PROPERTIES.get(material, DEFAULT_E_MODULUS_MPA)

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

        # C. Run Simulation, saving the STL to a servable path
        logs.append(f"Running structural simulation ({material}, {load_force}N)...")
        filename = f"{uuid.uuid4().hex}.stl"
        stl_path = os.path.join(MODELS_DIR, filename)
        sim_results = run_fea_simulation(
            cad_result, force_n=load_force, stl_path=stl_path, E_modulus_mpa=e_modulus_mpa
        )
        logs.append("Simulation complete.")

        model_file_url = request.host_url.rstrip("/") + f"/models/{filename}"

        return jsonify({
            "success": True,
            "iterationLogs": logs,
            "modelFileUrl": model_file_url,
            "msg": "Simulation completed successfully.",
            "prompt": text_prompt,
            "generated_code": generated_code,
            "simulation": sim_results
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
