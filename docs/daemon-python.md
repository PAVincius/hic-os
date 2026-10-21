# HIC OS: daemon em Python (`hic.py`)

> **Aviso:** o `install.command` descrito abaixo ainda não está neste repositório, então a instalação guiada não funciona a partir de um clone.
> Os dois LaunchAgents (`com.nebuloz.hic.*.plist`) e o `uninstall.command` estão aqui; o instalador será recuperado ou reescrito.
> Enquanto isso, o daemon roda manualmente com `python3 hic.py` (veja `python3 hic.py --help`).

Sistema de disciplina de foco para macOS. Um daemon em Python roda a cada 60s,
detecta quando você saiu dos apps de trabalho, e escalona três níveis de cobrança
até ligar o Focus Mode à força.

Sem dependências externas. Roda no `python3` do sistema.

---

## Instalação

```bash
cd hic-os
chmod +x install.command uninstall.command
./install.command
```

Ou duplo-clique em `install.command` no Finder.

O instalador copia o daemon para `~/.hic/`, registra dois LaunchAgents,
cria o comando `hic` e roda o diagnóstico de permissões.

### Permissões do macOS (obrigatórias)

O macOS vai perguntar. Sem elas o monitor fica cego:

| Permissão | Para quê | Onde |
|---|---|---|
| Acessibilidade | detectar o app em primeiro plano | Ajustes → Privacidade e Segurança → Acessibilidade |
| Automação | ler a URL da aba ativa do Brave | Ajustes → Privacidade e Segurança → Automação |
| Notificações | avisos de nível 1 e 2 | Ajustes → Notificações → Script Editor |

Rode `hic doctor` a qualquer momento para ver o que está faltando.

### Focus Mode (opcional, mas é o nível 3)

O macOS não expõe o Focus Mode por CLI. A única via suportada é o app **Atalhos**.
Crie dois atalhos, exatamente com estes nomes:

1. **`HIC Focus On`** → ação "Definir Foco" → Trabalho → Ativado
2. **`HIC Focus Off`** → ação "Definir Foco" → Trabalho → Desativado

Sem eles, o resto do sistema funciona normal — só o nível 3 não liga o Focus.

---

## Comandos

```
hic status          resumo do dia no terminal
hic dash            abre o mini-app em localhost:7777 (lista clicável)
hic plan            ritual matinal 3/3/3, agora com estimativas
hic task            lista as tarefas de hoje com estimado vs real
hic task add "PR do RBAC" 45 urgent
hic task start 2    cronometra a tarefa #2
hic task done 2     conclui e mostra o delta
hic task est 2 90   corrige a estimativa
hic frog "tarefa" 90    inicia bloco de deep work (minutos opcionais)
hic done            encerra o bloco atual
hic pause 30        silencia o monitor por N minutos
hic resume          religa o monitor
hic focus on|off    liga/desliga o Focus Mode
hic report 14       tabela dos últimos N dias
hic setup-focus     procura seus atalhos de Foco e configura sozinho
hic reclassify 7    reprocessa os logs com o config atual
hic doctor          testa todas as permissões
hic config          abre o config.json
```

---

## Como o monitor decide

A cada 60 segundos ele classifica o minuto em uma de cinco categorias:

| Classe | Quando |
|---|---|
| `WORK` | app em `work_apps`, ou Brave num domínio da `work_domains` |
| `DIST` | Brave num domínio da `blocked_domains` |
| `UNKNOWN` | domínio **ou app** que não está em nenhuma lista — vai para triagem |
| `OFF` | app que você marcou como distração, ou política estrita |
| `AWAY` | teclado e mouse parados há mais de 45 min |
| `LOCKED` | tela travada ou descanso de tela |
| `BLIND` | o macOS não devolveu o app — falta Acessibilidade |
| `NEUTRAL` | Spotify, Calendário — nem conta nem penaliza |

### As três listas de domínio

O sistema não tenta adivinhar se um site é "de tech". Ele trabalha com três estados:

- **`work_domains`** — allowlist. Silêncio. Semeada com ~119 domínios: dev, cloud,
  ML/pesquisa, IA, Google Workspace (Gmail e Meet **são** trabalho), gestão,
  LinkedIn, admin brasileiro e o domínio de saúde.
- **`blocked_domains`** — ~52 domínios. Cobra em 90 segundos. Redes, streaming,
  portais de notícia, compras, games, apostas, delivery.
- **Nem uma nem outra** → classe `UNKNOWN`. **Registra e não cobra.** Aparece no
  card "Domínios para triar" do dashboard com dois botões: *é trabalho* / *é
  distração*. Um clique escreve no `config.json`.

