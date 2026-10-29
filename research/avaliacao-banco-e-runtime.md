# Avaliação — banco embarcado para o catálogo e matching em runtime

Nota de análise, companheira de
[`sequencias-e-persistencia.md`](sequencias-e-persistencia.md). O documento anterior
descreve o que existe; este pesa prós e contras das opções de banco e de rodar em
runtime a regra que hoje só existe em `scripts/generate_data_set.py`, com medições
feitas no container. **A escolha não é feita aqui** — ela pertence a
`docs/features/sequencias-customizadas/02-proposal.md` e à ADR
`docs/adr/0002-persist-custom-sequences.md`, que estava em branco quando esta nota
foi escrita e foi preenchida depois, com as decisões confirmadas.

Base: `HEAD` = `fb97001`. Todas as medições foram feitas na imagem
`localhost/ciframe-research` (construída a partir deste repositório,
`python:3.9-slim`, Python 3.9.25), em um único processo; tempos em ms são o menor
valor de 3 a 5 repetições, salvo indicação em contrário.

## 0. O que está sendo comparado

Duas decisões independentes:

1. **Onde persistir o catálogo de sequências.** O que precisa sobreviver a reinício
   são poucas linhas (6 hoje), não as 67.585 músicas:
   `docs/features/sequencias-customizadas/00-enunciado.md:60-62` fixa que músicas e
   gêneros continuam vindo do CSV em memória e que só o catálogo de sequências
   precisa de persistência; `00-enunciado.md:63-65` fixa container único, sem
   serviço adicional.
2. **Como decidir que a sequência X aparece na música Y.** Hoje a decisão vem
   pronta na coluna 7 do CSV (`SEQ_FAMOSA`, `main.py:33`), gerada offline por
   `scripts/generate_data_set.py:7-24`. A alternativa é aplicar a mesma regra em
   runtime sobre `Musica.cifra` (`musica.py:16`).

Restrição que atravessa as duas: as 6 sequências atuais precisam continuar
devolvendo os mesmos resultados (`00-enunciado.md:66-67`), e o processo é um só
(`Dockerfile:12`, sem `--workers`; 2 PIDs medidos, master + 1 worker).

## 1. Banco: prós e contras por opção

Custo medido de **abrir e ler as 6 linhas do catálogo**, em 200 ciclos
abrir→ler→fechar (DuckDB: 50 ciclos), e tamanho do arquivo resultante:

| Opção | Dependência nova | open+read (ms) | bytes p/ 6 linhas | Escrita medida |
|---|---|---:|---:|---|
| `sqlite3` (stdlib) | não | 0,126 | 8.192 | 0,330 ms (insert/commit) |
| `sqlite3`, conexão global reaproveitada | não | 0,016 | 8.192 | — |
| `shelve`/`dbm.gnu` (stdlib) | não | 0,253 | 16.384 | — |
| TinyDB 4.8.2 | sim | 0,118 | 243 | — |
| DuckDB 1.4.5 | sim | 16,363 | 536.576 | — |
| LMDB 3.0.0 | sim | 0,136 | 20.480 | — |
| SQLAlchemy 2.0.55 + `sqlite3` | sim | 0,184 | 8.192 | — |
| PostgreSQL, MySQL/MariaDB, Redis, MongoDB | sim (serviço) | não medido | — | — |

A diferença entre as opções não está em throughput — o catálogo tem 6 linhas e
cresce devagar — e sim em peso de dependência, custo de abertura e formato do
arquivo. Pelo conjunto: `sqlite3`, `shelve`/`dbm`, TinyDB e LMDB ficam todos abaixo
de 0,3 ms e de 21 KB, então nenhum deles é limitante para o volume previsto;
DuckDB é o único fora de escala (16 ms e 536 KB para 6 linhas); SQLAlchemy
acrescenta 0,058 ms e uma dependência sobre o `sqlite3`; cliente-servidor não cabe
na restrição de container único. O que separa as opções dentro do primeiro grupo é
garantia de escrita (transação em `sqlite3` e LMDB, ausente em `shelve` e TinyDB) e
tipo de dependência (stdlib em `sqlite3`/`shelve`).

