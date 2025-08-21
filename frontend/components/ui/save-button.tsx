"use client";

import { CheckCheck, Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, ButtonProps } from "./button";

interface SaveButtonProps extends Omit<ButtonProps, "children"> {
  isLoading?: boolean;
  isSuccess?: boolean;
  hasChanges?: boolean;
  onSave?: () => void;
  children?: React.ReactNode;
}

export function SaveButton({ 
  isLoading = false, 
  isSuccess = false, 
  hasChanges = false,
  onSave,
  children,
  disabled,
  className = "",
  ...props 
}: SaveButtonProps) {
  const [showSuccess, setShowSuccess] = useState(false);

  // Handle success animation timing
  useEffect(() => {
    if (isSuccess && !isLoading) {
      setShowSuccess(true);
      const timer = setTimeout(() => setShowSuccess(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [isSuccess, isLoading]);

  const getButtonContent = () => {
    if (isLoading) {
      return (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          Salvando...
        </>
      );
    }
    
    if (showSuccess) {
      return (
        <>
          <CheckCheck className="h-4 w-4 text-green-600 animate-bounce-in" />
          Salvo!
        </>
      );
    }
    
    return children || (
      <>
        <Save className="h-4 w-4" />
        Salvar configurações globais
      </>
    );
  };

  const getButtonVariant = () => {
    if (showSuccess) return "outline";
    return "default";
  };

  const getButtonClassName = () => {
    let baseClasses = "gap-2 transition-all duration-200";
    
    if (showSuccess) {
      baseClasses += " border-green-200 bg-green-50 text-green-800 hover:bg-green-100 dark:border-green-700 dark:bg-green-950 dark:text-green-200";
    }
    
    return `${baseClasses} ${className}`;
  };

  return (
    <Button
      variant={getButtonVariant()}
      disabled={disabled || isLoading || !hasChanges}
      onClick={onSave}
      className={getButtonClassName()}
      {...props}
    >
      {getButtonContent()}
    </Button>
  );
}
