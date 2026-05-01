import { Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useDirettrici, useStazioni } from "@/hooks/useAnagrafiche";
import {
  CAMPI_REGOLA,
  CATEGORIE_COMUNI,
  GIORNI_TIPO,
  HINT_CAMPO,
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
    // Default op = "in" (multi-valore): scelta UX Sprint 7.6 MR 1, il
    // pianificatore tipicamente vuole una regola che copra più linee
    // contemporaneamente (es. tutte le linee di una sede).
    onChange([...filtri, { id: makeRowId(), campo: "direttrice", op: "in", valore: "" }]);
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
        const hint = HINT_CAMPO[row.campo];
        return (
          <div
            key={row.id}
            className="flex flex-col gap-2 rounded-md border border-border bg-white p-3"
          >
            <div className="grid grid-cols-12 items-end gap-2">
              <div className="col-span-4 flex flex-col gap-1">
                {idx === 0 && <Label className="text-xs">Campo</Label>}
                <Select
                  value={row.campo}
                  disabled={disabled}
                  onChange={(e) => {
                    const nuovoCampo = e.target.value as CampoRegola;
                    const opCompat = OP_PER_CAMPO[nuovoCampo];
                    // Cambio campo: preserva l'op corrente se è compatibile
                    // col nuovo campo (così non sovrascriviamo una scelta
                    // esplicita dell'utente, tipo "eq" su una regola
                    // caricata dal backend). Altrimenti preferisci "in"
                    // come default multi-valore.
                    const opPreferito = opCompat.includes(row.op)
                      ? row.op
                      : opCompat.includes("in")
                        ? "in"
                        : (opCompat[0] ?? "eq");
                    updateRow(idx, {
                      campo: nuovoCampo,
                      op: opPreferito,
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
            {hint !== undefined && (
              <p className="text-xs text-muted-foreground">{hint}</p>
            )}
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
 *
 * Per gli enumerati con op="in" (linea/categoria/giorno_tipo) usiamo
 * un pattern multi-select con chips: l'utente sceglie una opzione alla
 * volta da un dropdown e i selezionati appaiono come badge sopra (con
 * X per rimuoverli). Internamente la stringa è sempre CSV — il parsing
 * resta in `rowToPayload`.
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

  // Linea (= direttrice backend) multi: chips + dropdown.
  if (campo === "direttrice" && op === "in") {
    return (
      <MultiValueChips
        value={row.valore}
        disabled={disabled}
        options={direttrici}
        placeholder="+ aggiungi linea…"
        onChange={onChange}
      />
    );
  }

  // Linea singola: dropdown.
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

  // Stazione multi: chips
  if ((campo === "codice_origine" || campo === "codice_destinazione") && op === "in") {
    return (
      <MultiValueChips
        value={row.valore}
        disabled={disabled}
        options={stazioni}
        placeholder="+ aggiungi stazione…"
        onChange={onChange}
      />
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

  // Giorno tipo multi: chips
  if (campo === "giorno_tipo" && op === "in") {
    return (
      <MultiValueChips
        value={row.valore}
        disabled={disabled}
        options={[...GIORNI_TIPO]}
        placeholder="+ aggiungi giorno…"
        onChange={onChange}
      />
    );
  }

  // Categoria multi: chips con suggerimenti comuni
  if (campo === "categoria" && op === "in") {
    return (
      <MultiValueChips
        value={row.valore}
        disabled={disabled}
        options={[...CATEGORIE_COMUNI]}
        placeholder="+ aggiungi categoria…"
        allowCustom
        onChange={onChange}
      />
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

interface MultiValueChipsProps {
  value: string;
  disabled: boolean;
  options: string[];
  placeholder: string;
  /** Se true, accetta valori non presenti in `options` (input testo). */
  allowCustom?: boolean;
  onChange: (csv: string) => void;
}

/**
 * Multi-select compact: chips per i valori già scelti (rimovibili) +
 * dropdown a tendina con le opzioni residue. Internamente la stringa
 * è CSV per uniformità con il resto del sistema filtri.
 */
function MultiValueChips({
  value,
  disabled,
  options,
  placeholder,
  allowCustom = false,
  onChange,
}: MultiValueChipsProps) {
  const selected = value
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const remaining = options.filter((o) => !selected.includes(o));

  const removeAt = (idx: number) => {
    const next = selected.filter((_, i) => i !== idx);
    onChange(next.join(", "));
  };

  const addValue = (v: string) => {
    const trimmed = v.trim();
    if (trimmed.length === 0 || selected.includes(trimmed)) return;
    // La virgola e' separatore CSV: rifiutiamo valori che la contengono
    // per evitare che vengano riinterpretati come piu' valori al
    // prossimo `split(",")`. Caso reale solo per `allowCustom` (es.
    // categorie inserite a mano), gli enumerated sono safe.
    if (trimmed.includes(",")) return;
    onChange([...selected, trimmed].join(", "));
  };

  return (
    <div className="flex flex-col gap-1.5">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map((v, i) => (
            <Badge key={`${v}-${i}`} variant="secondary" className="gap-1 pr-1">
              <span className="font-normal">{v}</span>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20"
                  aria-label={`Rimuovi ${v}`}
                  title={`Rimuovi ${v}`}
                >
                  <X className="h-3 w-3" aria-hidden />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}
      <Select
        value=""
        disabled={disabled || (remaining.length === 0 && !allowCustom)}
        onChange={(e) => {
          if (e.target.value !== "") {
            addValue(e.target.value);
          }
        }}
      >
        <option value="">{placeholder}</option>
        {remaining.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </Select>
      {allowCustom && (
        <Input
          placeholder="Oppure digita e premi Invio…"
          disabled={disabled}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              const v = (e.target as HTMLInputElement).value;
              addValue(v);
              (e.target as HTMLInputElement).value = "";
            }
          }}
        />
      )}
    </div>
  );
}