### `sqlite3` (stdlib)

- **Prós:** já está na imagem (3.46.1, medido no container); zero dependência
  nova em `requirements.txt`; 8 KB e 0,126 ms para o catálogo inteiro; 0,016 ms se
  a conexão for mantida aberta; escrita transacional (0,330 ms incluindo commit);
  arquivo único, copiável para a imagem pelo `COPY . .` de `Dockerfile:8`; leitura
  concorrente segura entre processos.
- **Contras:** exige DDL e SQL para o que é uma lista de 6 a algumas dezenas de
  itens; escrita concorrente entre múltiplos workers exigiria atenção (hoje há 1
  worker); schema precisa ser versionado à mão.
- **Balanço:** o custo medido é o menor entre as opções que dão transação e
  arquivo único, e não acrescenta dependência.

### `shelve` / `dbm.gnu` (stdlib)

- **Prós:** também é stdlib; API de dicionário, sem SQL; 0,253 ms e 16 KB;
  backend `dbm.gnu` confirmado disponível na imagem.
- **Contras:** valores passam por `pickle` (arquivo não inspecionável e não
  portável entre versões/plataformas); sem transação, sem controle de concorrência
  e sem recuperação após escrita interrompida; 16 KB para 6 chaves mostra o
  overhead do backend; o backend efetivo depende da plataforma.
- **Balanço:** mais simples de escrever que SQL, com garantias bem mais fracas.

### TinyDB 4.8.2

- **Prós:** arquivo JSON legível e diffável; 243 bytes para 6 registros; 0,118 ms;
  modelo de documentos, que acomoda campos novos sem migração.
- **Contras:** dependência nova (wheel `py3-none-any`, instala sem `gcc`); reescreve
  o arquivo inteiro a cada escrita e não tem transação nem concorrência; sem
  índices (irrelevante neste tamanho).
- **Balanço:** o mais leve em bytes e o mais legível, às custas de garantias de
  escrita.

### DuckDB 1.4.5

- **Prós:** SQL analítico e transacional em um arquivo único; wheel `cp39` pronta;
  útil se o catálogo fosse consultado com agregações.
- **Contras:** 16,4 ms só para abrir e ler 6 linhas — ~130x o `sqlite3` — e 536 KB
  para 6 linhas; dependência grande; o ganho analítico não se aplica a um catálogo
  de dezenas de linhas lido por chave.
- **Balanço:** o custo fixo de abertura domina qualquer ganho no volume atual.

### LMDB 3.0.0

- **Prós:** 0,136 ms, 20 KB, transacional, leitura concorrente por mmap; wheel
  `cp39` disponível.
- **Contras:** dependência nova; API de bytes de baixo nível (nenhum SQL, nenhum
  documento); exige configurar `map_size`; inspeção manual do conteúdo.
- **Balanço:** desempenho comparável ao `sqlite3`, com mais código de acesso e sem
  linguagem de consulta.

### SQLAlchemy 2.0.55 sobre `sqlite3`

- **Prós:** 0,184 ms — apenas 0,058 ms acima do `sqlite3` puro; separa o código do
  dialeto, se o banco mudar depois.
- **Contras:** dependência nova; uma camada a mais para uma única tabela; não
  escolhe o driver sozinho (continua precisando de `sqlite3`).
- **Balanço:** custo de execução baixo, custo de complexidade alto para o tamanho
  do problema.

### Bancos cliente-servidor (PostgreSQL, MySQL/MariaDB, Redis, MongoDB)

