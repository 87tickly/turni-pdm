import type { ReactNode } from "react";

/**
 * Pattern editoriale shared del 4° ruolo Gestione Personale (Sprint
 * 7.10 MR β.1): eyebrow mono uppercase + h1 grande Exo 2 + lede + cluster
 * azioni allineato a destra. Sostituisce il pattern "h1 + p" delle 5
 * route GP per aprire la pagina con più gerarchia visiva.
 *
 * Le classi `.gp-*` sono definite in `index.css`.
 */
interface EditorialHeadProps {
  eyebrow: string;
  /** Titolo pagina (Exo 2 800, 38px). Stringa o ReactNode per inserire `<span class="gp-num">N</span>`. */
  title: ReactNode;
  lede?: ReactNode;
  /** Cluster azioni allineato a destra (bottoni Esci/Esporta/Nuovo…). */
  actions?: ReactNode;
}

export function EditorialHead({ eyebrow, title, lede, actions }: EditorialHeadProps) {
  return (
    <div className="gp-page-head">
      <div className="min-w-0 flex-1">
        <div className="gp-eyebrow">{eyebrow}</div>
        <h1 className="gp-title">{title}</h1>
        {lede !== undefined && <p className="gp-lede">{lede}</p>}
      </div>
      {actions !== undefined && <div className="gp-page-head-actions">{actions}</div>}
    </div>
  );
}

/** Sotto-elemento `<span>` per inserire un numero/contatore allineato al titolo. */
export function EditorialNum({ children }: { children: ReactNode }) {
  return <span className="gp-num">{children}</span>;
}
