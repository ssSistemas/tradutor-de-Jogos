# Validação

## Testes da exportação

Resultado: **21 testes offline aprovados**, além de compilação Python, sintaxe dos scripts shell e importação dos módulos sem instanciar a interface gráfica.

Os testes cobrem deduplicação e qualidade de quadros, armazenamento privado e limitado, preservação de nomes, contexto opcional, cancelamento antes de I/O, falhas e respostas incompletas sem cache, recusa de modelo ocupado, bloqueio por recursos, OCR simulado e tradução HTTP simulada. O portal é simulado para verificar recusa de monitor inteiro, múltiplas janelas e cancelamento sem repetição. O teste GStreamer recebe somente `videotestsrc` sintético com stride não trivial.

Os tempos desses testes não representam latência de inferência. As bindings instaladas emitem um aviso de depreciação de `GLib.unix_signal_add_full`, sem falha nos testes.

Não foi iniciado jogo, compartilhamento de tela, microfone, reprodução de áudio nem carga de modelo nessa validação. A execução gráfica completa da cópia **ainda não foi validada**. O fluxo completo durante gameplay e a compatibilidade com outros jogos continuam pendentes.

## Conteúdo e privacidade

A exportação foi feita por lista explícita de arquivos: código próprio, configuração de exemplo, Modelfile de referência, scripts, documentação e testes. Não inclui capturas, textos privados reconhecidos, logs, cache, áudio, vozes, modelos, ambientes Python ou credenciais.

Os módulos originais foram preservados e seus hashes comparados após a exportação. A lista de arquivos foi revisada e uma busca de assinaturas de credenciais e caminhos privados não encontrou ocorrências. Essa busca não é uma garantia universal de detecção de segredos.

Os relatórios locais de diagnóstico do ambiente não são parte da publicação. Esta documentação contém somente os procedimentos e os resultados dos testes do software.

## Migração local

O alias dedicado foi preparado por cópia local de pesos já existentes, sem download ou carga de inferência. Imports dos módulos, disponibilidade dos elementos GStreamer e executáveis dos launchers foram verificados sem abrir captura.

A adaptação local do atalho foi feita com backup e reversão, fora do repositório. Sua sintaxe e destino foram conferidos; isso **não é teste gráfico completo**. O piloto anterior foi preservado. Backups e caminhos locais não acompanham a publicação.
