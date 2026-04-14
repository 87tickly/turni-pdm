import { Construction } from "lucide-react"

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
      <Construction size={48} className="mb-4 opacity-30" />
      <h2 className="text-lg font-medium text-foreground">{title}</h2>
      <p className="text-sm mt-1">Sezione in costruzione</p>
    </div>
  )
}