- **Prós:** concorrência, durabilidade e ferramental maduros.
- **Contras:** exigem um processo a mais dentro do container ou um serviço à
  parte; `00-enunciado.md:63-65` fixa container único e sem serviços externos, e o
  comando documentado sobe apenas `gunicorn` (`Dockerfile:12`,
  `README.md:15-18`); não foram medidos.
- **Balanço:** ficam fora da restrição da tarefa antes de qualquer medição.

### O que vale para todas as opções

- Todas gravam em arquivo dentro do container. Mediante teste no container
  (§3.3 do documento companheiro): o arquivo sobrevive a `stop`/`start` e
  `restart`, mas some em `rm` + novo `run` e em rebuild da imagem. Nenhuma opção
  embarcada muda isso; persistência real exigiria volume, que o `Dockerfile` não
  declara e o comando documentado não monta.
- Nenhuma delas está no projeto hoje: `requirements.txt` tem só Flask e gunicorn.

## 2. Matching em runtime: a regra do gerador aplicada por requisição

### 2.1 O que a adaptação é

`scripts/generate_data_set.py:7-24` recebe a cifra como string separada por `;` e,
para cada uma das 6 sequências: (a) verifica `s in acorde` na string inteira em
minúsculas; (b) exige que **todo** token da música esteja entre os tokens da
sequência (`get_famosas`, linhas 13-20); (c) devolve o id da sequência. O
resultado vira a coluna 7 (`generate_data_set.py:84-88`).

Transportada para runtime, a mesma regra opera sobre `Musica.cifra`
(`musica.py:16`), a lista ordenada de tokens que `limpa_cifra` produz
(`main.py:11-23`). A tradução literal, executada dentro do laço que hoje testa a
tag (`main.py:207-209`):

```python
def aparece(seq_tokens, cifra_tokens):
    s = ';'.join(seq_tokens).lower()
    acorde = ';'.join(cifra_tokens).lower()
    if s in acorde:
        return all(t in seq_tokens for t in acorde.split(';'))
    return False
```

Duas observações medidas:

- A comparação de substring sobre a string junta pode casar na fronteira de
  tokens (`'em;g'` dentro de `'cem;g'`); a condição de vocabulário anula esse caso.
  Ancorar a busca em `';X;'` dentro de `';C;'` é equivalente na prática: para as 6
  sequências, os conjuntos de músicas resultantes são **idênticos** aos do CSV.
- O `.lower()` por música, por requisição, é o item mais caro da tradução literal;
  ele pode ser feito uma vez na carga.

### 2.2 Resultados: a regra reproduz exatamente a tag do CSV

Executando a regra em runtime sobre as 67.585 músicas carregadas, o conjunto de
músicas por sequência é igual, música a música, ao da coluna 7:

| seq | Sequência | Tag do CSV | Runtime literal | Runtime ancorado | Índice de bigramas |
|---|---|---:|---:|---:|---:|
| 0 | `Bm,G,D,A` | 199 | 199 | 199 | 199 |
| 1 | `C,G,Am,F` | 296 | 296 | 296 | 296 |
| 2 | `Em,G` | 4 | 4 | 4 | 4 |
| 3 | `C,A7,Dm,G7` | 5 | 5 | 5 | 5 |
| 4 | `Gm,F` | 7 | 7 | 7 | 7 |
| 5 | `C,C7,F,Fm` | 3 | 3 | 3 | 3 |

Igualdade de conjuntos (não só de contagem) verificada para as três variantes.
Ou seja: adotar a regra em runtime **não muda** o resultado das 6 sequências, que é
o critério de regressão da tarefa (`00-enunciado.md:66-67`).

### 2.3 Custo por requisição

Tempo do handler para uma sequência (varredura das 67.585 músicas + montagem dos
dicionários de resultado), comparado com o caminho atual (`main.py:203-223`):

