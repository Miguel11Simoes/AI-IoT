import * as THREE from "/twin3d/vendor/three/build/three.module.js";
import { OrbitControls } from "/twin3d/vendor/three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "/twin3d/vendor/three/examples/jsm/loaders/GLTFLoader.js";
import { EffectComposer } from "/twin3d/vendor/three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "/twin3d/vendor/three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "/twin3d/vendor/three/examples/jsm/postprocessing/UnrealBloomPass.js";

const RACK_COUNT = 8;
const COLS = 4;
const DEFAULT_WS_PORT = 8000;
const TEMP_MIN = 30;
const TEMP_MAX = 85;
const INITIAL_VIEW_LEFT_BIAS_X = 4.0;
const INITIAL_VIEW_DIAGONAL_DEG = 10;

const wsConfig = {
  host: window.location.hostname || "localhost",
  port: DEFAULT_WS_PORT,
  enabled: true,
};

const canvas = document.getElementById("twin-canvas");
const connectionPill = document.getElementById("connection-pill");
const rackTable = document.getElementById("rack-table");

const kpiHero = document.getElementById("kpi-hero");
const kpiHeroSub = document.getElementById("kpi-hero-sub");
const kpiHeroSparklineLine = document.getElementById("kpi-hero-sparkline-line");
const kpiAvg = document.getElementById("kpi-avg");
const kpiMax = document.getElementById("kpi-max");
const kpiCritical = document.getElementById("kpi-critical");
const kpiPower = document.getElementById("kpi-power");
const kpiPowerDelta = document.getElementById("kpi-power-delta");
const kpiSourceReal = document.getElementById("kpi-source-real");
const kpiSourceStale = document.getElementById("kpi-source-stale");
const kpiSourceSim = document.getElementById("kpi-source-sim");
const kpiHeaterEq = document.getElementById("kpi-heater-eq");
const kpiHeaterTarget = document.getElementById("kpi-heater-target");

const kpiAiStatus = document.getElementById("kpi-ai-status");
const kpiAiConfidence = document.getElementById("kpi-ai-confidence");
const kpiTrend = document.getElementById("kpi-trend");
const kpiPredict5 = document.getElementById("kpi-predict5");
const kpiAiRisk = document.getElementById("kpi-ai-risk");
const kpiCduStatus = document.getElementById("kpi-cdu-status");
const kpiSupplyA = document.getElementById("kpi-supply-a");
const kpiSupplyB = document.getElementById("kpi-supply-b");
const kpiCduFans = document.getElementById("kpi-cdu-fans");
const kpiCduPeltiers = document.getElementById("kpi-cdu-peltiers");

const HERO_SPARKLINE_WINDOW_MS = 60_000;
const HERO_SPARKLINE_POINTS = 36;
const heroSparklineHistory = [];

function fatal(message) {
  console.error(message);
  connectionPill.classList.remove("online");
  connectionPill.classList.add("offline");
  connectionPill.textContent = message;
}

function clamp01(value) {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function tempRatio(temp) {
  return clamp01((temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN));
}

function formatSigned(value, digits = 2) {
  const num = Number(value || 0);
  const sign = num >= 0 ? "+" : "";
  return `${sign}${num.toFixed(digits)}`;
}

function toStatusLabel(status) {
  if (status === "critical") return "Critical";
  if (status === "warning") return "Warning";
  return "Normal";
}

function toSourceLabel(sourceStatus) {
  if (sourceStatus === "real") return "Real";
  if (sourceStatus === "stale") return "Stale";
  return "Simulated";
}

function formatTempValue(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(1)}\u00B0C` : "--";
}

function formatPowerValue(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(2)} W` : "--";
}

function pushHeroSparklinePoint(temp) {
  const now = Date.now();
  heroSparklineHistory.push({ ts: now, value: Number(temp) || 0 });
  while (heroSparklineHistory.length && now - heroSparklineHistory[0].ts > HERO_SPARKLINE_WINDOW_MS) {
    heroSparklineHistory.shift();
  }
}