Por que não uma allowlist pura: pelo seu próprio log, 31% do tempo de navegador
estava em domínios que não são "de tech" mas são trabalho — Gmail, Meet, gov.br.
Allowlist rígida vira enxurrada de alerta no primeiro dia, e alerta errado mata
o sistema. A terceira classe converge para o seu fluxo real em uma semana sem
cobrar nada errado no caminho.

Casamento é **por sufixo de domínio**, não por substring: `github.com` casa
`gist.github.com` e não casa `notgithub.com`. E `google.com` puro ficou fora da
allowlist de propósito — só os subdomínios de trabalho passam, então busca no
Google cai em `UNKNOWN` até você decidir.

Se preferir a versão rígida, mude `unknown_domain_policy` para `"block"` no config.
`"allow"` volta ao comportamento antigo (só cobra o que está na blocklist).

### Escalonamento

Fora dos apps de trabalho, dentro do expediente:

- **20 min** → notificação discreta
- **25 min** → notificação + voz do macOS
- **30 min** → notificação + voz + janela modal que rouba o foco + Focus Mode ligado
- depois disso, re-dispara a cada 10 min até você voltar

Dentro de um bloco (`hic frog`) o primeiro aviso cai para **5 minutos**.

Domínio bloqueado tem caminho rápido: cobra em **90 segundos**, não em 20 minutos.

## Módulo fim de semana

Sábado e domingo **não são uma cópia do dia útil**. Dia útil protege o tempo do
trabalho de deriva; fim de semana protege você do próprio excesso. Por isso o
alvo é um **teto**, não um piso.

| | dia útil | fim de semana |
|---|---|---|
| janela | 09:00–18:00 (almoço isento) | 09:00–20:00 |
| alvo | 240 min (piso) | **180 min (teto)** |
| primeira cobrança | 20 min fora | 30 min fora |
| teto de escalada | nível 3 (modal + Focus forçado) | nível 2 — nunca invade a tela |
| convite matinal | 08:45, plano 3/3/3 | 10:00, **um** sapo só |

**A parada dura.** Quando você bate as 3h:

1. **No teto** → "3h00 de foco. Fecha o notebook — o resto do fim de semana é seu."
   O Focus Mode é **desligado**, e o sistema **cala a boca pelo resto do dia**:
   nenhuma cobrança para voltar ao trabalho, aconteça o que acontecer.
2. **+1h** → notificação com voz: "consistência bate intensidade em horizonte
   de cinco anos".
3. **+2h** → modal na sua cara mandando fechar. É o único caso em que o modal
   defende o descanso em vez do trabalho — e é de propósito.

O streak conta fim de semana com o alvo de fim de semana. Dia que você tirar de
`weekend_days` vira **dia protegido**: silêncio absoluto e **não quebra o streak**.

```jsonc
"weekend_enabled": true,
"weekend_days": [6, 7],        // 6=sábado, 7=domingo. Tire um para ter folga
"weekend_start": "09:00",
"weekend_end": "20:00",
"weekend_target_min": 180,     // o teto
"weekend_nag_after_min": 30,
"weekend_overrun_1_min": 60,   // avisa
"weekend_overrun_2_min": 120   // modal
```

### O que NÃO dispara

- Fora da janela do dia (09:00–18:00 útil, 09:00–20:00 fim de semana)
- Horário de almoço, 12:00–14:00 (só dia útil)
- Dia protegido — qualquer dia fora de `work_days` **e** `weekend_days`
- Depois de bater o teto do fim de semana
- Ausência longa da máquina — vira `AWAY`, e você leva um "você sumiu por X min" na volta
- Monitor pausado (`hic pause`)

---

## Configuração

`~/.hic/config.json`. Editar com `hic config`. Muda na hora, sem reinstalar.

Os campos que mais importam:

```jsonc
{
  "work_start": "09:00",          // início do expediente
  "work_end": "18:00",
  "lunch_start": "12:00",         // janela isenta
  "lunch_end": "14:00",
  "nag_after_min": 20,            // primeiro aviso
  "block_nag_after_min": 5,       // primeiro aviso DENTRO de um bloco
  "distraction_grace_sec": 90,    // tolerância em site bloqueado
  "away_after_min": 45,           // idle acima disso = ausente, não cobra
  "streak_target_min": 180,       // deep work/dia para manter o streak
  "daily_target_min": 240,        // meta da barra do dashboard
  "work_apps": [...],             // adicione seus apps aqui
  "blocked_domains": [...],       // adicione suas fugas aqui
  "voice": ""                     // ex: "Luciana" para voz PT-BR
}
```

