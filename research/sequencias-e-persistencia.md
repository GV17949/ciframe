# Pesquisa — ocorrência de sequências de acordes, banco embarcado e `#/porsequencia`

Base: `HEAD` = `fb97001` (2026-10-17). Todo o documento descreve o código e os dados
como estão neste commit; não há proposta de mudança.

## Sumário

O único mecanismo que hoje responde "a sequência X aparece na música Y" é uma tag
pré-computada no CSV (`SEQ_FAMOSA`, coluna 7), produzida fora do runtime por
`scripts/generate_data_set.py:7-24` com uma regra específica: a sequência precisa
ocorrer como bloco contíguo de acordes **e** o vocabulário de acordes da música inteira
precisa estar contido no vocabulário da sequência. Em tempo de requisição, `main.py`
não varre a cifra de nenhuma música: ele converte a lista de acordes recebida em uma
chave concatenada, procura essa chave em um dicionário de 6 entradas
(`main.py:40-45`, `190-197`) e filtra as músicas por pertencimento à lista
`seqs_famosas` (`main.py:203-223`). A cifra completa e ordenada de cada música existe
em memória (`musica.py:16`), mas a estrutura derivada `acordes` é um `set` sem ordem
nem repetição (`musica.py:17`), e é essa estrutura que alimenta a busca por
similaridade já existente (`main.py:230-263`).

O projeto não tem banco de dados nem qualquer caminho de escrita: `requirements.txt`
lista apenas Flask e gunicorn, o CSV é lido uma vez na importação (`main.py:49-98`) e
todas as rotas são somente leitura. O `Dockerfile` é de um único estágio
(`python:3.9-slim` + `gunicorn`, `Dockerfile:1-12`), sem `VOLUME`, e o comando de
execução documentado não monta volume (`README.md:15-18`). Medições em container
mostraram que arquivos criados em `/app` sobrevivem a `restart`, mas desaparecem
quando o container é removido e recriado; `sqlite3`, `dbm`, TinyDB e DuckDB funcionam
sem compilador na imagem, enquanto bancos cliente-servidor exigiriam um serviço
adicional.

A página `#/porsequencia` (`static/assets/js/routes.js:17-21`) já consome
`GET /similares?sequencia=<acordes separados por vírgula>[&generos=<gênero>]` e renderiza
os resultados, mas o catálogo exibido é um array de 4 sequências fixas no controller
(`static/assets/js/controllers/sequencia.js:2-37`), sem nenhuma chamada que busque o
catálogo no backend e sem formulário de cadastro. Esse catálogo de 4 difere do
catálogo de 6 do backend: as sequências `Em-G` (id 2) e `C-A7-Dm-G7` (id 3) existem na
API e não aparecem na página; juntas, elas respondem por 9 das 514 músicas tagueadas.
A página também não envia paginação, então consultas com mais de 100 resultados
(`Bm-G-D-A`: 199; `C-G-Am-F`: 296) mostram no máximo os 100 primeiros itens da
fatia calculada pelo servidor.

## 1. Como o catálogo de sequências existe hoje

### 1.1 Backend: dicionário fixo de 6 chaves

`main.py:40-45` define o catálogo inteiro em memória:

```python
sequencias = {'BmGDA' : 0,
        'CGAmF' : 1,
        'EmG' : 2,
        'CA7DmG7' : 3,
        'GmF' : 4,
        'CC7FFm' : 5}
```

- A chave é a concatenação dos nomes dos acordes, **na ordem**, sem separador.
- O valor é o id usado na tag do CSV.
- Não há nome, descrição, autor, data ou qualquer outro metadado no catálogo.
- `data/mapeamento_sequencias_famosas.txt:1-6` contém rótulos legíveis para os ids
  (`0,Sequência de Bm,Bm - G - D - A`, etc.), mas nenhum código lê esse arquivo
  (busca por `mapeamento_sequencias_famosas` em `.py`/`.js`/`.html` não retorna nada).

### 1.2 A definição de "aparece" que existe hoje (pré-computada no CSV)

A tag `SEQ_FAMOSA` (coluna 7 do CSV; índice `SEQ_FAMOSA = 7` em `main.py:33`) foi
gerada pelo script offline `scripts/generate_data_set.py:7-24`:

```python
def get_famosas(acorde):
    seqs = ['bm;g;d;a','c;g;am;f', 'em;g' , 'c;a7;dm;g7', 'gm;f', 'c;c7;f;fm' ]
    out = []
    for i in range(len(seqs)):
        s = seqs[i]
        acorde = acorde.lower()
        if s in acorde:
            achou = True
            tem_seqs = []
            for l in acorde.split(';'):
                tokens = s.split(';')
                if l not in tokens:
                    achou = False
                    break
            if achou:
                tem_seqs.append(str(i))
                out.append("-".join(tem_seqs))
    return out
```

A regra efetiva é a conjunção de duas condições:

1. **Ocorrência contígua:** a string da sequência (`"bm;g;d;a"`) aparece como
   substring da string de acordes da música (`"..."` unida por `;`). Isso equivale a
   exigir que os acordes da sequência apareçam em sequência, em posições adjacentes,
   na ordem exata.
2. **Vocabulário da música contido no vocabulário da sequência:** **todos** os acordes
   da música (cada token de `acorde.split(';')`) precisam pertencer ao conjunto de
   acordes da sequência. Uma música que contenha `Bm, G, D, A` **e** `Em`, por exemplo,
   não recebe a tag da sequência 0.

