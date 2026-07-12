// Barra di navigazione minimale: nessun marchio/simbolo/testo a sinistra
// (richiesta esplicita), solo le azioni a destra su vetro. L'identita' visiva
// (Madonnina) vive nel favicon (app/icon.svg).
export default function Nav({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="scroll-progress" id="scroll-progress" />
      <nav className="nav-fixed" id="nav" aria-label="Navigazione principale">
        <div className="container">
          <div className="nav">
            <div className="nav-actions">{children}</div>
          </div>
        </div>
      </nav>
    </>
  );
}
