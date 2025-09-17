---
doc_type: implementation_guide
source_flow_id: flow.atendimento_luminarias
version: 1.0.0
tags: [implementacao, ambientes, projeto, montagem, comissionamento]
environments: [industria_galpao, quadra_coberta, quadra_descoberta, campo_futebol, posto_gasolina]
languages: [pt-BR]
last_updated: 2025-09-17
---

# Guia de Implementação por Ambiente — Iluminação LED

Este guia resume boas práticas para seleção, instalação e comissionamento por ambiente conforme o fluxo. Deve ser usado em conjunto com o catálogo e com estudos luminotécnicos.

## Indústria / Galpão (produção e portapallets)

- Objetivo: níveis de iluminância 300–500 lux (produção), 200–300 lux (armazenagem), uniformidade ≥ 0,6 (tarefa)
- Produto típico: HighBay HB-Pro 120–240 W, óptica 60°/90°, CCT 4000–5000K, PF ≥ 0,95
- Montagem: 8–14 m de altura, espaçamento 1–1,5x a altura; pendente ou suporte rígido
- Dimerização: 0–10V com sensores (presença/luz) por corredor; reduzir consumo fora do horário de pico
- Cabeamento: circuito dedicado por fileira, bitola conforme corrente, proteção contra surtos (SPD)
- Comissionamento: configurar níveis-alvo e perfis; medir pontos críticos (solo e prateleiras)
- Observações: poeira/óleo → preferir IP65; cuidado com ofuscamento em picking

## Quadra Coberta

- Objetivo: 300–500 lux treino/recreativo; UGR reduzido para conforto visual
- Produto típico: Projetor SP-Arena 200–400 W, óptica 40°/60°, visor anti-ofuscamento
- Montagem: 8–12 m, evitar ângulos diretos ao campo de visão do atleta
- Dimerização: 0–10V/DALI por zona; cenas para treino/jogo/limpeza
- Comissionamento: medir uniformidade longitudinal e transversal; ajustar inclinação
- Observações: superfícies refletivas → avaliar CCT 4000K para conforto

## Quadra Descoberta

- Objetivo: 200–300 lux recreativo; resistência a intempéries e vibração
- Produto típico: SP-Arena 400–600 W, óptica 25°/40°, IP66
- Montagem: postes de 12–16 m, ângulo anti-ofuscamento, layout 4–6 postes
- Dimerização: perfis noturnos para vizinhança; sensores de presença
- Comissionamento: checar fixações, torque e aterramento; medições pós-instalação

## Campo de Futebol (society)

- Objetivo: 200–500 lux; uniformidade ≥ 0,5; controle de ofuscamento
- Produto típico: SP-Arena 400–600 W, óptica 10°/25° (lances longos), shields locais
- Montagem: 12–18 m, 4–8 postes; cross-aiming para uniformidade
- Dimerização: cenas pré-programadas (treino, jogo, manutenção)
- Comissionamento: aferir lux em grade 10x10; ajustar tilt/azimute

## Posto de Gasolina (Canopy)

- Objetivo: 150–300 lux zona de abastecimento; uniformidade ≥ 0,5
- Produto típico: CP-Fuel 100–200 W, 300 x 300 mm, óptica 90°, IP66
- Montagem: embutir no canopy; espaçamento 3–4 m; vedação adequada
- Dimerização: 0–10V com perfil noturno (redução 30–50% após 23h)
- Comissionamento: verificação de vedação, equalização de níveis e cores

## Boas Práticas de Comissionamento

- Checklist: torque de fixações, aterramento, SPD, estanqueidade, rotulagem de circuitos
- Medições: luxímetro calibrado, pontos por norma; registro fotográfico
- Documentação: as built, parâmetros de dimerização, mapa de luminárias e circuitos

## Segurança e Normas (resumo)

- Elétrica: NR10, aterramento e proteção; disjuntores por circuito
- Fotometria: ABNT NBR 5101 (vias públicas e algumas áreas externas), recomendações CIE/IES
- IP/IK: selecionar conforme ambiente; atenção a jatos d’água e impactos