| Estratégia | Custo por requisição (ms) |
|---|---:|
| Hoje: filtro + teste `str(id_seq) in musica.seqs_famosas` | 43,0 – 45,6 |
| Runtime, tradução literal (`.lower()` por música) | 34,1 – 47,6 |
| Runtime, ancorado em `;X;` com a string já em minúsculas | 16,7 – 20,5 |
| Runtime, só ocorrência contígua e sem teste de vocabulário | 16,8 – 27,7 |
| Consulta sobre índice de bigramas | 0,04 – 3,09 |

Nas duas últimas linhas o custo acompanha o número de matches (o teto é `Em,G`
contíguo, com 3.110 músicas); nas demais, ~200 a 300.

Medição de apoio (sequência 0): o laço atual, só com o teste de tag, custa 35,4 ms;
o mesmo laço com comparação ancorada custa 18,1 ms (18,6 ms somando o teste de
vocabulário) e devolve os mesmos 199 ids. `apply_filtro(musicas.values(), generos)`
custa 1,0 ms. Montar os dicionários de resultado é barato: 5,4 ms para os 3.110
matches de `Em,G` contíguo; `json.dumps` de uma página de 100 itens custa 0,33 ms
(36,8 KB).

O tempo total observado por HTTP hoje, no container, é 48–50 ms para
`GET /similares?sequencia=...` (mediana de 7 requisições, uma sequência por
requisição). O custo dominante em qualquer estratégia é o laço O(67.585); trocar o
teste de tag por um teste de substring não acrescenta uma segunda passada, porque o
laço já existe.

### 2.4 Outras formas de pré-calcular

| Estratégia | Custo único | Custo por requisição | Estado extra |
|---|---:|---:|---|
| Tag pronta no CSV (hoje) | fora do runtime | 43–46 ms (só o laço) | coluna 7, regenerada por script |
| Pré-cálculo na carga | 202,6 ms p/ as 6 (carga atual: 3,7 s) | 43–46 ms | dict em memória |
| Pré-cálculo na inserção da sequência | 16,7–20,5 ms por sequência | consulta ao que foi gravado | linhas derivadas no banco (514 hoje) |
| Índice de bigramas na carga | 3.064 ms, 94.488 chaves / 994.351 entradas | 0,04–3,09 ms | índice em memória (~1 M entradas) |

### 2.5 Prós e contras

**Rodar a regra em runtime (por requisição)**

- Prós: qualquer sequência nova funciona sem regerar CSV, sem reiniciar e sem
  deploy; não existe estado derivado para invalidar; o resultado das 6 atuais é
  reproduzido exatamente (medido); o custo no laço é igual ou menor que o do teste
  de tag atual; nenhuma dependência nova e nenhum schema para músicas.
- Contras: CPU em toda requisição, sempre O(67.585) — com 1 worker
  (`Dockerfile:12`), requisições concorrentes enfileiram; o custo cresce com o
  número de matches quando a definição escolhida for mais frouxa (`Em,G` contíguo
  dá 3.110 músicas, 5,4 ms só para montar os dicionários); a definição de "aparece"
  passa a viver em código de runtime, e a coluna 7 do CSV fica como dado morto que
  pode divergir do gerador; a comparação por substring exige cuidado com fronteira
  de token e com maiúsculas.

**Manter pré-calculado**

- Prós: custo de matching zero por requisição; determinístico e idêntico ao
  legado; nenhuma decisão de semântica em runtime.
- Contras: a regra só existe no gerador offline
  (`scripts/generate_data_set.py:7-24`) e depende do script de geração do CSV;
  sequências cadastradas por usuário não teriam tag a menos que o pré-cálculo
  aconteça em outro lugar (carga ou inserção); a coluna 7 é gerada com
  `''.join(...)` (`generate_data_set.py:88`), sem separador — uma música que
  satisfizesse duas sequências viraria um token só (`'01'`), que o teste por
  igualdade de `main.py:209` não encontra, e ids de dois dígitos ficariam
  ambíguos (hoje nenhuma música tem mais de uma tag: 514 = soma das 6 contagens);
  a carga atual não paga esse custo porque o CSV já traz a resposta — 202,6 ms se
  passasse a calcular na carga.

