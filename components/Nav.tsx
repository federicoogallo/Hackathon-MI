import Link from "next/link";

// La Madonnina del Duomo: figura dorata con aureola di stelle, manto e braccia
// aperte, su una nuvoletta — silhouette stilizzata ispirata alla statua.
const Logo = (
  <svg viewBox="0 0 24 24" fill="none">
    <defs>
      <linearGradient id="madonnina" x1="12" y1="2" x2="12" y2="22" gradientUnits="userSpaceOnUse">
        <stop stopColor="#ffedb6" />
        <stop offset="0.5" stopColor="#f0bf62" />
        <stop offset="1" stopColor="#cf9236" />
      </linearGradient>
    </defs>
    {/* aureola di stelle */}
    <g fill="url(#madonnina)">
      <circle cx="12" cy="2.3" r="0.62" />
      <circle cx="9.3" cy="2.75" r="0.54" />
      <circle cx="14.7" cy="2.75" r="0.54" />
      <circle cx="7.05" cy="3.95" r="0.48" />
      <circle cx="16.95" cy="3.95" r="0.48" />
      <circle cx="5.5" cy="5.75" r="0.42" />
      <circle cx="18.5" cy="5.75" r="0.42" />
    </g>
    {/* capo velato */}
    <circle cx="12" cy="6.85" r="1.5" fill="url(#madonnina)" />
    {/* manto che scende e si allarga */}
    <path
      fill="url(#madonnina)"
      d="M10.35 8.5c-0.85 0.62-1.28 1.7-1.4 2.95l-0.78 8.05c-0.07 0.72 0.5 1.28 1.2 1.1 0.83-0.2 1.7-0.3 2.63-0.3s1.8 0.1 2.63 0.3c0.7 0.18 1.27-0.38 1.2-1.1l-0.78-8.05c-0.12-1.25-0.55-2.33-1.4-2.95-0.9-0.66-2.23-0.66-3.12 0Z"
    />
    {/* braccia aperte (accoglienza) */}
    <g stroke="url(#madonnina)" strokeWidth="1.5" strokeLinecap="round">
      <path d="M10.45 9.6C8.95 10.2 7.95 11.35 7.4 12.9" />
      <path d="M13.55 9.6C15.05 10.2 16.05 11.35 16.6 12.9" />
    </g>
    {/* nuvoletta alla base */}
    <path
      fill="url(#madonnina)"
      opacity="0.92"
      d="M8.4 20.5c-1 0-1.6 0.9-1.3 1.5h9.8c0.3-0.6-0.3-1.5-1.3-1.5-0.25-0.7-1.05-0.95-1.7-0.5-0.5-0.7-1.6-0.7-2.1 0-0.65-0.45-1.45-0.2-1.7 0.5-0.5-0.02-0.9 0.12-1.4-0.5Z"
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
