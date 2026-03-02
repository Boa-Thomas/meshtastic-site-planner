# Meshtastic Site Planner

## Visão Geral do Projeto

Aplicação web full-stack para simulação e previsão de cobertura de rádio de redes Meshtastic. Utiliza o modelo ITM (Irregular Terrain Model) / Longley-Rice via software SPLAT! para gerar mapas de cobertura com base em dados de elevação do terreno (NASA SRTM). O objetivo principal é permitir o **planejamento otimizado de posicionamento de nós** para maximizar cobertura na rede mesh.

**Produção:** https://site.meshtastic.org

## Objetivos Estratégicos

### Simulação de Alcance de Nós
- Simular cobertura RF considerando terreno real (SRTM 30m/90m)
- Permitir estudo e planejamento de pontos otimizados para posicionamento de nós
- Buscar a maior cobertura possível em cada região

### Dados Necessários para Simulação Precisa
Os seguintes parâmetros são críticos para precisão:
1. **Altura AGL** (Above Ground Level) — altura real da antena em relação ao solo
2. **Linha de visada da antena** — obstruções no entorno (prédios, morros, vegetação densa)
3. **Tipo e ganho da antena** — modelo utilizado e ganho em dBi
4. **Potência de transmissão (TX Power)** — configurada no dispositivo
5. **Tipo de instalação** — mastro, telhado, janela, portátil, etc.
6. **Orientação da antena** — omnidirecional ou direcional (e azimute, se aplicável)

## Stack Tecnológica

### Frontend
- **Vue 3** (Composition API, `<script setup>`) + **TypeScript**
- **Pinia** para state management
- **Vite** como build tool
- **Bootstrap 5** para UI
- **Leaflet** para mapas interativos + GeoRaster para overlays de cobertura
- **html2canvas** + **jsPDF** para exportação de mapas em PDF

### Backend
- **FastAPI** (Python) + **Uvicorn**
- **Pydantic** para validação de dados
- **Redis** para cache de tarefas e resultados
- **boto3** para download de tiles SRTM da AWS S3
- **rasterio** + **numpy** + **matplotlib** para processamento geoespacial
- **SPLAT!** (submodule C++) — binário de propagação RF compilado no Docker

### Infraestrutura
- **Docker** + **Docker Compose** (4 serviços: app, redis, nginx-proxy, acme-companion)
- **Nginx Proxy** com Let's Encrypt automático
- Limite de memória: 12GB para o container principal

## Estrutura do Projeto

```
├── src/                    # Frontend Vue
│   ├── App.vue             # Layout principal (navbar + offcanvas + mapa)
│   ├── main.ts             # Inicialização Vue + Pinia
│   ├── store.ts            # Pinia store (estado, ações de simulação, export PDF)
│   ├── types.ts            # Interfaces TypeScript (Site, SplatParams)
│   ├── layers.ts           # Marcadores Leaflet customizados
│   ├── utils.ts            # Funções auxiliares
│   └── components/
│       ├── Transmitter.vue # Parâmetros TX (nome, coords, potência, frequência)
│       ├── Receiver.vue    # Parâmetros RX (sensibilidade, altura, ganho)
│       ├── Environment.vue # Parâmetros ambientais (clima, polarização, solo)
│       ├── Simulation.vue  # Opções de simulação (fração, alcance, resolução)
│       └── Display.vue     # Configurações visuais (dBm, colormap, transparência)
├── app/                    # Backend FastAPI
│   ├── main.py             # Endpoints: POST /predict, GET /status/{id}, GET /result/{id}
│   ├── models/
│   │   └── CoveragePredictionRequest.py  # Schema Pydantic (25+ campos)
│   └── services/
│       └── splat.py        # Orquestração SPLAT! (819 linhas): download terreno, conversão SDF, execução, GeoTIFF
├── splat/                  # Submodule git: SPLAT! (propagação RF ITM/ITWOM)
├── utils/                  # Scripts Python auxiliares
│   └── generate_colorbars.py
├── ui/                     # Frontend compilado (servido pelo FastAPI)
├── public/                 # Assets estáticos
├── Dockerfile              # Build multi-stage (Python + SPLAT! compilado)
├── docker-compose.yml      # Orquestração de 4 serviços
├── parameters.md           # Documentação detalhada dos parâmetros do modelo
└── ISSUES.md               # Catálogo de issues conhecidas (P0-P4)
```

## Fluxo Principal

1. Usuário preenche parâmetros (TX, RX, ambiente, simulação, display)
2. Frontend envia POST `/predict` com `CoveragePredictionRequest`
3. Backend gera task UUID, inicia processamento SPLAT! assíncrono
4. Pipeline SPLAT!: download tiles SRTM → conversão HGT→SDF → execução SPLAT! → PPM+KML → GeoTIFF
5. Frontend faz polling em `/status/{task_id}` até conclusão
6. Frontend baixa GeoTIFF via `/result/{task_id}`
7. GeoRaster renderiza overlay de cobertura no Leaflet

## Comandos de Desenvolvimento

```bash
# Frontend (dev)
pnpm run dev              # Servidor Vite com hot reload (proxy para :8080)
pnpm run build            # Type-check + build + copia assets

# Stack completa
docker-compose up --build # Compila SPLAT!, inicia FastAPI + Redis + Nginx

# Backend isolado
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Convenções

- Frontend em TypeScript com Vue Composition API (`<script setup>`)
- Backend em Python com FastAPI + Pydantic
- Idioma do código: inglês
- Documentação e comunicação: português (BR) conforme preferência do usuário
- Commits em inglês (padrão do repo)
- Sem ESLint/Prettier configurado atualmente

## Issues Conhecidas (ver ISSUES.md)

Prioridades catalogadas de P0 (segurança crítica) a P4 (DevOps):
- **P0:** Rate limiting, validação UUID, container root, Redis sem auth, CORS
- **P1:** Store monolítico, `any` types, deep clone, presets de dispositivos, validação de forms, linting
- **P2:** Save/load, estatísticas de cobertura, legenda no mapa, feedback visual, progresso, testes
- **P3:** Lazy loading, polling, Web Worker, Celery
- **P4:** .dockerignore, camadas Docker, health check, Docker Compose split
