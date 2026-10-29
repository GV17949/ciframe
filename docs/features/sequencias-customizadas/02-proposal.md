# Proposta — Sequências de Acordes Customizadas

## Abordagem escolhida

Catálogo de sequências em **SQLite** (biblioteca padrão do Python), com **matching
calculado em runtime** sobre a cifra de cada música, usando a mesma regra que hoje
gera a coluna `SEQ_FAMOSA`. Não há estado derivado: as 6 sequências originais são
semeadas no banco e passam pelo mesmo caminho das sequências cadastradas. A página
`#/porsequencia` deixa de ter catálogo fixo em JavaScript e passa a ler o catálogo
da API, além de ganhar o formulário de cadastro.

Base: `research/sequencias-e-persistencia.md` e
`research/avaliacao-banco-e-runtime.md` (medições no container, `HEAD` `fb97001`).

### Algoritmo de matching

Seja X = sequência (lista ordenada de acordes) e C = `Musica.cifra`
(`musica.py:16`, a cifra da música como lista ordenada, com repetições). Uma música
**casa** com X se, e somente se:

1. **Ocorrência contígua e ordenada:** existe `i` tal que
   `C[i:i+len(X)] == X`. Ordem dos acordes importa; os acordes precisam ser
   adjacentes; repetições dentro do bloco são preservadas.
2. **Vocabulário contido:** `set(C) ⊆ set(X)`, ou seja, a música inteira só usa
   acordes que aparecem na sequência.

Implementação: comparar `';'+X+';'` dentro de `';'+C+';'` com ambos em minúsculas
(evita casamento atravessando a fronteira de dois tokens) e testar
`set(C) <= set(X)`. Para não pagar `lower()`/`join` a cada requisição, a string
minúscula unida é calculada uma vez por música na carga (~10,4 MB para as 67.585
músicas).

- **Por que esta regra:** é exatamente a de `scripts/generate_data_set.py:7-24` e
  reproduz a coluna 7 música a música: 199 / 296 / 4 / 5 / 7 / 3 (igualdade de
  conjuntos, não só de contagem). É o critério de regressão de
  `00-enunciado.md:66-67` e o bar mínimo de `01-research.md:13-17`.
- **Custo medido:** 16,7–20,5 ms por busca no handler, contra 43,0–45,6 ms do
  caminho atual (que varre as 67.585 músicas testando a tag). O laço O(67.585) já
  existe hoje; trocar o teste de tag pela comparação de substring não acrescenta
  uma segunda passada.
- **O que a regra não faz:** não normaliza acentos, equivalência enarmônica,
  sufixos (`7`, `9`, `add9`) nem baixo invertido (`/F#`); a comparação é por
  igualdade exata de token, como em `main.py:11-23`, apenas insensível a
  maiúsculas/minúsculas. Sequências aceitam de 2 a 12 acordes.
- A coluna 7 do CSV deixa de ser consultada no caminho de sequências; o dado
  permanece no arquivo, sem uso (a coluna é gerada por `generate_data_set.py:84-88`).

### Banco de dados

**SQLite via `sqlite3` da stdlib**, arquivo único em `data/sequencias.db`.

- **Por quê:** já está na imagem (3.46.1), zero dependência nova em
  `requirements.txt`; abrir+ler o catálogo inteiro custa 0,126 ms (0,016 ms com
  conexão mantida aberta) e 8 KB de arquivo; escrita com commit, 0,330 ms;
  transacional, ao contrário de `shelve` e TinyDB; sem camada extra, ao contrário
  de SQLAlchemy. DuckDB ficou fora por 16,4 ms de abertura e 536 KB para 6 linhas;
  cliente-servidor, por exigir serviço adicional (`00-enunciado.md:63-65`).
