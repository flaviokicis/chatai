import React from "react";

interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  description?: string;
  icon?: React.ComponentType<{ className?: string }>;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, description, icon: Icon, actions }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="h-9 w-9 rounded-lg bg-primary/10 ring-1 ring-primary/20 grid place-items-center">
            <Icon className="h-5 w-5 text-primary" />
          </div>
        )}
        <div>
          {typeof title === "string" ? (
            <h1 className="text-xl md:text-2xl font-semibold tracking-tight">{title}</h1>
          ) : (
            <div className="text-xl md:text-2xl font-semibold tracking-tight">{title}</div>
          )}
          {subtitle && (
            <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
          )}
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex items-center gap-2">
          {actions}
        </div>
      )}
    </div>
  );
}
