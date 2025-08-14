"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { PositionedNode, QuestionNodeSummary } from "./types";
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
  const questionPrompt: string | undefined = node.kind === "Question" ? (node as unknown as QuestionNodeSummary).prompt : undefined;
  const isExpandable: boolean = !!questionPrompt;
  const kindLabel = node.kind === "Question" ? "Pergunta" : node.kind === "Decision" ? "Decisão" : "Terminal";

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
    return node.kind === "Question" && questionPrompt ? questionPrompt : node.label ?? node.id;
  }, [node, questionPrompt]);
  return (
    <div className={`${styles.nodeCard} ${flat ? styles.nodeCardFlat : ""} ${accent} ${highlighted ? styles.nodeCardActive : ""} ${variant === "compact" ? styles.nodeCardCompact : ""}`}>
      <div className={styles.nodeHeader}>
        <div
          className={`${variant === "compact" ? styles.nodeTitle : "font-medium truncate"} ${isExpandable ? styles.clickableTitle : ""}`}
          onClick={toggleOverlay}
          role={isExpandable ? "button" : undefined}
          tabIndex={isExpandable ? 0 : -1}
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
            {questionPrompt ? <div className={styles.overlayBody}>{questionPrompt}</div> : null}
            {questionPrompt ? (
              <div className={styles.overlayHint}>
                Observação: as perguntas mostradas aqui são reescritas automaticamente conforme o
                contexto da conversa para soar naturais ao usuário.
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}


