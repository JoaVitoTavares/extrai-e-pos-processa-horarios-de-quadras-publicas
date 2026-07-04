# Extrator SP Sports — aplicação base (TCC)

Exemplo mínimo de **web scraping de site dinâmico** (feito no Bubble.io).
Como os dados não vêm no HTML e não há API JSON limpa, dirigimos um navegador
real com **Playwright**.

## O que ele faz
1. Abre `https://webarena.app/arena/sp-sports`
2. Clica no esporte **Futebol de salão**
3. Seleciona o **dia atual** no calendário (`.picker__day--today`)
4. Seleciona o período **Noite**
5. Imprime os horários (Livre / Indisponível)

## Instalação
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso
```bash
python scraper.py          # roda sem abrir janela (headless)
python scraper.py --ver    # abre o navegador pra você ASSISTIR o passo a passo
```

## Próximos passos (para evoluir no TCC)
- **Agendar** de 15/30 min: `cron` em uma VPS Linux (`*/15 * * * *`)
- **Guardar histórico**: salvar cada coleta em SQLite/CSV
- **Alertar**: notificar quando um horário mudar de "Indisponível" para "Livre"
- Parametrizar esporte/período/data via argumentos de linha de comando

## Conceito-chave
Sempre desça a "escada" do mais leve pro mais pesado:
`requests` (HTML estático) → API JSON (aba Network) → **navegador headless**
(este caso). Aqui caímos no último degrau porque o site é dinâmico e a API é
ofuscada.
