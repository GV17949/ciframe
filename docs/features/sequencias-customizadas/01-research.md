# Pesquisa — Sequências de Acordes Customizadas

## Perguntas que você precisa responder

1. **Algoritmo de matching**: hoje, as 6 sequências hardcoded em `main.py` (linhas
   40-45) são comparadas contra músicas via uma tag pré-computada
   (`SEQ_FAMOSA`/`seqs_famosas`, vinda do CSV). Sequências cadastradas pelo usuário
   não têm essa tag — o matching precisa ser calculado em tempo real a partir da
   lista de acordes de cada música (`musica.acordes`/`musica.cifra`). O que vai
   definir "a sequência X aparece na música Y"? A ordem dos acordes importa?
   Repetições de acorde dentro da música importam? É preciso normalizar (ex.:
   maiúsculas/minúsculas, variações de escrita do mesmo acorde)?
2. **Validação da hipótese**: rode o algoritmo que você está considerando contra os
   dados reais em `data/top/dataset_final.csv`, para as 6 sequências hoje
   hardcoded, e confirme (ou refute) que ele reproduz os mesmos matches que o
   código atual produz via `seqs_famosas`. Esse é o bar mínimo de correção que
   você vai usar na fase de testes.
3. **Banco de dados**: quais bancos embarcados (sem serviço externo adicional) são
   viáveis dentro do container Docker único e local-only já documentado em
   `docs/adr/0001-local-only-docker-deploy.md`? O que cada opção implica para o
   `Dockerfile` atual e para a persistência dos dados entre reinícios do
   container?
4. **Frontend existente**: o que a página `#/porsequencia`
   (`static/templates/sequencia.html` +
   `static/assets/js/controllers/sequencia.js`) já faz? Repare que ela tem hoje uma
   lista *hardcoded no JavaScript* de 4 sequências (`sequencia1`..`sequencia4`),
   diferente das 6 que existem no backend — um detalhe real e pré-existente do
   código, não um erro seu, que vale entender antes de decidir o que precisa
   mudar.

## Registro das descobertas

1. A regra identificada para determinar se um acorde aparece em uma música é
   que a sequência precisa ocorrer como bloco contíguo de acordes (os acordes
   precisam aparecer em posições adjacentes e na ordem exata), e o vocabulário
   de acordes da música inteira precisa estar contido no vocabulário da sequência.
   `main.py:40-45` define o catálogo inteiro em memória. Examinando o 
   pré-processamento da tag `SEQ_FAMOSA` verifica-se que é necessário normalizar
   para minúsculas (`scripts/generate_data_set.py:12`) e o bloco `limpa_cifra` 
   (`main.py:11-23`) aplica normalização descartando tokens vazios e usando o
   prefixo antes de `|` caso o token o contenha.Não há, no runtime, `lower()`,
   remoção de acentos, equivalência enarmônica, remoção de
   sufixos (`7`, `9`, `add9`, `(11)` etc.) nem tratamento de baixo invertido (`/F#`):
   a comparação é por igualdade exata de string. O gerador da tag, por outro lado,
   faz `acorde.lower()` (`scripts/generate_data_set.py:12`), como mencionado,
   mas a tag resultante é só um id — a cifra armazenada permanece como está no CSV.
2. Adaptar o algoritmo presente em `scripts/generate_data_set.py` parece ser uma opção
   visto que alcançada a equivalência produziria os mesmos matches que o código atual
   produz via `seqs_famosas`.
3. O `Dockerfile:8` faz `COPY . .`, então qualquer arquivo de banco presente no contexto de
   build seria copiado para a imagem; arquivos criados em runtime ficam na camada
   gravável do container. TinyDB, DuckDB, sqlite3 e dbm são bancos que funcionam sem
   compilador na imagem.
4. A página `#/porsequencia` (`static/assets/js/routes.js:17-21`) já consome
   `GET /similares?sequencia=<acordes separados por vírgula>[&generos=<gênero>]` e renderiza
   os resultados, mas o catálogo exibido é um array de 4 sequências fixas no controller
   (`static/assets/js/controllers/sequencia.js:2-37`), sem nenhuma chamada que busque o
   catálogo no backend e sem formulário de cadastro.

## Trade-offs identificados

   Balanço (gerado pelo modelo): como o catálogo tem 6 linhas, throughput não diferencia 
   — o que diferencia é dependência, custo fixo de abertura e garantia de escrita. 
   sqlite3, shelve, TinyDB e LMDB ficam todos ≤0,3 ms e ≤21 KB; DuckDB é o único fora de 
   escala; SQLAlchemy custa +0,058 ms e uma dependência por uma camada desnecessária aqui; 
   cliente-servidor já está fora pela restrição de container único.

[Opções reais que você considerou para cada decisão (algoritmo, banco, frontend) e
os prós/contras de cada uma. Isso alimenta a fase de proposta — não decida ainda
aqui.]