**Pré-calcular na inserção**

- Prós: paga 16,7–20,5 ms uma vez por sequência e mantém a leitura no caminho
  atual (43–46 ms); combina com qualquer banco da seção 1; o resultado derivado
  pode ser gravado (514 linhas hoje).
- Contras: cria estado derivado que precisa ser recalculado se o CSV mudar (o CSV é
  lido uma vez na importação, `main.py:49-98`); uma sequência passa a ter dois
  caminhos de leitura conforme seja original ou cadastrada, se as 6 atuais
  continuarem vindo da coluna 7; o custo de escrita cresce com matches.

**Índice de bigramas**

- Prós: consulta em 0,04–3,09 ms, uma a duas ordens de grandeza abaixo das
  varreduras; serve de âncora para verificar a ordem contígua sem percorrer o
  corpus.
- Contras: 3,1 s e ~1 M entradas na carga (quase dobrando os 3,7 s atuais); só
  acelera a verificação de ordem contígua — definições de subsequência ou de
  conjunto ainda precisam de outra estrutura; memória proporcional ao corpus.

## 3. Como as duas decisões se combinam

| Catálogo | Matching | Situação |
|---|---|---|
| banco (seção 1) | runtime por requisição | catálogo persistido; 16,7–20,5 ms de CPU por busca; nada derivado para invalidar |
| banco | pré-cálculo na inserção + resultado gravado | leitura no caminho atual; exige recalcular quando o CSV mudar |
| CSV + as 6 fixas | tag do CSV | é o estado de hoje (`main.py:40-45`, `203-223`) |
| CSV + as 6 fixas | runtime | resultados idênticos aos de hoje (tabela 2.2), sem persistência |

As duas decisões não se obrigam: o banco guarda o catálogo (6 linhas hoje), e o
matching pode continuar lendo a coluna 7 para as 6 originais. O que as amarra é o
requisito de que sequências cadastradas também possam ser buscadas
(`00-enunciado.md:49-51`) — a coluna 7 não cobre sequência nova.

## 4. Resumo das medições

- Banco: `sqlite3` 0,126 ms / 8 KB; `shelve` 0,253 ms / 16 KB; TinyDB 0,118 ms /
  243 B; LMDB 0,136 ms / 20 KB; SQLAlchemy+`sqlite3` 0,184 ms / 8 KB; DuckDB
  16,363 ms / 536 KB (6 linhas). Cliente-servidor fora da restrição de container
  único.
- Regra do gerador em runtime: reproduz exatamente as 6 tags (199/296/4/5/7/3),
  música a música; custa 16,7–20,5 ms por requisição na forma ancorada e 34,1–47,6
  ms na tradução literal, contra 43,0–45,6 ms do caminho atual.
- Pré-cálculo: 202,6 ms na carga (uma vez, para as 6) ou 16,7–20,5 ms por sequência
  na inserção; índice de bigramas: 3.064 ms e ~1 M entradas para consultas de
  0,04–3,09 ms.
- HTTP hoje: 48–50 ms por busca de sequência, no container, com 1 worker.

## 5. Limitações destas medições

- Tudo foi medido com 1 worker e 1 requisição por vez; concorrência, contenção de
  escrita e comportamento com `--workers > 1` não foram testados.
- Os tempos são desta máquina e deste container; servem para comparar as opções
  entre si, não como previsão absoluta.
- O corpus é o `dataset_final.csv` deste commit, com as 67.585 músicas carregadas
  (a primeira linha do arquivo é descartada por `main.py:50`).
- As variantes de matching foram medidas por chamada direta às funções do handler
  e por `curl` contra o container; não foram testadas sob carga nem com filtro de
  gênero preenchido.
- DuckDB foi medido com 50 ciclos (não 200) por causa do custo de abertura.
