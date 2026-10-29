class Musica:

    def __init__(self, id_artista, nome_artista, id_musica, nome_musica,
    
            genero, popularidade, seqs_famosas, tom, cifra):

            self.id_artista = id_artista
            self.nome_artista = nome_artista
            
            self.id_musica = id_musica
            self.nome_musica = nome_musica

            self.genero = genero
            self.popularidade = popularidade
            self.tom = tom
            self.cifra = cifra
            self.acordes = list(set(cifra))
            self.seqs_famosas = seqs_famosas

            # formas derivadas, calculadas uma vez por música, usadas no
            # matching de sequências em runtime (ver sequencias.aparece)
            self.cifra_busca = ';' + ';'.join(cifra).lower() + ';'
            self.acordes_busca = frozenset(a.lower() for a in cifra)

            self.id_unico_musica = '%s_%s' % (id_artista, id_musica)

            self.url = 'http://www.cifraclub.com.br/%s/%s' % (id_artista, id_musica)

    def __str__(self):
        return '%s,%s,%s' % (self.id_unico_musica, self.genero, self.popularidade)

    def to_dict(self):
        """Representação pública usada pelos endpoints; omite campos derivados
        (cifra_busca/acordes_busca) que são detalhes internos do matching."""
        return {
            'id_artista': self.id_artista,
            'nome_artista': self.nome_artista,
            'id_musica': self.id_musica,
            'nome_musica': self.nome_musica,
            'genero': self.genero,
            'popularidade': self.popularidade,
            'tom': self.tom,
            'cifra': self.cifra,
            'acordes': self.acordes,
            'seqs_famosas': self.seqs_famosas,
            'id_unico_musica': self.id_unico_musica,
            'url': self.url,
        }
