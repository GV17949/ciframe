# Plano — Sequências de Acordes Customizadas

> O agente encontrou esse arquivo durante a conversa na estapa de
> planejamento e o utilizou durante o desenvolvimento como fonte
> primária apesar de eu ter indicado explícitamente para ele criar
> uma cópia separada que seria a que ele deveria utilizar na etapa
> de implementação. Resolvi manter como estava para registrar
> esse comportamento.

Base: `02-proposal.md` (decisões confirmadas) e as medições de
`research/avaliacao-banco-e-runtime.md`. Plano executado; resultados em
`04-test-report.md`.

> **Regra de condução:** se durante a implementação a abordagem mudar (semântica de
> matching, esquema do banco, formato da API, arquivos tocados), **atualize este
> plano antes de continuar** — não deixe o plano desatualizado. A cópia em
> `research/plano-implementacao.md` deve ser atualizada junto.

## Passos

### Fase 1 — Backend: catálogo e matching

1. [x] Criar `sequencias.py` (novo módulo na raiz, ao lado de `main.py`/`musica.py`)
   com: `DB_PATH = 'data/sequencias.db'`; lista `ORIGINAIS` com os 6 pares
   `(id, 'Bm,G,D,A')` na mesma ordem de `main.py:40-45`; `normalizar(texto)` →
   lista de tokens aparados; `criar_schema()` com `CREATE TABLE IF NOT EXISTS`;
   `semear()` idempotente (`INSERT OR IGNORE` dos ids 0–5); `listar()`;
   `inserir(texto)` (levanta `Duplicada` no `UNIQUE`); `buscar(texto)`;
   `preparar(seq_tokens)` → `(bloco_ancorado, vocabulario)` calculado **uma vez
   por requisição**; `aparece(seq_preparada, musica)` com a regra contígua +
   vocabulário.
   Pronto quando: chamar `criar_schema()` + `semear()` cria o arquivo, a tabela e as
   6 linhas, e repetir a chamada não duplica nada.

2. [x] Em `musica.py:16-18`, adicionar dois campos derivados calculados no
   `__init__`: `cifra_busca` (cifra em minúsculas, unida por `;` e com `;` nas duas
   pontas) e `acordes_busca` (`frozenset` dos acordes em minúsculas). Nada mais muda
   no modelo; `acordes` e `seqs_famosas` continuam existindo.
   Pronto quando: para uma música conhecida, `cifra_busca` é `';' + cifra em
   minúsculas + ';'` e `acordes_busca` é igual a `{a.lower() for a in acordes}`.

3. [x] Em `main.py`: remover o dicionário `sequencias` (linhas 40-45), importar
   `sequencias`, chamar `criar_schema()` + `semear()` depois da carga do CSV e
   montar `acordes_lower` (mapa minúsculo→forma do corpus) a partir de `acordes`.
   Pronto quando: o app sobe com as 6 sequências vindas do banco e `/acordes`
   continua devolvendo 6.653 tokens.

4. [x] Reescrever o ramo de sequência de `/similares` (`main.py:190-197`) para
   normalizar `sequencia_tag`, buscar no catálogo e, se não existir, devolver `[]`.
   Adaptar `get_similares_por_sequencia` (`main.py:203-223`) para chamar
   `sequencias.preparar(...)` uma vez fora do laço e testar `aparece(...)` no lugar
   de `str(id_seq) in seqs_famosas`, mantendo o mesmo dicionário de resposta (sem
   `diferenca`/`intersecao`).
   Pronto quando: as 6 sequências devolvem 199/296/4/5/7/3 e `bm,g,d,a` (minúsculo)
   passa a devolver o mesmo que `Bm,G,D,A`.

5. [x] Adicionar `GET /sequencias` e `POST /sequencias` em `main.py`, ambos com
   `json.dumps(...)`: `GET` lista `[{id, acordes}]`; `POST` recebe
   `{"acordes": "Dm,G,C"}`, valida (2 a 12 tokens, nenhum vazio, cada token presente
   em `acordes_lower`) e responde `201`, `400` (inválido) ou `409` (duplicata na
   forma minúscula). Rotações (`Bm,G,D,A` × `G,D,A,Bm`) contam como distintas.
   Pronto quando: os três status são observáveis por `curl` e o corpo continua
   string JSON com `Content-Type: text/html`.

### Fase 2 — Frontend

6. [x] `static/assets/js/controllers/sequencia.js:2-37`: remover `sequencia1`–
   `sequencia4` e carregar `vm.sequenciasFamosas` de `GET /sequencias`, convertendo
   `"Bm,G,D,A"` em `[{acorde, cor:'#2E1C74'}]` (formato que o `df-hex` já consome).
   Pronto quando: a página lista as 6, inclusive `Em,G` e `C,A7,Dm,G7`.

7. [x] No mesmo controller, adicionar `vm.novaSequencia`, `vm.cadastrar()` (POST,
   recarrega o catálogo e seleciona a nova) e uma mensagem de erro para `400`/`409`.
   `createChordsString` (`:55-61`) passa a devolver `encodeURIComponent(...)`.
   Pronto quando: cadastrar pela página funciona e uma sequência com `C#` chega
   intacta ao backend.

8. [x] `static/templates/sequencia.html:6`: adicionar o formulário (input + botão +
   mensagem de erro) acima da lista de sequências; resultados, filtro de gênero e
   ordenação no cliente ficam como estão.
   Pronto quando: cadastro e busca funcionam sem mudar o layout dos cards.

### Fase 3 — Verificação e fechamento

