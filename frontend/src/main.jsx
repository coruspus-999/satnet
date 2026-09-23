import React, {useEffect, useMemo, useRef, useState} from "react";
import {createRoot} from "react-dom/client";
import {Canvas, useFrame} from "@react-three/fiber";
import {OrbitControls, Stars, Line, Html} from "@react-three/drei";
import {Activity, AlertTriangle, ArrowDownUp, Database, Download, Gauge, Globe2, Pause, Play, Radio, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Upload, X} from "lucide-react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const DEMO_TLE = `ISS (ZARYA)
1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999
2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003`;

function orbitPoints(radius, tilt, phase = 0, count = 160) {
  return Array.from({length: count + 1}, (_, i) => {
    const a = phase + i / count * Math.PI * 2;
    return [radius * Math.cos(a), Math.sin(tilt) * radius * Math.sin(a), Math.cos(tilt) * radius * Math.sin(a)];
  });
}

// Map real TEME position (km, geocentric) into the scene. LEO radii are
// 6600-7400 km; the scene Earth has radius 3, so scale by EARTH_UNITS/KM.
const EARTH_RADIUS_KM = 6371;
const EARTH_UNITS = 3;
const KM_PER_UNIT = EARTH_RADIUS_KM / EARTH_UNITS;

function temeToScene(positionKm, scaleFactor = 1) {
  if (!positionKm || positionKm.length !== 3) return null;
  const r = Math.hypot(positionKm[0], positionKm[1], positionKm[2]);
  if (!Number.isFinite(r) || r < 1) return null;
  // Compress radial distance so LEO-to-GEO orbits all fit the scene, while
  // preserving direction: u = r_km -> units = 3 * (r / r_ref)^0.4.
  const units = EARTH_UNITS * Math.pow(r / EARTH_RADIUS_KM, 0.4) * scaleFactor;
  return [
    (positionKm[0] / r) * units,
    (positionKm[2] / r) * units,
    (positionKm[1] / r) * units,
  ];
}

function trajectoryLinePoints(states, every = 4) {
  const points = [];
  for (let i = 0; i < states.length; i += every) {
    const p = temeToScene(states[i].position_km);
    if (p) points.push(p);
  }
  const last = temeToScene(states[states.length - 1]?.position_km);
  if (last) points.push(last);
  return points.length > 1 ? points : null;
}

function Earth() {
  return <group>
    <mesh><sphereGeometry args={[3, 96, 96]}/><meshStandardMaterial color="#071a2b" metalness={0.5} roughness={0.68}/></mesh>
    <mesh><sphereGeometry args={[3.035, 64, 64]}/><meshBasicMaterial color="#27749a" wireframe transparent opacity={0.17}/></mesh>
    <mesh><sphereGeometry args={[3.12, 64, 64]}/><meshBasicMaterial color="#35d7ff" transparent opacity={0.055}/></mesh>
  </group>;
}

function SatelliteMarker({position, label, risk, selected, onClick}) {
  return <group position={position} onClick={(e) => {e.stopPropagation(); onClick?.();}}>
    <mesh><sphereGeometry args={[selected ? .09 : .065, 18, 18]}/><meshBasicMaterial color={risk ? "#ff4f73" : "#65e6ff"}/></mesh>
    <mesh><sphereGeometry args={[selected ? .19 : .13, 18, 18]}/><meshBasicMaterial color={risk ? "#ff4f73" : "#65e6ff"} transparent opacity={.12}/></mesh>
    <Html distanceFactor={8}><div className={`sat-tag ${risk ? "danger" : ""} ${selected ? "selected" : ""}`}>{label}</div></Html>
  </group>;
}

// Demo orbits shown only before any simulation data arrives (clearly
// labeled in the scene header as decorative).
const DEMO_ORBITS = [
  { radius: 4.2, tilt: 0.62, phase: 1.1 },
  { radius: 4.75, tilt: -0.44, phase: 4.1 },
  { radius: 5.35, tilt: 0.28, phase: 2.4 },
];

function SpaceScene({
  trajectories,
  conjunctions,
  selected,
  setSelected,
  playTime,
}) {
  const group = useRef();

  useFrame((_, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * 0.018;
    }
  });

  const live = trajectories?.length ? trajectories : [];
  const riskIds = new Set(
    (conjunctions || []).flatMap((c) => [String(c.satellite_a), String(c.satellite_b)])
  );

  return (
    <>
      <color attach="background" args={["#02060b"]} />

      <ambientLight intensity={0.35} />

      <pointLight position={[5, 4, 5]} intensity={18} color="#61dfff" />
      <pointLight position={[-5, -2, -4]} intensity={8} color="#7b5cff" />

      <Stars
        radius={90}
        depth={45}
        count={5000}
        factor={2.1}
        saturation={0}
        fade
        speed={0.12}
      />

      <group ref={group}>
        <Earth />

        {live.length === 0 &&
          DEMO_ORBITS.map((orbit, index) => (
            <Line
              key={`demo-${index}`}
              points={orbitPoints(orbit.radius, orbit.tilt, orbit.phase)}
              color="#3fd8ff"
              transparent
              opacity={0.16}
              lineWidth={1}
            />
          ))}

        {live.map((trajectory, index) => {
          const satellite = trajectory.satellite || {};
          const satelliteId = String(satellite.norad_id ?? index);
          const satelliteName = satellite.name || `SAT-${satelliteId}`;
          const hasRisk = riskIds.has(satelliteId);
          const linePoints = trajectoryLinePoints(trajectory.states || []);
          if (!linePoints) return null;

          // Animate the marker along the real TEME trajectory.
          const stateCount = trajectory.states.length;
          const animIndex = Math.floor(
            ((playTime * 0.00018 * (index + 1)) % 1) * (stateCount - 1)
          );
          const markerPos =
            temeToScene(trajectory.states[animIndex]?.position_km) || linePoints[0];

          return (
            <group key={`satellite-${satelliteId}`}>
              <Line
                points={linePoints}
                color={hasRisk ? "#ff4f73" : "#42d9ff"}
                transparent
                opacity={hasRisk ? 0.6 : 0.2}
                lineWidth={hasRisk ? 1.8 : 1}
              />
              <SatelliteMarker
                position={markerPos}
                label={`${satelliteName} · ${satelliteId}`}
                risk={hasRisk}
                selected={selected === satelliteName}
                onClick={() => setSelected(satelliteName)}
              />
            </group>
          );
        })}
      </group>

      <OrbitControls
        enableDamping
        dampingFactor={0.06}
        minDistance={5}
        maxDistance={18}
      />
    </>
  );
}


function SpaceView({
  trajectories,
  conjunctions,
  selected,
  setSelected,
  playTime,
}) {
  return (
    <Canvas
      camera={{
        position: [8, 5.5, 8],
        fov: 45,
      }}
      dpr={[1, 1.7]}
      gl={{
        antialias: true,
        powerPreference: "high-performance",
      }}
    >
      <SpaceScene
        trajectories={trajectories}
        conjunctions={conjunctions}
        selected={selected}
        setSelected={setSelected}
        playTime={playTime}
      />
    </Canvas>
  );
}
function Stat({icon:Icon,label,value,sub}) {return <div className="stat"><div className="stat-icon"><Icon size={16}/></div><div><span>{label}</span><b>{value}</b>{sub&&<small>{sub}</small>}</div></div>}
function fmtTime(iso){return iso?new Date(iso).toLocaleString():"—"}
function riskOrder(x){return {RED:0,YELLOW:1,GREEN:2}[x]??9}

function App(){
  const [tle,setTle]=useState(DEMO_TLE), [radius,setRadius]=useState(25), [step,setStep]=useState(60), [hours,setHours]=useState(2);
  const [status,setStatus]=useState("READY"), [result,setResult]=useState(null), [trajectories,setTrajectories]=useState([]), [error,setError]=useState("");
  const [query,setQuery]=useState(""), [riskFilter,setRiskFilter]=useState("ALL"), [sort,setSort]=useState("risk"), [selected,setSelected]=useState(null);
  const [playing,setPlaying]=useState(false), [playTime,setPlayTime]=useState(0), [remoteGroup,setRemoteGroup]=useState("stations"), [loadingTle,setLoadingTle]=useState(false);
  const fileRef=useRef();
  useEffect(()=>{if(!playing)return;const id=setInterval(()=>setPlayTime(t=>t+1000),80);return()=>clearInterval(id)},[playing]);

  async function run(){
    setStatus("RUNNING"); setError(""); setResult(null); setTrajectories([]); setPlayTime(0);
    const start=new Date(Date.now()+60000), end=new Date(start.getTime()+Number(hours)*3600000);
    try{const r=await fetch(`${API}/api/simulations`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tle_text:tle,start_time:start.toISOString(),end_time:end.toISOString(),time_step_seconds:Number(step),safety_radius_km:Number(radius),ml_enabled:false})});
      const d=await r.json(); if(!r.ok)throw Error(d.detail||"Simulation failed"); setResult(d); setStatus("COMPLETED");
      const tr=await fetch(`${API}/api/simulations/${d.simulation_id}/trajectories`); if(tr.ok){const td=await tr.json();setTrajectories(td.trajectories||[])}
    }catch(e){setError(e.message);setStatus("ERROR")}
  }
  async function fetchRemote(){setLoadingTle(true);setError("");try{const r=await fetch(`${API}/api/tle/fetch`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({group:remoteGroup})});const d=await r.json();if(!r.ok)throw Error(d.detail||"TLE fetch failed");setTle(d.records.map(x=>`${x.name}\n${x.line1}\n${x.line2}`).join("\n"));}catch(e){setError(e.message)}finally{setLoadingTle(false)}}
  async function importFile(e){const f=e.target.files?.[0];if(f)setTle(await f.text())}
  const rows=useMemo(()=>{
    // Conjunction events carry NORAD ids; resolve display names from trajectories.
    const nameById = {};
    trajectories.forEach(t=>{ if(t.satellite) nameById[String(t.satellite.norad_id)]=t.satellite.name||`SAT-${t.satellite.norad_id}`; });
    const pairLabel = (id)=>nameById[String(id)]||`NORAD ${id}`;
    let a=[...(result?.conjunctions||[])].map(x=>({...x, _pair: `${pairLabel(x.satellite_a)} ↔ ${pairLabel(x.satellite_b)}`}))
      .filter(x=>x._pair.toLowerCase().includes(query.toLowerCase()));
    if(riskFilter!=="ALL")a=a.filter(x=>x.risk_level===riskFilter);
    a.sort((x,y)=>sort==="distance"?x.miss_distance_km-y.miss_distance_km:sort==="tca"?new Date(x.tca)-new Date(y.tca):riskOrder(x.risk_level)-riskOrder(y.risk_level)); return a;
  },[result,query,riskFilter,sort,trajectories]);
  const activeRisk=rows.some(x=>x.risk_level==="RED")?"RED":rows.some(x=>x.risk_level==="YELLOW")?"YELLOW":"GREEN";
  return <div className="app">
    <header className="topbar"><div className="brand"><div className="brand-mark"><Radio size={20}/></div><div><strong>SATNET</strong><small>ORBITAL RISK COMMAND</small></div></div><div className="top-right"><span className="pulse"/> SYSTEM ONLINE <i/> TEME / UTC <i/> V1.1</div></header>
    <main>
      <section className="hero"><div className="hero-copy"><div className="eyebrow"><ShieldCheck size={13}/> CLOSE APPROACH INTELLIGENCE</div><h1>See the orbit.<br/><em>Understand the risk.</em></h1><p>High-fidelity orbital analysis with SGP4 propagation, spatial screening and a WebGL command view designed for fast, explainable conjunction assessment.</p><div className="stats"><Stat icon={Database} label="SATELLITES" value={result?.satellite_count??"—"}/><Stat icon={Gauge} label="CANDIDATES" value={result?.candidate_pairs??"—"}/><Stat icon={AlertTriangle} label="EVENTS" value={result?.conjunction_count??"—"}/><Stat icon={Activity} label="PROCESS" value={result?`${result.processing_time_seconds.toFixed(2)}s`:"—"} sub={result?.ml_fallback_used?"SGP4 FALLBACK":"BASELINE SGP4"}/></div></div>
        <div className="scene"><div className="scene-head"><span><span className="pulse"/> {trajectories.length ? "TEME TRAJECTORIES · KM · UTC" : "DEMO ORBITS · RUN ANALYSIS FOR REAL DATA"}</span><span>ROTATE · ZOOM · SELECT</span></div><SpaceView trajectories={trajectories} conjunctions={result?.conjunctions||[]} selected={selected} setSelected={setSelected} playTime={playTime}/></div></section>
      <section className="workspace"><aside className="control panel"><div className="panel-kicker"><SlidersHorizontal size={13}/> SIMULATION CONTROL</div>
        <div className="field"><label>TLE SOURCE</label><div className="source-row"><select value={remoteGroup} onChange={e=>setRemoteGroup(e.target.value)}><option value="stations">Stations</option><option value="starlink">Starlink</option><option value="active">Active</option><option value="weather">Weather</option><option value="gps-ops">GPS Operational</option></select><button className="ghost" onClick={fetchRemote} disabled={loadingTle}>{loadingTle?<RefreshCw className="spin" size={14}/>:<Globe2 size={14}/>} FETCH</button></div></div>
        <div className="field"><label>TLE DATASET</label><textarea value={tle} onChange={e=>setTle(e.target.value)} spellCheck="false"/><input ref={fileRef} hidden type="file" accept=".tle,.txt" onChange={importFile}/><button className="ghost wide" onClick={()=>fileRef.current?.click()}><Upload size={14}/> IMPORT TLE FILE</button></div>
        <div className="grid2"><div className="field"><label>TIME STEP / SEC</label><input type="number" min="1" value={step} onChange={e=>setStep(e.target.value)}/></div><div className="field"><label>WINDOW / HOURS</label><input type="number" min="1" max="48" value={hours} onChange={e=>setHours(e.target.value)}/></div></div>
        <div className="field"><label>SCREENING RADIUS / KM <b>{radius}</b></label><input className="range" type="range" min="1" max="100" value={radius} onChange={e=>setRadius(e.target.value)}/></div>
        <button className="run" onClick={run} disabled={status==="RUNNING"}>{status==="RUNNING"?<RefreshCw className="spin" size={16}/>:<Play size={16} fill="currentColor"/>}{status==="RUNNING"?" RUNNING ANALYSIS":" RUN ANALYSIS"}</button>
        <div className={`status ${status.toLowerCase()}`}><Activity size={14}/><span>{status}</span>{result&&<small>{result.satellite_count} sats · {result.duration_seconds/3600} h</small>}</div>
        {result?.warning&&<div className="warning"><AlertTriangle size={14}/>{result.warning}</div>}{error&&<div className="error"><X size={14}/>{error}</div>}
      </aside>
      <section className="panel intelligence"><div className="table-head"><div><div className="panel-kicker">RISK & CONJUNCTION INTELLIGENCE</div><h2>Event matrix</h2></div><div className="table-tools"><div className="search"><Search size={14}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search satellites"/></div><select value={riskFilter} onChange={e=>setRiskFilter(e.target.value)}><option>ALL</option><option>RED</option><option>YELLOW</option><option>GREEN</option></select><select value={sort} onChange={e=>setSort(e.target.value)}><option value="risk">Risk</option><option value="distance">Distance</option><option value="tca">TCA</option></select></div></div>
        <div className="risk-strip"><span className={`risk-dot ${activeRisk.toLowerCase()}`}/><b>{result?`${result.conjunction_count} detected conjunction${result.conjunction_count===1?"":"s"}`:"Awaiting simulation"}</b><span>Pc is shown as N/A until valid covariance + encounter-plane data are supplied.</span></div>
        <div className="table-wrap"><table><thead><tr><th>PAIR <ArrowDownUp size={11}/></th><th>TCA</th><th>MISS DISTANCE</th><th>RELATIVE V</th><th>Pc</th><th>RISK</th></tr></thead><tbody>{rows.length?rows.map((r,i)=><tr key={i} className={r.risk_level.toLowerCase()}><td><strong>{r._pair}</strong></td><td>{fmtTime(r.tca)}</td><td>{Number(r.miss_distance_km).toFixed(3)} km</td><td>{Number(r.relative_velocity_km_s).toFixed(3)} km/s</td><td className="na">{r.pc==null?"N/A":Number(r.pc).toExponential(2)}</td><td><span className={`risk-pill ${r.risk_level.toLowerCase()}`}>{r.risk_level}</span></td></tr>):<tr><td colSpan="6" className="empty"><ShieldCheck size={22}/><b>No conjunction events</b><span>Run an analysis or adjust the screening radius.</span></td></tr>}</tbody></table></div>
        {result&&<div className="result-foot"><span>Simulation <b>{result.simulation_id.slice(0,8)}</b> · {result.processing_time_seconds.toFixed(3)} sec</span><div><a href={`${API}/api/reports/${result.simulation_id}/csv`}><Download size={13}/> CSV</a><a href={`${API}/api/reports/${result.simulation_id}/pdf`}><Download size={13}/> PDF</a></div></div>}
      </section></section>
      <section className="playback panel"><div><div className="panel-kicker">MISSION TIMELINE</div><b>{playing?"PLAYBACK ACTIVE":"READY FOR PLAYBACK"}</b><span> · {selected||"No satellite selected"}</span></div><div className="play-controls"><button onClick={()=>setPlaying(!playing)}>{playing?<Pause size={14}/>:<Play size={14}/>}</button><input type="range" min="0" max="100000" value={playTime%100000} onChange={e=>setPlayTime(+e.target.value)}/><span>T+ {(playTime/1000).toFixed(0)}s</span></div></section>
    </main><footer><span>SATNET 1.1</span><span>SGP4 · cKDTree · FASTAPI · WEBGL</span><span>ANALYSIS ONLY · NO AUTONOMOUS CONTROL</span></footer>
  </div>
}
createRoot(document.getElementById("root")).render(<App/>);
