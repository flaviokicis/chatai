"use client";

import { useMemo } from "react";
import { FileText, Database, Hash, TrendingUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { DocumentSummary } from "@/lib/rag-admin";

interface StatsDashboardProps {
  documents: DocumentSummary[];
  isLoading: boolean;
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  trend?: string;
}

function StatCard({ icon, label, value, trend }: StatCardProps): React.JSX.Element {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium text-muted-foreground">{label}</p>
            <p className="text-2xl font-bold text-foreground">{value}</p>
            {trend && (
              <p className="text-xs text-muted-foreground">
                {trend}
              </p>
            )}
          </div>
          <div className="rounded-full bg-primary/10 p-3">
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsDashboard({ documents, isLoading }: StatsDashboardProps): React.JSX.Element {
  const stats = useMemo(() => {
    const totalChunks = documents.reduce((acc, doc) => acc + doc.chunkCount, 0);
    const totalSize = documents.reduce((acc, doc) => acc + (doc.fileSize ?? 0), 0);
    const avgChunksPerDoc = documents.length > 0 ? Math.round(totalChunks / documents.length) : 0;

    const formatSize = (bytes: number): string => {
      if (bytes === 0) return "0 B";
      const units = ["B", "KB", "MB", "GB"];
      let size = bytes;
      let unitIndex = 0;
      while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
      }
      return `${size.toFixed(1)} ${units[unitIndex]}`;
    };

    return {
      documentCount: documents.length,
      totalChunks,
      totalSize: formatSize(totalSize),
      avgChunks: avgChunksPerDoc,
    };
  }, [documents]);

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <div className="h-20 animate-pulse rounded-md bg-muted/50" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard
        icon={<FileText className="h-5 w-5 text-primary" />}
        label="Total de Documentos"
        value={stats.documentCount}
        trend={stats.documentCount === 0 ? "Nenhum documento ainda" : "Pronto para consultas"}
      />
      <StatCard
        icon={<Database className="h-5 w-5 text-primary" />}
        label="Total de Chunks"
        value={stats.totalChunks.toLocaleString()}
        trend={`${stats.avgChunks} média por documento`}
      />
      <StatCard
        icon={<Hash className="h-5 w-5 text-primary" />}
        label="Armazenamento"
        value={stats.totalSize}
        trend="Comprimido e indexado"
      />
      <StatCard
        icon={<TrendingUp className="h-5 w-5 text-primary" />}
        label="Média Chunks/Doc"
        value={stats.avgChunks}
        trend="Densidade de conhecimento"
      />
    </div>
  );
}

export default StatsDashboard;