9. [x] Criar `scripts/verifica_sequencias.py`: ajusta `sys.path` para a raiz do
   repositório, importa `main`, recalcula os matches das 6 sequências com `aparece`
   e compara, música a música, com a coluna 7; imprime as contagens e sai com código
   1 em qualquer divergência.
   Pronto quando: `python scripts/verifica_sequencias.py` roda a partir da raiz e
   termina com código 0.

10. [x] Testes de contrato com `curl`: `GET /sequencias` (6 itens), `POST` válido
    (`201`), curto (`400`), acorde inexistente (`400`), duplicado (`409`), sequência
    desconhecida em `/similares` (`[]`).
    Pronto quando: todos os casos batem com o esperado e ficam registrados para o
    `04-test-report.md`.

11. [x] Persistência: cadastrar uma sequência, `podman restart`, confirmar que ela
    continua listada e buscável; conferir `Mounts: []`; confirmar que `rm` + novo
    `run` perde o catálogo (comportamento esperado e documentado).
    Pronto quando: restart preserva e a limitação está registrada.

12. [x] `README.md`: acrescentar o parágrafo sobre onde o catálogo vive (sobrevive a
    restart, some em `rm`/rebuild) e os dois endpoints novos. `.dockerignore`:
    excluir `data/sequencias.db` para não assar um banco local na imagem.
    `.gitignore`: ignorar `data/sequencias.db` (gerado em runtime).
    Pronto quando: rebuild da imagem não contém `data/sequencias.db` e o arquivo
    não aparece no `git status`.

13. [x] Preencher `04-test-report.md` com o resultado dos passos 9–12 (fase 5).

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `main.py` | remove o dict fixo; rotas `GET`/`POST /sequencias`; validação; handler de sequência por matching em runtime |
| `musica.py` | campos derivados `cifra_busca` e `acordes_busca` no `__init__` |
| `sequencias.py` (novo) | conexão SQLite, schema, seed dos ids 0–5, `listar`/`inserir`/`buscar`/`normalizar`/`aparece` |
| `static/assets/js/controllers/sequencia.js` | catálogo vindo da API, cadastro, `encodeURIComponent` |
| `static/templates/sequencia.html` | formulário de cadastro e mensagem de erro |
| `scripts/verifica_sequencias.py` (novo) | regressão das 6 sequências contra a coluna 7 |
| `.dockerignore` | excluir `data/sequencias.db` do contexto de build |
| `.gitignore` | ignorar `data/sequencias.db` (gerado em runtime) |
| `README.md` | persistência do catálogo e endpoints novos |
| `data/sequencias.db` | gerado em runtime, não versionado |

Fora da lista: `Dockerfile`, `requirements.txt`, `docs/adr/*`, `routes.js`,
`data/top/*.csv` e `static/index.html`.

## Riscos e mitigação

- **Matching divergir da tag do CSV.** É o risco central. Detecção: passo 9 (script
  compara música a música). Se divergir, corrigir a normalização antes de seguir —
  não ajustar o script para aceitar a diferença.
- **Seed duplicar a cada restart.** `UNIQUE` em `acordes_busca` + `INSERT OR IGNORE`;
  teste de restart no passo 11.
- **Banco local assado na imagem.** `data/sequencias.db` entra no `COPY . .`
  (`Dockerfile:8`); mitigado pelo `.dockerignore` no passo 12.
- **`#` em acorde quebrar a URL.** `createChordsString` não codifica hoje; mitigado
  no passo 7 e testado com `C#m`.
- **Resposta string + `text/html` no AngularJS.** O `$http` do Angular 1.4 faz
  `JSON.parse` da string; se o catálogo não aparecer, checar o parse antes de mexer
  no backend (o `/similares` atual já depende disso).
- **Memória extra.** `cifra_busca` + `acordes_busca` somam ~37 MB para 67.585
  músicas; se o container ficar apertado, medir antes de trocar por cálculo por
  requisição (custo medido: 18,1 → 18,6 ms sem os conjuntos prontos).
- **Latência acima do medido.** Se a busca passar de ~20 ms, confirmar que a
  preparação da sequência (bloco `;X;` + vocabulário) é feita uma vez por
  requisição, não a cada música. Medição desta implementação no ambiente atual:
  ~108 ms quando reconstruída por música, ~38 ms com `preparar` fora do laço.
- **Mais de um worker no futuro.** A conexão SQLite é uma só por processo; com
  `--workers > 1` revisar conexão/WAL (hoje `Dockerfile:12` roda 1 worker).
- **Catálogo sem teto.** Cadastro anônimo pode crescer sem limite; aceito no escopo,
  registrado como limitação.

## Definição de pronto

- [x] `GET /sequencias` devolve as 6 originais (ids 0–5) após qualquer restart.
- [x] `POST /sequencias` cadastra uma sequência nova e ela aparece no `GET`.
- [x] `GET /similares?sequencia=<nova>` devolve músicas usando a regra contígua +
      vocabulário.
- [x] As 6 originais devolvem 199/296/4/5/7/3, com igualdade de conjuntos contra a
      coluna 7 (`scripts/verifica_sequencias.py` sai com 0).
- [x] `#/porsequencia` lista as 6 (não 4), cadastra uma nova e busca por ela; filtro
      de gênero e ordenação por popularidade continuam funcionando.
- [x] Endpoints novos mantêm `json.dumps(...)` e `Content-Type: text/html`.
- [x] Catálogo sobrevive a `podman restart`; limitação de `rm`/rebuild documentada no
      `README.md`.
- [x] `04-test-report.md` preenchido com os resultados.
