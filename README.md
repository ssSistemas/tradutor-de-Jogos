# Tradutor de Jogos

Protótipo experimental em Python/GTK para reconhecer texto em inglês de uma região de uma janela e traduzi-lo para português brasileiro usando Tesseract e TranslateGemma local via Ollama. O nome descreve a intenção do projeto; a compatibilidade com outros jogos ainda precisa ser validada.

Esta versão trabalha com **texto visível**. Não captura áudio, não transcreve falas, não usa microfone e não reproduz voz: **não há dublagem pronta**. Não promete tradução instantânea. Não há atualização automática, telemetria ou API paga. O compartilhamento da janela exige consentimento pelo portal nativo do GNOME.

## Estado

Exportação independente do piloto local. Os scripts não instalam ou substituem atalhos automaticamente. A interface mantém a legenda preta com texto branco, sem barra nativa por padrão, alça para mover e botão pequeno para fechar. A cópia foi verificada com testes offline; ainda precisa de uma sessão gráfica autorizada para validar o conjunto após a migração. **O fluxo completo durante gameplay ainda não está validado e não há garantia universal de compatibilidade com jogos.** Consulte [validação](docs/VALIDACAO.md) e [limitações](docs/LIMITACOES.md).

## Dependências e instalação

Alvo inicial: Linux, GNOME/Wayland, portal de compartilhamento de janela, PipeWire e GPU NVIDIA com `nvidia-smi`. Python 3.11+ é necessário pelo TOML da biblioteca padrão; a máquina original usa Python 3.14. Outros ambientes, CPU e outras GPUs não foram validados. As versões observadas estão em [DEPENDENCIAS.md](DEPENDENCIAS.md).

Confira os pacotes dos repositórios oficiais da sua distribuição antes de instalar. Exemplo Debian/Ubuntu, **comando manual, não executado por este projeto**:

```sh
sudo apt install python3 python3-gi python3-pil gir1.2-gtk-4.0 \
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-pipewire \
  tesseract-ocr tesseract-ocr-eng xdg-desktop-portal xdg-desktop-portal-gnome
```

Use os drivers NVIDIA e o Ollama já instalados e compatíveis com o sistema. Não execute scripts de instalação obtidos sem revisão. O projeto não instala drivers, não muda permissões do GNOME e não altera swap.

O Ollama deve servir apenas localmente em `127.0.0.1:11434`. Revise os [termos do modelo](LICENCIAMENTO.md) antes de obtê-lo. Com a base `translategemma:4b` já instalada, crie um **alias exclusivo** deste projeto:

```sh
ollama list
ollama ps
ollama create tradutor-de-jogos:4b -f Modelfile
```

Não carregue nem encerre modelos de outras sessões. Se a base não estiver instalada, o download `ollama pull translategemma:4b` é uma etapa separada e explícita, cerca de 3,3 GB na quantização observada. Pesos, executáveis e bibliotecas de terceiros não acompanham o repositório. Nenhum download ou criação de alias acontece no lançamento do aplicativo.

Configuração opcional:

```sh
mkdir -p ~/.config/tradutor-de-jogos
cp -n config.example.toml ~/.config/tradutor-de-jogos/config.toml
```

O padrão `context = "general"` não aplica termos do EVE. Use `context = "eve"` para ativar o glossário explícito desse jogo e os nomes próprios predefinidos; os nomes são editáveis na interface. `TG_CONFIG=/caminho/config.toml` seleciona outro arquivo. O único modelo permitido é o alias dedicado, evitando descarregar um modelo compartilhado por acidente.

## Iniciar e usar

Na pasta deste repositório:

```sh
./iniciar.sh
```

1. Clique em **Compartilhar janela do jogo…**. O GNOME abre seu consentimento nativo. Se cancelar ou negar, não há tentativa automática por outra API.
2. Selecione somente a janela desejada. Não inclua chats ou conversas de terceiros. O código exige uma única janela e recusa monitor inteiro.
3. Na prévia, arraste uma região pequena, estável e legível e confirme **Usar esta área do jogo**. Até essa confirmação, não ocorre OCR.
4. Confira o texto reconhecido e a tradução. Há até 2 amostras por segundo, mas OCR e tradução são executados sequencialmente e podem levar vários segundos. Animações podem impedir que a região estabilize.
5. Para a janela de legenda independente, execute `./legenda.sh`. A alça `⋮⋮` move a janela; o menu permite recuperar a barra nativa. **Esc**, **Ctrl+Q** e **Fechar legenda** fecham só a legenda. Não há atalho global.

Uma segunda execução de `iniciar.sh` abre/apresenta a legenda, sem duplicar a captura. Não há modo de compartilhamento automático no lançamento. A função **Imagem salva (diagnóstico)…** aceita somente arquivo escolhido pelo usuário, sem capturar tela.

## Parar, dados e reversão

Use **Parar compartilhamento** para fechar a sessão do portal e cancelar o trabalho próprio. **Sair** fecha o aplicativo. Alternativa na mesma pasta:

```sh
/usr/bin/python3 parar.py
```

O comando valida o PID e o caminho de `main.py` antes de sinalizar só esta cópia. A liberação da requisição local pode levar alguns segundos; não mate o serviço Ollama. O alias é liberado após cada tradução. O programa recusa carregar enquanto detecta qualquer modelo ativo em outra sessão; essa verificação não reserva o serviço contra acessos concorrentes.

Os quadros ficam na memória e não são salvos como imagens. **Texto OCR, tradução e metadados são gravados localmente**, com diretório 0700 e arquivos de resultado/cache 0600, em:

```text
${XDG_STATE_HOME:-~/.local/state}/tradutor-de-jogos/
```

O cache contém no máximo 128 entradas por padrão; o histórico do portal guarda os últimos 128 eventos, sem pixels. A legenda lê `ultimo-texto-ao-vivo.json`. Arquivos podem permanecer depois de parar. Não compartilhe esse diretório. O `.gitignore` é proteção auxiliar, não substitui revisar `git diff --cached` antes de um commit.

Depois de fechar aplicativo e legenda, para limpar os dados do **caminho padrão**, execute manualmente:

```sh
rm -r -- ~/.local/state/tradutor-de-jogos
```

Se definiu `XDG_STATE_HOME`, use o caminho correspondente. A configuração em `~/.config/tradutor-de-jogos` é separada. Se adaptou um atalho manualmente, restaure seu backup antes de remover esta cópia. O piloto anterior é independente. Se criou o alias e não o deseja mais, após parar o programa: `ollama rm tradutor-de-jogos:4b` remove só esse alias. Não remova os modelos base usados por outras sessões.

## Desenvolvimento e testes

```sh
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m compileall -q .
sh -n iniciar.sh legenda.sh
```

Os testes usam textos/pixels sintéticos e mocks. Não abrem portal, janelas, microfone, jogo ou conexão com modelo real. Um teste recebe somente `videotestsrc` sintético do GStreamer. São testes de comportamento local; não medem desempenho real do jogo.

O código principal é dividido em `main.py` (coordenação), `portal.py` (consentimento e vídeo), `region.py` (recorte), `frames.py` (estabilidade), `core.py` (OCR/tradução/cache), `viewer.py` (legenda) e `settings.py` (configuração/dados privados).

## Repositório e licença

Destino autorizado: repositório público **ssSistemas/tradutor-de-jogos**, separado do piloto. A visibilidade pública do repositório não equivale à escolha de uma licença de uso ou redistribuição. Não há licença pública escolhida para este código. As licenças das dependências são independentes. Consulte [LICENCIAMENTO.md](LICENCIAMENTO.md).