- **Persistência:** o arquivo fica na camada gravável do container. Sobrevive a
  `stop`/`start` e `restart`; **não** sobrevive a `rm` + novo `run` nem a rebuild da
  imagem. Não haverá `VOLUME` nem volume nomeado — o requisito é sobreviver a
  reinício (`00-enunciado.md:52-53`) e o deploy continua o de
  `docs/adr/0001-local-only-docker-deploy.md`. Essa perda precisa estar escrita no
  `README.md`.
- **Processo:** `Dockerfile:12` roda gunicorn sem `--workers` (1 worker, medido).
  A conexão é aberta uma vez na carga do módulo; se o número de workers mudar, cada
  processo terá a sua conexão (leitores concorrentes são suportados; escritas são
  serializadas pelo SQLite).

### Esquema de dados (alto nível)

```
sequencias
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  acordes     TEXT NOT NULL          -- como o visitante digitou, ex.: "Bm,G,D,A"
  acordes_busca TEXT NOT NULL UNIQUE -- minúsculo, usado para busca e deduplicação
  criado_em   TEXT NOT NULL          -- ISO 8601
```

- As 6 originais são semeadas com `id` 0–5 (mesmos ids de `main.py:40-45`), de forma
  idempotente na carga; novas sequências começam em 6.
- Nenhuma tabela de músicas: `musicas`/`generos` continuam vindo do CSV em memória
  (`main.py:49-98`).

### API

Todos os endpoints mantêm `json.dumps(...)` como corpo e o `Content-Type: text/html`
legado (`00-enunciado.md:68`).

- `GET /sequencias` → `[{"id": 0, "acordes": "Bm,G,D,A"}, ...]`, ordenado por `id`
  (as 6 originais primeiro).
- `POST /sequencias` → corpo `{"acordes": "Dm,G,C"}`; `201` com o registro criado.
  `400` se a lista tiver menos de 2 acordes, token vazio ou acorde fora do conjunto
  `/acordes` (6.653 tokens, `main.py:39`); `409` se a forma normalizada já existir.
- `GET /similares?sequencia=<acordes separados por vírgula>[&generos=...]` mantém o
  contrato e o formato da resposta de hoje (sem `diferenca`/`intersecao`), mas passa
  a resolver a sequência pelo catálogo normalizado em vez do dicionário fixo
  (`main.py:190-197`) e a calcular os matches em vez de testar a tag
  (`main.py:203-223`). Sequência desconhecida continua devolvendo `[]`; a busca fica
  insensível a maiúsculas (hoje `bm,g,d,a` devolve `[]`).
- Sem edição, remoção ou moderação nesta entrega.

### Frontend

- `static/assets/js/controllers/sequencia.js:2-37`: removem-se `sequencia1`–`sequencia4`;
  `activate`/inicialização passa a fazer `GET /sequencias` e montar
  `vm.sequenciasFamosas` no formato que o template já consome
  (`[{acorde, cor}]`), preservando o hexágono de `df-hex`.
- O formulário de cadastro (campo de acordes separados por vírgula + botão) faz
  `POST /sequencias`, recarrega o catálogo e seleciona a sequência criada.
- `createChordsString` (`sequencia.js:55-61`) passa a usar `encodeURIComponent`: hoje
  a string não é codificada e um acorde com `#` vira fragmento de URL.
- `static/templates/sequencia.html:6` ganha o bloco do formulário; o restante do
  layout, o filtro de gênero e a ordenação por popularidade no cliente ficam como
  estão.
- Efeito colateral desejado: a página passa a mostrar as 6 sequências, incluindo
  `Em,G` (4 músicas) e `C,A7,Dm,G7` (5 músicas), que hoje não aparecem.

### Como será verificado

1. **Regressão (bar mínimo):** script que roda o matching em runtime sobre as 67.585
   músicas e compara, música a música, com a coluna 7 para as 6 sequências —
   esperado 199/296/4/5/7/3 e igualdade de conjuntos.
