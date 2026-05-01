# DEM / Terrain Source Roadmap

Visão de longo prazo para a fonte de dados de elevação e modelagem de obstrução
no Meshtastic Site Planner.

## Status

| Fase | Escopo | Estado |
|------|--------|--------|
| A    | Copernicus GLO-30 selecionável via env | ✅ entregue |
| B    | FABDEM (DTM real, sem dossel) | ✅ entregue (requer mirror operacional) |
| C    | Clutter espacial (canopy height por pixel) | ✅ entregue (requer mirror + calibração de campo) |

## Fase A — entregue

Implementado em `app/services/splat.py` e `app/services/engine_factory.py`:

- Variável de ambiente `DEM_SOURCE` (default `srtm`).
- Suporte a `DEM_SOURCE=copernicus`: baixa Copernicus GLO-30 COGs do bucket
  AWS público `copernicus-dem-30m` e transcodifica em memória para o formato
  `.hgt.gz` esperado pelo `srtm2sdf`.
- Caches (disco + Redis) namespaced por fonte (`dem:srtm:hgt:*`,
  `dem:copernicus:hgt:*`) para que tiles de fontes diferentes nunca colidam.
- ZSET de popularidade do prefetch também segregado por fonte
  (`dem:{source}:access`).

**Como ativar:** `DEM_SOURCE=copernicus docker-compose up`.
**Rollback:** remover a variável (volta para SRTM).
Caches antigos (`srtm:hgt:*`, `srtm:access`) continuam órfãos — podem ser
limpos com `redis-cli --scan --pattern 'srtm:*' | xargs redis-cli del` quando
houver janela.

---

## Fase B — FABDEM (DTM real, sem dossel) — entregue

**Motivação:** Copernicus e SRTM são DSMs (incluem floresta/edificações).
Em SPLAT! isso "infla" o terreno em mata densa e subestima o alcance real do
solo. FABDEM remove dossel/prédios via redes neurais — DTM puro, ideal para
o modelo Longley-Rice que assume altura do *solo*.

### O que foi implementado
- `DEM_SOURCE=fabdem` registrado em `DEM_SOURCES` (`app/services/splat.py`).
- `_download_fabdem_tile` baixa do bucket configurado (não há mirror público).
- Reaproveita `_cog_to_hgt_gz` para transcodificar GeoTIFF → `.hgt.gz`.
- **Fallback automático** via `FABDEM_FALLBACK_SOURCE` (default `copernicus`)
  para tiles ausentes (oceano, cobertura parcial, mirror incompleto).
- Filename template configurável (`FABDEM_FILENAME_TEMPLATE`,
  default `{ns}{lat:02d}{ew}{lon:03d}_FABDEM_V1-2.tif`).

### Pré-requisitos para ativação em produção
- [x] Licença CC BY-NC-SA OK para o projeto (não-comercial).
- [ ] **Hospedagem ainda pendente.** FABDEM não está em AWS Open Data. Opções:
  1. Mirror próprio em S3/R2 (~150 GB para cobertura global).
  2. Mirror Brasil-only (~5 GB) com fallback automático para Copernicus
     fora do país (já suportado pelo `FABDEM_FALLBACK_SOURCE`).
- [ ] Adicionar atribuição no rodapé: "Terrain: FABDEM (Hawker et al., 2022)
  CC BY-NC-SA 4.0".

### Como ativar
```bash
DEM_SOURCE=fabdem \
FABDEM_BUCKET=meu-mirror \
FABDEM_PREFIX=fabdem-v1-2 \
FABDEM_FALLBACK_SOURCE=copernicus \
docker-compose up
```

---

## Fase C — Clutter espacial (canopy height por pixel) — entregue

**Motivação:** O flag `-gc` do SPLAT! aceita apenas um **valor único** de
altura de clutter aplicado a todo o mapa. Hoje é um chute (ex.: 10 m médio
de mata). A Fase C transforma isso num raster por pixel a partir de dados
reais de altura de dossel.

### Limitação fundamental
O SPLAT! não consome um raster de clutter espacial. Solução: **gerar um DSM
sintético = DTM (FABDEM) + canopy height** e alimentá-lo no `srtm2sdf`. Do
ponto de vista do SPLAT!, é apenas terreno mais alto onde há vegetação.