O script que originou essa lógica está no histórico: `git show acfefb0:scripts/find_seq_famosas.py`
(commit `acfefb0`, 2015-12-12), com 3 sequências e o mesmo par
substring + vocabulário. O script em `scripts/generate_data_set.py` é Python 2
(`print` sem parênteses em `:27` e `:89`, `sys.setdefaultencoding` em `:30`) e não roda
como está no Python 3.9 do container; ele é um gerador offline do CSV.

### 1.3 O que o runtime faz com a tag

- Na importação, `musica[SEQ_FAMOSA].split(";")` transforma a coluna em lista
  (`main.py:63`); o valor `NA` já foi removido de toda a linha por
  `line.replace('NA', '')` (`main.py:53`), então músicas sem tag ficam com `['']`.
- `Musica` guarda `self.seqs_famosas = seqs_famosas` (`musica.py:18`).
- `GET /similares?sequencia=...` (`main.py:170-201`):
  - `sequencia_tag` é lido em `main.py:175`;
  - todos os caracteres `,` são removidos (`main.py:191`), produzindo a chave
    concatenada;
  - se a chave não estiver em `sequencias`, a resposta é `[]` (HTTP 200)
    (`main.py:194-197`);
  - se estiver, `get_similares_por_sequencia(id_seq, generos_key)` (`main.py:203-223`)
    percorre as músicas filtradas por gênero e mantém aquelas em que
    `str(id_seq) in musica.seqs_famosas` (`main.py:209`).
- O teste `in` é **pertencimento a elemento de lista**, não substring. Como o CSV atual
  só tem tags de um dígito, isso funciona; se uma música tivesse mais de uma tag, o
  gerador as uniria sem separador (`''.join(...)` em `scripts/generate_data_set.py:88`),
  produzindo algo como `['04']`, que não casa com `'0'` nem com `'4'`. Nenhuma linha do
  CSV atual tem tag com mais de um dígito.
- Não existe, em `main.py`, nenhuma função que compare uma sequência com
  `musica.cifra` ou `musica.acordes` em tempo de requisição. O único uso de
  `musica.acordes` é na busca por similaridade (`main.py:240-257`).

### 1.4 Medições sobre o CSV atual

Parsing equivalente ao de `main.py:52-63` (com `limpa_cifra` de `main.py:11-23`),
executado sobre `data/top/dataset_final.csv`:

| Fato | Valor |
|---|---|
| Linhas do arquivo | 67.586 |
| Linhas carregadas por `main.py` | 67.585 |
| Músicas com cifra vazia (`acordes == []`) | 8.141 |
| Tokens de acorde distintos em runtime | 6.653 (igual ao `GET /acordes` ao vivo) |
| Comprimento da cifra por música | mín. 0, máx. 2.065, média 51,87 tokens |
| Músicas com alguma tag | 514 |
| Tag `0` (`Bm,G,D,A`) | 199 |
| Tag `1` (`C,G,Am,F`) | 296 |
| Tag `2` (`Em,G`) | 4 |
| Tag `3` (`C,A7,Dm,G7`) | 5 |
| Tag `4` (`Gm,F`) | 7 |
| Tag `5` (`C,C7,F,Fm`) | 3 |

A primeira linha do CSV é um **dado**, não cabeçalho
(`14-bis,a-qualquer-tempo,14 Bis,A Qualquer Tempo,MPB,70115,B,NA,...`), e
`main.py:49-50` chama `f.readline()` para descartá-la. Consequências observadas ao
vivo: `GET /musicas` devolve 67.585 itens e `GET /musica/14-bis_a-qualquer-tempo`
devolve HTTP 500, enquanto `GET /musica/14-bis_adoraveis-criaturas` devolve 200.

A verificação de que a tag reproduz exatamente a regra do gerador foi feita para as
6 sequências: para cada uma, o conjunto de músicas com a tag é exatamente o conjunto
de músicas com ocorrência contígua **e** vocabulário da música ⊆ vocabulário da
sequência (199, 296, 4, 5, 7, 3 — interseções idênticas às tags).

## 2. Definições de "a sequência X aparece na música Y" representáveis com os dados atuais

### 2.1 Estruturas de dados disponíveis por música

| Estrutura | Onde é criada | Ordem | Repetição | Conteúdo |
|---|---|---|---|---|
| `Musica.cifra` | `musica.py:16`, a partir de `limpa_cifra` (`main.py:11-23`) | preservada | preservada | todos os tokens de acorde na ordem do CSV |
| `Musica.acordes` | `musica.py:17` (`list(set(cifra))`) | perdida (ordem de `set`) | removida | acordes distintos |
| `Musica.seqs_famosas` | `musica.py:18`, `main.py:63` | irrelevante | irrelevante | ids de sequência pré-computados |
| `Musica.tom` | `musica.py:15` | — | — | tonalidade da cifra (coluna 6) |

`Musica.id_unico_musica` é `"<id_artista>_<id_musica>"` (`musica.py:20`); as 67.585
linhas carregadas têm esse par único (medido). `Musica.url` é montada como
`http://www.cifraclub.com.br/<id_artista>/<id_musica>` (`musica.py:22`).

### 2.2 Quantidade de músicas por definição

