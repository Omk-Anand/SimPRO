import React, { useState, useRef } from 'react';
import { Canvas, useLoader } from '@react-three/fiber';
import { OrbitControls, Center } from '@react-three/drei';
import * as THREE from 'three';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import { Loader2, Play, Box, Activity, Thermometer } from 'lucide-react';

// 3D Model Mesh Component to load and display the STL file
function STLModel({ url }) {
  const geom = useLoader(STLLoader, url);
  return (
    <Center>
      <mesh geometry={geom}>
        <meshStandardMaterial color="#3b82f6" roughness={0.4} metalness={0.2} />
      </mesh>
    </Center>
  );
}

export default function Dashboard() {
  const [prompt, setPrompt] = useState('A cantilever beam 100mm long, 10mm wide, 10mm high');
  const [material, setMaterial] = useState('aluminum');
  const [loadForce, setLoadForce] = useState(1000);
  
  const [loading, setLoading] = useState(false);
  const [simulationData, setSimulationData] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);

  // Change this to your deployed Render backend URL in production
  const BACKEND_URL = 'https://simpro-1.onrender.com';

  const handleSimulate = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setLogs(['Sending request to backend...']);

    try {
      const response = await fetch(BACKEND_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          material,
          load_force: parseFloat(loadForce)
        })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.msg || 'Simulation failed on the server.');
      }

      setSimulationData(data);
      setLogs(data.iterationLogs || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Left Sidebar: Controls & Logs */}
      <div className="w-1/3 p-6 overflow-y-auto border-r border-slate-800 flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Box className="text-blue-500" /> AI 3D CAD & FEA Studio
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Describe a part, generate code, and analyze structural & thermal properties.
          </p>
        </div>

        <form onSubmit={handleSimulate} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
              Part Description Prompt
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              placeholder="e.g., An L-bracket with mounting holes..."
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                Material
              </label>
              <select
                value={material}
                onChange={(e) => setMaterial(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm outline-none"
              >
                <option value="aluminum">Aluminum 6061</option>
                <option value="titanium">Titanium Ti-6Al-4V</option>
                <option value="pla">PLA (3D Printed)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                Load Force (N)
              </label>
              <input
                type="number"
                value={loadForce}
                onChange={(e) => setLoadForce(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm outline-none"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white font-medium py-2.5 rounded-lg transition flex items-center justify-center gap-2 mt-2"
          >
            {loading ? <Loader2 className="animate-spin w-5 h-5" /> : <Play className="w-5 h-5" />}
            {loading ? 'Running Simulation...' : 'Generate & Simulate'}
          </button>
        </form>

        {/* Results Metrics Panel */}
        {simulationData && (
          <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 flex flex-col gap-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300">Simulation Metrics</h3>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800">
                <span className="text-slate-400 block">Max Stress</span>
                <span className="text-base font-semibold text-blue-400">
                  {simulationData.structural.max_von_mises_stress_mpa} MPa
                </span>
              </div>
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800">
                <span className="text-slate-400 block">Max Displacement</span>
                <span className="text-base font-semibold text-blue-400">
                  {simulationData.structural.max_displacement_mm} mm
                </span>
              </div>
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800">
                <span className="text-slate-400 block">Peak Temp</span>
                <span className="text-base font-semibold text-amber-400">
                  {simulationData.thermal.max_temperature_c} °C
                </span>
              </div>
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800">
                <span className="text-slate-400 block">Mesh Elements</span>
                <span className="text-base font-semibold text-emerald-400">
                  {simulationData.mesh.num_tetrahedra} tets
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Console / Iteration Logs */}
        <div className="flex-1 bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-400 overflow-y-auto max-h-48">
          <div className="text-slate-200 font-bold mb-1">Execution Logs:</div>
          {error && <div className="text-red-400 mb-1">Error: {error}</div>}
          {logs.map((log, index) => (
            <div key={index} className="mb-0.5">&gt; {log}</div>
          ))}
        </div>
      </div>

      {/* Right Main Viewport: 3D Canvas */}
      <div className="flex-1 relative bg-slate-900">
        {simulationData?.modelFileUrl ? (
          <Canvas camera={{ position: [150, 150, 150], fov: 50 }}>
            <ambientLight intensity={0.7} />
            <directionalLight position={[10, 20, 15]} intensity={1} />
            <pointLight position={[-10, -20, -15]} intensity={0.5} />
            <STLModel url={simulationData.modelFileUrl} />
            <OrbitControls makeDefault />
          </Image of 3D computer graphics viewport rendering an STL mechanical part>
          </Canvas>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 gap-2">
            <Box className="w-12 h-12 stroke-1" />
            <p>Enter a prompt and click "Generate & Simulate" to view the 3D model.</p>
          </div>
        )}
      </div>
    </div>
  );
}
