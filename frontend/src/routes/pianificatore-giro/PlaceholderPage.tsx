import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";

interface PlaceholderPageProps {
  title: string;
  description: string;
  sub: string;
  endpoint: string;
}

/** Pagina segnaposto per le sub 6.2-6.5 — costruite dopo Sub 6.1. */
export function PlaceholderPage({ title, description, sub, endpoint }: PlaceholderPageProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{sub} — in arrivo</CardTitle>
          <CardDescription>
            Questa pagina sarà costruita nella sottosprint successiva. Endpoint backend:
          </CardDescription>
        </CardHeader>
        <CardContent>
          <code className="block rounded-md bg-secondary px-3 py-2 font-mono text-xs">
            {endpoint}
          </code>
        </CardContent>
      </Card>
    </div>
  );
}
