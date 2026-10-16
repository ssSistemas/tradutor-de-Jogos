# Dependências revisadas

Revisão de origem: 2026-10-16. Nenhum código de pacote, binário, modelo, imagem de usuário, fonte tipográfica ou áudio foi incorporado à exportação. Bibliotecas são importadas da instalação do sistema. Não há `pip install` automático ou código baixado no lançamento.

| Dependência | Função | Versão observada no Razer | Origem / licença principal |
|---|---|---|---|
| Python | Runtime/stdlib/TOML/HTTP local | 3.14.4 | [PSF e avisos da stdlib](https://docs.python.org/3/license.html) |
| PyGObject | Bindings GTK/Gio/GStreamer | 3.56.2 | [GNOME, LGPL-2.1-or-later](https://pygobject.gnome.org/) |
| GTK/GLib/Gio | Interface e D-Bus | GTK 4, versão exata depende do pacote | [GTK COPYING](https://gitlab.gnome.org/GNOME/gtk/-/blob/main/COPYING), LGPL-2.1-or-later e avisos por arquivo |
| Pillow | Pixels/PNG em memória | 12.1.1 | [licença upstream](https://github.com/python-pillow/Pillow/blob/main/LICENSE); pacote instalado identifica a licença histórica como HPND, upstream atual usa MIT-CMU; verificar o arquivo da versão distribuída |
| Tesseract + eng | OCR em processo filho | 5.5.0 | [Apache-2.0](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE); dados eng separados |
| GStreamer | Pipeline de vídeo RGB | 1.x | [LGPL e condições por plugin](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html) |
| PipeWire / pipewiresrc | Vídeo autorizado pelo portal | 1.6.2 (PipeWire) | [COPYING upstream](https://gitlab.freedesktop.org/pipewire/pipewire/-/blob/master/COPYING); MIT e componentes com avisos próprios |
| xdg-desktop-portal + GNOME backend | Consentimento e FD restrito | ScreenCast v5 observado | [portal oficial](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html); conferir licença e pacote do backend instalado |
| Ollama servidor local | Inferência HTTP loopback | versão não fixada nesta exportação | [MIT do código do servidor](https://github.com/ollama/ollama/blob/main/LICENSE), não é licença dos modelos |
| TranslateGemma 4B | Tradução EN → PT-BR | GGUF Q4_K_M, cerca de 3,3 GB | [lançamento oficial](https://blog.google/innovation-and-ai/technology/developers-tools/translategemma/), [termos Gemma](https://ai.google.dev/gemma/terms) |
| nvidia-smi / driver NVIDIA | Verificação de VRAM / execução GPU | instalado no sistema, não incluído | Licença do fornecedor e pacotes da distribuição |

No Debian/Ubuntu, consulte `/usr/share/doc/<pacote>/copyright` para a versão instalada. Foram lidos os avisos locais de Pillow e Tesseract; a enumeração não é um inventário de todas as dependências transitivas de uma futura distribuição binária. Não houve empacotamento binário aqui.

A pipeline usa somente vídeo cru, `videorate`, `videoconvert`, `appsink` e `pipewiresrc`; não depende de codecs de áudio nem dos protótipos ASR/TTS anteriores. Dependências de testes: `unittest`/`unittest.mock` da stdlib e as mesmas bibliotecas do sistema; fixtures são geradas em memória.
