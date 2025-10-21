import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QueryResult } from "@/lib/rag-admin";

import { QueryTester } from "./query-tester";

const sampleResult: QueryResult = {
  success: true,
  noDocuments: false,
  context: "## Contexto Relevante\nDocument highlights...",
  judgeReasoning: "Chunks cobrem a pergunta.",
  attempts: 2,
  sufficient: true,
  error: null,
  chunks: [
    {
      id: "chunk-1",
      content: "Lorem ipsum dolor sit amet",
      score: 0.87,
      category: "produtos",
      keywords: "LED, vendas",
      possibleQuestions: ["Qual o diferencial do LED?"],
      metadata: { chunkIndex: 0 },
      documentName: "Onboarding.pdf",
    },
  ],
};

describe("QueryTester", () => {
  it("shows validation message when submitting an empty query", async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <QueryTester
        disabled={false}
        isLoading={false}
        onSubmit={handleSubmit}
        result={null}
      />
    );

    await user.click(screen.getByRole("button", { name: /Testar Consulta/i }));

    expect(handleSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Please provide a query to test retrieval/i)
    ).toBeInTheDocument();
  });

  it("invokes onSubmit with the provided query text", async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <QueryTester
        disabled={false}
        isLoading={false}
        onSubmit={handleSubmit}
        result={null}
      />
    );

    await user.type(
      screen.getByPlaceholderText(/Quais são os argumentos/i),
      "Benefícios do LED"
    );
    await user.click(screen.getByRole("button", { name: /Testar Consulta/i }));

    expect(handleSubmit).toHaveBeenCalledWith("Benefícios do LED");
  });

  it("renders query result with context and chunks", () => {
    const handleSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <QueryTester
        disabled={false}
        isLoading={false}
        onSubmit={handleSubmit}
        result={sampleResult}
      />
    );

    expect(screen.getByText(/Contexto Relevante/i)).toBeInTheDocument();
    expect(screen.getByText(/Judge notes/i)).toBeInTheDocument();
    expect(screen.getByText(/Chunks cobrem a pergunta/i)).toBeInTheDocument();
    expect(screen.getByText(/Lorem ipsum dolor sit amet/i)).toBeInTheDocument();
    expect(screen.getByText(/Score: 0.870/i)).toBeInTheDocument();
  });
});