Contagens sobre as 67.585 músicas carregadas, usando `Musica.cifra` em runtime.
Definições comparadas (X = sequência, C = lista `cifra` da música):

- **Tag atual:** X ocorre como bloco contíguo em C **e** `set(C) ⊆ set(X)`.
- **Ocorrência contígua:** existe `i` tal que `C[i:i+len(X)] == X` (ordem exata,
  posições adjacentes, repetições de X preservadas).
- **Subsequência ordenada:** existem índices `i1 < i2 < ... < in` com `C[ik] == X[k]`
  (ordem exata, lacunas permitidas).
- **Contenção não ordenada:** `set(X) ⊆ set(C)` (posição e repetição ignoradas).
- **Interseção não vazia:** `set(X) ∩ set(C) ≠ ∅`; é a condição de
  `get_similares` (`main.py:245`), que não exige que X "apareça", apenas que compartilhe
  algum acorde.
- **Invariante de tom (não implementada no runtime):** compararia graus
  (`NCIFRA`/`tom`) em vez de nomes de acorde; os dados para isso existem em
  `data/dataset_seq_notas.csv` e `Musica.tom`, mas nenhum código de `main.py` os usa.

| Definição | seq 0 `Bm,G,D,A` | seq 1 `C,G,Am,F` | seq 2 `Em,G` | seq 3 `C,A7,Dm,G7` | seq 4 `Gm,F` | seq 5 `C,C7,F,Fm` |
|---|---:|---:|---:|---:|---:|---:|
| Tag atual: contígua **e** vocabulário da música ⊆ vocabulário da sequência | 199 | 296 | 4 | 5 | 7 | 3 |
| Ocorrência contígua (ordem exata, tokens adjacentes) | 866 | 1.216 | 3.110 | 96 | 1.039 | 132 |
| Subsequência ordenada (ordem exata, com lacunas) | 4.763 | 5.887 | 13.643 | 427 | 3.641 | 280 |
| Contenção não ordenada (todos os acordes da sequência em qualquer posição) | 5.768 | 6.894 | 14.160 | 582 | 3.847 | 365 |
| Interseção não vazia (semântica de `/similares?acordes`, não é "aparece") | — | — | — | — | — | — |

Observações medidas:

- A condição de vocabulário é o que mais reduz a tag: das 866 músicas com
  `Bm,G,D,A` contíguo, **667** têm pelo menos um acorde fora de `{Bm,G,D,A}` e por
  isso não recebem a tag 0.
- Toda música tagueada também satisfaz a ocorrência contígua (199/199, 296/296,
  4/4, 5/5, 7/7, 3/3), mas o contrário não vale.
- A estrutura `acordes` (sem ordem) só permite expressar a linha "contenção não
  ordenada"; para qualquer definição que dependa de ordem é necessário usar
  `cifra` (que preserva ordem e repetições).

### 2.3 Tokenização e normalização existentes

`limpa_cifra` (`main.py:11-23`) é a única transformação aplicada à cifra na carga:

- tokens vazios são descartados (`main.py:14`);
- se o token contém `|`, usa-se o prefixo antes de `|` e o primeiro campo
  (`main.py:16-18`);
- caso contrário, o token é dividido por espaços (`main.py:20-22`).

Não há, no runtime, `lower()`, remoção de acentos, equivalência enarmônica, remoção de
sufixos (`7`, `9`, `add9`, `(11)` etc.) nem tratamento de baixo invertido (`/F#`):
a comparação é por igualdade exata de string. O gerador da tag, por outro lado,
faz `acorde.lower()` (`scripts/generate_data_set.py:12`), mas a tag resultante é só um
id — a cifra armazenada permanece como está no CSV.

Características medidas dos tokens em runtime:

- 2.278 tokens distintos contêm `(`;
- 3.808 tokens distintos contêm `/` (baixo invertido ou acorde dividido), somando
  267.926 ocorrências;
- 44 tokens distintos não começam por `A`–`G`, incluindo artefatos da extração HTML
  do cifraclub (`e|-`, `2x`, `add9`, `/F#`, `(Cm)`, `IV`);
- grafias enarmônicas coexistem e são tokens diferentes: `A#` 10.135 ocorrências vs.
  `Bb` 59.759; `C#` 23.911 vs. `Db` 4.090; `D#` 12.147 vs. `Eb` 23.626;
  `F#` 49.300 vs. `Gb` 1.407; `G#` 21.349 vs. `Ab` 12.259;
- 35 linhas contêm espaços dentro de um campo separado por `;` (ex.:
  `C6 G`, `G7(4 9)`), que `limpa_cifra` quebra em tokens separados;
- 6 linhas contêm `|` (tablatura), tratadas pelo ramo `main.py:16-18`;
- 8.141 músicas têm cifra vazia; a lista `acordes` fica vazia e nenhuma definição de
  ocorrência pode casá-las.

### 2.4 A noção de similaridade que já existe (conjuntos, não ocorrência)

`GET /similares?acordes=...` e `GET /similares?id_unico_musica=...` caem em
`get_similares` (`main.py:230-263`), que:

- calcula `inter = set(acordes) ∩ set(musica.acordes)` e
  `diff = set(musica.acordes) - set(acordes)` (`main.py:240-241`);
