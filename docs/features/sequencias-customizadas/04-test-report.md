# Relatório de testes — Sequências de Acordes Customizadas

## Cobertura

> Devido a problemas com minha máquina pessoal (dispositivo de boot não
> encontrado), pude realizar a atividade somente com a máquina do laboratório,
> porém esta não possui as ferramentas necessárias para a criação de um ambiente
> virtual python e nem o Docker, algo que o próprio agente identificou quando
> quando tentou utilizar certas ferramentas durante a atividade. As alternativas
> foram aplicadas automaticamente pelo próprio agente quando este identificou
> a limitação.

Não há framework de testes no repositório; a verificação é feita por um script de
regressão versionado e por testes de contrato com `curl` na imagem Docker real.

| Verificação | O que cobre | Onde |
|---|---|---|
| `scripts/verifica_sequencias.py` | Recálculo do matching em runtime contra a coluna `SEQ_FAMOSA` para as 6 originais, música a música (igualdade de conjuntos, não só de contagem) | automatizado |
| Contrato `GET /sequencias` | Catálogo com as 6 originais (ids 0–5) após o seed | `curl` |
| Contrato `POST /sequencias` | `201` válido, `400` curto/token vazio/acorde inexistente, `409` duplicado (inclusive mudando a caixa) | `curl` |
| Contrato `GET /similares?sequencia=` | Contagens das 6 originais, busca minúscula, sequência desconhecida → `[]`, filtro por gênero | `curl` + Python |
| Persistência | Cadastro sobrevive a `podman restart`; `Mounts: []`; `rm` + novo `run` perde o catálogo (esperado) | `podman` |
| Frontend | Página `#/porsequencia` renderiza as 6 sequências e o formulário; JS passa em `node --check` | Chrome headless (`--dump-dom`) |
| Latência | Handler de busca e tempo HTTP por requisição | medição pontual |

## Teste de regressão obrigatório

O script [`scripts/verifica_sequencias.py`](../../../scripts/verifica_sequencias.py)
importa `main`, recalcula os matches com
`sequencias.preparar`/`sequencias.aparece` e compara, música a música, o conjunto de
`id_unico_musica` com o conjunto obtido pela tag `SEQ_FAMOSA` do CSV. Ele imprime as
contagens e sai com código 1 em qualquer divergência.

Saída obtida (`podman run --rm --entrypoint python ciframe scripts/verifica_sequencias.py`):

```
0 Bm,G,D,A           esperado=199 calculado=199 ok
1 C,G,Am,F           esperado=296 calculado=296 ok
2 Em,G               esperado=  4 calculado=  4 ok
3 C,A7,Dm,G7         esperado=  5 calculado=  5 ok
4 Gm,F               esperado=  7 calculado=  7 ok
5 C,C7,F,Fm          esperado=  3 calculado=  3 ok

Todas as 6 sequências batem com a coluna SEQ_FAMOSA.
```

Resultado: **199 / 296 / 4 / 5 / 7 / 3**, com igualdade de conjuntos, código de
saída 0. As contagens via HTTP também batem quando somadas as páginas de 100 itens
(`Bm,G,D,A` = 199 em duas páginas; `C,G,Am,F` = 296 em três).

Casos de borda cobertos pela mesma varredura: músicas sem cifra (8.141), cifras com
acorde repetido e músicas cujo vocabulário não está contido na sequência. A busca
`bm,g,d,a` devolve os mesmos 199 ids de `Bm,G,D,A` (passou a ser insensível a
maiúsculas).

## Contrato da API

Executado contra o container em `:8080`:

| Caso | Resultado |
|---|---|
| `GET /sequencias` | `200`, 6 itens, ids 0–5 |
| `POST {"acordes":"Dm,G,C"}` | `201`, `{"id": 6, "acordes": "Dm,G,C"}` |
| `POST {"acordes":"C"}` | `400` (menos de 2 acordes) |
| `POST {"acordes":"C,,G"}` | `400` (token vazio) |
| `POST {"acordes":"C,ZZZ"}` | `400` (acorde fora de `/acordes`) |
| `POST {"acordes":"dm,g,c"}` | `409` (duplicata normalizada) |
| `GET /similares?sequencia=Zz,YY` | `200`, `[]` |
| `GET /similares?sequencia=F%23%2CC%23` | `200`, 2 músicas (o `#` codificado chega intacto) |
| `Content-Type` das respostas | `text/html; charset=utf-8` (legado mantido) |

