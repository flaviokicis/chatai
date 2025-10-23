"use client";

import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, File, X, Loader2, CheckCircle2, AlertCircle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type UploadStep = "uploading" | "processing" | "chunking" | "embedding" | "complete";

interface UploadFile {
  file: File;
  id: string;
  status: "pending" | "uploading" | "success" | "error";
  currentStep?: UploadStep;
  error?: string;
  chunksCreated?: number;
  totalWords?: number;
}

interface UploadZoneProps {
  onUpload: (file: File) => Promise<{ success: boolean; chunksCreated: number; totalWords: number; error?: string; message?: string }>;
  onUploadComplete?: () => void;
  disabled?: boolean;
  maxFiles?: number;
}

export function UploadZone({ onUpload, onUploadComplete, disabled = false, maxFiles = 50 }: UploadZoneProps): React.JSX.Element {
  const [files, setFiles] = useState<UploadFile[]>([]);

  const validateFile = (file: File): string | null => {
    console.log('[UploadZone] Validating file:', file.name, 'type:', file.type, 'size:', file.size);
    const validTypes = ["application/pdf", "text/plain", "text/markdown", "application/json"];
    const validExtensions = [".pdf", ".txt", ".md", ".json"];
    
    const hasValidExtension = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
    const hasValidType = validTypes.includes(file.type);
    
    if (!hasValidExtension && !hasValidType) {
      console.log('[UploadZone] File rejected - invalid type');
      return "Tipo de arquivo não suportado. Use PDF, TXT, MD ou JSON.";
    }
    
    if (file.size > 10 * 1024 * 1024) {
      console.log('[UploadZone] File rejected - too large');
      return "Arquivo muito grande. Máximo: 10MB.";
    }
    
    console.log('[UploadZone] File validation passed');
    return null;
  };

  const handleUploadFile = useCallback(async (uploadFile: UploadFile) => {
    console.log('[UploadZone] handleUploadFile called for:', uploadFile.file.name);
    setFiles(prev => prev.map(f => 
      f.id === uploadFile.id ? { ...f, status: "uploading", currentStep: "uploading" } : f
    ));

    const stepInterval = setInterval(() => {
      setFiles(prev => prev.map(f => {
        if (f.id !== uploadFile.id || f.status !== "uploading") return f;
        
        const steps: UploadStep[] = ["uploading", "processing", "chunking", "embedding"];
        const currentIndex = steps.indexOf(f.currentStep || "uploading");
        const nextIndex = Math.min(currentIndex + 1, steps.length - 1);
        
        return { ...f, currentStep: steps[nextIndex] };
      }));
    }, 3000);

    try {
      console.log('[UploadZone] Calling onUpload callback for:', uploadFile.file.name);
      const result = await onUpload(uploadFile.file);
      console.log('[UploadZone] Upload result:', result);
      
      clearInterval(stepInterval);

      if (result.success) {
        setFiles(prev => prev.map(f => 
          f.id === uploadFile.id 
            ? { ...f, status: "success", currentStep: "complete", chunksCreated: result.chunksCreated, totalWords: result.totalWords } 
            : f
        ));

        onUploadComplete?.();

        setTimeout(() => {
          setFiles(prev => prev.filter(f => f.id !== uploadFile.id));
        }, 5000);
      } else {
        setFiles(prev => prev.map(f => 
          f.id === uploadFile.id 
            ? { ...f, status: "error", error: result.error || result.message || "Upload failed" } 
            : f
        ));
      }
    } catch (error) {
      clearInterval(stepInterval);
      setFiles(prev => prev.map(f => 
        f.id === uploadFile.id 
          ? { ...f, status: "error", error: error instanceof Error ? error.message : "Upload failed" } 
          : f
      ));
    }
  }, [onUpload, onUploadComplete]);

  const onDrop = useCallback((acceptedFiles: File[], rejectedFiles: any[]) => {
    console.log('[UploadZone] onDrop called - acceptedFiles:', acceptedFiles.length, 'rejectedFiles:', rejectedFiles.length);
    console.log('[UploadZone] Current files in state:', files.length, 'maxFiles:', maxFiles);
    
    const allNewFiles: UploadFile[] = [];
    
    if (rejectedFiles.length > 0) {
      console.log('[UploadZone] Rejected files:', rejectedFiles);
      rejectedFiles.forEach((rejection, index) => {
        console.log(`[UploadZone] Rejected file ${index + 1}:`, {
          name: rejection.file?.name,
          type: rejection.file?.type,
          size: rejection.file?.size,
          errors: rejection.errors
        });
        
        const errorMessages = rejection.errors?.map((e: any) => {
          if (e.code === 'file-invalid-type') return 'Tipo de arquivo não suportado';
          if (e.code === 'file-too-large') return 'Arquivo muito grande (máx 10MB)';
          if (e.code === 'too-many-files') return 'Muitos arquivos selecionados';
          return e.message || 'Erro desconhecido';
        }).join(', ') || 'Arquivo rejeitado';
        
        allNewFiles.push({
          file: rejection.file,
          id: `${Date.now()}-${Math.random()}-${index}`,
          status: "error",
          error: errorMessages,
        });
      });
    }
    
    const filesToAdd = acceptedFiles.slice(0, maxFiles - files.length);
    console.log('[UploadZone] Files to add:', filesToAdd.length);

    filesToAdd.forEach((file) => {
      const error = validateFile(file);
      allNewFiles.push({
        file,
        id: `${Date.now()}-${Math.random()}`,
        status: error ? "error" : "pending",
        error: error || undefined,
      });
    });

    console.log('[UploadZone] New files created:', allNewFiles.length);
    setFiles(prev => [...prev, ...allNewFiles]);

    allNewFiles.forEach(uploadFile => {
      if (uploadFile.status !== "error") {
        console.log('[UploadZone] Starting upload for:', uploadFile.file.name);
        void handleUploadFile(uploadFile);
      }
    });
  }, [files.length, maxFiles, handleUploadFile, validateFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'application/json': ['.json'],
    },
    maxSize: 10 * 1024 * 1024,
    maxFiles,
    disabled: disabled || files.length >= maxFiles,
    multiple: true,
    onDragEnter: () => console.log('[UploadZone] Drag enter detected'),
    onDragLeave: () => console.log('[UploadZone] Drag leave detected'),
    onDropAccepted: (files) => console.log('[UploadZone] Drop accepted:', files.length, 'files'),
    onDropRejected: (fileRejections) => console.log('[UploadZone] Drop rejected:', fileRejections),
  });
  
  console.log('[UploadZone] Render - isDragActive:', isDragActive, 'disabled:', disabled, 'files.length:', files.length);

  const removeFile = useCallback((id: string) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  }, []);

  const getStepLabel = (step: UploadStep | undefined): string => {
    switch (step) {
      case "uploading": return "Enviando arquivo";
      case "processing": return "Processando PDF";
      case "chunking": return "Analisando com IA (GPT-5)";
      case "embedding": return "Gerando embeddings";
      case "complete": return "Concluído";
      default: return "Preparando";
    }
  };

  const hasActiveUploads = files.some(f => f.status === "uploading");

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={cn(
          "relative border-2 border-dashed rounded-lg p-8 transition-all duration-200 cursor-pointer",
          isDragActive && !disabled
            ? "border-primary bg-primary/5 scale-[1.01] shadow-lg"
            : "border-border hover:border-primary/50 hover:bg-accent/30",
          disabled && "opacity-50 cursor-not-allowed",
          files.length >= maxFiles && "opacity-60 cursor-not-allowed"
        )}
      >
        <input {...getInputProps()} />

        <div className="flex flex-col items-center justify-center text-center">
          <div className={cn(
            "rounded-full p-4 mb-4 transition-all duration-200",
            isDragActive ? "bg-primary/20 scale-110" : "bg-primary/10"
          )}>
            <Upload className={cn(
              "h-8 w-8 transition-colors",
              isDragActive ? "text-primary" : "text-muted-foreground"
            )} />
          </div>
          
          <h3 className="text-lg font-semibold mb-2">
            {isDragActive ? "Solte os arquivos aqui" : "Arraste arquivos ou clique para selecionar"}
          </h3>
          
          <p className="text-sm text-muted-foreground mb-4">
            PDF, TXT, Markdown ou JSON • Até {maxFiles} arquivos por vez • Máximo 10MB cada
          </p>

          <Button
            type="button"
            disabled={disabled || files.length >= maxFiles}
            variant="outline"
            size="sm"
          >
            <File className="mr-2 h-4 w-4" />
            Selecionar Arquivos
          </Button>

          {files.length > 0 && (
            <p className="text-xs text-muted-foreground mt-4">
              {files.length} / {maxFiles} {files.length === 1 ? "arquivo" : "arquivos"}
            </p>
          )}
        </div>
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-foreground">
              {hasActiveUploads ? "Enviando arquivos..." : "Arquivos"}
            </p>
            {files.some(f => f.status === "error" || f.status === "pending") && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setFiles(prev => prev.filter(f => f.status === "uploading" || f.status === "success"))}
                className="text-xs h-7"
              >
                Limpar com erro
              </Button>
            )}
          </div>

          {files.map((uploadFile) => (
            <div
              key={uploadFile.id}
              className={cn(
                "flex items-center gap-3 p-4 rounded-lg border transition-all duration-200",
                uploadFile.status === "success" && "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800",
                uploadFile.status === "error" && "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800",
                uploadFile.status === "uploading" && "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800 shadow-sm",
                uploadFile.status === "pending" && "bg-muted/50 border-border"
              )}
            >
              <div className="flex-shrink-0">
                {uploadFile.status === "uploading" && (
                  <Loader2 className="h-5 w-5 animate-spin text-blue-600 dark:text-blue-400" />
                )}
                {uploadFile.status === "success" && (
                  <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                )}
                {uploadFile.status === "error" && (
                  <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                )}
                {uploadFile.status === "pending" && (
                  <File className="h-5 w-5 text-muted-foreground" />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate text-foreground">
                  {uploadFile.file.name}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <p className="text-xs text-muted-foreground">
                    {(uploadFile.file.size / 1024).toFixed(1)} KB
                  </p>
                  {uploadFile.status === "success" && uploadFile.chunksCreated !== undefined && (
                    <>
                      <span className="text-xs text-muted-foreground">•</span>
                      <p className="text-xs text-green-600 dark:text-green-400 font-medium">
                        {uploadFile.chunksCreated} chunks • {uploadFile.totalWords?.toLocaleString()} palavras
                      </p>
                    </>
                  )}
                  {uploadFile.status === "error" && uploadFile.error && (
                    <>
                      <span className="text-xs text-muted-foreground">•</span>
                      <p className="text-xs text-red-600 dark:text-red-400">{uploadFile.error}</p>
                    </>
                  )}
                  {uploadFile.status === "uploading" && uploadFile.currentStep && (
                    <>
                      <span className="text-xs text-muted-foreground">•</span>
                      <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                        {getStepLabel(uploadFile.currentStep)}
                      </p>
                    </>
                  )}
                </div>
                {uploadFile.status === "uploading" && (
                  <div className="mt-3 space-y-1.5">
                    {(["uploading", "processing", "chunking", "embedding"] as UploadStep[]).map((step) => {
                      const steps: UploadStep[] = ["uploading", "processing", "chunking", "embedding"];
                      const currentIndex = steps.indexOf(uploadFile.currentStep || "uploading");
                      const stepIndex = steps.indexOf(step);
                      const isActive = stepIndex === currentIndex;
                      const isComplete = stepIndex < currentIndex;
                      
                      return (
                        <div key={step} className="flex items-center gap-2">
                          <div className={cn(
                            "flex h-5 w-5 items-center justify-center rounded-full transition-all",
                            isComplete && "bg-green-600 dark:bg-green-500",
                            isActive && "bg-blue-600 dark:bg-blue-500 animate-pulse",
                            !isComplete && !isActive && "bg-border"
                          )}>
                            {isComplete ? (
                              <Check className="h-3 w-3 text-white" />
                            ) : isActive ? (
                              <Loader2 className="h-3 w-3 text-white animate-spin" />
                            ) : (
                              <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
                            )}
                          </div>
                          <span className={cn(
                            "text-xs transition-colors",
                            isActive && "text-blue-600 dark:text-blue-400 font-semibold",
                            isComplete && "text-green-600 dark:text-green-400",
                            !isComplete && !isActive && "text-muted-foreground"
                          )}>
                            {getStepLabel(step)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {(uploadFile.status === "error" || uploadFile.status === "pending") && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(uploadFile.id);
                  }}
                  className="flex-shrink-0 hover:bg-destructive/10 hover:text-destructive"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default UploadZone;