- mantém músicas com `len(inter) > 0` (`main.py:245`);
- devolve `diferenca` e `intersecao` (`main.py:256-257`);
- ordena por `(len(diferenca), -len(intersecao))` (`main.py:263`).

Essa é a semântica usada pela página `#/poracordes`, que esconde resultados com
`diferenca` não vazia e mostra os demais em um segundo bloco
(`static/templates/acordes.html:40-43`, `61-91`). Ela não é usada pelo endpoint de
sequência, cuja resposta não contém `diferenca` nem `intersecao`
(`main.py:210-220`).

### 2.5 Dados presentes no repositório que o runtime não carrega

- `data/dataset_seq_notas.csv` (66.525 linhas) contém `ARTISTA`, `MUSICA`, `ESTILO`,
  `TOM`, `VISUALIZACOES`, `CIFRA` e `NCIFRA`; `NCIFRA` é a cifra normalizada em graus
  (`I;V;VI;IV;...`).
- `data/transposition_matrix2.csv` é a matriz de transposição usada por
  `scripts/simplify_chords.R:32` e `scripts/normalize_chords.R:34`.
- `data/top/chords-transitions-empty.csv` contém apenas o cabeçalho com 42 transições
  (`I-II`, `I-III`, ...) e é lido por `scripts/build-chords-transitions.R:70`.
- Nenhum desses arquivos é referenciado por `main.py`, `musica.py` ou pelo frontend
  (a busca por esses nomes só encontra os scripts `.R`).

## 3. Persistência e banco embarcado no container único

### 3.1 Estado atual

- Não há banco de dados. `README.md:8-9` descreve "uma base de dados carregada de um
  CSV em memória (sem banco)"; `AGENTS.md:9-11` repete "there is no database".
- `requirements.txt:1-5` lista somente `Flask==3.1.3` e `gunicorn==23.0.0`.
- Nenhum módulo de banco é importado em `main.py`/`musica.py` (não há `import sqlite3`,
  `dbm`, `shelve`, ORM ou driver).
- Todos os dados são carregados na importação do módulo (`main.py:49-98`) e ficam em
  estruturas Python: `musicas` (`OrderedDict` ordenado por popularidade,
  `main.py:88-89`), `genero_musicas` (`main.py:82-85`, ordenado por popularidade em
  `main.py:95-96`), `generos` (`main.py:92`) e `acordes` (`main.py:77-78`).
- Não há rota de escrita: as rotas declaradas em `main.py:101-170` não têm
  `methods=...`, e não existe `POST`/`PUT`/`DELETE` em lugar nenhum.
- Não há `VOLUME` no `Dockerfile` (`Dockerfile:1-12`) nem volume no comando de
  execução documentado (`README.md:15-18`).
- `docs/adr/0002-persist-custom-sequences.md:1-8` era um template não preenchido
  (`[seu texto aqui]`) na data desta pesquisa; não havia decisão registrada sobre
  persistência.

### 3.2 Restrições registradas na documentação

- `docs/adr/0001-local-only-docker-deploy.md:3-16`: decisão de remover App
  Engine/Heroku e usar um único `Dockerfile` com gunicorn localmente; o backend mantém
  a arquitetura (um `main.py`, busca em memória a partir do CSV, Python 3.9); o alvo de
  nuvem ficou indefinido.
- `docs/features/sequencias-customizadas/00-enunciado.md:57-68` fixa: catálogo de
  músicas/gêneros continua vindo do CSV em memória; a aplicação continua no
  `Dockerfile` único e local-only, "container único, sem serviços externos
  adicionais"; as 6 sequências originais precisam manter os mesmos resultados;
  endpoints continuam retornando `json.dumps(...)`.
- `docs/features/sequencias-customizadas/00-enunciado.md:47-55` pede que o catálogo de
  sequências seja persistido em banco e sobreviva a reinícios do servidor.

O `Dockerfile` em si não menciona "container único" nem serviços externos; essa
restrição está no enunciado da tarefa, não no ADR 0001.

### 3.3 Persistência de arquivos no container (medido)

Execução do próprio `Dockerfile` em runtime compatível (imagem `python:3.9-slim`
construída localmente):

| Experimento | Resultado |
|---|---|
| container iniciado sem `-v` (porta 18080:8080), escrever `/app/probe.txt` | escrita permitida (processo roda como root; `/app` é gravável) |
| `restart` do container e ler `/app/probe.txt` | arquivo presente |
| remover o container e rodar um novo a partir da mesma imagem | arquivo ausente |
| `Mounts` do container | `[]` (nenhum volume) |
| `python -c "import sqlite3; ..."` dentro do container | funciona; `sqlite3` 3.46.1 no Python 3.9.25 |
| abrir `sqlite3.connect('/app/probe.db')` e inserir | funciona; arquivo criado |

Ou seja: o filesystem gravável do container preserva arquivos entre `stop`/`start` e
`restart`, mas não entre `rm` + novo `run` nem entre rebuilds da imagem. O
`Dockerfile:8` faz `COPY . .`, então qualquer arquivo de banco presente no contexto de
build seria copiado para a imagem; arquivos criados em runtime ficam na camada
gravável do container. O `.dockerignore:1-4` exclui `.git`, `.venv`, `__pycache__` e
`*.pyc`.

### 3.4 Opções embarcadas verificadas no ambiente do container

Todos os testes abaixo foram feitos na mesma base `python:3.9-slim` (Python 3.9.25,
pip 23.0.1, **sem `gcc`** — `which gcc` retorna ausente).

