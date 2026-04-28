import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useDirettrici, useStazioni } from "@/hooks/useAnagrafiche";
import {
  CAMPI_REGOLA,
  CATEGORIE_COMUNI,
  GIORNI_TIPO,
  LABEL_CAMPO,
  LABEL_OP,
  OP_PER_CAMPO,
  makeRowId,
  type CampoRegola,
  type FiltroRow,
} from "@/lib/regola/schema";

interface FiltriEditorProps {
  filtri: FiltroRow[];
  onChange: (filtri: FiltroRow[]) => void;
  disabled?: boolean;
}

/**
 * Builder visuale di filtri di una regola.
 *
 * Una "riga" = {campo, op, valore}. Cambiando campo, l'op si reset al
 * primo compatibile e valore si svuota. Il widget del valore cambia in
 * base alla coppia (campo, op).
 *
 * NB: `valore` è sempre stringa qui — la conversione in tipo backend
 * (lista/bool/etc) avviene nel submit della regola via `rowToPayload`.
 */
export function FiltriEditor({ filtri, onChange, disabled = false }: FiltriEditorProps) {
  const direttriciQuery = useDirettrici();
  const stazioniQuery = useStazioni();

  const updateRow = (idx: number, patch: Partial<FiltroRow>) => {
    const next = filtri.map((r, i) => (i === idx ? { ...r, ...patch } : r));
    onChange(next);
  };

  const removeRow = (idx: number) => {
    onChange(filtri.filter((_, i) => i !== idx));
  };

  const addRow = () => {
    onChange([...filtri, { id: makeRowId(), campo: "direttrice", op: "eq", valore: "" }]);
  };

  return (
    <div className="flex flex-col gap-3">
      {filtri.length === 0 ? (
        <p className="rounded-md border border-dashed border-border bg-secondary/40 px-3 py-3 text-sm text-muted-foreground">
          Nessun filtro: la regola si applica a tutte le corse del programma. Aggiungi un filtro per
          restringere (es. solo direttrice X, solo categoria REG).
        </p>
      ) : filtri.length > 1 ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <strong>Filtri multipli = AND.</strong> Una corsa deve soddisfare TUTTI i filtri per
          essere coperta. Per "una direttrice tra X, Y, Z" usa <em>un solo</em> filtro con operatore{" "}
          <code className="rounded bg-amber-100 px-1">tra le opzioni</code>.
        </p>
      ) : null}

      {filtri.map((row, idx) => {
        const opsAvailable = OP_PER_CAMPO[row.campo];
        return (
          <div
            key={row.id}
            className="grid grid-cols-12 items-end gap-2 rounded-md border border-border bg-white p-3"
          >
            <div className="col-span-4 flex flex-col gap-1">
              {idx === 0 && <Label className="text-xs">Campo</Label>}
              <Select
                value={row.campo}
                disabled={disabled}
                onChange={(e) => {
                  const nuovoCampo = e.target.value as CampoRegola;
                  const opCompat = OP_PER_CAMPO[nuovoCampo];
                  updateRow(idx, {
                    campo: nuovoCampo,
                    op: opCompat[0] ?? "eq",
                    valore: "",
                  });
                }}
              >
                {CAMPI_REGOLA.map((c) => (
                  <option key={c} value={c}>
                    {LABEL_CAMPO[c]}
                  </option>
                ))}
              </Select>
            </div>

            <div className="col-span-3 flex flex-col gap-1">
              {idx === 0 && <Label className="text-xs">Operatore</Label>}
              <Select
                value={row.op}
                disabled={disabled || opsAvailable.length === 1}
                onChange={(e) => updateRow(idx, { op: e.target.value, valore: "" })}
              >
                {opsAvailable.map((op) => (
                  <option key={op} value={op}>
                    {LABEL_OP[op] ?? op}
                  </option>
                ))}
              </Select>
            </div>

            <div className="col-span-4 flex flex-col gap-1">
              {idx === 0 && <Label className="text-xs">Valore</Label>}
              <ValueInput
                row={row}
                disabled={disabled}
                direttrici={direttriciQuery.data ?? []}
                stazioni={(stazioniQuery.data ?? []).map((s) => s.codice)}
                onChange={(valore) => updateRow(idx, { valore })}
              />
            </div>

            <div className="col-span-1 flex justify-end">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeRow(idx)}
                disabled={disabled}
                aria-label="Rimuovi filtro"
                title="Rimuovi filtro"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          </div>
        );
      })}

      <Button
        variant="outline"
        size="sm"
        onClick={addRow}
        disabled={disabled}
        className="self-start"
      >
        <Plus className="mr-1.5 h-4 w-4" aria-hidden /> Aggiungi filtro
      </Button>
    </div>
  );
}

interface ValueInputProps {
  row: FiltroRow;
  disabled: boolean;
  direttrici: string[];
  stazioni: string[];
  onChange: (valore: string) => void;
}

/**
 * Widget del valore: cambia in base a (campo, op). Sempre legge/scrive
 * stringhe — il parsing finale (CSV → array, "true" → bool) avviene a
 * submit time.
 */
function ValueInput({ row, disabled, direttrici, stazioni, onChange }: ValueInputProps) {
  const { campo, op } = row;
  const isList = op === "in" || op === "between";

  // Booleano: select sì/no
  if (campo === "is_treno_garantito_feriale" || campo === "is_treno_garantito_festivo") {
    return (
      <Select
        value={row.valore || "true"}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="true">Sì</option>
        <option value="false">No</option>
      </Select>
    );
  }

  // Direttrice singola: dropdown da anagrafica
  if (campo === "direttrice" && op === "eq") {
    return (
      <Select value={row.valore} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">— seleziona —</option>
        {direttrici.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </Select>
    );
  }

  // Stazione singola: dropdown
  if ((campo === "codice_origine" || campo === "codice_destinazione") && op === "eq") {
    return (
      <Select value={row.valore} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">— seleziona —</option>
        {stazioni.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>
    );
  }

  // Giorno tipo singolo
  if (campo === "giorno_tipo" && op === "eq") {
    return (
      <Select value={row.valore} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">— seleziona —</option>
        {GIORNI_TIPO.map((g) => (
          <option key={g} value={g}>
            {g}
          </option>
        ))}
      </Select>
    );
  }

  // Categoria singola: input con datalist (suggerimenti comuni, libero
  // perché può estendersi via dato)
  if (campo === "categoria" && op === "eq") {
    return (
      <>
        <Input
          list="categorie-comuni"
          value={row.valore}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Es. REG"
        />
        <datalist id="categorie-comuni">
          {CATEGORIE_COMUNI.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </>
    );
  }

  // Fascia oraria + between → "HH:MM, HH:MM"
  if (campo === "fascia_oraria" && op === "between") {
    return (
      <Input
        value={row.valore}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        placeholder="04:00, 15:59"
      />
    );
  }

  // Fascia oraria + gte/lte → time
  if (campo === "fascia_oraria") {
    return (
      <Input
        type="time"
        value={row.valore}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  // Liste con `in` (csv): input testo libero, suggerimento dei separatori.
  return (
    <Input
      value={row.valore}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      placeholder={isList ? "Valore1, Valore2, …" : "Valore"}
    />
  );
}
