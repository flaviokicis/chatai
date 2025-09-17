## Documentos de Playground para RAG — Luminárias LED

Este diretório contém documentos fictícios, porém realistas, para testar recuperação de conhecimento (RAG) sobre luminárias e projetos de iluminação. O conteúdo está em PT‑BR, alinhado ao fluxo `backend/playground/fluxo_luminarias.json`.

### O que tem aqui

- `catalogo_de_produtos_led.md`: catálogo de produtos (famílias, modelos, especificações, acessórios, garantias).
- `implementacao_por_ambiente_led.md`: guia de implementação por ambiente conforme o fluxo (galpão/indústria, quadra coberta/descoberta, campo, posto/canopy).
- `desafios_por_ambiente_led.md`: desafios, riscos e mitigação por ambiente.
- `faq_tecnico_led.md`: perguntas e respostas técnicas (fotometria, elétrica, normas, dimerização).
- `faq_vendas_led.md`: perguntas comerciais (escopo, prazos, ROI, garantia, proposta).
- `build_pdfs.py`: script opcional para gerar PDFs a partir dos `.md`.

Todos os `.md` possuem front matter YAML com metadados úteis para testes de RAG (ex.: `doc_type`, `tags`, `environments`, `source_flow_id`).

### Geração de PDFs (opcional)

Você pode gerar PDFs locais a partir dos `.md` usando dependências puramente Python. Recomendado executar dentro do backend e gerenciar pacotes com `uv`.

1) Preparar ambiente

```bash
cd /Users/jessica/me/chatai/backend
source .venv/bin/activate
```

2) Instalar dependências necessárias com `uv` (Markdown → HTML → PDF por xhtml2pdf):

```bash
uv add markdown xhtml2pdf
```

3) Rodar o builder

```bash
uv run python backend/playground/documents/build_pdfs.py --out-dir backend/playground/documents/pdfs
```

Saída: PDFs gerados em `backend/playground/documents/pdfs` com o mesmo nome base dos arquivos `.md`.

Observações:

- Caso prefira, você pode usar ferramentas como `pandoc` ou `weasyprint`. O script tenta ser mínimo e sem dependências nativas. 
- O front matter YAML é removido do conteúdo renderizado.

### Como usar estes dados no seu RAG

- Indexe os `.md` (ou PDFs) com chunking por seções e preservação dos metadados do front matter (ex.: como atributos no vetor). 
- Use `doc_type`, `environments` e `tags` como filtros/boost no retrieval, em vez de heurísticas fixas de fluxo. 
- Estes documentos complementam o fluxo com contexto rico: escolhas de produto, níveis de iluminância, restrições normativas, mitigação de ofuscamento/poeira/umidade e recomendações práticas.

### Tipos de dados recomendados (próximos passos)

- Especificações técnicas detalhadas por modelo (fichas técnicas individuais por SKU)
- Relatórios fotométricos (ex.: sumário de arquivos IES/LDTS e curvas de distribuição)
- Guias de instalação e manutenção (checklists, torque, altura de montagem, NR10)
- Estudos de caso (antes/depois, medições de iluminância, ROI, consumo)
- Tabelas de equivâlencia (W→lm, lm→lux estimado por área e altura)
- Matriz de compatibilidade (drivers/controle: 0-10V, DALI, sensores, dimerização)
- Tabela de normas e referências (ABNT NBR 5101/ISO/CIE; IP/IK; ofuscamento UGR)
- Modelos de proposta (BOM, lead time, garantia, SLA de atendimento)
- FAQ técnico e de vendas (flicker, CRI, CCT, ofuscamento, IP/IK, THD, FP)
- CSV do catálogo estruturado (para testes de mixed retrieval tabular + texto)

### Notas de design

- Estes materiais referenciam ambientes do fluxo, mas não assumem um mapa fixo de fluxos; novos ambientes podem ser adicionados criando novos documentos com metadados adequados, mantendo o sistema agnóstico e configurável.


