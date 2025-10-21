"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, Save } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

interface EditMetadataDialogProps {
  documentId: string;
  documentName: string;
  currentMetadata?: Record<string, unknown> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (documentId: string, metadata: Record<string, unknown>) => Promise<void>;
  isSaving: boolean;
}

interface MetadataEntry {
  key: string;
  value: string;
  type: "string" | "number" | "boolean";
}

export function EditMetadataDialog({
  documentId,
  documentName,
  currentMetadata,
  open,
  onOpenChange,
  onSave,
  isSaving,
}: EditMetadataDialogProps): React.JSX.Element {
  const [entries, setEntries] = useState<MetadataEntry[]>([]);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newType, setNewType] = useState<"string" | "number" | "boolean">("string");

  useEffect(() => {
    if (open && currentMetadata) {
      const hiddenKeys = new Set(['file_size', 'file_path', 'tenant_id']);
      
      const metadataEntries: MetadataEntry[] = Object.entries(currentMetadata)
        .filter(([key, value]) => {
          if (hiddenKeys.has(key)) return false;
          if (value === null || value === undefined) return false;
          if (value === '') return false;
          return true;
        })
        .map(([key, value]) => {
          let type: "string" | "number" | "boolean" = "string";
          if (typeof value === "number") type = "number";
          else if (typeof value === "boolean") type = "boolean";

          return {
            key,
            value: String(value),
            type,
          };
        });
      setEntries(metadataEntries);
    } else if (open) {
      setEntries([]);
    }
  }, [open, currentMetadata]);

  const handleAddEntry = useCallback(() => {
    if (!newKey.trim()) return;

    const exists = entries.some((e) => e.key === newKey);
    if (exists) {
      return;
    }

    setEntries((prev) => [
      ...prev,
      {
        key: newKey.trim(),
        value: newValue,
        type: newType,
      },
    ]);
    setNewKey("");
    setNewValue("");
    setNewType("string");
  }, [newKey, newValue, newType, entries]);

  const handleRemoveEntry = useCallback((key: string) => {
    setEntries((prev) => prev.filter((e) => e.key !== key));
  }, []);

  const handleUpdateEntry = useCallback((key: string, newValue: string) => {
    setEntries((prev) =>
      prev.map((e) => (e.key === key ? { ...e, value: newValue } : e))
    );
  }, []);

  const handleSave = useCallback(async () => {
    const metadata: Record<string, unknown> = {};
    entries.forEach((entry) => {
      let value: unknown = entry.value;
      if (entry.type === "number") {
        value = Number(entry.value);
      } else if (entry.type === "boolean") {
        value = entry.value.toLowerCase() === "true";
      }
      metadata[entry.key] = value;
    });

    await onSave(documentId, metadata);
  }, [entries, documentId, onSave]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pencil className="h-5 w-5 text-primary" />
            Editar Metadados do Documento
          </DialogTitle>
          <DialogDescription>
            Personalize metadados para <span className="font-medium">{documentName}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border bg-muted/30 p-4">
            <h4 className="mb-3 text-sm font-semibold text-foreground">
              Metadados Atuais
            </h4>
            {entries.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nenhum metadado. Adicione sua primeira entrada abaixo.
              </p>
            ) : (
              <div className="space-y-2">
                {entries.map((entry) => (
                  <div
                    key={entry.key}
                    className="flex items-center gap-3 rounded-md bg-background p-3"
                  >
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-medium text-foreground">
                          {entry.key}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {entry.type}
                        </Badge>
                      </div>
                      <Input
                        value={entry.value}
                        onChange={(e) => handleUpdateEntry(entry.key, e.target.value)}
                        className="h-8 text-sm"
                        placeholder="Valor"
                      />
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveEntry(entry.key)}
                      className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-lg border bg-muted/30 p-4">
            <h4 className="mb-3 text-sm font-semibold text-foreground">
              Adicionar Nova Entrada
            </h4>
            <div className="grid gap-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="new-key" className="text-xs">
                    Chave
                  </Label>
                  <Input
                    id="new-key"
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value)}
                    placeholder="ex: categoria, fonte"
                    className="h-9"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAddEntry();
                      }
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-type" className="text-xs">
                    Tipo
                  </Label>
                  <select
                    id="new-type"
                    value={newType}
                    onChange={(e) =>
                      setNewType(e.target.value as "string" | "number" | "boolean")
                    }
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    <option value="string">Texto</option>
                    <option value="number">Número</option>
                    <option value="boolean">Booleano</option>
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-value" className="text-xs">
                  Valor
                </Label>
                <div className="flex gap-2">
                  <Input
                    id="new-value"
                    value={newValue}
                    onChange={(e) => setNewValue(e.target.value)}
                    placeholder={
                      newType === "boolean"
                        ? "true ou false"
                        : newType === "number"
                        ? "123"
                        : "valor"
                    }
                    className="h-9"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAddEntry();
                      }
                    }}
                  />
                  <Button
                    type="button"
                    onClick={handleAddEntry}
                    disabled={!newKey.trim()}
                    size="sm"
                    className="shrink-0"
                  >
                    <Plus className="mr-1 h-4 w-4" />
                    Adicionar
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
          >
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <>Salvando...</>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Salvar Metadados
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default EditMetadataDialog;

