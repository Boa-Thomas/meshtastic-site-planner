# Plano de Implementação: Nós Avançados + Simulação de Eventos Discretos (DES) + Testes

## Contexto

O Meshtastic Site Planner atualmente permite simular cobertura RF de nós individuais usando SPLAT!/ITM. Precisamos estendê-lo para:
1. **Parâmetros avançados de nós** — altura AGL, obstruções, tipo/ganho da antena, TX power, tipo de instalação, orientação da antena, presets de dispositivos e canais
2. **Simulação de Eventos Discretos (DES)** — modelar propagação de mensagens na rede mesh considerando o protocolo Meshtastic (managed flood routing, hop limit, contention window, duty cycle, colisões, ACK/retransmissão)
3. **Testes automatizados** — Vitest (frontend), pytest (backend), Playwright (E2E)

## Decisões Arquiteturais

1. **DES roda no frontend (TypeScript)** — dados do SPLAT! já estão client-side como GeoRaster; visualização em tempo real requer coupling com Leaflet; sem roundtrip para cada evento. Web Worker para 100+ nós.
2. **Conectividade nó-a-nó híbrida** — usa pixel value do GeoRaster (SPLAT!) quando disponível; fallback para Free-Space Path Loss (FSPL) simplificado quando não há predição.
3. **Decomposição do store.ts monolítico** — pré-requisito para as novas features. Split em mapStore, nodesStore, sitesStore, desStore.
4. **MeshNode é distinto de Site** — MeshNode representa um dispositivo no mapa com parâmetros; Site é o resultado de uma predição SPLAT!. Um nó pode participar do DES sem ter predição SPLAT!.
5. **Região default: Brasil (BR_915)** — 915 MHz, 100% duty cycle. Configurável pelo usuário para outras regiões (US, EU, etc.) com duty cycle ajustado automaticamente.
6. **Visualização DES completa com animação** — linhas animadas entre nós, pulso ao transmitir, cores por qualidade de sinal, controles de play/pause/step/velocidade.

---

## Fase 1: Infraestrutura de Testes (sem mudanças de feature)

### 1.1 Frontend — Vitest
- Instalar: `vitest`, `@vue/test-utils`, `jsdom`, `@vitest/coverage-v8`
- Criar `vitest.config.ts` (environment: jsdom, include: `src/**/*.test.ts`)
- Scripts em `package.json`: `"test": "vitest"`, `"test:coverage": "vitest --coverage"`

### 1.2 Backend — pytest
- Adicionar ao `requirements.txt`: `pytest`, `pytest-asyncio`, `httpx`
- Criar `app/tests/__init__.py`, `app/tests/conftest.py` (mock Redis, TestClient)
- Testes iniciais: `app/tests/test_models.py` (validação Pydantic), `app/tests/test_api.py` (endpoints)

### 1.3 E2E — Playwright
- Instalar: `@playwright/test`
- Criar `playwright.config.ts`, diretório `e2e/`

**Arquivos a criar/modificar:**
- `vitest.config.ts` (novo)
- `playwright.config.ts` (novo)
- `package.json` (add devDeps + scripts)
- `requirements.txt` (add pytest deps)
- `app/tests/conftest.py`, `app/tests/test_models.py`, `app/tests/test_api.py` (novos)

---

## Fase 2: Sistema de Tipos + Presets

### 2.1 Novos tipos em `src/types/index.ts`

