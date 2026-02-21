# Relatório Técnico - Frontend 3D Digital Twin

**Data:** 21 de fevereiro de 2026  
**Projeto:** AI-IoT Cooperative Cooling + 3D Digital Twin  
**Autor:** Sistema de Controle Cooperativo

---

## 1. Visão Geral

O frontend do projeto consiste num **Digital Twin 3D** interativo que visualiza em tempo real o estado térmico de um datacenter com 8 racks. A aplicação é construída com **Three.js** e utiliza **WebSocket** para streaming de dados ao vivo do servidor Python.

### 1.1 Localização
```
twin3d/
├── index.html          # Estrutura HTML da aplicação
├── styles.css          # Estilos CSS customizados
├── main.js            # Lógica principal da aplicação (700 linhas)
└── vendor/            # Bibliotecas Three.js
    └── three/
        ├── build/
        │   └── three.module.js
        └── examples/jsm/
            ├── controls/
            │   └── OrbitControls.js
            ├── loaders/
            │   └── GLTFLoader.js
            └── postprocessing/
                ├── EffectComposer.js
                ├── RenderPass.js
                ├── UnrealBloomPass.js
                └── [outros]
```

---

## 2. Arquitetura do Frontend

### 2.1 Stack Tecnológica
- **Three.js** (r150+): Renderização 3D WebGL
- **GLTFLoader**: Carregamento do modelo 3D do rack
- **OrbitControls**: Navegação 3D interativa
- **UnrealBloomPass**: Pós-processamento com bloom para efeitos visuais
- **WebSocket API**: Comunicação bidirecional em tempo real
- **Fetch API**: Fallback para polling HTTP

### 2.2 Modelo de Dados
```javascript
{
  "racks": [
    {
      "id": "R01",
      "status": "normal" | "warning" | "critical",
      "hot_temp": 45.5,
      "thermal_map": [55.2, 52.1, 48.3, ...],
      "mode": "cooperative" | "synthetic" | "isolated",
      "anomaly_detected": false
    },
    ...
  ],
  "cluster": {
    "avg": 63.12,
    "max": 71.26,
    "critical_rack": "R02",
    "total_cooling_kw": 19.11
  },
  "ai": {
    "status": "nominal" | "warning" | "critical",
    "confidence": 0.862,
    "trend": "+0.02",
    "prediction_5min": 63.2,
    "anomaly_risk": "low" | "medium" | "high"
  }
}
```

---

## 3. Funcionalidades Implementadas

### 3.1 Renderização 3D

#### 3.1.1 Carregamento do Modelo GLB
- Modelo 3D customizado do rack (`rack/data_center_rack.glb`)
- 8 instâncias clonadas dispostas em grid 4×2
- Posicionamento automático com espaçamento configurável

#### 3.1.2 Sistema de Materiais Dinâmicos
```javascript
function thermalGradient(temp)
```
- Mapeamento de temperatura (30°C - 85°C) para gradiente de cor:
  - **Azul ciano** (frio): 30°C
  - **Verde**: 45°C
  - **Amarelo**: 60°C
  - **Laranja**: 70°C
  - **Vermelho**: 85°C+
- Aplicação em tempo real à geometria do rack

#### 3.1.3 Pós-Processamento Visual
- **UnrealBloomPass**: Efeito de brilho intensificado em racks críticos
- **Threshold dinâmico**: Bloom mais intenso para temperaturas >70°C
- **Anti-aliasing**: Renderização suave

### 3.2 Comunicação em Tempo Real

#### 3.2.1 WebSocket (Modo Primário)
```javascript
function connectWebSocket()
```
- Conexão persistente em `ws://127.0.0.1:8000`
- Reconexão automática em caso de falha (timeout: 1.2s)
- Parsing de JSON em tempo real
- Fallback automático para polling se WebSocket indisponível

#### 3.2.2 HTTP Polling (Modo Fallback)
```javascript
async function pollTwinOnce()
```
- Polling periódico do endpoint `/api/twin` a cada 800ms
- Ativado automaticamente se WebSocket falhar
- Indicador visual "WS DISABLED (POLLING)"

#### 3.2.3 Configuração Dinâmica
```javascript
async function loadRuntimeConfig()
```
- Leitura de `/api/config` ao inicializar
- Configuração de host/porta do WebSocket
- Adaptação automática ao ambiente (localhost vs. rede)