function renderHeroSparkline() {
  if (!kpiHeroSparklineLine) return;
  if (heroSparklineHistory.length < 2) {
    kpiHeroSparklineLine.setAttribute("points", "");
    return;
  }

  const recent = heroSparklineHistory.slice(-HERO_SPARKLINE_POINTS);
  const minVal = Math.min(...recent.map((p) => p.value));
  const maxVal = Math.max(...recent.map((p) => p.value));
  const span = Math.max(0.2, maxVal - minVal);
  const width = 120;
  const height = 34;
  const xStep = width / Math.max(1, recent.length - 1);

  const points = recent
    .map((point, idx) => {
      const x = idx * xStep;
      const yNorm = (point.value - minVal) / span;
      const y = height - 2 - yNorm * (height - 8);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  kpiHeroSparklineLine.setAttribute("points", points);
}

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
} catch (err) {
  fatal("WebGL unavailable");
  throw err;
}

renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.96;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x101b2a, 0.02);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 120);
camera.position.set(INITIAL_VIEW_LEFT_BIAS_X, 7.2, 13.8);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.045;
controls.target.set(INITIAL_VIEW_LEFT_BIAS_X, 1.3, 0);
controls.minDistance = 6;
controls.maxDistance = 28;
controls.maxPolarAngle = 1.45;

let composer = null;
let bloomPass = null;
try {
  composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 0.28, 0.58, 0.26);
  composer.addPass(bloomPass);
} catch (err) {
  console.warn("Bloom disabled:", err);
  composer = null;
  bloomPass = null;
}

const hemi = new THREE.HemisphereLight(0x8bb9e8, 0x162333, 0.46);
scene.add(hemi);

const key = new THREE.DirectionalLight(0xe8f4ff, 0.8);
key.position.set(7, 12, 5);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.near = 0.5;
key.shadow.camera.far = 48;
scene.add(key);

const spot = new THREE.SpotLight(0xaed8ff, 0.7, 42, Math.PI * 0.28, 0.42, 1.6);
spot.position.set(-8, 13, -6);
spot.target.position.set(0, 0.7, 0);
spot.castShadow = true;
scene.add(spot);
scene.add(spot.target);

const rim = new THREE.DirectionalLight(0x2e8bcf, 0.34);
rim.position.set(-10, 5, -8);
scene.add(rim);

const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(44, 32),
  new THREE.MeshStandardMaterial({ color: 0x101926, metalness: 0.34, roughness: 0.72 })
);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

const floorSheen = new THREE.Mesh(
  new THREE.PlaneGeometry(44, 32),
  new THREE.MeshPhysicalMaterial({
    color: 0x1a2c42,
    metalness: 0.72,
    roughness: 0.28,
    clearcoat: 1.0,
    clearcoatRoughness: 0.18,
    transparent: true,
    opacity: 0.13,
  })
);
floorSheen.rotation.x = -Math.PI / 2;
floorSheen.position.y = 0.01;
scene.add(floorSheen);

const grid = new THREE.GridHelper(40, 40, 0x1e3e4e, 0x153141);
grid.position.y = 0.02;
scene.add(grid);

const rackRoot = new THREE.Group();
rackRoot.position.x = -0.9;
scene.add(rackRoot);

let hoveredRackId = -1;
let criticalRackLabel = "";
let racksLoaded = false;

const rackSlots = [];
for (let i = 0; i < RACK_COUNT; i += 1) {
  rackSlots.push({
    id: i,
    group: null,
    heatMeshes: [],
    haloLight: null,
    criticalMarker: null,
    targetHot: 34,
    targetLiquid: 29,
    currentHot: 34,
    currentLiquid: 29,
    targetAnomaly: false,
    anomaly: false,
    fanPwm: 0,
    mode: "pending",
    status: "normal",
    isReal: false,
    isCritical: false,
    label: `R${String(i + 1).padStart(2, "0")}`,
    targetColor: new THREE.Color(0x4aa7ff),
    currentColor: new THREE.Color(0x4aa7ff),
    targetIntensity: 0.9,
    currentIntensity: 0.9,
    currentScale: 1,
  });
}

