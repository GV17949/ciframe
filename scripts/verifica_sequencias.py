#!/usr/bin/env python3
# coding: utf-8
"""Regressão das 6 sequências originais e dos endpoints do catálogo.

Recalcula os matches com `sequencias.aparece` (runtime) e compara, música a
música, com a coluna `SEQ_FAMOSA` do CSV, que é o resultado que o app produzia
antes da mudança. Em seguida exercita GET/POST /sequencias,
/similares?sequencia=, /musicas e /musica/<id>/ contra um catálogo temporário
(não toca em data/sequencias.db). Sai com código 1 em qualquer divergência.

Uso (a partir da raiz do repositório):
    python scripts/verifica_sequencias.py
"""
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

import sequencias

# catálogo isolado: o import de main cria e semeia o schema neste caminho
TMP = tempfile.mkdtemp(prefix='deciframe-sequencias-')
sequencias.DB_PATH = os.path.join(TMP, 'sequencias.db')

import main


def verificar_matching():
    musicas = list(main.musicas.values())
    if not musicas:
        print('ERRO: corpus vazio; não há como comparar o matching.')
        return 1

    falhas = 0
    for id_seq, texto in sequencias.ORIGINAIS:
        seq_preparada = sequencias.preparar(sequencias.normalizar(texto))
        calculado = {
            musica.id_unico_musica
            for musica in musicas
            if sequencias.aparece(seq_preparada, musica)
        }
        esperado = {
            musica.id_unico_musica
            for musica in musicas
            if str(id_seq) in musica.seqs_famosas
        }

        if not esperado:
            print('%d %-18s ERRO: nenhuma música esperada na coluna 7' % (
                id_seq, texto))
            falhas += 1
            continue

        so_calculado = calculado - esperado
        so_esperado = esperado - calculado
        status = 'ok' if calculado == esperado else 'DIVERGIU'

        print('%d %-18s esperado=%3d calculado=%3d %s' % (
            id_seq, texto, len(esperado), len(calculado), status))

        if calculado != esperado:
            falhas += 1
            for id_musica in sorted(so_esperado):
                print('  só na coluna 7: %s' % id_musica)
            for id_musica in sorted(so_calculado):
                print('  só no runtime:  %s' % id_musica)

    return falhas


def _json(resposta):
    return json.loads(resposta.get_data(as_text=True))


def verificar_endpoints():
    cliente = main.app.test_client()
    falhas = 0

    def checar(descricao, resposta, esperado):
        if resposta.status_code == esperado:
            return 0
        print('  FALHOU %s: esperado %d, obtido %d' % (
            descricao, esperado, resposta.status_code))
        return 1

    def postar(corpo, esperado, descricao):
        return checar(descricao, cliente.post('/sequencias', json=corpo), esperado)

    # catálogo inicial: as 6 originais sob os ids 0-5
    resposta = cliente.get('/sequencias')
    falhas += checar('GET /sequencias', resposta, 200)
    if resposta.status_code == 200:
        catalogo = _json(resposta)
        ids = [item['id'] for item in catalogo]
        if ids[:6] != list(range(6)):
            print('  FALHOU GET /sequencias: ids iniciais %r' % (ids[:6],))
            falhas += 1

    # cadastro e validação
    falhas += postar({'acordes': 'Dm,G,C'}, 201, 'POST sequência nova')
    falhas += postar({'acordes': 'dm, g, c'}, 409, 'POST duplicada (caixa/espaço)')
    falhas += postar([1], 400, 'POST corpo que não é objeto')
    falhas += postar({'acordes': 1}, 400, 'POST "acordes" não-string')
    falhas += postar({'acordes': 'C'}, 400, 'POST com menos de 2 acordes')
    falhas += postar({'acordes': 'C,,G'}, 400, 'POST com acorde vazio')
    falhas += postar({'acordes': 'Xyz,Q'}, 400, 'POST com acorde desconhecido')
    falhas += checar('POST sem corpo JSON',
                     cliente.post('/sequencias'), 400)

    resposta = cliente.get('/sequencias')
    falhas += checar('GET /sequencias após cadastro', resposta, 200)
    if resposta.status_code == 200:
        catalogo = _json(resposta)
        if len(catalogo) != len(sequencias.ORIGINAIS) + 1:
            print('  FALHOU: catálogo com %d itens após um cadastro' % len(catalogo))
            falhas += 1

    # busca por sequência cadastrada e por sequência inexistente
    resposta = cliente.get('/similares', query_string={'sequencia': 'Dm,G,C'})
    falhas += checar('GET /similares?sequencia=<cadastrada>', resposta, 200)
    if resposta.status_code == 200 and not isinstance(_json(resposta), list):
        print('  FALHOU: /similares?sequencia não devolveu uma lista')
        falhas += 1

    resposta = cliente.get('/similares', query_string={'sequencia': 'Hm,Z'})
    falhas += checar('GET /similares?sequencia=<inexistente>', resposta, 200)
    if resposta.status_code == 200 and _json(resposta) != []:
        print('  FALHOU: sequência inexistente devolveu resultados')
        falhas += 1

    # endpoints de música: não podem expor campos internos nem quebrar
    resposta = cliente.get('/musicas')
    falhas += checar('GET /musicas', resposta, 200)
    if resposta.status_code == 200:
        musicas_json = _json(resposta)
        if any('cifra_busca' in m or 'acordes_busca' in m for m in musicas_json):
            print('  FALHOU: /musicas expõe campos internos do matching')
            falhas += 1

    id_musica = next(iter(main.musicas))
    resposta = cliente.get('/musica/%s/' % id_musica)
    falhas += checar('GET /musica/<id>/', resposta, 200)
    if resposta.status_code == 200:
        musica_json = _json(resposta)
        if 'cifra_busca' in musica_json or 'acordes_busca' in musica_json:
            print('  FALHOU: /musica/<id>/ expõe campos internos do matching')
            falhas += 1

    return falhas


def main_verificacao():
    try:
        falhas = verificar_matching()
        falhas += verificar_endpoints()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

    if falhas:
        print('\n%d verificação(ões) falharam.' % falhas)
        return 1

    print('\nMatching das 6 sequências e endpoints do catálogo: ok.')
    return 0


if __name__ == '__main__':
    sys.exit(main_verificacao())
