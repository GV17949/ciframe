# coding: utf-8
"""Catálogo persistido de sequências de acordes famosas.

As músicas continuam no CSV em memória (ver `main.py`); este módulo guarda
apenas o catálogo de sequências no SQLite e a regra de matching em runtime.
"""
import os
import sqlite3
import threading
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'sequencias.db')

ORIGINAIS = [
    (0, 'Bm,G,D,A'),
    (1, 'C,G,Am,F'),
    (2, 'Em,G'),
    (3, 'C,A7,Dm,G7'),
    (4, 'Gm,F'),
    (5, 'C,C7,F,Fm'),
]


class SequenciaDuplicada(Exception):
    """A sequência já existe no catálogo (mesma forma normalizada)."""


_conexao_unica = None
_lock = threading.Lock()


def normalizar(texto):
    """Devolve os tokens da sequência, aparados, preservando ordem e caixa."""
    if texto is None:
        return []
    return [token.strip() for token in texto.split(',')]


def _chave(texto):
    """Forma minúscula usada para busca e deduplicação."""
    return ','.join(token.lower() for token in normalizar(texto))


def _conexao():
    global _conexao_unica
    if _conexao_unica is None:
        diretorio = os.path.dirname(DB_PATH)
        if diretorio:
            os.makedirs(diretorio, exist_ok=True)
        _conexao_unica = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conexao_unica.row_factory = sqlite3.Row
    return _conexao_unica


def criar_schema():
    with _lock:
        conn = _conexao()
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS sequencias (
                   id            INTEGER PRIMARY KEY AUTOINCREMENT,
                   acordes       TEXT NOT NULL,
                   acordes_busca TEXT NOT NULL UNIQUE,
                   criado_em     TEXT NOT NULL
               )'''
        )
        conn.commit()


def semear():
    """Insere as 6 originais de forma idempotente, sob os ids 0-5."""
    agora = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _conexao()
        for id_seq, acordes in ORIGINAIS:
            conn.execute(
                'INSERT OR IGNORE INTO sequencias '
                '(id, acordes, acordes_busca, criado_em) VALUES (?, ?, ?, ?)',
                (id_seq, acordes, _chave(acordes), agora),
            )
        conn.commit()


def listar():
    with _lock:
        linhas = _conexao().execute(
            'SELECT id, acordes FROM sequencias ORDER BY id'
        ).fetchall()
    return [{'id': linha['id'], 'acordes': linha['acordes']} for linha in linhas]


def buscar(acordes):
    with _lock:
        linha = _conexao().execute(
            'SELECT id, acordes FROM sequencias WHERE acordes_busca = ?',
            (_chave(acordes),),
        ).fetchone()
    if linha is None:
        return None
    return {'id': linha['id'], 'acordes': linha['acordes']}


def inserir(acordes):
    tokens = normalizar(acordes)
    texto = ','.join(tokens)
    agora = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _conexao()
        try:
            cursor = conn.execute(
                'INSERT INTO sequencias (acordes, acordes_busca, criado_em) '
                'VALUES (?, ?, ?)',
                (texto, _chave(texto), agora),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise SequenciaDuplicada(texto)
    return {'id': cursor.lastrowid, 'acordes': texto}


def preparar(seq_tokens):
    """Pré-calcula o bloco ancorado e o vocabulário de uma sequência.

    Deve ser chamado uma vez por busca, antes do laço sobre as músicas.
    """
    seq_lower = [token.lower() for token in seq_tokens]
    bloco = ';' + ';'.join(seq_lower) + ';'
    return bloco, frozenset(seq_lower)


def aparece(seq_preparada, musica):
    """A sequência aparece na música como bloco contíguo e ordenado da cifra,
    e o vocabulário da música está contido no vocabulário da sequência.
    """
    bloco, vocabulario = seq_preparada
    return vocabulario >= musica.acordes_busca and bloco in musica.cifra_busca