| Opção | Onde executa | Presente no projeto hoje | Verificação feita | Armazenamento |
|---|---|---|---|---|
| `sqlite3` (stdlib) | in-process | não | `import sqlite3` ok; escrita/leitura em `/app/probe.db` ok | arquivo |
| `dbm`/`shelve` (stdlib) | in-process | não | backend `dbm.gnu` ok; escrita/leitura ok | arquivo/diretório |
| TinyDB 4.8.2 | in-process | não | wheel `py3-none-any` disponível; `TinyDB('/tmp/t.json').insert(...)` ok | arquivo JSON |
| DuckDB 1.4.5 | in-process | não | wheel `cp39-manylinux` disponível; `CREATE TABLE`/`INSERT`/`SELECT` ok | arquivo `.duckdb` |
| SQLAlchemy 2.0.55 | in-process (camada ORM; precisa de driver) | não | wheel `cp39-manylinux` disponível | via driver (ex.: `sqlite3`) |
| LMDB 3.0.0 | in-process | não | wheel `cp39-manylinux` disponível | arquivo/diretório |
| PostgreSQL, MySQL/MariaDB, Redis, MongoDB | processo/serviço separado | não | não testado | serviço externo |

Fatos que delimitam a viabilidade dentro deste repositório:

- Adicionar qualquer opção de terceiros exige uma linha nova em `requirements.txt`
  (instalado em `Dockerfile:5-6`); as opções de stdlib não exigem mudança de
  dependências.
- Os wheels baixados para as opções de terceiros acima são `cp39`/`py3-none-any`,
  portanto instalam sem `gcc`.
- Bancos cliente-servidor exigiriam um processo adicional dentro do container ou um
  serviço/container à parte; o comando documentado sobe apenas `gunicorn`
  (`Dockerfile:12`, `README.md:15-18`).

### 3.5 Processo e concorrência

- `Dockerfile:12` executa `gunicorn --bind 0.0.0.0:8080 main:app`, sem `--workers` e
  sem `--preload`. Em execução, o container mostra 2 processos: o master do gunicorn e
  1 worker (`podman top`: PIDs 1 e 2 com a mesma linha de comando).
- O carregamento do CSV (`main.py:49-98`) ocorre no import do módulo; cada worker
  carregaria sua própria cópia se o número de workers fosse aumentado, mas hoje há um
  único worker.
- O caminho de desenvolvimento é `app.run(debug=True)` (`main.py:279-280`), que usa o
  servidor de desenvolvimento do Flask na porta 5000 (`README.md:22-31`), não o
  gunicorn.

## 4. Frontend `#/porsequencia`

### 4.1 Rota e composição

- Rota: `static/assets/js/routes.js:17-21` → `templates/sequencia.html` +
  `SequenciaController` com `controllerAs: "Sequencia"`.
- O módulo é `deciframeApp` (`static/assets/js/app.js:1-2`), AngularJS 1.4.9 carregado
  por CDN (`static/index.html:130-134`), sem build step.
- A página é linkada da home em `static/templates/home.html:78-86`.
- `RESTAPI` é definido como `http://localhost:5003` (`static/assets/js/app.js:3-5`),
  mas o controller de sequência não o usa: `var apiUrl = ""` (`sequencia.js:72`), ou
  seja, a requisição é relativa à mesma origem que serve o frontend.

### 4.2 Estado inicial e catálogo fixo

`static/assets/js/controllers/sequencia.js:2-37` define 4 objetos literais
(`sequencia1`..`sequencia4`) e os empilha em `vm.sequenciasFamosas`. Cada objeto tem
`index: 1` (não usado) e um array `acordes` de `{acorde, cor}`, com `cor` fixa
`#2E1C74`:

| Objeto | Acordes | Chave resultante | Id no backend |
|---|---|---|---|
| `sequencia1` | `Bm, G, D, A` | `BmGDA` | 0 |
| `sequencia2` | `C, G, Am, F` | `CGAmF` | 1 |
| `sequencia3` | `Gm, F` | `GmF` | 4 |
| `sequencia4` | `C, C7, F, Fm` | `CC7FFm` | 5 |

As 4 chaves existem no dicionário de `main.py:40-45`. As entradas `EmG` (id 2) e
`CA7DmG7` (id 3) não têm objeto correspondente no frontend. Em números: as 4
sequências exibidas alcançam 505 das 514 músicas tagueadas; as 2 sequências
backend-only alcançam 4 + 5 = 9.

O template renderiza a lista com `ng-repeat` sobre `Sequencia.sequenciasFamosas` e um
`df-hex` por acorde (`static/templates/sequencia.html:6-8`); cada `df-hex` recebe
`acorde`, `acorde-color` e `acorde-checked="Sequencia.temAcorde(acordeon)"`. O
`ng-click` que dispara a busca está no `div` que envolve a sequência inteira
(`sequencia.html:6`), não no hex individual.

`vm.temAcorde` (`sequencia.js:47-53`) compara objetos com `indexOf` no array
`vm.minhaSequencia.acordes`; como o clique atribui o mesmo objeto de
`vm.sequenciasFamosas` a `vm.minhaSequencia` (`sequencia.js:64-66`), a comparação por
identidade funciona e os hexes da sequência selecionada ficam com `acorde-checked`
verdadeiro (preenchimento branco, `static/templates/directives/df-hex.html:4,8`).

