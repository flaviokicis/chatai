---
doc_type: faq_technical
source_flow_id: flow.atendimento_luminarias
version: 1.0.0
tags: [faq, tecnico, led, fotometria, eletrico, normas, dimerizacao]
environments: [industria_galpao, quadra_coberta, quadra_descoberta, campo_futebol, posto_gasolina]
languages: [pt-BR]
last_updated: 2025-09-17
---

# FAQ Técnico — Iluminação LED

Perguntas e respostas técnicas frequentes sobre nossos produtos e práticas de projeto/instalação.

## Especificação e desempenho

Q: Qual a diferença entre lm (lúmen), lux e W?
A: Lúmen mede fluxo luminoso (quantidade de luz). Lux mede iluminância (luz incidente por área). Watt é potência elétrica consumida. Eficiência luminosa ≈ lúmens por watt (lm/W).

Q: O que significa L70/L80 e B10?
A: Indicadores de manutenção de fluxo ao longo do tempo (LM-80/TM-21). L80B10 100.000 h significa que, após 100.000 horas, ao menos 90% das unidades mantêm ≥ 80% do fluxo inicial.

Q: Como controlar ofuscamento (UGR) em quadras?
A: Use ópticas adequadas (25°–60°), visores/shields e ângulos de montagem fora da linha de visão dos atletas. Em ambientes internos, priorize UGR baixo com difusores/visores e layout adequado.

Q: Qual CCT/CRI recomendado para indústria e esportes?
A: Indústria: 4000–5000K, CRI ≥ 80 (≥ 90 para inspeção de cor). Esportes: 5000K, CRI ≥ 80 (≥ 90 para TV/filmagem). Ajustar conforme conforto visual e refletâncias.

Q: O que é THD e Fator de Potência?
A: THD é Distorção Harmônica Total da corrente — preferir < 15%. Fator de Potência ≥ 0,95 melhora qualidade de energia e reduz perdas.

Q: Precisamos de proteção contra surtos (SPD)?
A: Sim. Recomendamos SPD de 4–10 kV conforme ambiente e qualidade da rede. Em áreas externas, combine SPD no driver e no quadro.

Q: Os drivers são dimerizáveis? 0–10V vs DALI?
A: Linhas padrão suportam 0–10V; DALI é opcional. 0–10V é simples e analógico; DALI é digital, endereçável e facilita cenas/monitoramento.

Q: E quanto a flicker e efeito estroboscópico (SVM)?
A: Drivers com baixa ondulação de ripple e dimerização adequada minimizam flicker. Para ambientes sensíveis, considerar especificação com SVM < 0,9 e percent flicker reduzido.

## Proteção mecânica e ambiental

Q: O que significam IP e IK?
A: IP indica proteção contra poeira/água (ex.: IP65/66). IK indica resistência a impacto (ex.: IK08/09). Selecione conforme risco do ambiente.

Q: Postos de gasolina exigem certificação de área classificada?
A: Em áreas com vapores inflamáveis sim. A linha CP-Fuel possui versões com certificações específicas — confirmar escopo do projeto.

Q: Como lidar com poeira, óleo e vibração em galpões?
A: Use luminárias IP65 com superfícies lisas, fixações com torque correto e arruelas de pressão. Planeje manutenção periódica.

## Projeto e instalação

Q: Existe equivalência simples entre LED e lâmpadas metálicas (HQI/HPS)?
A: Como regra inicial, considere 1:1 por fluxo (lm), mas a distribuição óptica e a altura de montagem impactam muito. Sempre validar com estudo luminotécnico.

Q: Qual altura/ângulo para quadra descoberta e campo?
A: Tipicamente 12–18 m; ópticas 10°/25° para lances longos. Cross-aiming melhora uniformidade. Evitar ofuscamento direto.

Q: Cabeamento e queda de tensão em longas linhas?
A: Dimensione seção do cabo pelo comprimento e corrente, mantendo queda de tensão dentro de limites. Separe circuitos por zona para dimerização.

Q: Posso usar sensores de presença/luz?
A: Sim. Integração via 0–10V/DALI. Em galpões com corredores, sensores por fileira reduzem consumo mantendo segurança operacional.

## Documentação e conformidade

Q: Vocês fornecem arquivos fotométricos (IES/LDTS)?
A: Sim, sob demanda. Úteis para Dialux/Relux, permitindo simulação precisa por ambiente.

Q: Quais normas devo observar?
A: ABNT NBR 5101 (vias públicas e áreas externas correlatas), recomendações CIE/IES, NR10 (segurança elétrica), além de requisitos locais do cliente.

Q: Garantia e condições?
A: Garantia padrão 5 anos, considerando rede estável, temperatura ambiente dentro da faixa e instalação conforme manual.

## Manutenção e operação

Q: Como planejar manutenção em alturas elevadas?
A: Prever pontos de ancoragem/acesso, janelas de manutenção e reposição por lotes. Telemetria/dados de driver podem apoiar manutenção preditiva.

Q: Há impacto térmico relevante?
A: Sim. Temperaturas altas reduzem vida útil. Avalie Ta/Tc especificadas e ventilação do ambiente.


