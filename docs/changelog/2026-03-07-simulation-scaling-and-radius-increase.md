# feat: increase max simulation radius to 600km and add dynamic worker scaling

**Data:** 2026-03-07
**Branch:** claude/ecstatic-hugle
**Arquivos alterados:** Dockerfile, app/services/splat.py, app/celery_app.py, app/main.py, app/autoscaler.py (new), docker-compose.yml, src/components/Simulation.vue, requirements.txt

## O que foi feito
- Increased SPLAT! MAXPAGES from 64 to 225, raising max simulation radius from ~400km to 600km
- Added configurable radius cap via `MAX_SIMULATION_RADIUS_KM` env var (default: 600)
- Split Celery into two queue types: `default` (light, <=200km) and `heavy` (>200km)
- Added two worker service types in Docker Compose with YAML anchors for DRY config
- Created autoscaler service that monitors Redis queue depth and dynamically scales workers via Docker API
- Frontend now accepts up to 600km with a complexity warning for simulations >200km

## Por que
Users attempting 400km+ simulations were getting partial results due to SPLAT! MAXPAGES=64 limit (~445km at equator, less at higher latitudes). With a single worker, large simulations blocked the queue for all users. Multiple nodes with high simulation distances require parallel processing.

## Decisões técnicas
- **MAXPAGES=225**: Patched post-configure via sed in Dockerfile. ARRAYSIZE=270225 defined directly in std-parms.h since splat.cpp's `#if MAXPAGES==X` chains only support predefined values up to 64
- **Memory per instance**: 225 pages * ~5.5MB = ~1.24GB (fits in 4-8GB worker containers)
- **Queue separation**: Heavy workers consume both `heavy` AND `default` queues (`-Q heavy,default`) to avoid idle time when heavy queue is empty
- **Autoscaler over Celery autoscale**: Docker socket approach chosen over Celery's built-in `--autoscale` for true horizontal scaling (new containers vs. just threads)
- **Scale-down cooldown**: 120s delay before reducing workers to prevent thrashing

## Impacto
- Simulation radius increased from 400km to 600km
- Worker scaling: baseline 2 workers (1 light + 1 heavy), up to 7 (4 light + 3 heavy) under load
- New dependency: `docker==7.1.0` (Docker SDK for autoscaler)
- New service: `autoscaler` requires Docker socket mount

## Próximos passos
- Test Docker build with MAXPAGES=225 compilation
- Verify autoscaler behavior under load (multi-node simultaneous simulations)
- Consider adding Prometheus metrics to autoscaler for monitoring
