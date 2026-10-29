# deciframe

Descubra as músicas que você já sabe tocar (e ainda não faz ideia). Busque por
título/artista, gênero, pelos acordes que você já manja, ou por sequências de
acordes famosas — o deciframe cruza isso com uma base de cifras e sugere
músicas parecidas.

Stack: backend Flask (Python) servindo uma API JSON + um frontend AngularJS
estático, numa base de dados carregada de um CSV em memória (sem banco).

## Rodando localmente

### Com Docker

```
docker build -t ciframe .
docker run -p 8080:8080 ciframe
```

Acesse [http://localhost:8080](http://localhost:8080).

### Com virtualenv

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Acesse [http://localhost:5000](http://localhost:5000).

### Catálogo de sequências

As sequências de acordes (as 6 originais e as cadastradas em `#/porsequencia`)
ficam em `data/sequencias.db` (SQLite), criado e semeado no primeiro start. O
arquivo vive na camada gravável do container: sobrevive a `stop`/`start` e
`restart`, mas é perdido ao remover o container (`rm` + novo `run`) ou ao
rebuildar a imagem. As músicas e gêneros continuam vindo do CSV em memória.

Endpoints do catálogo: `GET /sequencias` (lista `[{id, acordes}]`) e
`POST /sequencias` com `{"acordes": "Dm,G,C"}` (`201` criado, `400` inválido,
`409` duplicada).

---

Para convenções de contribuição, veja [CONTRIB.md](CONTRIB.md). Licença: [LICENSE](LICENSE).
