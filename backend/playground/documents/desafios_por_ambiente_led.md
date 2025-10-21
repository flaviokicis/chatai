---
doc_type: challenges
source_flow_id: flow.atendimento_luminarias
version: 1.0.0
tags: [desafios, riscos, manutencao, ofuscamento, poeira, umidade]
environments: [industria_galpao, quadra_coberta, quadra_descoberta, campo_futebol, posto_gasolina]
languages: [pt-BR]
last_updated: 2025-09-17
---

# Desafios por Ambiente — Riscos e Mitigações

Este documento lista problemas recorrentes e práticas de mitigação ao projetar e operar sistemas de iluminação LED em diferentes ambientes.

## Indústria / Galpão

- Poeira/óleo em suspensão: reduzir aquecimento e evitar incrustação; usar IP65, superfície lisa
- Ofuscamento em picking: óptica 90°/prismas, visores locais e níveis adequados
- Harmônicos/queda de tensão: drivers com PF ≥ 0,95, THD < 15%, cabos dimensionados
- Altura elevada: planejar acesso com plataforma; manutenção preditiva (horímetro/telemetria)
- Vibração de pontes rolantes: fixações reforçadas, arruelas de pressão, torque especificado

## Quadra Coberta

- Ofuscamento do atleta: visores/shields, ângulos de montagem fora da linha de visão
- Reflexos em superfícies brilhantes: CCT 4000K e controle de luminância
- Ruído e interferência: manter drivers afastados de áudio/vídeo sensível
- Zonas de sombra em cantos: reforço de pontos e cross-lighting

## Quadra Descoberta

- Intempéries (chuva/vento): IP66, conectores IP68, verificação periódica de vedação
- Poluição luminosa: dimerização por horário e ópticas de feixe apertado
- Corrosão: parafusos inox, pintura resistente UV e maresia
- Vandalismo/impacto: IK09, alturas maiores e proteções físicas

## Campo de Futebol (society)

- Uniformidade longitudinal: mix de ópticas (10°/25°) e ajuste fino de tilt
- Ofuscamento em bolas altas: shields e ângulos limitados
- Sombreamento por postes: estudos de posicionamento e cross-aiming
- Segurança: afastamento de linhas de alta tensão e sinalização durante manutenção

## Posto de Gasolina (Canopy)

- Vapores e segurança: certificações de área classificada quando aplicável; vedação rigorosa
- Infiltração no embutido: verificação de drenos, gaxetas e estanqueidade
- Insetos e sujeira: vedações contínuas, limpeza programada
- Vizinhança: perfis noturnos com redução gradual e CCT confortável

## Matriz de Risco (resumo)

| Ambiente | Risco | Severidade | Mitigação |
| --- | --- | --- | --- |
| Galpão | Poeira/óleo | Alta | IP65, superfícies lisas |
| Quadra coberta | Ofuscamento | Alta | Visores, ângulo |
| Quadra descoberta | Intempéries | Alta | IP66, conectores IP68 |
| Campo | Uniformidade | Média | Mix ópticas, ajuste |
| Posto | Vapores/vedação | Alta | Certificação/selagem |

> Use esta matriz como orientação inicial; conduza análise de risco específica por site.