```typescript
// Tipos de instalação
type InstallationType = 'mast' | 'rooftop' | 'window' | 'portable' | 'tower'
type AntennaOrientation = 'omnidirectional' | 'directional'
type ObstructionLevel = 'clear' | 'partial' | 'heavy'

// Presets
interface DevicePreset {
  id: string; name: string; txPowerW: number; txPowerDbm: number;
  frequencyMhz: number; antennaGainDbi: number; rxSensitivityDbm: number;
  chipset: 'sx1262' | 'sx1276' | 'sx1268' | 'lr1110'
}

interface ChannelPreset {
  id: ChannelPresetId; name: string; sf: number; bw: number;
  cr: number; sensitivityDbm: number; bitrateBps: number
}

// MeshNode — conceito central novo
interface MeshNode {
  id: string; name: string; lat: number; lon: number;
  // TX/RX params (podem ser auto-preenchidos por preset)
  txPowerW: number; txPowerDbm: number; frequencyMhz: number;
  txHeight: number; txGainDbi: number;
  rxSensitivityDbm: number; rxHeight: number; rxGainDbi: number; rxLossDb: number;
  // Parâmetros avançados (novos)
  installationType: InstallationType;
  antennaOrientation: AntennaOrientation;
  directionalParams?: { azimuth: number; beamwidth: number };
  obstructionLevel: ObstructionLevel;
  devicePresetId?: string;
  channelPresetId: ChannelPresetId;
  hopLimit: number; // 0-7
  siteId?: string; // link para predição SPLAT! se existir
}
```

### 2.2 Dados de presets em `src/data/`

- `src/data/devicePresets.ts` — Heltec V3, RAK WisBlock 4631, T-Beam Supreme, T-Beam v1.2, T-Echo, Station G2, etc.
- `src/data/channelPresets.ts` — SHORT_TURBO até VERY_LONG_SLOW com SF, BW, CR, sensibilidade, bitrate
- `src/data/antennaPresets.ts` — Stock stubby (1dBi), Stock whip (2.15dBi), 5dBi omni, 6dBi omni, 9dBi Yagi, 12dBi Yagi

**Arquivos a criar:**
- `src/types/index.ts` (novo, substitui `src/types.ts`)
- `src/types/georaster.d.ts` (novo, declarações de tipo para GeoRaster)
- `src/data/devicePresets.ts`, `src/data/channelPresets.ts`, `src/data/antennaPresets.ts` (novos)

---

## Fase 3: Decomposição do Store

Extrair `src/store.ts` (403 linhas) em stores focados:

| Store | Responsabilidade | Origem |
|-------|-----------------|--------|
| `src/stores/mapStore.ts` | Map init, tile layers, markers | store.ts linhas 240-288 |
| `src/stores/sitesStore.ts` | SPLAT! sites, simulação API, raster layers | store.ts linhas 13-99, 290-403 |
| `src/stores/nodesStore.ts` | CRUD de MeshNode, presets | Código novo |
| `src/stores/desStore.ts` | Estado do DES, controle de simulação | Código novo |
| `src/composables/useExport.ts` | Lógica de export PDF | store.ts linhas 100-239 |

Mover inicialização do mapa de `Transmitter.vue` (onMounted, linha 96) para `App.vue`.

**Arquivos a criar/modificar:**
- `src/stores/mapStore.ts`, `sitesStore.ts`, `nodesStore.ts`, `desStore.ts` (novos)
- `src/composables/useExport.ts` (novo)
- `src/App.vue` (modificar: adicionar map init)
- `src/components/Transmitter.vue` (modificar: remover map init)
- Todos os componentes (atualizar imports do store)
- `src/store.ts` (remover após migração)

---

## Fase 4: Parâmetros Avançados de Nós

### 4.1 Novos componentes Vue

- `src/components/NodeEditor.vue` — painel principal de edição de nó
- `src/components/NodeList.vue` — lista de nós com status (tem predição ou não)
- `src/components/DevicePresetSelector.vue` — dropdown de dispositivo (auto-preenche TX/RX)
- `src/components/ChannelPresetSelector.vue` — dropdown de canal (auto-preenche sensibilidade)
- `src/components/InstallationConfig.vue` — tipo de instalação + nível de obstrução
- `src/components/AntennaConfig.vue` — modelo de antena, orientação, parâmetros direcionais

### 4.2 Fluxo de interação

1. Usuário clica "Adicionar Nó" → mapa entra em modo de colocação (cursor crosshair)
2. Click no mapa → nó criado com coordenadas, abre NodeEditor
3. Seleção de preset de dispositivo → auto-preenche TX power, frequência, ganho, sensibilidade
4. Seleção de preset de canal → ajusta sensibilidade baseado em SF/BW
5. Configuração de instalação (tipo, obstrução) e antena (modelo, orientação)
6. "Rodar Cobertura" por nó específico → converte MeshNode em SplatParams e usa API `/predict`

