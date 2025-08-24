"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { PositionedNode, QuestionNodeSummary, DecisionNodeSummary, TerminalNodeSummary, ActionNodeSummary } from "./types";
import styles from "./styles.module.css";

function KindBadge({ kind }: { kind: string }) {
  const cls =
    kind === "Question" ? styles.qBadge : kind === "Decision" ? styles.dBadge : styles.tBadge;
  return <span className={`${styles.badge} ${cls}`}>{kind}</span>;
}

export function NodeCard({ node, highlighted, variant = "default", flat }: { node: PositionedNode; highlighted?: boolean; variant?: "default" | "compact"; flat?: boolean }) {
  const showMeta = variant === "default";
  const showBadge = variant === "default";
  const accent = variant === "default" ? (node.kind === "Question" ? styles.qAccent : node.kind === "Decision" ? styles.dAccent : styles.tAccent) : "";
  
  // Extract meaningful content for different node types
  const questionPrompt: string | undefined = node.kind === "Question" ? (node as QuestionNodeSummary).prompt : undefined;
  const decisionPrompt: string | undefined = node.kind === "Decision" ? (node as DecisionNodeSummary).decision_prompt || undefined : undefined;
  const terminalReason: string | undefined = node.kind === "Terminal" ? (node as TerminalNodeSummary).reason || undefined : undefined;
  const actionType: string | undefined = node.kind === "Action" ? (node as ActionNodeSummary).action_type : undefined;
  
  // Node is expandable if it has meaningful content to show
  const expandableContent = questionPrompt || decisionPrompt || terminalReason || actionType;
  const isExpandable: boolean = !!expandableContent;
  
  const getKindLabel = (kind: string) => {
    switch (kind) {
      case "Question": return "Pergunta";
      case "Decision": return "Decisão";
      case "Terminal": return "Terminal";
      case "Action": return "Ação";
      case "Subflow": return "Subfluxo";
      default: return kind;
    }
  };
  
  const kindLabel = getKindLabel(node.kind);

  const [isOverlayOpen, setIsOverlayOpen] = useState(false);

  const toggleOverlay = useCallback(() => {
    if (!isExpandable) return;
    setIsOverlayOpen((v) => !v);
  }, [isExpandable]);

  useEffect(() => {
    if (!isOverlayOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOverlayOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [isOverlayOpen]);

  const nodeTitle = useMemo(() => {
    return expandableContent || node.label || node.id;
  }, [expandableContent, node]);
  return (
    <div className={`${styles.nodeCard} ${flat ? styles.nodeCardFlat : ""} ${accent} ${highlighted ? styles.nodeCardActive : ""} ${variant === "compact" ? styles.nodeCardCompact : ""}`}>
      <div className={styles.nodeHeader}>
        <div
          className={`${variant === "compact" ? styles.nodeTitle : "font-medium truncate"} ${isExpandable ? styles.clickableTitle + " transition-colors" : ""}`}
          onClick={toggleOverlay}
          role={isExpandable ? "button" : undefined}
          tabIndex={isExpandable ? 0 : -1}
          title={isExpandable ? "Clique para ver detalhes completos" : undefined}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && isExpandable) {
              e.preventDefault();
              toggleOverlay();
            }
          }}
        >
          {nodeTitle}
        </div>
        {showBadge ? <KindBadge kind={node.kind} /> : null}
      </div>
      {showMeta ? (
        <div className={styles.meta}>
          <div>Código: {node.id}</div>
          {node.isEntry ? <div>Início</div> : null}
        </div>
      ) : null}
      {variant === "default" && node.kind === "Question" && questionPrompt ? (
        <div className={styles.prompt}>
          <div className={styles.promptTitle}>Pergunta</div>
          <div className={styles.promptBody}>{questionPrompt}</div>
        </div>
      ) : null}
      {variant === "default" ? (
      <div className={styles.outgoing}>
        <div className={styles.outgoingTitle}>Saídas</div>
        <ul className={styles.outgoingList}>
          {node.outgoing.map((e, i) => (
            <li key={`${e.source}->${e.target}#${e.priority ?? 0}#${i}`}>
              {e.label ? <span className={styles.edgeLabel}>{e.label}</span> : null}
              {e.target}
              {e.condition_description ? (
                <span className={styles.edgeCond}> – {e.condition_description}</span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      ) : null}

      {isOverlayOpen ? (
        <div className={styles.overlayBackdrop} onClick={() => setIsOverlayOpen(false)}>
          <div className={styles.overlayCard} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <button aria-label="Fechar" className={styles.overlayClose} onClick={() => setIsOverlayOpen(false)}>
              ×
            </button>
            <div className={styles.overlayHeader}>
              <span className={`${styles.badge} ${node.kind === "Question" ? styles.qBadge : node.kind === "Decision" ? styles.dBadge : styles.tBadge}`}>{kindLabel}</span>
              <div className={styles.overlayMeta}>Código: {node.id}</div>
            </div>
            
            {/* Show content based on node type */}
            {questionPrompt ? (
              <>
                <div className={styles.overlayBody}>{questionPrompt}</div>
                <div className={styles.overlayHint}>
                  Observação: as perguntas mostradas aqui são reescritas automaticamente conforme o
                  contexto da conversa para soar naturais ao usuário.
                </div>
              </>
            ) : null}
            
            {decisionPrompt ? (
              <>
                <div className={styles.overlayBody}>{decisionPrompt}</div>
                <div className={styles.overlayHint}>
                  Esta é a lógica de decisão que determina o próximo passo no fluxo.
                </div>
              </>
            ) : null}
            
            {terminalReason ? (
              <>
                <div className={styles.overlayBody}>{terminalReason}</div>
                <div className={styles.overlayHint}>
                  Este é um ponto final do fluxo. {(node as TerminalNodeSummary).success ? "Fluxo concluído com sucesso." : "Fluxo finalizado."}
                </div>
              </>
            ) : null}
            
            {actionType && !questionPrompt && !decisionPrompt && !terminalReason ? (
              <>
                <div className={styles.overlayBody}>Tipo de ação: {actionType}</div>
                <div className={styles.overlayHint}>
                  Esta é uma ação executada automaticamente pelo sistema.
                </div>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}


