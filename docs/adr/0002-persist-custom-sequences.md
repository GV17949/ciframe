# Persist custom chord sequences in SQLite, matched at request time

The six "famous" chord sequences were hardcoded in `main.py` (a module-level dict,
removed by this decision) and could only be discovered through a column that the
offline dataset generator wrote into `data/top/dataset_final.csv` (`SEQ_FAMOSA`,
produced by `scripts/generate_data_set.py:7-24` and concatenated at lines 84-88).
Adding a sequence meant editing the generator, regenerating the CSV and redeploying,
and the frontend kept its own hardcoded copy of four of the six. The coursework
feature (`docs/features/sequencias-customizadas/00-enunciado.md`) requires any
anonymous visitor to register a sequence, search with it straight away, and have the
catalog survive a container restart, without leaving the single local-only container
decided in `0001-local-only-docker-deploy.md`.

We introduced SQLite — the `sqlite3` module already present in the
`python:3.9-slim` base image — as the project's only persistent store, holding a
`sequencias` table (id, the chord list as typed, its lowercase form for lookup and
deduplication, creation timestamp) seeded idempotently with the six originals under
their existing ids 0-5. Nothing else moved: songs, genres and the
popularity/genre indexes are still loaded from the CSV into memory at import
(`main.py:44-93`), as the task requires.

The matching rule was ported from the generator to request time instead of being
stored. A song matches a sequence when the sequence appears as a contiguous, ordered
block of the song's chord list and the song's whole chord vocabulary is contained
in the sequence's vocabulary — the same condition `get_famosas` applies offline,
including the lowercase comparison, but anchored on token boundaries. Computed per
request over `Musica.cifra`, it takes 42-51 ms per search in the container (17-20 ms
on a faster development machine), against 37-40 ms for the previous pass that tested
the precomputed tag over the same 67,585 songs, and it reproduces the existing tags
exactly (199/296/4/5/7/3, song-for-song set equality). Storing tags for newly
registered sequences, or precomputing derived rows at registration, was rejected: it
adds state that must be invalidated whenever the CSV changes, and saves only
milliseconds at request volumes this deployment does not see.

The runtime path keeps two derived fields per song: `cifra_busca` (the joined
lowercase chord list) and `acordes_busca` (its lowercase vocabulary). They add about
57 MB of process memory on top of the CSV-loaded corpus (13 MB and 43 MB
respectively). Dropping the vocabulary set and testing membership against
`Musica.acordes` instead measured 89 ms per search, so the memory is the cheaper
trade.

SQLite was chosen over the embedded alternatives tested in the same container
(TinyDB, `shelve`/`dbm`, LMDB, DuckDB) because it is the only standard-library option
with transactions and opens plus reads the whole six-row catalog in 0.126 ms from an
8 KB file, with no new dependency; DuckDB took 16.4 ms and 536 KB for the same six
rows, and client-server databases would break the single-container constraint.

The consequences are deliberate. The catalog file lives in the container's writable
layer: it survives `stop`/`start` and `restart`, but is lost on `rm` plus a new `run`
and on image rebuilds. That matches the stated requirement (survive a restart) and
keeps the deploy contract from ADR 0001 untouched — no `VOLUME`, no compose file, no
backup story. The CSV's `SEQ_FAMOSA` column stops being read by the sequence path and
becomes dead data, though it stays in the dataset. Every search now costs CPU
proportional to the corpus (one Python loop over 67,585 songs) instead of a tag
lookup, and gunicorn still runs a single worker (`Dockerfile:12`), so concurrent
searches serialize; raising the worker count would mean revisiting SQLite connection
and WAL settings. Sequence lookup also became case-insensitive, a small behavior
change from the exact-string comparison of the hardcoded dictionary, and the page's
catalog now comes from the same table, which removes the frontend's hardcoded
four-item list. Finally, the catalog is open, anonymous and unmoderated, with no cap
on size — acceptable for the coursework scope, not for a public deployment.

Left undecided on purpose: whether the catalog later gains derived match tables or an
index (a bigram anchor costs 3.06 s of startup for 0.04-3.09 ms queries) if request
volume ever justifies it; and whether the database file should get a named volume or a
backup path if durability across rebuilds becomes a requirement.

The validation policy is decided at registration: the chord list must contain 2-12
non-empty tokens, every token must exist in the corpus vocabulary (case-insensitive
against `/acordes`, `main.py:181-190`), and duplicates are detected on the lowercase
comma-joined form, so `"C, G"` and `"c,g"` collide. Rotations such as `Bm,G,D,A` and
`G,D,A,Bm` remain distinct entries because the matching rule is order-sensitive.
