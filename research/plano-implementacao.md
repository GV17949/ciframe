# Sequências de Acordes Customizadas — Design Document

> Cópia de referência do plano (`docs/features/sequencias-customizadas/03-plan.md`),
> no formato de `~/reppit-framework/templates/design_doc_template.md`. Plano
> executado; resultados em `04-test-report.md`.

## Current Context

- Backend Flask de arquivo único (`main.py`) carrega `data/top/dataset_final.csv`
  em memória na importação (`main.py:49-98`): 67.585 músicas, sem banco de dados.
- As 6 sequências "famosas" são um dicionário fixo (`main.py:40-45`) e só são
  descobertas por uma coluna pré-computada no CSV (`SEQ_FAMOSA`, coluna 7),
  produzida offline por `scripts/generate_data_set.py:7-24` e concatenada em
  `:84-88`.
- A página `#/porsequencia` tem um catálogo próprio de 4 sequências em JavaScript
  (`static/assets/js/controllers/sequencia.js:2-37`), diferente das 6 do backend.
- Lacunas: cadastrar sequência exige editar o gerador, regerar o CSV e redeployar;
  não há persistência de nada; o frontend não reflete o backend.
- **Regra de condução:** durante a implementação, qualquer mudança de abordagem
  (semântica, esquema, API, arquivos tocados) exige atualizar o plano **antes** de
  continuar; este documento e `03-plan.md` andam juntos.

## Requirements

### Functional Requirements

- Cadastro anônimo de sequência (lista ordenada de 2 a 12 acordes), sem login.
- Catálogo persistido em banco; sobrevive a restart do container.
- Busca por qualquer sequência do catálogo (6 originais + novas) via
  `GET /similares?sequencia=...`, com o mesmo formato de resposta de hoje.
- As 6 originais mantêm exatamente os resultados atuais (199/296/4/5/7/3).
- `#/porsequencia` lista o catálogo real e permite cadastrar; filtro de gênero e
  ordenação por popularidade continuam.
- Endpoints continuam devolvendo `json.dumps(...)` (não `jsonify`).

### Non-Functional Requirements

- Container único, local-only, sem serviço adicional (`00-enunciado.md:63-65`).
- Sem dependência nova: `sqlite3` da stdlib.
- Busca em runtime na faixa medida de 17–20 ms de handler (43–46 ms no caminho
  atual); HTTP ~48–50 ms.
- Carga do CSV inalterada em comportamento; ~37 MB extras em memória para as
  strings/conjuntos derivados.
- Nenhuma métrica/log estruturado a introduzir (não há infraestrutura hoje).
- Persistência limitada à camada gravável do container (restart, não `rm`/rebuild).

## Design Decisions

### 1. Semântica de matching

Implementar a mesma regra do gerador, em runtime, porque:

- Reproduz a coluna 7 música a música (199/296/4/5/7/3, igualdade de conjuntos),
  que é o critério de regressão (`00-enunciado.md:66-67`, `01-research.md:13-17`).
- Custa 17–20 ms por busca contra 43–46 ms do caminho atual, e o laço O(67.585)
  já existe.
- Alternativas (contígua sem vocabulário: 866/1.216/3.110/96/1.039/132;
  subsequência ordenada: 4.763/5.887/13.643/427/3.641/280) mudariam as 6 e
  quebrariam a regressão.

Regra: a sequência aparece como bloco contíguo e ordenado da cifra **e** o
vocabulário da música está contido no vocabulário da sequência. Comparação em
minúsculas, ancorada em `;X;` para não casar através da fronteira de tokens. O
bloco ancorado e o vocabulário da sequência são calculados por `preparar` uma vez
por requisição, antes do laço sobre as músicas.

### 2. Banco de dados

SQLite (`sqlite3`), arquivo `data/sequencias.db`, porque:

- Já vem na imagem (3.46.1); 0,126 ms para abrir+ler o catálogo, 8 KB, escrita com
  transação (0,330 ms).
- TinyDB/`shelve` não têm transação; LMDB exige API de bytes e `map_size`; DuckDB
  custou 16,4 ms e 536 KB para 6 linhas; SQLAlchemy só acrescenta camada;
  cliente-servidor violaria o container único.
- Sem `VOLUME`/volume nomeado: o requisito é sobreviver a restart, e o deploy de
  `docs/adr/0001-local-only-docker-deploy.md` fica intacto.

### 3. Quando calcular o match

Em runtime, por requisição, porque:

- Zero estado derivado para invalidar quando o CSV muda (ele é lido uma vez na
  importação, `main.py:49-98`).
- Pré-cálculo no cadastro (16,7–20,5 ms por sequência, 514 linhas hoje) e
  pré-cálculo na carga (202,6 ms) só ganhariam em volume que o deploy não tem.