2. **Contrato da API:** `GET /sequencias` com 6 itens após o seed; `POST` válido
   (`201`), curto (`400`), acorde inexistente (`400`), duplicado (`409`); sequência
   desconhecida em `/similares` → `[]`; corpo sempre `json.dumps`, `Content-Type`
   `text/html`.
3. **Persistência:** cadastrar, `podman restart`, conferir que a sequência continua
   listada e buscável; conferir `Mounts: []`; documentar que `rm` + novo `run` perde
   o catálogo.
4. **Frontend:** página lista 6; cadastrar uma sequência nova e buscar por ela;
   filtro de gênero continua funcionando; `Em,G` retorna 4 e `C,A7,Dm,G7` retorna 5;
   sequência com `C#m` funciona na URL.
5. **Latência:** handler em 17–20 ms e requisição HTTP na mesma faixa de hoje
   (48–50 ms medidos no container).

## Alternativas consideradas e descartadas

1. **Pré-calcular no cadastro e gravar os ids das músicas (tabela derivada).**
   Pagaria 16,7–20,5 ms uma vez por sequência e a leitura cairia para uma consulta;
   descartada porque cria estado derivado (514 linhas hoje, crescendo com
   catálogo × matches) que precisa ser recalculado se o CSV mudar — o CSV é lido uma
   vez na importação (`main.py:49-98`) — e porque o ganho só aparece em volume de
   requisições que o deploy atual (1 worker, ~20 ms por busca) não tem.
2. **TinyDB, `shelve`/`dbm`, LMDB.** Todos abaixo de 0,3 ms e 21 KB, mas: TinyDB
   reescreve o arquivo inteiro a cada escrita e não tem transação; `shelve` grava
   pickle sem transação; LMDB exige API de bytes e `map_size`. O `sqlite3` já vem na
   imagem e cobre o caso com transação.
3. **Semânticas mais permissivas** — contígua sem condição de vocabulário
   (866/1.216/3.110/96/1.039/132) ou subsequência ordenada
   (4.763/5.887/13.643/427/3.641/280). Descartadas porque mudariam o resultado das 6
   sequências e quebrariam `00-enunciado.md:66-67`.
4. **Manter as 6 na tag do CSV e calcular só as novas.** Manteria a regressão, mas
   criaria duas semânticas conviventes: duas sequências iguais poderiam dar
   resultados diferentes conforme a origem.
5. **Volume Docker / `VOLUME` no `Dockerfile`.** Mudaria o contrato de deploy
   (`Dockerfile`, `README.md`) para cobrir `rm`/rebuild, que o requisito não pede.
6. **Índice de bigramas para consulta em 0,04–3,09 ms.** Custa 3,06 s e ~1 M entradas
   na carga, o que quase dobra o startup atual (3,7 s), para um ganho que o volume
   atual não justifica.

## Escopo explícito

**Dentro do escopo:**

- Tabela `sequencias` em SQLite com seed idempotente das 6 originais (ids 0–5).
- Matching em runtime com a regra contígua + vocabulário, aplicada a todas as
  sequências.
- `GET /sequencias`, `POST /sequencias` e adaptação de `GET /similares?sequencia=`.
- `#/porsequencia` lendo o catálogo da API, com formulário de cadastro e codificação
  da URL.
- Regressão das 6 sequências e persistência do catálogo entre reinícios.

**Fora do escopo (e por quê):**

- Migrar músicas/gêneros para o banco — `00-enunciado.md:60-62` fixa o CSV.
- Volume Docker / `VOLUME` — requisito é reinício, não recriação do container.
- Paginação e ordenação no servidor: a página continua sem enviar `pagina`, então
  `Bm,G,D,A` (199) e `C,G,Am,F` (296) mostram no máximo 100 itens, como hoje.
- Edição, remoção, autenticação e moderação do catálogo aberto.
- Normalização enarmônica, de sufixos ou de baixo invertido.
- Regenerar a coluna `SEQ_FAMOSA` do CSV e otimizações de índice.