### 4.3 Fluxo de interação

1. Estado inicial (`sequencia.js:32-45`): `minhaSequencia = {}`, `musics = []`,
   `showSearchResultsCount = false`, `meuGenero = ""`, `generos = GENEROS`.
2. Clique em uma sequência (`sequencia.html:6` → `sequencia.js:63-90`):
   - `vm.minhaSequencia = sequencia`;
   - `progressbar.start()`, `esfigeSpeech = "Procurando músicas com base na sequencia..."`,
     `isSearching = true`, `musics = []`;
   - monta `similares?sequencia=` + `createChordsString(vm.minhaSequencia.acordes)`
     (`sequencia.js:55-61`, `72-73`), que junta os acordes com `,`;
   - se `meuGenero` não for `""`/`null`, acrescenta `&generos=<gênero>`
     (`sequencia.js:74-76`), sem `encodeURIComponent`;
   - `$http.get(apiUrl.concat(searchString))` (`sequencia.js:77`).
3. Sucesso (`sequencia.js:78-84`): `progressbar.complete()`,
   `esfigeSpeech = "Encontrei essas músicas"`, `isSearching = false`,
   `showSearchResultsCount = true`, `musics = data`.
4. Erro (`sequencia.js:85-89`): `esfigeSpeech = "Ops! Algo errado."`,
   `isSearching = false`, `showSearchResultsCount = false`.
5. O painel direito só aparece quando `Sequencia.minhaSequencia.acordes.length` é
   verdadeiro (`sequencia.html:19`); nele ficam o texto, o `<select>` de gênero
   (`sequencia.html:24-30`) e os hexes da sequência selecionada
   (`sequencia.html:34`).
6. Mudar o gênero dispara `ng-change="Sequencia.pesquisarPorSequencia()"`
   (`sequencia.html:28`), sem argumento; o controller mantém a sequência atual
   (`sequencia.js:64-66`).
7. Clicar em qualquer hex da sequência selecionada chama `limparPesquisa()`
   (`sequencia.html:34` → `sequencia.js:92-95`), que faz `minhaSequencia = {}` e
   `musics = []`, mas **não** limpa `meuGenero`.
8. Resultados (`sequencia.html:40-58`): `ng-repeat="music in Sequencia.musics |
   orderBy:'-popularidade'"`, com `ng-hide="music.diferenca.length"`; cada card mostra
   `nome_musica`, `nome_artista`, `genero` e, no clique, chama
   `goToLirics(music)` (`sequencia.js:97-99`), que faz `$window.open(music.url)`.
9. O botão "Encontrei essas músicas" (`sequencia.html:10-14`) rola a página até
   `#results` via jQuery (`sequencia.js:101-104`).

### 4.4 Contrato de API consumido pela página

Requisição efetiva, sem paginação e sem codificação:

```
GET /similares?sequencia=Bm,G,D,A
GET /similares?sequencia=C,G,Am,F&generos=Rock
```

O backend remove as vírgulas (`main.py:191`) e usa a string resultante como chave. A
resposta é um array JSON serializado com `json.dumps` (`main.py:197`), servido como
`text/html; charset=utf-8` (comportamento legado descrito em `AGENTS.md:43-47`), com
os campos `id_unico_musica`, `id_artista`, `id_musica`, `nome_artista`, `nome_musica`,
`popularidade`, `acordes`, `genero` e `url` (`main.py:210-220`). Ao vivo, a resposta
para `sequencia=Bm,G,D,A` contém exatamente esses campos e **não** contém `diferenca`
nem `intersecao`.

O cabeçalho `Access-Control-Allow-Origin: *` é adicionado a todas as respostas
(`main.py:274-277`), embora a página use a mesma origem.

### 4.5 Comportamentos e limites observáveis

- **Catálogo fixo:** a página não faz `GET` de catálogo nenhum. A única chamada HTTP do
  controller é a busca (`sequencia.js:77`). Não há chamada a `/generos`, `/acordes` ou
  a um endpoint de sequências; `vm.generos` vem da constante `GENEROS`
  (`sequencia.js:43`, `static/assets/js/app.js:6-58`).
- **Sem cadastro:** `static/templates/sequencia.html` não tem `<input>`, `<form>`,
  `<textarea>` ou botão de salvar; a única interação é escolher uma das 4 sequências e
  filtrar por gênero.
- **Sem identidade/nome:** o objeto de sequência tem apenas `index` e `acordes`; a
  "identidade" enviada ao backend é a concatenação dos acordes.
- **Sem paginação:** `pagina` nunca é enviado; o backend aplica
  `get_pagina(..., '1')` (`main.py:176`, `196`, `226-228`) com `TAM_PAGINA = 100`
  (`main.py:35`). Ao vivo: seq 0 devolve 100 na página 1 e 99 na página 2 (total 199);
  seq 1 devolve 100/100/96 (total 296); as demais devolvem todos os resultados
  (4, 5, 7, 3).