### 3.3 Dashboard de Métricas

#### 3.3.1 KPIs Principais
1. **Cluster Thermal State**
   - Temperatura média do cluster em °C
   - Tendência (°C/min) com indicador visual
   - Sparkline com histórico de 60 segundos (36 pontos)

2. **Métricas Globais**
   - Global Avg: Média de todos os racks
   - Global Max: Temperatura máxima registada
   - Critical Rack: Rack com maior temperatura
   - Total Cooling Power: Potência total (kW) + variação

3. **AI Monitor**
   - Status: NOMINAL / WARNING / CRITICAL
   - Confidence: Nível de confiança do modelo (%)
   - Trend: Tendência térmica projetada
   - Prediction (5 min): Previsão de temperatura
   - Anomaly Risk: LOW / MEDIUM / HIGH

#### 3.3.2 Tabela de Racks
| Coluna | Descrição |
|--------|-----------|
| Rack | ID do rack (R01-R08) |
| Status | Indicador visual (🟢 Normal / 🟡 Warning / 🔴 Critical) |
| Hot °C | Temperatura hotspot |
| Thermal | Gradiente visual linear |
| Fan | Velocidade da ventoinha (RPM) |
| Pump | Velocidade da bomba (RPM) |
| Mode | Modo de operação (cooperative/synthetic/isolated) |

#### 3.3.3 Legenda Térmica
- Gradiente contínuo de 30°C a 75°C+
- Cores sincronizadas com o modelo 3D

### 3.4 Controles Interativos

#### 3.4.1 OrbitControls
- **Rotação**: Arrastar com botão esquerdo
- **Zoom**: Scroll do rato
- **Pan**: Arrastar com botão direito
- Limites de zoom: 10-100 unidades
- Auto-rotação desativada

#### 3.4.2 Vista Inicial
```javascript
function frameRacksInitialView()
```
- Posicionamento diagonal para melhor visualização
- Ângulo de 10° para mostrar topo dos racks
- Offset lateral para centragem visual

### 3.5 Sistema de Animação

#### 3.5.1 Loop de Renderização
```javascript
function animate(nowMs)
```
- 60 FPS (ou refresh rate do ecrã)
- Delta time para animações suaves
- Atualização visual incremental (não brusca)

#### 3.5.2 Interpolação de Cores
```javascript
function applyRackVisual(slot, dtSec, nowSec)
```
- Transição suave entre temperaturas (sem saltos)
- Lerp factor: 2.5 (transição em ~0.4s)
- Previne flickering visual

#### 3.5.3 Sparkline Animado
- Atualização em tempo real
- Sliding window de 60 segundos
- Auto-scaling do eixo Y

---

## 4. Gestão de Estado

### 4.1 Variáveis Globais
```javascript
const RACK_COUNT = 8
const DEFAULT_WS_PORT = 8000
const TEMP_MIN = 30
const TEMP_MAX = 85
const HERO_SPARKLINE_WINDOW_MS = 60_000
```

### 4.2 Estado de Conexão
- Pill de status: ONLINE (verde) / OFFLINE (vermelho) / POLLING (amarelo)
- Reconexão automática em loop
- Cleanup de timers em desconexão

---

## 5. Tratamento de Erros

### 5.1 Erros Fatais
```javascript
function fatal(message)
```
- Log no console
- Atualização do pill de status
- Não bloqueia a UI (continua renderizando)

### 5.2 Erros Recuperáveis
- WebSocket `onclose`: Inicia polling e tenta reconectar
- WebSocket `onerror`: Fallback para polling
- Fetch errors: Silenciados (retry no próximo ciclo)

### 5.3 Validação de Dados
- Parse de JSON com try-catch
- Validação de arrays de racks
- Fallback para valores padrão em dados inválidos

---

## 6. Performance

### 6.1 Otimizações Implementadas
- **Cloning de geometria**: Reutilização do modelo base
- **Material pooling**: Materiais partilhados onde possível
- **Throttling de updates**: Limita taxa de atualização visual
- **Lazy loading**: Three.js carregado como ES module
- **No garbage**: Reutilização de objetos Color/Vector3

### 6.2 Métricas Esperadas
- **FPS**: 60 (em hardware moderno)
- **Latência WS**: <50ms (rede local)
- **Memory footprint**: ~150MB (inclui Three.js + GLB)
- **Initial load**: ~2s (inclui carregamento de GLB)