As mensagens de cobrança também são configuráveis em `messages.l1/l2/l3`.
Se elas ficarem previsíveis demais, troque — mensagem que você já decorou
para de funcionar.

---

## A lista de prioridade

A ordem dos baldes **é** a priorização: sapo → urgentes → manutenção. Nenhuma
decisão nova de manhã, nenhum quadrante para preencher.

O que torna isso diferente de um to-do qualquer: **o daemon cronometra sozinho.**
Enquanto uma tarefa está com o cronômetro ligado, cada minuto classificado como
`WORK` é creditado nela. Você não aperta start/stop de nada — basta trabalhar.

```
[❚❚] [✓]  Pipeline de inferência    SAPO   ▓▓▓░░░░░░  47/180m
[▶ ] [✓]  Revisar PR do RBAC        URGENTE ▓▓▓▓▓▓▓▓  52/30m   ← estourou
```

- **Uma tarefa ativa por vez.** Iniciar outra pausa a anterior — o relógio não
  pode correr em duas.
- **Alerta de estouro.** Passou da estimativa que *você* deu, notificação. Passou
  do dobro, outra, sugerindo quebrar a tarefa. É a Lei de Parkinson virando dado.
- **Viés de estimativa.** O card no dashboard acumula todas as tarefas concluídas
  e diz quanto você leva em relação ao que estima. Se dá 130%, some 30% nas suas
  próximas estimativas e pare de prometer o impossível.
- `hic frog` sem argumento pega o sapo do plano, liga o cronômetro dele e usa a
  estimativa da tarefa como duração do bloco.

Tudo é clicável em `localhost:7777` — play, concluir, editar a estimativa no
próprio número, remover, adicionar. O CLI continua existindo para quem já está
no terminal.

**Os avisos da lista:** convite às 08:45 se não houver plano; ao fechar um bloco,
"X: 47min reais de 90min estimados, terminou?"; e o alerta de estouro em tempo real.

## Dashboard

`http://localhost:7777` — sobe sozinho com o sistema (LaunchAgent com `KeepAlive`).

Mostra: minutos de deep work vs. meta, streak Seinfeld, minutos de distração com
os domínios responsáveis, linha do tempo minuto a minuto do expediente, plano 3/3/3
do dia, últimos 14 dias, e onde o tempo foi por app.

Atualiza a cada 15 segundos. Só escuta em `127.0.0.1` — nada exposto na rede.

---

## Dados

Tudo local, em texto puro, seu para sempre:

```
~/.hic/config.json          configuração
~/.hic/state.json           estado corrente do monitor
~/.hic/logs/YYYY-MM-DD.jsonl   um registro por minuto
~/.hic/plans/YYYY-MM-DD.json   plano 3/3/3 do dia
~/.hic/*.log                stdout/stderr dos agents
```

Um dia de log tem ~540 linhas e ocupa uns 60 KB. Nada sai da máquina.

---

## Manutenção

```bash
launchctl list | grep hic                    # agents rodando?
tail -f ~/.hic/monitor.err.log               # erros do monitor
launchctl kickstart -k gui/$(id -u)/com.nebuloz.hic.monitor   # forçar restart
./uninstall.command                          # remove agents e CLI, preserva logs
```

Para atualizar o daemon depois de editar `hic.py`, rode `./install.command`
de novo — ele preserva seu `config.json`.

---

## Onde este sistema falha

Vale saber antes de confiar nele:

1. **Foreground ≠ deep work.** O monitor conta o Cursor aberto como trabalho.
   Cursor aberto enquanto você olha o teto por 40 minutos também conta. A métrica
   mede presença, não profundidade — ela pega o pior caso (você sumiu), não o
   caso medíocre (você está lá, improdutivo).

2. **O Brave é o ponto fraco.** Ele conta como trabalho por padrão, e a blocklist
   só cobre o que você listou. Toda fuga nova precisa ser adicionada à mão.
   Revise `blocked_domains` uma vez por semana, olhando o card "Distração" —
   ele te diz exatamente onde você está indo.

3. **Fadiga de alerta é o risco real.** Se o sistema te cobrar em momentos
   legítimos — reunião, leitura de paper, whiteboard — você vai matar o processo
   em uma semana. Quando isso acontecer, a resposta certa é `hic pause 60`,
   não `launchctl bootout`. E depois ajuste o config.

4. **Nada disso escreve código por você.** A métrica que decide se você virou HIC
   não está neste dashboard — está no que você publicou, mediu e colocou em
   produção. Este sistema só protege o tempo. O que você faz com ele é outro
   problema.
