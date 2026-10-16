# Limitações conhecidas e próximos passos

## Comportamento atual

- OCR de texto **inglês** para PT-BR; não acompanha fala ou áudio.
- Captura exige uma janela autorizada pelo portal e um recorte confirmado. O código não tenta contornar negativas. Monitor inteiro é recusado.
- O compartilhamento não verifica a identidade executável do jogo. A seleção correta é responsabilidade do usuário na prévia. Chats ou dados privados visíveis dentro da região podem ser reconhecidos.
- Não há integração com processos/memória do jogo, anticheat ou renderização interna. Isso não estabelece compatibilidade com políticas de todos os jogos.
- A legenda é uma janela GTK independente. Sobreposição, ordem das janelas, foco e tela cheia dependem do compositor. Não há clique atravessando a janela, injeção no jogo ou garantia de ficar sempre acima.
- A legenda mostra a **última leitura concluída**. Ela pode permanecer antiga quando a região fica preta, muda continuamente ou a captura para. O aviso de atraso está na janela principal; o status da legenda é oculto para manter o visual compacto.
- Animações e OCR ruidoso podem atrasar ou impedir a tradução. Recortes pequenos, estáveis e com contraste ajudam. A fila é limitada ao quadro mais recente e um recorte pendente, com um trabalhador por vez.
- No protótipo anterior, medições de tradução incluíram vários segundos de carregamento. Esta exportação conserva a liberação do alias após cada tarefa; sessão quente foi um experimento incompleto e **não foi incluída**.
- Os limites padrão de 4 GiB de RAM disponível e 5000 MiB de VRAM livre são políticas conservadoras. Não garantem ausência de travamento e não representam requisitos oficiais do modelo. Não há reserva de memória contra outros processos.
- O guarda de modelos consulta `/api/ps` e recusa carregar se houver outro modelo ativo. Existe uma janela de concorrência entre consulta e geração: não use o alias dedicado em outra sessão. Não há descarregamento global.
- Cancelar/fechar pode aguardar um bloqueio de rede local ou a carga inicial do Ollama; o timeout de geração é de 90 s. Não há promessa de parada instantânea.
- O cache e o histórico agora têm limites por quantidade, mas não há um orçamento total de memória do PipeWire/PIL/GTK nem medição conclusiva do pico junto ao jogo. Prévia em 4K ainda cria cópias grandes de pixels.

## Melhorias a validar antes de migrar o atalho

1. Abrir a cópia sem iniciar captura; verificar visual e encerramento na sessão GNOME.
2. Com consentimento do usuário, testar uma janela inofensiva e depois um recorte pequeno do jogo, medindo OCR, carga, inferência, RSS e VRAM simultaneamente.
3. Verificar conteúdo antigo na legenda, interrupção sob pressão e captura quando muda o tamanho/foco da janela.
4. Projetar sessão quente com orçamento de recursos e liberação por inatividade somente após testes. Não reativar swap como efeito colateral.
5. Só então oferecer migração explícita do atalho e escolher licença/destino de distribuição, se desejado.