- Índice de bigramas (3,06 s de carga, consultas de 0,04–3,09 ms) fica como
  evolução futura, não como parte desta mudança.

### 4. Validação e duplicidade do cadastro

Validar contra `/acordes` e deduplicar pela forma exata normalizada, porque:

- Evita sequência que nunca pode casar (acorde fora do corpus).
- `UNIQUE` em `acordes_busca` resolve duplicata exata com `409`.
- Rotações (`Bm,G,D,A` × `G,D,A,Bm`) são mantidas como sequências distintas, para
  não impor uma noção de equivalência que a regra de matching não usa.

### 5. Fonte do catálogo no frontend

`#/porsequencia` passa a ler `GET /sequencias`, porque:

- Elimina a divergência 4 × 6 e torna o catálogo a única fonte de verdade.
- O template já renderiza `[{acorde, cor}]`; só a origem dos dados muda.

## Technical Design

### 1. Core Components

```python
# sequencias.py (novo)
from typing import Optional
from musica import Musica
DB_PATH: str = 'data/sequencias.db'
ORIGINAIS: list[tuple[int, str]] = [(0, 'Bm,G,D,A'), (1, 'C,G,Am,F'), (2, 'Em,G'),
                                    (3, 'C,A7,Dm,G7'), (4, 'Gm,F'), (5, 'C,C7,F,Fm')]

class SequenciaDuplicada(Exception): ...

def normalizar(texto: str) -> list[str]: ...
def criar_schema() -> None: ...
def semear() -> None: ...
def listar() -> list[dict]: ...          # [{'id': 0, 'acordes': 'Bm,G,D,A'}, ...]
def inserir(acordes: str) -> dict: ...   # grava e devolve {'id': ..., 'acordes': ...}
def buscar(acordes: str) -> Optional[dict]: ...
def preparar(seq_tokens: list[str]) -> tuple[str, frozenset]: ...  # uma vez por busca
def aparece(seq_preparada: tuple, musica: Musica) -> bool: ...
```

```python
# musica.py (alteração em __init__, linhas 16-18)
self.cifra_busca: str = ';' + ';'.join(cifra).lower() + ';'   # bloco contíguo
self.acordes_busca: frozenset = frozenset(a.lower() for a in cifra)  # vocabulário
```

### 2. Data Models

```sql
CREATE TABLE IF NOT EXISTS sequencias (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  acordes       TEXT NOT NULL,            -- como digitado, aparado
  acordes_busca TEXT NOT NULL UNIQUE,     -- minúsculo, usado na busca/dedupe
  criado_em     TEXT NOT NULL             -- ISO 8601
);
```

- Seed idempotente: ids 0–5, `INSERT OR IGNORE` por `acordes_busca`; novas a partir
  de 6.
- Nenhuma tabela de músicas: `musicas`/`generos` continuam no CSV em memória.

### 3. Integration Points

| Endpoint | Entrada | Saída | Erros |
|---|---|---|---|
| `GET /sequencias` | — | `[{"id":0,"acordes":"Bm,G,D,A"}, ...]` | — |
| `POST /sequencias` | `{"acordes":"Dm,G,C"}` | `201` + `{"id":6,"acordes":"Dm,G,C"}` | `400` inválido, `409` duplicada |
| `GET /similares?sequencia=...` | acordes separados por vírgula, `&generos=` opcional | lista de músicas (mesmo formato de hoje) | desconhecida → `[]` |

- Todos com `json.dumps(...)` e `Content-Type: text/html` (legado,
  `00-enunciado.md:68`).
- Fluxo de busca: normaliza → `buscar` no catálogo → `apply_filtro` por gênero
  (`main.py:266-272`) → `aparece` por música → dicionário de resposta atual.

### 4. Files Changes

| Arquivo | Mudança |
|---|---|
| `main.py` | remove dict fixo; rotas de catálogo; validação; handler por matching |
| `musica.py` | `cifra_busca` e `acordes_busca` |
| `sequencias.py` (novo) | banco, seed, normalização, matching |
| `static/assets/js/controllers/sequencia.js` | catálogo da API, cadastro, encoding |
| `static/templates/sequencia.html` | formulário de cadastro |
| `scripts/verifica_sequencias.py` (novo) | regressão das 6 |
| `.dockerignore` | excluir `data/sequencias.db` |
| `.gitignore` | ignorar `data/sequencias.db` (gerado em runtime) |
| `README.md` | persistência e endpoints novos |
| `data/sequencias.db` | gerado em runtime, não versionado |

Únicos arquivos tocados; `Dockerfile`, `requirements.txt`, `docs/adr/*`,
`routes.js`, `data/top/*.csv` e `static/index.html` ficam fora.

## Implementation Plan