- **Ordenação:** o backend não ordena `get_similares_por_sequencia`
  (`main.py:203-223`); a ordenação por popularidade acontece no cliente
  (`sequencia.html:42`). Sem filtro de gênero, a coleção percorrida é a concatenação
  dos grupos de gênero na ordem da lista `generos` (`main.py:92`, `266-272`), e essa
  lista vem de um `set`; a fatia de 100 itens, portanto, não é "as 100 mais populares".
  Medição: duas execuções do mesmo `GET /similares?sequencia=Bm,G,D,A` após reiniciar o
  processo devolveram conjuntos de ids com interseção de 94 de 100 itens. Com filtro de
  gênero, a lista daquele gênero já está ordenada por popularidade
  (`main.py:95-96`).
- **`ng-hide="music.diferenca.length"`:** a resposta de sequência não tem `diferenca`;
  a expressão não recebe um array e não esconde cards. O mesmo atributo existe em
  `acordes.html:43`, onde a resposta de `/similares?acordes` inclui `diferenca`.
- **Gêneros:** a constante do frontend tem 51 entradas; `GET /generos` devolve 52. A
  diferença é `"R&B;"`, presente no CSV (linhas de `alicia-keys`, ex.:
  `data/top/dataset_final.csv:2167`) e ausente da constante. O backend compara o
  gênero por igualdade exata em `apply_filtro` (`main.py:266-272`); um valor que não
  existe em `generos` resulta em coleção vazia (HTTP 200, `[]`), verificado ao vivo com
  `generos=NaoExiste`.
- **Codificação da URL:** `createChordsString` concatena nomes como `C#` sem
  `encodeURIComponent` (`sequencia.js:55-61`, `73`). Em uma URL, `#` inicia o fragmento;
  portanto o construtor atual não transporta acordes com sustenido. As 4 sequências
  atuais não usam `#`.
- **Botão de resultados:** `showSearchResultsCount` vira `true` em qualquer sucesso,
  inclusive quando `data` é `[]` (`sequencia.js:78-83`), e só volta a `false` em erro
  ou ao clicar no botão (`sequencia.js:101-104`).
- **Limpeza parcial:** `limparPesquisa` zera sequência e resultados, mas não o gênero;
  a próxima sequência escolhida é buscada com o gênero anterior
  (`sequencia.js:92-95`).
- **Sem loading visual no grid:** `isSearching` é mantido no controller
  (`sequencia.js:69`, `81`, `87`), mas o template de sequência não o utiliza; a barra
  `ngProgress` é iniciada/concluída (`sequencia.js:67`, `79`).

### 4.6 O que não existe hoje no frontend

- Nenhuma chamada para obter a lista de sequências do backend.
- Nenhum formulário, `POST`, validação ou mensagem de duplicidade.
- Nenhum controle de página ou "carregar mais".
- Nenhum uso de `id` de sequência; a página só conhece os acordes.
- Nenhum tratamento específico para resultados sem `diferenca` (o atributo é herdado
  da página de acordes).

## 5. Fluxos entre componentes

```
scripts/generate_data_set.py (offline, Python 2)
  └─> data/top/dataset_final.csv
        col 7 = SEQ_FAMOSA (ids 0..5 ou NA)
        col 8 = CIFRA (acordes separados por ';')
             │
             ▼  (import de main.py; main.py:49-98)
main.py: musicas (OrderedDict por popularidade), genero_musicas,
         generos (set -> list), acordes (set), sequencias (dict fixo)
             │
             ▼
GET /similares?sequencia=Bm,G,D,A&generos=Rock
  main.py:170-201  →  chave "BmGDA"  →  sequencias["BmGDA"] = 0
  main.py:203-223  →  apply_filtro(generos)  →  str(0) in musica.seqs_famosas
  main.py:226-228  →  fatia [0:100]
  main.py:197      →  json.dumps(...)  (Content-Type: text/html)
             │
             ▼
sequencia.js:77  →  vm.musics = data  (sequencia.js:83)
             │
             ▼
sequencia.html:40-58  →  cards; clique → $window.open(music.url) (musica.py:22)
```

Fluxos observáveis:

- **Catálogo de sequências:** existe apenas como o `dict` de `main.py:40-45` e como os
  4 objetos de `sequencia.js:2-37`; os dois conjuntos não são sincronizados por código.
- **Tags:** são produzidas fora do runtime (script offline); o servidor apenas lê a
  coluna 7. Não há atualização de tag quando a cifra muda.
- **Músicas/gêneros:** sempre do CSV; nenhuma rota grava em `musicas`,
  `genero_musicas` ou `generos`.
- **Escrita:** não há nenhum fluxo de escrita no sistema (nem no backend, nem no
  frontend).
- **Rotas estáticas:** `/` serve `static/index.html` (`main.py:101-103`) e
  `/<path>` serve arquivos estáticos (`main.py:109-112`); `#/porsequencia` é uma rota
  do Angular (`routes.js:17-21`), não uma rota do Flask.

## 6. Histórico git relevante

| Commit | Data | Conteúdo |
|---|---|---|
| `acfefb0` | 2015-12-12 | cria `scripts/find_seq_famosas.py`, com 3 sequências e a regra substring + vocabulário |
| `c3ccc1b` | 2015-12-13 | "API para sequências famosas" em `back-end/api.py` |
| `ddceb74` | 2016-02-23 | cria a página de sequência no frontend, com as 4 sequências fixas em JS |
| `3b4d191` | 2016-05-17 | introduz o parâmetro `sequencia`, o `dict` de 6 chaves, `get_similares_por_sequencia` e `get_pagina` |
| `249bdc9` | 2026-10-15 | troca a URL do Heroku por URL relativa nos controllers (inclui `sequencia.js`), correções de Python 3 |
| `ff57dc5` | 2026-10-15 | moderniza dependências e troca o deploy legado pelo `Dockerfile` (ADR 0001) |
| `3b8ec59` | 2026-10-15 | adiciona enunciado e templates da tarefa de sequências customizadas |
| `e03bc62` | 2026-10-17 | remove a restrição de não tocar no frontend legado (ADR 0003) |
| `fb97001` | 2026-10-17 | atualização do enunciado (HEAD) |

