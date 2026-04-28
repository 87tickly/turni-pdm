import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useMateriali } from "@/hooks/useAnagrafiche";
import { makeRowId, type ComposizioneRow } from "@/lib/regola/schema";

interface ComposizioneEditorProps {
  composizione: ComposizioneRow[];
  onChange: (composizione: ComposizioneRow[]) => void;
  disabled?: boolean;
}

/**
 * Builder della composizione: lista di {materiale, n_pezzi}.
 *
 * Min 1 elemento (validato dal backend, qui non blocchiamo per
 * permettere la rimozione e ricostruzione fluida — il submit del
 * RegolaEditor garantisce length >= 1).
 *
 * Esempi:
 *   [{ETR526, 1}, {ETR425, 1}]  composizione doppia (Mi.Centrale-Tirano)
 *   [{ATR803, 1}]                singolo materiale (Cremona)
 */
export function ComposizioneEditor({
  composizione,
  onChange,
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
          <div className="col-span-7 flex flex-col gap-1">
            {idx === 0 && <Label className="text-xs">Materiale</Label>}
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
        </div>
      ))}

      <Button
        variant="outline"
        size="sm"
        onClick={addRow}
        disabled={disabled || materiali.length === 0}
        className="self-start"
      >
        <Plus className="mr-1.5 h-4 w-4" aria-hidden /> Aggiungi materiale
      </Button>
    </div>
  );
}
