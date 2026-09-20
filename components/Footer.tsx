import Link from "next/link";
import { Brand } from "@/components/Nav";
import { REPO_URL } from "@/lib/data";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-top">
          <div><Brand /><p>Grandi idee. Nuove persone. La tua città.</p></div>
          <nav className="footer-links" aria-label="Link a fondo pagina">
            <Link href="/#events">Esplora</Link><Link href="/review">In revisione</Link><Link href="/privacy">Privacy</Link>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub <span aria-hidden="true">↗</span></a>
            <a href="#top">Torna su <span aria-hidden="true">↑</span></a>
          </nav>
        </div>
        <div className="footer-bottom">
          <span>Un progetto indipendente, fatto per chi costruisce.</span>
          <span className="footer-place"><svg className="footer-star" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M12 2v20M2 12h20M5 5l14 14M5 19 19 5" /></svg> Milano, Italia <span className="footer-coords">45.4642° N · 9.1900° E</span></span>
        </div>
      </div>
    </footer>
  );
}
