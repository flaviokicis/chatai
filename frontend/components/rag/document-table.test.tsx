import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DocumentSummary } from "@/lib/rag-admin";

import { DocumentTable } from "./document-table";

const sampleDocuments: DocumentSummary[] = [
  {
    id: "doc-1",
    fileName: "Onboarding.pdf",
    fileType: "pdf",
    fileSize: 1024 * 150,
    createdAt: "2024-11-10T12:00:00.000Z",
    chunkCount: 12,
  },
  {
    id: "doc-2",
    fileName: "Pricing.md",
    fileType: "md",
    fileSize: 2048,
    createdAt: "2024-11-12T08:30:00.000Z",
    chunkCount: 5,
  },
];

describe("DocumentTable", () => {
  it("renders loading indicator when data is loading", () => {
    render(
      <DocumentTable
        documents={[]}
        isLoading
        onViewDocument={() => {}}
        onDeleteDocument={() => {}}
      />
    );

    expect(screen.getByText(/Loading documents/i)).toBeInTheDocument();
  });

  it("renders empty state when no documents are present", () => {
    render(
      <DocumentTable
        documents={[]}
        isLoading={false}
        onViewDocument={() => {}}
        onDeleteDocument={() => {}}
      />
    );

    expect(
      screen.getByText(/No documents uploaded for this tenant yet/i)
    ).toBeInTheDocument();
  });

  it("displays document rows and triggers callbacks", async () => {
    const user = userEvent.setup();
    const handleView = vi.fn();
    const handleDelete = vi.fn();

    render(
      <DocumentTable
        documents={sampleDocuments}
        isLoading={false}
        onViewDocument={handleView}
        onDeleteDocument={handleDelete}
      />
    );

    const onboardingRow = screen.getByText("Onboarding.pdf").closest("tr");
    const pricingRow = screen.getByText("Pricing.md").closest("tr");

    expect(onboardingRow).not.toBeNull();
    expect(pricingRow).not.toBeNull();
    expect(onboardingRow).toHaveTextContent("12");
    expect(pricingRow).toHaveTextContent("5");

    await user.click(screen.getByRole("button", { name: /View document Onboarding.pdf/i }));
    expect(handleView).toHaveBeenCalledWith("doc-1");

    await user.click(screen.getByRole("button", { name: /Delete document Pricing.md/i }));
    expect(handleDelete).toHaveBeenCalledWith("doc-2");
  });
});
