import { Construction } from "lucide-react"

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh]">
      <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mb-4">
        <Construction size={20} className="text-muted-foreground" />
      </div>
      <h2 className="text-[15px] font-medium">{title}</h2>
      <p className="text-[12px] text-muted-foreground mt-1">
        In costruzione
      </p>
    </div>
  )
}
