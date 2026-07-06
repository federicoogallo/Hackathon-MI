import Link from "next/link";

// La Madonnina del Duomo: figura aureolata dorata con raggi.
const Logo = (
  <svg viewBox="0 0 24 24" fill="none">
    <defs>
      <linearGradient id="madonnina" x1="12" y1="1.5" x2="12" y2="21.5" gradientUnits="userSpaceOnUse">
        <stop stopColor="#ffe9b0" />
        <stop offset="0.55" stopColor="#f2c46a" />
        <stop offset="1" stopColor="#d59a3d" />
      </linearGradient>
    </defs>
    {/* raggi dell'aureola */}
    <g stroke="url(#madonnina)" strokeWidth="1.1" strokeLinecap="round">
      <path d="M12 1.6V3.1" />
      <path d="M8.7 2.3l.6 1.4" />
      <path d="M15.3 2.3l-.6 1.4" />
      <path d="M6 4l1.1 1" />
      <path d="M18 4l-1.1 1" />
    </g>
    {/* capo */}
    <circle cx="12" cy="6.1" r="1.75" fill="url(#madonnina)" />
    {/* manto/veste che si allarga, con mani giunte accennate */}
    <path
      fill="url(#madonnina)"
      d="M12 8.1c-1.6 0-2.6 1.05-2.86 2.5l-.28 1.6c-.12.66-.55 1.02-1.05 1.28-.5.26-.36.98.2.98l.86-.05-1.06 5.9c-.12.66.42 1.2 1.06 1.02 1.02-.28 2.04-.43 3.08-.43s2.06.15 3.08.43c.64.18 1.18-.36 1.06-1.02l-1.06-5.9.86.05c.56 0 .7-.72.2-.98-.5-.26-.93-.62-1.05-1.28l-.28-1.6C14.6 9.15 13.6 8.1 12 8.1Z"
    />
  </svg>
);

export default function Nav({
  brandTitle, brandSub, brandHref, children,
}: {
  brandTitle: string;
  brandSub: string;
  brandHref: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <div className="scroll-progress" id="scroll-progress" />
      <nav className="nav-fixed" id="nav" aria-label="Navigazione principale">
        <div className="container">
          <div className="nav">
            <Link className="brand" href={brandHref}>
              <span className="brand-mark">{Logo}</span>
              <span><b>{brandTitle}</b><span>{brandSub}</span></span>
            </Link>
            <div className="nav-actions">{children}</div>
          </div>
        </div>
      </nav>
    </>
  );
}