---

## 7. Compatibilidade

### 7.1 Navegadores Suportados
- ✅ Chrome/Edge 90+
- ✅ Firefox 88+
- ✅ Safari 14+ (macOS/iOS)
- ⚠️ Mobile: Funcional mas limitado (performance)

### 7.2 Requisitos
- WebGL 2.0
- ES6 Modules
- WebSocket API
- Fetch API

---

## 8. Estrutura de Ficheiros Estáticos

### 8.1 Servidos pelo Python Server
```python
# server.py - WebService class
ui_service = WebService(
    app=app,
    host="127.0.0.1",
    port=8080,
    project_root=project_root,
    ui_entry="twin3d/index.html"
)
```

### 8.2 Mapeamento de Rotas
- `/` → `twin3d/index.html`
- `/twin3d/*` → Ficheiros estáticos
- `/rack/*` → Modelo GLB
- `/api/*` → REST endpoints

---

## 9. Endpoints REST Consumidos

### 9.1 GET `/api/config`
```json
{
  "ws_host": "127.0.0.1",
  "ws_port": 8000,
  "ws_rack_count": 8,
  "ws_enabled": true
}
```

### 9.2 GET `/api/twin`
```json
{
  "racks": [...],
  "cluster": {...},
  "ai": {...}
}
```

---

## 10. Fluxo de Dados

```
┌─────────────┐
│   Browser   │
│  (twin3d)   │
└──────┬──────┘
       │
       │ 1. HTTP GET /
       ↓
┌─────────────┐
│   Python    │
│   Server    │
│  (port 8080)│
└──────┬──────┘
       │
       │ 2. index.html + JS
       ↓
┌─────────────┐
│   Browser   │
│  loads 3D   │
└──────┬──────┘
       │
       │ 3. WS connect
       ↓
┌─────────────┐
│  WebSocket  │
│  (port 8000)│
└──────┬──────┘
       │
       │ 4. JSON stream
       ↓
┌─────────────┐
│   Three.js  │
│   renders   │
└─────────────┘
```

---

## 11. Próximos Desenvolvimentos Sugeridos

### 11.1 Funcionalidades
- [ ] Modo escuro/claro
- [ ] Gráficos históricos expandidos (Chart.js)
- [ ] Alertas sonoros para anomalias
- [ ] Export de dados (CSV/JSON)
- [ ] Modo fullscreen para a vista 3D

### 11.2 Melhorias Técnicas
- [ ] Service Worker para offline capability
- [ ] Compressão de WebSocket (permessage-deflate)
- [ ] Instancing de geometria para melhor performance
- [ ] LOD (Level of Detail) para distância
- [ ] WebXR support para VR/AR

### 11.3 UX/UI
- [ ] Tutorial interativo ao primeiro acesso
- [ ] Tooltips 3D ao hover sobre racks
- [ ] Filtros por status/temperatura
- [ ] Presets de câmara (top view, side view)

---

## 12. Dependências

### 12.1 Bibliotecas Frontend
```javascript
import * as THREE from "/twin3d/vendor/three/build/three.module.js"
import { OrbitControls } from "/twin3d/vendor/three/examples/jsm/controls/OrbitControls.js"
import { GLTFLoader } from "/twin3d/vendor/three/examples/jsm/loaders/GLTFLoader.js"
import { EffectComposer } from "/twin3d/vendor/three/examples/jsm/postprocessing/EffectComposer.js"
import { RenderPass } from "/twin3d/vendor/three/examples/jsm/postprocessing/RenderPass.js"
import { UnrealBloomPass } from "/twin3d/vendor/three/examples/jsm/postprocessing/UnrealBloomPass.js"
```

### 12.2 Assets
- `rack/data_center_rack.glb` (modelo 3D customizado)

---

## 13. Conclusão

O frontend **3D Digital Twin** implementado oferece uma visualização imersiva e em tempo real do estado térmico do datacenter cooperativo. A arquitetura modular permite extensões futuras e a utilização de WebSocket garante latência mínima na atualização dos dados.

**Estatísticas:**
- **700 linhas** de JavaScript (main.js)
- **21 funções** principais
- **3 modos** de comunicação (WS primário, HTTP fallback, config dinâmica)
- **8 KPIs** visuais
- **60 FPS** de renderização

A aplicação está completamente funcional e pronta para demonstração.