### 4.3 Conversão MeshNode → SplatParams

Novo utilitário `src/utils/nodeToSplatParams.ts`:
- Mapeia parâmetros do MeshNode para o formato esperado pela API
- Aplica modificadores de instalação (obstrução → system_loss adicional)
- Calcula altura efetiva baseado no tipo de instalação

**Backend não precisa de mudanças** — a conversão acontece no frontend antes do POST `/predict`.

---

## Fase 5: Motor DES (TypeScript puro, sem dependência Vue/Leaflet)

### 5.1 Estrutura de diretórios

```
src/des/
  index.ts                  # Barrel export
  types.ts                  # SimEvent, Packet, LinkInfo, SimulationConfig, SimulationState, SimulationMetrics
  EventQueue.ts             # Min-heap por tempo (insert, extractMin, peek, size, isEmpty, clear)
  AirtimeCalculator.ts      # Fórmula LoRa: T_symbol, preamble, payload symbols → airtime em ms
  LinkBudget.ts             # Modo A: pixel GeoRaster → dBm; Modo B: FSPL fallback
  ContentionWindow.ts       # Delay SNR-based: low SNR → menor delay → rebroadcast primeiro
  ChannelModel.ts           # Ocupação do canal, detecção de colisão (intervalos sobrepostos)
  MeshtasticProtocol.ts     # Managed flood routing, dedup por packet ID, ACK implicit/explicit
  SimulationEngine.ts       # Loop DES: event queue → processEvent → schedule new events
  SimulationMetrics.ts      # Cálculo de métricas (delivery ratio, latência, hop count, airtime, colisões)
```

### 5.2 Tipos DES (`src/des/types.ts`)

```typescript
type EventType = 'message_send' | 'message_receive' | 'message_rebroadcast'
               | 'ack_send' | 'ack_receive' | 'collision' | 'timeout' | 'channel_busy' | 'lbt_defer'

interface SimEvent { id: number; time: number; type: EventType; sourceNodeId: string; targetNodeId?: string; packet: Packet }
interface Packet { id: string; originNodeId: string; destinationNodeId?: string; currentHopCount: number; maxHopLimit: number; payloadSizeBytes: number; snrAtReceiver?: number; rssiAtReceiver?: number; isAck: boolean; retryCount: number; txStartTime?: number; txEndTime?: number }
interface LinkInfo { fromNodeId: string; toNodeId: string; rssiDbm: number; snrDb: number; distanceKm: number; canHear: boolean }
interface SimulationConfig { durationMs: number; dutyCyclePercent: number; lbtEnabled: boolean; lbtThresholdDbm: number; maxRetransmissions: number; noiseFloorDbm: number; region: 'BR_915' | 'US_902' | 'EU_868' | 'EU_433' /* default: BR_915 */ }
interface SimulationMetrics { totalMessagesSent: number; totalMessagesDelivered: number; deliveryRatio: number; averageLatencyMs: number; maxLatencyMs: number; averageHopCount: number; totalCollisions: number; airtimeByNode: Map<string, number>; dutyCycleByNode: Map<string, number> }
```

### 5.3 Módulos-chave

**EventQueue** — min-heap binário por SimEvent.time. Pure data structure.

**AirtimeCalculator** — implementa fórmula LoRa padrão:
- `T_symbol = 2^SF / BW * 1000` (ms)
- `preamble_time = (preambleSymbols + 4.25) * T_symbol`
- `payload_symbols = 8 + max(0, ceil((8*PL - 4*SF + 28 + 16) / (4*(SF - 2*DE))) * CR)`
- `airtime = preamble_time + payload_symbols * T_symbol`

**LinkBudget** — dual-mode:
- Modo A (SPLAT!): lê pixel value do GeoRaster nas coords do receptor, mapeia 0-254 → min_dbm..max_dbm
- Modo B (FSPL): `FSPL(dB) = 20*log10(d_km) + 20*log10(f_MHz) + 32.44`, `RSSI = EIRP - FSPL + rxGain - rxLoss - obstructionLoss`
- Para antenas direcionais: redução de ganho baseada no ângulo off-axis (modelo cos²)

