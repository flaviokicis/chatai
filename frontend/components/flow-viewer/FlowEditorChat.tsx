"use client";

import { useState } from "react";

export function FlowEditorChat() {
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([
    { role: "assistant", text: "Oi! Me diga como você quer ajustar este fluxo e eu preparo as mudanças." },
  ]);
  const [input, setInput] = useState("");

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
  }

  return (
    <div className="rounded-xl border bg-card text-card-foreground shadow-sm flex flex-col h-[420px] sm:h-[480px]">
      <div className="p-3 border-b text-sm font-medium">Editor do fluxo (beta)</div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 ${m.role === "assistant" ? "bg-muted" : "bg-primary text-primary-foreground ml-auto"}`}>
            <div className="text-sm leading-relaxed whitespace-pre-wrap">{m.text}</div>
          </div>
        ))}
      </div>
      <form onSubmit={onSubmit} className="p-3 border-t flex items-center gap-2">
        <input
          className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm"
          placeholder="Conte rapidamente o que você quer mudar neste fluxo…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="rounded-lg bg-primary text-primary-foreground px-3 py-2 text-sm">Enviar</button>
      </form>
    </div>
  );
}