## Persistência

- `podman restart` após cadastrar `Dm,G,C` e `F#,C#`: o `GET /sequencias` continuou
  devolvendo os 8 itens e a busca por `F#,C#` continuou retornando 2 músicas.
- `podman inspect ... --format '{{json .Mounts}}'` → `[]` (nenhum volume).
- `rm` + novo `run`: o catálogo voltou às 6 originais, sem duplicação do seed —
  comportamento esperado e documentado no `README.md`.
- Build da imagem: `data/sequencias.db` não entra na imagem (`.dockerignore`).

## Frontend

`google-chrome --headless --dump-dom http://localhost:8080/#/porsequencia` retornou
o template já compilado pelo AngularJS com:

- 6 blocos `.acordes-container` (antes eram 4 fixos no JS);
- as sequências `Em,G` e `C,A7,Dm,G7`, que não apareciam antes;
- o input `placeholder="Nova sequência (ex.: Dm,G,C)"` e o botão `Cadastrar`.

`node --check static/assets/js/controllers/sequencia.js` passou.

## Latência (medição pontual, container local)

- Handler `get_similares_por_sequencia` para `Bm,G,D,A`: **42–51 ms** (3 execuções,
  após aquecimento).
- Requisição HTTP completa: **51–71 ms** (5 execuções).
- Loop antigo só com o teste de tag, no mesmo ambiente: **37–40 ms**.
- O caminho genérico por acordes (`/similares?acordes=...`) ficou em **450–820 ms**.

Observação honesta: as medições de `research/avaliacao-banco-e-runtime.md`
(17–20 ms de handler, 43–46 ms de tag) foram feitas em ambiente mais rápido. Aqui o
matching preparado fica próximo do custo do teste de tag antigo — o ganho real da
mudança é não depender de estado derivado e permitir sequências novas, não uma
redução de latência para as 6 originais. A preparação do bloco/vocabulário é feita
uma vez por requisição (reconstruí-la por música custava ~108 ms, medido e
corrigido durante a implementação).

## Como rodar

```bash
podman build -t ciframe .
podman run --rm --entrypoint python ciframe scripts/verifica_sequencias.py

podman run -d --name cif-http -p 8080:8080 ciframe
sleep 12
curl http://localhost:8080/sequencias
curl -H 'Content-Type: application/json' -d '{"acordes":"Dm,G,C"}' http://localhost:8080/sequencias
curl 'http://localhost:8080/similares?sequencia=bm,g,d,a'
```

## O que ficou de fora

- **Framework de testes unitários:** o projeto não tem um, e o escopo não pedia
  adicionar. A regressão e os contratos cobrem o caminho crítico.
- **Interação real no browser (cliques, submit do formulário):** o Chrome headless
  validou a renderização inicial e o catálogo vindo da API, mas não automatizei o
  fluxo de clique/cadastro na página; esse fluxo foi validado pela API e pelo
  controller (a página usa o mesmo `POST` testado com `curl`). A demonstração em
  vídeo/gif fica como entrega manual.
- **Concorrência e múltiplos workers:** o `Dockerfile` roda 1 worker; não testei
  `--workers > 1` nem escritas concorrentes no SQLite.
- **Carga/estresse e tamanho do catálogo:** sem teste de volume; o cadastro é aberto
  e sem teto por decisão de escopo.
- **Normalização musical:** acentos, enarmonia, sufixos (`7`, `9`, `add9`) e baixo
  invertido continuam fora — a comparação é por igualdade exata de token,
  insensível apenas a maiúsculas/minúsculas.
- **Paginação no servidor:** `Bm,G,D,A` (199) e `C,G,Am,F` (296) continuam
  truncados em 100 no cliente, como antes.