### Fontes de canopy height
| Dataset | Resolução | Cobertura | Notas |
|---|---|---|---|
| **Lang et al. 2023** (ETH/Google) | 10 m | Global | Derivado de Sentinel-2 + GEDI. Disponível no GEE e como tiles GeoTIFF. Melhor opção global aberta. |
| **GEDI L4B** | 1 km | ±51° lat | Resolução baixa demais para alcance Meshtastic curto. |
| **Potapov et al. 2021** | 30 m | Global | Mais antigo, baseline de comparação. |
| **MapBiomas Brasil — altura de vegetação** | 30 m | Só Brasil | Anual, atualizado, ótimo para o caso BR. |

**Recomendação:** Lang 2023 como default global, com possibilidade de
override por MapBiomas em tiles brasileiros.

### O que foi implementado
- Novo módulo `app/services/clutter.py` com `ClutterSource` e
  `make_clutter_source_from_env()`.
- Sources reconhecidos: `lang2023`, `mapbiomas`, `custom` (todos via mirror
  operacional configurado por env vars).
- `Splat._apply_clutter` decodifica o `.hgt.gz` do DTM, soma o raster de
  canopy multiplicado pelo fator de penetração, preserva voids (-32768),
  re-encoda. Tudo em memória.
- Cache namespace estendido: quando clutter está ativo, vira
  `{dem_source}+{clutter_source}` (ex.: `fabdem+lang2023`). SDFs e tiles HGT
  ficam isolados por combinação. Quando clutter está off, namespace continua
  `{dem_source}` puro — caches existentes seguem válidos.
- `splat`/`splat-hd` invocados **sem `-gc`** quando clutter espacial está
  ativo (evita dupla contagem de obstrução).

### Como ativar
```bash
DEM_SOURCE=fabdem \
FABDEM_BUCKET=meu-dtm-mirror \
CLUTTER_SOURCE=lang2023 \
CLUTTER_BUCKET=meu-canopy-mirror \
CLUTTER_PENETRATION_FACTOR=0.6 \
docker-compose up
```

### Pré-requisitos para ativação em produção
- [ ] Mirror de canopy height (Lang 2023 global ou MapBiomas Brasil).
- [ ] **Calibração empírica** do `CLUTTER_PENETRATION_FACTOR` contra
  medições reais de RSSI da rede Meshtastic. Default 0.6 é chute.

### Risco / pontos abertos
- **Tamanho do cache:** canopy + DTM dobra o uso de disco/Redis. Avaliar
  bumping de `SPLAT_TILE_CACHE_SIZE_GB`.
- **Validação:** comparar previsões antes/depois com medições reais de RSSI
  da rede Meshtastic em SP/Mata Atlântica. Sem isso, o `CLUTTER_PENETRATION_FACTOR`
  vira chute.
- **Custo de I/O:** dobra o número de downloads na primeira request de
  uma região fria. Mitigação: prefetch worker estende para canopy também.

### Testes
- Soma DTM + canopy produz valores plausíveis (não overflow int16).
- Cache key inclui clutter source.
- Fallback: tile de canopy ausente → DTM puro.
- Snapshot: para um par lat/lon de referência, RSSI em mata densa **cai**
  vs. baseline sem clutter.

---

## Próximos passos (operacionais, não de código)

1. **Validar Fase A em prod:** habilitar `DEM_SOURCE=copernicus` para
   uma fração de tráfego, comparar previsão vs. SRTM.
2. **Hospedar FABDEM:** stand up de bucket S3/R2 (mirror Brasil-only é
   suficiente como MVP, fallback para Copernicus já está pronto).
3. **Hospedar canopy height:** Lang 2023 (global) ou MapBiomas (BR).
4. **Calibrar `CLUTTER_PENETRATION_FACTOR`** contra medições reais —
   esse é o único parâmetro que precisa de dados de campo.
5. **Considerar UI exposing source choice:** hoje é só env var.

## Métricas de sucesso

- Discrepância média entre RSSI previsto e medido em campo
  (alvo: < 10 dB de erro absoluto em 80% dos pontos).
- Cobertura prevista em mata Atlântica deve **diminuir** vs. SRTM puro
  (sinal de que o modelo está mais conservador e realista).
- Taxa de cache hit > 90% após uma semana de uso.