**ContentionWindow** — delay SNR-based seguindo protocolo Meshtastic:
- SNR mais baixo → slot menor → rebroadcast mais cedo (nós distantes primeiro)
- `delay = slot * slotTime` onde slot é mapeado do SNR

**SimulationEngine** — loop principal:
1. `extractMin()` da fila de eventos
2. Avança relógio para `event.time`
3. `processEvent()` → despacha por tipo (send, receive, rebroadcast, ack, collision, timeout)
4. Agenda novos eventos derivados
5. Suporta: `step()` (um evento), `run()` (todos), `pause()`, `reset()`

**Protocolo modelado:**
- **Managed flood**: cada nó rebroadcast até hop_limit, com contention window SNR-based
- **Dedup**: pacotes já vistos (por packet ID) são descartados
- **ACK**: implícito para broadcast (sender ouve rebroadcast), explícito para mensagens diretas
- **Retransmissão**: max 3 tentativas para mensagens diretas sem ACK
- **Duty cycle**: EU 10%, US 100%, configurável
- **Colisão**: duas transmissões sobrepostas no tempo no mesmo receptor = colisão

---

## Fase 6: Integração DES com Vue/Leaflet

### 6.1 Store DES (`src/stores/desStore.ts`)

Estado: `engine`, `status` (idle/running/paused/completed), `processedEvents[]`, `currentEventIndex`, `metrics`, `config`, `playbackSpeed`, `animationTimerId`

Ações: `initialize()`, `sendBroadcast(fromNodeId)`, `sendDirect(from, to)`, `step()`, `play()`, `pause()`, `reset()`, `runToCompletion()`

### 6.2 Componentes Vue DES

- `src/components/des/DesControls.vue` — Start/Pause/Step/Reset, speed slider, seletor de nó origem/destino, config (duração, duty cycle, LBT)
- `src/components/des/DesMetrics.vue` — delivery ratio, latência, hop count, airtime por nó, colisões
- `src/components/des/DesEventLog.vue` — log scrollável de eventos com cores por tipo
- `src/components/des/DesLinkOverlay.vue` — overlay de links entre nós no mapa (toggle-able)

### 6.3 Visualização no Mapa (`src/composables/useDesVisualization.ts`)

- **Transmissão**: quando um nó transmite, mostra anel pulsante (CSS `@keyframes pulse`)
- **Recepção**: polyline animada (dash animation) do transmissor ao receptor, cor por qualidade (verde/amarelo/vermelho baseado no RSSI)
- **Colisão**: marcador vermelho piscante no receptor
- CSS animations adicionadas em `src/style.css`

### 6.4 Integração com App.vue

- Novo painel colapsável "Simulação de Rede (DES)" no offcanvas sidebar
- Toggle entre modo "Cobertura SPLAT!" e modo "Simulação DES"
- NodeList sempre visível quando há nós

---

## Fase 7: Testes Automatizados Completos

### 7.1 Testes unitários DES (Vitest) — `src/des/__tests__/`

| Arquivo | Testes |
|---------|--------|
| `EventQueue.test.ts` | Extração em ordem, heap vazio, insert/extract intercalado |
| `AirtimeCalculator.test.ts` | LONG_FAST, SHORT_TURBO, VERY_LONG_SLOW, payload variável, dobro por SF step |
| `LinkBudget.test.ts` | FSPL para distância/frequência conhecidos, obstrução, limiar sensibilidade, extração do raster, fallback |
| `ContentionWindow.test.ts` | SNR baixo → menor delay, clamping SNR, delay em múltiplos do slot time |
| `SimulationEngine.test.ts` | Broadcast em topologia linear, hop limit, dedup, ACK direto, retransmissão, duty cycle EU, colisões, métricas |

### 7.2 Testes de stores (Vitest) — `src/stores/__tests__/`