function thermalGradient(temp) {
  const t = tempRatio(temp);
  const color = new THREE.Color();
  if (t < 0.33) {
    color.setRGB(0.24 - t * 0.12, 0.55 + t * 0.82, 1.0 - t * 1.15);
  } else if (t < 0.66) {
    const p = (t - 0.33) / 0.33;
    color.setRGB(0.2 + p * 0.8, 0.9 - p * 0.4, 0.15 + p * 0.05);
  } else {
    const p = (t - 0.66) / 0.34;
    color.setRGB(1.0, 0.5 - p * 0.3, 0.2 - p * 0.1);
  }
  return color;
}

function cloneRackModel(template, idx) {
  const rack = template.clone(true);
  const row = Math.floor(idx / COLS);
  const col = idx % COLS;
  const spacingX = 2.9;
  const spacingZ = 3.6;
  rack.position.set((col - (COLS - 1) / 2) * spacingX, 0, (row - 0.5) * spacingZ);
  rack.rotation.y = row % 2 === 0 ? 0 : Math.PI;

  const candidateHeatMeshes = [];
  const allMeshes = [];
  const meshStats = [];

  rack.traverse((obj) => {
    if (!obj.isMesh) return;
    allMeshes.push(obj);
    obj.castShadow = true;
    obj.receiveShadow = true;

    if (Array.isArray(obj.material)) {
      obj.material = obj.material.map((m) => m.clone());
    } else if (obj.material) {
      obj.material = obj.material.clone();
    }

    const lname = (obj.name || "").toLowerCase();
    const looksInner =
      /(server|slot|bay|unit|blade|drawer|front|panel|chassis|module|mesh)/.test(lname) &&
      !/(frame|outer|shell|rack|cage|back|side|base|stand|wheel)/.test(lname);

    let centerZ = 0;
    if (obj.geometry) {
      if (!obj.geometry.boundingBox) {
        obj.geometry.computeBoundingBox();
      }
      if (obj.geometry.boundingBox) {
        const bbox = obj.geometry.boundingBox;
        const c = new THREE.Vector3();
        const size = new THREE.Vector3();
        bbox.getCenter(c);
        bbox.getSize(size);
        centerZ = c.z;
        const volume = Math.max(0, size.x * size.y * size.z);
        meshStats.push({ mesh: obj, centerZ, volume });
      }
    }

    if (looksInner && centerZ >= -0.03) {
      candidateHeatMeshes.push(obj);
    }
  });

  let heatMeshes = candidateHeatMeshes;
  if (!heatMeshes.length) {
    const sortedFront = meshStats.slice().sort((a, b) => b.centerZ - a.centerZ);
    const frontTake = Math.max(1, Math.floor(sortedFront.length * 0.45));
    const frontCandidates = sortedFront.slice(0, frontTake);
    const largest = meshStats.slice().sort((a, b) => b.volume - a.volume)[0]?.mesh ?? null;
    heatMeshes = frontCandidates.map((item) => item.mesh).filter((mesh) => mesh !== largest);
    if (!heatMeshes.length && frontCandidates.length) {
      heatMeshes = frontCandidates.map((item) => item.mesh);
    }
  }
  if (!heatMeshes.length) {
    heatMeshes = allMeshes;
  }

  const haloLight = new THREE.PointLight(0x4aa7ff, 0.0, 3.2, 2.0);
  haloLight.position.set(0, 1.15, 0.35);
  rack.add(haloLight);

  const criticalMarker = new THREE.Mesh(
    new THREE.RingGeometry(0.36, 0.48, 40),
    new THREE.MeshBasicMaterial({
      color: 0xffb24c,
      transparent: true,
      opacity: 0.0,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  criticalMarker.rotation.x = -Math.PI / 2;
  criticalMarker.position.set(0, 2.32, 0);
  criticalMarker.visible = false;
  rack.add(criticalMarker);

  return { rack, heatMeshes, haloLight, criticalMarker };
}

function frameRacksInitialView() {
  const box = new THREE.Box3().setFromObject(rackRoot);
  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const target = center.clone();
  target.x += INITIAL_VIEW_LEFT_BIAS_X;
  target.y += size.y * 0.22;

  const halfFovY = THREE.MathUtils.degToRad(camera.fov * 0.5);
  const halfFovX = Math.atan(Math.tan(halfFovY) * camera.aspect);
  const distX = (size.x * 0.62) / Math.max(0.25, Math.tan(halfFovX));
  const distY = (size.y * 0.72) / Math.max(0.25, Math.tan(halfFovY));
  const distance = Math.max(distX, distY, size.z * 1.4) + 4.2;
  const diagonalRad = THREE.MathUtils.degToRad(INITIAL_VIEW_DIAGONAL_DEG);
  const camOffsetX = Math.sin(diagonalRad) * distance;
  const camOffsetZ = Math.cos(diagonalRad) * distance;

  const camY = target.y + size.y * 1.35 + 1.9;
  camera.position.set(target.x + camOffsetX, camY, target.z + camOffsetZ);
  controls.target.copy(target);
  controls.update();
}

function applyRackVisual(slot, dtSec, nowSec) {
  slot.currentHot += (slot.targetHot - slot.currentHot) * Math.min(1, dtSec * 2.4);
  slot.currentLiquid += (slot.targetLiquid - slot.currentLiquid) * Math.min(1, dtSec * 2.4);
  slot.anomaly = slot.targetAnomaly;

  slot.targetColor.copy(thermalGradient(slot.currentHot)).multiplyScalar(0.62);
  slot.currentColor.lerp(slot.targetColor, Math.min(1, dtSec * 3.4));

  const fan = THREE.MathUtils.clamp(slot.fanPwm / 255, 0, 1);
  const baseIntensity = 0.34 + fan * 0.38;
  const anomalyPulse = slot.anomaly ? 0.24 + Math.sin(nowSec * 6.0 + slot.id) * 0.08 : 0.0;
  const criticalPulse = slot.isCritical ? 0.12 + Math.sin(nowSec * 4.6 + slot.id) * 0.06 : 0.0;
  const hoverBoost = slot.id === hoveredRackId ? 0.12 : 0.0;
  slot.targetIntensity = baseIntensity + anomalyPulse + hoverBoost;
  slot.targetIntensity += criticalPulse;
  slot.currentIntensity += (slot.targetIntensity - slot.currentIntensity) * Math.min(1, dtSec * 4.5);

  slot.heatMeshes.forEach((mesh) => {
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    mats.forEach((mat) => {
      if (!mat || !("emissive" in mat)) return;
      mat.emissive.copy(slot.currentColor);
      mat.emissiveIntensity = slot.currentIntensity;
    });
  });

  if (slot.haloLight) {
    slot.haloLight.color.copy(slot.currentColor);
    slot.haloLight.intensity = 0.05 + slot.currentIntensity * 0.18;
  }

  if (slot.group) {
    slot.group.position.y = slot.anomaly ? 0.03 + Math.sin(nowSec * 4.8 + slot.id) * 0.012 : 0;
    const targetScale = slot.id === hoveredRackId ? 1.025 : 1.0;
    slot.currentScale += (targetScale - slot.currentScale) * Math.min(1, dtSec * 7.5);
    slot.group.scale.setScalar(slot.currentScale);
  }

  if (slot.criticalMarker) {
    slot.criticalMarker.visible = slot.isCritical;
    if (slot.isCritical) {
      const mat = slot.criticalMarker.material;
      mat.opacity = 0.42 + Math.sin(nowSec * 4.8 + slot.id) * 0.16;
      mat.color.copy(slot.currentColor).lerp(new THREE.Color(0xffb24c), 0.35);
      const s = 1.0 + Math.sin(nowSec * 3.6 + slot.id) * 0.06;
      slot.criticalMarker.scale.set(s, s, 1);
    }
  }
}

function compactMode(mode) {
  const text = String(mode || "").trim();
  if (!text) return "n/a";
  if (text === "cooperative") return "co-op";
  if (text === "synthetic_cooperative") return "synthetic";
  if (text === "anomaly_guard") return "guard";
  return text.replaceAll("_", " ");
}

function getVirtualClusterMetrics(payload) {
  const racks = Array.isArray(payload?.racks) ? payload.racks : [];
  const samples = racks
    .map((rack) => ({
      label: String(rack.label || ""),
      temp: Number(rack.temp_liquid ?? rack.temp_liquid_virtual ?? rack.temp_hot_virtual ?? rack.temp_hot),
    }))
    .filter((sample) => sample.label && Number.isFinite(sample.temp));

  if (!samples.length) {
    const g = payload?.global || {};
    return {
      avg: Number(g.avg_hot || 0),
      max: Number(g.max_hot || 0),
      criticalRack: String(g.critical_rack || ""),
      criticalTemp: Number(g.critical_temp || 0),
    };
  }

  let total = 0;
  let critical = samples[0];
  samples.forEach((sample) => {
    total += sample.temp;
    if (sample.temp > critical.temp) critical = sample;
  });

  return {
    avg: total / samples.length,
    max: critical.temp,
    criticalRack: critical.label,
    criticalTemp: critical.temp,
  };
}

function updatePanel(payload) {
  if (!payload || !payload.global || !payload.racks) return;
  const g = payload.global;
  const cdu = payload.cdu || {};
  const cluster = getVirtualClusterMetrics(payload);
  const avgHot = cluster.avg;
  const maxHot = cluster.max;
  const criticalTemp = cluster.criticalTemp;
  const totalPower = Number(g.total_cooling_power_kw ?? g.power_index_kw ?? 0);
  const powerDeltaPct = Number(g.power_delta_pct_1h ?? 0);
  const powerDeltaReady = Boolean(g.power_delta_ready);
  const trend = Number(g.trend_c_per_min || 0);
  const predict5 = Number(g.predicted_hot_5m || avgHot);
  const aiConfidence = Number(g.ai_confidence || 0);
  const anomalyRiskPct = Number(g.anomaly_risk_pct ?? 0);
  const aiStatus = String(g.ai_status || "nominal");
  const sourceReal = Number(g.active_nodes || 0);
  const sourceStale = Number(g.stale_nodes || 0);
  const sourceSim = Number(g.simulated_nodes || 0);
  const heaterEqCluster = Number(g.cluster_heater_equivalent_w || 0);
  const heaterEqTarget = Number(g.heater_equivalent_target_w || 0);

  kpiHero.textContent = `${avgHot.toFixed(1)}\u00B0C`;
  kpiHeroSub.textContent = `Trend: ${formatSigned(trend)}\u00B0C/min`;
  pushHeroSparklinePoint(avgHot);
  renderHeroSparkline();

  kpiAvg.textContent = `${avgHot.toFixed(2)}\u00B0C`;
  kpiMax.textContent = `${maxHot.toFixed(2)}\u00B0C`;
  kpiCritical.textContent = `${cluster.criticalRack} (${criticalTemp.toFixed(1)}\u00B0C)`;
  kpiPower.textContent = `${totalPower.toFixed(2)} kW`;
  if (kpiPowerDelta) {
    if (powerDeltaReady) {
      const arrow = powerDeltaPct >= 0 ? "\u2191" : "\u2193";
      kpiPowerDelta.textContent = `${arrow} ${Math.abs(powerDeltaPct).toFixed(1)}% vs last hour`;
    } else {
      kpiPowerDelta.textContent = "-- vs last hour";
    }
  }
  if (kpiSourceReal) kpiSourceReal.textContent = String(sourceReal);
  if (kpiSourceStale) kpiSourceStale.textContent = String(sourceStale);
  if (kpiSourceSim) kpiSourceSim.textContent = String(sourceSim);
  if (kpiHeaterEq) kpiHeaterEq.textContent = `${heaterEqCluster.toFixed(1)} W`;
  if (kpiHeaterTarget) kpiHeaterTarget.textContent = `target ${heaterEqTarget.toFixed(1)} W/rack`;

  kpiAiStatus.textContent = aiStatus.replaceAll("_", " ");
  kpiAiStatus.classList.remove("neutral", "nominal", "warning", "critical");
  if (aiStatus === "anomaly_detected") {
    kpiAiStatus.classList.add(g.anomaly_racks > 1 ? "critical" : "warning");
  } else {
    kpiAiStatus.classList.add("nominal");
  }

  kpiAiConfidence.textContent = `${(aiConfidence * 100).toFixed(1)} %`;
  kpiTrend.textContent = `${formatSigned(trend)}\u00B0C/min`;
  kpiPredict5.textContent = `${predict5.toFixed(1)}\u00B0C`;
  if (kpiAiRisk) {
    const riskPct = Math.max(0, Math.min(100, anomalyRiskPct));
    const riskLabel = riskPct >= 70 ? "High" : riskPct >= 35 ? "Medium" : "Low";
    kpiAiRisk.textContent = `${riskLabel} (${riskPct.toFixed(1)}%)`;
  }

  if (kpiSupplyA) {
    kpiSupplyA.textContent = `${Number(g.t_supply_A || cdu.t_supply_A || 0).toFixed(1)}\u00B0C`;
  }
  if (kpiSupplyB) {
    kpiSupplyB.textContent = `${Number(g.t_supply_B || cdu.t_supply_B || 0).toFixed(1)}\u00B0C`;
  }
  if (kpiCduFans) {
    const fanA = Number(g.fanA_pwm || cdu.fanA_pwm || 0);
    const fanB = Number(g.fanB_pwm || cdu.fanB_pwm || 0);
    kpiCduFans.textContent = `${fanA} / ${fanB}`;
  }
  if (kpiCduPeltiers) {
    const peltierA = Boolean(g.peltierA_on ?? cdu.peltierA_on);
    const peltierB = Boolean(g.peltierB_on ?? cdu.peltierB_on);
    kpiCduPeltiers.textContent = `${peltierA ? "ON" : "OFF"} / ${peltierB ? "ON" : "OFF"}`;
  }
  if (kpiCduStatus) {
    const online = Boolean(g.cdu_online || cdu.online);
    kpiCduStatus.textContent = online ? "online" : "fallback";
    kpiCduStatus.classList.remove("neutral", "nominal", "warning", "critical");
    kpiCduStatus.classList.add(online ? "nominal" : "warning");
  }

  rackTable.innerHTML = "";
  payload.racks.forEach((rack) => {
    const tr = document.createElement("tr");
    const status = rack.status || (rack.anomaly ? "critical" : "normal");
    const displayTempRaw = Number(rack.temp_hot);
    const virtualTempRaw = Number(rack.temp_liquid ?? rack.temp_liquid_virtual ?? rack.temp_hot_virtual ?? rack.temp_hot);
    const displayTemp = Number.isFinite(displayTempRaw) ? displayTempRaw : 0;
    const virtualTemp = Number.isFinite(virtualTempRaw) ? virtualTempRaw : displayTemp;
    const width = (tempRatio(virtualTemp) * 100).toFixed(1);
    const sourceStatus = String(rack.source_status || (rack.is_real ? "real" : "simulated"));
    const sourceBlend = Number(rack.source_blend || 0);
    const sourceMeta =
      sourceStatus === "stale"
        ? `${Math.round(sourceBlend * 100)}% blend`
        : sourceStatus === "real"
          ? "live telemetry"
          : "model fallback";
    const realTempLabel = formatTempValue(rack.temp_hot_real);
    const virtualTempLabel = formatTempValue(rack.temp_liquid ?? rack.temp_liquid_virtual);
    const heaterRealLabel = formatPowerValue(rack.heater_real_w);
    const heaterEqLabel = formatPowerValue(rack.heater_equivalent_w);
    const heaterScale = Number(rack.heater_scale_factor || 1);
    const coolingLabel = `F ${Number(rack.fan_pwm || 0)}`;

    if (rack.anomaly) tr.classList.add("alert");
    if (rack.is_real) tr.classList.add("real");
    if (Number(rack.rack_id) === hoveredRackId) tr.classList.add("hovered");

    tr.innerHTML = `
      <td>${rack.label}</td>
      <td>
        <div class="cell-stack tight">
          <span class="source-chip ${sourceStatus}"><span class="status-dot ${status}"></span>${toSourceLabel(sourceStatus)}</span>
          <span class="subtle-tag">${sourceMeta}</span>
        </div>
      </td>
      <td class="heat-cell">
        <div class="cell-stack">
          <div class="micro-line"><span>Real</span><strong>${realTempLabel}</strong></div>
          <div class="micro-line"><span>Virtual</span><strong>${virtualTempLabel}</strong></div>
        </div>
        <div class="temp-bar compact">
          <div class="temp-fill" style="width:${width}%"></div>
          <span class="temp-val">${displayTemp.toFixed(1)}\u00B0C -> ${virtualTemp.toFixed(1)}\u00B0C</span>
        </div>
      </td>
      <td>
        <div class="cell-stack tight">
          <div class="micro-line"><span>Real</span><strong>${heaterRealLabel}</strong></div>
          <div class="micro-line"><span>Eq</span><strong>${heaterEqLabel}</strong></div>
          <span class="subtle-tag">x${heaterScale.toFixed(2)}</span>
        </div>
      </td>
      <td>
        <div class="cell-stack tight">
          <div class="micro-line"><span>${coolingLabel}</span></div>
          <span class="subtle-tag">${toStatusLabel(status)}</span>
        </div>
      </td>
      <td><span class="mode-chip">${compactMode(rack.mode)}</span></td>
    `;

    tr.addEventListener("mouseenter", () => {
      hoveredRackId = Number(rack.rack_id);
    });
    tr.addEventListener("mouseleave", () => {
      hoveredRackId = -1;
    });

    rackTable.appendChild(tr);
  });
}

function handleTwinMessage(payload) {
  criticalRackLabel = getVirtualClusterMetrics(payload).criticalRack;
  updatePanel(payload);
  if (!Array.isArray(payload?.racks)) return;
  payload.racks.forEach((rack) => {
    const slot = rackSlots[rack.rack_id];
    if (!slot) return;
    slot.label = rack.label;
    slot.targetHot = Number(rack.temp_liquid ?? rack.temp_liquid_virtual ?? rack.temp_hot_virtual ?? rack.temp_hot);
    slot.targetLiquid = Number(rack.temp_liquid ?? rack.temp_liquid_virtual ?? rack.temp_hot);
    slot.targetAnomaly = Boolean(rack.anomaly);
    slot.fanPwm = Number(rack.fan_pwm || 0);
    slot.mode = rack.mode || "n/a";
    slot.status = rack.status || "normal";
    slot.isReal = String(rack.source_status || "") === "real";
    slot.isCritical = slot.label === criticalRackLabel;
  });
}

function setConnection(online) {
  connectionPill.classList.toggle("online", online);
  connectionPill.classList.toggle("offline", !online);
  connectionPill.textContent = online ? "WS connected" : "WS disconnected";
}

let socket = null;
let reconnectTimer = null;
let pollTimer = null;

async function pollTwinOnce() {
  try {
    const response = await fetch(`/api/twin?racks=${RACK_COUNT}`, { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    handleTwinMessage(payload);
  } catch (err) {
    console.warn("Polling /api/twin failed", err);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTwinOnce();
  pollTimer = window.setInterval(pollTwinOnce, 1000);
}

function stopPolling() {
  if (!pollTimer) return;
  window.clearInterval(pollTimer);
  pollTimer = null;
}

async function loadRuntimeConfig() {
  try {
    const response = await fetch("/api/config", { cache: "no-store" });
    if (!response.ok) return;
    const cfg = await response.json();
    wsConfig.port = Number(cfg.ws_port || DEFAULT_WS_PORT);
    wsConfig.enabled = Boolean(cfg.ws_enabled);
    if (typeof cfg.ws_host === "string" && cfg.ws_host.trim() && cfg.ws_host !== "0.0.0.0") {
      wsConfig.host = cfg.ws_host.trim();
    }
  } catch (err) {
    console.warn("Config endpoint unavailable, using defaults", err);
  }
}

function connectWebSocket() {
  if (!wsConfig.enabled) {
    setConnection(false);
    connectionPill.textContent = "WS disabled (polling)";
    startPolling();
    return;
  }
  if (socket) {
    socket.close();
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${wsConfig.host}:${wsConfig.port}`);

  socket.onopen = () => {
    setConnection(true);
    stopPolling();
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleTwinMessage(payload);
    } catch (err) {
      console.error("Invalid WS payload", err);
    }
  };

  socket.onclose = () => {
    setConnection(false);
    startPolling();
    reconnectTimer = window.setTimeout(connectWebSocket, 1200);
  };

  socket.onerror = (ev) => {
    console.error("WS error", ev);
    setConnection(false);
    startPolling();
  };
}

const loader = new GLTFLoader();
loader.load(
  "/rack/data_center_rack.glb",
  (gltf) => {
    const base = gltf.scene;
    const box = new THREE.Box3().setFromObject(base);
    const center = new THREE.Vector3();
    const size = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);

    base.position.sub(center);
    base.position.y += size.y * 0.5;

    const targetHeight = 2.2;
    const scale = targetHeight / Math.max(0.2, size.y);
    base.scale.setScalar(scale);

    rackSlots.forEach((slot, idx) => {
      const { rack, heatMeshes, haloLight, criticalMarker } = cloneRackModel(base, idx);
      slot.group = rack;
      slot.heatMeshes = heatMeshes;
      slot.haloLight = haloLight;
      slot.criticalMarker = criticalMarker;
      rackRoot.add(rack);
    });

    rackRoot.updateMatrixWorld(true);
    frameRacksInitialView();
    racksLoaded = true;
  },
  undefined,
  (error) => {
    fatal("GLB load failed");
    console.error("Failed to load rack GLB", error);
  }
);

let prevMs = performance.now();
function animate(nowMs) {
  requestAnimationFrame(animate);
  const dt = Math.min((nowMs - prevMs) / 1000, 0.08);
  prevMs = nowMs;
  const nowSec = nowMs / 1000;

  rackSlots.forEach((slot) => applyRackVisual(slot, dt, nowSec));
  controls.update();

  if (composer) {
    composer.render();
  } else {
    renderer.render(scene, camera);
  }
}

function onResize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  renderer.setSize(w, h);
  if (composer) {
    composer.setSize(w, h);
  }
  if (bloomPass && bloomPass.setSize) {
    bloomPass.setSize(w, h);
  }
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  if (racksLoaded) {
    frameRacksInitialView();
  }
}

window.addEventListener("resize", onResize);
loadRuntimeConfig().finally(() => {
  connectWebSocket();
  animate(performance.now());
});
