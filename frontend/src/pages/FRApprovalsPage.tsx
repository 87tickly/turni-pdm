/**
 * FR Approvals Page — Step 10 (23/04/2026).
 *
 * Pagina di gestione delle stazioni FR (dormita) approvate per ogni PdC.
 * L'utente sceglie il PdC dall'input, poi approva/revoca stazioni tramite
 * il pannello FRApprovalsPanel.
 */
import { useState } from "react"
import { FRApprovalsPanel } from "@/components/FRApprovalsPanel"


export function FRApprovalsPage() {
  const [pdcId, setPdcId] = useState("")

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold">Stazioni FR approvate</h1>
        <p
          className="text-[13px] mt-1"
          style={{ color: "var(--color-on-surface-muted)" }}
        >
          Gestisci per ogni PdC l'elenco delle stazioni dove e' autorizzata
          la dormita (FR). Il builder v4 usera' questo elenco per chiudere
          automaticamente le giornate senza rientro.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <label className="text-[13px] font-medium">PdC ID</label>
        <input
          type="text"
          value={pdcId}
          onChange={(e) => setPdcId(e.target.value)}
          placeholder="es. ALOR_C"
          className="flex-1 text-[13px] px-3 py-1.5 rounded border"
          style={{
            borderColor: "var(--color-outline-variant)",
            backgroundColor: "var(--color-surface-variant)",
          }}
        />
      </div>

      {pdcId ? (
        <FRApprovalsPanel pdcId={pdcId} />
      ) : (
        <div
          className="text-[13px] italic p-6 text-center rounded"
          style={{
            color: "var(--color-on-surface-muted)",
            backgroundColor: "var(--color-surface-variant)",
          }}
        >
          Inserisci un PdC ID per gestirne le FR approvate.
        </div>
      )}
    </div>
  )
}
