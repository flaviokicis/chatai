interface PageHeaderProps {
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

export function PageHeader({ title, description, icon: Icon }: PageHeaderProps) {
  return (
    <div className="mb-6 flex items-center gap-3">
      <div className="h-9 w-9 rounded-lg bg-primary/10 ring-1 ring-primary/20 grid place-items-center">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
