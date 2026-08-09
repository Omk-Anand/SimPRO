import os
import traceback
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health_check():
    """Simple health check endpoint to verify the server is live."""
    return jsonify({
        "status": "online",
        "message": "CadQuery FEA Simulation API is up and running!"
    }), 200


@app.route("/simulate", methods=["POST"])
def simulate():
    """Primary endpoint for running CadQuery FEA simulations."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing JSON payload"}), 400

        # Extract code and load force from incoming request
        cad_code = data.get("code", "")
        load_force = data.get("load_force", 1000)

        if not cad_code:
            return jsonify({"error": "No CadQuery code provided"}), 400

        # Create a restricted execution scope
        local_scope = {}
        
        # Safely execute the passed CadQuery code snippet
        exec(cad_code, globals(), local_scope)

        # Retrieve the generated CadQuery object (typically named 'result')
        result_obj = local_scope.get("result", None)

        if result_obj is None:
            return jsonify({
                "status": "ERROR",
                "message": "CadQuery script executed, but no variable named 'result' was found."
            }), 400

        # --- SIMULATION PLACEHOLDER LOGIC ---
        # Replace this section with your actual scikit-fem / FEA calculation logic
        max_stress = float(load_force) * 0.15
        yield_limit = 250.0
        status = "PASS" if max_stress < yield_limit else "FAIL"

        return jsonify({
            "status": status,
            "max_stress": max_stress,
            "yield_limit": yield_limit,
            "message": "Simulation completed successfully."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    # For local development testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
