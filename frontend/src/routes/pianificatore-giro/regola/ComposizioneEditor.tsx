import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useMateriali } from "@/hooks/useAnagrafiche";
import { makeRowId, type ComposizioneRow } from "@/lib/regola/schema";

/**
 * Modo di composizione (Sprint 7.6 MR 1):
 *
 * - **singola**: 1 unità del materiale macro (es. 1×ETR526). UI =
 *   un solo dropdown materiale, `n_pezzi` nascosto (sempre 1).
 * - **doppia**: 2 unità accoppiate (anche di tipo diverso, es.
 *   ETR526+ETR425). UI = due dropdown materiale, `n_pezzi` nascosto
 *   (sempre 1 per ciascuno). Per la manutenzione i km vengono contati
 *   per ognuno dei due materiali.
 * - **personalizzata**: composizione libera (locomotiva + N carrozze
 *   tipo E464+5×Vivalto, o accoppiamenti speciali non ancora censiti).
 *   UI = N righe, `n_pezzi` editabile. Bypassa il check
 *   `materiale_accoppiamento_ammesso` (= il flag backend
 *   `is_composizione_manuale=true`).
 */
export type ModoComposizione = "singola" | "doppia" | "personalizzata";

interface ComposizioneEditorProps {
  composizione: ComposizioneRow[];
  onChange: (composizione: ComposizioneRow[]) => void;
  modo: ModoComposizione;
  disabled?: boolean;
}

/**
 * Builder della composizione: lista di {materiale, n_pezzi}.
 *
 * Min 1 elemento (validato dal backend, qui non blocchiamo per
 * permettere la rimozione e ricostruzione fluida — il submit del
 * RegolaEditor garantisce length >= 1).
 *
 * Esempi (convenzione: 1 unità = 1 riga con n_pezzi=1):
 *   [{ETR526, 1}, {ETR425, 1}]              doppia mista (526+425)
 *   [{ATR803, 1}]                            singola (Cremona)
 *   [{ETR526, 1}, {ETR526, 1}]              doppia uguale (526+526)
 *   [{E464, 1}, {Vivalto, 5}]               personalizzata (loco + 5 carrozze)
 */
export function ComposizioneEditor({
  composizione,
  onChange,
  modo,
  disabled = false,
}: ComposizioneEditorProps) {
  const materialiQuery = useMateriali();
  // Solo i materiali "macro" (con famiglia valorizzata) sono selezionabili.
  // I pezzi atomici (E464N, TN-Ale526-A41, …) non sono assegnabili
  // direttamente a una regola — sono inclusi nei macro (es. MD include
  // E464 + carrozze; ETR526 include TN-Ale526-A41/A42/…).
  const materiali = (materialiQuery.data ?? []).filter(
    (m) => m.famiglia !== null && m.famiglia.length > 0,
  );

  const updateRow = (idx: number, patch: Partial<ComposizioneRow>) => {
    onChange(composizione.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const removeRow = (idx: number) => {
    onChange(composizione.filter((_, i) => i !== idx));
  };

  const addRow = () => {
    const primoMateriale = materiali[0]?.codice ?? "";
    onChange([
      ...composizione,
      { id: makeRowId(), materiale_tipo_codice: primoMateriale, n_pezzi: 1 },
    ]);
  };

  // Etichette dei dropdown: per Doppia distinguiamo "Materiale 1" / "Materiale 2".
  const labelMateriale = (idx: number): string => {
    if (modo === "doppia") return idx === 0 ? "Materiale 1" : "Materiale 2";
    return "Materiale";
  };

  // In Singola/Doppia n_pezzi è sempre 1 e l'input non è editabile.
  // In Personalizzata l'utente può alzare la quantità (carrozze, ecc).
  const showPezzi = modo === "personalizzata";

  // In Singola/Doppia la struttura è fissa: niente bottone Aggiungi/Rimuovi.
  const allowStructEdit = modo === "personalizzata";

  return (
    <div className="flex flex-col gap-3">
      {composizione.length === 0 && (
        <p className="rounded-md border border-dashed border-destructive/40 bg-destructive/5 px-3 py-3 text-sm text-destructive">
          Composizione vuota: aggiungi almeno un materiale per pubblicare la regola.
        </p>
      )}

      {composizione.map((row, idx) => (
        <div
          key={row.id}
          className="grid grid-cols-12 items-end gap-2 rounded-md border border-border bg-white p-3"
        >
          <div className={showPezzi ? "col-span-7 flex flex-col gap-1" : "col-span-11 flex flex-col gap-1"}>
            {(idx === 0 || modo === "doppia") && (
              <Label className="text-xs">{labelMateriale(idx)}</Label>
            )}
            <Select
              value={row.materiale_tipo_codice}
              disabled={disabled}
              onChange={(e) => updateRow(idx, { materiale_tipo_codice: e.target.value })}
            >
              <option value="">— seleziona —</option>
              {Object.entries(
                materiali.reduce<Record<string, typeof materiali>>((acc, m) => {
                  const fam = m.famiglia ?? "Altro";
                  acc[fam] = acc[fam] ?? [];
                  acc[fam].push(m);
                  return acc;
                }, {}),
              )
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([famiglia, items]) => (
                  <optgroup key={famiglia} label={famiglia}>
                    {items.map((m) => (
                      <option key={m.codice} value={m.codice}>
                        {m.codice}
                        {m.nome_commerciale !== null && m.nome_commerciale !== ""
                          ? ` — ${m.nome_commerciale}`
                          : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
            </Select>
          </div>

          {showPezzi && (
            <div className="col-span-4 flex flex-col gap-1">
              {idx === 0 && <Label className="text-xs">N. pezzi</Label>}
              <Input
                type="number"
                min={1}
                value={row.n_pezzi}
                disabled={disabled}
                onChange={(e) =>
                  updateRow(idx, {
                    n_pezzi: Math.max(1, Number.parseInt(e.target.value, 10) || 1),
                  })
                }
              />
            </div>
          )}

          {allowStructEdit && (
            <div className="col-span-1 flex justify-end">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeRow(idx)}
                disabled={disabled}
                aria-label="Rimuovi materiale"
                title="Rimuovi materiale"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          )}
        </div>
      ))}

      {allowStructEdit && (
        <Button
          variant="outline"
          size="sm"
          onClick={addRow}
          disabled={disabled || materiali.length === 0}
          className="self-start"
        >
          <Plus className="mr-1.5 h-4 w-4" aria-hidden /> Aggiungi materiale
        </Button>
      )}

      {modo === "doppia" && (
        <p className="text-xs text-muted-foreground">
          Composizione doppia: il chilometraggio sarà contato per ognuno dei due materiali (utile
          per la pianificazione manutenzione).
        </p>
      )}
    </div>
  );
}
