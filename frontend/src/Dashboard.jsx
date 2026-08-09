import React, { useState } from 'react';
import { Canvas, useLoader } from '@react-three/fiber';
import { OrbitControls, Stage } from '@react-three/drei';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import { Play, RotateCcw, AlertCircle, CheckCircle, Cpu } from 'lucide-react';
import axios from 'axios';

// 3D Model Renderer utilizing react-three-fiber
// 3D Model Renderer utilizing standard Three.js STLLoader
function ModelViewer({ stlUrl }) {
  if (!stlUrl) return null;
  const geometry = useLoader(STLLoader, stlUrl);
  
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color="#64748b" roughness={0.4} metalness={0.2} />
    </mesh>
  );
}
export default function Dashboard() {
  const [prompt, setPrompt] = useState('Design a lightweight drone arm bracket');
  const [loadForce, setLoadForce] = useState(100);
  const [material, setMaterial] = useState('aluminum');
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState([]);
  const [stlUrl, setStlUrl] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, processing, success, failed

  const handleRunSimulation = async () => {
    setLoading(true);
    setStatus('processing');
    setLogs([`Sending constraints to Render backend optimization loop...`]);
    setStlUrl(null);

    try {
      // Points to your FastAPI service deployed on Render
      const response = await axios.post('https://simpro-xilm.onrender.com/api/simulate', {
        prompt,
        load_force: Number(loadForce),
        material
      });

      const { success, iterationLogs, modelFileUrl, msg } = response.data;
      
      setLogs(iterationLogs || [msg]);
      
      if (success) {
        setStatus('success');
        setStlUrl(modelFileUrl); 
      } else {
        setStatus('failed');
      }
    } catch (error) {
      setStatus('failed');
      setLogs((prev) => [...prev, `Error: Failed to connect to simulation engine. ${error.message}`]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* LEFT: Engineering Control & Agent Logs */}
      <div className="w-1/3 border-r border-slate-800 bg-slate-900/50 p-6 flex flex-col justify-between overflow-y-auto">
        <div>
          <div className="flex items-center gap-2 mb-6">
            <Cpu className="w-6 h-6 text-indigo-400" />
            <h1 className="text-xl font-bold tracking-tight">PulseSim AI Engine</h1>
          </div>

          {/* Configuration Forms */}
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Design Prompt</label>
              <textarea 
                value={prompt} 
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-500 transition-colors resize-none h-20"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Target Load (N)</label>
                <input 
                  type="number" 
                  value={loadForce} 
                  onChange={(e) => setLoadForce(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Material Type</label>
                <select 
                  value={material} 
                  onChange={(e) => setMaterial(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
                >
                  <option value="aluminum">Aluminum 6061</option>
                  <option value="titanium">Titanium Ti-6Al-4V</option>
                  <option value="pla">PLA Plastic (3D Printed)</option>
                </select>
              </div>
            </div>

            <button
              onClick={handleRunSimulation}
              disabled={loading}
              className="w-full mt-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              {loading ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {loading ? 'Executing Loop passes...' : 'Generate & Simulate'}
            </button>
          </div>
        </div>

        {/* Real-time Iteration Terminal Output */}
        <div className="mt-6 flex-1 flex flex-col min-h-[250px]">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Agent Optimization Loop Logs</h2>
          <div className="flex-1 w-full bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-xs overflow-y-auto space-y-2">
            {logs.length === 0 && <span className="text-slate-600">Awaiting engineering parameters...</span>}
            {logs.map((log, index) => (
              <div key={index} className="text-emerald-400 border-l border-emerald-500 pl-2 py-0.5">
                {log}
              </div>
            ))}
            {status === 'processing' && <div className="text-indigo-400 animate-pulse">Running mechanical finite element solver...</div>}
          </div>
        </div>
      </div>

      {/* RIGHT: Live Interactive 3D Physics Viewport */}
      <div className="w-2/3 h-full relative bg-slate-950">
        {/* State Banner HUD Overlay */}
        <div className="absolute top-6 left-6 z-10 flex items-center gap-3 bg-slate-900/90 backdrop-blur border border-slate-800 px-4 py-2.5 rounded-xl">
          {status === 'idle' && <div className="w-2 h-2 rounded-full bg-slate-500" />}
          {status === 'processing' && <div className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />}
          {status === 'success' && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          {status === 'failed' && <AlertCircle className="w-4 h-4 text-rose-500" />}
          <span className="text-xs font-medium uppercase tracking-wider">
            Viewport: {status === 'idle' ? 'Ready' : status === 'processing' ? 'AI Auto-Correcting Structure' : status === 'success' ? 'Validated Mesh Passed Simulation' : 'Structural Constraints Failed'}
          </span>
        </div>

        {/* Three.js Render Environment */}
        {stlUrl ? (
          <Canvas camera={{ position: [0, 0, 15], fov: 45 }}>
            <ambientLight intensity={0.4} />
            <pointLight position={[10, 10, 10]} intensity={1.5} />
            <directionalLight position={[-10, -10, -10]} intensity={0.5} />
            <React.Suspense fallback={null}>
              <Stage intensity={0.6} environment="city" adjustCamera={true}>
                <ModelViewer stlUrl={stlUrl} />
              </Stage>
            </React.Suspense>
            <OrbitControls makeDefault enableZoom={true} />
          </Canvas>
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-slate-500 border border-dashed border-slate-800 m-4 rounded-2xl bg-slate-900/10">
            <span className="text-sm font-medium">3D Viewport Idle</span>
            <span className="text-xs text-slate-600 mt-1">Specify parameters to start generative loop processing.</span>
          </div>
        )}
      </div>
    </div>
  );
}
