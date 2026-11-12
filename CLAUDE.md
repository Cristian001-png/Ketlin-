# Instruções do projeto

## Idioma
- Responda **sempre em português do Brasil**: mensagens, resumos, tabelas,
  vereditos e explicações.
- Quando um script imprimir texto em inglês, traduza ao apresentar o resultado.
  Mantenha tickers, números, comandos, caminhos de arquivo e chaves JSON como estão.
- Mensagens de commit também em português.

## Skills de day trade (`.claude/skills/trader-*`)
Instaladas a partir de github.com/Jakeschincariol/day-trader-skill (licença MIT,
ver `.claude/skills/LICENSE-day-trader-skill`). Fluxo típico de um pregão:

1. `/trader-scanner` – varre o mercado e monta a watchlist
2. `/trader-news` – notícias e 8-K de cada ação da watchlist
3. `/trader-entry` – sinaliza o momento da entrada
4. `/trader-exit` – define stop e alvo
5. `/trader-timemachine` – simula 10.000 desfechos do trade
6. `/trader-budget` – calcula quantas ações comprar
7. `/trader-risk` – confere os limites (PASS / BLOCK)
8. `/trader-broker` – envia a ordem (paper trading por padrão, só com o seu "sim")

Extras: `/trader-alerts` (alertas de preço), `/trader-analyst` (análise de
resultados), `/trader-pelosi` (trades declarados por membros do Congresso dos EUA).

Preços em US$ e horários no fuso de Nova York (ET). Nada aqui é recomendação de investimento.
