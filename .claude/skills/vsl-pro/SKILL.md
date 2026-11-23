---
name: vsl-pro
description: Cria VSLs (vídeos de vendas) profissionais e completos para redes sociais — roteiro de alta conversão, narração e vídeo renderizado em MP4 (9:16, 1:1 ou 16:9). Use quando o usuário pedir VSL, vídeo de vendas, anúncio em vídeo ou roteiro de vendas.
---

# VSL Pro — vídeo de vendas profissional

Você produz uma VSL do zero até o MP4 final: briefing → roteiro → revisão → narração → render → conferência.

## 1. Briefing (pergunte só o que faltar, numa mensagem só)

- **Produto** e o que a pessoa recebe (formato, módulos, bônus)
- **Preço** e forma de acesso
- **Público** e a principal dor/desejo dele
- **Prova** real disponível (experiência, cases, números verdadeiros) — nunca invente
- **Imagem** do apresentador ou do produto (caminho do arquivo)
- **Formato**: 9:16 (Reels/TikTok/Shorts), 1:1 (feed) ou 16:9 (YouTube); duração (60s curta ou 2–3 min completa)
- **CTA**: para onde a pessoa vai (link da bio, botão, WhatsApp)
- **Narração**: voz sintética (edge-tts), áudio gravado pelo próprio usuário, ou só texto na tela

Se o usuário já deu as informações, não pergunte de novo — siga.

## 2. Roteiro

Leia `references/estrutura-vsl.md` e escreva o roteiro seguindo a estrutura de 12 blocos.
Regras:
- Gancho nos primeiros 3 segundos (pergunta ou afirmação que bate na dor).
- Frases curtas, linguagem falada, uma ideia por cena.
- Texto na tela = versão enxuta da fala (máx. ~12 palavras por linha).
- **Ética obrigatória**: nada de renda garantida, depoimentos falsos, escassez falsa ou números inventados. Se o produto não garante resultado, diga isso — aumenta a confiança.
- Mostre o roteiro ao usuário em tabela (cena | fala | texto na tela) e peça aprovação antes de renderizar, a não ser que ele tenha pedido para ir direto.

## 3. Montar o arquivo de cenas

Crie um `vsl.json` seguindo `examples/exemplo.json`. Campos principais:
- `photo`, `size` (`1080x1920`, `1080x1080` ou `1920x1080`), `accent` (cor de destaque em hex), `brand`
- `voice`: `"edge"` (gera narração com edge-tts), `"files"` (cada cena tem `"audio": "caminho.mp3"`) ou `"none"`
- `edge_voice`: ex. `pt-BR-AntonioNeural` (masculina) ou `pt-BR-FranciscaNeural` (feminina)
- `scenes`: lista com `mode` (`hero` = foto em destaque com zoom lento; `dark` = fundo escuro desfocado), `say` (fala da narração), `dur` (segundos — opcional se houver narração; aí a duração segue o áudio) e `items`.
- `items`: `[tempo, tipo, texto]`. Tipos: `h` título branco, `g` título destaque, `s` texto menor, `x` nome grande do produto, `price` preço gigante, `b` item com check, `tag` pílula, `strike` texto riscado (preço antigo).
  O tempo pode ser número (segundos) ou fração `"0.4"`… use números simples; com narração, os tempos são ajustados proporcionalmente à duração real da cena.

## 4. Renderizar

```bash
pip install pillow numpy edge-tts   # edge-tts só se voice = "edge"
python3 scripts/render_vsl.py vsl.json --preview   # gera frames de conferência em out/preview/
python3 scripts/render_vsl.py vsl.json             # gera out/VSL_final.mp4
```
Requer `ffmpeg` instalado.

Antes do render completo, rode `--preview`, abra as imagens e confira: texto cortado, sobreposição, legibilidade, rosto visível. Corrija o JSON e só então renderize.

## 5. Entrega

- Confira o MP4 final (duração, áudio presente, 2–3 frames extraídos com ffmpeg).
- Entregue: o vídeo, o roteiro em texto e uma legenda de post curta com CTA e 3–5 hashtags.
- Sugira 1 variação de gancho para teste A/B.

## Dicas de conversão
- Rosto do apresentador no início e no CTA gera confiança.
- Mostre o que a pessoa recebe de forma concreta (lista com checks).
- Ancoragem de preço só com comparação verdadeira ("menos que um lanche").
- Repita o CTA no fim falado E escrito.
