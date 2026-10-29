angular.module('deciframeApp').controller('SequenciaController', function($http, $window, ngProgressFactory, $anchorScroll, $location, GENEROS) {
  var COR_ACORDE = '#2E1C74';
  var vm = this;

  vm.sequenciasFamosas = [];
  vm.minhaSequencia = {};
  vm.novaSequencia = "";
  vm.erroCadastro = "";
  vm.erroCatalogo = "";
  vm.enviandoCadastro = false;
  vm.isSearching = false;
  vm.showSearchResultsCount = false;
  vm.esfigeSpeech =  "";
  vm.musics = [];
  vm.generos = GENEROS;
  vm.meuGenero = "";
  vm.progressbar = ngProgressFactory.createInstance();

  var montarSequencia = function(sequencia) {
    var acordes = sequencia.acordes.split(',');
    return {
      'id': sequencia.id,
      'acordes': acordes.map(function(acorde) {
        return { 'acorde': acorde.trim(), 'cor': COR_ACORDE };
      })
    };
  }

  var carregarSequencias = function(selecionarId) {
    $http.get('sequencias')
      .success(function(data) {
        vm.erroCatalogo = "";
        vm.sequenciasFamosas = data.map(montarSequencia);
        if (selecionarId !== undefined) {
          for (var i = 0; i < vm.sequenciasFamosas.length; i++) {
            if (vm.sequenciasFamosas[i].id === selecionarId) {
              vm.pesquisarPorSequencia(vm.sequenciasFamosas[i]);
              break;
            }
          }
        }
      })
      .error(function() {
        vm.erroCatalogo = "Não foi possível carregar o catálogo de sequências.";
      });
  }

  carregarSequencias();

  vm.temAcorde = function(acorde) {
    if (vm.minhaSequencia.acordes) {
      return (vm.minhaSequencia.acordes.indexOf(acorde) > -1);
    } else {
      return false;
    }
  }

  var createChordsString = function(chords) {
    var str = "";
    for (var i = 0; i < chords.length; i++) {
      str = str.concat(chords[i].acorde, ',');
    }
    return encodeURIComponent(str.substring(0, str.length-1));
  }

  vm.cadastrar = function() {
    if (vm.enviandoCadastro) {
      return;
    }
    vm.erroCadastro = "";
    if (!vm.novaSequencia || !vm.novaSequencia.trim()) {
      vm.erroCadastro = "Informe uma sequência de acordes.";
      return;
    }

    vm.enviandoCadastro = true;
    $http.post('sequencias', { 'acordes': vm.novaSequencia })
      .success(function(nova) {
        vm.novaSequencia = "";
        carregarSequencias(nova.id);
      })
      .error(function(data, status) {
        if (status === 409) {
          vm.erroCadastro = "Essa sequência já está cadastrada.";
        } else if (status === 400) {
          vm.erroCadastro = (data && data.erro) || "Sequência inválida.";
        } else {
          vm.erroCadastro = "Ops! Algo errado.";
        }
      })
      .finally(function() {
        vm.enviandoCadastro = false;
      });
  }

  vm.pesquisarPorSequencia = function(sequencia) {
    if (sequencia) {
      vm.minhaSequencia = sequencia;
    }
    vm.progressbar.start();
    vm.esfigeSpeech = "Procurando músicas com base na sequencia...";
    vm.isSearching = true;
    vm.musics = [];

    var apiUrl = "";
    var searchString = "similares?sequencia=".concat(createChordsString(vm.minhaSequencia.acordes));
    if (vm.meuGenero !== "" && vm.meuGenero !== null) {
      searchString += "&generos=" + encodeURIComponent(vm.meuGenero);
    }
    $http.get(apiUrl.concat(searchString))
      .success(function(data) {
        vm.progressbar.complete();
        vm.esfigeSpeech = "Encontrei essas músicas";
        vm.isSearching = false;
        vm.showSearchResultsCount = true;
        vm.musics = data;
      })
      .error(function(data) {
        vm.esfigeSpeech = "Ops! Algo errado.";
        vm.isSearching = false;
        vm.showSearchResultsCount = false;
      });
  }

  vm.limparPesquisa = function() {
    vm.minhaSequencia = {};
    vm.musics = [];
  }

  vm.goToLirics = function(music) {
    $window.open(music.url);
  };

  vm.goToResults = function() {
    vm.showSearchResultsCount = false;
    $("body").animate({scrollTop: $("#results").offset().top}, "slow");
  };
});