| Arquivo | Testes |
|---------|--------|
| `nodesStore.test.ts` | Add/remove/update nó, aplicar preset, preset de canal atualiza sensibilidade |
| `sitesStore.test.ts` | Run simulation, polling, resultado, remoção |
| `desStore.test.ts` | Initialize, step, play/pause, reset, métricas |

### 7.3 Testes backend (pytest) — `app/tests/`

| Arquivo | Testes |
|---------|--------|
| `test_models.py` | Validação campos Pydantic (lat, lon, tx_height, radio_climate, colormap), defaults |
| `test_api.py` | POST /predict retorna task_id, validação de input, rate limit, GET /status estados, GET /result GeoTIFF |
| `test_splat_service.py` | Formato QTH, conversão longitude, cálculo ERP, mapeamento clima, DCF 32 níveis, cálculo tiles |

### 7.4 Testes E2E (Playwright) — `e2e/`

| Arquivo | Cenários |
|---------|----------|
| `simulation.spec.ts` | Ciclo completo de simulação SPLAT! (preencher → executar → verificar overlay) |
| `node-management.spec.ts` | Adicionar nó via mapa, aplicar preset, editar, deletar |
| `des-simulation.spec.ts` | Broadcast com 3 nós, step-through, métricas finais |

---

## Ordem de Implementação (sequência segura)

| Step | O quê | Risco | Dependência |
|------|--------|-------|-------------|
| 1 | Infraestrutura de testes (Vitest, pytest, Playwright) | Zero | Nenhuma |
| 2 | Sistema de tipos + presets | Aditivo | Nenhuma |
| 3 | Decomposição do store | Refactoring | Steps 1-2 |
| 4 | Parâmetros avançados de nós (UI + nodesStore) | Feature nova | Step 3 |
| 5 | Motor DES core (TypeScript puro, TDD) | Feature nova | Steps 2, 4 |
| 6 | DES store + componentes UI + visualização | Integração | Steps 3, 5 |
| 7 | Testes E2E + polimento | Qualidade | Steps 4, 6 |

---

## Arquivos Críticos a Modificar

| Arquivo existente | Mudança |
|-------------------|---------|
| `src/store.ts` | Decompor → 4 stores + 1 composable, depois remover |
| `src/types.ts` | Substituir por `src/types/index.ts` expandido |
| `src/App.vue` | Map init, DES panel toggle, NodeList |
| `src/components/Transmitter.vue` | Remover map init (onMounted) |
| `src/layers.ts` | Adicionar variantes de marcadores para nós |
| `src/style.css` | Adicionar animações CSS para DES |
| `package.json` | Adicionar devDeps de testes + scripts |
| `requirements.txt` | Adicionar pytest deps |
| `vite.config.ts` | Adicionar proxy para novos endpoints se necessário |

## ~45 Novos Arquivos

- 9 módulos DES (`src/des/`)
- 5 testes DES (`src/des/__tests__/`)
- 4 stores (`src/stores/`)
- 3 testes stores (`src/stores/__tests__/`)
- 6 componentes de nó (`src/components/`)
- 4 componentes DES (`src/components/des/`)
- 3 dados de presets (`src/data/`)
- 2 utilitários (`src/utils/`)
- 1 composable (`src/composables/`)
- 2 type files (`src/types/`)
- 3 configs de teste (vitest, playwright, conftest)
- 5 testes backend (`app/tests/`)
- 3 testes E2E (`e2e/`)

---

## Verificação

### Após cada fase:
- `pnpm run test` — todos os testes Vitest passam
- `pnpm run build` — build frontend sem erros TypeScript
- `cd app && python -m pytest` — todos os testes pytest passam
- Workflow existente de simulação SPLAT! continua funcionando (regressão)

### Verificação final:
- Colocar 3+ nós no mapa com parâmetros diferentes
- Rodar cobertura SPLAT! para pelo menos 1 nó
- Executar DES broadcast e verificar propagação animada no mapa
- Verificar métricas (delivery ratio, latência, colisões)
- Executar DES mensagem direta e verificar ACK
- `npx playwright test` — todos os testes E2E passam