O commit `249bdc9` documenta que a API local estava quebrada porque os controllers
apontavam para `https://ciframe-api.herokuapp.com/`; o `apiUrl = ""` atual é
consequência direta dessa correção (`git show 249bdc9 -- static/assets/js/controllers/sequencia.js`).

## 7. Método de verificação e limitações

Verificações executadas neste ambiente:

- Leitura integral de `main.py`, `musica.py`, `Dockerfile`, `requirements.txt`,
  `README.md`, `AGENTS.md`, ADRs 0001/0002/0003, templates de
  `docs/features/sequencias-customizadas/`, `static/templates/sequencia.html`,
  `static/templates/acordes.html`, `static/assets/js/controllers/sequencia.js`,
  `acordes.js`, `musica.js`, `main.js`, `app.js`, `routes.js`, `static/index.html`,
  `scripts/generate_data_set.py`, `scripts/find_seq_famosas.py` (histórico),
  `scripts/*.R` e os arquivos de dados citados.
- Análise do CSV com um parser que replica `limpa_cifra` (`main.py:11-23`): contagens de
  tags, comprimentos, tokens distintos, grafias enarmônicas, linhas com `|`/espaços e
  interseções entre definições de matching. A contagem de tokens distintos (6.653)
  coincidiu com o `GET /acordes` do servidor ao vivo.
- Build da imagem com o `Dockerfile` do repositório e execução em porta alternativa
  (container sem volume), com `GET` em `/generos`, `/musicas`, `/acordes`, `/musica/...`,
  `/search` e `/similares` para as 6 sequências, páginas 1–3 e filtros de gênero.
  Resultados citados na seção 4.5.
- Reinício do processo e repetição de `GET /similares?sequencia=Bm,G,D,A` para medir a
  variação da fatia de 100 itens (interseção 94/100).
- Testes de persistência: arquivo em `/app` sobrevive a `restart`, desaparece após
  remoção do container; `sqlite3` grava no filesystem do container.
- Testes na base `python:3.9-slim`: `sqlite3` 3.46.1, `dbm.gnu`, ausência de `gcc`,
  download de wheels `cp39`/`py3-none-any` para TinyDB, DuckDB, SQLAlchemy e LMDB,
  execução de escrita/leitura com TinyDB e DuckDB.

Limitações:

- O binário `docker` não está instalado neste ambiente; os testes de container usaram
  `podman`, que executou o mesmo `Dockerfile` e a mesma imagem base
  (`python:3.9-slim`). O comportamento de filesystem/volume descrito é o do runtime
  observado.
- Não há navegador disponível para renderizar o AngularJS; as afirmações sobre
  template/expressões vêm do código e do contrato JSON medido no servidor, não de uma
  execução visual.
- O `Dockerfile` não fixa digest da imagem base; a versão observada foi Python 3.9.25
  com SQLite 3.46.1 na data da pesquisa.
- Não há suíte de testes automatizados no repositório (nenhum arquivo de teste e
  nenhum runner em `requirements.txt`).

## 8. Arquivos de referência rápida

| Arquivo | Papel |
|---|---|
| `main.py` | carga do CSV, catálogo fixo de sequências, todas as rotas |
| `musica.py` | modelo `Musica` (`cifra`, `acordes`, `seqs_famosas`, `tom`, `url`) |
| `scripts/generate_data_set.py` | geração offline da coluna `SEQ_FAMOSA` e da `CIFRA` |
| `data/top/dataset_final.csv` | 67.586 linhas; col 7 tags, col 8 cifra |
| `data/mapeamento_sequencias_famosas.txt` | rótulos dos ids 0–5 (não lido por código) |
| `data/dataset_seq_notas.csv` | cifras normalizadas em graus (usado só por scripts R) |
| `Dockerfile` | imagem única `python:3.9-slim` + gunicorn na 8080 |
| `requirements.txt` | Flask 3.1.3, gunicorn 23.0.0 |
| `docs/adr/0001-local-only-docker-deploy.md` | decisão de deploy local-only |
| `docs/adr/0002-persist-custom-sequences.md` | decisão de persistir o catálogo em SQLite (preenchida depois da pesquisa) |
| `docs/features/sequencias-customizadas/00-enunciado.md` | restrições e requisitos da tarefa |
| `static/assets/js/controllers/sequencia.js` | 4 sequências fixas e chamada a `/similares` |
| `static/templates/sequencia.html` | layout da página `#/porsequencia` |
| `static/assets/js/app.js` | constante `GENEROS` (51 entradas) |

## 9. Nota companheira

Este documento é descritivo. A pesagem de prós e contras das opções de banco e da
execução da regra do gerador em runtime, com as medições correspondentes, está em
[`avaliacao-banco-e-runtime.md`](avaliacao-banco-e-runtime.md).