Sem estimativas de tempo (decisão do projeto). Ordem e critério de pronto por
passo estão em `03-plan.md`; resumo:

1. Phase 1: Backend — `sequencias.py` (schema, seed, normalização, `preparar` +
   `aparece`); campos derivados em `musica.py`; `main.py` com catálogo, rotas e
   handler; validação (`400`/`409`).
2. Phase 2: Frontend — controller lendo `GET /sequencias`, cadastro, mensagens de
   erro, `encodeURIComponent`; template com formulário.
3. Phase 3: Verificação e fechamento — `scripts/verifica_sequencias.py`, testes de
   contrato com `curl`, teste de restart, `.dockerignore`, `.gitignore`,
   `README.md`, `04-test-report.md`.

Se a abordagem mudar em qualquer fase, atualizar `03-plan.md` e este documento antes
de continuar a implementação.

## Testing Strategy

### Unit Tests

- Não há framework de testes no repositório; a verificação é por script.
- `scripts/verifica_sequencias.py`: recalcula as 6 com `preparar`/`aparece` e
  compara, música a música, com `musica.seqs_famosas`; imprime contagens; sai com
  código 1 em divergência. Casos de borda cobertos por ele: cifra vazia (8.141
  músicas), repetição de acorde, acorde fora do vocabulário.
- Normalização: `normalizar(' Bm , G,D,A ')` → `['Bm','G','D','A']`; string vazia,
  token vazio e 1 token devem ser rejeitados antes do banco.

### Integration Tests

- `curl`: `GET /sequencias` (6 itens), `POST` válido/curto/inexistente/duplicado,
  sequência desconhecida em `/similares`, busca minúscula.
- Persistência: cadastrar → `podman restart` → conferir `GET /sequencias` e uma busca;
  `podman inspect` com `Mounts: []`; `rm` + novo `run` perde o catálogo (esperado).
- Frontend manual: 6 sequências listadas, cadastro, busca, filtro de gênero,
  ordenação por popularidade, sequência com `C#`.

## Observability

Não se aplica: não há logging estruturado nem métricas no projeto; o container expõe
apenas o access log do gunicorn. A latência da busca é verificada pontualmente nos
testes (17–20 ms de handler), sem instrumentação permanente.

## Future Considerations

### Potential Enhancements

- Paginação/ordenação no servidor (hoje a página não envia `pagina` e resultados
  acima de 100 são truncados: `Bm,G,D,A` 199, `C,G,Am,F` 296).
- Tabela derivada ou índice de bigramas se o volume de requisições justificar.
- Volume nomeado/backup se durabilidade entre rebuilds virar requisito.
- Edição/remoção de sequências, moderação e teto de catálogo.
- Normalização enarmônica/sufixos (hoje comparação exata de token).

### Known Limitations

- Catálogo perdido em `rm` + novo `run` e em rebuild da imagem.
- Um worker; buscas concorrentes serializam.
- Coluna 7 do CSV deixa de ser usada no caminho de sequências (dado morto).
- Cadastro aberto e sem limite de tamanho do catálogo.

## Dependencies

### Development Dependencies

- Nenhuma dependência nova em runtime (`sqlite3` é stdlib; Flask/gunicorn já estão em
  `requirements.txt`).
- Ferramentas de verificação: `python3`, `podman`, `curl`.
- Sem framework de teste; o script de regressão roda com o Python do projeto.

## Security Considerations

- Cadastro anônimo por requisito: sem autenticação/autorização.
- Entrada validada no servidor (2–12 tokens, tokens não vazios, acordes existentes),
  independentemente da validação no frontend.
- SQL sempre parametrizado; nenhuma interpolação de string na query.
- Sem rate limit nem moderação — aceito no escopo e registrado como limitação.

## Rollout Strategy

1. Desenvolvimento local com `python main.py` (porta 5000).
2. Verificação: `scripts/verifica_sequencias.py`, `curl` e teste manual da página.
3. Build da imagem (`docker build -t ciframe .`) e execução em `:8080`; o primeiro
   start cria `data/sequencias.db` e semeia as 6.
4. `restart` preserva o catálogo; `rm`/rebuild reinicia vazio (documentado).
5. Sem staging: deploy é local-only (`docs/adr/0001-local-only-docker-deploy.md`).

## References

- `docs/features/sequencias-customizadas/00-enunciado.md`
- `docs/features/sequencias-customizadas/01-research.md`
- `docs/features/sequencias-customizadas/02-proposal.md`
- `docs/features/sequencias-customizadas/03-plan.md` (plano executável)
- `docs/adr/0001-local-only-docker-deploy.md`
- `docs/adr/0002-persist-custom-sequences.md`
- `research/sequencias-e-persistencia.md`
- `research/avaliacao-banco-e-runtime.md`
- `~/reppit-framework/templates/design_doc_template.md`
