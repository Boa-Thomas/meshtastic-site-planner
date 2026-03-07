# fix: overlay refresh bug, preview race condition, and Docker permissions

**Data:** 2026-03-07
**Commit:** 4982f78
**Branch:** fix/overlay-refresh-and-docker-permissions
**PR:** https://github.com/meshtastic/meshtastic-site-planner/pull/57
**Arquivos alterados:** Dockerfile, src/App.vue, src/stores/sitesStore.ts, pnpm-lock.yaml

## O que foi feito

Três bugs independentes corrigidos:

1. **`resolution` inválido no GeoRasterLayer** (`sitesStore.ts`)
2. **Race condition no cleanup do preview** (`App.vue`)
3. **Permissão do volume `.splat_tiles` no Docker** (`Dockerfile`)

## Por que

O usuário reportou que ao rodar cobertura com 1 nó e depois adicionar um segundo nó e rodar novamente, o overlay da primeira simulação permanecia visível e o overlay da segunda simulação só aparecia no nível máximo de zoom.

Adicionalmente, o worker Celery falhava na inicialização com `sqlite3.OperationalError: unable to open database file`.

## Decisões técnicas

### Bug 1 — `resolution` como objeto inválido

O campo `resolution` do `GeoRasterLayer` estava recebendo um objeto JS (`{ 0: 16, 5: 32, 8: 64, 12: 128, 15: 256 }`) com um cast de tipo TypeScript (`as unknown as number`) para bypassar o compilador. A API do GeoRasterLayer 4.1.2 espera um `number`.

Com um objeto, o comportamento de renderização de tiles por zoom é indefinido — na prática, tiles não renderizavam na maioria dos níveis de zoom, só no máximo (onde algum fallback da biblioteca funcionava).

**Fix:** substituído por `resolution: 256` (valor padrão da biblioteca, funciona em todos os zoom levels).

A intenção original era resolução adaptiva por zoom para performance. Se necessário no futuro, usar a API correta: `getResolution: (zoom) => zoom < 8 ? 64 : 256`.

### Bug 2 — Race condition no preview

Em `onRunNodeCoverage` (chamado do NodeEditor "Run Coverage" com radius > 15km), o fluxo com preview é:

1. Preview (15km, baixa resolução) inicia em paralelo com o full (90km)
2. Preview completa primeiro → `.then()` roda: `previewTaskId = taskId`, depois `await addSiteFromBuffer(...)`
3. `addSiteFromBuffer` chama `await parseGeoraster(...)` — isso **yield** para o event loop
4. Durante esse yield, o full result pode chegar e o código principal continua
5. `findIndex(s => s.taskId === previewTaskId)` retorna `-1` — o preview ainda não foi feito `push` em `localSites`
6. Cleanup é pulado; preview fica como layer órfão

**Fix:** `await previewPromise` foi movido para **antes** do cleanup check. Isso garante que o preview está completamente em `localSites` (o `parseGeoraster` concluiu e o `push` aconteceu) antes de tentar removê-lo.

O preview ainda mostra enquanto o full roda — a diferença é que aguardamos o `parseGeoraster` local do preview concluir antes de trocar pelas camadas finais. Impacto na UX é negligível (operação local, milissegundos).

### Bug 3 — Volume Docker sem permissão

O worker Celery falhava com:
```
sqlite3.OperationalError: unable to open database file
```

Ao tentar criar o cache `diskcache` em `/app/.splat_tiles`.

**Causa raiz:** o `chown -R appuser:appuser /app` no Dockerfile roda em build time, mas `/app/.splat_tiles` não existia ainda (é criado pelo volume mount em runtime). Docker semeia um volume vazio com o conteúdo do diretório da imagem — como o diretório não existia, o volume foi criado com ownership `root`, e `appuser` não tinha permissão de escrita.

**Fix:** adicionado `mkdir -p /app/.splat_tiles` antes do `chown`, para que o Docker semeie o volume vazio com o diretório já com ownership correto.

**Atenção:** se o volume `splat-tile-cache` já existe no servidor com permissão errada, é necessário recriá-lo:
```bash
docker compose down
docker volume rm meshtastic-site-planner_splat-tile-cache
docker compose up --build -d
```

## Impacto

- Todos os overlays de cobertura agora renderizam corretamente em todos os níveis de zoom
- Nenhum layer órfão de preview é deixado no mapa
- Worker Celery inicializa sem erro de permissão

## Próximos passos

- Se performance em baixo zoom for um problema no futuro, implementar resolução adaptiva usando a API correta do GeoRasterLayer (`getResolution` callback)
- Considerar adicionar um timeout ao preview para evitar que o preview demore mais que o esperado
